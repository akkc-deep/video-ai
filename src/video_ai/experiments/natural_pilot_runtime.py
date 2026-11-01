"""Serial stationary pilot acquisition; frozen source helpers remain unchanged."""
from fractions import Fraction
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
from time import monotonic
from uuid import uuid4

from .natural_pilot import load_pilot, pilot_case
from .natural_acquisition import identity, read_json, verify, write_json
from .natural_acquisition_runtime import _reference_gate, _finish, _recover_case, _verified_result
from ..config import load_config
from ..runtime.paths import RuntimePaths, create_run
from ..runtime.logging import RunLogger
from ..runtime.manifest import now, hash_file, thaw
from ..runtime.research_material_records import verify_wan_material, load_research_material_context


def _generate_pilot(root, plan, case, folder):
    from ..adapters.common import HttpClient
    from ..adapters.comfyui import ComfyClient
    from ..runtime.manifest import create_manifest
    from ..runtime.production_inputs import freeze_inputs, check_stage_space
    from ..runtime.production_state import RunLock
    from ..runtime.workflows import WorkflowTemplate
    from ..runtime.production_visual_templates import validate_fixed_visual_template, validate_production_model_paths
    from ..runtime.services import ServiceManager, port_listening
    from ..runtime.service_specs import build_service_specs
    from ..runtime.owned_cleanup import stop_owned_preserving_exception
    config=load_config(Path(plan['config']['path']));paths=RuntimePaths.from_config(config)
    if port_listening(config.services['comfyui'],3):
        raise RuntimeError('external Comfy service is listening; do not take over')
    check_stage_space(config,frames=49);validate_production_model_paths(config)
    folder.mkdir(parents=True,exist_ok=False)
    run=create_run(paths)
    write_json(folder/'generation-run.json',dict(case_id=case['case_id'],run_dir=str(run),created_at=now(),
        collection=read_json(Path(root)/'collection-receipt.json')['collection']))
    _reference_gate(case,folder,config,paths)
    frozen=freeze_inputs(config,run,text=case['positive_prompt']);config=frozen.config
    reference=Path(case['reference']['path'])
    store=create_manifest(run,config,inputs=dict(selected_image=thaw(hash_file(reference))),models={},workflows={},verify_integrity=False)
    logger=RunLogger(run,production=True)
    for name in ('input','output','temp','user'): (run/'comfy'/name).mkdir(parents=True,exist_ok=True)
    relative=run.name+'/vco06_material/selected-reference.png';model_input=run/'comfy/input'/relative
    model_input.parent.mkdir(parents=True)
    with reference.open('rb') as source,model_input.open('xb') as target: shutil.copyfileobj(source,target)
    template=WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['wan']['path']),
        Path(frozen.options['workflow_snapshots']['wan_mapping']['path']),config.models)
    validate_fixed_visual_template(template,'wan')
    parameters=dict(positive_prompt=case['positive_prompt'],start_image=relative,width=768,height=432,
        length=49,fps=16,seed_high=case['seed_high'],seed_low=case['seed_low'])
    graph=template.instantiate(parameters,output_prefix=run.name+'/vco06_material/wan')
    graph_ref=write_json(folder/'evidence/wan-graph.json',graph)
    request_ref=write_json(folder/'evidence/wan-material-request.json',dict(schema_version=1,
        record_kind='real_direct_wan_material_request',created_at=now(),run_dir=str(run),
        selected_image=case['reference'],actual_model_input=identity(model_input),conversion=case['conversion'],
        parameters=parameters,graph=graph_ref,frozen_options=identity(run/'production/options.json'),
        scope='Separate four-request stationary development pilot; complete original49 native16 output, no injected video bias.'))
    with RunLock(run):
        manager=ServiceManager(paths,store,logger);handle=None
        try:
            handle=manager.ensure(build_service_specs(config,run,production=True,frozen=frozen,store=store)['comfyui'])
            if not handle.owned: raise RuntimeError('Comfy process must be owned by this pilot')
            client=ComfyClient(HttpClient(config.services['comfyui'],config.timeouts['comfy_request'],logger),store,logger)
            client.validate_template(template)
            load_pilot(root);verify(case['reference'])
            if identity(model_input)['sha256']!=case['reference']['sha256']:
                raise ValueError('actual pilot model input differs')
            print('SUBMIT_ONE',case['case_id'],flush=True)
            submission=client.submit_once(graph,stage='source_clips',kind='shot_attempt',unit_id='shot_0001:attempt_0001')
            write_json(folder/'evidence/submission.json',dict(prompt_id=submission.prompt_id,attempt_id=submission.attempt_id,
                request=request_ref,created_at=now()))
            print('PROMPT',case['case_id'],submission.prompt_id,flush=True)
            client.wait_for(submission,deadline_seconds=config.timeouts['wan'],poll_seconds=5)
            history=client.http.get_json('/history/'+submission.prompt_id)[submission.prompt_id]
            return _finish(case,folder,run,frozen,store,logger,history)
        finally:
            if handle is not None: stop_owned_preserving_exception(manager,handle,logger,'vco06-stationary-pilot')


