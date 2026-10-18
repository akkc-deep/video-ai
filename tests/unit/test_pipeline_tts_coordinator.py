"""TEST ONLY isolated real coordinator and bounded TTS final-failure receipts."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import wave
import pytest
from http_helpers import Response, ScriptedTransport
from unit.test_pipeline_voice_admission import fixture


@pytest.mark.parametrize('failure',['400','badwav'])
@pytest.mark.parametrize('first',[False,True])
@pytest.mark.parametrize('retry_succeeds',[False,True])
def test_coordinator_explicit_tts_retry_is_one_new_child_attempt(runtime_run,monkeypatch,failure,first,retry_succeeds):
    from video_ai import pipeline
    from video_ai.config import load_config
    from video_ai.runtime.manifest import ManifestStore,hash_file,thaw,now
    from video_ai.runtime import preflight as admission,pipeline_inventory
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.services import ServiceSpec
    from video_ai.runtime.timeline_checks import _artifact
    from video_ai.runtime.paths import RuntimePaths
    from unit.test_speech_checks import reviewed_input
    s,baseline,parent,c,script,yaml=fixture(runtime_run,monkeypatch,model=True)
    current=load_config(c.config_file);store=ManifestStore.open(parent);events=[];posts=[]
    class Manager:
        def __init__(self,*args):pass
        def ensure(self,spec):events.append('start');return SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:None))
        def stop(self,handle):events.append('stop')
    monkeypatch.setattr(s,'ServiceManager',Manager)
    monkeypatch.setattr(s,'scan_isolation',lambda *a,**k:{})
    monkeypatch.setattr(s,'validate_fixed_voice_log',lambda *a:None)
    monkeypatch.setattr(s,'service_log',lambda *a:'TEST ONLY')
    monkeypatch.setattr(s,'build_service_specs',lambda *a:{'tts':ServiceSpec('tts',c.services['tts'],('TEST ONLY','-c',str(yaml)),c.project_root,30)})
    freeze=s.freeze_inputs;startup=s.validate_voice_startup
    monkeypatch.setattr(s,'freeze_inputs',lambda config,*a,**k:freeze(replace(config,project_root=c.project_root),*a,**k))
    monkeypatch.setattr(s,'validate_voice_startup',lambda config,*a,**k:startup(replace(config,project_root=c.project_root),*a,**k))
    native_wav=s.standardize_wav
    monkeypatch.setattr(s,'standardize_wav',lambda *a,**k:native_wav(*a,**dict(k,config=current,paths=RuntimePaths.from_config(current))))
    body=BytesIO()
    with wave.open(body,'wb') as wav:wav.setparams((1,2,48000,0,'NONE',''));wav.writeframes(b'\0\0'*4800)
    state={'target':1 if first else 3}
    def route(request,timeout):
        posts.append(request.data)
        if len(posts)==state['target']:
            return Response({'error':'TEST ONLY rejected'},status=400) if failure=='400' else Response(b'TEST ONLY complete invalid WAV',headers={'Content-Type':'audio/wav'})
        return Response(body.getvalue(),headers={'Content-Type':'audio/wav'})
    http=s.HttpClient;transport=ScriptedTransport(route)
    monkeypatch.setattr(s,'HttpClient',lambda *a:http(*a,transport=transport))
    review=reviewed_input(parent,script)
    logger=RunLogger(parent)
    preflight=admission.PreflightReport((admission.PreflightCheck('TEST ONLY',True,'isolated resource admission'),))
    preflight_path=logger.save_json('pipeline/preflight.json',preflight.as_dict())
    store.record_stage('preflight','running');store.record_stage('preflight','completed',artifacts=[_artifact(hash_file(preflight_path))])
    canonical=parent/'logs/pipeline/unit-review.json';canonical.write_bytes(review.read_bytes())
    logger.save_json('pipeline/pipeline-options.json',dict(schema_version=1,run_id=parent.name,created_at=now(),
        input_identities=thaw(store.snapshot()['inputs']),unit_review_identity=thaw(hash_file(canonical)),image_inputs_identity=None,
        settings_identity=None,output_path=None,cpu_planner=False,execution_policy=dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300)))
    assert not s.synthesize_script(c,script,run_dir=parent,store=store,segmentation_path=canonical).passed
    uid='reference_replay' if first else 'speech_0002';before=store.snapshot();before_posts=len(posts)
    assert before_posts==(1 if first else 3)
    monkeypatch.setattr(admission,'preflight',lambda *a,**k:preflight)
    def projection(config,identities):
        value=thaw(config);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',projection)
    refused=pipeline.plan_resume(current,run_dir=parent)
    assert refused.refusal_reasons and len(posts)==before_posts
    plan=pipeline.plan_resume(current,run_dir=parent,retry_failed=True)
    assert plan.requires_child_run and any(row.stage=='speech' and row.unit_id==uid for row in plan.invalidated)
    state['target']=None if retry_succeeds else before_posts+1
    result=pipeline.resume_pipeline(current,run_dir=parent,retry_failed=True)
    assert result.run_dir!=parent and result.parent_run_dir==parent
    child=ManifestStore.open(result.run_dir).snapshot()
    from video_ai.runtime.pipeline_import import load_pipeline_import,same_identity,fresh
    receipt=load_pipeline_import(result.run_dir)
    for name in ('tts_runtime','tts_installed_data','tts_runtime_data','tts_serialization','tts_runtime_startup'):
        old=before['inputs'][name]
        assert same_identity(receipt['source_identities'][old['path']],old)
        assert same_identity(thaw(fresh(old)),old)
        assert Path(child['inputs'][name]['path']).is_relative_to(result.run_dir)
    if retry_succeeds:
        report=s.load_committed_speech(result.run_dir)
        remaining=1+sum(row['kind']=='speech' for row in report['report']['spans'])-sum(row['status']=='completed' for row in before['units']['speech'].values())
        assert result.status=='awaiting_review' and 'voice_acceptance' in result.waiting_for
        assert child['stages']['speech']['status']=='completed' and report['accepted'] is False
        assert len(posts)==before_posts+remaining
    else:
        remaining=1
        assert result.status=='failed'
        assert child['stages']['speech']['status']=='failed' and child['units']['speech'][uid]['status']=='failed'
        assert len(posts)==before_posts+1
    assert len(list((result.run_dir/'logs/http').glob('*.request.json')))==remaining
    assert child['stages']['preflight']['status']=='completed' and child['stages']['timeline']['status']=='pending'
    after=store.snapshot();assert after['stages']==before['stages'] and after['units']==before['units']
    assert after['events'][:len(before['events'])]==before['events']
    assert all(after['workflows'][key]==value for key,value in before['workflows'].items())
    assert events==['start','stop','start','stop']
