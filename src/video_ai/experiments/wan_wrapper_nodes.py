"""Three experiment-only nodes registered after the fixed Wrapper initialises."""
from __future__ import annotations
from contextlib import contextmanager
import gc
import importlib
import json
from pathlib import Path
import threading
import time

from .wan_fast_profiles import digest,write_once
from .wan_fast_experiment import read
from .wan_wrapper_backend import WrapperProfile,build_graph,contract,prepare
from .wan_wrapper_text import validate_conditioning


class WorkerContext:
    def __init__(self,root,*,mode,epoch,authorization=None):
        if mode not in ('cpu','gpu'):raise ValueError('worker mode')
        self.root=Path(root);self.mode=mode;self.epoch=epoch;self.authorization=authorization
        self.lock=threading.RLock();self.registry={};self.pair=None;self.factory=None;self.leases=None
        self.text_cache=None;self.text_receipt=None;self.image_cache=None;self.vae_cache=None
        self.submission_lock=threading.Lock()
        self.profiles={};self.models={};self.active_graph=None
        self.is_matrix=False;self.active_trial=None
        if (self.root/'experiment.json').exists():
            self.marker=read(self.root/'experiment.json');self.comparison_sha256=self.marker['comparison_sha256']
            self.profiles={m:WrapperProfile.from_dict(read(self.root/f'frozen/profiles/{m}.json')['profile']) for m in ('control','fast')}
            for p in self.profiles.values():prepare(self.root,p)
            self.models=self.profiles['control'].identity_dict()['common']['models']
            self.is_matrix=self.marker.get('schema_version')==2

    def require_gpu(self):
        if self.mode=='cpu':raise ValueError('CPU mode refuses checkpoint admission and video execution')
        if any(p.identity_dict()['kind']!='experiment' for p in self.profiles.values()):raise ValueError('offline fixture forbidden in real GPU worker')
        auth=self.authorization
        if self.is_matrix:
            from .wan_wrapper_matrix import authorize_group
            authorize_group(self.root,auth)
            return
        if (not auth or auth.get('task_id')!='LVA-07-05' or auth.get('approved') is not True
                or not auth.get('user_evidence') or auth.get('comparison_sha256')!=self.comparison_sha256
                or auth.get('max_samples')!=2):raise ValueError('separate LVA-07-05 GPU authorization required')

    def preflight_resources(self,*,phase=False):
        self.require_gpu()
        if phase:self.require_text()
        import psutil,torch
        limits=contract()['future_full_model_limits']
        ram=limits['min_phase_available_ram_bytes'] if phase else limits['min_available_ram_bytes']
        vram=limits['min_phase_free_vram_bytes'] if phase else limits['min_free_vram_bytes']
        if psutil.virtual_memory().available<ram:raise ValueError('available RAM below configured minimum')
        if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<vram:raise ValueError('free VRAM below configured minimum')
        torch.cuda.set_per_process_memory_fraction(limits['torch_gpu_allocator_bytes']/torch.cuda.get_device_properties(0).total_memory)
        torch.backends.cuda.enable_math_sdp(False)

    def allow_request(self,method,route):
        if route.startswith('/api/'):route=route[4:]
        if method=='POST' and route in ('/prompt','/lva07/admit-pair','/lva07/prepare-text'):self.require_gpu()

    @contextmanager
    def stage(self,name):
        start=time.perf_counter()
        try:yield
        finally:
            self.root.mkdir(parents=True,exist_ok=True)
            with (self.root/'stage-metrics.jsonl').open('a',encoding='utf-8') as f:
                row=dict(stage=name,seconds=time.perf_counter()-start,epoch=self.epoch)
                if self.is_matrix:row.update(trial=self.active_trial,mode=self.marker['mode'])
                f.write(json.dumps(row)+'\n')

    def invoke(self,name,**kwargs):
        klass=self.registry[name];return getattr(klass(),klass.FUNCTION)(**kwargs)

    def require_text(self,positive=None,negative=None):
        if (self.text_cache is None or not self.text_receipt or self.text_receipt.get('epoch')!=self.epoch
                or self.text_receipt.get('comparison_sha256')!=self.comparison_sha256):
            raise ValueError('current prepared text required before admission or VAE')
        if positive is not None:
            if digest(dict(positive=positive,negative=negative))!=self.text_receipt['prompt_sha256']:
                raise ValueError('prepared text prompt differs')
        # Samplers may mutate conditioning; every trial receives private tensors.
        if self.is_matrix:
            from copy import deepcopy
            return deepcopy(self.text_cache)
        return dict(self.text_cache)

    def require_image(self):
        self.require_text()
        if self.image_cache is None or self.vae_cache is None or not self.text_receipt.get('image_prepared'):
            raise ValueError('current prepared image required before admission or sampling')
        from .wan_wrapper_vae import copy_image_conditioning
        return copy_image_conditioning(self.image_cache),self.vae_cache

    def prepare_text(self,probe_id):
        self.require_gpu()
        from .wan_wrapper_backend import canonical_uuid
        canonical_uuid(probe_id)
        with self.lock:
            folder=self.root/'text';intent=folder/'intent.json'
            if intent.exists() or self.text_cache is not None or self.pair is not None:raise ValueError('original text intent exists; GET only')
            expected=dict(probe_id=probe_id,profile_sha256=self.profiles['control'].digest(),epoch=self.epoch)
            if read(folder/'client-intent.json')!=expected:raise ValueError('original text ID/profile/epoch differs')
            self.preflight_resources()
            write_once(intent,expected)
            try:
                from .wan_wrapper_runtime_support import InputLeases,admission_progress_scope
                from .wan_wrapper_text import encode_native_text,save_prepared_text
                fixture=read(self.root/'fixture.json')
                image_path=self.root/'input'/fixture['input_relative']
                if image_path.resolve()!=image_path or not image_path.is_relative_to((self.root/'input').resolve()):
                    raise ValueError('prepared image path alias or escape')
                image_asset=dict(path=str(image_path),bytes=fixture['source_image']['bytes'],sha256=fixture['input_sha256'])
                self.leases=InputLeases([*self.models.values(),image_asset])
                from .wan_wrapper_vae import prepare_native_image
                with admission_progress_scope():
                    text,proof=encode_native_text(self,fixture)
                    image,vae,image_proof=prepare_native_image(self,fixture)
                receipt=save_prepared_text(self,fixture,text,{**proof,**image_proof},probe_id)
                self.text_cache=text;self.text_receipt=receipt;self.image_cache=image;self.vae_cache=vae
                write_once(folder/'accepted.json',dict(probe_id=probe_id,receipt=receipt))
                return read(folder/'accepted.json')
            except BaseException as exc:
                self.text_cache=None;self.text_receipt=None;self.image_cache=None;self.vae_cache=None
                if self.leases:self.leases.close();self.leases=None
                write_once(folder/'failed.json',dict(probe_id=probe_id,error=type(exc).__name__,error_message=str(exc)))
                raise

    def admit(self,admission_id):
        self.require_gpu()
        from .wan_wrapper_backend import canonical_uuid
        canonical_uuid(admission_id)
        with self.lock:
            self.require_text();self.require_image()
            folder=self.root/'admission';intent=folder/'intent.json'
            if intent.exists():raise ValueError('original admission already exists; GET only, never repeat unknown POST')
            client_intent=read(folder/'client-intent.json')
            if client_intent!=dict(admission_id=admission_id,profile_sha256=self.profiles['fast'].digest(),epoch=self.epoch):
                raise ValueError('original client admission ID/profile/epoch differs')
            self.preflight_resources(phase=True)
            write_once(intent,dict(admission_id=admission_id,epoch=self.epoch,profile_sha256=self.profiles['fast'].digest()))
            from .wan_wrapper_lora import admit_pair
            try:
                self.factory.admission_id=admission_id
                from .wan_wrapper_runtime_support import InputLeases,admission_progress_scope
                if self.leases is None:self.leases=InputLeases(list(self.models.values()))
                else:self.leases.verify()
                with admission_progress_scope():
                    self.pair=admit_pair(self.factory,self.profiles['fast'],self.leases)
                write_once(folder/'accepted.json',dict(admission_id=admission_id,receipt=self.pair.receipt))
                return read(folder/'accepted.json')
            except BaseException as exc:
                if self.leases:self.leases.close();self.leases=None
                write_once(folder/'failed.json',dict(admission_id=admission_id,error=type(exc).__name__,error_message=str(exc)))
                raise

    def validate_graph(self,graph):
        self.require_gpu()
        if self.pair is None or self.pair.receipt.get('epoch')!=self.epoch or not self.pair.receipt.get('full_model_verified'):
            raise ValueError('current pair admission required before video POST')
        fixture=read(self.root/'fixture.json')
        if self.is_matrix:
            from .wan_wrapper_matrix import TRIALS,graph as matrix_graph,require_fast_review,require_parent,require_no_rejection
            require_no_rejection(self.marker['matrix_root'])
            mode=self.marker['mode']
            trials=[t for t in TRIALS if matrix_graph(self.profiles[mode],fixture,t)==graph]
            if len(trials)!=1:raise ValueError('graph differs from frozen matrix trial')
            trial=trials[0];index=TRIALS.index(trial)
            if index:
                previous=TRIALS[index-1]
                if not (self.root/'trials'/previous/'technical-complete.json').exists():raise ValueError('previous technical completion required')
                done=read(self.root/'trials'/previous/'technical-complete.json')
                claim=read(self.root/'worker-submissions'/(previous+'.json'))
                accepted=read(self.root/'worker-submissions'/(previous+'-accepted.json'))
                if (claim.get('epoch')!=self.epoch or done.get('prompt_id')!=accepted.get('prompt_id')
                    or done.get('profile_sha256')!=self.profiles[mode].digest()):raise ValueError('same epoch previous technical completion required')
            if mode=='fast':require_fast_review(self.root)
            if fixture.get('matrix_fixture')=='child':require_parent(self.root)
            return mode
        modes=[m for m,p in self.profiles.items() if build_graph(p,fixture)==graph]
        if len(modes)!=1:raise ValueError('graph differs from frozen experiment')
        mode=modes[0]
        if mode=='fast':
            from .wan_wrapper_backend import WrapperExperimentClient
            client=WrapperExperimentClient(self.root,profile_digest=self.profiles['fast'].digest(),port=self.marker['port'])
            try:client._fast_gate()
            finally:client.close()
        self.active_graph=graph
        return mode

    def claim_prompt(self,payload):
        from .wan_wrapper_backend import canonical_uuid
        if not isinstance(payload,dict) or set(payload)!={'prompt','client_id'}:raise ValueError('exact original prompt envelope required')
        canonical_uuid(payload['client_id'])
        with self.submission_lock:
            mode=self.validate_graph(payload['prompt']);trial=payload['prompt']['30']['inputs']['trial_token'] if self.is_matrix else mode+'_1'
            intent=read(self.root/'trials'/trial/'intent.json')
            if intent!=dict(client_id=payload['client_id'],graph=payload['prompt'],graph_sha256=digest(payload['prompt'])):
                raise ValueError('original durable client/graph differs')
            target=self.root/'worker-submissions'/(trial+'.json')
            if target.exists():raise ValueError('mode already claimed; recover original ID only')
            claim=dict(epoch=self.epoch,mode=mode,client_id=payload['client_id'],graph_sha256=digest(payload['prompt']),
                profile_sha256=self.profiles[mode].digest(),comparison_sha256=self.comparison_sha256)
            if self.is_matrix:claim.update(trial_id=trial,matrix_sha256=self.marker['matrix_sha256'],group=self.marker['group'])
            write_once(target,claim)
            if self.is_matrix:self.active_graph=payload['prompt'];self.active_trial=trial
            return claim


