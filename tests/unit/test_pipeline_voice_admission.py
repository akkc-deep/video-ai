"""TEST ONLY immutable VAI04 baseline and author-bound current inference inputs."""
from dataclasses import replace
from pathlib import Path
import json
import os
import wave
import pytest

from source_clip_helpers import write


def fixture(runtime_run,monkeypatch,*,model=False,reference=True,sealed=True,malformed=None,script_text='Original words.',baseline=False):
    from video_ai.config import load_config
    from video_ai.runtime import speech_checks as s
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import
    parent,original,_=runtime_run
    project=parent/'TEST-ONLY-project';project.mkdir()
    voice=thaw(original.voice.raw)
    leaves=[]
    for name in ('gpt_weights','sovits_weights','bert_root','hubert_root'):
        path=project/name
        if name.endswith('_root'):
            path.mkdir();path=path/'leaf.bin'
        path.write_bytes(('TEST ONLY '+name).encode());leaves.append(path)
        voice[name]=str(path.parent if name.endswith('_root') else path)
    ref=project/'reference.wav'
    with wave.open(str(ref),'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\0\0'*4800)
    leaves.append(ref);voice.update(reference_audio=str(ref),reference_sha256=hash_file(ref).sha256)
    old_voice=write(project/'voice-original.json',voice)
    raw=thaw(original.raw);raw.update(voice_config=str(old_voice),workflows={k:str(v) for k,v in original.workflows.items()})
    raw['services']['ollama']='http://127.0.0.1:11435'
    old=load_config(write(project/'config-original.json',raw))
    installed=dict(custom=dict(version='v2',device='cpu',is_half=False,
        t2s_weights_path=voice['gpt_weights'],vits_weights_path=voice['sovits_weights'],
        bert_base_path=voice['bert_root'],cnhuhbert_base_path=voice['hubert_root']),default={'keep':'fixed'})
    installed.update({version:dict(installed['custom'],version=version) for version in ('v1','v2','v3','v4','v2Pro','v2ProPlus')})
    yaml=write(project/'config/tts-api.yaml',installed)
    script=parent/'TEST-ONLY-script.txt';script.write_text(script_text,encoding='utf-8')
    old_ids={n:hash_file(p) for n,p in dict(config=old.config_file,voice=old_voice,tts_yaml=yaml,script=script).items()}
    old_store=create_manifest(parent,old,inputs=old_ids,models={},workflows={})
    acceptance=write(project/'acceptance.json',dict(passed=True,components={'tts':{'status':'passed'}},
        voice_sha256=hash_file(old_voice).sha256,tts_config_sha256=hash_file(yaml).sha256))
    root=project/'baseline';write(root/'docs/video-ai/VAI-04-evidence/verification.json',dict(task='VAI-04',passed=True,
        acceptance=thaw(hash_file(acceptance))))
    inv=project/'inventory';write(inv/'files.json',[dict(target=str(p),source=str(p),sha256=hash_file(p).sha256) for p in leaves])
    monkeypatch.setattr(s,'RUNTIME_ROOT',root);monkeypatch.setattr(s,'INVENTORY',inv);monkeypatch.setattr(s,'ROOTS',())
    if baseline:
        command=s.audio_command
        monkeypatch.setattr(s,'audio_command',lambda args,**kwargs:command(args,**dict(kwargs,paths=RuntimePaths.from_config(old))))
        return s,parent,parent,replace(old,project_root=project),script,yaml
    voice.update(speed_factor=1.2,reference_text='TEST ONLY changed reference words')
    voice['inference']=dict(voice['inference'],top_k=9,temperature=.8)
    if reference:
        new_ref=project/'revised-reference.wav';data=ref.read_bytes()
        new_ref.write_bytes(data[:-2] if malformed=='truncated' else b'NOT WAV' if malformed=='not_wav' else data)
        voice.update(reference_audio=str(new_ref),reference_sha256=hash_file(new_ref).sha256)
    if model:
        new_model=project/'revised-gpt.ckpt';new_model.write_bytes(b'TEST ONLY revised voice model');voice['gpt_weights']=str(new_model)
    new_voice=write(project/'voice-current.json',voice);raw['voice_config']=str(new_voice)
    current=load_config(write(project/'config-current.json',raw))
    child=create_run(RuntimePaths.from_config(original))
    create_manifest(child,current,inputs={n:hash_file(p) for n,p in dict(config=current.config_file,voice=new_voice,script=script).items()},models={},workflows={})
    base=write(parent/'logs/pipeline/TEST-ONLY-base.json',old_store.snapshot())
    changes=write(parent/'logs/pipeline/TEST-ONLY-changes.json',dict(schema_version=1,base_run_id=parent.name,
        base_manifest_snapshot_identity=thaw(hash_file(base)),created_at=now(),reason='TEST ONLY revised voice',
        script_identity=None,unit_review_identity=None,config_identity=thaw(hash_file(current.config_file)),shot_changes=[]))
    files=[current.voice.gpt_weights,current.voice.sovits_weights,current.voice.reference_audio,
        *current.voice.bert_root.rglob('*'),*current.voice.hubert_root.rglob('*')]
    create_pipeline_import(current,run_dir=child,parent_run_dir=parent,reason='TEST ONLY revision',
        changes_identity=hash_file(changes) if sealed else None,copies=[],
        source_identities={str(p):thaw(hash_file(p)) for p in files if p.is_file()})
    command=s.audio_command
    monkeypatch.setattr(s,'audio_command',lambda args,**kwargs:command(args,**dict(kwargs,paths=RuntimePaths.from_config(current))))
    # Substitute only the installed YAML lookup boundary; immutable run snapshots
    # retain the real canonical project root and full loaded config identity.
    return s,parent,child,replace(current,project_root=project),script,yaml


