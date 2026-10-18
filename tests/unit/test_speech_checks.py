import json
from pathlib import Path
from types import SimpleNamespace
import wave
import pytest


@pytest.fixture
def speech_setup(runtime_run, monkeypatch):
    from video_ai.runtime import speech_checks as s
    from video_ai.runtime.manifest import hash_file
    from video_ai.adapters.common import HttpResponse, AdapterError
    run, config, paths = runtime_run
    script = run/'original.txt'
    script.write_bytes('甲，乙。\r\n\r\n末尾'.encode())
    state = dict(calls=[], stops=[], owned=True, failure=None, scan=0, drift=False, resources=1, mutate=None, mutate_unit='speech_0001')
    def freeze(config, script): return dict(script=hash_file(script), config=hash_file(config.config_file)), {}
    monkeypatch.setattr(s, 'freeze_inputs', freeze)
    monkeypatch.setattr(s, 'validate_voice_startup', lambda *a,**k: None)
    # Service process boundaries are injected; the example uses pre-migration 11434.
    monkeypatch.setattr(s, 'build_service_specs', lambda *a: {'tts':object()})
    def scan(*a,**k):
        state['scan'] += 1
        return {'fixture':{'sha256':'changed' if state['drift'] and state['scan']>1 else 'same'}}
    monkeypatch.setattr(s, 'scan_isolation', scan)
    class Manager:
        def __init__(self,*a,**k): self.owned_pids = set()
        def ensure(self,spec): return SimpleNamespace(owned=state['owned'], process=SimpleNamespace(poll=lambda: None))
        def stop(self,handle): state['stops'].append(handle)
    monkeypatch.setattr(s,'ServiceManager',Manager)
    class Sampler:
        def __init__(self,*a,**k): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def summary(self): return {'verified_samples':state['resources']}
    monkeypatch.setattr(s,'ResourceSampler',Sampler,raising=False)
    class Tts:
        def __init__(self,*a): pass
        def payload(self,text): return {'text':text}
        def synthesize(self,text,*,unit_id):
            state['calls'].append((unit_id,text))
            if state['mutate'] and unit_id==state['mutate_unit']: state['mutate']()
            if state['failure'] and unit_id == 'speech_0002':
                if state['failure']=='interrupt': raise KeyboardInterrupt()
                raise AdapterError(state['failure'],'injected lost response')
            evidence = run/'logs'/f'{unit_id}.body'
            evidence.write_bytes(b'fixture raw')
            return HttpResponse(200,{},b'fixture raw',evidence)
    monkeypatch.setattr(s,'TtsClient',Tts)
    def standardize(raw,target,**kwargs):
        from video_ai.media.audio import AudioInfo
        with wave.open(str(target),'wb') as f:
            f.setparams((1,2,48000,0,'NONE',''))
            f.writeframes(b'\0\0'*4800)
        ident = hash_file(target)
        return AudioInfo(target,ident.sha256,ident.bytes,48000,1,2,4800)
    monkeypatch.setattr(s,'standardize_wav',standardize)
    monkeypatch.setattr(s,'validate_tts_load_log',lambda *a: None)
    monkeypatch.setattr(s,'validate_fixed_voice_log',lambda *a: None)
    monkeypatch.setattr(s,'service_log',lambda *a: '')
    return s,run,config,script,state


def test_complete_spans_pcm_preview_and_manifest(speech_setup):
    s,run,config,script,state = speech_setup
    result = s.synthesize_script(config,script,run_dir=run)
    assert result.passed and not result.listened and result.total_speech_samples == 14400
    data = json.loads(result.segments_path.read_text(encoding='utf-8'))
    assert data['coverage_verified'] and ''.join(p['text'] for p in data['spans']) == script.read_bytes().decode()
    assert [t for uid,t in state['calls'] if uid.startswith('speech_')] == ['甲，','乙。','末尾']
    assert len(state['stops']) == 1
    manifest = json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['stages']['speech']['status'] == 'completed'
    assert all(v['submission'] is None for v in manifest['units']['speech'].values())
    with wave.open(str(run/'audio/listening-preview.wav'),'rb') as f: assert f.getnframes() == 14400
    assert json.loads((run/'voice-listening.json').read_text())['accepted'] is False


