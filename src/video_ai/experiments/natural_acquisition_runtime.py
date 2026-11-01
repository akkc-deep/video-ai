"""Once-only serial Wan collection, preserving original requests and every outcome."""
from fractions import Fraction
from pathlib import Path
import shutil
from time import monotonic
from uuid import uuid4

from .natural_acquisition import identity, load_collection, read_json, verify, write_json
from ..config import load_config
from ..runtime.manifest import now, hash_file, thaw
from ..runtime.paths import RuntimePaths, create_run
from ..runtime.logging import RunLogger


def _original_acceptance(logger, saved, graph, base_url):
    """Read durable original acceptance even if its manifest cursor was not updated."""
    import math
    from uuid import UUID
    from ..adapters.common import strict_json
    from ..runtime.production_support import recover_http
    posts = [p for p in logger.path('http').glob('*.request.json') if read_json(p).get('method') == 'POST']
    if len(posts) != 1:
        raise ValueError('exactly one original source POST required')
    raw, _, _ = recover_http(logger,uid='shot_0001:attempt_0001',url=base_url+'/prompt',
        payload=dict(prompt=graph,client_id=saved['client_id']),durable=False)
    accepted = strict_json(raw)
    pid, number = accepted.get('prompt_id'),accepted.get('number')
    if (not isinstance(pid,str) or str(UUID(pid)) != pid or type(number) not in (int,float)
            or not math.isfinite(number) or accepted.get('node_errors') != {}
            or saved.get('prompt_id') is not None and saved['prompt_id'] != pid
            or saved.get('number') is not None and saved['number'] != number
            or saved.get('state') in ('failed','rejected')):
        raise ValueError('original acceptance/client/graph identity differs')
    return dict(saved,prompt_id=pid,number=number)


def _case(root, case_id):
    plan = load_collection(root)
    matches = [c for c in plan['cases'] if c['case_id'] == case_id]
    if len(matches) != 1:
        raise ValueError('unknown preregistered case')
    return plan, matches[0], Path(root)/'cases'/case_id


def _locator(root, case, folder):
    value = read_json(folder/'generation-run.json')
    expected = read_json(Path(root)/'collection-receipt.json')['collection']
    if value['case_id'] != case['case_id'] or value['collection'] != expected:
        raise ValueError('existing case locator identity differs')
    from ..runtime.manifest import validate_run_dir
    return validate_run_dir(Path(value['run_dir']))


def _verified_result(root, case, folder):
    run = _locator(root, case, folder)
    result = read_json(folder/'evidence/generation-result.json')
    request_ref = identity(folder/'evidence/wan-material-request.json')
    request = read_json(request_ref['path'])
    expected = dict(positive_prompt=case['positive_prompt'], start_image=run.name+'/vco06_material/selected-reference.png',
        width=768, height=432, length=49, fps=16, seed_high=case['seed_high'], seed_low=case['seed_low'])
    if (result['status'] != 'generated' or result['request'] != request_ref
            or result['selected_image'] != case['reference'] or request['parameters'] != expected
            or request['run_dir'] != str(run) or request['selected_image'] != case['reference']
            or request['conversion'] != case['conversion']):
        raise ValueError('completed acquisition differs from frozen case')
    for item in [result['video'], result['original_model_output'], result['selected_image'],
                 request['actual_model_input'], request['graph'], request['frozen_options']]:
        verify(item)
    if (result['video']['sha256'] != result['original_model_output']['sha256']
            or request['actual_model_input']['sha256'] != case['reference']['sha256']):
        raise ValueError('acquisition media/input byte identity differs')
    _verify_transaction(run,folder,request,result)
    return result


