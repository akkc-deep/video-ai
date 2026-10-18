import json
from pathlib import Path
import pytest
from unit.test_speech_semantics import review_for
from unit.test_automated_storyboard import automatic_run
from unit.test_storyboard_import import imported


def test_unit_review_binds_source_identity_and_detects_mtime(runtime_run):
    from video_ai.runtime import pipeline_reviews as p
    from video_ai.runtime.manifest import hash_file,thaw
    run,config,paths=runtime_run
    script=run/'original.txt';script.write_text('红鸟飞过蓝湖。',encoding='utf-8')
    path=run/'unit-review.json';review=review_for(script.read_text(encoding='utf-8'))
    review['script_identity']=thaw(hash_file(script));path.write_text(json.dumps(review),encoding='utf-8')
    loaded=p.load_unit_review(path,script_path=script)
    assert loaded.script.text==script.read_text(encoding='utf-8')
    import os
    os.utime(script,ns=(script.stat().st_atime_ns,script.stat().st_mtime_ns+1000000))
    with pytest.raises(OSError):p.load_unit_review(path,script_path=script)


@pytest.mark.parametrize('bad',[None,'unknown','duplicate','foreign','future','mtime','identity_future','canonical_source'])
def test_review_index_exact_roles_and_fresh_identities(runtime_run,bad):
    from video_ai.runtime import pipeline_reviews as p
    from video_ai.runtime.manifest import hash_file,thaw,now
    run,config,paths=runtime_run
    folder=run/'logs/pipeline';folder.mkdir(parents=True)
    author=run/'logs/author.json';author.write_text('{}',encoding='utf-8')
    path=folder/'reviews.json';record=dict(schema_version=1,run_id=run.name,created_at=now(),entries={'voice_acceptance':thaw(hash_file(author))})
    if bad=='unknown':record['entries']['unknown']=record['entries']['voice_acceptance']
    if bad=='duplicate':record['entries']['timing']=record['entries']['voice_acceptance']
    if bad=='foreign':record['run_id']='other'
    if bad=='future':record['created_at']='2999-01-01T00:00:00+00:00'
    if bad=='mtime':record['entries']['voice_acceptance']['mtime_ns']+=1
    if bad=='identity_future':record['entries']['voice_acceptance']['verified_at']='2999-01-01T00:00:00+00:00'
    if bad=='canonical_source':record['entries']={'source_clips':record['entries']['voice_acceptance']}
    path.write_text(json.dumps(record),encoding='utf-8')
    if bad is None:assert p.load_reviews(run,path)=={'voice_acceptance':author}
    else:
        with pytest.raises((OSError,ValueError)):p.load_reviews(run,path)


def complete_voice_fixture(timeline_run):
    import wave
    from video_ai.runtime.manifest import hash_file,thaw,now
    from video_ai.runtime.speech_checks import _artifact
    from test_timeline_checks import rewrite_segments
    run,config,store,data=timeline_run
    for item in data['spans']:
        if item['kind']=='speech':
            raw=Path(item['pcm']['path']).with_name('raw.wav');raw.write_bytes(Path(item['pcm']['path']).read_bytes())
            item['raw']=_artifact(raw)
            unit=store.snapshot()['units']['speech'][item['unit_id']]
            # This fixture supplements the existing real speech run with raw artifacts.
            snapshot=store.snapshot();snapshot['units']['speech'][item['unit_id']]['artifacts'].append(item['raw'])
            (run/'manifest.json').write_text(json.dumps(snapshot),encoding='utf-8')
    folder=run/'audio/reference_replay';folder.mkdir()
    pcm=folder/'pcm-48000.wav';pcm.write_bytes(Path(data['spans'][0]['pcm']['path']).read_bytes())
    raw=folder/'raw.wav';raw.write_bytes(pcm.read_bytes())
    data['reference_replay']=dict(unit_id='reference_replay',status='completed',text=config.voice.reference_text,
        raw=_artifact(raw),pcm=_artifact(pcm),samples=4800,sample_rate=48000,channels=1,sample_width=2)
    store.record_unit('speech','reference_replay','running');store.record_unit('speech','reference_replay','completed',
        artifacts=[_artifact(raw),_artifact(pcm)])
    preview=run/'audio/listening-preview.wav'
    with wave.open(str(preview),'wb') as f:
        f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\0\0'*14400)
    data['listening_preview']=dict(identity=_artifact(preview),samples=14400,sample_rate=48000,preview_only=True)
    rewrite_segments(run,store,data)
    record=dict(schema_version=1,run_id=run.name,segments_identity=thaw(hash_file(run/'segments.json')),
        reference_identity=thaw(hash_file(pcm)),preview_identity=thaw(hash_file(preview)),
        audio_identities=[dict(unit_id=s['unit_id'],text=s['text'],raw=thaw(hash_file(Path(s['raw']['path']))),
            pcm=thaw(hash_file(Path(s['pcm']['path']))),samples=s['samples']) for s in data['spans'] if s['kind']=='speech'],
        review_method='human_audio',reviewer='TEST ONLY listener',reviewed_at=now(),listened=True,accepted=True,
        user_statement='TEST ONLY all current audio listened and accepted')
    author=run/'logs/pipeline/voice-review.json';author.parent.mkdir(parents=True);author.write_text(json.dumps(record),encoding='utf-8')
    return run,config,store,data,author,record


