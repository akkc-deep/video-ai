"""TEST ONLY real speech HTTP/PCM paths under persistence failures and generations."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import json
import wave
import pytest
from http_helpers import Response,ScriptedTransport
from unit.test_pipeline_voice_admission import fixture


def setup(runtime_run,monkeypatch,*,baseline=False):
    from video_ai import pipeline
    from video_ai.config import load_config
    from video_ai.runtime.manifest import ManifestStore,hash_file,thaw,now
    from video_ai.runtime import preflight as admission,pipeline_inventory
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.services import ServiceSpec
    from video_ai.runtime.timeline_checks import _artifact
    from video_ai.runtime.paths import RuntimePaths
    from unit.test_speech_checks import reviewed_input
    s,original,parent,c,script,yaml=fixture(runtime_run,monkeypatch,model=True,script_text='一，二，三。',baseline=baseline)
    current=load_config(c.config_file);store=ManifestStore.open(parent);events=[];posts=[]
    state={'mode':'400','unit_text':'二，','interrupt':KeyboardInterrupt('TEST ONLY exact original interruption'),'failure_enabled':False}
    class Manager:
        def __init__(self,*args):pass
        def ensure(self,spec):events.append('start');return SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:None))
        def stop(self,handle):events.append('stop')
    monkeypatch.setattr(s,'ServiceManager',Manager);monkeypatch.setattr(s,'scan_isolation',lambda *a,**k:{})
    monkeypatch.setattr(s,'validate_fixed_voice_log',lambda *a:None);monkeypatch.setattr(s,'service_log',lambda *a:'TEST ONLY')
    monkeypatch.setattr(s,'build_service_specs',lambda *a:{'tts':ServiceSpec('tts',c.services['tts'],('TEST ONLY','-c',str(yaml)),c.project_root,30)})
    freeze=s.freeze_inputs;startup=s.validate_voice_startup
    monkeypatch.setattr(s,'freeze_inputs',lambda config,*a,**k:freeze(replace(config,project_root=c.project_root),*a,**k))
    monkeypatch.setattr(s,'validate_voice_startup',lambda config,*a,**k:startup(replace(config,project_root=c.project_root),*a,**k))
    native=s.standardize_wav
    monkeypatch.setattr(s,'standardize_wav',lambda *a,**k:native(*a,**dict(k,config=current,paths=RuntimePaths.from_config(current))))
    body=BytesIO()
    with wave.open(body,'wb') as wav:wav.setparams((1,2,48000,0,'NONE',''));wav.writeframes(b'\0\0'*4800)
    def route(request,timeout):
        text=json.loads(request.data)['text'];posts.append(text)
        if text==state['unit_text']:
            if state['mode']=='400':return Response({'error':'TEST ONLY rejected'},status=400)
            if state['mode']=='interrupt':state['failure_enabled']=True;raise state['interrupt']
            if state['mode']=='lost':raise ConnectionResetError('TEST ONLY response lost')
        return Response(body.getvalue(),headers={'Content-Type':'audio/wav'})
    http=s.HttpClient;monkeypatch.setattr(s,'HttpClient',lambda *a:http(*a,transport=ScriptedTransport(route)))
    review=reviewed_input(parent,script);logger=RunLogger(parent)
    preflight=admission.PreflightReport((admission.PreflightCheck('TEST ONLY',True,'isolated resource admission'),))
    note=logger.save_json('pipeline/preflight.json',preflight.as_dict())
    store.record_stage('preflight','running');store.record_stage('preflight','completed',artifacts=[_artifact(hash_file(note))])
    logger.save_json('pipeline/pipeline-options.json',dict(schema_version=1,run_id=parent.name,created_at=now(),
        input_identities=thaw(store.snapshot()['inputs']),unit_review_identity=thaw(hash_file(review)),image_inputs_identity=None,
        settings_identity=None,output_path=None,cpu_planner=False,execution_policy=dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300)))
    monkeypatch.setattr(admission,'preflight',lambda *a,**k:preflight)
    def projection(config,identities):
        value=thaw(config);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',projection)
    return SimpleNamespace(s=s,pipeline=pipeline,parent=parent,c=c,current=current,store=store,script=script,review=review,state=state,posts=posts,events=events)


@pytest.mark.parametrize('damage',[None,'local_mtime','local_payload','canonical_mtime','canonical_payload'])
def test_baseline_schema2_isolates_real_startup_save_and_consumes_strictly(runtime_run,monkeypatch,damage):
    from video_ai.config import read_json
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime.logging import RunLogger
    import os
    f=setup(runtime_run,monkeypatch,baseline=True);f.state['mode']='success'
    canonical=f.c.project_root/'config/tts-api.yaml';before=hash_file(canonical)
    assert 'pipeline_import' not in f.store.snapshot()['workflows']
    class Manager:
        def __init__(self,*args):pass
        def ensure(self,spec):
            runtime=Path(spec.args[spec.args.index('-c')+1])
            assert runtime!=canonical and runtime.is_relative_to(f.parent)
            # Actual bundled save_configs serialization, without model loading.
            initial=hash_file(runtime)
            f.s.audio_command((f.c.tools['tts_python'],'-B','-c',
                'import yaml,sys; p=sys.argv[1]; d=yaml.load(open(p,encoding="utf-8"),Loader=yaml.FullLoader); yaml.dump(d,open(p,"w"))',runtime),
                paths=f.s.RuntimePaths.from_config(f.current),logger=RunLogger(f.parent),unit_id='baseline_startup_save',timeout=30)
            after=hash_file(runtime)
            assert (after.bytes,after.sha256)==(initial.bytes,initial.sha256) and after.mtime_ns!=initial.mtime_ns
            f.events.append('start');return SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:None))
        def stop(self,handle):f.events.append('stop')
    monkeypatch.setattr(f.s,'ServiceManager',Manager)
    result=f.s.synthesize_script(f.c,f.script,run_dir=f.parent,store=f.store,segmentation_path=f.review)
    assert result.passed,read_json(f.parent/'segments.json').get('error')
    after=hash_file(canonical)
    assert (before.path,before.bytes,before.mtime_ns,before.sha256)==(after.path,after.bytes,after.mtime_ns,after.sha256)
    assert f.events==['start','stop'] and len(f.posts)==4
    assert 'voice_revision' not in f.store.snapshot()['inputs']
    consumed=f.s.load_committed_speech(f.parent)
    assert consumed['report']['schema_version']==2 and consumed['accepted'] is False
    plan=f.pipeline.plan_resume(f.current,run_dir=f.parent)
    assert not plan.refusal_reasons and not plan.requires_child_run and 'voice_acceptance' in plan.waiting_for
    if damage is not None:
        path=canonical if damage.startswith('canonical') else Path(f.store.snapshot()['inputs']['tts_runtime']['path'])
        if damage.endswith('mtime'):
            stat=path.stat();os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000))
        else:path.write_bytes(path.read_bytes()+b'\n# TEST ONLY late mutation\n')
        with pytest.raises((ValueError,OSError)):f.s.load_committed_speech(f.parent)
        with pytest.raises((ValueError,OSError)):f.pipeline.plan_resume(f.current,run_dir=f.parent)
        assert len(f.posts)==4


def test_legacy_baseline_startup_keeps_compatibility(runtime_run,monkeypatch):
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import hash_file
    s,parent,run,c,script,yaml=fixture(runtime_run,monkeypatch,baseline=True)
    before=hash_file(yaml)
    s.freeze_inputs(c,script)
    assert s.validate_voice_startup(c,paths=s.RuntimePaths.from_config(c),logger=RunLogger(run)) is None
    after=hash_file(yaml)
    assert (before.bytes,before.sha256,before.mtime_ns)==(after.bytes,after.sha256,after.mtime_ns)


@pytest.mark.parametrize('damage',['tts_yaml','voice','model'])
def test_baseline_schema2_config_isolation_retains_admission(runtime_run,monkeypatch,damage):
    f=setup(runtime_run,monkeypatch,baseline=True);f.state['mode']='success'
    path={'tts_yaml':f.c.project_root/'config/tts-api.yaml','voice':f.c.voice.config_file,'model':f.c.voice.gpt_weights}[damage]
    path.write_bytes(path.read_bytes()+b'\n ')
    result=f.s.synthesize_script(f.c,f.script,run_dir=f.parent,store=f.store,segmentation_path=f.review)
    assert not result.passed and f.posts==[] and f.events==[]
    assert not (f.parent/'logs/voice-runtime-configuration.yaml').exists()


def inject_persistence_failure(f,monkeypatch,mode):
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import ManifestStore
    diagnostic=RunLogger.exception;write=f.s.atomic_report;record=ManifestStore.record_stage
    def diagnostic_fail(self,stage,*a,**k):
        if f.state['failure_enabled'] and mode=='diagnostic' and stage=='speech':raise OSError('TEST ONLY diagnostic failure')
        return diagnostic(self,stage,*a,**k)
    def report_fail(path,data):
        if f.state['failure_enabled'] and Path(path).name=={'segments':'segments.json','listening':'voice-listening.json'}.get(mode):
            raise OSError('TEST ONLY report failure')
        return write(path,data)
    def stage_fail(self,stage,status,*a,**k):
        if f.state['failure_enabled'] and mode=='stage' and stage=='speech' and status=='interrupted':raise OSError('TEST ONLY stage failure')
        return record(self,stage,status,*a,**k)
    monkeypatch.setattr(RunLogger,'exception',diagnostic_fail);monkeypatch.setattr(f.s,'atomic_report',report_fail)
    monkeypatch.setattr(ManifestStore,'record_stage',stage_fail)


@pytest.mark.parametrize('mode',['diagnostic','segments','listening','stage'])
@pytest.mark.parametrize('exit_kind',['ctrlc','exit'])
def test_native_speech_preserves_exact_interrupt_and_owned_stop(runtime_run,monkeypatch,mode,exit_kind):
    f=setup(runtime_run,monkeypatch);f.state.update(mode='interrupt',unit_text=f.c.voice.reference_text)
    if exit_kind=='exit':f.state['interrupt']=SystemExit(7)
    inject_persistence_failure(f,monkeypatch,mode)
    with pytest.raises(type(f.state['interrupt'])) as caught:
        f.s.synthesize_script(f.c,f.script,run_dir=f.parent,store=f.store,segmentation_path=f.review)
    assert caught.value is f.state['interrupt'] and f.events==['start','stop']
    assert f.posts==[f.c.voice.reference_text]


@pytest.mark.parametrize('mode',['diagnostic','segments','listening','stage'])
def test_real_pipeline_cli_returns_130_after_tts_interrupt_and_persistence_failure(runtime_run,monkeypatch,mode):
    from video_ai import cli
    f=setup(runtime_run,monkeypatch)
    assert not f.s.synthesize_script(f.c,f.script,run_dir=f.parent,store=f.store,segmentation_path=f.review).passed
    f.state.update(mode='interrupt');inject_persistence_failure(f,monkeypatch,mode)
    code=cli.main(['resume','--config',str(f.current.config_file),'--run-dir',str(f.parent),'--retry-failed','--json'])
    assert code==130 and f.events==['start','stop','start','stop']
    assert f.posts.count('一，')==1 and f.posts.count('二，')==2 and '三。' not in f.posts


def test_new_interrupt_during_failure_diagnostics_is_preserved(runtime_run,monkeypatch):
    from video_ai.runtime.logging import RunLogger
    f=setup(runtime_run,monkeypatch);diagnostic=RunLogger.exception
    def interrupt_diagnostic(self,stage,*a,**k):
        if stage=='speech':raise f.state['interrupt']
        return diagnostic(self,stage,*a,**k)
    monkeypatch.setattr(RunLogger,'exception',interrupt_diagnostic)
    with pytest.raises(KeyboardInterrupt) as caught:
        f.s.synthesize_script(f.c,f.script,run_dir=f.parent,store=f.store,segmentation_path=f.review)
    assert caught.value is f.state['interrupt'] and f.events==['start','stop']
    assert json.loads((f.parent/'segments.json').read_text(encoding='utf-8'))['status']=='interrupted'


def mixed_child(f,monkeypatch,mode):
    """Actual failed parent, copied prefix, then a new native second clause."""
    assert not f.s.synthesize_script(f.c,f.script,run_dir=f.parent,store=f.store,segmentation_path=f.review).passed
    f.state.update(mode=mode,unit_text='三。')
    write=f.s.atomic_report
    def interrupt_before_send(path,data):
        result=write(path,data)
        if (mode=='before_next' and Path(path).name=='segments.json' and Path(path).parent!=f.parent
                and not f.state.get('boundary_interrupted')
                and any(row.get('unit_id')=='speech_0002' and row['status']=='completed' for row in data['spans'])
                and any(row.get('unit_id')=='speech_0003' and row['status']=='pending' for row in data['spans'])):
            f.state['boundary_interrupted']=True
            raise f.state['interrupt']
        return result
    monkeypatch.setattr(f.s,'atomic_report',interrupt_before_send)
    result=f.pipeline.resume_pipeline(f.current,run_dir=f.parent,retry_failed=True)
    assert result.status==('interrupted' if mode=='before_next' else 'failed')
    assert f.posts.count('一，')==1 and f.posts.count('二，')==2
    assert f.posts.count('三。')==(0 if mode=='before_next' else 1)
    return result.run_dir


@pytest.mark.parametrize('mode',['before_next','400'])
@pytest.mark.parametrize('extra_failed_generation',[False,True])
def test_actual_coordinator_resumes_mixed_prefix_across_generations(runtime_run,monkeypatch,mode,extra_failed_generation):
    from video_ai.runtime.manifest import ManifestStore,hash_file
    from video_ai.runtime.pipeline_import import load_pipeline_import
    f=setup(runtime_run,monkeypatch);child=mixed_child(f,monkeypatch,mode);first_child=child
    original=json.loads((child/'segments.json').read_text(encoding='utf-8'))
    parent_before=f.store.snapshot();child_before=ManifestStore.open(child).snapshot()
    prefix={row['unit_id']:row for row in [original['reference_replay'],*original['spans']] if row['status']=='completed'}
    child_report=hash_file(child/'segments.json')
    plan=f.pipeline.plan_resume(f.current,run_dir=child,retry_failed=mode=='400')
    assert not plan.refusal_reasons and plan.requires_child_run
    if extra_failed_generation:
        f.state.update(mode='400')
        failed=f.pipeline.resume_pipeline(f.current,run_dir=child,retry_failed=mode=='400')
        assert failed.status=='failed'
        child=failed.run_dir
        mode='400'
    before_posts=len(f.posts);f.state.update(mode='success')
    result=f.pipeline.resume_pipeline(f.current,run_dir=child,retry_failed=mode=='400')
    assert result.status=='awaiting_review' and 'voice_acceptance' in result.waiting_for
    assert f.posts[before_posts:]==['三。']
    consumed=f.s.load_committed_speech(result.run_dir);report=consumed['report']
    receipt=load_pipeline_import(result.run_dir)
    copied={row['unit_id']:row for row in [report['reference_replay'],*report['spans']] if row['status']=='completed'}
    for uid,row in prefix.items():
        for key in ('raw','pcm'):
            assert copied[uid][key]['path']!=row[key]['path']
            assert (copied[uid][key]['bytes'],copied[uid][key]['sha256'])==(row[key]['bytes'],row[key]['sha256'])
        assert copied[uid]['http_evidence_path']==row['http_evidence_path']
        assert row['http_evidence_path'] in receipt['source_identities']
        assert report['reused_units'][uid]['origin_run_id']==(f.parent.name if uid!='speech_0002' else child_before['run_id'])
    assert report['reused_units']['speech_0002']['source_report_identity']['sha256']==child_report.sha256
    assert f.store.snapshot()['units']==parent_before['units']
    assert ManifestStore.open(first_child).snapshot()['units']==child_before['units']


@pytest.mark.parametrize('damage',['lost','copy_pcm','original_http','original_pcm','native_http','missing_native_http','missing_native_conversion'])
def test_mixed_prefix_unknown_or_changed_evidence_refuses_without_post(runtime_run,monkeypatch,damage):
    f=setup(runtime_run,monkeypatch);child=mixed_child(f,monkeypatch,'lost' if damage=='lost' else '400')
    report=json.loads((child/'segments.json').read_text(encoding='utf-8'))
    if damage!='lost':
        row=report['spans'][0]
        if damage=='original_pcm':
            path=Path(json.loads((f.parent/'segments.json').read_text(encoding='utf-8'))['spans'][0]['pcm']['path'])
        elif damage=='native_http':path=Path(report['spans'][1]['http_evidence_path'])
        elif damage.startswith('missing_native_'):
            report['spans'][1].pop('http_evidence_path' if damage=='missing_native_http' else 'audio_evidence_path')
            (child/'segments.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
            path=None
        else:path=Path(row['pcm']['path'] if damage=='copy_pcm' else row['http_evidence_path'])
        if path is not None:path.write_bytes(path.read_bytes()+b'TEST ONLY mutation')
    before=len(f.posts)
    if damage=='lost':
        with pytest.raises(ValueError,match='unknown TTS intent|incomplete original stage'):
            f.s._load_partial_speech(child)
        plan=f.pipeline.plan_resume(f.current,run_dir=child,retry_failed=True)
        assert not plan.requires_child_run and 'speech/speech_0003:submission' in plan.waiting_for
        with pytest.raises(f.pipeline.PipelineRefusal,match='lost response remains unknown'):
            f.pipeline.resume_pipeline(f.current,run_dir=child,retry_failed=True)
    else:
        with pytest.raises((ValueError,OSError)):
            f.pipeline.plan_resume(f.current,run_dir=child,retry_failed=True)
        with pytest.raises(f.pipeline.PipelineRefusal):
            f.pipeline.resume_pipeline(f.current,run_dir=child,retry_failed=True)
    assert len(f.posts)==before
