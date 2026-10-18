"""TEST ONLY actual TTS rejection/bad-body evidence and explicit new attempts."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import wave
import pytest
from http_helpers import Response,ScriptedTransport
from unit.test_pipeline_voice_admission import fixture


@pytest.mark.parametrize('failure',['400','badwav','short_frames','empty_frames'])
@pytest.mark.parametrize('first',[False,True])
@pytest.mark.parametrize('retry_fails',[False,True])
def test_complete_failed_tts_response_retries_once_in_independent_child(runtime_run,monkeypatch,failure,first,retry_fails):
    from video_ai.config import load_config,read_json
    from video_ai.runtime.manifest import ManifestStore,hash_file
    from video_ai.runtime.services import ServiceSpec
    from video_ai.runtime.pipeline_import import derive_completed_stages,make_reuse_context,fresh
    from video_ai.media.audio import AudioInfo
    from unit.test_speech_checks import reviewed_input
    s,baseline,parent,c,script,yaml=fixture(runtime_run,monkeypatch,model=True)
    store=ManifestStore.open(parent);store.record_stage('preflight','running');store.record_stage('preflight','completed')
    review=reviewed_input(parent,script);events=[];attempts=[]
    class Manager:
        def __init__(self,*args):pass
        def ensure(self,spec):events.append('start');return SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:None))
        def stop(self,handle):events.append('stop')
    monkeypatch.setattr(s,'ServiceManager',Manager);monkeypatch.setattr(s,'scan_isolation',lambda *args,**kwargs:{})
    monkeypatch.setattr(s,'validate_fixed_voice_log',lambda *args:None);monkeypatch.setattr(s,'service_log',lambda *args:'TEST ONLY')
    monkeypatch.setattr(s,'build_service_specs',lambda *args:{'tts':ServiceSpec('tts',c.services['tts'],('TEST ONLY','-c',str(yaml)),c.project_root,30)})
    body=BytesIO()
    with wave.open(body,'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\0\0'*4800)
    empty=BytesIO()
    with wave.open(empty,'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'')
    defect=body.getvalue()[:-2] if failure=='short_frames' else empty.getvalue() if failure=='empty_frames' else b'TEST ONLY invalid complete WAV'
    state={'fail':True,'calls':0,'target':1 if first else 3}
    def route(request,timeout):
        state['calls']+=1;attempts.append(request.data)
        if state['fail'] and state['calls']==state['target']:
            return Response({'error':'TEST ONLY rejected'},status=400) if failure=='400' else Response(defect,headers={'Content-Type':'audio/wav'})
        return Response(body.getvalue(),headers={'Content-Type':'audio/wav'})
    transport=ScriptedTransport(route);http=s.HttpClient
    monkeypatch.setattr(s,'HttpClient',lambda *args:http(*args,transport=transport))
    native_standardize=s.standardize_wav
    def standardize(raw,target,**kwargs):
        if raw.read_bytes()==defect:return native_standardize(raw,target,**kwargs)
        target.write_bytes(raw.read_bytes());identity=hash_file(target);return AudioInfo(target,identity.sha256,identity.bytes,48000,1,2,4800)
    monkeypatch.setattr(s,'standardize_wav',standardize)
    assert not s.synthesize_script(c,script,run_dir=parent,store=store,segmentation_path=review).passed
    uid='reference_replay' if first else 'speech_0002'
    partial=s._load_partial_speech(parent)
    assert set(partial['known_failed_units'])=={uid}
    parent_before={p:p.read_bytes() for p in parent.rglob('*') if p.is_file()}
    current=load_config(c.config_file)
    if not first and not retry_fails:
        refused=derive_completed_stages(current,parent_run_dir=parent,stages=(),partial_stages=('speech',),reason='TEST ONLY missing explicit retry')
        refused_store=ManifestStore.open(refused);refused_store.record_stage('preflight','running');refused_store.record_stage('preflight','completed')
        r=read_json(refused/'segments.json');units=('reference_replay',)+tuple(i['unit_id'] for i in r['spans'] if i['kind']=='speech')
        forbidden_context=make_reuse_context(refused,stage='speech',unit_ids=units,current_input_identities={k:fresh(v) for k,v in refused_store.snapshot()['inputs'].items()})
        before_calls=state['calls']
        with pytest.raises(ValueError,match='exact explicit author targets'):
            s.resume_speech(replace(current,project_root=c.project_root),run_dir=refused,reuse_context=forbidden_context,store=refused_store)
        assert state['calls']==before_calls
    child=derive_completed_stages(current,parent_run_dir=parent,stages=(),partial_stages=('speech',),retry_targets={'speech':(uid,)},reason='TEST ONLY explicit retry')
    child_store=ManifestStore.open(child);child_store.record_stage('preflight','running');child_store.record_stage('preflight','completed')
    report=read_json(child/'segments.json');ids={k:fresh(v) for k,v in child_store.snapshot()['inputs'].items()}
    unit_ids=('reference_replay',)+tuple(i['unit_id'] for i in report['spans'] if i['kind']=='speech')
    context=make_reuse_context(child,stage='speech',unit_ids=unit_ids,current_input_identities=ids)
    old_calls=state['calls'];state.update(fail=retry_fails,target=old_calls+1)
    result=s.resume_speech(replace(current,project_root=c.project_root),run_dir=child,reuse_context=context,store=child_store)
    if retry_fails:
        assert not result.passed and state['calls']-old_calls==1
        assert child_store.snapshot()['stages']['speech']['status']=='failed'
        with pytest.raises(ValueError):s.load_committed_speech(child)
    else:
        assert result.passed,read_json(child/'segments.json').get('error')
        assert state['calls']-old_calls==len(context.remaining_units)
        assert s.load_committed_speech(child)['accepted'] is False
    assert all(p.read_bytes()==b for p,b in parent_before.items())
    assert events==['start','stop','start','stop']
    raw=parent/'audio'/uid/'raw.wav'
    if raw.exists():
        raw.write_bytes(raw.read_bytes()+b'TEST ONLY later failed-media drift')
        with pytest.raises((ValueError,OSError)):s._load_partial_speech(parent)
