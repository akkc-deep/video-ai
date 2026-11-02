"""Formal production waits for work, while transports retain request bounds."""
from types import SimpleNamespace

import pytest

from unit.test_production_inputs import production_config
from unit.test_video import media_context
from integration.test_jimeng_candidates import candidate_setup


def invoke_production(monkeypatch, config, operation):
    from video_ai import production
    monkeypatch.setattr(production, '_make_legacy_video', lambda *a, **k: operation())
    return production.make_video(config, text='Production test.')


def test_new_frozen_policy_and_old_identity_are_readable(production_config, runtime_run):
    import json
    from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
    run, _, _ = runtime_run
    frozen = freeze_inputs(production_config, run, text='Production test.')
    assert frozen.options['execution_policy'].get('time_limits') == 'unlimited_v1'
    assert frozen.options['execution_policy']['media_command_seconds'] is None
    path = run/'production/options.json'
    legacy = frozen.options
    legacy['execution_policy'].pop('time_limits')
    legacy['execution_policy']['media_command_seconds'] = 300
    path.write_text(json.dumps(legacy), encoding='utf-8')
    before = path.read_bytes()
    loaded = load_frozen_inputs(run)
    assert loaded.options == legacy and path.read_bytes() == before


def test_formal_process_wait_has_no_timeout(production_config, runtime_run, monkeypatch):
    from video_ai.runtime import processes
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.logging import RunLogger
    run, _, paths = runtime_run
    waits = []
    class Process:
        returncode = 0
        def wait(self, *, timeout):
            waits.append(timeout)
            return 0
    monkeypatch.setattr(processes.subprocess, 'Popen', lambda *a, **k: Process())
    def operation():
        return processes.run_logged((str(production_config.tools['ffmpeg']), '-version'),
            cwd=run, env=build_child_env(paths), timeout=.001, logger=RunLogger(run, production=True),
            stage='composition')
    result = invoke_production(monkeypatch, production_config, operation)
    assert not result.timed_out and waits == [None]


def test_formal_media_validation_survives_elapsed_phase(production_config, monkeypatch):
    from video_ai.media.images import _deadline, _remaining
    def operation():
        deadline = _deadline(1, 0)
        return _remaining(deadline, 100000)
    result = invoke_production(monkeypatch, production_config, operation)
    assert result is None
    # Scope must not leak into subsequent non-production calls.
    with pytest.raises(TimeoutError):
        _remaining(_deadline(1, 0), 100000)


@pytest.mark.parametrize('module_name', ['scene_comfy_transactions', 'scene_upscale_transactions'])
@pytest.mark.parametrize('exposed_timeout',[True,False])
def test_formal_tracking_outlives_phase_and_keeps_http_timeout(
        production_config, runtime_run, monkeypatch, module_name, exposed_timeout):
    import importlib
    fixture_module = importlib.import_module('unit.test_'+module_name)
    module = importlib.import_module('video_ai.runtime.'+module_name)
    store, request, graph, template = fixture_module.transaction.__wrapped__(runtime_run)
    client = fixture_module.Client(store, request, graph)
    if exposed_timeout:client.request_timeout = .25
    clock = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    for method in ('object_info', 'submit', 'queue', 'history'):
        original = getattr(client, method)
        def bounded(*a, _original=original, **kwargs):
            assert 0 < kwargs['timeout'] <= .25
            clock[0] += 100000
            return _original(*a, **kwargs)
        monkeypatch.setattr(client, method, bounded)
    recover = getattr(module, 'recover_or_submit_scene_clip', None) or module.recover_or_submit_scene_frame
    def operation():
        return recover(store, request, graph, client=client, template=template,
            ensure_service=lambda: clock.__setitem__(0, 100000), logger=None, timeout=1,
            **({} if exposed_timeout else {'request_timeout_seconds':.25}))
    result = invoke_production(monkeypatch, production_config, operation)
    assert isinstance(result, dict), result
    assert result['prompt_id'] == client.pid and client.posts == 1