def register_nodes(registry,context):
    if any(name in registry for name in ('LVA07Prepare','LVA07Sampler','LVA07SaveVideo')):raise ValueError('experimental node collision')
    context.registry=registry
    class Prepare:
        RETURN_TYPES=('WANVIDIMAGE_EMBEDS','WANVIDEOTEXTEMBEDS','WANVAE');FUNCTION='execute';CATEGORY='LVA07/experiment'
        @classmethod
        def INPUT_TYPES(cls):
            fields={'required':dict(start_image=('IMAGE',),positive_prompt=('STRING',{'multiline':True}),negative_prompt=('STRING',{'multiline':True}),
                clip_name=('STRING',),vae_name=('STRING',),width=('INT',{'default':768}),height=('INT',{'default':432}),num_frames=('INT',{'default':93}))}
            if context.is_matrix:fields['required']['trial_token']=('STRING',)
            return fields
        def execute(self,**kwargs):
            context.require_gpu()
            with context.lock:
                return self._execute(**kwargs)
        def _execute(self,start_image,positive_prompt,negative_prompt,clip_name,vae_name,width,height,num_frames,trial_token=None):
            expected=read(context.root/'fixture.json')['budget']['generated_frames'] if context.is_matrix else 93
            if context.is_matrix and trial_token!=context.active_trial:raise ValueError('active trial token differs')
            if (width,height,num_frames)!=(768,432,expected):raise ValueError('fixed dimensions/frame budget')
            if clip_name!=Path(context.models['t5']['path']).name or vae_name!=Path(context.models['vae']['path']).name:raise ValueError('text/VAE identity differs')
            with context.stage('text_cache_bind'):
                text=context.require_text(positive_prompt,negative_prompt)
            with context.stage('image_cache_bind'):
                image,vae=context.require_image()
            return image,text,vae

    class Sampler:
        RETURN_TYPES=('LATENT',);FUNCTION='execute';CATEGORY='LVA07/experiment'
        @classmethod
        def INPUT_TYPES(cls):
            fields={'required':dict(role=(['high','low'],),mode=(['control','fast'],),model_name=('STRING',),
                image_embeds=('WANVIDIMAGE_EMBEDS',),text_embeds=('WANVIDEOTEXTEMBEDS',),seed=('INT',{'default':0,'min':0,'max':0xffffffffffffffff})),
                'optional':dict(samples=('LATENT',))}
            if context.is_matrix:fields['required']['trial_token']=('STRING',)
            return fields
        def execute(self,**kwargs):
            context.require_gpu()
            with context.lock:return self._execute(**kwargs)
        def _execute(self,role,mode,model_name,image_embeds,text_embeds,seed,samples=None,trial_token=None):
            import torch
            from .wan_wrapper_lora import prepare_control_expert,prepare_expert,release_expert
            from .wan_wrapper_head import HEAD_KEY,head_reload_scope
            from .wan_wrapper_text import set_context_length
            from .wan_wrapper_offload import block_offload_scope
            if role not in ('high','low') or mode not in context.profiles:raise ValueError('role/mode')
            fixture=read(context.root/'fixture.json') if context.is_matrix else None
            expected_seed=fixture['seed_'+role] if fixture else (264244520398999 if role=='high' else 0)
            max_tokens=max(fixture['expected_tokens'].values()) if fixture else 664
            if context.is_matrix and (trial_token!=context.active_trial or mode!=context.marker['mode']):raise ValueError('active trial/mode differs')
            if (model_name!=Path(context.models['base_'+role]['path']).name or seed!=expected_seed
                    or (role=='high' and samples is not None) or (role=='low' and samples is None)):raise ValueError('fixed role/model/seed/latent chain')
            p=context.profiles[mode];recipe=p.identity_dict()['recipe'];segment=contract()['recipes'][mode][role]
            with context.stage(role+'_build'):
                owner=prepare_control_expert(context.factory,role) if mode=='control' else prepare_expert(context.factory,role,context.pair)
            count=0;timesteps=[];actual_sigmas=[];text_lengths=set()
            transformer=owner.transformer;original=transformer.forward
            initial_text_len=getattr(transformer,'text_len',None)
            sampler_module=importlib.import_module(registry['WanVideoSampler'].__module__)
            scheduler=sampler_module.get_scheduler
            def observed_forward(*a,**kw):
                nonlocal count
                length=set_context_length(transformer,a,kw,max_tokens=max_tokens)
                if length is not None:text_lengths.add(length)
                count+=1;return original(*a,**kw)
            def observed_scheduler(*a,**kw):
                result=scheduler(*a,**kw);timesteps.extend(result[1].detach().cpu().tolist());actual_sigmas.extend(result[0].sigmas.detach().cpu().tolist());return result
            transformer.forward=observed_forward;sampler_module.get_scheduler=observed_scheduler
            try:
                with head_reload_scope(owner,sampler_module),block_offload_scope(transformer),context.stage(role+'_sample'):
                    output=context.invoke('WanVideoSampler',model=owner.patcher,image_embeds=image_embeds,text_embeds=text_embeds,
                        steps=recipe['steps'],cfg=recipe['cfg'],shift=5.,seed=seed,scheduler='euler',riflex_freq_index=0,
                        force_offload=True,samples=samples,denoise_strength=1.,batched_cfg=False,rope_function='comfy',
                        sigmas=torch.tensor(recipe['sigmas'],dtype=torch.float32),start_step=segment['start_step'],
                        end_step=segment['end_step'],add_noise_to_samples=False)
                expected=recipe['expected_forward_counts'][0 if role=='high' else 1]
                if count!=expected or timesteps!=segment['timesteps'] or actual_sigmas!=segment['sigmas']:raise ValueError('actual forward/scheduler contract differs')
                head_installs=getattr(getattr(getattr(transformer,'head',None),'head',None),'_lva07_head_installations',0)
                if HEAD_KEY in owner.patcher.patches and head_installs<1:raise ValueError('actual sampler head installation missing')
                evidence=f'{context.active_trial}/{role}' if context.is_matrix else f'{mode}-{role}'
                write_once(context.root/f'node-evidence/{evidence}.json',dict(epoch=context.epoch,profile_sha256=p.digest(),
                    role=role,actual_forwards=count,timesteps=timesteps,sigmas=actual_sigmas,text_lengths=sorted(text_lengths),head_full_delta_installations=head_installs,
                    control_lora_applied=0 if mode=='control' else None))
                return (output[0],)
            finally:
                transformer.forward=original;sampler_module.get_scheduler=scheduler
                if initial_text_len is not None:transformer.text_len=initial_text_len
                del original,transformer
                with context.stage(role+'_release'):release_expert(owner)

    class Save:
        RETURN_TYPES=();OUTPUT_NODE=True;FUNCTION='execute';CATEGORY='LVA07/experiment'
        @classmethod
        def INPUT_TYPES(cls):return {'required':dict(images=('IMAGE',),fps=('INT',{'default':16}),filename_prefix=('STRING',))}
        def execute(self,**kwargs):
            context.require_gpu()
            with context.lock:return self._execute(**kwargs)
        def _execute(self,images,fps,filename_prefix):
            allowed=(f'lva07/{context.marker["mode"]}/{context.active_trial}',) if context.is_matrix else ('lva07/control_1','lva07/fast_1')
            if fps!=16 or filename_prefix not in allowed:raise ValueError('fixed output namespace')
            from .wan_wrapper_media import encode_frames,promote_encoded
            target=context.root/'output'/(filename_prefix+'.mp4')
            tools=context.profiles['control'].identity_dict()['common']['tool']
            frames=read(context.root/'fixture.json')['budget']['generated_frames'] if context.is_matrix else 93
            with context.stage('encode_validate'):
                partial=encode_frames(context.root,target,images,expected_frames=frames,ffmpeg=tools['ffmpeg']['path'])
                proof=promote_encoded(context.root,target,partial,expected_frames=frames,save_frames=context.is_matrix,ffmpeg=tools['ffmpeg']['path'],ffprobe=tools['ffprobe']['path'])
            from server import PromptServer
            from .wan_wrapper_backend import canonical_uuid
            trial=filename_prefix.split('/')[-1];mode=context.marker['mode'] if context.is_matrix else trial.removesuffix('_1')
            claim=read(context.root/'worker-submissions'/(trial+'.json'))
            prompt_id=canonical_uuid(PromptServer.instance.last_prompt_id)
            write_once(target.with_suffix('.generation-binding.json'),dict(**claim,prompt_id=prompt_id,
                media_proof_sha256=digest(proof),encoder_intent_sha256=digest(read(target.with_suffix('.encoder-intent.json'))),
                encoder_result_sha256=digest(read(target.with_suffix('.encoder-result.json')))))
            return {'ui':{'images':[dict(filename=target.name,subfolder=target.parent.relative_to(context.root/'output').as_posix(),type='output')]}}
    if 'WanVideoDecode' in registry:
        native_decode=registry['WanVideoDecode']
        class Decode(native_decode):
            def decode(self,vae,**kwargs):
                context.require_gpu()
                from .wan_wrapper_vae import vae_memory_scope
                with context.lock,vae_memory_scope(vae),context.stage('vae_decode'):
                    return super().decode(vae=vae,**kwargs)
        registry['WanVideoDecode']=Decode
    registry.update(LVA07Prepare=Prepare,LVA07Sampler=Sampler,LVA07SaveVideo=Save)
    return registry