def _verify_transaction(run,folder,request,result):
    from ..runtime.production_inputs import load_frozen_inputs
    from ..runtime.manifest import ManifestStore
    from ..runtime.workflows import WorkflowTemplate
    from ..runtime.production_comfy import _local_histories, output_from_history, same
    frozen = load_frozen_inputs(run)
    manifest = ManifestStore.open(run,verify_integrity=False).snapshot()
    if (request['frozen_options'] != identity(run/'production/options.json')
            or request['actual_model_input']['path'] != str(run/'comfy/input'/request['parameters']['start_image'])
            or {k:manifest['inputs']['selected_image'][k] for k in ('path','bytes','sha256')} != request['selected_image']):
        raise ValueError('original run input/options producer differs')
    saved = manifest['units']['shot_attempt']['shot_0001:attempt_0001']['submission']
    graph = read_json(request['graph']['path'])
    workflow = manifest['workflows'][saved['attempt_id']]
    if ({k:workflow[k] for k in ('path','bytes','sha256')} != identity(saved['request_path'])
            or not same(read_json(saved['request_path']),graph)):
        raise ValueError('original manifest workflow identity differs')
    template = WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['wan']['path']),
        Path(frozen.options['workflow_snapshots']['wan_mapping']['path']),frozen.config.models)
    if template.instantiate(request['parameters'],output_prefix=run.name+'/vco06_material/wan') != graph:
        raise ValueError('original graph differs from frozen parameters/template')
    logger = RunLogger(run,production=True)
    accepted = _original_acceptance(logger,saved,graph,frozen.config.services['comfyui'])
    if accepted['prompt_id'] != result['prompt_id']:
        raise ValueError('result prompt differs from original accepted request')
    targets = []
    for history, _ in _local_histories(logger,'shot_0001:attempt_0001',route='/history/'+accepted['prompt_id']):
        if accepted['prompt_id'] in history:
            target = output_from_history(history[accepted['prompt_id']],accepted,graph,template,run,
                run.name+'/vco06_material/wan','.mp4')
            if target is not None:
                targets.append(identity(target))
    if not targets or any(t != result['original_model_output'] for t in targets):
        raise ValueError('completed actual source history/output required')
    if result['info']['frames'] != 49 or result['info']['fps'] != 16:
        raise ValueError('complete original native video inspection required')
    for evidence in result['technical_evidence']:
        verify(evidence)


def _reference_gate(case, folder, config, paths):
    from ..media.colorimetry import inspect_color_asset, decode_analysis_frame, load_color_analysis_set
    row = dict(asset_frame_index=0,clip_id='repair_reference_image',generated_frame_index=None,
               retained_frame_index=None,output_frame_index=None,pts=0,time_base='1/16')
    proof = folder/'evidence/reference-mapping.json'
    write_json(proof,dict(source=thaw(hash_file(Path(case['reference']['path']))),rows=[row]))
    logger = RunLogger(create_run(paths))
    sidecar, _ = inspect_color_asset(dict(asset_id='selected_reference',stage='native_tail',path=case['reference']['path'],
        mapping=dict(rows=[row],evidence=[thaw(hash_file(proof))]),
        processing=dict(operation='New independently authored sRGB reference before actual Wan request.',
                        upstream_ids=[],command_records=[])), config=config,paths=paths,logger=logger,timeout=300)
    record, _ = decode_analysis_frame(sidecar,frame_index=0,config=config,paths=paths,logger=logger,timeout=300)
    recpath = logger.root/'colorimetry/selected_reference/analysis/frame_000000.json'
    with load_color_analysis_set([recpath],config=config,timeout=300) as reader:
        pixels = reader.read_rgb(recpath)
        reader.verify()
    if sidecar['interpretation']['status'] != 'resolved' or record['status'] != 'ready' or pixels is None:
        raise ValueError('new reference must pass actual sRGB pixel gate before generation')
    write_json(folder/'evidence/reference-gate.json',dict(reference=case['reference'],analysis=identity(recpath),
        color_status='resolved',pixel_status='ready',created_at=now()))


def _finish(case, folder, run, frozen, manifest, logger, history):
    from ..runtime.workflows import WorkflowTemplate
    from ..runtime.production_comfy import output_from_history
    from ..media.video import inspect_video
    config = frozen.config
    paths = RuntimePaths.from_config(config)
    template = WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['wan']['path']),
        Path(frozen.options['workflow_snapshots']['wan_mapping']['path']),config.models)
    saved = manifest.snapshot()['units']['shot_attempt']['shot_0001:attempt_0001']['submission']
    graph = read_json(folder/'evidence/wan-graph.json')
    output = output_from_history(history,saved,graph,template,run,run.name+'/vco06_material/wan','.mp4')
    target = folder/'generated-native16.mp4'
    if not target.exists():
        with output.open('rb') as source, target.open('xb') as dest:
            shutil.copyfileobj(source,dest)
    if identity(target)['sha256'] != identity(output)['sha256']:
        raise ValueError('retained original output differs')
    info, evidence = inspect_video(output,width=768,height=432,config=config,paths=paths,logger=logger,
        unit_id='shot_0001:attempt_0001',timeout=300)
    if info['frames'] != 49 or info['fps'] != 16:
        raise ValueError('complete frozen native frame budget differs')
    result = dict(status='generated',finished_at=now(),case_id=case['case_id'],split=case['split'],
        scene_group=case['scene_group'],source_eligibility='material_only',video=identity(target),
        original_model_output=identity(output),selected_image=case['reference'],info=info,
        technical_evidence=[identity(p) for p in evidence],request=identity(folder/'evidence/wan-material-request.json'),
        prompt_id=saved['prompt_id'],actual_full_playback=False,natural_label='unverified',ready_for_propose=False)
    write_json(folder/'evidence/generation-result.json',result)
    return result