@contextmanager
def _pilot_acquisition_lock(root):
    from . import natural_pilot
    load_pilot(root)
    path=natural_pilot.PILOT_ROOT/'.pilot-comfy-acquire.lock'
    owner=dict(pid=os.getpid(),token=uuid4().hex,root=str(root),created_at=now())
    try: write_json(path,owner)
    except FileExistsError as error:
        raise RuntimeError('pilot model acquisition is locked; do not take over or submit') from error
    try: yield
    finally:
        if read_json(path)!=owner: raise RuntimeError('pilot acquisition lock owner changed; retained')
        path.unlink()


def acquire_pilot_case(root, case_id):
    plan,case,folder=pilot_case(root,case_id)
    if (folder/'evidence/generation-result.json').is_file(): return _verified_result(root,case,folder)
    with _pilot_acquisition_lock(root):
        # Bind again after acquiring the cross-case, cross-pilot service guard.
        plan,case,folder=pilot_case(root,case_id)
        if folder.exists():
            if (folder/'evidence/generation-result.json').is_file(): return _verified_result(root,case,folder)
            if not (folder/'generation-run.json').is_file():
                raise ValueError('existing incomplete pilot case without locator; no new dispatch')
            return _recover_case(root,case,folder)
        try: return _generate_pilot(root,plan,case,folder)
        except BaseException as error:
            if folder.exists(): write_json(folder/('failure-'+uuid4().hex+'.json'),dict(created_at=now(),case_id=case_id,
                kind=type(error).__name__,message=str(error),recovery='Original request only; no replacement or new POST.'))
            raise


