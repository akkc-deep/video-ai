"""Owned production Wrapper worker. Ordinary Comfy transactions, no experiment POSTs."""
from contextlib import contextmanager
from copy import deepcopy
import gc
import importlib
import json
import os
from pathlib import Path
import threading
import time

from ..config import read_json
from ..experiments.wan_fast_profiles import digest,write_once
from .wan_production import (ENVIRONMENT_RELATIVE,SOURCE,PROTOCOL,production_profile,wrapper_template,
    effective_parameters,request_graph,select_mode)
from .workflows import safe_comfy_path


class ProductionContext:
    """Implements only the numerical sampler's context interface, not its experiment protocol."""
    def __init__(self,run,launch,*,cpu=False):
        self.run=Path(run).resolve();self.launch=launch;self.mode='cpu' if cpu else 'gpu'
        if launch['protocol']!=PROTOCOL or launch['run']!=str(self.run):raise ValueError('production launch differs')
        self.epoch=launch['epoch'];self.owner_root=self.run/'comfy/wan-production'/self.epoch;self.root=self.owner_root
        self.models=launch['models'];self.comparison_sha256=digest(launch)
        self.profiles={m:production_profile(m) for m in ('control','fast')}
        self.lock=threading.RLock();self.registry={};self.pair=None;self.factory=None;self.leases=None
        self.text_cache=self.text_receipt=self.image_cache=self.vae_cache=None
        # Compatibility with the admitted variable-frame numerical sampler.
        # These are production clip tokens; no matrix fixtures/authorization are read.
        self.is_matrix=True;self.active_trial=None;self.marker={};self.claims={}
        self.image_lease=None

    def assert_owner(self):
        from .production_state import process_started_at
        if process_started_at(self.launch['owner_pid'])!=self.launch['owner_started_at']:
            raise ValueError('production controller exited or changed')
        lock=self.launch['run_lock']
        if lock is None or read_json(self.run/'.make-video.lock')!=lock:
            raise ValueError('production run lock lost')

    def require_gpu(self):
        self.assert_owner()
        if self.mode!='gpu':raise ValueError('CPU probe refuses production inference')
        if self.leases is not None:self.leases.verify()

    def preflight_resources(self,*,phase=False):
        self.require_gpu()
        import torch,psutil
        limits=self.profiles['fast'].identity_dict()['memory_limits']
        if not phase:
            from observe_wan_wrapper_comfy import host_available_commit_bytes
            if host_available_commit_bytes()<limits['min_available_commit_bytes']:
                raise ValueError('production Wrapper available host commit below admitted minimum')
        if psutil.virtual_memory().available<limits['min_phase_available_ram_bytes' if phase else 'min_available_ram_bytes']:
            raise ValueError('production Wrapper available RAM below admitted minimum')
        if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<limits['min_phase_free_vram_bytes' if phase else 'min_free_vram_bytes']:
            raise ValueError('production Wrapper free VRAM below admitted minimum')
        torch.cuda.set_per_process_memory_fraction(limits['torch_gpu_allocator_bytes']/torch.cuda.get_device_properties(0).total_memory)
        torch.backends.cuda.enable_math_sdp(False)

    @contextmanager
    def stage(self,name):
        started=time.perf_counter()
        try:yield
        finally:
            self.root.mkdir(parents=True,exist_ok=True)
            with (self.root/'stage-metrics.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(dict(stage=name,seconds=time.perf_counter()-started,epoch=self.epoch,clip=self.active_trial))+'\n')

    def invoke(self,name,**kwargs):
        cls=self.registry[name];return getattr(cls(),cls.FUNCTION)(**kwargs)

    def require_text(self,positive=None,negative=None):
        if self.text_cache is None or self.text_receipt is None:raise ValueError('production text not prepared')
        if positive is not None and digest(dict(positive=positive,negative=negative))!=self.text_receipt['prompt_sha256']:
            raise ValueError('production text differs from original request')
        return deepcopy(self.text_cache)

    def require_image(self):
        if self.image_cache is None or self.vae_cache is None:raise ValueError('production image not prepared')
        if self.image_lease is None:raise ValueError('production image lease lost')
        self.image_lease.verify()
        return deepcopy(self.image_cache),self.vae_cache

    def claim_prompt(self,payload):
        self.require_gpu()
        from uuid import UUID
        if set(payload)!={'prompt','client_id'} or str(UUID(payload['client_id']))!=payload['client_id']:
            raise ValueError('production original client identity required')
        graph=payload['prompt'];mode=select_mode(graph)
        if mode=='native':raise ValueError('production Wrapper refuses native POST')
        prefix=graph['108']['inputs']['filename_prefix'];safe_comfy_path(prefix)
        parts=Path(prefix).parts
        if len(parts)!=4 or parts[0]!=self.run.name or parts[1] not in ('scene_clips','source_clips') or parts[3]!='attempt_0001':
            raise ValueError('production output namespace differs')
        if parts[1]=='scene_clips':
            folder=self.run/'production/scene-clips'/parts[2]
            original=read_json(folder/'graph.json');intent=read_json(folder/'intent.json')
            input_record=read_json(folder/'input.json');request=read_json(folder/'request.json')
            if request['input_sha256']!=digest(input_record) or request['graph_sha256']!=digest(graph):
                raise ValueError('production scene input/request binding differs')
        else:
            manifest=read_json(self.run/'manifest.json')
            intent=manifest['units']['shot_attempt'][parts[2]+':attempt_0001']['submission']
            original=read_json(Path(intent['request_path']))
            input_record=read_json(self.run/'logs/production/source-clips'/(parts[2]+'.input-copy.json'))
        if original!=graph or intent['client_id']!=payload['client_id']:
            raise ValueError('production POST differs from persisted original intent')
        prep=graph['10']['inputs']
        image_path=(self.run/'comfy/input'/safe_comfy_path(prep['start_image'])).resolve(strict=True)
        image=input_record['target']
        if not image_path.is_relative_to(self.run/'comfy/input') or str(image_path)!=image['path']:
            raise ValueError('production frozen input path differs')
        p=dict(positive=prep['positive_prompt'],negative=prep['negative_prompt'],width=prep['width'],height=prep['height'],
            length=prep['num_frames'],fps=graph['108']['inputs']['fps'],seed_high=prep['seed_high'],seed_low=prep['seed_low'])
        p=effective_parameters(p,mode)
        if request_graph(wrapper_template(mode),p,prep['start_image'],prefix)!=graph:
            raise ValueError('production Wrapper graph differs from fixed recipe')
        path=self.owner_root/'claims'/(digest(prefix)+'.json')
        if path.exists() or prefix in self.claims:raise ValueError('production original already claimed; GET only')
        claim=dict(protocol=PROTOCOL,epoch=self.epoch,client_id=payload['client_id'],graph_sha256=digest(graph),graph=graph,input_image=image)
        write_once(path,claim);self.claims[prefix]=claim
        return claim

    def prepare(self,**kwargs):
        self.require_gpu()
        token=kwargs['trial_token'];claim=self.claims.get(token)
        if claim is None or claim['graph']['10']['inputs']!=kwargs:raise ValueError('production prepare lacks original claim')
        self.text_cache=self.text_receipt=self.image_cache=self.vae_cache=None
        if self.image_lease is not None:self.image_lease.close();self.image_lease=None
        gc.collect()
        self.root=self.owner_root/'clips'/digest(token);self.root.mkdir(parents=True,exist_ok=True)
        self.active_trial=token;self.marker={'mode':kwargs['mode']}
        self.preflight_resources()
        from ..experiments.wan_wrapper_runtime_support import InputLeases
        if self.leases is None:self.leases=InputLeases(list(self.models.values()))
        image=(self.run/'comfy/input'/safe_comfy_path(kwargs['start_image'])).resolve(strict=True)
        if not image.is_relative_to(self.run/'comfy/input'):raise ValueError('production input escape')
        self.image_lease=InputLeases([claim['input_image']])
        fixture=dict(positive=kwargs['positive_prompt'],negative=kwargs['negative_prompt'],input_relative=kwargs['start_image'],
            input_sha256=claim['input_image']['sha256'],seed_high=kwargs['seed_high'],seed_low=kwargs['seed_low'],
            budget=dict(generated_frames=kwargs['num_frames']),expected_tokens=self.token_counts(kwargs))
        write_once(self.root/'fixture.json',fixture)
        from ..experiments.wan_wrapper_text import encode_native_text
        from ..experiments.wan_wrapper_vae import prepare_native_image
        text,proof=encode_native_text(self,fixture)
        self.text_cache=text;self.text_receipt=dict(prompt_sha256=digest(dict(positive=fixture['positive'],negative=fixture['negative'])))
        image,vae,image_proof=prepare_native_image(self,fixture)
        self.image_cache=image;self.vae_cache=vae
        write_once(self.root/'prepared.json',dict(epoch=self.epoch,graph_sha256=claim['graph_sha256'],**proof,**image_proof))
        if kwargs['mode']=='fast' and self.pair is None:
            self.preflight_resources(phase=True)
            from ..experiments.wan_wrapper_lora import admit_pair
            with self.stage('pair_admission'):
                self.pair=admit_pair(self.factory,self.profiles['fast'],self.leases)
        return self.require_image()[0],self.require_text(),self.vae_cache

    def token_counts(self,kwargs):
        from safetensors import safe_open
        from comfy.text_encoders.wan import WanT5Tokenizer
        if not hasattr(self,'tokenizer'):
            with safe_open(self.models['t5']['path'],framework='pt',device='cpu') as reader:
                keys=[key for key in reader.keys() if key.endswith('spiece_model')]
                if len(keys)!=1:raise ValueError('production tokenizer identity differs')
                self.tokenizer=WanT5Tokenizer(tokenizer_data={'spiece_model':reader.get_tensor(keys[0])})
        result={}
        for slot,name in (('prompt_embeds','positive_prompt'),('negative_prompt_embeds','negative_prompt')):
            chunks=self.tokenizer.tokenize_with_weights(kwargs[name])['umt5xxl']
            if len(chunks)!=1:raise ValueError('production requires one full unscheduled context')
            result[slot]=len(chunks[0])
        return result

    def close(self):
        if self.image_lease is not None:self.image_lease.close()
        if self.leases is not None:self.leases.close()


def register_production_nodes(registry,context):
    from ..experiments.wan_wrapper_nodes import register_nodes
    numeric=dict(registry);register_nodes(numeric,context)
    # Reuse the exact observed numerical sampler/decode scopes, not experiment preparation/save/HTTP gates.
    class Prepare:
        RETURN_TYPES=('WANVIDIMAGE_EMBEDS','WANVIDEOTEXTEMBEDS','WANVAE');FUNCTION='execute';CATEGORY='VideoAI/production'
        @classmethod
        def INPUT_TYPES(cls):
            return {'required':dict(start_image=('STRING',),positive_prompt=('STRING',{'multiline':True}),negative_prompt=('STRING',{'multiline':True}),
                width=('INT',{'default':768}),height=('INT',{'default':432}),num_frames=('INT',{'default':93}),
                seed_high=('INT',{'default':0,'min':0,'max':0xffffffffffffffff}),seed_low=('INT',{'default':0,'min':0,'max':0xffffffffffffffff}),
                mode=(['fast','control'],),protocol=('STRING',),recipe_sha256=('STRING',),trial_token=('STRING',))}
        def execute(self,**kwargs):
            with context.lock:return context.prepare(**kwargs)

    class Save:
        RETURN_TYPES=();OUTPUT_NODE=True;FUNCTION='execute';CATEGORY='VideoAI/production'
        @classmethod
        def INPUT_TYPES(cls):return {'required':dict(images=('IMAGE',),fps=('INT',{'default':16}),filename_prefix=('STRING',))}
        def execute(self,images,fps,filename_prefix):
            context.require_gpu()
            if fps!=16 or filename_prefix!=context.active_trial:raise ValueError('production output identity differs')
            from ..experiments.wan_wrapper_media import encode_frames
            fixture=read_json(context.root/'fixture.json')
            target=context.run/'comfy/output'/(safe_comfy_path(filename_prefix)+'_00001.mp4')
            with context.lock,context.stage('encode'):
                partial=encode_frames(context.run,target,images,expected_frames=fixture['budget']['generated_frames'],ffmpeg=context.launch['tools']['ffmpeg'])
                # Production performs its usual decoded-media check after ordinary Comfy completion.
                os.rename(partial,target)
                from server import PromptServer
                write_once(target.with_suffix('.generation.json'),dict(protocol=PROTOCOL,epoch=context.epoch,
                    prompt_id=PromptServer.instance.last_prompt_id,claim_sha256=digest(context.claims[filename_prefix]),
                    profile_sha256=context.profiles[context.marker['mode']].digest()))
            return {'ui':{'images':[dict(filename=target.name,subfolder=target.parent.relative_to(context.run/'comfy/output').as_posix(),type='output')]}}

    registry.update(VideoAIWanPrepare=Prepare,VideoAIWanSampler=numeric['LVA07Sampler'],VideoAIWanSave=Save,
                    WanVideoDecode=numeric['WanVideoDecode'])
    context.registry=registry


def software_rows(rows,environment):
    """Relocate only paths under the original sealed environment, preserving all hashes."""
    original=Path('E:/VideoAI')/ENVIRONMENT_RELATIVE
    result=[]
    for row in rows:
        path=Path(row['path'])
        if not path.is_relative_to(original):raise ValueError('software inventory path outside sealed Wrapper environment')
        result.append(dict(row,path=str(Path(environment)/path.relative_to(original))))
    return result


def serve(run,launch_path,port,*,cpu=False):
    """Boot only the isolated repaired environment; weights load inside a claimed prompt."""
    import builtins
    import runpy
    import sys
    launch=read_json(launch_path)
    context=ProductionContext(run,launch,cpu=cpu);context.assert_owner()
    environment=Path(launch['runtime_root'])/ENVIRONMENT_RELATIVE
    if Path(launch['source_root']).resolve()!=SOURCE or Path(launch['environment']).resolve()!=environment.resolve():
        raise ValueError('production source/environment binding differs')
    if Path(sys.executable).resolve()!=(environment/'python_embeded/python.exe').resolve():raise ValueError('isolated Wrapper interpreter required')
    if Path(launch_path).resolve()!=context.owner_root/'launch.json':raise ValueError('production launch path differs')
    # Bind a process-private Job before importing torch or Comfy.
    sys.path.insert(0,str(SOURCE/'scripts'))
    from observe_wan_wrapper_comfy import BoundedJob
    from types import SimpleNamespace
    job=BoundedJob(SimpleNamespace(_handle=-1),4*1024**3 if cpu else context.profiles['fast'].identity_dict()['memory_limits']['process_private_commit_bytes'],cpu=cpu)
    from ..experiments.wan_wrapper_runtime_support import InputLeases,SoftwareVerifier,SOFTWARE_SHA256
    source_leases=InputLeases(launch['source_artifacts'])
    inventory=SOURCE/'docs/task-designs/LVA-07-04-software.json'
    import hashlib
    if hashlib.sha256(inventory.read_bytes()).hexdigest()!=SOFTWARE_SHA256:raise ValueError('production software inventory differs')
    wrapper=environment/'ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper-LVA07'
    rows=software_rows(read_json(inventory)['files'],environment)
    rows += [dict(path=str((wrapper/r['path']).resolve()),bytes=r['bytes'],sha256=r['sha256']) for r in read_json(environment/'sources.json')['wrapper_files']]
    verifier=SoftwareVerifier(rows,[environment/'ComfyUI',environment/'python_embeded'])
    for row in rows:
        p=Path(row['path'])
        if row.get('group')=='runtime' and p.suffix.lower() in ('.exe','.dll','.pyd','.zip','.pth'):verifier.verify(p)
    verifier.install()
    comfy=environment/'ComfyUI'
    sys.argv=[str(comfy/'main.py'),*(['--cpu'] if cpu else []),'--listen','127.0.0.1','--port',str(port),'--disable-auto-launch','--offline',
        '--disable-all-custom-nodes','--whitelist-custom-nodes',wrapper.name,'--disable-assets','--cache-none',
        '--models-directory',str(Path(launch['models']['vae']['path']).parent.parent),
        '--database-url','sqlite:///'+(context.run/'comfy/user/comfyui.db').as_posix()]
    for name in ('input','output','temp','user'):
        directory=context.run/'comfy'/name;directory.mkdir(parents=True,exist_ok=True)
        sys.argv+=['--'+name+'-directory',str(directory)]
    sys.path.insert(0,str(comfy));os.chdir(comfy)
    original_import=builtins.__import__;installed=[]
    def observed_import(name,globals=None,locals=None,fromlist=(),level=0):
        imported=original_import(name,globals,locals,fromlist,level)
        if name=='nodes' and not installed:
            nodes=sys.modules.get('nodes')
            if nodes is not None and hasattr(nodes,'init_extra_nodes'):
                original=nodes.init_extra_nodes;installed.append((nodes,original))
                async def initialize(*args,**kwargs):
                    result=await original(*args,**kwargs)
                    modules=[m for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve()==(wrapper/'nodes_model_loading.py').resolve()]
                    if len(modules)!=1:raise ValueError('production Wrapper module identity differs')
                    import folder_paths
                    for role,category in dict(base_high='diffusion_models',base_low='diffusion_models',t5='text_encoders',vae='vae',lora_high='loras',lora_low='loras').items():
                        path=folder_paths.get_full_path(category,Path(context.models[role]['path']).name)
                        if path is None or Path(path).resolve()!=Path(context.models[role]['path']).resolve():raise ValueError('production model search path differs: '+role)
                    from ..experiments.wan_wrapper_lora import PinnedExpertFactory
                    prefix=modules[0].__package__
                    context.factory=PinnedExpertFactory(context,modules[0],importlib.import_module(prefix+'.custom_linear'),
                        importlib.import_module(prefix+'.lva07_mixed_delta'),importlib.import_module(prefix+'.lva07_applicability'),
                        importlib.import_module('comfy.lora'),importlib.import_module(prefix+'.utils'))
                    register_production_nodes(nodes.NODE_CLASS_MAPPINGS,context)
                    from server import PromptServer
                    from aiohttp import web
                    @web.middleware
                    async def guard(request,handler):
                        if request.method=='POST':
                            try:
                                if request.path not in ('/prompt','/api/prompt'):raise ValueError('production worker accepts only original prompt POSTs')
                                with context.lock:claim=context.claim_prompt(await request.json())
                            except (ValueError,KeyError,OSError) as exc:return web.json_response({'error':str(exc)},status=403)
                        response=await handler(request)
                        if request.method=='POST' and response.status==200:
                            accepted=json.loads(response.body)
                            write_once(context.owner_root/'accepted'/(digest(claim['graph'])+'.json'),dict(client_id=claim['client_id'],**accepted))
                        return response
                    PromptServer.instance.app.middlewares.append(guard)
                    write_once(context.owner_root/'worker.json',dict(protocol=PROTOCOL,pid=os.getpid(),epoch=context.epoch,cpu_probe=cpu))
                    return result
                nodes.init_extra_nodes=initialize
        return imported
    builtins.__import__=observed_import
    def watch_owner():
        import psutil
        process=psutil.Process()
        while True:
            time.sleep(2)
            try:
                context.assert_owner()
                if not cpu and process.memory_info().rss>context.profiles['fast'].identity_dict()['memory_limits']['rss_stop_bytes']:
                    write_once(context.owner_root/'resource-stop.json',dict(reason='owned worker RSS exceeds admitted limit'))
                    os._exit(1)
            except (ValueError,OSError):os._exit(1)
    threading.Thread(target=watch_owner,daemon=True).start()
    try:runpy.run_path(str(comfy/'main.py'),run_name='__main__')
    finally:
        builtins.__import__=original_import
        context.close();verifier.close();source_leases.close()
        # Keep the Job handle alive through interpreter exit (kill-on-close includes this process).