@pytest.mark.parametrize('model',[False,True])
def test_real_freeze_admits_author_bound_voice_and_actual_payload(runtime_run,monkeypatch,model):
    from video_ai.runtime._pipeline_voice_admission import voice_revision,verify_reused_voice
    from video_ai.adapters.tts import TtsClient
    s,parent,child,c,script,yaml=fixture(runtime_run,monkeypatch,model=model)
    revision=voice_revision(c,child,script)
    inputs,models=s.freeze_inputs(c,script,revision_context=revision)
    payload=TtsClient(None,c.voice).payload('Original words.')
    assert payload['speed_factor']==1.2 and payload['prompt_text']==c.voice.reference_text
    assert payload['ref_audio_path']==str(c.voice.reference_audio) and payload['top_k']==9 and payload['temperature']==.8
    assert models['gpt_weights'].path==str(c.voice.gpt_weights) and inputs['voice_revision_baseline'].path!=str(c.voice.config_file)
    with pytest.raises(ValueError):verify_reused_voice(c,parent,{})
    with pytest.raises((ValueError,OSError)):s.freeze_inputs(c,script)
    c.voice.gpt_weights.write_bytes(b'TEST ONLY post-admission mutation')
    with pytest.raises((ValueError,OSError)):s.freeze_inputs(c,script,revision_context=revision)


@pytest.mark.parametrize('bad',['unsealed','truncated','not_wav'])
def test_revision_refuses_unsealed_or_incomplete_reference(runtime_run,monkeypatch,bad):
    from video_ai.runtime._pipeline_voice_admission import voice_revision
    s,parent,child,c,script,yaml=fixture(runtime_run,monkeypatch,sealed=bad!='unsealed',malformed=bad)
    revision=voice_revision(c,child,script)
    with pytest.raises((ValueError,OSError)):s.freeze_inputs(c,script,revision_context=revision)