def _recover_case(root, case, folder):
    """Same-request recovery only; never calls submit or starts a replacement run."""
    run = _locator(root,case,folder)
    from ..runtime.production_state import RunLock
    with RunLock(run):
        return _recover_locked(root,case,folder,run)


def _recover_locked(root,case,folder,run):
    from ..runtime.production_inputs import load_frozen_inputs
    from ..runtime.manifest import ManifestStore
    from ..runtime.production_comfy import _local_histories, _accept, _submission
    from ..runtime.workflows import WorkflowTemplate
    from ..runtime.services import port_listening
    from ..adapters.common import HttpClient
    from ..adapters.comfyui import ComfyClient
    frozen = load_frozen_inputs(run)
    store = ManifestStore.open(run,verify_integrity=False)
    saved = store.snapshot()['units'].get('shot_attempt',{}).get('shot_0001:attempt_0001',{}).get('submission')
    if not saved:
        raise ValueError('existing incomplete request: inspect original intent; never repeat POST')
    graph = read_json(folder/'evidence/wan-graph.json')
    logger = RunLogger(run,production=True)
    accepted = _original_acceptance(logger,saved,graph,frozen.config.services['comfyui'])
    template = WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['wan']['path']),
        Path(frozen.options['workflow_snapshots']['wan_mapping']['path']),frozen.config.models)
    client = ComfyClient(HttpClient(frozen.config.services['comfyui'],frozen.config.timeouts['comfy_request'],logger),store,logger)
    if saved.get('prompt_id') is None:
        _accept(client,saved,'source_clips','shot_attempt','shot_0001:attempt_0001',template,
                accepted['prompt_id'],accepted['number'])
    prompt = accepted['prompt_id']
    for history, _ in _local_histories(logger,'shot_0001:attempt_0001',route='/history/'+prompt):
        entry = history.get(prompt)
        if entry and entry.get('status',{}).get('completed') is True:
            return _finish(case,folder,run,frozen,store,logger,entry)
    if not port_listening(frozen.config.services['comfyui'],3):
        raise ValueError('existing accepted request has no complete history and original service is offline; never repeat POST')
    # Existing service is read only: no ownership transfer, startup, cancellation or POST.
    info = client.http.get_json('/system_stats')
    if not isinstance(info,dict) or not isinstance(info.get('system'),dict):
        raise ValueError('original GET recovery service identity unverified')
    client.wait_for(_submission(accepted,'source_clips','shot_attempt','shot_0001:attempt_0001',template),
                    deadline_seconds=frozen.config.timeouts['wan'],poll_seconds=5)
    history = client.http.get_json('/history/'+prompt)[prompt]
    return _finish(case,folder,run,frozen,store,logger,history)