def _prepare_index(plan,case,folder,result):
    from .natural_material_preparation import save_mapping_evidence
    from ..media.colorimetry import inspect_color_asset, decode_analysis_frame, load_color_analysis_set
    from ..runtime.processes import run_logged
    from ..runtime.environment import build_child_env
    config=load_config(Path(plan['config']['path']));paths=RuntimePaths.from_config(config)
    logger=RunLogger(create_run(paths));started=monotonic()
    write_json(folder/('pilot-preparation-'+logger.run_dir.name+'.json'),dict(created_at=now(),
        case_id=case['case_id'],source=result['video'],implementation=identity(Path(__file__)),audit_run=str(logger.run_dir)))
    command=run_logged([str(config.tools['ffprobe']),'-v','error','-count_frames','-show_streams','-show_frames',
        '-of','json',result['video']['path']],cwd=logger.run_dir,env=build_child_env(paths),timeout=300,
        logger=logger,stage='pilot_native_probe',unit_id='wan_material_0001')
    if command.returncode!=0 or command.timed_out: raise ValueError('pilot complete native probe failed')
    probe=read_json(command.stdout_path);streams,frames=probe['streams'],probe['frames']
    if (len(streams)!=1 or streams[0]['codec_type']!='video' or len(frames)!=49
            or Fraction(streams[0]['r_frame_rate'])!=16 or Fraction(streams[0]['avg_frame_rate'])!=16
            or any(Fraction(f['pts'])*Fraction(streams[0]['time_base'])!=Fraction(i,16) for i,f in enumerate(frames))):
        raise ValueError('complete pilot49 native16/PTS/video-only contract differs')
    rows=[dict(asset_frame_index=i,clip_id='wan_material_0001',generated_frame_index=i,retained_frame_index=None,
        output_frame_index=None,pts=f['pts'],time_base=streams[0]['time_base']) for i,f in enumerate(frames)]
    proof=save_mapping_evidence(folder,Path(result['video']['path']),rows,audit_id=logger.run_dir.name)
    sidecar,_=inspect_color_asset(dict(asset_id='generated_material',stage='generated',path=result['video']['path'],
        mapping=dict(rows=rows,evidence=[thaw(hash_file(proof))]),processing=dict(
            operation='Unmodified original pilot Wan output, complete material coordinates.',upstream_ids=[],command_records=[])),
        config=config,paths=paths,logger=logger,timeout=300)
    records=[]
    for i in range(49):
        remaining=300-(monotonic()-started)
        if remaining<=0: raise TimeoutError('pilot all49-frame decode exceeded300 seconds')
        record,_=decode_analysis_frame(sidecar,frame_index=i,config=config,paths=paths,logger=logger,timeout=remaining)
        if record['status']!='ready' or record['pixels'] is None: raise ValueError('every pilot frame requires proven sRGB pixels')
        records.append(identity(logger.root/'colorimetry/generated_material/analysis'/f'frame_{i:06d}.json'))
    with load_color_analysis_set([r['path'] for r in records],config=config,timeout=300) as reader:
        for row in records:
            if reader.read_rgb(row['path']) is None: raise ValueError('missing pilot RGB frame')
        reader.verify()
    gate=read_json(folder/'evidence/reference-gate.json')
    write_json(folder/'source-index.json',dict(schema_version=1,kind='wan_material_evidence_v1',
        request=result['request'],result=identity(folder/'evidence/generation-result.json'),reference=gate['analysis'],frames=records))


def prepare_pilot_case(root, case_id):
    from ..runtime.production_research_material import import_research_material
    plan,case,folder=pilot_case(root,case_id);result=_verified_result(root,case,folder)
    index_path=folder/'source-index.json'
    if not index_path.exists(): _prepare_index(plan,case,folder,result)
    index=read_json(index_path);gate=read_json(folder/'evidence/reference-gate.json')
    if (index.get('request')!=result['request'] or index.get('result')!=identity(folder/'evidence/generation-result.json')
            or index.get('reference')!=gate['analysis']):
        raise ValueError('pilot source-index/case binding differs')
    request_path=folder/'import-request.json'
    if request_path.exists():
        request=read_json(request_path)
        if request.get('source_index')!=identity(index_path) or request.get('config')!=plan['config']:
            raise ValueError('pilot import request/case binding differs')
    config=load_config(Path(plan['config']['path']))
    verify_wan_material(index_path,config=config)
    if not request_path.exists():
        write_json(request_path,dict(schema_version=1,material_id=str(uuid4()),policy='research_material_import_v1',
            source_index=identity(index_path),config=plan['config'],requested_at=now(),
            reason='Four-request stationary development pilot, technical import only; natural label unverified.'))
    output=folder/'import-result.json'
    if output.exists(): imported=read_json(output)
    else:
        imported=import_research_material(request_path,paths=RuntimePaths.from_config(config))
        write_json(output,imported)
    context=load_research_material_context(Path(imported['run_dir']))
    if (imported.get('status')!='research_input_ready' or imported['commit']!=context['commit']
            or any(context['source'][k]!=result['video'][k] for k in ('bytes','sha256'))
            or any(context['selected_image'][k]!=case['reference'][k] for k in ('bytes','sha256'))):
        raise ValueError('pilot imported source/reference/case identity differs')
    return imported