def test_unchanged_revised_voice_inherits_original_authorization_for_new_requests(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_voice_admission import voice_revision
    from video_ai.runtime.manifest import ManifestStore,create_manifest,hash_file,thaw
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import
    from video_ai.config import load_config
    s,parent,child,c,script,yaml=fixture(runtime_run,monkeypatch,model=True)
    revision=voice_revision(c,child,script);inputs,models=s.freeze_inputs(c,script,revision_context=revision)
    store=ManifestStore.open(child);store.update(lambda d:(d['inputs'].update(thaw(inputs)),d['models'].update(thaw(models))))
    current=load_config(c.config_file);grandchild=create_run(RuntimePaths.from_config(current))
    create_manifest(grandchild,current,inputs=store.snapshot()['inputs'],models=store.snapshot()['models'],workflows={})
    sources={str(record['path']):record for record in [*store.snapshot()['inputs'].values(),*store.snapshot()['models'].values()]}
    create_pipeline_import(current,run_dir=grandchild,parent_run_dir=child,reason='TEST ONLY unchanged voice resume',copies=[],source_identities=sources)
    inherited=voice_revision(c,grandchild,script)
    assert inherited is not None and (inherited.changes_identity.path,inherited.changes_identity.sha256)==(revision.changes_identity.path,revision.changes_identity.sha256)
    assert s.freeze_inputs(c,script,revision_context=inherited)[1]['gpt_weights'].sha256==models['gpt_weights'].sha256


def test_model_revision_creates_owned_runtime_config_without_touching_baseline(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_voice_admission import voice_revision
    from video_ai.runtime.logging import RunLogger
    from video_ai.config import read_json
    s,parent,child,c,script,yaml=fixture(runtime_run,monkeypatch,model=True)
    original=yaml.read_bytes();logger=RunLogger(child)
    path=s.validate_voice_startup(c,paths=s.RuntimePaths.from_config(c),logger=logger,revision_context=voice_revision(c,child,script))
    assert path.suffix=='.yaml'
    data=read_json(child/'logs/voice-runtime-serialization.json')['configuration']
    assert path.is_relative_to(child) and path!=yaml and data['custom']['t2s_weights_path']==str(c.voice.gpt_weights)
    assert data['custom']['device']=='cpu' and data['custom']['version']=='v2' and data['default']=={'keep':'fixed'}
    assert yaml.read_bytes()==original
    before=path.read_bytes()
    # Installed GPT-SoVITS init_t2s_weights/init_vits_weights call exactly this
    # yaml.dump/save operation. Exercise its real bundled serializer, no models.
    s.audio_command((c.tools['tts_python'],'-B','-c',
        'import yaml,sys; p=sys.argv[1]; d=yaml.load(open(p,encoding="utf-8"),Loader=yaml.FullLoader); yaml.dump(d,open(p,"w"))',path),
        paths=s.RuntimePaths.from_config(c),logger=logger,unit_id='voice_normalization',timeout=30)
    assert path.read_bytes()==before


def test_real_revised_tts_posts_current_payload_and_waits_for_new_listening(runtime_run,monkeypatch):
    from types import SimpleNamespace
    from io import BytesIO
    from video_ai.runtime.manifest import ManifestStore,hash_file
    from video_ai.runtime.services import ServiceSpec
    from video_ai.media.audio import AudioInfo
    from video_ai.config import read_json
    from http_helpers import Response,ScriptedTransport
    from unit.test_speech_checks import reviewed_input
    s,parent,child,c,script,yaml=fixture(runtime_run,monkeypatch,model=True)
    original=yaml.read_bytes();store=ManifestStore.open(child)
    store.record_stage('preflight','running');store.record_stage('preflight','completed')
    review=reviewed_input(child,script)
    events=[]
    class Manager:
        def __init__(self,*args):pass
        def ensure(self,spec):
            path=Path(spec.args[spec.args.index('-c')+1]);events.append(('start',path))
            assert path.suffix=='.yaml'
            assert read_json(child/'logs/voice-runtime-serialization.json')['configuration']['custom']['t2s_weights_path']==str(c.voice.gpt_weights)
            before=path.stat().st_mtime_ns
            s.audio_command((c.tools['tts_python'],'-B','-c',
                'import yaml,sys; p=sys.argv[1]; d=yaml.load(open(p,encoding="utf-8"),Loader=yaml.FullLoader); yaml.dump(d,open(p,"w"))',path),
                paths=s.RuntimePaths.from_config(c),logger=s.RunLogger(child),unit_id='voice_startup_rewrite',timeout=30)
            assert path.stat().st_mtime_ns!=before
            return SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:None))
        def stop(self,handle):events.append(('stop',None))
    monkeypatch.setattr(s,'ServiceManager',Manager)
    spec=ServiceSpec('tts',c.services['tts'],('TEST ONLY never launched','-c',str(yaml)),c.project_root,30)
    monkeypatch.setattr(s,'build_service_specs',lambda *args:{'tts':spec})
    monkeypatch.setattr(s,'scan_isolation',lambda *args,**kwargs:{})
    monkeypatch.setattr(s,'validate_fixed_voice_log',lambda *args:None)
    monkeypatch.setattr(s,'service_log',lambda *args:'TEST ONLY no process')
    body=BytesIO()
    with wave.open(body,'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\0\0'*4800)
    transport=ScriptedTransport(lambda request,timeout:Response(body.getvalue(),headers={'Content-Type':'audio/wav'}))
    http=s.HttpClient
    monkeypatch.setattr(s,'HttpClient',lambda *args:http(*args,transport=transport))
    def standardize(raw,target,**kwargs):
        target.write_bytes(raw.read_bytes());identity=hash_file(target)
        return AudioInfo(target,identity.sha256,identity.bytes,48000,1,2,4800)
    monkeypatch.setattr(s,'standardize_wav',standardize)
    result=s.synthesize_script(c,script,run_dir=child,store=store,segmentation_path=review)
    assert result.passed,read_json(child/'segments.json').get('error')
    assert result.listened is False and read_json(child/'voice-listening.json')['accepted'] is False
    speech=[r for r in read_json(child/'segments.json')['spans'] if r['kind']=='speech']
    assert len(transport.calls)==1+len(speech) and all(call[0]=='POST' for call in transport.calls)
    for call in transport.calls:
        payload=json.loads(call[2]);assert payload['speed_factor']==1.2 and payload['top_k']==9
        assert payload['ref_audio_path']==str(c.voice.reference_audio) and payload['prompt_text']==c.voice.reference_text
    assert [e[0] for e in events]==['start','stop'] and events[0][1].is_relative_to(child)
    assert yaml.read_bytes()==original and s.load_committed_speech(child)['accepted'] is False
    startup=read_json(child/'logs/voice-runtime-startup.json')
    assert startup['before']['mtime_ns']!=startup['after_identity']['mtime_ns'] and startup['owned'] is True
    assert startup['before']['sha256']==startup['after_identity']['sha256']
    # A subsequent full import retains the original run-local service proof.
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import create_manifest,thaw
    from video_ai.runtime.pipeline_import import create_pipeline_import,load_pipeline_import
    from video_ai.config import load_config
    current=load_config(c.config_file);grandchild=create_run(RuntimePaths.from_config(current))
    grandstore=create_manifest(grandchild,current,inputs=store.snapshot()['inputs'],models=store.snapshot()['models'],workflows={})
    inventory=s.speech_import_inventory(child,grandchild)
    imported=create_pipeline_import(current,run_dir=grandchild,parent_run_dir=child,reason='TEST ONLY revised speech proof reuse',
        source_identities=inventory['source_identities'],copies=inventory['copies'],stages=[inventory['stage']],units=inventory['units'])
    receipt=load_pipeline_import(grandchild)
    reused={row['id']:dict(origin_run_id=row['imported_record']['origin_run_id'],source_report_identity=row['imported_record']['source_report_identity'],
        source_unit_id=row['imported_record']['source_unit_id'],signature=row['signature'],import_identity=thaw(imported)) for row in receipt['units']}
    report=s.serialize_imported_speech(current,grandchild,source_report=read_json(child/'segments.json'),import_identity=imported,
        reused_units=reused,copies=receipt['copies'])
    write(grandchild/'segments.json',report);grandstore.record_stage('speech','running')
    for uid in reused:
        grandstore.record_unit('speech',uid,'running');grandstore.record_unit('speech',uid,'completed',
            artifacts=[s._artifact(grandchild/'audio'/uid/name) for name in ('raw.wav','pcm-48000.wav')])
    grandstore.record_stage('speech','completed',artifacts=[s._artifact(grandchild/'segments.json')])
    assert s.load_committed_speech(grandchild)['accepted'] is False
    runtime=Path(store.snapshot()['inputs']['tts_runtime']['path']);stat=runtime.stat()
    os.utime(runtime,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000))
    with pytest.raises(OSError):s.load_committed_speech(child)
    from video_ai.runtime.manifest import FileIdentity
    with pytest.raises(OSError):s.revalidate_identities({'tts_runtime':FileIdentity(**store.snapshot()['inputs']['tts_runtime'])})
