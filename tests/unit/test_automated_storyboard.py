import array
import json
from pathlib import Path
import wave
import pytest
from storyboard_helpers import mock_generation,review_for,write_review


@pytest.fixture
def automatic_run(timeline_run):
    from video_ai.runtime.manifest import hash_file,thaw,now
    from video_ai.runtime.timeline_checks import plan_timeline,_artifact
    run,config,store,data=timeline_run;manifest=store.snapshot()
    for span in data['spans']:
        if span['kind']!='speech':continue
        p=Path(span['pcm']['path'])
        with wave.open(str(p),'wb') as file:
            file.setparams((1,2,48000,0,'NONE',''));file.writeframes(array.array('h',[0]*200+[100]*3600+[0]*1000).tobytes())
        artifact=_artifact(hash_file(p));span['pcm']=artifact;manifest['units']['speech'][span['unit_id']]['artifacts']=[artifact]
    p=run/'segments.json';p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');manifest['stages']['speech']['artifacts']=[_artifact(hash_file(p))]
    (run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    listening=dict(schema_version=1,listened=True,accepted=True,user_statement='Test fixture audio acceptance',accepted_at=now(),
        segments_identity=thaw(hash_file(p)),audio=[{k:s[k] for k in ('unit_id','text','pcm','samples')} for s in data['spans'] if s['kind']=='speech'])
    (run/'voice-listening.json').write_text(json.dumps(listening),encoding='utf-8');assert plan_timeline(config,run_dir=run).passed
    folder=run/'logs/storyboard';folder.mkdir()
    authorization=dict(schema_version=1,run_id=run.name,authority='user_message',scope='delegate_audio_timing',statement='Test user delegates marking after accepting audio',granted_at=now(),
        script_identity=thaw(hash_file(run/'script.txt')),timeline_identity=thaw(hash_file(run/'timeline.json')),voice_listening_identity=thaw(hash_file(run/'voice-listening.json')))
    delegation=folder/'delegation.json';delegation.write_text(json.dumps(authorization),encoding='utf-8')
    return run,config,store,delegation


def test_delegated_signal_record_can_finalize_without_faking_human_audio(automatic_run,monkeypatch):
    from video_ai.runtime.storyboard_checks import create_automated_timing_review,plan_storyboard,finalize_storyboard,load_committed_storyboard
    run,config,store,delegation=automatic_run;mock_generation(monkeypatch)
    reasons={f'speech_{i:04d}':'Fixture agent text review: one consistent scene.' for i in range(1,4)}
    path=create_automated_timing_review(config,run_dir=run,delegation_path=delegation,semantic_reasons=reasons)
    record=json.loads(path.read_text(encoding='utf-8'))
    assert record['review_method']=='automated_audio' and record['human_boundary_reviewed'] is False
    assert record['units'][0]['spoken_start_sample']==200 and record['units'][0]['boundary_uncertainty_samples']==240
    assert plan_storyboard(config,run_dir=run,timing_review_path=path).status=='review_required'
    review=write_review(run,review_for(run));assert finalize_storyboard(config,run_dir=run,review_path=review).passed
    result=load_committed_storyboard(run)
    assert result['timing_basis']['method']=='automated_audio' and result['timing_basis']['human_boundary_reviewed'] is False
    assert result['validation']['actual_video_sync']=='unverified'


@pytest.mark.parametrize('bad',['absent','scope','wrong_run','acceptance','identity','semantic','overwrite','tamper','estimate_type'])
def test_automatic_path_requires_delegation_and_reproducible_evidence(automatic_run,bad):
    from video_ai.runtime.storyboard_checks import create_automated_timing_review,load_timing_review
    from video_ai.runtime.timeline_checks import load_committed_timeline
    run,config,store,delegation=automatic_run;data=json.loads(delegation.read_text(encoding='utf-8'))
    reasons={f'speech_{i:04d}':'Single scene fixture' for i in range(1,4)}
    if bad=='absent':delegation.unlink()
    if bad=='scope':data['scope']='other'
    if bad=='wrong_run':data['run_id']='other'
    if bad=='identity':data['timeline_identity']['sha256']='a'*64
    if bad=='acceptance':(run/'voice-listening.json').write_text('{}')
    if bad=='semantic':reasons.pop('speech_0001')
    if bad!='absent':delegation.write_text(json.dumps(data),encoding='utf-8')
    if bad in ('overwrite','tamper','estimate_type'):
        path=create_automated_timing_review(config,run_dir=run,delegation_path=delegation,semantic_reasons=reasons)
        if bad=='overwrite':
            before=path.read_bytes()
            with pytest.raises(ValueError):create_automated_timing_review(config,run_dir=run,delegation_path=delegation,semantic_reasons=reasons)
            assert path.read_bytes()==before
        else:
            record=json.loads(path.read_text(encoding='utf-8'))
            if bad=='estimate_type':
                from video_ai.runtime.manifest import hash_file,thaw
                note=Path(record['units'][0]['evidence_identity']['path'])
                analysis=json.loads(note.read_text(encoding='utf-8'));analysis['units'][0]['estimate']['schema_version']=True
                note.write_text(json.dumps(analysis),encoding='utf-8')
                for unit in record['units']:unit['evidence_identity']=thaw(hash_file(note))
            else:record['units'][0]['spoken_start_sample']+=1
            path.write_text(json.dumps(record),encoding='utf-8')
            with pytest.raises(ValueError):load_timing_review(run,path,load_committed_timeline(run))
    else:
        with pytest.raises((ValueError,OSError)):create_automated_timing_review(config,run_dir=run,delegation_path=delegation,semantic_reasons=reasons)
        assert not (run/'logs/storyboard/timing-review.json').exists()
