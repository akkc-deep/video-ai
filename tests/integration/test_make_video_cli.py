from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from unit.test_production_inputs import production_config


@pytest.mark.parametrize('inputs', [[], ['--text', '湖水。', '--script', 'script.txt'], ['--text', '湖水。', '--run-dir', 'run']])
def test_make_video_requires_one_input(inputs, capsys):
    from video_ai.cli import main
    assert main(['make-video', *inputs, '--json']) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'blocked'
    assert result['movie'] is None


@pytest.mark.parametrize('text', ['', ' \r\n\t', '。！？'])
def test_cli_unspeakable_text_returns_strict_json(text, capsys):
    from video_ai.cli import main
    assert main(['make-video', '--text', text, '--json']) == 2
    data = json.loads(capsys.readouterr().out)
    assert data['run_dir'] is None
    assert data['human_review'] == 'unverified'
    assert all(v == 'unverified' for v in data['technical_checks'].values())


def test_default_config_initializes_and_does_not_claim_delivery(monkeypatch, capsys):
    from video_ai.cli import main
    import video_ai.production as production
    from video_ai.runtime.preflight import PreflightReport, PreflightCheck
    from video_ai.runtime.production_inputs import DEFAULT_CONFIG
    real = production.load_config
    observed = []
    def load(path, **kwargs):
        observed.append(path)
        return real(path, **kwargs)
    monkeypatch.setattr(production, 'load_config', load)
    # Model loading is deliberately outside MAKE-01. Substitute only local resource probes.
    monkeypatch.setattr(production, 'production_preflight', lambda config, run: PreflightReport((PreflightCheck('local', True, 'fixture'),)))
    def stop_at_units(*args):
        from video_ai.runtime.production_state import ProductionRefused
        raise ProductionRefused('MAKE-01 preflight-only fixture')
    monkeypatch.setattr(production, '_run_generation', stop_at_units)
    assert main(['make-video', '--text', '湖水。\r\n白鸟。', '--json']) == 2
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert observed[0] == DEFAULT_CONFIG
    assert data['status'] == 'blocked'
    assert data['active_stage'] == 'units'
    assert data['movie'] is data['subtitle'] is data['receipt_path'] is None
    run = Path(data['run_dir'])
    assert (run/'production/script.txt').read_bytes() == '湖水。\r\n白鸟。'.encode()
    state = json.loads((run/'production/production-state.json').read_text(encoding='utf-8'))
    assert state['stages']['preflight']['status'] == 'completed'
    assert state['stages']['units']['status'] == 'pending'
    assert not (run/'.make-video.lock').exists()
    assert list((run/'logs/production/invocations').glob('*.json'))
    assert main(['make-video', '--run-dir', str(run), '--json']) == 2
    again = json.loads(capsys.readouterr().out)
    assert again['run_id'] == data['run_id']
    assert again['active_stage'] == 'units'


def test_external_service_rejection_makes_zero_posts_and_leaves_server_alive(tmp_path):
    from video_ai.production import make_video
    from video_ai.runtime.production_inputs import DEFAULT_CONFIG
    posts = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            posts.append(self.path); self.send_response(500); self.end_headers()
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    try:
        data = json.loads(DEFAULT_CONFIG.read_text(encoding='utf-8'))
        data['services']['ollama'] = f'http://127.0.0.1:{server.server_port}'
        path = tmp_path/'config.json'; path.write_text(json.dumps(data), encoding='utf-8')
        result = make_video(path, text='白鸟。')
        assert result.status == 'blocked'
        assert str(server.server_port) in result.error['message']
        assert posts == []
        with socket.create_connection(server.server_address, timeout=1): pass
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)


@pytest.mark.parametrize('failure,expected', [(OSError('disk error'), ('failed', 1)), (KeyboardInterrupt(), ('interrupted', 130))])
def test_invocation_failure_and_interrupt_preserve_state(monkeypatch, failure, expected):
    import video_ai.production as production
    def fail(*args): raise failure
    monkeypatch.setattr(production, 'production_preflight', fail)
    result = production.make_video(text='白鸟。')
    assert (result.status, result.exit_code) == expected
    assert result.active_stage == 'preflight'
    assert result.error['evidence_paths']
    for path in result.error['evidence_paths']: assert Path(path).is_file()
    state = json.loads((result.run_dir/'production/production-state.json').read_text(encoding='utf-8'))
    assert state['invocation_status'] == expected[0]
    assert state['stages']['preflight']['status'] == 'running'