@pytest.mark.parametrize('exited', [False, True])
def test_formal_startup_waits_for_health_but_fails_if_process_exits(
        production_config, runtime_run, run_store, monkeypatch, exited):
    from unit.test_services import manager, spec, Process
    from video_ai.runtime import services
    mgr, _ = manager(run_store, runtime_run, lambda *a: pytest.fail('unexpected HTTP'))
    process = Process()
    clock = [0]
    checks = []
    def health(name, url, timeout):
        assert 0 < timeout <= 2
        checks.append(timeout)
        if len(checks) < 3:
            raise services.ServiceStartError('still starting')
        return {'queue': {'queue_running': [], 'queue_pending': []}}
    def launch(*a, **k):
        if exited:
            process.returncode = 1
        return process
    monkeypatch.setattr(mgr, '_health', health)
    monkeypatch.setattr(services, 'port_listening', lambda *a: False)
    monkeypatch.setattr(services.subprocess, 'Popen', launch)
    monkeypatch.setattr(services.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(services.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0]+100000))
    def operation():
        if exited:
            with pytest.raises(services.ServiceStartError, match='exited before health'):
                mgr.ensure(spec(runtime_run, timeout=1))
            assert len(checks) == 1
            return 'exited'
        handle = mgr.ensure(spec(runtime_run, timeout=1))
        assert handle.owned and len(checks) == 3
        mgr.stop(handle)
        return 'healthy'
    assert invoke_production(monkeypatch, production_config, operation) == ('exited' if exited else 'healthy')


def test_formal_native_extraction_validates_all_frames_without_time_limit(
        production_config, media_context, monkeypatch):
    from unit.test_video import make_video
    from video_ai.media.scene_native_batch import extract_native_scene_batch
    source = make_video(media_context, frames=3)
    run, kwargs = media_context
    result = invoke_production(monkeypatch, production_config, lambda:
        extract_native_scene_batch(source, run/'native', expected_frames=3,
            width=128, height=72, **kwargs))
    assert isinstance(result, tuple), result
    images, evidence = result
    assert len(images) == 3 and evidence


def test_formal_continuity_reads_outlive_phase_but_keep_resource_ceiling(
        production_config, runtime_run, monkeypatch):
    from video_ai.runtime import _scene_continuity_io as io
    path = runtime_run[0]/'input.json'
    path.write_text('{"value": 1}', encoding='utf-8')
    clock = [0]
    monkeypatch.setattr(io, 'monotonic', lambda: clock[0])
    def operation():
        reader = io.Reader(1)
        clock[0] = 100000
        value = reader.read(path)
        with pytest.raises(ValueError, match='resource_limit'):
            reader.charge('large.json', 16777217)
        return value
    assert invoke_production(monkeypatch, production_config, operation) == {'value': 1}


def test_formal_direct_decode_has_no_subprocess_timeout(production_config, monkeypatch):
    from video_ai.media import scene_upscale
    calls = []
    def execute(args, **kwargs):
        calls.append(kwargs['timeout'])
        return SimpleNamespace(returncode=0, stdout=b'pixels')
    monkeypatch.setattr(scene_upscale.subprocess, 'run', execute)
    result = invoke_production(monkeypatch, production_config,
        lambda: scene_upscale._decode('source.mp4', production_config))
    assert result == b'pixels' and calls == [None]


def test_legacy_comfy_tracking_survives_elapsed_phase_with_bounded_requests(
        production_config, runtime_run, run_store, monkeypatch):
    from uuid import uuid4
    from integration.test_comfy_tracking import setup_client, submit, post_count
    from http_helpers import Response
    from video_ai.adapters import comfyui
    pid = str(uuid4()); clock = [0]; polls = []
    def route(request, timeout):
        assert 0 < timeout <= .1
        if request.method == 'POST':
            return Response({'prompt_id': pid, 'number': 1, 'node_errors': {}})
        if '/history/' in request.full_url:
            polls.append(request.full_url); clock[0] += 100000
            if len(polls) == 1:
                return Response({})
            return Response({pid: dict(status=dict(completed=True, status_str='success', messages=[]),
                outputs={'108': {'images': [dict(filename='clip.mp4', subfolder='run', type='output')]}})})
        return Response({'queue_running': [], 'queue_pending': []})
    client, transport, graph = setup_client(run_store, runtime_run, route)
    monkeypatch.setattr(comfyui, 'time', SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda _: None))
    def operation():
        submission = submit(client, graph)
        return client.wait_for(submission, deadline_seconds=1)
    result = invoke_production(monkeypatch, production_config, operation)
    assert hasattr(result, 'prompt_id'), result
    assert result.prompt_id == pid and len(polls) == 2 and post_count(transport) == 1


