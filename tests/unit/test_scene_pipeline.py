"""Coordinator records diagnose progress; only original stage evidence authorizes work."""
from pathlib import Path

import pytest


def test_pipeline_error_result_has_only_early_scene_fields():
    from video_ai.runtime.scene_pipeline_records import ScenePipelineResult
    value = ScenePipelineResult(status='blocked',active_stage='preflight',
        error={'kind':'ProductionRefused','message':'configuration required','evidence_paths':[]})
    assert set(value.to_dict())==set('schema_version production_strategy run_id run_dir status active_stage log_dir error'.split())
    assert value.exit_code==2 and value.schema_version==2
    for state,code in [('failed',1),('interrupted',130)]:
        assert ScenePipelineResult(status=state,active_stage='units').exit_code==code


@pytest.mark.parametrize('kwargs',[{'status':'delivered'},{'active_stage':'composition'},
    {'schema_version':True},{'production_strategy':'legacy'},{'run_id':'unknown'}])
def test_pipeline_result_rejects_invented_readiness_or_run_identity(kwargs):
    from video_ai.runtime.scene_pipeline_records import ScenePipelineResult
    with pytest.raises(ValueError): ScenePipelineResult(**kwargs)


def test_empty_scene_progress_is_read_only_and_does_not_invent_common_prefix(runtime_run,tmp_path):
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.scene_pipeline_records import load_scene_pipeline_progress
    from integration.test_scene_revision_flow import tree_identity
    run,config,_ = runtime_run
    frozen = freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    before = tree_identity(run)
    result = load_scene_pipeline_progress(frozen)
    assert set(result)==set('schema_version production_strategy run_id common plan images clips media'.split())
    assert result['common']==dict(status='pending',record=None,source_mode=None,error=None)
    assert result['plan']==dict(status='pending',record=None,error=None)
    assert result['images']['status']=='pending'
    assert result['clips'] is result['media'] is None
    assert tree_identity(run)==before


def test_half_prepared_prefix_is_blocked_and_never_overwritten(runtime_run,tmp_path):
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.scene_pipeline_records import load_scene_pipeline_progress
    from integration.test_scene_revision_flow import tree_identity
    run,config,_ = runtime_run
    frozen = freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    (run/'production/units.json').write_text('{}')
    before = tree_identity(run)
    assert load_scene_pipeline_progress(frozen)['common']['status']=='blocked'
    assert tree_identity(run)==before


def test_invalid_email_secret_is_rejected_before_submission_copy(runtime_run,tmp_path):
    import json
    from unit.test_jimeng_config import configured
    from video_ai.production import make_video
    from video_ai.runtime.production_inputs import freeze_inputs
    run,config,_=runtime_run
    freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    settings=tmp_path/'email-with-secret.json'
    settings.write_text(json.dumps({'password':'do-not-persist-this-secret'}))
    result=make_video(run_dir=run,email_settings=settings)
    assert result.status=='blocked'
    assert not any(b'do-not-persist-this-secret' in p.read_bytes() for p in run.rglob('*') if p.is_file())


def test_automatic_units_failure_reports_the_actual_early_stage(runtime_run,tmp_path,monkeypatch):
    import video_ai.production as production
    import video_ai.runtime.production_storyboard as storyboard
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import ProductionStateStore,RunLock,ProductionRefused
    from video_ai.runtime.manifest import create_manifest
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.production_scene_pipeline import produce_scene_pipeline
    run,config,paths=runtime_run
    frozen=freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    ProductionStateStore.create(run)
    create_manifest(run,frozen.config,inputs=frozen.options['execution_policy']['input_identities'],models={},workflows={},verify_integrity=False)
    monkeypatch.setattr(production,'_finish_prefix',lambda *args:None)
    def fail(*args,**kwargs):raise ProductionRefused('planner not configured')
    monkeypatch.setattr(storyboard,'produce_units',fail)
    with RunLock(run) as held:
        result=produce_scene_pipeline(frozen,paths=paths,logger=RunLogger(run,production=True),lock=held)
    assert result.status=='blocked' and result.active_stage=='units'


def test_validated_candidate_prefix_does_not_reenter_earlier_stage_writers(runtime_run,tmp_path,monkeypatch):
    import video_ai.runtime.production_scene_pipeline as pipeline
    import video_ai.runtime.image_selection_records as images
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from video_ai.runtime.scene_media_records import SceneMediaResult
    from video_ai.runtime.logging import RunLogger
    run,config,paths=runtime_run
    frozen=freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    candidate=run/'already-validated.mp4';candidate.write_bytes(b'validated by the substituted read-only boundary')
    expected=SceneMediaResult(run_id=run.name,run_dir=run,status='awaiting_final_review',candidate=candidate,active_stage='composition')
    (run/'production/scene-plan-commit.json').write_text('{}')
    monkeypatch.setattr(pipeline,'_common',lambda *a,**kw:({},None,{}))
    monkeypatch.setattr(images,'load_committed_plan',lambda *a:({},dict(scenes=[],batches=[])))
    monkeypatch.setattr(pipeline,'_preflight_later',lambda *a:expected)
    monkeypatch.setattr(images,'load_accepted_batches',lambda *a:[])
    def refuse(*args,**kwargs):raise ProductionRefused('reentered an earlier stage after complete prefix admission')
    monkeypatch.setattr(images,'require_complete_image_acceptance',refuse)
    with RunLock(run) as held:
        result=pipeline.produce_scene_pipeline(frozen,paths=paths,logger=RunLogger(run,production=True),lock=held)
    assert result is expected