def test_public_result_is_deeply_immutable_and_json_safe():
    from video_ai.production import ProductionResult
    result = ProductionResult(status='blocked', error=dict(kind='Refused', message='输入拒绝', evidence_paths=[]))
    with pytest.raises(FrozenInstanceError): result.status = 'delivered'
    with pytest.raises(TypeError): result.technical_checks['audio_samples'] = 'passed'
    with pytest.raises(TypeError): result.error['message'] = 'changed'
    data = json.loads(json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False))
    assert set(data) == {'schema_version', 'run_id', 'run_dir', 'status', 'active_stage', 'movie', 'subtitle',
                        'receipt_path', 'log_dir', 'technical_checks', 'human_review', 'error'}
    with pytest.raises(ValueError): ProductionResult(schema_version=True)
    with pytest.raises(ValueError): ProductionResult(status='delivered')


@pytest.mark.parametrize('error', [dict(kind={}, message=[], evidence_paths=[]),
                                  dict(kind='Error', message=True, evidence_paths=[]),
                                  dict(kind='Error', message='bad', evidence_paths={})])
def test_result_without_run_rejects_invalid_error_types(error):
    from video_ai.production import ProductionResult
    with pytest.raises(ValueError): ProductionResult(error=error)


def test_resume_live_lock_refused_without_mutation(runtime_run):
    from video_ai.production import make_video
    from video_ai.runtime.production_state import RunLock
    run, _, _ = runtime_run
    with RunLock(run):
        before = (run/'.make-video.lock').read_bytes()
        result = make_video(run_dir=run)
        assert result.status == 'blocked', result.error
        assert result.exit_code == 2
        assert (run/'.make-video.lock').read_bytes() == before


@pytest.mark.parametrize('secondary', ['invocation', 'lock'])
def test_finalization_does_not_hide_interruption(monkeypatch, secondary):
    import video_ai.production as production
    from video_ai.runtime.production_state import RunLock
    def interrupt(config, run):
        if secondary == 'lock': (run/'.make-video.lock').write_text('foreign replacement', encoding='utf-8')
        raise KeyboardInterrupt('original cancellation')
    monkeypatch.setattr(production, 'production_preflight', interrupt)
    real = production.write_exclusive
    def fail_invocation(path, data):
        if 'invocations' in path.parts: raise OSError('secondary disk error')
        return real(path, data)
    if secondary == 'invocation': monkeypatch.setattr(production, 'write_exclusive', fail_invocation)
    result = production.make_video(text='白鸟。')
    assert result.status == 'interrupted'
    assert result.exit_code == 130
    assert 'original cancellation' in result.error['message']
    assert result.error['evidence_paths']


def test_resume_repairs_manifest_lagging_completed_preflight(monkeypatch):
    import video_ai.production as production
    from video_ai.runtime.manifest import ManifestStore
    from video_ai.runtime.preflight import PreflightReport, PreflightCheck
    monkeypatch.setattr(production, 'production_preflight', lambda config, run: PreflightReport((PreflightCheck('local', True, 'ok'),)))
    def stop_at_units(*args):
        from video_ai.runtime.production_state import ProductionRefused
        raise ProductionRefused('MAKE-01 preflight-only fixture')
    monkeypatch.setattr(production, '_run_generation', stop_at_units)
    real = ManifestStore.record_stage
    def fail(self, stage, status, **kwargs):
        if stage == 'preflight' and status == 'completed': raise OSError('interrupted manifest commit')
        return real(self, stage, status, **kwargs)
    monkeypatch.setattr(ManifestStore, 'record_stage', fail)
    first = production.make_video(text='白鸟。')
    assert first.status == 'failed'
    assert first.active_stage == 'units'
    monkeypatch.setattr(ManifestStore, 'record_stage', real)
    resumed = production.make_video(run_dir=first.run_dir)
    assert resumed.status == 'blocked'
    assert ManifestStore.open(first.run_dir, verify_integrity=False).snapshot()['stages']['preflight']['status'] == 'completed'