@pytest.mark.parametrize('scene', [False, True])
def test_formal_composition_recovery_reads_original_unlimited_completion(
        production_config, runtime_run, monkeypatch, scene):
    from video_ai.runtime import processes, production_composition, _scene_composition_commands
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.logging import RunLogger
    run, _, paths = runtime_run
    logger = RunLogger(run, production=True)
    args = (str(production_config.tools['ffmpeg']), '-version')
    process = SimpleNamespace(returncode=0, wait=lambda **k: 0)
    monkeypatch.setattr(processes.subprocess, 'Popen', lambda *a, **k: process)
    intent = dict(args=list(args), cwd=str(run), operation='encode', unit_id='encode')
    def operation():
        uid = _scene_composition_commands._unit('encode', 'token') if scene else 'encode'
        result = processes.run_logged(args, cwd=run, env=build_child_env(paths), timeout=300,
            logger=logger, stage='scene_composition' if scene else 'composition', unit_id=uid)
        if scene:
            context = {'composition_store': SimpleNamespace(run_dir=run)}
            saved = _scene_composition_commands._completion(context, intent, 'token')
        else:
            saved = production_composition._command_result(intent, logger)
        assert saved['started_at'] == result.started_at
        return saved
    result = invoke_production(monkeypatch, production_config, operation)
    assert isinstance(result, dict), result
    assert result['returncode'] == 0


def test_formal_jimeng_task_outlives_execution_timeout(candidate_setup, production_config, monkeypatch):
    from integration.test_jimeng_candidates import generate
    from video_ai.runtime import jimeng_candidates
    clock = iter(range(0, 10000000, 100000))
    monkeypatch.setattr(jimeng_candidates, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    candidate_setup[2]['statuses'] = ['in_queue', 'generating', 'done']
    result = invoke_production(monkeypatch, production_config, lambda: generate(candidate_setup))
    assert isinstance(result, dict), result
    assert len(result['candidates']) == 2 and candidate_setup[2]['submits'] == 1


def test_formal_reference_task_outlives_execution_timeout(production_config, runtime_run, tmp_path, monkeypatch):
    from reference_helpers import reference_setup, generate_reference
    from video_ai.runtime import jimeng_reference_candidates
    setup = reference_setup(runtime_run, tmp_path, monkeypatch)
    clock = iter(range(0, 10000000, 100000))
    monkeypatch.setattr(jimeng_reference_candidates, 'time',
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None))
    result = invoke_production(monkeypatch, production_config, lambda: generate_reference(setup))
    assert isinstance(result, dict), result
    assert result['candidates'] and len(setup['state']['submits']) == 2