@pytest.mark.parametrize('failure,status', [('ambiguous','ambiguous'),('explicit','failed'),('invalid_result','failed'),('interrupt','interrupted')])
def test_failure_preserves_first_stops_following(speech_setup, failure, status):
    s,run,config,script,state = speech_setup
    state['failure'] = failure
    if failure=='interrupt':
        with pytest.raises(KeyboardInterrupt): s.synthesize_script(config,script,run_dir=run)
    else:
        assert not s.synthesize_script(config,script,run_dir=run).passed
    data = json.loads((run/'segments.json').read_text(encoding='utf-8'))
    speech = [p for p in data['spans'] if p['kind']=='speech']
    assert [p['status'] for p in speech] == ['completed',status,'pending']
    assert (run/'audio/speech_0001/pcm-48000.wav').exists()
    assert not (run/'audio/speech_0003').exists() and len(state['stops'])==1
    assert len([u for u,t in state['calls'] if u=='speech_0002'])==1


def test_external_service_not_touched(speech_setup):
    s,run,config,script,state = speech_setup
    state['owned'] = False
    assert not s.synthesize_script(config,script,run_dir=run).passed
    assert not state['stops'] and not state['calls']


@pytest.mark.parametrize('failure', ['isolation','resource','input'])
def test_acceptance_gates(speech_setup, failure):
    s,run,config,script,state = speech_setup
    if failure=='isolation': state['drift']=True
    if failure=='resource': state['resources']=0
    if failure=='input': script.write_bytes(b' \r\n,!?')
    result=s.synthesize_script(config,script,run_dir=run)
    # Resource sample admission belongs to historical evidence; subsequent
    # executions follow VAI-13's disabled GPU policy even on the legacy CLI.
    assert result.passed if failure=='resource' else not result.passed
    if failure=='resource':assert 'resources' not in json.loads(result.segments_path.read_text(encoding='utf-8'))
    if failure=='input': assert not state['calls']


def test_source_changes_fail_stage(speech_setup):
    s,run,config,script,state = speech_setup
    state['mutate'] = lambda: script.write_bytes(b'changed source')
    assert not s.synthesize_script(config,script,run_dir=run).passed
    assert 'frozen input/model changed' in json.loads((run/'segments.json').read_text(encoding='utf-8'))['error']['message']


def test_media_failure_retains_raw_and_first_pcm(speech_setup, monkeypatch):
    s,run,config,script,state = speech_setup
    original = s.standardize_wav
    def conversion(*a,**k):
        if k['unit_id']=='speech_0002': raise ValueError('bad WAV samples')
        return original(*a,**k)
    monkeypatch.setattr(s,'standardize_wav',conversion)
    assert not s.synthesize_script(config,script,run_dir=run).passed
    assert (run/'audio/speech_0002/raw.wav').exists()
    assert (run/'audio/speech_0001/pcm-48000.wav').exists()
    assert not (run/'audio/speech_0003').exists()


@pytest.mark.parametrize('bad', ['missing','cuda','version','path','fallback'])
def test_fixed_voice_log_requires_matching_loaded_models(runtime_run, bad):
    from video_ai.runtime.speech_checks import validate_fixed_voice_log
    voice = runtime_run[1].voice
    log = '\n'.join(f'{key} : {value}' for key,value in dict(device='cpu',is_half='False',version='v2',
        t2s_weights_path=voice.gpt_weights.as_posix(),vits_weights_path=voice.sovits_weights.as_posix(),
        bert_base_path=voice.bert_root.as_posix(),cnhuhbert_base_path=voice.hubert_root.as_posix()).items())
    log += '\n' + '\n'.join(f'Loading {name} weights from {getattr(voice,key).as_posix()}' for name,key in
                         [('Text2Semantic','gpt_weights'),('VITS','sovits_weights'),('BERT','bert_root'),('CNHuBERT','hubert_root')])
    validate_fixed_voice_log(log,voice)
    if bad=='missing': log=''
    if bad=='cuda': log=log.replace('device : cpu','device : cuda:0')
    if bad=='version': log=log.replace('version : v2','version : v1')
    if bad=='path': log=log.replace(voice.gpt_weights.as_posix(),'D:/wrong.ckpt')
    if bad=='fallback': log+='\nfallback'
    with pytest.raises((ValueError,OSError)): validate_fixed_voice_log(log,voice)