def test_cli_automatic_speech_timeline_and_same_run_no_posts(runtime_run, monkeypatch, capsys):
    import video_ai.runtime.production_storyboard as storyboard
    from video_ai.runtime.production_state import ProductionRefused
    def stop_at_storyboard(*args,**kwargs):raise ProductionRefused('MAKE-02 speech prefix fixture')
    monkeypatch.setattr(storyboard,'produce_storyboard',stop_at_storyboard)
    from production_helpers import model_server,config_for_server,install_owned_services
    from video_ai.cli import main
    from video_ai.config import load_config
    from video_ai.runtime.production_inputs import DEFAULT_CONFIG
    from video_ai.runtime.preflight import PreflightReport,PreflightCheck
    import video_ai.production as production
    run,_,_=runtime_run
    with model_server() as (url,posts):
        config=config_for_server(load_config(DEFAULT_CONFIG),url,run)
        install_owned_services(monkeypatch)
        monkeypatch.setattr(production,'production_preflight',lambda *args:PreflightReport((PreflightCheck('fixture',True,'local probes only'),)))
        assert main(['make-video','--text','晨光照亮平静的湖面。一只白鸟从湖边起飞。','--config',str(config.config_file),'--json'])==2
        data=json.loads(capsys.readouterr().out)
        assert data['status']=='blocked' and data['active_stage']=='storyboard'
        assert data['movie'] is data['subtitle'] is data['receipt_path'] is None
        assert data['human_review']=='unverified'
        assert data['technical_checks']['source_text_coverage']=='passed'
        assert data['technical_checks']['audio_samples']=='passed'
        assert len(posts)==3
        assert [body['text'] for path,body in posts if path=='/tts']==['晨光照亮平静的湖面。','一只白鸟从湖边起飞。']
        assert main(['make-video','--run-dir',data['run_dir'],'--json'])==2
        again=json.loads(capsys.readouterr().out)
        assert again['run_id']==data['run_id'] and again['active_stage']=='storyboard'
        assert len(posts)==3