def _generate_new(root, plan, case, folder):
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
    config = load_config(Path(plan['config']['path']))
    paths = RuntimePaths.from_config(config)
    check_stage_space(config,frames=49)
    validate_production_model_paths(config)
    # Exclusive case ownership is persisted before any possible service or POST.
    folder.mkdir(parents=True,exist_ok=False)
    run = create_run(paths)
    write_json(folder/'generation-run.json',dict(case_id=case['case_id'],run_dir=str(run),created_at=now(),
        collection=read_json(Path(root)/'collection-receipt.json')['collection']))
    _reference_gate(case,folder,config,paths)
    frozen = freeze_inputs(config,run,text=case['positive_prompt'])
    config = frozen.config
    reference = Path(case['reference']['path'])
    manifest = create_manifest(run,config,inputs=dict(selected_image=thaw(hash_file(reference))),
        models={},workflows={},verify_integrity=False)
    logger = RunLogger(run,production=True)
    for name in ('input','output','temp','user'):
        (run/'comfy'/name).mkdir(parents=True,exist_ok=True)
    relative = run.name+'/vco06_material/selected-reference.png'
    model_input = run/'comfy/input'/relative
    model_input.parent.mkdir(parents=True)
    with reference.open('rb') as source,model_input.open('xb') as target:
        shutil.copyfileobj(source,target)
    template = WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['wan']['path']),
        Path(frozen.options['workflow_snapshots']['wan_mapping']['path']),config.models)
    validate_fixed_visual_template(template,'wan')
    parameters = dict(positive_prompt=case['positive_prompt'],start_image=relative,width=768,height=432,
        length=49,fps=16,seed_high=case['seed_high'],seed_low=case['seed_low'])
    graph = template.instantiate(parameters,output_prefix=run.name+'/vco06_material/wan')
    graph_ref = write_json(folder/'evidence/wan-graph.json',graph)
    request_ref = write_json(folder/'evidence/wan-material-request.json',dict(schema_version=1,
        record_kind='real_direct_wan_material_request',created_at=now(),run_dir=str(run),
        selected_image=case['reference'],actual_model_input=identity(model_input),conversion=case['conversion'],
        parameters=parameters,graph=graph_ref,frozen_options=identity(run/'production/options.json'),
        scope='Preregistered new full49 native16 real model output; no injected color or production clip claim.'))
    with RunLock(run):
        if port_listening(config.services['comfyui'],3):
            raise RuntimeError('external Comfy service is listening; do not take over')
        manager = ServiceManager(paths,manifest,logger)
        handle = None
        try:
            handle = manager.ensure(build_service_specs(config,run,production=True,frozen=frozen,store=manifest)['comfyui'])
            if not handle.owned:
                raise RuntimeError('Comfy process must be owned by this acquisition')
            client = ComfyClient(HttpClient(config.services['comfyui'],config.timeouts['comfy_request'],logger),manifest,logger)
            client.validate_template(template)
            load_collection(root)
            verify(case['reference'])
            if identity(model_input)['sha256'] != case['reference']['sha256']:
                raise ValueError('actual model input differs')
            print('SUBMIT_ONE',case['case_id'],flush=True)
            submission = client.submit_once(graph,stage='source_clips',kind='shot_attempt',unit_id='shot_0001:attempt_0001')
            write_json(folder/'evidence/submission.json',dict(prompt_id=submission.prompt_id,attempt_id=submission.attempt_id,
                request=request_ref,created_at=now()))
            print('PROMPT',case['case_id'],submission.prompt_id,flush=True)
            client.wait_for(submission,deadline_seconds=config.timeouts['wan'],poll_seconds=5)
            history = client.http.get_json('/history/'+submission.prompt_id)[submission.prompt_id]
            return _finish(case,folder,run,frozen,manifest,logger,history)
        finally:
            if handle is not None:
                stop_owned_preserving_exception(manager,handle,logger,'vco06-preregistered-acquisition')


def acquire_case(root, case_id):
    plan, case, folder = _case(root,case_id)
    if folder.exists():
        if (folder/'evidence/generation-result.json').is_file():
            return _verified_result(root,case,folder)
        if not (folder/'generation-run.json').is_file():
            raise ValueError('existing incomplete case without locator; never dispatch as new')
        return _recover_case(root,case,folder)
    try:
        return _generate_new(root,plan,case,folder)
    except BaseException as exc:
        if folder.exists():
            write_json(folder/('failure-'+uuid4().hex+'.json'),dict(created_at=now(),case_id=case_id,
                kind=type(exc).__name__,message=str(exc),recovery='Original request only; no replacement or automatic POST.'))
        raise