@pytest.mark.parametrize('target', ['raw','reference_raw','reference_pcm'])
def test_completed_audio_mutation_fails_stage(speech_setup, target):
    s,run,config,script,state = speech_setup
    relative = {'raw':'speech_0001/raw.wav', 'reference_raw':'reference_replay/raw.wav',
                'reference_pcm':'reference_replay/pcm-48000.wav'}[target]
    state['mutate_unit'] = 'speech_0002'
    state['mutate'] = lambda: (run/'audio'/relative).write_bytes(b'changed completed audio')
    assert not s.synthesize_script(config,script,run_dir=run).passed


@pytest.mark.parametrize('field', ['voice','tts_yaml'])
def test_approved_voice_identity_cannot_change(field):
    from video_ai.runtime.speech_checks import validate_voice_baseline
    inputs = dict(voice=SimpleNamespace(sha256='voice-original'),tts_yaml=SimpleNamespace(sha256='yaml-original'))
    baseline = dict(voice_sha256='voice-original',tts_config_sha256='yaml-original')
    validate_voice_baseline(inputs,baseline)
    inputs[field] = SimpleNamespace(sha256='edited')
    with pytest.raises(OSError): validate_voice_baseline(inputs,baseline)


@pytest.mark.parametrize('when', ['before','after'])
def test_manifest_completion_interrupt_consistent(speech_setup, monkeypatch, when):
    from video_ai.runtime.manifest import ManifestStore
    s,run,config,script,state = speech_setup
    original = ManifestStore.record_unit
    triggered = False
    def persist(self,kind,unit_id,status,**kwargs):
        nonlocal triggered
        if unit_id=='speech_0002' and status=='completed' and not triggered:
            triggered = True
            if when=='after': original(self,kind,unit_id,status,**kwargs)
            raise KeyboardInterrupt()
        return original(self,kind,unit_id,status,**kwargs)
    monkeypatch.setattr(ManifestStore,'record_unit',persist)
    with pytest.raises(KeyboardInterrupt): s.synthesize_script(config,script,run_dir=run)
    data = json.loads((run/'segments.json').read_text(encoding='utf-8'))
    units = json.loads((run/'manifest.json').read_text(encoding='utf-8'))['units']['speech']
    expected = 'completed' if when=='after' else 'interrupted'
    assert units['speech_0002']['status']==expected
    assert next(p for p in data['spans'] if p['unit_id']=='speech_0002')['status']==expected
    assert units['speech_0001']['status']=='completed' and not (run/'audio/speech_0003').exists()


def test_pcm_changed_after_conversion_not_completed(speech_setup, monkeypatch):
    s,run,config,script,state = speech_setup
    original = s.standardize_wav
    def conversion(raw,target,**kw):
        info = original(raw,target,**kw)
        target.write_bytes(b'changed after validation')
        return info
    monkeypatch.setattr(s,'standardize_wav',conversion)
    assert not s.synthesize_script(config,script,run_dir=run).passed
    manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['units']['speech']['reference_replay']['status']=='failed'


def test_source_changed_during_final_scan_fails(speech_setup, monkeypatch):
    s,run,config,script,state = speech_setup
    original=s.scan_isolation
    def scan(*a,**kw):
        result=original(*a,**kw)
        if state['scan']==2: script.write_bytes(b'changed during final scan')
        return result
    monkeypatch.setattr(s,'scan_isolation',scan)
    assert not s.synthesize_script(config,script,run_dir=run).passed