@pytest.mark.parametrize('input_mode,final_boundary', [('text',None),('script',None)]+[('text',p) for p in ('receipt_record','final_checkpoint','delivery_report','delivery_state')])
def test_cli_text_to_candidate_then_same_run_zero_model_or_media(production_config, runtime_run, monkeypatch, capsys, input_mode, final_boundary):
    """A missing coordinator stage or repeated completed media breaks this test."""
    import video_ai.production as production
    import video_ai.runtime.production_upscale as upscale
    from video_ai.cli import main
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.preflight import PreflightReport, PreflightCheck
    from production_helpers import model_server, config_for_server
    from production_visual_helpers import comfy_server, configure_comfy, install_visual_owned
    from unit.test_production_storyboard import visual_handler
    run, _, paths = runtime_run
    with model_server(visual_handler) as (url, planner_posts), comfy_server(
        production_config, run, paths, RunLogger(run, production=True)
    ) as (comfy_url, posts, gets, history):
        config = configure_comfy(config_for_server(production_config, url, run), comfy_url, run)
        # Keep the HTTP contract complete while avoiding 96 default-pause fixture frames.
        raw = json.loads(config.config_file.read_text(encoding='utf-8'))
        raw['media']['timeline'] = dict(sentence_pause_seconds=0, paragraph_pause_seconds=0, opening_seconds=0, closing_seconds=0)
        config.config_file.write_text(json.dumps(raw), encoding='utf-8')
        manager = install_visual_owned(monkeypatch)
        monkeypatch.setattr(upscale, 'ServiceManager', manager)
        monkeypatch.setattr(upscale, 'port_listening', lambda *args: False)
        monkeypatch.setattr(production, 'create_run', lambda *args: run)
        monkeypatch.setattr(production, 'production_preflight', lambda *args: PreflightReport((PreflightCheck('fixture', True, 'local'),)))
        text = ' 湖水。\r\n白鸟。 '
        monkeypatch.setattr(production, 'DEFAULT_CONFIG', config.config_file)
        script = run/'input-script.txt'
        script.write_bytes(b'\xef\xbb\xbf' + text.encode())
        args = ['--text', text] if input_mode == 'text' else ['--script', str(script)]
        import video_ai.runtime.production_delivery as delivery
        fired=[]
        def crash(point,role):
            if final_boundary==point and not fired:
                fired.append(point);raise KeyboardInterrupt('final delivery boundary')
        monkeypatch.setattr(delivery,'boundary',crash)
        exit_code=main(['make-video', *args, '--json'])
        if final_boundary:
            assert exit_code==130
            partial=json.loads(capsys.readouterr().out)
            assert partial['status']=='interrupted' and Path(run/'production/delivery.json').is_file()
            counts=(len(posts),len(gets),len(planner_posts))
            import video_ai.runtime.production_composition as composition_module
            monkeypatch.setattr(composition_module,'produce_composition',lambda *args,**kwargs:pytest.fail('completed generation called'))
            monkeypatch.setattr(delivery,'copy_media',lambda *args:pytest.fail('completed delivery copy repeated'))
            assert main(['make-video','--run-dir',str(run),'--json'])==0
            assert counts==(len(posts),len(gets),len(planner_posts))
        else:assert exit_code==0
        result = json.loads(capsys.readouterr().out)
        assert result['status'] == 'delivered' and result['active_stage'] is None, result
        assert set(result['technical_checks'].values()) == {'passed'}
        assert result['human_review'] == 'unverified'
        assert all(Path(result[key]).is_file() for key in ('movie', 'subtitle', 'receipt_path'))
        receipt = json.loads(Path(result['receipt_path']).read_text(encoding='utf-8'))
        assert receipt['human_review'] == receipt['actual_video_semantics'] == receipt['actual_action_sync'] == 'unverified'
        state = json.loads((run/'production/production-state.json').read_text(encoding='utf-8'))
        assert state['stages']['upscale']['status'] == state['stages']['composition']['status'] == 'completed'
        composition = json.loads((run/'production/composition.json').read_text(encoding='utf-8'))['payload']
        assert Path(composition['candidate']['path']).is_file()
        assert Path(composition['subtitle']['path']).is_file()
        assert Path(result['movie']).read_bytes() == Path(composition['candidate']['path']).read_bytes()
        assert Path(result['subtitle']).read_bytes() == Path(composition['subtitle']['path']).read_bytes()
        assert all(row['status'] == 'completed' for row in state['stages'].values())
        assert state['invocation_status'] == 'delivered'
        assert composition['samples'] == composition['frames'] * 3000
        upscale_posts = [body for body in posts if body['prompt'].get('3', {}).get('class_type') == 'ImageUpscaleWithModel']
        assert len(upscale_posts) == composition['frames']
        assert len({body['client_id'] for body in upscale_posts}) == composition['frames']
        assert len(planner_posts) == 4  # units, two TTS, storyboard
        assert len(posts)==8  # two SDXL, two Wan, four real HTTP upscale requests
        events=[json.loads(line) for line in (run/'logs/production/events.jsonl').read_text(encoding='utf-8').splitlines()]
        commands=[e for e in events if e.get('event')=='command_started' and e.get('stage')=='composition']
        assert len(commands)==2
        assert len([e for e in commands if '-c:v' in e['details']['args']])==1
        assert len([e for e in commands if '-count_frames' in e['details']['args']])==1
        assert (run/'production/script.txt').read_bytes()==(b'\xef\xbb\xbf' if input_mode=='script' else b'')+text.encode()
        srt = Path(composition['subtitle']['path']).read_text(encoding='utf-8')
        assert '湖水。' in srt and '白鸟。' in srt
        before = (len(posts), len(gets), len(planner_posts))
        files = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in run.rglob('*') if path.is_file() and path.suffix in ('.png', '.mp4', '.wav', '.srt', '.ass')}
        process_files = set((run/'logs/production/processes').glob('*'))
        import video_ai.runtime.production_delivery as delivery
        monkeypatch.setattr(delivery,'copy_media',lambda *args:pytest.fail('successful delivery copy repeated'))
        assert main(['make-video', '--run-dir', str(run), '--json']) == 0
        again = json.loads(capsys.readouterr().out)
        assert again['run_id'] == result['run_id'] and again['active_stage'] is None
        assert [again[k] for k in ('movie', 'subtitle', 'receipt_path')] == [result[k] for k in ('movie', 'subtitle', 'receipt_path')]
        assert set(again['technical_checks'].values()) == {'passed'}
        assert (len(posts), len(gets), len(planner_posts)) == before
        assert set((run/'logs/production/processes').glob('*')) == process_files
        assert {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in files} == files
        assert main(['make-video','--run-dir',str(run)])==0
        terminal=capsys.readouterr()
        assert all(result[k] in terminal.out for k in ('movie','subtitle','receipt_path'))
        if input_mode=='text' and final_boundary is None:
            from video_ai.production import make_video
            state_path=run/'production/production-state.json';saved=state_path.read_bytes()
            for stage in ('units','speech','timeline','storyboard','start_images','source_clips'):
                broken=json.loads(saved);broken['units'].pop(stage)
                state_path.write_text(json.dumps(broken),encoding='utf-8')
                refused=make_video(run_dir=run)
                assert refused.status=='blocked',stage
                state_path.write_bytes(saved)
            for stage,field in (('speech','voice_identity'),('units','script_identity'),('units','prompt')):
                baseline=json.loads(saved);row=next(iter(baseline['units'][stage].values()))
                intent_path=Path(row['request']['intent_path']);intent_bytes=intent_path.read_bytes()
                intent_stat=intent_path.stat();counts=(len(posts),len(gets),len(planner_posts))
                intent=json.loads(intent_bytes)
                if field=='voice_identity':intent[field]['sha256']='0'*64
                elif field=='script_identity':intent['context'][field]['sha256']='0'*64
                else:intent[field]+=' changed'
                intent_path.write_text(json.dumps(intent),encoding='utf-8')
                try:
                    refused=make_video(run_dir=run)
                    assert refused.status=='blocked',field
                    assert counts==(len(posts),len(gets),len(planner_posts))
                finally:
                    intent_path.write_bytes(intent_bytes);state_path.write_bytes(saved)
                    import os
                    os.utime(intent_path,ns=(intent_stat.st_atime_ns,intent_stat.st_mtime_ns))
            from video_ai.runtime.production_state import RunLock
            real_exit=RunLock.__exit__;at_release=[]
            def foreign_release(self,*args):
                at_release.append(state_path.read_bytes())
                assert json.loads(at_release[-1])['invocation_status']=='delivered'
                self.path.write_text('foreign replacement',encoding='utf-8')
                return real_exit(self,*args)
            monkeypatch.setattr(RunLock,'__exit__',foreign_release)
            failed=make_video(run_dir=run)
            assert failed.exit_code!=0 and at_release
            assert state_path.read_bytes()==at_release[-1]


