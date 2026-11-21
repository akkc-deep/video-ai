"""Explicit LVA-07-06 matrix contract. No torch, model loading or implicit execution."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import shutil
import subprocess
import time

from .wan_fast_profiles import artifact, digest, write_once
from .wan_fast_experiment import read

TRIALS = ('cold_1', 'warm_1', 'warm_2', 'warm_3')
FIXTURES = {
    'low': (264244520398999, 93, 93, 0),
    'high': (264244520399048, 93, 93, 0),
    'parent': (264244520399004, 93, 93, 0),
    'child': (264244520399005, 81, 77, 1),
}
GROUPS = tuple(f'{f}-{m}' for f in FIXTURES for m in ('control', 'fast'))
SCRATCH = Path('E:/VideoAI/scratch/benchmarks')
SOURCE_ROOTS = dict(low='LVA-01-gpu-low-20261115-01', high='LVA-01-gpu-high-20261115-01',
                    parent='LVA-01-gpu-parent-20261115-01', child='LVA-01-gpu-parent-20261115-01')


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def is_matrix(profile):
    return profile.identity_dict()['schema_version'] == 2


def validate_contracts(contracts):
    if set(contracts) != set(FIXTURES):
        raise ValueError('exact four fixture contracts required')
    required = {'seed_high','seed_low','generated_frames','retained_frames','retained_source_start',
                'source_fixture_sha256','prompt_sha256','expected_tokens'}
    for key, values in FIXTURES.items():
        c = contracts[key]
        if set(c) != required or tuple(c.get(k) for k in ('seed_high','generated_frames','retained_frames','retained_source_start')) != values or c['seed_low'] != 0:
            raise ValueError('original fixture seed/frame contract differs: '+key)
        for name in ('source_fixture_sha256', 'prompt_sha256'):
            value = c[name]
            if not isinstance(value,str) or len(value)!=64 or any(x not in '0123456789abcdef' for x in value):
                raise ValueError('fixture digest differs')
        tokens=c['expected_tokens']
        if set(tokens)!={'prompt_embeds','negative_prompt_embeds'} or any(type(n) is not int or n<512 for n in tokens.values()):
            raise ValueError('complete padded native token lengths required')


def create_profiles(common, contracts, *, kind='experiment'):
    from .wan_wrapper_backend import WrapperProfile
    validate_contracts(contracts)
    result={}
    for mode in ('control','fast'):
        value=WrapperProfile.create(mode,common,kind=kind).identity_dict()
        value['schema_version']=2
        value['settings'].pop('num_frames')
        value['frame_contract']={'source':'fixture_contracts','fps':16}
        value['fixture_contracts']=deepcopy(contracts)
        result[mode]=WrapperProfile.from_dict(value)
    return result


def validate_profile(value):
    from .wan_wrapper_backend import WrapperProfile, SETTINGS
    legacy=deepcopy(value)
    if legacy.pop('fixture_contracts',None) is None:
        raise ValueError('matrix fixture contracts missing')
    validate_contracts(value['fixture_contracts'])
    settings=deepcopy(SETTINGS);settings.pop('num_frames')
    if value.get('settings')!=settings or value.get('frame_contract')!={'source':'fixture_contracts','fps':16}:
        raise ValueError('fixed matrix compute/frame settings differ')
    legacy.update(schema_version=1,settings=SETTINGS,frame_contract=dict(generated_frames=93,retained_frames=93,fps=16))
    WrapperProfile.from_dict(legacy)


def validate_fixture(profile, fixture):
    value=profile.identity_dict();key=fixture.get('matrix_fixture')
    if key not in FIXTURES:raise ValueError('unknown matrix fixture')
    c=value['fixture_contracts'][key]
    if any(fixture.get(k)!=c[k] for k in ('seed_high','seed_low','source_fixture_sha256','prompt_sha256','expected_tokens')):
        raise ValueError('frozen fixture seed/text identity differs')
    budget=fixture.get('budget',{})
    if any(budget.get(k)!=c[k] for k in ('generated_frames','retained_frames','retained_source_start')):
        raise ValueError('frozen fixture frame budget differs')
    name=Path(fixture.get('input_relative',''))
    if not fixture.get('input_relative') or name.is_absolute() or '..' in name.parts or not fixture.get('input_sha256'):
        raise ValueError('bounded frozen input required')
    if value['kind']=='experiment':
        if digest({k:fixture[k] for k in ('positive','negative')})!=c['prompt_sha256']:
            raise ValueError('original complete prompt differs')
    return c


def graph(profile, fixture, trial):
    from .wan_wrapper_backend import build_graph
    if trial not in TRIALS:raise ValueError('exact four trials only')
    c=validate_fixture(profile,fixture)
    # Build the established nodes; change only explicit fixture and trial inputs.
    g=build_graph(profile,fixture,_legacy=True)
    g['10']['inputs'].update(num_frames=c['generated_frames'],trial_token=trial)
    for role,node in (('high','30'),('low','40')):
        g[node]['inputs'].update(seed=c['seed_'+role],trial_token=trial)
    g['108']['inputs']['filename_prefix']=f'lva07/{profile.mode}/{trial}'
    return g


def comparison(profiles, fixture):
    a,b=(profiles[m].identity_dict() for m in ('control','fast'))
    if {k:v for k,v in a.items() if k not in ('mode','recipe')} != {k:v for k,v in b.items() if k not in ('mode','recipe')}:
        raise ValueError('matrix common profiles differ')
    for p in profiles.values():validate_fixture(p,fixture)
    value=dict(profiles={m:p.digest() for m,p in profiles.items()},fixture=fixture)
    return dict(comparison=value,comparison_sha256=digest(value))


def freeze_group(root,profiles,fixture,*,matrix_root,group,matrix_sha256,port=8297):
    root=Path(root).resolve();matrix_root=Path(matrix_root).resolve()
    if group not in GROUPS or root!=matrix_root/'groups'/group:raise ValueError('exact group path required')
    if fixture['matrix_fixture']!=group.rsplit('-',1)[0]:raise ValueError('group fixture differs')
    value=comparison(profiles,fixture)
    write_once(root/'fixture.json',fixture)
    for mode,p in profiles.items():
        write_once(root/f'frozen/profiles/{mode}.json',dict(profile=p.identity_dict(),profile_sha256=p.digest()))
        for trial in TRIALS:write_once(root/f'frozen/graphs/{mode}/{trial}.json',graph(p,fixture,trial))
    write_once(root/'frozen/comparison.json',value)
    marker=dict(schema_version=2,kind='LVA-07-06',port=port,matrix_root=str(matrix_root),group=group,
                matrix_sha256=matrix_sha256,mode=group.rsplit('-',1)[1],comparison_sha256=value['comparison_sha256'],
                profiles={m:p.digest() for m,p in profiles.items()})
    write_once(root/'experiment.json',marker)
    return marker


def prepare_group(root,profile):
    from .wan_wrapper_backend import WrapperProfile
    root=Path(root).resolve();marker=read(root/'experiment.json')
    if marker.get('kind')!='LVA-07-06' or marker.get('schema_version')!=2:raise ValueError('matrix group marker')
    matrix_root=Path(marker['matrix_root']).resolve();group=marker['group']
    if group not in GROUPS or root!=matrix_root/'groups'/group:raise ValueError('matrix group path differs')
    profiles={}
    for mode in ('control','fast'):
        saved=read(root/f'frozen/profiles/{mode}.json');p=WrapperProfile.from_dict(saved['profile'])
        if saved!={'profile':p.identity_dict(),'profile_sha256':p.digest()}:raise ValueError('matrix profile drift')
        profiles[mode]=p
    if profiles.get(profile.mode)!=profile:raise ValueError('matrix requested profile differs')
    fixture=read(root/'fixture.json');value=comparison(profiles,fixture)
    if marker['profiles']!={m:p.digest() for m,p in profiles.items()} or marker['comparison_sha256']!=value['comparison_sha256'] or read(root/'frozen/comparison.json')!=value:
        raise ValueError('matrix comparison drift')
    for mode,p in profiles.items():
        for trial in TRIALS:
            if read(root/f'frozen/graphs/{mode}/{trial}.json')!=graph(p,fixture,trial):raise ValueError('matrix graph drift')
    return marker


def matrix_manifest(root):
    root=Path(root).resolve();saved=read(root/'matrix.json');manifest=read(root/'frozen/manifest.json')
    if saved!={'matrix_sha256':digest(manifest),'manifest':manifest}:raise ValueError('matrix manifest drift')
    if manifest.get('task_id')!='LVA-07-06' or manifest.get('groups')!=list(GROUPS) or manifest.get('trials')!=list(TRIALS):
        raise ValueError('matrix allowlist drift')
    if manifest.get('matrix_root')!=str(root) or manifest.get('port')!=8297:raise ValueError('unique matrix root/port differs')
    return saved


def authorize_group(root,authorization):
    root=Path(root).resolve();marker=read(root/'experiment.json');group=marker.get('group')
    if (marker.get('kind')!='LVA-07-06' or group not in GROUPS or root!=Path(marker['matrix_root']).resolve()/'groups'/group):
        raise ValueError('authorization group path differs')
    auth=authorization
    if (not auth or auth.get('task_id')!='LVA-07-06' or auth.get('approved') is not True or not auth.get('user_evidence')
        or auth.get('matrix_sha256')!=marker.get('matrix_sha256') or auth.get('groups')!=list(GROUPS)
        or auth.get('max_samples')!=32 or auth.get('max_samples_per_group')!=4 or auth.get('max_service_seconds','missing') is not None
        or auth.get('max_upscale_frames')!=2848 or auth.get('max_final_outputs')!=24):
        raise ValueError('exact LVA-07-06 matrix authorization required')
    saved=matrix_manifest(marker['matrix_root'])
    if saved['matrix_sha256']!=marker['matrix_sha256']:raise ValueError('matrix authorization identity differs')
    if marker['profiles']!=saved['manifest']['profiles']:raise ValueError('group matrix profiles differ')
    if marker.get('port')!=8297:raise ValueError('fixed matrix port differs')
    fixture=read(root/'fixture.json')
    if fixture['matrix_fixture']!=group.rsplit('-',1)[0] or marker['mode']!=group.rsplit('-',1)[1]:raise ValueError('group role drift')
    key=fixture['matrix_fixture'];template=saved['manifest']['fixtures'][key]
    if key!='child' and fixture!=template:raise ValueError('matrix fixture drift')
    if key=='child' and {k:v for k,v in fixture.items() if k not in ('input_relative','input_sha256','source_image','parent_binding')}!=template:
        raise ValueError('matrix child template drift')
    return marker


def summarize_rows(rows):
    warm=sorted(float(r['seconds']) for r in rows if r['trial'].startswith('warm_') and r.get('seconds') is not None)
    n=len(warm);h=(n-1)*.95 if n else 0;i=int(h)
    p95=warm[i]+(warm[min(i+1,n-1)]-warm[i])*(h-i) if n else None
    return dict(warm=dict(n=n,p50_seconds=statistics.median(warm) if n else None,p95_seconds=p95),
                accepted=sum(r.get('quality')=='accepted' for r in rows),rejected=sum(r.get('quality')=='rejected' for r in rows),
                pending=sum(r.get('quality') not in ('accepted','rejected') for r in rows))


def group_profile(root,mode=None):
    from .wan_wrapper_backend import WrapperProfile
    root=Path(root);marker=read(root/'experiment.json');mode=mode or marker['mode']
    return WrapperProfile.from_dict(read(root/f'frozen/profiles/{mode}.json')['profile'])


def offline_result(root,trial):
    from .wan_wrapper_backend import WrapperExperimentClient
    def no_http(*a,**kw):raise ValueError('original complete archive required; no HTTP')
    root=Path(root);p=group_profile(root)
    client=WrapperExperimentClient(root,profile_digest=p.digest(),port=read(root/'experiment.json')['port'],http=no_http)
    try:
        value=client.completed(trial,graph(p,read(root/'fixture.json'),trial))
        if value is None:raise ValueError('original technical completion required')
        return value
    finally:client.close()


def require_review(root,trial='cold_1',*,validate_media=True):
    root=Path(root);marker=read(root/'experiment.json')
    result=offline_result(root,trial) if validate_media else read(root/'trials'/trial/'technical-complete.json')
    review=read(root/'reviews'/(trial+'.json'))
    expected=dict(matrix_sha256=marker['matrix_sha256'],group=marker['group'],trial_id=trial,
                  profile_sha256=marker['profiles'][marker['mode']],fixture_sha256=digest(read(root/'fixture.json')),
                  graph_sha256=result['graph_sha256'],prompt_id=result['prompt_id'],
                  generated_sha256=result['generated_sha256'],retained_sha256=result['retained_sha256'],
                  last_frame_sha256=result['last_frame_sha256'])
    if review.get('decision')!='accepted' or not review.get('human_evidence') or any(review.get(k)!=v for k,v in expected.items()):
        raise ValueError('exact matrix human acceptance required')
    return result,review


def require_fast_review(root):
    root=Path(root);marker=read(root/'experiment.json')
    if marker['mode']!='fast':raise ValueError('fast group required')
    key=marker['group'].rsplit('-',1)[0];control=Path(marker['matrix_root'])/'groups'/(key+'-control')
    other=read(control/'experiment.json')
    if other['matrix_sha256']!=marker['matrix_sha256'] or other['profiles']!=marker['profiles']:
        raise ValueError('same matrix control required')
    require_review(control,validate_media=False)


def require_parent(root):
    root=Path(root);marker=read(root/'experiment.json');fixture=read(root/'fixture.json')
    binding=fixture.get('parent_binding')
    if not binding:raise ValueError('new accepted Wrapper parent required')
    parent=Path(marker['matrix_root'])/'groups'/('parent-'+marker['mode'])
    if Path(binding.get('parent_root','')).resolve()!=parent.resolve() or binding.get('parent_trial')!='cold_1':
        raise ValueError('exact same mode parent required')
    pm=read(parent/'experiment.json');stopped=read(parent/'service-result.json')
    if pm['profiles'][marker['mode']]!=marker['profiles'][marker['mode']] or pm['matrix_sha256']!=marker['matrix_sha256']:
        raise ValueError('same matrix/profile parent required')
    if not stopped.get('exited') or not stopped.get('port_closed'):raise ValueError('parent service must exit before child')
    result,review=require_review(parent,validate_media=False)
    if artifact(result['last_frame']).sha256!=result['last_frame_sha256']:raise ValueError('accepted parent tail content differs')
    expected=dict(parent_root=str(parent.resolve()),parent_trial='cold_1',profile_sha256=result['profile_sha256'],
                  prompt_id=result['prompt_id'],generated_sha256=result['generated_sha256'],
                  retained_sha256=result['retained_sha256'],last_frame_sha256=result['last_frame_sha256'],
                  review_sha256=digest(review))
    if binding!=expected or fixture['input_sha256']!=result['last_frame_sha256']:
        raise ValueError('accepted parent/tail/review differs')
    return result


def original_fixtures():
    from .wan_wrapper_backend import SOURCE
    from video_ai.planning.production_scenes import canonical_digest
    fixtures={};sources=[]
    for key,folder in SOURCE_ROOTS.items():
        root=SCRATCH/folder;child=key=='child';name='child-' if child else ''
        fp=root/('child-fixture.json' if child else 'fixture.json')
        request=root/'frozen'/(name+'original-request.json');gp=root/'frozen'/(name+'original-graph.json')
        f=read(fp);req=read(request);g=read(gp);params=req['parameters']
        request_sha=artifact(request).sha256
        if f.get('source_request_sha256',request_sha)!=request_sha:raise ValueError('original request content drift')
        prompt_sha=digest({k:params[k] for k in ('positive','negative')})
        if f.get('prompt_sha256',prompt_sha)!=prompt_sha:raise ValueError('original fixture prompt drift')
        if canonical_digest(g)!=f['source_graph_sha256'] or req['graph_sha256']!=f['source_graph_sha256']:
            raise ValueError('original fixture/request/graph differs')
        conditioning=[v for v in g.values() if v.get('class_type')=='WanImageToVideo']
        if len(conditioning)!=1:raise ValueError('unique original image conditioning node required')
        for name in ('positive','negative'):
            link=conditioning[0]['inputs'][name]
            if g[link[0]]['inputs'].get('text')!=params[name]:raise ValueError('original graph/request full text differs')
        if not child:
            # request.input_sha256 hashes the input RECORD, not the adapted PNG.
            inputs=read(SOURCE/'docs/task-designs/LVA-01-gpu-experiments.json')['fixtures']
            record=next(row for row in inputs if row['id']==f['fixture_id'])
            input_path=Path(record['source_request']).parent/'input.json';input_record=read(input_path)
            if (canonical_digest(input_record)!=req['input_sha256'] or input_record['target']['sha256']!=f['input_sha256']
                or input_record['source']['sha256']!=f['selected_image_sha256'] or req['selected_image']['sha256']!=f['selected_image_sha256']):
                raise ValueError('original selected-input record binding differs')
            sources.append(artifact(input_path).identity_dict())
        c=FIXTURES[key]
        if (params['seed_high'],params['length'],f['budget']['retained_frames'],f['budget']['retained_source_start'])!=c or params['seed_low']!=0:
            raise ValueError('original fixed fixture budget differs')
        if params['steps']!=40 or params['cfg']!=3.5 or params['lora_enabled']:raise ValueError('original quality request required')
        f.update(matrix_fixture=key,positive=params['positive'],negative=params['negative'],seed_high=params['seed_high'],seed_low=0,
                 source_fixture_sha256=artifact(fp).sha256,prompt_sha256=prompt_sha)
        if not child:
            image=root/'input'/f['input_relative'];identity=artifact(image)
            if identity.sha256!=f['input_sha256']:raise ValueError('original selected input differs')
            f.update(input_relative='start.png',source_image=identity.identity_dict())
        else:
            for name in ('input_relative','input_sha256','input_policy','parent_binding'):f.pop(name,None)
        # Audio/font bindings are direct downstream inputs, frozen before GPU.
        original=SCRATCH/SOURCE_ROOTS['parent'] if child else root
        narration=read(original/'narration-source.json');font=read(original/'render-font.json')
        expected_request=artifact(original/'frozen/original-request.json').sha256
        if narration.get('original_request_sha256')!=expected_request:raise ValueError('original narration request binding differs')
        if artifact(narration['path']).sha256!=narration['sha256'] or artifact(font['path']).sha256!=font['sha256']:
            raise ValueError('original narration/font differs')
        f['postprocess_sources']=dict(narration=narration,font=font)
        fixtures[key]=f;sources.extend(artifact(p).identity_dict() for p in (fp,request,gp,original/'narration-source.json',original/'render-font.json'))
    return fixtures,sources


def init_matrix(root):
    from .wan_wrapper_backend import SOURCE
    import sys
    root=Path(root).resolve()
    if root==SCRATCH.resolve() or not root.is_relative_to(SCRATCH.resolve()) or root.exists():raise ValueError('new matrix scratch root required')
    if shutil.disk_usage(SCRATCH).free<32*1024**3:raise ValueError('32GiB new experiment disk reserve required')
    handoff_at_utc=utcnow();handoff_monotonic=time.monotonic()
    fixtures,source_artifacts=original_fixtures()
    root.mkdir();(root/'frozen').mkdir()
    write_once(root/'frozen/token-input.json',fixtures)
    environment=SCRATCH/'LVA-07-04-environment'
    command=[str(environment/'python_embeded/python.exe'),'-I','-B','-X','utf8',str(SOURCE/'scripts/inspect_wan_wrapper_matrix_tokens.py'),
             '--input',str(root/'frozen/token-input.json'),'--output',str(root/'frozen/token-lengths.json')]
    with (root/'tokenizer.stdout.log').open('xb') as out,(root/'tokenizer.stderr.log').open('xb') as err:
        result=subprocess.run(command,stdout=out,stderr=err,timeout=180,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('original CPU tokenizer preparation failed; see tokenizer.stderr.log')
    counts=read(root/'frozen/token-lengths.json')['expected_tokens'];contracts={}
    for key,f in fixtures.items():
        f['expected_tokens']=counts[key]
        contracts[key]={k:f[k] for k in ('seed_high','seed_low','source_fixture_sha256','prompt_sha256','expected_tokens')}
        contracts[key].update({k:f['budget'][k] for k in ('generated_frames','retained_frames','retained_source_start')})
    sys.path.insert(0,str(SOURCE/'scripts'))
    from observe_wan_wrapper_comfy import make_profiles,verify_environment
    verify_environment();common=make_profiles()['control'].identity_dict()['common']
    common['source']['artifacts'].extend(source_artifacts)
    ps=create_profiles(common,contracts)
    for mode,p in ps.items():write_once(root/f'frozen/profiles/{mode}.json',dict(profile=p.identity_dict(),profile_sha256=p.digest()))
    manifest=dict(schema_version=2,task_id='LVA-07-06',matrix_root=str(root),port=8297,groups=list(GROUPS),trials=list(TRIALS),
                  profiles={m:p.digest() for m,p in ps.items()},fixtures=fixtures,
                  handoff_at_utc=handoff_at_utc,handoff_monotonic=handoff_monotonic,
                  max_samples=32,max_upscale_frames=2848,max_final_outputs=24,model_copies=0)
    write_once(root/'frozen/manifest.json',manifest)
    saved=dict(matrix_sha256=digest(manifest),manifest=manifest);write_once(root/'matrix.json',saved)
    for group in GROUPS:
        key=group.rsplit('-',1)[0]
        if key=='child':continue
        f=fixtures[key];gr=root/'groups'/group
        freeze_group(gr,ps,f,matrix_root=root,group=group,matrix_sha256=saved['matrix_sha256'])
        (gr/'input').mkdir();shutil.copyfile(f['source_image']['path'],gr/'input/start.png')
        if artifact(gr/'input/start.png').sha256!=f['input_sha256']:raise ValueError('matrix copied image differs')
    return dict(root=str(root),matrix_sha256=saved['matrix_sha256'],profiles=manifest['profiles'],
                tokens=counts,gpu_used=False,full_model_payload_read=False)


def seal_child(root,group):
    from .wan_wrapper_backend import WrapperProfile
    root=Path(root).resolve();saved=matrix_manifest(root)
    if group not in ('child-control','child-fast'):raise ValueError('child group required')
    mode=group.rsplit('-',1)[1];parent=root/'groups'/('parent-'+mode)
    result,review=require_review(parent)
    stopped=read(parent/'service-result.json')
    if not stopped.get('exited') or not stopped.get('port_closed'):raise ValueError('parent owned service must exit')
    ps={m:WrapperProfile.from_dict(read(root/f'frozen/profiles/{m}.json')['profile']) for m in ('control','fast')}
    fixture=deepcopy(saved['manifest']['fixtures']['child']);identity=artifact(result['last_frame'])
    fixture.update(input_relative='start.png',input_sha256=identity.sha256,source_image=identity.identity_dict(),
        parent_binding=dict(parent_root=str(parent.resolve()),parent_trial='cold_1',profile_sha256=result['profile_sha256'],
                            prompt_id=result['prompt_id'],generated_sha256=result['generated_sha256'],
                            retained_sha256=result['retained_sha256'],last_frame_sha256=result['last_frame_sha256'],review_sha256=digest(review)))
    gr=root/'groups'/group
    marker=freeze_group(gr,ps,fixture,matrix_root=root,group=group,matrix_sha256=saved['matrix_sha256'])
    (gr/'input').mkdir(exist_ok=True)
    target=gr/'input/start.png'
    if not target.exists():shutil.copyfile(result['last_frame'],target)
    if artifact(target).sha256!=fixture['input_sha256']:raise ValueError('child copy differs')
    require_parent(gr)
    return marker


def review(root,group,trial,decision,evidence):
    if group not in GROUPS or trial not in TRIALS or decision not in ('accepted','rejected') or not evidence.strip():raise ValueError('explicit original human quality decision required')
    root=Path(root);gr=root/'groups'/group;marker=read(gr/'experiment.json');result=offline_result(gr,trial)
    value=dict(task_id='LVA-07-06',matrix_sha256=marker['matrix_sha256'],group=group,trial_id=trial,
               profile_sha256=marker['profiles'][marker['mode']],fixture_sha256=digest(read(gr/'fixture.json')),
               graph_sha256=result['graph_sha256'],prompt_id=result['prompt_id'],decision=decision,human_evidence=evidence,
               **{k+'_sha256':result[k+'_sha256'] for k in ('generated','retained','last_frame')},recorded_at_utc=utcnow())
    requested=gr/'reviews'/(trial+'-requested.json')
    if requested.exists():value['requested_at_utc']=read(requested)['requested_at_utc']
    write_once(gr/'reviews'/(trial+'.json'),value)
    return value


def report(root):
    root=Path(root);saved=matrix_manifest(root);groups={}
    for group in GROUPS:
        gr=root/'groups'/group;rows=[]
        stages=[json.loads(line) for line in (gr/'stage-metrics.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()] if (gr/'stage-metrics.jsonl').exists() else []
        for trial in TRIALS:
            record=gr/'trials'/trial/'technical-complete.json';rv=gr/'reviews'/(trial+'.json')
            row=dict(trial=trial,status='NOT_RUN',seconds=None,quality='pending')
            folder=gr/'trials'/trial
            if (folder/'intent.json').exists():row['status']='SUBMIT_UNKNOWN'
            if (folder/'accepted.json').exists():row.update(status='ACCEPTED_PENDING',prompt_id=read(folder/'accepted.json')['prompt_id'])
            if (folder/'history.failed.json').exists():row.update(status='FAILED',failure=str(folder/'history.failed.json'))
            if record.exists():
                result=read(record)
                row.update(status='TECHNICAL_COMPLETE',result=str(record),prompt_id=result['prompt_id'],
                           generated_sha256=result['generated_sha256'],retained_sha256=result['retained_sha256'])
                timing=folder/'timing.json'
                if timing.exists():row['seconds']=read(timing).get('original_submit_to_technical_seconds')
            if rv.exists():row.update(quality=read(rv)['decision'],review=str(rv))
            row['stages']=[item for item in stages if item.get('trial')==trial]
            history=folder/'history.completed.json'
            if history.exists():
                entry=read(history).get(row.get('prompt_id'),{})
                messages=entry.get('status',{}).get('messages',[])
                starts=[v[1]['timestamp'] for v in messages if v[0]=='execution_start' and 'timestamp' in v[1]]
                ends=[v[1]['timestamp'] for v in messages if v[0]=='execution_success' and 'timestamp' in v[1]]
                row['execution_seconds']=(ends[-1]-starts[0])/1000 if starts and ends else None
            row['forward_evidence']={role:str(gr/f'node-evidence/{trial}/{role}.json') for role in ('high','low') if (gr/f'node-evidence/{trial}/{role}.json').exists()}
            rows.append(row)
        groups[group]=dict(rows=rows,summary=summarize_rows(rows),service_result=str(gr/'service-result.json') if (gr/'service-result.json').exists() else None,
                          stage_metrics=str(gr/'stage-metrics.jsonl'),resources=str(gr/'resources.jsonl'))
        groups[group]['setup_stages']=[item for item in stages if item.get('trial') is None]
        groups[group]['resource_summary']=resource_summary(gr/'resources.jsonl')
        launch=gr/'frozen/service-launch.json'
        if launch.exists():groups[group]['service_launch']=read(launch)
    final={}
    for group in GROUPS:
        if group.startswith('parent-'):continue
        for trial in TRIALS:
            work=root/'postprocess'/f'{group}-{trial}';rp=work/'final-review.json';done=work/'operation-complete.json'
            final[f'{group}/{trial}']=dict(status='NOT_RUN' if not done.exists() else 'AWAITING_REVIEW',
                quality=read(rp)['decision'] if rp.exists() else 'pending',receipt=str(done) if done.exists() else None,
                owned_exit_ok=False)
            if done.exists() and (work/'service-result.json').exists():
                exited=read(work/'service-result.json')
                final[f'{group}/{trial}']['owned_exit_ok']=bool(exited.get('exited') and exited.get('port_closed') and exited.get('exit_code')==0)
            if rp.exists() and done.exists():
                approval=read(rp);operation=read(done);candidate=operation['candidate']
                if approval.get('operation_sha256')!=digest(operation) or approval.get('candidate_sha256')!=candidate['candidate_sha256']:
                    final[f'{group}/{trial}']['quality']='CONFLICT'
    native_complete=all(r['status']=='TECHNICAL_COMPLETE' and r['quality']=='accepted' for g in groups.values() for r in g['rows'])
    final_complete=all(r['quality']=='accepted' and r['owned_exit_ok'] for r in final.values())
    owned_complete=all((root/'groups'/g/'service-result.json').exists() and read(root/'groups'/g/'service-result.json').get('passed') for g in GROUPS)
    stopped_failure=any(r['status']=='FAILED' or r['quality']=='rejected' for g in groups.values() for r in g['rows']) or any(r['quality']=='rejected' for r in final.values())
    return dict(task_id='LVA-07-06',matrix_sha256=saved['matrix_sha256'],updated_at_utc=utcnow(),groups=groups,final_outputs=final,
                complete=native_complete and final_complete and owned_complete,observed_failure_stop=stopped_failure,
                production_ready=False,quality_policy='Only explicit original human decisions count',
                temperature='fresh process after preparation/admission; not disk/model cold',
                limitations=['integer timesteps, fp32 VAE and different sampling recipe; not pure backend speedup',
                             'report reads receipts only; missing/unknown/rejected samples are not successful'])


def require_no_rejection(root):
    root=Path(root)
    for path in list((root/'groups').glob('*/reviews/*.json'))+list((root/'postprocess').glob('*/final-review.json')):
        if read(path).get('decision')=='rejected':raise ValueError('human quality rejection stops all new production')
    for path in (root/'groups').glob('*/trials/*/history.failed.json'):
        raise ValueError('original technical failure stops all new production: '+str(path))


def require_all_native_accepted(root):
    require_no_rejection(root)
    for group in GROUPS:
        for trial in TRIALS:require_review(Path(root)/'groups'/group,trial,validate_media=False)


def review_final(root,group,trial,decision,evidence):
    if group not in GROUPS or group.startswith('parent-') or trial not in TRIALS or decision not in ('accepted','rejected') or not evidence.strip():
        raise ValueError('explicit final media human decision required')
    root=Path(root);work=root/'postprocess'/f'{group}-{trial}';done=read(work/'operation-complete.json');candidate=done['candidate']
    if artifact(candidate['candidate']).sha256!=candidate['candidate_sha256']:raise ValueError('final candidate content differs')
    result=dict(task_id='LVA-07-06',matrix_sha256=matrix_manifest(root)['matrix_sha256'],group=group,trial=trial,
                decision=decision,human_evidence=evidence,recorded_at_utc=utcnow(),operation_sha256=digest(done),
                candidate_sha256=candidate['candidate_sha256'],subtitles_sha256=candidate['subtitles_sha256'],
                narration=candidate['narration'])
    write_once(work/'final-review.json',result)
    return result


def request_review(root,group,trial,scope):
    root=Path(root)
    if group not in GROUPS or trial not in TRIALS or scope not in ('native','final'):raise ValueError('specific actual media review scope required')
    if scope=='native':
        gr=root/'groups'/group;result=offline_result(gr,trial);path=gr/'reviews'/(trial+'-requested.json')
        media=result['retained'];sha=result['retained_sha256']
    else:
        work=root/'postprocess'/f'{group}-{trial}';done=read(work/'operation-complete.json');candidate=done['candidate']
        media=candidate['candidate'];sha=candidate['candidate_sha256'];path=work/'final-review-requested.json'
    if artifact(media).sha256!=sha:raise ValueError('actual review media content differs')
    if path.exists():return read(path)
    value=dict(group=group,trial=trial,scope=scope,media=media,media_sha256=sha,requested_at_utc=utcnow())
    write_once(path,value)
    return value


def record_trial_timing(root,trial,mode,*,observed_monotonic=None):
    root=Path(root);folder=root/'trials'/trial;path=folder/'timing.json'
    if path.exists():return read(path)
    source=folder/'submission-start.json';start=read(source) if source.exists() else None
    now=time.monotonic() if observed_monotonic is None else observed_monotonic
    elapsed=now-start['started_monotonic'] if start else None
    value=dict(original_started_at_utc=start['started_at_utc'] if start else None,technical_observed_at_utc=utcnow(),
               technical_observed_monotonic=now,
               original_submit_to_technical_seconds=elapsed if elapsed is not None and elapsed>=0 else None,
               observation_mode=mode,boundary='first durable submission start to observed technical completion; recovery/notification delay retained')
    write_once(path,value)
    return value


def resource_summary(path):
    path=Path(path)
    if not path.exists():return None
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    good=[r for r in rows if r.get('status')=='observed'];memory=[r['process_memory'] for r in rows if r.get('process_memory')]
    devices=[d for r in good for d in r.get('devices',[])]
    return dict(samples=len(rows),observed_samples=len(good),interval_seconds=10,
                native_peak_rss_bytes=max((r['peak_rss'] for r in memory),default=None),
                native_peak_private_commit_bytes=max((r['peak_private_commit'] for r in memory),default=None),
                device_sampled_peak_used_mib=max((d['used_mib'] for d in devices),default=None),
                device_sampled_peak_utilization_percent=max((d['utilization_percent'] for d in devices),default=None),
                last_process_counters=memory[-1] if memory else None,
                scope='device-wide sampled GPU values; native process counters; blockswap40 configured, physical offload count not separately measured')