def reviewed_input(run,script):
    from test_speech_semantics import review_for
    from video_ai.runtime.manifest import hash_file,thaw
    path=run/'logs/pipeline/unit-review.json';path.parent.mkdir(parents=True,exist_ok=True)
    review=review_for(script.read_bytes().decode('utf-8-sig'))
    review['script_identity']=thaw(hash_file(script))
    path.write_text(json.dumps(review),encoding='utf-8')
    return path


@pytest.mark.parametrize('refined',[False,True])
def test_shared_manifest_schema2_and_zero_gpu(speech_setup,monkeypatch,refined):
    from video_ai.runtime.manifest import create_manifest,hash_file
    s,run,config,script,state=speech_setup
    if refined:script.write_bytes('红鸟飞过蓝湖。\r\n末尾'.encode('utf-8'))
    review=reviewed_input(run,script)
    if refined:
        from video_ai.planning.segments import TextSpan
        from test_speech_semantics import review_for
        text=script.read_bytes().decode('utf-8')
        subdivided=(TextSpan(0,4,text[:4],'speech','phrase','speech_0001'),TextSpan(4,7,text[4:7],'speech','sentence','speech_0002'),
            TextSpan(7,9,text[7:9],'skip','newline',None),TextSpan(9,11,text[9:11],'speech','end','speech_0003'))
        record=review_for(text,subdivided);record['script_identity']=json.loads(review.read_text(encoding='utf-8'))['script_identity']
        review.write_text(json.dumps(record),encoding='utf-8')
    store=create_manifest(run,config,inputs={'script':hash_file(script)},models={},workflows={})
    store.record_stage('preflight','running');store.record_stage('preflight','completed')
    monkeypatch.setattr(s,'create_manifest',lambda *a,**k:pytest.fail('second manifest'))
    monkeypatch.setattr(s,'ResourceSampler',lambda *a,**k:pytest.fail('GPU sampler'))
    assert s.synthesize_script(config,script,run_dir=run,store=store,segmentation_path=review).passed
    data=json.loads((run/'segments.json').read_text(encoding='utf-8'))
    assert data['schema_version']==2 and data['segmentation_identity']['path']==str(review)
    assert data['execution_policy']==dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300,
        tts_request_timeout_seconds=config.timeouts['tts_request'])
    assert 'resources' not in data
    if refined:assert [text for uid,text in state['calls'] if uid.startswith('speech_')]==['红鸟飞过','蓝湖。','末尾']


def test_bad_unit_review_refuses_before_manifest_or_tts(speech_setup):
    s,run,config,script,state=speech_setup
    path=reviewed_input(run,script);review=json.loads(path.read_text(encoding='utf-8'))
    review['spans'][0]['single_visual_semantics']=False;path.write_text(json.dumps(review),encoding='utf-8')
    with pytest.raises(ValueError):s.synthesize_script(config,script,run_dir=run,segmentation_path=path)
    assert not state['calls'] and not (run/'manifest.json').exists()


def test_shared_store_refuses_orphan_speech(speech_setup):
    from video_ai.runtime.manifest import create_manifest
    s,run,config,script,state=speech_setup
    review=reviewed_input(run,script)
    store=create_manifest(run,config,inputs={},models={},workflows={})
    store.record_stage('preflight','running');store.record_stage('preflight','completed')
    (run/'audio').mkdir();(run/'audio/sentinel').write_bytes(b'foreign')
    with pytest.raises(ValueError):s.synthesize_script(config,script,run_dir=run,store=store,segmentation_path=review)
    assert not state['calls'] and (run/'audio/sentinel').read_bytes()==b'foreign'