@pytest.mark.parametrize('bad',[None,'method','flag','text','samples','order','reference','preview','future','extra'])
def test_voice_acceptance_is_exact_and_never_rewrites_false_listening(timeline_run,bad):
    from video_ai.runtime import pipeline_reviews as p
    from video_ai.runtime.speech_checks import load_committed_speech
    run,config,store,data,path,record=complete_voice_fixture(timeline_run)
    false=run/'voice-listening.json';false.write_text(json.dumps(dict(schema_version=1,listened=False,accepted=False,
        audio=[{k:s[k] for k in ('unit_id','text','pcm','samples')} for s in data['spans'] if s['kind']=='speech'])),encoding='utf-8')
    before=false.read_bytes()
    if bad=='method':record['review_method']='agent_audio'
    if bad=='flag':record['listened']=1
    if bad=='text':record['audio_identities'][0]['text']='different'
    if bad=='samples':record['audio_identities'][0]['samples']+=1
    if bad=='order':record['audio_identities'].reverse()
    if bad=='reference':record['reference_identity']=record['preview_identity']
    if bad=='preview':record['preview_identity']['sha256']='a'*64
    if bad=='future':record['reviewed_at']='2999-01-01T00:00:00+00:00'
    if bad=='extra':record['verdict']='passed'
    path.write_text(json.dumps(record),encoding='utf-8')
    if bad is None:
        receipt=p.accept_voice_review(config,run,path)
        assert Path(receipt.path)!=path and store.snapshot()['workflows']['voice_acceptance']['path']==receipt.path
        assert load_committed_speech(run)['accepted'] is True
        from video_ai.runtime.timeline_checks import plan_timeline
        assert plan_timeline(config,run_dir=run).listening_accepted is True
    else:
        with pytest.raises((OSError,ValueError)):p.accept_voice_review(config,run,path)
        assert 'voice_acceptance' not in store.snapshot()['workflows']
    assert false.read_bytes()==before


def test_imported_speech_retains_real_origin_and_rechecks_parent_leaf(timeline_run):
    from video_ai.runtime import speech_checks as s
    from video_ai.runtime.pipeline_import import create_pipeline_import,load_pipeline_import
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw
    run,config,store,data,path,record=complete_voice_fixture(timeline_run)
    child=create_run(RuntimePaths.from_config(config))
    target=create_manifest(child,config,inputs=store.snapshot()['inputs'],models={},workflows={})
    inventory=s.speech_import_inventory(run,child)
    identity=create_pipeline_import(config,run_dir=child,parent_run_dir=run,reason='TEST ONLY audio reuse',
        source_identities=inventory['source_identities'],copies=inventory['copies'],stages=[inventory['stage']],units=inventory['units'])
    receipt=load_pipeline_import(child)
    reused={row['id']:dict(origin_run_id=row['imported_record']['origin_run_id'],source_report_identity=row['imported_record']['source_report_identity'],
        source_unit_id=row['imported_record']['source_unit_id'],signature=row['signature'],import_identity=thaw(identity)) for row in receipt['units']}
    report=s.serialize_imported_speech(config,child,source_report=data,import_identity=identity,reused_units=reused,copies=receipt['copies'])
    (child/'segments.json').write_text(json.dumps(report),encoding='utf-8')
    target.record_stage('speech','running')
    for uid in reused:
        artifacts=[s._artifact(child/'audio'/uid/name) for name in ('raw.wav','pcm-48000.wav')]
        target.record_unit('speech',uid,'running');target.record_unit('speech',uid,'completed',artifacts=artifacts)
    target.record_stage('speech','completed',artifacts=[s._artifact(child/'segments.json')])
    loaded=s.load_committed_speech(child)
    assert set(loaded['report']['reused_units'])==set(reused)
    assert all(u['submission'] is None for u in target.snapshot()['units']['speech'].values())
    pcm=Path(data['spans'][0]['pcm']['path']);raw=bytearray(pcm.read_bytes());raw[-1]=1;pcm.write_bytes(raw)
    with pytest.raises((OSError,ValueError)):s.load_committed_speech(child)