def prepare_case(root, case_id):
    """Technical all-frame sRGB evidence and official import; no holdout natural metrics."""
    plan, case, folder = _case(root,case_id)
    result = _verified_result(root,case,folder)
    from ..media.colorimetry import inspect_color_asset, decode_analysis_frame, load_color_analysis_set
    from ..runtime.processes import run_logged
    from ..runtime.environment import build_child_env
    from ..runtime.research_material_records import verify_wan_material
    from ..runtime.production_research_material import import_research_material
    config = load_config(Path(plan['config']['path']))
    paths = RuntimePaths.from_config(config)
    index_path = folder/'source-index.json'
    if not index_path.exists():
        # Each retry gets a separate audit. Partial original decodes are never overwritten.
        logger = RunLogger(create_run(paths))
        command = run_logged([str(config.tools['ffprobe']),'-v','error','-count_frames','-show_streams',
            '-show_frames','-of','json',result['video']['path']],cwd=logger.run_dir,env=build_child_env(paths),
            timeout=300,logger=logger,stage='native_material_probe',unit_id='wan_material_0001')
        if command.returncode != 0 or command.timed_out:
            raise ValueError('native material probe failed')
        probe = read_json(command.stdout_path)
        streams, frames = probe['streams'], probe['frames']
        if (len(streams) != 1 or streams[0]['codec_type'] != 'video' or len(frames) != 49
                or Fraction(streams[0]['r_frame_rate']) != 16 or Fraction(streams[0]['avg_frame_rate']) != 16
                or any(Fraction(f['pts'])*Fraction(streams[0]['time_base']) != Fraction(i,16) for i,f in enumerate(frames))):
            raise ValueError('complete native16/PTS/video-only contract differs')
        rows = [dict(asset_frame_index=i,clip_id='wan_material_0001',generated_frame_index=i,
            retained_frame_index=None,output_frame_index=None,pts=f['pts'],time_base=streams[0]['time_base'])
            for i,f in enumerate(frames)]
        proof = logger.root/'generated-material-mapping.json'
        write_json(proof,dict(source=thaw(hash_file(Path(result['video']['path']))),rows=rows))
        sidecar, _ = inspect_color_asset(dict(asset_id='generated_material',stage='generated',path=result['video']['path'],
            mapping=dict(rows=rows,evidence=[thaw(hash_file(proof))]),processing=dict(
                operation='Unmodified real Wan output in material coordinates.',upstream_ids=[],command_records=[])),
            config=config,paths=paths,logger=logger,timeout=300)
        records = []
        started = monotonic()
        for i in range(49):
            remaining = 300-(monotonic()-started)
            if remaining <= 0:
                raise TimeoutError('complete native color decode exceeded 300 seconds')
            record, _ = decode_analysis_frame(sidecar,frame_index=i,config=config,paths=paths,logger=logger,timeout=remaining)
            if record['status'] != 'ready' or record['pixels'] is None:
                raise ValueError('all original frames require actual sRGB pixels')
            records.append(identity(logger.root/'colorimetry/generated_material/analysis'/f'frame_{i:06d}.json'))
        with load_color_analysis_set([r['path'] for r in records],config=config,timeout=300) as reader:
            for r in records:
                if reader.read_rgb(r['path']) is None:
                    raise ValueError('missing original pixel frame')
            reader.verify()
        gate = read_json(folder/'evidence/reference-gate.json')
        write_json(index_path,dict(schema_version=1,kind='wan_material_evidence_v1',request=result['request'],
            result=identity(folder/'evidence/generation-result.json'),reference=gate['analysis'],frames=records))
    verify_wan_material(index_path,config=config)
    request_path = folder/'import-request.json'
    if not request_path.exists():
        write_json(request_path,dict(schema_version=1,material_id=str(uuid4()),policy='research_material_import_v1',
            source_index=identity(index_path),config=plan['config'],requested_at=now(),
            reason='Preregistered independent natural material collection; technical import only, observations unverified.'))
    imported = import_research_material(request_path,paths=paths)
    output = folder/'import-result.json'
    if not output.exists():
        write_json(output,imported)
    return imported


def collection_status(root):
    plan = load_collection(root)
    rows = []
    for case in plan['cases']:
        folder = Path(root)/'cases'/case['case_id']
        state = 'not_started'
        media = None
        if folder.exists():
            state = 'incomplete'
            if (folder/'evidence/generation-result.json').is_file():
                media = _verified_result(root,case,folder)['video']
                state = 'generated'
            if (folder/'import-result.json').is_file():
                from ..runtime.research_material_records import load_research_material_context
                imported = read_json(folder/'import-result.json')
                if media is None or imported.get('status') != 'research_input_ready':
                    state = 'invalid_import_record'
                else:
                    context = load_research_material_context(Path(imported['run_dir']))
                    if imported['commit'] != context['commit']:
                        raise ValueError('imported context identity differs')
                    state = 'import_recorded'
        rows.append(dict(case_id=case['case_id'],scene_group=case['scene_group'],split=case['split'],
            reference=case['reference'],status=state,video=media,natural_label='unverified'))
    return dict(schema_version=1,status='awaiting_observation',cases=rows,
        generated_videos=sum(r['video'] is not None for r in rows),
        import_receipts=sum(r['status']=='import_recorded' for r in rows),
        observed_natural_positives=0,ready_for_propose=False,production_eligible=False)