def test_automatic_common_cannot_claim_prepared_reports_without_original_speech_records(runtime_run,tmp_path):
    import wave
    from types import SimpleNamespace
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import ArtifactStamp,ProductionStateStore
    from video_ai.runtime.manifest import thaw
    from video_ai.planning.production_timeline import ProductionAudioInfo,build_production_timeline
    from video_ai.runtime._scene_revision_origins import owned_common
    from scene_pipeline_helpers import persist_prepared_common
    run,config,_=runtime_run
    frozen=freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    span=next(s for s in frozen.script.spans if s.kind=='speech')
    pcm=run/'audio.wav'
    with wave.open(str(pcm),'wb') as stream:
        stream.setparams((1,2,48000,0,'NONE',''));stream.writeframes(b'\x01\x00'*3001)
    units=dict(decoded_text=frozen.script.text,has_bom=False,spans=thaw(frozen.script.spans),semantic_specs={span.unit_id:dict(facts={})})
    timeline=build_production_timeline(frozen.script,{span.unit_id:ProductionAudioInfo(ArtifactStamp.read(pcm),48000,1,2,3001)},settings=frozen.config.media.timeline)
    persist_prepared_common(dict(run=run,units=units,timeline=timeline))
    assert owned_common(frozen)['units']==units
    ProductionStateStore.create(run)
    with pytest.raises(ValueError,match='automatic|speech|checkpoint'):owned_common(frozen)


def test_baseline_http_send_rechecks_real_lock_after_credentials_are_read(runtime_run,tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from video_ai.runtime.jimeng_candidates import generate_candidates
    from video_ai.adapters.jimeng import JimengClient
    run,config,_=runtime_run
    frozen=freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    for name in ('TEST_VOLC_AK','TEST_VOLC_SK'):monkeypatch.setenv(name,'synthetic-test-only')
    sends=[]
    def transport(method,url,**kwargs):
        if kwargs.get('ownership_check') is not None:kwargs['ownership_check']()
        sends.append(method);raise RuntimeError('stale owner reached HTTP transport')
    client=JimengClient(frozen.config.image_generation,http=SimpleNamespace(request=transport))
    original=client.check_credentials;checks=[]
    with RunLock(run) as held:
        def credentials():
            checks.append(True)
            if len(checks)==2:held.path.write_text(json.dumps(dict(held.owner,token='e'*32)),encoding='utf-8')
            return original()
        monkeypatch.setattr(client,'check_credentials',credentials)
        try:
            with pytest.raises(ProductionRefused):generate_candidates(frozen,'scene_0001','原提示词',client=client,lock=held)
        finally:held.path.write_text(json.dumps(held.owner),encoding='utf-8')
    assert sends==[]


def test_pipeline_inputs_boundary_precedes_common_ready_marker(runtime_run,tmp_path,monkeypatch):
    from types import SimpleNamespace
    import video_ai.runtime.production_scene_pipeline as pipeline
    from video_ai.runtime.scene_pipeline_records import record_common
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock
    from unit.test_jimeng_config import configured
    run,config,_=runtime_run;frozen=freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    for stage in ('units','timeline'):(run/f'production/{stage}.json').write_text('{}')
    def stop(point):
        if point=='pipeline-inputs':raise KeyboardInterrupt('after durable inputs, before common ready')
    monkeypatch.setattr(pipeline,'boundary',stop)
    with RunLock(run) as held:
        with pytest.raises(KeyboardInterrupt):record_common(frozen,{},SimpleNamespace(clips=[]),'prepared',lock=held)
    assert (run/'production/scene-pipeline/inputs.json').is_file()
    assert not (run/'production/scene-pipeline/common-inputs-ready.json').exists()


def test_invocation_rechecks_inherited_proof_before_recording_readiness(runtime_run,monkeypatch):
    from types import SimpleNamespace
    import video_ai.runtime.production_scene_pipeline as pipeline
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    run,_,_=runtime_run
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'scene_revision':{'sha256':'a'*64}})
    result=SimpleNamespace(to_dict=lambda:dict(status='upscale_ready'))
    def changed(*args):raise ProductionRefused('source changed during cleanup')
    monkeypatch.setattr(pipeline,'require_scene_revision',changed)
    with RunLock(run) as held:
        with pytest.raises(ValueError,match='source changed'):pipeline.record_invocation(frozen,'advance',result,[],lock=held)
    assert not (run/'logs/production/scene-invocations').exists()


@pytest.mark.parametrize('record,field,value',[
    ('inputs','schema_version',2.0),('common-inputs-ready','schema_version',2.0),
    ('common-inputs-ready','created_at','invalid timestamp'),
])
def test_common_records_reject_noncanonical_schema_and_time(runtime_run,tmp_path,record,field,value):
    import json
    from types import SimpleNamespace
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_pipeline_records import record_common,validate_common_record
    run,config,_=runtime_run
    frozen=freeze_inputs(configured(config,tmp_path),run,text='完整原文。')
    for stage in ('units','timeline'):(run/f'production/{stage}.json').write_text('{}')
    timeline=SimpleNamespace(clips=[])
    with RunLock(run) as held:record_common(frozen,{},timeline,'prepared',lock=held)
    path=run/'production/scene-pipeline'/(record+'.json')
    saved=json.loads(path.read_text(encoding='utf-8'));saved[field]=value
    path.write_text(json.dumps(saved),encoding='utf-8')
    with pytest.raises(ValueError):validate_common_record(frozen,{},timeline,'prepared')