def test_bounded_tracking_clock_boundary_keeps_durable_ambiguous_state(runtime_run,run_store,monkeypatch):
    from uuid import uuid4
    from integration.test_comfy_tracking import setup_client,submit,post_count
    from http_helpers import Response
    from video_ai.adapters import comfyui
    from video_ai.adapters.common import AdapterError,FailureKind
    client,transport,graph=setup_client(run_store,runtime_run,
        lambda *a:Response({'prompt_id':str(uuid4()),'number':1,'node_errors':{}}))
    submission=submit(client,graph)
    ticks=iter((0,.5,2))
    monkeypatch.setattr(comfyui,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
    with pytest.raises(AdapterError) as failure:
        client.wait_for(submission,deadline_seconds=1)
    assert failure.value.kind==FailureKind.ambiguous
    saved=run_store.snapshot()['units']['shot']['shot_0001']['submission']
    assert saved['state']=='ambiguous' and post_count(transport)==1


@pytest.mark.parametrize('failure', [RuntimeError('failed'), KeyboardInterrupt('cancelled')])
def test_formal_execution_scope_resets_after_failure(production_config,monkeypatch,failure):
    from video_ai.media.images import _deadline,_remaining
    def operation():
        assert _deadline(1,0) is None
        raise failure
    result=invoke_production(monkeypatch,production_config,operation)
    assert result.status in ('failed','interrupted')
    with pytest.raises(TimeoutError):_remaining(_deadline(1,0),2)


@pytest.mark.parametrize('review',[False,True])
def test_direct_scene_operation_gets_unlimited_scope_and_releases_it(monkeypatch,review):
    from video_ai.runtime import production_scene_clips,production_scene_continuity
    from video_ai.media.images import _deadline
    monkeypatch.setattr(production_scene_clips,'_entry',lambda *a,**k:_deadline(1,0))
    frozen=SimpleNamespace(options={},config=SimpleNamespace(raw={}))
    if review:
        result=production_scene_continuity.consume_scene_continuity_review(frozen,[],None,'unused.json',paths=None,logger=None)
    else:result=production_scene_clips.produce_scene_clips(frozen,[],None,paths=None,logger=None)
    assert result is None
    assert _deadline(1,0)==1


def test_formal_frame_send_guard_stays_cancelled_after_completion(production_config,runtime_run,monkeypatch):
    from unit.test_scene_upscale_transactions import transaction,Client
    from video_ai.runtime.scene_upscale_transactions import recover_or_submit_scene_frame,SceneSubmitUnknown
    store,request,graph,template=transaction.__wrapped__(runtime_run)
    client=Client(store,request,graph)
    client.request_timeout=.25;client.ownership_check=lambda:None
    def operation():
        return recover_or_submit_scene_frame(store,request,graph,client=client,template=template,
            ensure_service=lambda:None,logger=None,timeout=1)
    result=invoke_production(monkeypatch,production_config,operation)
    assert isinstance(result,dict),result
    with pytest.raises(SceneSubmitUnknown):client.ownership_check()
    assert client.posts==1


def test_formal_capability_and_yaml_processing_has_no_command_timeout(production_config,runtime_run,monkeypatch):
    import json
    import subprocess
    from dataclasses import replace
    from video_ai.runtime.production_inputs import production_preflight
    config=replace(production_config,models=runtime_run[1].models)
    timeouts=[]
    def runner(args,**kwargs):
        timeouts.append(kwargs['timeout'])
        if args[-1]=='-encoders':text=' V....D libx264 H264\n A..... aac AAC\n'
        elif args[-1]=='-filters':text=' .. subtitles V->V render\n'
        elif '-c' in args:text=json.dumps({'custom':{'version':'v2','device':'cpu','is_half':False}})
        else:text='fixture version\n'
        kwargs['stdout'].write(text)
        return subprocess.CompletedProcess(args,0)
    result=invoke_production(monkeypatch,production_config,lambda:production_preflight(config,runtime_run[0],
        runner=runner,port_probe=lambda *a:False))
    assert result.passed and timeouts and all(value is None for value in timeouts)


@pytest.mark.parametrize('scene',[False,True])
def test_historical_real_float_300_completion_can_recover_outside_scope(media_context,scene):
    from video_ai.runtime import processes,production_composition,_scene_composition_commands
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.logging import RunLogger
    run,kwargs=media_context
    logger=RunLogger(run,production=True)
    args=(str(kwargs['config'].tools['ffmpeg']),'-version')
    uid=_scene_composition_commands._unit('encode','historical') if scene else 'encode'
    result=processes.run_logged(args,cwd=run,env=build_child_env(kwargs['paths']),timeout=300,
        logger=logger,stage='scene_composition' if scene else 'composition',unit_id=uid)
    import json
    events=[json.loads(line) for line in logger.path('events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert type(events[-1]['details']['timeout']) is float
    intent=dict(args=list(args),cwd=str(run),operation='encode',unit_id=uid)
    if scene:
        saved=_scene_composition_commands._completion({'composition_store':SimpleNamespace(run_dir=run)},intent,'historical')
    else:saved=production_composition._command_result(intent,logger)
    assert saved['started_at']==result.started_at and saved['returncode']==0
