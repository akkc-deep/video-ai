"""Isolated LVA-07 Wrapper profiles and original-request protocol. No torch import."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from uuid import UUID

from .wan_fast_profiles import Artifact, digest, write_once
from .wan_fast_experiment import baseline_api, read

SOURCE = Path(__file__).resolve().parents[3]
MODEL_ROLES = frozenset(('base_high','base_low','t5','vae','lora_high','lora_low'))
MODEL_PINS={
    'base_high':('diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors',14294742832,'6122e79d55e0f235698d11d657f3b196c5273c830da00b2b013c5a048d5e6a42'),
    'base_low':('diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors',14294742832,'5471a457b6ac404202a5fbe6c11595a3d5641fc766b00f38763f72303fffc21e'),
    't5':('text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',6735906897,'c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68'),
    'vae':('vae/wan_2.1_vae.safetensors',253815318,'2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b'),
    'lora_high':('loras/wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors',634645944,'887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19'),
    'lora_low':('loras/wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors',739472104,'8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1')}
POLICY_SHA = '9dbc2f5536bab2057147d0ebebc3af7f8a3db1a3c060f8bc41af6a4185dc2587'
SETTINGS = dict(width=768,height=432,num_frames=93,fps=16,compute_dtype='float16',
    vae_precision='fp32',attention='sdpa',compile=False,merge=False,fast_fp8=False,
    low_mem_load=False,blocks_to_swap=40,prefetch_blocks=0,use_non_blocking=False,
    offload_txt_emb=True,offload_img_emb=True,text_path='native_wan_bridge_prepared',
    encoder=dict(codec='libx264',preset='medium',crf=18,pix_fmt='yuv420p',audio=False))
REQUIRED_NODES = ('LoadImage','CLIPLoader','CLIPTextEncode','WanVideoTextEmbedBridge',
    'WanVideoVAELoader','WanVideoImageToVideoEncode','WanVideoModelLoader','WanVideoBlockSwap',
    'WanVideoSampler','WanVideoDecode','LVA07Prepare','LVA07Sampler','LVA07SaveVideo')


def contract():
    return read(SOURCE/'docs/task-designs/LVA-07-04-contract.json')


def recipe(mode):
    if mode not in ('control','fast'):
        raise ValueError('unknown mode')
    c=contract()['recipes'][mode];fast=mode=='fast'
    return dict(steps=4 if fast else 40,cfg=1.0 if fast else 3.5,split=c['split'],
        sigmas=c['sigmas_float32'],timesteps=c['high']['timesteps']+c['low']['timesteps'],
        sampler='euler',shift=5.0,lora_enabled=fast,lora_strengths=[1.,1.] if fast else [0.,0.],
        expected_forward_counts=[2,2] if fast else [30,50],pure_backend_equivalence=False)


@dataclass(frozen=True,slots=True)
class WrapperProfile:
    """Canonical JSON prevents mutable dicts from changing an admitted profile."""
    canonical: str

    @classmethod
    def create(cls,mode,common,*,kind='experiment'):
        return cls.from_dict(dict(schema_version=1,backend='wan_wrapper',kind=kind,mode=mode,
            common=common,settings=SETTINGS,recipe=recipe(mode),
            frame_contract=dict(generated_frames=93,retained_frames=93,fps=16),
            memory_limits=contract()['future_full_model_limits']))

    @classmethod
    def from_dict(cls,v):
        if v.get('schema_version')==2:
            from .wan_wrapper_matrix import validate_profile
            validate_profile(v)
            return cls(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False))
        if (set(v)!={'schema_version','backend','kind','mode','common','settings','recipe','frame_contract','memory_limits'}
            or v['schema_version']!=1 or v['backend']!='wan_wrapper'
            or v['kind'] not in ('experiment','offline_fixture')):
            raise ValueError('profile schema')
        if v['recipe']!=recipe(v['mode']):raise ValueError('fixed recipe differs')
        if v['settings']!=SETTINGS or v['frame_contract']!=dict(generated_frames=93,retained_frames=93,fps=16):
            raise ValueError('fixed compute/frame settings differ')
        if v['memory_limits']!=contract()['future_full_model_limits']:raise ValueError('memory limit drift')
        common=v['common']
        if set(common)!= {'source','runtime','tool','models','policy'} or set(common['models'])!=MODEL_ROLES:
            raise ValueError('common identity/model roles')
        if common['policy'].get('sha256')!=POLICY_SHA:raise ValueError('policy identity')
        if v['kind']=='experiment':
            manifest=read(SOURCE/'docs/task-designs/LVA-07-environment-manifest.json')
            aliases={'wan_high':'base_high','wan_low':'base_low','text_encoder':'t5'}
            pins={aliases.get(m['role'],m['role']):m for m in manifest['models']}
            for role,model in common['models'].items():
                pin=pins[role]
                filename,size,sha=MODEL_PINS[role]
                if (Path(model.get('path',''))!=Path('E:/VideoAI/shared/models/comfyui')/filename
                        or model.get('bytes')!=size or model.get('sha256')!=sha):raise ValueError('immutable original model pin: '+role)
                if any(model.get(k)!=pin.get(k) for k in ('path','bytes','sha256','header_sha256')):
                    raise ValueError('fixed model identity: '+role)
            for group in ('source','runtime','tool'):
                if not common[group].get('artifacts'):raise ValueError('explicit '+group+' artifacts required')
        return cls(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False))

    @property
    def mode(self):return self.identity_dict()['mode']
    def identity_dict(self):return json.loads(self.canonical)
    def digest(self):return digest(self.identity_dict())


def comparison_identity(profiles,fixture):
    if set(profiles)!= {'control','fast'}:raise ValueError('both modes required')
    values={k:WrapperProfile.from_dict(p.identity_dict()).identity_dict() for k,p in profiles.items()}
    for k,v in values.items():
        if v['mode']!=k:raise ValueError('mode identity mismatch')
    common={k:v for k,v in values['control'].items() if k not in ('mode','recipe')}
    if common!={k:v for k,v in values['fast'].items() if k not in ('mode','recipe')}:
        raise ValueError('common configuration differs')
    if (fixture.get('seed_high')!=264244520398999 or fixture.get('seed_low')!=0
            or not fixture.get('input_relative') or not fixture.get('input_sha256')):
        raise ValueError('fixed input/seed fixture required')
    name=Path(fixture['input_relative'])
    if name.is_absolute() or '..' in name.parts:raise ValueError('input path escapes root')
    value=dict(common=common,fixture=fixture)
    return dict(comparison=value,comparison_sha256=digest(value))


def build_graph(profile,fixture,trial=None,*,_legacy=False):
    if profile.identity_dict()['schema_version']==2 and not _legacy:
        from .wan_wrapper_matrix import graph
        return graph(profile,fixture,trial or 'cold_1')
    v=profile.identity_dict();mode=v['mode'];models=v['common']['models']
    def name(role):return Path(models[role]['path']).name
    return {
        '97':dict(class_type='LoadImage',inputs=dict(image=fixture['input_relative'])),
        '10':dict(class_type='LVA07Prepare',inputs=dict(start_image=['97',0],positive_prompt=fixture['positive'],
            negative_prompt=fixture['negative'],clip_name=name('t5'),vae_name=name('vae'),width=768,height=432,num_frames=93)),
        '30':dict(class_type='LVA07Sampler',inputs=dict(role='high',mode=mode,model_name=name('base_high'),
            image_embeds=['10',0],text_embeds=['10',1],seed=264244520398999)),
        '40':dict(class_type='LVA07Sampler',inputs=dict(role='low',mode=mode,model_name=name('base_low'),
            image_embeds=['10',0],text_embeds=['10',1],seed=0,samples=['30',0])),
        '50':dict(class_type='WanVideoDecode',inputs=dict(vae=['10',2],samples=['40',0],enable_vae_tiling=False,
            tile_x=272,tile_y=272,tile_stride_x=144,tile_stride_y=128,normalization='default')),
        '108':dict(class_type='LVA07SaveVideo',inputs=dict(images=['50',0],fps=16,filename_prefix='lva07/'+mode+'_1'))}


def freeze_comparison(root,profiles,fixture,*,port=8297):
    root=Path(root);value=comparison_identity(profiles,fixture)
    write_once(root/'fixture.json',fixture)
    for mode,p in profiles.items():
        write_once(root/f'frozen/profiles/{mode}.json',dict(profile=p.identity_dict(),profile_sha256=p.digest()))
        write_once(root/f'frozen/graphs/{mode}.json',build_graph(p,fixture))
    write_once(root/'frozen/comparison.json',value)
    marker=dict(schema_version=1,kind='LVA-07-04',port=port,comparison_sha256=value['comparison_sha256'],
                profiles={k:p.digest() for k,p in profiles.items()})
    write_once(root/'experiment.json',marker)
    return marker


def prepare(root,profile):
    if profile.identity_dict()['schema_version']==2:
        from .wan_wrapper_matrix import prepare_group
        return prepare_group(root,profile)
    root=Path(root);ps={}
    for mode in ('control','fast'):
        saved=read(root/f'frozen/profiles/{mode}.json');p=WrapperProfile.from_dict(saved['profile'])
        if saved!={'profile':p.identity_dict(),'profile_sha256':p.digest()}:raise ValueError('profile digest drift')
        ps[mode]=p
    if ps[profile.mode]!=profile:raise ValueError('requested profile differs')
    fixture=read(root/'fixture.json');comparison=comparison_identity(ps,fixture)
    if read(root/'frozen/comparison.json')!=comparison:raise ValueError('comparison/fixture drift')
    marker=read(root/'experiment.json')
    if marker['profiles']!={k:p.digest() for k,p in ps.items()} or marker['comparison_sha256']!=comparison['comparison_sha256']:
        raise ValueError('comparison marker drift')
    for mode,p in ps.items():
        if read(root/f'frozen/graphs/{mode}.json')!=build_graph(p,fixture):raise ValueError('graph drift')
    return marker


def capabilities(schemas,*,origin,epoch=None,matrix=False):
    if origin not in ('observed_cpu_http','declared_experiment_node','verified_current_worker_http'):
        raise ValueError('capability origin')
    missing=set(REQUIRED_NODES)-set(schemas)
    if missing:raise ValueError('missing node schemas: '+','.join(sorted(missing)))
    contracts=read(SOURCE/('docs/task-designs/LVA-07-06-node-contract.json' if matrix else 'docs/task-designs/LVA-07-04-node-contract.json'))
    for name in REQUIRED_NODES:
        schema=schemas[name]
        if 'input' not in schema or 'output' not in schema:raise ValueError('invalid schema: '+name)
        expected=contracts[name]
        actual={group:{k:('ENUM' if isinstance(spec[0],list) else spec[0]) for k,spec in fields.items()}
            for group,fields in schema['input'].items() if group in ('required','optional')}
        if actual!=expected['input'] or list(schema['output'])!=expected['output']:raise ValueError('node argument/output contract drift: '+name)
        flat={**schema['input'].get('required',{}),**schema['input'].get('optional',{})}
        for arg,choices in expected['required_choices'].items():
            if not isinstance(flat[arg][0],list) or not set(choices)<=set(flat[arg][0]):raise ValueError('node choices differ: '+name+'.'+arg)
    return dict(origin=origin,epoch=epoch,schemas_sha256=digest(schemas),nodes=list(REQUIRED_NODES))


def canonical_uuid(value):
    try:
        if not isinstance(value,str) or str(UUID(value))!=value:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('noncanonical accepted UUID') from None
    return value


def accepted_parent_binding(parent_root,parent_trial,profile_digest,child_fixture):
    from .wan_fast_profiles import artifact
    parent_root=Path(parent_root).resolve(strict=True)
    saved=read(parent_root/'experiment.json')
    modes=[mode for mode,value in saved['profiles'].items() if value==profile_digest]
    if len(modes)!=1 or parent_trial!=modes[0]+'_1':raise ValueError('same Wrapper mode/profile parent required')
    p=WrapperProfile.from_dict(read(parent_root/f'frozen/profiles/{modes[0]}.json')['profile'])
    prepare(parent_root,p);f=read(parent_root/'fixture.json')
    if not f.get('source_clip_id') or child_fixture.get('budget',{}).get('parent_clip_id')!=f['source_clip_id']:
        raise ValueError('child parent clip identity differs')
    stopped=read(parent_root/'service-result.json')
    if stopped.get('exited') is not True or stopped.get('port_closed') is not True:raise ValueError('parent owned service must stop before child')
    def no_http(*a,**kw):raise ValueError('parent completion requires sufficient original archive, no HTTP')
    client=WrapperExperimentClient(parent_root,profile_digest=profile_digest,port=saved['port'],http=no_http)
    try:result=client.completed(parent_trial,build_graph(p,f))
    finally:client.close()
    if result is None:raise ValueError('original parent technical completion required')
    approval=parent_root/'trials'/parent_trial/'observation-accepted.json';accepted=read(approval)
    if (accepted.get('decision')!='accepted' or accepted.get('profile_sha256')!=profile_digest
            or accepted.get('prompt_id')!=result['prompt_id']
            or any(accepted.get(role+'_sha256')!=result[role+'_sha256'] for role in ('generated','retained','last_frame'))):
        raise ValueError('exact parent human acceptance required')
    if child_fixture.get('input_sha256')!=result['last_frame_sha256']:raise ValueError('child input must be original accepted last frame')
    return dict(parent_root=str(parent_root),parent_trial=parent_trial,parent_profile_sha256=profile_digest,
        parent_generated_sha256=result['generated_sha256'],parent_retained_sha256=result['retained_sha256'],
        parent_last_frame_sha256=result['last_frame_sha256'],human_acceptance=artifact(approval).identity_dict(),last_frame=result['last_frame'])


def verify_parent(fixture,profile_digest):
    binding=fixture.get('parent_binding')
    if fixture.get('requires_new_parent') and not binding:raise ValueError('parent binding required')
    if binding and accepted_parent_binding(binding['parent_root'],binding['parent_trial'],profile_digest,fixture)!=binding:
        raise ValueError('Wrapper parent acceptance/tail/profile drift')


class WrapperExperimentClient:
    def __init__(self,root,*,profile_digest,port,http=None):
        self.root=Path(root);self.profile_digest=profile_digest;self.port=port
        self.api=baseline_api();self.delegate=self.api.ExperimentClient(root,port=port,http=self._http)
        self.transport=http or self.delegate.http;self.injected=http is not None
        self.asset_leases=None
        p,f=self._verify()
        self.is_matrix=p.identity_dict()['schema_version']==2
        if not self.injected:
            from .wan_wrapper_runtime_support import InputLeases
            common=p.identity_dict()['common']
            assets=[a for group in ('source','runtime','tool') for a in common[group]['artifacts']]
            self.asset_leases=InputLeases(assets)

    def _verify(self):
        if self.asset_leases is not None:self.asset_leases.verify()
        profiles=[WrapperProfile.from_dict(read(self.root/f'frozen/profiles/{m}.json')['profile']) for m in ('control','fast')]
        matches=[p for p in profiles if p.digest()==self.profile_digest]
        if len(matches)!=1:raise ValueError('unknown profile')
        p=matches[0];prepare(self.root,p)
        if not self.injected and p.identity_dict()['kind']!='experiment':raise ValueError('fixture forbidden on real transport')
        return p,read(self.root/'fixture.json')

    def _matrix_ready(self,*,trial=None,admission=False):
        """Local readiness before any fresh intent is made durable."""
        if not self.is_matrix or self.injected:return
        self.delegate.assert_owned_service()
        owner=read(self.root/'service-owner.json');att=read(self.root/'worker-attestation.json')
        current=read(self.root/'current-http-capabilities.json');marker=read(self.root/'experiment.json')
        if (att.get('epoch')!=owner['epoch'] or att.get('pid')!=owner['pid'] or not att.get('gpu_authorized')
            or att.get('mode')!='gpu' or att.get('profiles')!=marker['profiles'] or current.get('epoch')!=owner['epoch']):
            raise ValueError('matrix service is not ready for a new intent')
        proof=capabilities(current['schemas'],origin='verified_current_worker_http',epoch=owner['epoch'],matrix=True)
        if current!={**proof,'schemas':current['schemas']}:raise ValueError('matrix current schema differs')
        from .wan_wrapper_matrix import require_no_rejection,authorize_group,require_parent
        require_no_rejection(marker['matrix_root'])
        authorize_group(self.root,read(Path(marker['matrix_root'])/'authorization.json'))
        if admission:
            receipt=read(self.root/'text/client-accepted.json')['receipt']
            if receipt.get('epoch')!=owner['epoch'] or not receipt.get('encoder_released') or not receipt.get('image_prepared'):
                raise ValueError('same epoch prepared text/image required before admission intent')
        if trial is not None:
            from .wan_wrapper_matrix import TRIALS
            pair=read(self.root/'admission/pair.json')
            if pair.get('epoch')!=owner['epoch'] or not pair.get('full_model_verified') or pair.get('comparison_sha256')!=marker['comparison_sha256']:
                raise ValueError('same epoch complete pair required before video intent')
            index=TRIALS.index(trial)
            if index:
                previous=TRIALS[index-1];done=read(self.root/'trials'/previous/'technical-complete.json')
                claim=read(self.root/'worker-submissions'/(previous+'.json'))
                if claim.get('epoch')!=owner['epoch'] or done.get('profile_sha256')!=self.profile_digest:
                    raise ValueError('same epoch preceding trial required before new intent')
            if marker['mode']=='fast':self._fast_gate()
            if marker['group'].startswith('child-'):require_parent(self.root)

    def _http(self,method,route,payload=None):
        p,_=self._verify()
        if not self.injected:
            self.delegate.assert_owned_service()
            att=read(self.root/'worker-attestation.json');owner=read(self.root/'service-owner.json')
            if (att.get('epoch')!=owner.get('epoch') or att.get('pid')!=owner['pid']
                    or att.get('profiles')!=read(self.root/'experiment.json')['profiles']):raise ValueError('worker attestation differs')
            if method=='POST':
                if att.get('mode')!='gpu' or not att.get('gpu_authorized'):raise ValueError('LVA-07-05 GPU authorization required')
                current=read(self.root/'current-http-capabilities.json')
                if current.get('epoch')!=att['epoch']:raise ValueError('current HTTP capability epoch differs')
                proof=capabilities(current['schemas'],origin='verified_current_worker_http',epoch=att['epoch'],matrix=self.is_matrix)
                if current!={**proof,'schemas':current['schemas']}:raise ValueError('current HTTP schema proof differs')
        return self.transport(method,route,payload)

    def bind(self,trial_id,graph):
        p,f=self._verify()
        if self.is_matrix:
            from .wan_wrapper_matrix import TRIALS,require_parent
            marker=read(self.root/'experiment.json')
            if trial_id not in TRIALS or p.mode!=marker['mode'] or graph!=build_graph(p,f,trial_id):raise ValueError('fixed matrix trial/graph differs')
            if f['matrix_fixture']=='child':require_parent(self.root)
        elif trial_id!=p.mode+'_1' or graph!=build_graph(p,f):raise ValueError('fixed trial/graph differs')
        if not self.injected:
            image=(self.root/'input'/f['input_relative']).resolve(strict=True)
            if not image.is_relative_to((self.root/'input').resolve()):raise ValueError('input escapes root')
            Artifact(str(image),image.stat().st_size,f['input_sha256']).verify()
        if not self.is_matrix and f.get('requires_new_parent') and not f.get('parent_binding'):raise ValueError('parent binding required')
        if not self.is_matrix and f.get('parent_binding'):
            verify_parent(f,self.profile_digest)
        folder=self.root/'trials'/trial_id
        value=dict(profile_sha256=self.profile_digest,comparison_sha256=read(self.root/'experiment.json')['comparison_sha256'],
                   fixture_sha256=digest(f),graph_sha256=digest(graph))
        write_once(folder/'profile-binding.json',value)
        if (folder/'intent.json').exists():
            intent=read(folder/'intent.json')
            canonical_uuid(intent.get('client_id'))
            if intent.get('graph')!=graph or intent.get('graph_sha256')!=digest(graph):raise ValueError('intent drift')
            write_once(folder/'intent-binding.json',dict(**value,intent_sha256=digest(intent)))
        self._accepted(folder)
        return value

    def _accepted(self,folder):
        accepted=folder/'accepted.json';post=folder/'post.response.json'
        if accepted.exists():
            pid=canonical_uuid(read(accepted).get('prompt_id'))
            if post.exists() and (read(post).get('prompt_id')!=pid or read(post).get('node_errors')!={}):
                raise ValueError('accepted/post conflict')
            write_once(folder/'acceptance-binding.json',dict(accepted_sha256=digest(read(accepted)),
                intent_sha256=digest(read(folder/'intent.json'))))
            return pid
        return None

    def _fast_gate(self):
        marker=read(self.root/'experiment.json');owner=read(self.root/'service-owner.json')
        pair=read(self.root/'admission/pair.json')
        if (pair.get('profile_sha256')!=self.profile_digest or pair.get('comparison_sha256')!=marker['comparison_sha256']
                or pair.get('epoch')!=owner.get('epoch') or pair.get('full_model_verified') is not True):raise ValueError('live full-model pair required')
        if self.is_matrix:
            from .wan_wrapper_matrix import require_fast_review
            require_fast_review(self.root)
            return
        review=read(self.root/'reviews/control_1.json');control=read(self.root/'trials/control_1/technical-complete.json')
        expected=dict(comparison_sha256=marker['comparison_sha256'],control_profile_sha256=marker['profiles']['control'],
            fixture_sha256=digest(read(self.root/'fixture.json')),control_graph_sha256=digest(read(self.root/'frozen/graphs/control.json')),
            prompt_id=control['prompt_id'],media_sha256=control['generated_sha256'])
        if (review.get('decision')!='accepted' or not review.get('human_evidence')
                or any(review.get(k)!=v for k,v in expected.items())):raise ValueError('exact control human acceptance required')
        control_client=WrapperExperimentClient(self.root,profile_digest=marker['profiles']['control'],port=self.port,http=self.transport if self.injected else None)
        try:
            if control_client.completed('control_1',read(self.root/'frozen/graphs/control.json'))!=control:raise ValueError('control completion required')
        finally:control_client.close()

    def admit_pair(self):
        from uuid import uuid4
        p,_=self._verify()
        if p.mode!='fast':raise ValueError('fast profile admission only')
        path=self.root/'admission/client-intent.json'
        fresh=not path.exists()
        if fresh:
            self._matrix_ready(admission=True)
            owner_path=self.root/'service-owner.json'
            epoch=read(owner_path)['epoch'] if owner_path.exists() else 'offline-fixture'
            write_once(path,dict(admission_id=str(uuid4()),profile_sha256=p.digest(),epoch=epoch))
        intent=read(path);canonical_uuid(intent.get('admission_id'))
        if intent.get('profile_sha256')!=p.digest():raise ValueError('admission intent profile differs')
        if fresh:
            result=self._http('POST','/lva07/admit-pair',{k:v for k,v in intent.items() if k!='epoch'})
        else:
            result=self._http('GET','/lva07/admission/'+intent['admission_id'])
        if result.get('status')=='unknown':return result
        if result.get('admission_id')!=intent['admission_id']:raise ValueError('admission response original ID differs')
        if 'receipt' in result:
            receipt=result['receipt'];marker=read(self.root/'experiment.json');owner=read(self.root/'service-owner.json')
            if (receipt.get('epoch')!=owner['epoch'] or receipt.get('profile_sha256')!=p.digest()
                    or receipt.get('comparison_sha256')!=marker['comparison_sha256'] or not receipt.get('full_model_verified')):
                raise ValueError('pair admission receipt differs')
            write_once(path.with_name('client-accepted.json'),result)
        return result

    def prepare_text(self):
        from uuid import uuid4
        p,_=self._verify()
        if p.mode!='control':raise ValueError('text preparation requires control profile')
        path=self.root/'text/client-intent.json';fresh=not path.exists()
        if fresh:
            self._matrix_ready()
            owner=self.root/'service-owner.json'
            write_once(path,dict(probe_id=str(uuid4()),profile_sha256=p.digest(),
                epoch=read(owner)['epoch'] if owner.exists() else 'offline-fixture'))
        intent=read(path);canonical_uuid(intent.get('probe_id'))
        if intent.get('profile_sha256')!=p.digest():raise ValueError('text intent profile differs')
        result=self._http('POST','/lva07/prepare-text',{k:v for k,v in intent.items() if k!='epoch'}) if fresh else self._http('GET','/lva07/text/'+intent['probe_id'])
        if result.get('status')=='unknown':return result
        if result.get('probe_id')!=intent['probe_id']:raise ValueError('text response original ID differs')
        if 'receipt' in result:
            receipt=result['receipt'];marker=read(self.root/'experiment.json')
            fixture=read(self.root/'fixture.json')
            if (receipt.get('probe_id')!=intent['probe_id'] or receipt.get('epoch')!=intent['epoch']
                    or receipt.get('comparison_sha256')!=marker['comparison_sha256']
                    or receipt.get('control_profile_sha256')!=p.digest() or not receipt.get('encoder_released')
                    or receipt.get('fixture_sha256')!=digest(fixture)
                    or receipt.get('prompt_sha256')!=digest({k:fixture[k] for k in ('positive','negative')})):
                raise ValueError('text receipt binding differs')
            if (not receipt.get('image_prepared') or not receipt.get('vae_cpu')
                    or receipt.get('vae_precision')!='fp32' or not receipt.get('image_embeds_finite')
                    or receipt.get('image_input_sha256')!=fixture['input_sha256']
                    or receipt.get('image_embeds_shape')!=[16,((fixture['budget']['generated_frames']-1)//4+1) if self.is_matrix else 24,54,96]):
                raise ValueError('prepared image receipt differs')
            write_once(path.with_name('client-accepted.json'),result)
        return result

    def submit(self,trial_id,graph):
        self.bind(trial_id,graph)
        folder=self.root/'trials'/trial_id
        if self._accepted(folder):return self._accepted(folder)
        if not (folder/'intent.json').exists():
            self._matrix_ready(trial=trial_id)
            if self.is_matrix:
                from .wan_wrapper_matrix import utcnow
                write_once(folder/'submission-start.json',dict(started_at_utc=utcnow(),started_monotonic=__import__('time').monotonic()))
        if self._verify()[0].mode=='fast' and not (folder/'intent.json').exists():self._fast_gate()
        try:
            pid=self.delegate.submit(trial_id,graph)
            canonical_uuid(pid);self._accepted(folder)
            return pid
        finally:
            if (folder/'intent.json').exists():self.bind(trial_id,graph)

    def recover(self,trial_id,graph):
        folder=self.root/'trials'/trial_id
        self.bind(trial_id,graph)
        if not (folder/'intent.json').exists():raise ValueError('original intent missing; outcome unknown')
        result=self.completed(trial_id,graph)
        if result is None and (folder/'history.completed.json').exists():return self._collect_archive(trial_id,graph)
        if result:return result
        pid=self.submit(trial_id,graph)
        if self.is_matrix and (folder/'accepted.json').exists():
            history=self._http('GET','/history/'+pid);entry=history.get(pid)
            if entry:
                row=entry.get('prompt',[]);intent=read(folder/'intent.json')
                if len(row)<4 or row[2]!=graph or row[3].get('client_id')!=intent['client_id']:raise ValueError('original recovered history differs')
                if entry.get('status',{}).get('status_str')=='error':
                    write_once(folder/'history.failed.json',history)
                    raise RuntimeError('original matrix request failed; no replay')
                if entry.get('status',{}).get('completed'):
                    write_once(folder/'history.completed.json',history)
                    return self._collect_archive(trial_id,graph)
        return pid

    def _collect_archive(self,trial_id,graph):
        folder=self.root/'trials'/trial_id;pid=self._accepted(folder)
        history=read(folder/'history.completed.json');entry=history.get(pid,{});row=entry.get('prompt',[]);intent=read(folder/'intent.json')
        outputs=entry.get('outputs',{}).get('108',{}).get('images',[])
        if (not pid or len(row)<4 or row[1]!=pid or row[2]!=graph or row[3].get('client_id')!=intent['client_id']
                or entry.get('status',{}).get('completed') is not True or len(outputs)!=1 or outputs[0].get('type')!='output'):
            raise ValueError('original archived history differs')
        target=(self.root/'output'/outputs[0].get('subfolder','')/outputs[0]['filename']).resolve(strict=True)
        if not target.is_relative_to((self.root/'output').resolve()):raise ValueError('archived output escapes root')
        from .wan_wrapper_media import collect_media
        p,f=self._verify();result=collect_media(self.root,target,trial_id=trial_id,prompt_id=pid,profile=p,fixture=f,graph=graph)
        write_once(folder/'technical-complete.json',result)
        return result

    def completed(self,trial_id,graph):
        self.bind(trial_id,graph);folder=self.root/'trials'/trial_id
        if not (folder/'technical-complete.json').exists():return None
        result=read(folder/'technical-complete.json');pid=self._accepted(folder)
        if (not pid or not (folder/'intent.json').exists() or result.get('prompt_id')!=pid
                or result.get('trial_id')!=trial_id or result.get('graph_sha256')!=digest(graph)
                or result.get('profile_sha256')!=self.profile_digest
                or result.get('fixture_sha256')!=digest(read(self.root/'fixture.json'))
                or result.get('input_sha256')!=read(self.root/'fixture.json')['input_sha256']):raise ValueError('completion identity drift')
        history=read(folder/'history.completed.json');row=history[pid]['prompt'];intent=read(folder/'intent.json')
        if len(row)<4 or row[1]!=pid or row[2]!=graph or row[3].get('client_id')!=intent['client_id']:
            raise ValueError('archived history identity differs')
        entry=history[pid];outputs=entry.get('outputs',{}).get('108',{}).get('images',[])
        if entry.get('status',{}).get('completed') is not True or len(outputs)!=1 or outputs[0].get('type')!='output':
            raise ValueError('archived history completion differs')
        target=(self.root/'output'/outputs[0].get('subfolder','')/outputs[0]['filename']).resolve()
        if not target.is_relative_to((self.root/'output').resolve()) or target!=Path(result['generated']).resolve():raise ValueError('original output differs')
        from .wan_wrapper_media import validate_result
        frames=read(self.root/'fixture.json')['budget']['retained_frames'] if self.is_matrix else 93
        if result.get('technical',{}).get('frames')!=frames or result.get('technical',{}).get('fps')!=16:raise ValueError('completed frame contract')
        validate_result(self.root,result,profile=self._verify()[0])
        return result

    def collect(self,trial_id,graph,*,timeout=7200):
        result=self.completed(trial_id,graph)
        if result:return result
        if (self.root/'trials'/trial_id/'history.completed.json').exists():return self._collect_archive(trial_id,graph)
        self.submit(trial_id,graph)
        target,pid=self.delegate.wait(trial_id,graph,timeout=timeout)
        self.bind(trial_id,graph)
        from .wan_wrapper_media import collect_media
        p,f=self._verify()
        result=collect_media(self.root,target,trial_id=trial_id,prompt_id=pid,profile=p,fixture=f,graph=graph)
        write_once(self.root/'trials'/trial_id/'technical-complete.json',result)
        return result

    def close(self):
        # Controller owns lifetime. Client never terminates a PID by number.
        if self.asset_leases:self.asset_leases.close();self.asset_leases=None


def read_v1_archive(root,mode):
    """Read old completed evidence without source leases, network, producer or writes."""
    from .wan_fast_profiles import artifact
    root=Path(root);trial=mode+'_1';folder=root/'trials'/trial
    p=WrapperProfile.from_dict(read(root/f'frozen/profiles/{mode}.json')['profile'])
    if p.identity_dict()['schema_version']!=1:raise ValueError('v1 archive only')
    prepare(root,p);fixture=read(root/'fixture.json');graph=build_graph(p,fixture)
    if not (folder/'technical-complete.json').exists():raise ValueError('original intent outcome unknown; archive only, no POST')
    result=read(folder/'technical-complete.json');intent=read(folder/'intent.json');pid=canonical_uuid(read(folder/'accepted.json')['prompt_id'])
    entry=read(folder/'history.completed.json')[pid];row=entry['prompt']
    if (result['prompt_id']!=pid or result['profile_sha256']!=p.digest() or result['graph_sha256']!=digest(graph)
        or result['fixture_sha256']!=digest(fixture) or intent['graph']!=graph or len(row)<4 or row[1]!=pid
        or row[2]!=graph or row[3].get('client_id')!=intent['client_id'] or not entry.get('status',{}).get('completed')):
        raise ValueError('original archive bindings differ')
    target=Path(result['generated']);proof=read(target.with_suffix('.media-proof.json'))
    claim=read(root/'worker-submissions'/(trial+'.json'));generation=read(target.with_suffix('.generation-binding.json'))
    expected=dict(**claim,prompt_id=pid,media_proof_sha256=digest(proof),
                  encoder_intent_sha256=digest(read(target.with_suffix('.encoder-intent.json'))),
                  encoder_result_sha256=digest(read(target.with_suffix('.encoder-result.json'))))
    if generation!=expected or claim['graph_sha256']!=digest(graph) or claim['client_id']!=intent['client_id']:
        raise ValueError('original worker generation proof differs')
    for role in ('generated','retained','last_frame'):
        path=Path(result[role]).resolve(strict=True)
        if not path.is_relative_to(root.resolve()) or artifact(path).sha256!=result[role+'_sha256']:raise ValueError('original archive media content differs')
    if proof['technical']!=result['technical'] or proof['last_frame_sha256']!=result['last_frame_sha256'] or proof['source_sha256']!=result['generated_sha256']:
        raise ValueError('original full media proof differs')
    return result