@pytest.mark.parametrize('stage',['units','speech','storyboard','start_images','source_clips'])
def test_completed_model_checkpoint_requires_original_request(runtime_run,stage):
    from video_ai.runtime.production_state import validate_checkpoint
    from video_ai.runtime.manifest import now
    run,_,_=runtime_run
    uid='units_batch_0001_initial' if stage=='units' else 'storyboard_batch_0001_initial' if stage=='storyboard' else 'fixture'
    data=dict(schema_version=1,execution_mode='automatic',run_id=run.name,stage=stage,unit_id=uid,
        created_at=now(),status='completed',request=None,outputs={},payload={})
    # Check request admission before payload dispatch; null model identity cannot be consumed.
    with pytest.raises(ValueError,match='request'):validate_checkpoint(data,run,stage,uid)


def test_success_result_serialization_checked_before_generation(monkeypatch):
    import video_ai.production as production
    from video_ai.runtime.preflight import PreflightReport,PreflightCheck
    real=production.ProductionResult
    def result(*args,**kwargs):
        if kwargs.get('status')=='delivered':raise TypeError('cannot serialize success')
        return real(*args,**kwargs)
    monkeypatch.setattr(production,'ProductionResult',result)
    monkeypatch.setattr(production,'production_preflight',lambda *args:PreflightReport((PreflightCheck('fixture',True,'local'),)))
    monkeypatch.setattr(production,'_run_generation',lambda *args:pytest.fail('generation started before serializability'))
    failed=production.make_video(text='湖水。')
    assert failed.exit_code==1 and 'cannot serialize success' in failed.error['message']


def test_success_cleanup_failure_never_mutates_state_after_foreign_lock(monkeypatch):
    import video_ai.production as production
    from video_ai.runtime.production_state import RunLock
    changes=[]
    class Store:
        def __init__(self,run):self.run_dir=run
        def snapshot(self):return dict(invocation_status='delivered',active_stage=None,stages={s:dict(status='completed') for s in production.STAGES})
        def set_invocation(self,*args):changes.append(args)
    monkeypatch.setattr(production.ProductionStateStore,'create',lambda run:Store(run))
    monkeypatch.setattr(production,'create_manifest',lambda *args,**kwargs:None)
    monkeypatch.setattr(production,'_finish_prefix',lambda *args:None)
    monkeypatch.setattr(production,'_run_generation',lambda frozen,state,manifest:dict(run_id=state.run_dir.name))
    original=RunLock.__exit__
    def release(self,*args):
        self.path.write_text('foreign owner',encoding='utf-8');return original(self,*args)
    monkeypatch.setattr(RunLock,'__exit__',release)
    result=production.make_video(text='湖水。')
    assert result.status=='blocked' and result.movie is None
    assert changes==[]
