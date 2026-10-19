"""Scene final evidence and durable publication interruption boundaries."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('operation',['consume','delivery'])
@pytest.mark.parametrize('preparation',['malformed','unknown','unprepared'])
def test_public_preparation_refusal_is_blocked_without_identity_or_writes(runtime_run,operation,preparation):
    from uuid import uuid4
    from video_ai.runtime import production_scene_delivery as delivery
    run,_,_=runtime_run
    target=run if preparation=='unprepared' else run.parent/('invalid-run' if preparation=='malformed' else '20261019-000000-'+uuid4().hex[:12])
    frozen=SimpleNamespace(options=dict(script_path=str(target/'inputs/script.txt'),run_id=target.name),
                           config=SimpleNamespace(production_strategy='paragraph_jimeng_v1'))
    before={str(path):path.read_bytes() for path in run.rglob('*') if path.is_file()}
    if operation=='consume':
        result=delivery.consume_scene_final_observation(frozen,{},None,run/'missing-observation.json',paths=None,logger=None)
    else:result=delivery.produce_scene_delivery(frozen,{},None,paths=None,logger=None)
    assert result.status=='blocked',result.error
    assert result.run_id is None and result.run_dir is None and result.log_dir is None
    assert before=={str(path):path.read_bytes() for path in run.rglob('*') if path.is_file()}
    if target!=run:assert not target.exists()


def test_final_failed_raw_blocks_without_rejection_receipt_and_accepted_resists_later_fail(runtime_run,monkeypatch):
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from unit.test_scene_final_observations import context,authored,NOW
    run,_,_=runtime_run
    expected=context(run); expected['template']['run_id']=run.name
    monkeypatch.setattr(delivery,'datetime',SimpleNamespace(now=lambda tz:NOW))
    frozen=SimpleNamespace(options=dict(run_id=run.name))
    with RunLock(run) as lock:
        store=SceneClipStore(frozen,run,lock=lock)
        store.root=run/'production/scene-composition'
        ctx=dict(store=store,frozen=frozen)
        monkeypatch.setattr(delivery,'_observation_context',lambda context,candidate=None:(store,{},expected))
        failed=authored(expected); failed['checks']['style']='failed'
        failed.update(verdict='failed',issues=[dict(check='style',frames=dict(start=0,end=1),description='Flicker.')])
        import json
        raw=json.dumps(failed).encode(); path=store.write_bytes('final-observations/'+hashlib.sha256(raw).hexdigest()+'.json',raw)
        state=delivery.final_observation_state(ctx)
        assert state['rejected']['_raw_only']
        with pytest.raises(ProductionRefused): delivery.require_scene_final_acceptance_record(ctx)
        assert not (store.root/'final-observation-rejected.json').exists()
        # Acceptance receives a fresh candidate version in the separate store.
        path.unlink()
        passed=authored(expected); raw=json.dumps(passed).encode()
        original=store.write_bytes('final-observations/'+hashlib.sha256(raw).hexdigest()+'.json',raw)
        receipt=delivery._observation_receipt(store,{},passed,original,'accepted_at','2026-10-19T12:00:00+00:00')
        store.write('final-observation-accepted.json',receipt)
        before=(store.root/'final-observation-accepted.json').read_bytes()
        with pytest.raises(ProductionRefused): delivery._check_replacement(delivery.final_observation_state(ctx),failed)
        assert (store.root/'final-observation-accepted.json').read_bytes()==before


@pytest.mark.parametrize('changed_source',['upstream','raw','new_failed','rejection'])
def test_observation_acceptance_rechecks_after_fresh_scan_before_receipt(runtime_run,monkeypatch,changed_source):
    import json
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from unit.test_scene_final_observations import context,authored,NOW
    run,_,_=runtime_run;expected=context(run);expected['template']['run_id']=run.name
    frozen=SimpleNamespace(options=dict(run_id=run.name,model_stamps={}))
    monkeypatch.setattr(delivery,'datetime',SimpleNamespace(now=lambda tz:NOW))
    monkeypatch.setattr(delivery,'now',lambda:NOW.isoformat())
    monkeypatch.setattr(delivery,'_result',lambda *args,**kwargs:None)
    observation=run/'authored-input.json';observation.write_text(json.dumps(authored(expected)),encoding='utf-8')
    upstream=run/'upstream.bin';upstream.write_bytes(b'authentic captured upstream bytes')
    with RunLock(run) as lock:
        store=SceneClipStore(frozen,run,lock=lock);store.root=run/'production/scene-composition'
        store.guard_paths[str(upstream)]=store.artifact(upstream)
        ctx=dict(store=store,frozen=frozen)
        monkeypatch.setattr(delivery,'_observation_context',lambda context,candidate=None:(store,{},expected))
        original_scan=delivery.final_observation_state;scans=0
        def scan(context,*,candidate=None):
            nonlocal scans
            state=original_scan(context,candidate=candidate);scans+=1
            if scans==2:
                if changed_source=='new_failed':
                    failed=authored(expected);failed['checks']['style']='failed'
                    failed.update(verdict='failed',issues=[dict(check='style',frames=dict(start=0,end=1),description='Flicker.')])
                    raw=json.dumps(failed).encode();store.write_bytes('final-observations/'+hashlib.sha256(raw).hexdigest()+'.json',raw)
                elif changed_source=='rejection':store.write('final-observation-rejected.json',{})
                else:
                    target=upstream if changed_source=='upstream' else Path(state['originals'][0]['observation']['path'])
                    raw=target.read_bytes();target.write_bytes(bytes([raw[0]^1])+raw[1:])
            return state
        monkeypatch.setattr(delivery,'final_observation_state',scan)
        with pytest.raises(ProductionRefused):delivery._consume(ctx,observation)
        assert not (store.root/'final-observation-accepted.json').exists()


@pytest.mark.parametrize('changed_source',['raw','new_failed','receipt','rejection'])
def test_final_acceptance_capture_uses_validated_snapshot_not_late_recapture(runtime_run,monkeypatch,changed_source):
    import json
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from unit.test_scene_final_observations import context,authored,NOW
    run,_,_=runtime_run;expected=context(run);expected['template']['run_id']=run.name
    frozen=SimpleNamespace(options=dict(run_id=run.name,model_stamps={}))
    monkeypatch.setattr(delivery,'datetime',SimpleNamespace(now=lambda tz:NOW))
    with RunLock(run) as lock:
        store=SceneClipStore(frozen,run,lock=lock);store.root=run/'production/scene-composition'
        value=authored(expected);raw=json.dumps(value).encode()
        original=store.write_bytes('final-observations/'+hashlib.sha256(raw).hexdigest()+'.json',raw)
        receipt=delivery._observation_receipt(store,{},value,original,'accepted_at',NOW.isoformat())
        receipt_path=store.write('final-observation-accepted.json',receipt)
        ctx=dict(store=store,frozen=frozen)
        monkeypatch.setattr(delivery,'_observation_context',lambda context,candidate=None:(store,{},expected))
        original_scan=delivery.final_observation_state
        def scan(context,*,candidate=None):
            state=original_scan(context,candidate=candidate)
            if changed_source=='raw':original.write_bytes(raw+b' ')
            elif changed_source=='receipt':receipt_path.write_bytes(receipt_path.read_bytes()+b' ')
            elif changed_source=='rejection':store.write('final-observation-rejected.json',{})
            else:
                failed=authored(expected);failed['checks']['style']='failed'
                failed.update(verdict='failed',issues=[dict(check='style',frames=dict(start=0,end=1),description='Flicker.')])
                failed_raw=json.dumps(failed).encode()
                store.write_bytes('final-observations/'+hashlib.sha256(failed_raw).hexdigest()+'.json',failed_raw)
            return state
        monkeypatch.setattr(delivery,'final_observation_state',scan)
        with pytest.raises(ProductionRefused):delivery.require_scene_final_acceptance_record(ctx)


@pytest.mark.parametrize('record_name',['candidate-commit.json','commands/encode-test.intent.json'])
def test_second_scan_cannot_recapture_changed_candidate_or_command_json(runtime_run,monkeypatch,record_name):
    import json
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from unit.test_scene_final_observations import context,authored,NOW
    run,_,_=runtime_run;expected=context(run);expected['template']['run_id']=run.name
    frozen=SimpleNamespace(options=dict(run_id=run.name,model_stamps={}))
    candidate=dict(created_at=expected['created_at'])
    monkeypatch.setattr(delivery,'datetime',SimpleNamespace(now=lambda tz:NOW))
    monkeypatch.setattr(delivery,'now',lambda:NOW.isoformat())
    monkeypatch.setattr(delivery,'_result',lambda *args,**kwargs:None)
    monkeypatch.setattr(delivery,'build_scene_final_observation_template',lambda *args:expected['template'])
    original_context=delivery._observation_context
    monkeypatch.setattr(delivery,'_observation_context',lambda context,candidate=None:original_context(context,candidate=dict(created_at=expected['created_at'])))
    observation=run/'authored-input.json';observation.write_text(json.dumps(authored(expected)),encoding='utf-8')
    with RunLock(run) as lock:
        store=SceneMediaStore(frozen,run,lock=lock)
        stage=store.for_root('production/scene-composition')
        record=stage.path(record_name);record.parent.mkdir(parents=True,exist_ok=True);record.write_text('{"immutable":true}\n',encoding='utf-8')
        ctx=dict(store=store,frozen=frozen,units={},timeline=None,scene_clips=dict(clips=[]),image_acceptance={},upscaled={})
        original_scan=delivery.final_observation_state;scans=0
        def scan(context,*,candidate=None):
            nonlocal scans
            scans+=1
            if scans==2:record.write_bytes(record.read_bytes()+b' ')
            return original_scan(context,candidate=candidate)
        monkeypatch.setattr(delivery,'final_observation_state',scan)
        with pytest.raises(ProductionRefused):delivery._consume(ctx,observation)
        assert not (stage.root/'final-observation-accepted.json').exists()


def test_failed_raw_repair_rechecks_original_hash_before_rejected_receipt(runtime_run,monkeypatch):
    import json
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from unit.test_scene_final_observations import context,authored,NOW
    run,_,_=runtime_run;expected=context(run);expected['template']['run_id']=run.name
    frozen=SimpleNamespace(options=dict(run_id=run.name,model_stamps={}))
    monkeypatch.setattr(delivery,'datetime',SimpleNamespace(now=lambda tz:NOW))
    monkeypatch.setattr(delivery,'now',lambda:NOW.isoformat())
    observation=run/'passed-input.json';observation.write_text(json.dumps(authored(expected)),encoding='utf-8')
    with RunLock(run) as lock:
        store=SceneClipStore(frozen,run,lock=lock);store.root=run/'production/scene-composition'
        failed=authored(expected);failed['checks']['style']='failed'
        failed.update(verdict='failed',issues=[dict(check='style',frames=dict(start=0,end=1),description='Flicker.')])
        raw=json.dumps(failed).encode();original=store.write_bytes('final-observations/'+hashlib.sha256(raw).hexdigest()+'.json',raw)
        ctx=dict(store=store,frozen=frozen)
        monkeypatch.setattr(delivery,'_observation_context',lambda context,candidate=None:(store,{},expected))
        scan=delivery.final_observation_state
        def mutate(context,*,candidate=None):
            state=scan(context,candidate=candidate);original.write_bytes(raw+b' ');return state
        monkeypatch.setattr(delivery,'final_observation_state',mutate)
        with pytest.raises(ProductionRefused):delivery._consume(ctx,observation)
        assert not (store.root/'final-observation-rejected.json').exists()


def _final_reuse_setup(runtime_run,monkeypatch,reuse_status,lock):
    import json
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from unit.test_scene_final_observations import context,authored,NOW
    run,_,_=runtime_run;expected=context(run);expected['template']['run_id']=run.name
    frozen=SimpleNamespace(options=dict(run_id=run.name,model_stamps={}))
    monkeypatch.setattr(delivery,'datetime',SimpleNamespace(now=lambda tz:NOW))
    monkeypatch.setattr(delivery,'now',lambda:NOW.isoformat())
    monkeypatch.setattr(delivery,'_result',lambda context,status,*args,**kwargs:status)
    store=SceneClipStore(frozen,run,lock=lock);store.root=run/'production/scene-composition'
    value=authored(expected)
    if reuse_status!='accepted':
        value['checks']['style']='failed'
        value.update(verdict='failed',issues=[dict(check='style',frames=dict(start=0,end=1),description='Flicker.')])
    raw=json.dumps(value).encode()
    original=store.write_bytes('final-observations/'+hashlib.sha256(raw).hexdigest()+'.json',raw)
    time_key='accepted_at' if reuse_status=='accepted' else 'rejected_at'
    receipt_path=store.path('final-observation-'+('accepted' if reuse_status=='accepted' else 'rejected')+'.json')
    if reuse_status!='raw_failed':
        store.write(receipt_path,delivery._observation_receipt(store,{},value,original,time_key,NOW.isoformat()))
    paths=dict(raw=original,receipt=receipt_path)
    for kind in ('candidate','pcm'):
        path=run/('captured-'+kind+'.bin');path.write_bytes(('captured actual '+kind+' bytes').encode())
        store.guard_paths[str(path)]=store.artifact(path);paths[kind]=path
    observation=run/'duplicate-input.json';observation.write_bytes(raw)
    ctx=dict(store=store,frozen=frozen)
    monkeypatch.setattr(delivery,'_observation_context',lambda context,candidate=None:(store,{},expected))
    return ctx,observation,paths


@pytest.mark.parametrize('reuse_status',['accepted','rejected','raw_failed'])
@pytest.mark.parametrize('changed_source,phase',[('candidate','read'),('pcm','validate'),('raw','read'),('receipt','validate')])
def test_duplicate_observation_reuse_rechecks_after_external_input(runtime_run,monkeypatch,reuse_status,changed_source,phase):
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    run,_,_=runtime_run
    with RunLock(run) as lock:
        ctx,observation,paths=_final_reuse_setup(runtime_run,monkeypatch,reuse_status,lock)
        original_read=Path.read_bytes;original_validate=delivery._validate;pending=False;changed=False
        def change():
            nonlocal changed
            target=paths[changed_source];target.write_bytes(original_read(target)+b' ');changed=True
        def read(path):
            nonlocal pending
            raw=original_read(path)
            if path==observation:
                if phase=='read':change()
                else:pending=True
            return raw
        def validate(value,expected,*,now):
            nonlocal pending
            result=original_validate(value,expected,now=now)
            if pending:pending=False;change()
            return result
        monkeypatch.setattr(Path,'read_bytes',read)
        monkeypatch.setattr(delivery,'_validate',validate)
        with pytest.raises(ProductionRefused):delivery._consume(ctx,observation)
        assert changed


@pytest.mark.parametrize('reuse_status',['accepted','rejected','raw_failed'])
def test_unchanged_duplicate_observation_and_failed_raw_repair_reuse(runtime_run,monkeypatch,reuse_status):
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.production_state import RunLock
    run,_,_=runtime_run
    with RunLock(run) as lock:
        ctx,observation,paths=_final_reuse_setup(runtime_run,monkeypatch,reuse_status,lock)
        status=delivery._consume(ctx,observation)
        assert status==('final_review_ready' if reuse_status=='accepted' else 'final_review_failed')
        assert paths['receipt'].is_file()


def publication_context(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore
    run,config,paths=runtime_run
    movie=config.output_root/(run.name+'.mp4')
    targets=dict(movie=str(movie),subtitle=str(movie.with_suffix('.srt')),receipt=str(movie.with_suffix('.delivery.json')))
    frozen=SimpleNamespace(options=dict(run_id=run.name,output_paths=targets))
    store=SceneClipStore(frozen,run)
    store.root=run/'production/scene-delivery'
    folder=run/'candidate';folder.mkdir()
    for name,raw in [('movie.mp4',b'authored candidate bytes'),('text.srt',b'original subtitle bytes')]:
        (folder/name).write_bytes(raw)
    candidate=dict(candidate=store.artifact(folder/'movie.mp4'),subtitle=store.artifact(folder/'text.srt'),
                   technical_checks=dict(source_text_coverage='passed',audio_samples='passed',frame_mapping='passed',subtitles='passed',final_media='passed'))
    return dict(store=store,frozen=frozen,timeline=SimpleNamespace(total_frames=2),scene_clips={},image_acceptance={}),candidate


@pytest.mark.parametrize('point,crash_role',[(event,role) for role in ('movie','subtitle','receipt')
    for event in ('temp-attempt','temp-created','temp-fsynced','prepared','renamed','published')]
    +[('receipt-ready','receipt'),('completed','receipt')])
def test_delivery_recovers_owned_boundaries_and_receipt_is_last(runtime_run,monkeypatch,point,crash_role):
    from video_ai.runtime import scene_delivery_files as files
    from video_ai.runtime.production_state import RunLock
    context,candidate=publication_context(runtime_run);store=context['store'];run=store.run_dir
    with RunLock(run) as lock:
        store.lock=lock
        def crash(event,role):
            if event==point and role==crash_role: raise KeyboardInterrupt()
        monkeypatch.setattr(files,'boundary',crash)
        with files.SceneOutputLock(store,candidate['candidate'],context['frozen'].options['output_paths']['movie']) as output_lock:
            with pytest.raises(KeyboardInterrupt): files.publish(context,candidate,{},output_lock,lambda:store.assert_owned())
        tx_before=store.read('transaction.json')
        unknown=Path(tx_before['operations'][crash_role]['temp_path']) if point=='temp-created' else None
        if point=='temp-created':assert unknown.exists() and tx_before['operations'][crash_role]['file_id'] is None
        if crash_role!='receipt':assert not Path(context['frozen'].options['output_paths']['receipt']).exists()
        monkeypatch.setattr(files,'boundary',lambda *args:None)
        with files.SceneOutputLock(store,candidate['candidate'],context['frozen'].options['output_paths']['movie']) as output_lock:
            receipt=files.publish(context,candidate,{},output_lock,lambda:store.assert_owned())
        if unknown is not None:assert unknown.exists() and unknown.stat().st_size==0
        assert receipt['actual_final_video_consistency']=='passed'
        tx=store.read('transaction.json')
        assert tx['status']=='completed'
        assert all(op['status']=='published' for op in tx['operations'].values())
        snapshot={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        assert files.validate_completed(context,candidate,{})==receipt
        assert snapshot=={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}


def test_same_byte_unowned_target_is_rejected(runtime_run):
    from video_ai.runtime import scene_delivery_files as files
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    context,candidate=publication_context(runtime_run);store=context['store'];run=store.run_dir
    target=Path(context['frozen'].options['output_paths']['movie']);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(Path(candidate['candidate']['path']).read_bytes())
    with RunLock(run) as lock:
        store.lock=lock
        with files.SceneOutputLock(store,candidate['candidate'],target) as output_lock:
            with pytest.raises(ProductionRefused):files.publish(context,candidate,{},output_lock,lambda:store.assert_owned())
    assert target.read_bytes()==Path(candidate['candidate']['path']).read_bytes()


@pytest.mark.parametrize('violation',['source','lock','target'])
def test_delivery_stops_on_source_lock_or_target_change_before_rename(runtime_run,monkeypatch,violation):
    import json
    from video_ai.runtime import scene_delivery_files as files
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    context,candidate=publication_context(runtime_run);store=context['store'];run=store.run_dir
    source=Path(candidate['candidate']['path']);original=source.read_bytes()
    target=Path(context['frozen'].options['output_paths']['movie'])
    with RunLock(run) as lock:
        store.lock=lock
        with files.SceneOutputLock(store,candidate['candidate'],target) as output_lock:
            def mutate(event,role):
                if event=='prepared' and role=='movie':
                    if violation=='source':source.write_bytes(b'altered candidate')
                    elif violation=='lock':output_lock.path.write_text('{}',encoding='utf-8')
                    else:target.write_bytes(original)
            def guard():
                store.assert_owned()
                for value in (candidate['candidate'],candidate['subtitle']):store.validate_artifact(value)
            monkeypatch.setattr(files,'boundary',mutate)
            try:
                with pytest.raises(ProductionRefused):files.publish(context,candidate,{},output_lock,guard)
                assert not Path(context['frozen'].options['output_paths']['receipt']).exists()
                if violation=='target':assert target.read_bytes()==original
                else:assert not target.exists()
            finally:
                source.write_bytes(original)
                output_lock.path.write_text(json.dumps(output_lock.owner),encoding='utf-8')


def test_completed_replay_rejects_same_byte_replacement_with_other_file_id(runtime_run):
    from video_ai.runtime import scene_delivery_files as files
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    context,candidate=publication_context(runtime_run);store=context['store'];run=store.run_dir
    target=Path(context['frozen'].options['output_paths']['movie'])
    with RunLock(run) as lock:
        store.lock=lock
        with files.SceneOutputLock(store,candidate['candidate'],target) as output_lock:
            files.publish(context,candidate,{},output_lock,lambda:store.assert_owned())
        original=target.read_bytes();target.rename(target.with_name(target.name+'.held-original'))
        target.write_bytes(original)
        with pytest.raises(ProductionRefused):files.validate_completed(context,candidate,{})


def test_output_lock_refuses_noncaller_thread_before_any_write(runtime_run):
    from concurrent.futures import ThreadPoolExecutor
    from video_ai.runtime import scene_delivery_files as files
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    context,candidate=publication_context(runtime_run);base=context['store'];run=base.run_dir
    with RunLock(run) as lock:
        store=SceneMediaStore(context['frozen'],run,lock=lock).for_root('production/scene-delivery')
        output_lock=files.SceneOutputLock(store,candidate['candidate'],context['frozen'].options['output_paths']['movie'])
        def acquire():
            with output_lock:raise AssertionError('foreign thread acquired scene output lock')
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(ProductionRefused):pool.submit(acquire).result(timeout=5)
        assert not output_lock.path.exists() and not store.root.exists()


def test_authentic_candidate_explicit_review_delivery_and_twice_readonly_prefix(runtime_run,tmp_path,monkeypatch):
    """Authored synthetic review proves protocol only, not real viewing quality."""
    import json
    from scene_media_helpers import prepared_upscaled
    from unit.test_scene_final_observations import authored
    from video_ai.runtime.production_scene_composition import produce_scene_composition
    from video_ai.runtime.production_scene_delivery import consume_scene_final_observation,produce_scene_delivery
    from video_ai.runtime.scene_completed import validate_scene_completed_prefix
    from video_ai.runtime.scene_media_records import require_scene_delivery,require_scene_final_acceptance
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime import scene_delivery_files
    setup=prepared_upscaled(runtime_run,tmp_path,monkeypatch)
    frozen,units,timeline=setup['frozen'],setup['units'],setup['timeline']
    kwargs=dict(paths=setup['paths'],logger=setup['logger'])
    candidate=produce_scene_composition(frozen,units,timeline,**kwargs)
    assert candidate.status=='awaiting_final_review',candidate.error
    assert produce_scene_delivery(frozen,units,timeline,**kwargs).status=='blocked'
    assert all(not Path(p).exists() for p in frozen.options['output_paths'].values())
    template=json.loads(Path(candidate.final_observation_template).read_text(encoding='utf-8'))
    authored_value=authored(dict(template=template))
    from datetime import datetime,timezone
    authored_value['viewed_at']=datetime.now(timezone.utc).isoformat()
    observation=setup['run']/'test-authored-final-observation.json';observation.write_text(json.dumps(authored_value),encoding='utf-8')
    accepted=consume_scene_final_observation(frozen,units,timeline,observation,**kwargs)
    assert accepted.status=='final_review_ready',accepted.error
    accepted_receipt=require_scene_final_acceptance(frozen,units,timeline)
    # A later failed submission is rejected before any immutable raw is retained.
    failed=deepcopy(authored_value);failed['checks']['style']='failed'
    failed.update(verdict='failed',issues=[dict(check='style',frames=dict(start=0,end=1),description='Synthetic failure.')])
    observation.write_text(json.dumps(failed),encoding='utf-8')
    assert consume_scene_final_observation(frozen,units,timeline,observation,**kwargs).status=='blocked'
    assert require_scene_final_acceptance(frozen,units,timeline)==accepted_receipt
    # Guard every captured dependency again between already-published media and
    # the last receipt, retaining owned partial outputs for exact recovery.
    candidate_bytes=Path(candidate.candidate).read_bytes()
    receipt_path=setup['run']/'production/scene-composition/final-observation-accepted.json'
    acceptance_bytes=receipt_path.read_bytes()
    upscale_body=next(path for path in (setup['run']/'production/scene-upscale').rglob('*.body') if path.stat().st_size)
    command_events=setup['run']/'logs/production/events.jsonl'
    for target_event,role,changed,original in [
        ('published','movie',Path(candidate.candidate),candidate_bytes),
        ('published','subtitle',receipt_path,acceptance_bytes),
        ('receipt-ready','receipt',command_events,command_events.read_bytes()),
        ('prepared','receipt',upscale_body,upscale_body.read_bytes()),
    ]:
        def mutate(event,current_role):
            if event==target_event and current_role==role:
                changed.write_bytes(bytes([original[0]^1])+original[1:])
        monkeypatch.setattr(scene_delivery_files,'boundary',mutate)
        interrupted=produce_scene_delivery(frozen,units,timeline,**kwargs)
        assert interrupted.status=='blocked',interrupted.error
        assert not Path(frozen.options['output_paths']['receipt']).exists()
        changed.write_bytes(original)
    monkeypatch.setattr(scene_delivery_files,'boundary',lambda *args:None)
    result=produce_scene_delivery(frozen,units,timeline,**kwargs)
    assert result.status=='delivered',result.error
    receipt=require_scene_delivery(frozen,units,timeline)
    assert receipt['schema_version']==2 and receipt['actual_final_video_consistency']=='passed'
    for role,source in [('movie',candidate.candidate),('subtitle',template['subtitle']['path'])]:
        assert Path(frozen.options['output_paths'][role]).read_bytes()==Path(source).read_bytes()
    snapshot={str(p):p.read_bytes() for p in setup['run'].rglob('*') if p.is_file()}
    def forbid(*args,**kwargs):raise AssertionError('completed replay attempted publication')
    monkeypatch.setattr(scene_delivery_files,'publish',forbid)
    for _ in range(2):
        progress=validate_scene_completed_prefix(frozen,units,timeline)
        assert progress['delivery']['status']=='delivered'
        assert produce_scene_delivery(frozen,units,timeline,**kwargs).status=='delivered'
    assert snapshot=={str(p):p.read_bytes() for p in setup['run'].rglob('*') if p.is_file()}
    # Any candidate byte change invalidates the accepted version, without repair.
    original=Path(candidate.candidate).read_bytes()
    Path(candidate.candidate).write_bytes(bytes([original[0]^1])+original[1:])
    with pytest.raises(ProductionRefused):require_scene_delivery(frozen,units,timeline)


def test_authentic_failed_raw_without_receipt_permanently_blocks_candidate(runtime_run,tmp_path,monkeypatch):
    import json
    from datetime import datetime,timezone
    from scene_media_helpers import prepared_upscaled
    from unit.test_scene_final_observations import authored
    from video_ai.runtime.production_scene_composition import produce_scene_composition
    from video_ai.runtime import production_scene_delivery as delivery
    from video_ai.runtime.scene_media_records import load_scene_media_progress
    setup=prepared_upscaled(runtime_run,tmp_path,monkeypatch)
    frozen,units,timeline=setup['frozen'],setup['units'],setup['timeline']
    kwargs=dict(paths=setup['paths'],logger=setup['logger'])
    candidate=produce_scene_composition(frozen,units,timeline,**kwargs)
    assert candidate.status=='awaiting_final_review',candidate.error
    template=json.loads(Path(candidate.final_observation_template).read_text(encoding='utf-8'))
    passed=authored(dict(template=template));passed['viewed_at']=datetime.now(timezone.utc).isoformat()
    failed=deepcopy(passed);failed['checks']['style']='failed'
    failed.update(verdict='failed',issues=[dict(check='style',frames=dict(start=0,end=1),description='Authored synthetic failed playback.')])
    path=setup['run']/'test-authored-failed-final.json';path.write_text(json.dumps(failed),encoding='utf-8')
    def crash(point):
        if point=='observation-original':raise KeyboardInterrupt()
    monkeypatch.setattr(delivery,'boundary',crash)
    result=delivery.consume_scene_final_observation(frozen,units,timeline,path,**kwargs)
    assert result.status=='interrupted',result.error
    rejected=setup['run']/'production/scene-composition/final-observation-rejected.json'
    assert not rejected.exists()
    snapshot={str(p):p.read_bytes() for p in setup['run'].rglob('*') if p.is_file()}
    assert load_scene_media_progress(frozen,units,timeline)['final_review']['status']=='final_review_failed'
    assert snapshot=={str(p):p.read_bytes() for p in setup['run'].rglob('*') if p.is_file()}
    assert delivery.produce_scene_delivery(frozen,units,timeline,**kwargs).status=='blocked'
    path.write_text(json.dumps(passed),encoding='utf-8')
    monkeypatch.setattr(delivery,'boundary',lambda *args:None)
    assert delivery.consume_scene_final_observation(frozen,units,timeline,path,**kwargs).status=='blocked'
    assert rejected.exists()
    path.write_text(json.dumps(failed),encoding='utf-8')
    result=delivery.consume_scene_final_observation(frozen,units,timeline,path,**kwargs)
    assert result.status=='final_review_failed' and result.candidate==candidate.candidate,result.error
    assert all(not Path(p).exists() for p in frozen.options['output_paths'].values())