def test_partial_speech_resume_consumes_sealed_prefix_without_reposting(speech_setup,monkeypatch):
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,ManifestStore
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import,load_pipeline_import,make_reuse_context
    s,parent,config,script,state=speech_setup
    monkeypatch.setattr(s,'freeze_inputs',lambda cfg,path:(dict(script=hash_file(path),config=hash_file(cfg.config_file),voice=hash_file(cfg.voice.config_file)),{}))
    original=s.atomic_report
    interrupted=False
    def stop_after_first(path,data):
        nonlocal interrupted
        original(path,data)
        if path.name=='segments.json' and not interrupted and any(x.get('unit_id')=='speech_0001' and x.get('status')=='completed' for x in data['spans']):
            interrupted=True;raise KeyboardInterrupt()
    monkeypatch.setattr(s,'atomic_report',stop_after_first)
    with pytest.raises(KeyboardInterrupt):s.synthesize_script(config,script,run_dir=parent)
    monkeypatch.setattr(s,'atomic_report',original)
    snapshot=ManifestStore.open(parent).snapshot()
    child=create_run(RuntimePaths.from_config(config));store=create_manifest(child,config,inputs=snapshot['inputs'],models={},workflows={})
    store.record_stage('preflight','running');store.record_stage('preflight','completed')
    inventory=s.speech_import_inventory(parent,child,partial=True)
    identity=create_pipeline_import(config,run_dir=child,parent_run_dir=parent,reason='TEST ONLY proven unsent suffix',
        source_identities=inventory['source_identities'],copies=inventory['copies'],stages=[inventory['stage']],units=inventory['units'])
    receipt=load_pipeline_import(child)
    unit_ids=('reference_replay','speech_0001','speech_0002','speech_0003')
    identities={k:hash_file(Path(v['path'])) for k,v in store.snapshot()['inputs'].items()}
    context=make_reuse_context(child,stage='speech',unit_ids=unit_ids,current_input_identities=identities)
    report=s.serialize_imported_speech(config,child,source_report=json.loads((parent/'segments.json').read_text(encoding='utf-8')),
        import_identity=identity,reused_units=context.verified_units,copies=receipt['copies'])
    (child/'segments.json').write_text(json.dumps(report),encoding='utf-8')
    for uid in context.verified_units:
        store.record_unit('speech',uid,'running');store.record_unit('speech',uid,'completed',artifacts=[s._artifact(child/'audio'/uid/n) for n in ('raw.wav','pcm-48000.wav')])
    before=list(state['calls'])
    result=s.resume_speech(config,run_dir=child,reuse_context=context,store=store)
    assert result.passed
    assert state['calls'][len(before):]==[('speech_0002','乙。'),('speech_0003','末尾')]
    assert store.snapshot()['units']['speech']['speech_0001']['submission'] is None
    consumed=s.load_committed_speech(child)
    assert consumed['accepted'] is False and len(consumed['audio'])==3


def test_partial_inventory_refuses_unknown_intent(speech_setup):
    from video_ai.runtime.paths import create_run,RuntimePaths
    s,parent,config,script,state=speech_setup
    state['failure']='ambiguous'
    assert not s.synthesize_script(config,script,run_dir=parent).passed
    child=create_run(RuntimePaths.from_config(config))
    with pytest.raises(ValueError):s.speech_import_inventory(parent,child,partial=True)


@pytest.mark.parametrize('bad',['http_body','intent_text'])
def test_committed_speech_replays_original_tts_proof(speech_setup,monkeypatch,bad):
    from video_ai.runtime.manifest import hash_file
    s,run,config,script,state=speech_setup
    monkeypatch.setattr(s,'freeze_inputs',lambda cfg,path:(dict(script=hash_file(path),config=hash_file(cfg.config_file),voice=hash_file(cfg.voice.config_file)),{}))
    assert s.synthesize_script(config,script,run_dir=run).passed
    if bad=='http_body':(run/'logs/speech_0001.body').write_bytes(b'changed HTTP response')
    else:
        path=run/'logs/tts/speech_0001.intent.json';data=json.loads(path.read_text(encoding='utf-8'));data['text']='forged intent'
        path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises((ValueError,OSError)):s.load_committed_speech(run)