def pilot_status(root):
    plan=load_pilot(root);rows=[]
    for case in plan['cases']:
        folder=Path(root)/'cases'/case['case_id'];state='not_started';video=None;imported=None
        if folder.exists(): state='incomplete'
        if (folder/'evidence/generation-result.json').is_file():
            video=_verified_result(root,case,folder)['video'];state='generated'
        if (folder/'import-result.json').is_file():
            imported=read_json(folder/'import-result.json')
            context=load_research_material_context(Path(imported['run_dir']))
            if (video is None or imported.get('status')!='research_input_ready' or imported['commit']!=context['commit']
                    or any(context['source'][k]!=video[k] for k in ('bytes','sha256'))
                    or any(context['selected_image'][k]!=case['reference'][k] for k in ('bytes','sha256'))):
                raise ValueError('pilot status imported source/case identity differs')
            state='import_recorded'
        rows.append(dict(case_id=case['case_id'],scene_group=case['scene_group'],split='development',
            video=video,reference=case['reference'],state=state,import_result=imported,natural_label='unverified'))
    return dict(status='exploratory_development_only',max_requests=4,cases=rows,
        generated_videos=sum(r['video'] is not None for r in rows),
        import_receipts=sum(r['state']=='import_recorded' for r in rows),ready_for_propose=False,production_eligible=False)


def export_pilot_portal(root):
    status=pilot_status(root);cases=[]
    for case in status['cases']:
        if case['video'] is None: continue
        cases.append(dict(**case,video_url=Path(case['video']['path']).relative_to(root).as_posix(),
            reference_url=Path(case['reference']['path']).relative_to(root).as_posix()))
    data=dict(collection=read_json(Path(root)/'collection-receipt.json')['collection'],cases=cases)
    template=Path(__file__).parents[3]/'scripts/experiments/vco06_observe.html'
    text=template.read_text(encoding='utf-8').replace('/*COLLECTION_DATA*/null',
        json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c'))
    raw=text.encode('utf-8');target=Path(root)/f'observe-pilot-{len(cases):02d}-{hashlib.sha256(raw).hexdigest()[:12]}.html'
    if target.exists():
        if target.read_bytes()!=raw: raise FileExistsError('different pilot portal exists; keep original snapshot')
    else:
        with target.open('xb') as stream: stream.write(raw)
    return dict(status='pilot_observation_portal_ready',cases=len(cases),portal=identity(target),ready_for_propose=False)


def record_pilot_observation(root, observation_path):
    from ..adapters.common import strict_json
    from ..runtime._scene_continuity_io import local
    from .natural_acquisition_observation import _time, validate_observation
    from .natural_remote_observation import validate_remote_observation
    path=local(observation_path,runtime=False)
    with path.open('rb') as stream: raw=stream.read(16*1024**2+1)
    if len(raw)>16*1024**2: raise ValueError('pilot observation exceeds16MiB')
    row=strict_json(raw)
    state=(validate_remote_observation(row) if row.get('kind')=='natural_material_observation_remote_v2' else validate_observation(row))
    _,case,folder=pilot_case(root,row['case_id']);result=_verified_result(root,case,folder)
    if (row['collection']!=read_json(Path(root)/'collection-receipt.json')['collection']
            or row['video']!=result['video'] or row['reference']!=case['reference'] or case['split']!='development'
            or _time(row['reviewed_at'])<_time(result['finished_at'])
            or state!='unverified' and _time(row['playback']['started_at'])<_time(result['finished_at'])):
        raise ValueError('pilot observation source/collection/time binding differs')
    target=Path(root)/'observations'/case['case_id']/(hashlib.sha256(raw).hexdigest()+'.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    try:
        with target.open('xb') as stream: stream.write(raw)
    except FileExistsError:
        if target.read_bytes()!=raw: raise ValueError('pilot observation digest collision')
    return dict(status=state,observation=identity(target),case_id=case['case_id'],natural_label=row['natural_label'],
        ready_for_propose=False,production_eligible=False)