def test_schema1_speech_import_policy_uses_original_request_timeout(timeline_run):
    from video_ai.runtime import speech_checks as s
    from video_ai.runtime.pipeline_import import create_pipeline_import,load_pipeline_import
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw
    from video_ai.config import load_config
    run,config,store,data,path,record=complete_voice_fixture(timeline_run)
    child=create_run(RuntimePaths.from_config(config))
    raw=thaw(config.raw);raw.update(voice_config=str(config.voice.config_file),workflows={k:str(v) for k,v in config.workflows.items()})
    raw['timeouts']=dict(config.timeouts,tts_request=config.timeouts['tts_request']+17)
    current=child/'TEST-ONLY-config.json';current.write_text(json.dumps(raw),encoding='utf-8');revised=load_config(current)
    create_manifest(child,revised,inputs=dict(config=hash_file(current),voice=hash_file(revised.voice.config_file)),models={},workflows={})
    inventory=s.speech_import_inventory(run,child)
    identity=create_pipeline_import(revised,run_dir=child,parent_run_dir=run,reason='TEST ONLY original timeout',
        source_identities=inventory['source_identities'],copies=inventory['copies'],stages=[inventory['stage']],units=inventory['units'])
    receipt=load_pipeline_import(child)
    reused={row['id']:dict(origin_run_id=row['imported_record']['origin_run_id'],source_report_identity=row['imported_record']['source_report_identity'],
        source_unit_id=row['imported_record']['source_unit_id'],signature=row['signature'],import_identity=thaw(identity)) for row in receipt['units']}
    report=s.serialize_imported_speech(revised,child,source_report=data,import_identity=identity,reused_units=reused,copies=receipt['copies'])
    assert report['execution_policy']['tts_request_timeout_seconds']==config.timeouts['tts_request']


def test_legacy_speech_import_keeps_original_acceptance_fresh(imported):
    run,parent,store,config=legacy_speech_run(imported)
    from video_ai.runtime.speech_checks import load_committed_speech
    assert load_committed_speech(run)['accepted'] is True
    with (parent/'voice-listening.json').open('a',encoding='utf-8') as f:f.write(' ')
    with pytest.raises((OSError,ValueError)):load_committed_speech(run)


def legacy_speech_run(imported):
    from video_ai.runtime.manifest import ManifestStore,create_manifest,hash_file,thaw
    from video_ai.config import load_config
    from video_ai.runtime.speech_checks import load_committed_speech,_artifact
    run,parent,segments=imported
    original=ManifestStore.open(parent).snapshot();config=load_config(Path(original['config_snapshot']['path']))
    store=create_manifest(run,config,inputs=original['inputs'],models={},workflows={})
    segments.update(run_dir=str(run),script_copy=thaw(hash_file(run/'script.txt')))
    store.record_stage('speech','running')
    for span in segments['spans']:
        if span['kind']=='skip':continue
        span['pcm']=_artifact(run/'audio'/span['unit_id']/'pcm-48000.wav')
        store.record_unit('speech',span['unit_id'],'running');store.record_unit('speech',span['unit_id'],'completed',artifacts=[span['pcm']])
    (run/'segments.json').write_text(json.dumps(segments),encoding='utf-8')
    store.record_stage('speech','completed',artifacts=[_artifact(run/'segments.json')])
    listening=json.loads((run/'voice-listening.json').read_text(encoding='utf-8'));listening['segments_identity']=thaw(hash_file(run/'segments.json'))
    (run/'voice-listening.json').write_text(json.dumps(listening),encoding='utf-8')
    return run,parent,store,config


def test_schema2_speech_replays_legacy_receipt_at_actual_origin(imported):
    from video_ai.runtime import speech_checks as s,storyboard_checks as sc
    from video_ai.runtime.pipeline_import import create_pipeline_import,load_pipeline_import,make_reuse_context,fresh
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import create_manifest,thaw
    legacy,original,source_store,config=legacy_speech_run(imported)
    child=create_run(RuntimePaths.from_config(config));store=create_manifest(child,config,inputs=source_store.snapshot()['inputs'],models={},workflows={})
    inventory=s.speech_import_inventory(legacy,child)
    identity=create_pipeline_import(config,run_dir=child,parent_run_dir=legacy,reason='TEST ONLY real older receipt origin',
        source_identities=inventory['source_identities'],copies=inventory['copies'],stages=[inventory['stage']],units=inventory['units'])
    receipt=load_pipeline_import(child)
    context=make_reuse_context(child,stage='speech',unit_ids=('speech_0001','speech_0002','speech_0003'),
        current_input_identities={k:fresh(v) for k,v in store.snapshot()['inputs'].items()})
    report=s.serialize_imported_speech(config,child,source_report=s.load_committed_speech(legacy)['report'],import_identity=identity,
        reused_units=context.verified_units,copies=receipt['copies'])
    (child/'segments.json').write_text(json.dumps(report),encoding='utf-8');store.record_stage('speech','running')
    for uid in context.verified_units:
        pcm=s._artifact(child/'audio'/uid/'pcm-48000.wav');store.record_unit('speech',uid,'running');store.record_unit('speech',uid,'completed',artifacts=[pcm])
    store.record_stage('speech','completed',artifacts=[s._artifact(child/'segments.json')])
    sc._verify_import(child,report)
    with (original/'voice-listening.json').open('a',encoding='utf-8') as f:f.write(' ')
    with pytest.raises((OSError,ValueError)):sc._verify_import(child,report)
