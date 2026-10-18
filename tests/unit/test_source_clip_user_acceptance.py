from copy import deepcopy
import json
import os
from pathlib import Path
import pytest

from source_clip_helpers import setup,review,user_acceptance,write


def test_user_acceptance_commits_with_honest_flags_no_observations_and_fresh_consumer(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import hash_file,thaw
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    original_draft=(f.run/'source-clips-draft.json').read_bytes()
    before=set((f.run/'logs/source-clips').glob('*'));path,_=user_acceptance(f.run)
    assert f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    report=f.sc.load_committed_source_clips(f.run)
    assert report['validation']==dict(structure_passed=True,media_passed=True,video_text_semantics_passed=False,
        motion_semantics_passed=False,ready_for_upscale=True,final_video_sync='unverified',full_film_acceptance='unverified')
    assert (f.run/'source-clips-draft.json').read_bytes()==original_draft
    assert set((f.run/'logs/source-clips').glob('*'))-before=={path}
    assert not (f.run/'logs/source-clips/test-video-observation.json').exists()
    f.store.record_stage('upscale','running')
    assert f.sc.load_committed_source_clips(f.run)['passed']
    for target in (f.run/'shots/shot_0001/source.mp4',path):
        raw=target.read_bytes();stamp=target.stat().st_mtime_ns
        target.write_bytes(raw+b'changed')
        try:
            with pytest.raises((ValueError,OSError)):f.sc.load_committed_source_clips(f.run)
        finally:target.write_bytes(raw);os.utime(target,ns=(stamp,stamp))
    # Refresh all report receipts so rejection proves method-derived semantics,
    # rather than merely detecting a stale report hash.
    report['validation']['video_text_semantics_passed']=True
    write(f.run/'source-clips.json',report);identity=thaw(hash_file(f.run/'source-clips.json'))
    manifest=f.store.snapshot();manifest['workflows']['source_clips_report']=identity
    for record in [manifest['stages']['source_clips'],*manifest['units']['shot'].values()]:
        for artifact in record['artifacts']:
            if Path(artifact['path'])==f.run/'source-clips.json':
                for key in ('bytes','sha256','verified_at'):artifact[key]=identity[key]
    write(f.run/'manifest.json',manifest)
    with pytest.raises(ValueError):f.sc.load_committed_source_clips(f.run)


def test_user_acceptance_receipt_strict_header_and_all13_binding_rejections(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import hash_file
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    path,original=user_acceptance(f.run);draft=json.loads((f.run/'source-clips-draft.json').read_text(encoding='utf-8'))
    assert f.sc.review(f.run,path,draft,hash_file(f.run/'source-clips-draft.json'))
    for bad in ('schema_bool','schema_float','accepted_int','accepted_string','accepted_false','scope','checks_order','checks_missing',
        'reviewer','text','timestamp','future','run','draft','upstream','missing','extra','reorder','association','source','range','bool','verdict','unknown'):
        data=deepcopy(original)
        if bad=='schema_bool':data['schema_version']=True
        if bad=='schema_float':data['schema_version']=1.0
        if bad=='accepted_int':data['accepted']=1
        if bad=='accepted_string':data['accepted']='true'
        if bad=='accepted_false':data['accepted']=False
        if bad=='scope':data['acceptance_scope']='full_film'
        if bad=='checks_order':data['unverified_checks'].reverse()
        if bad=='checks_missing':data['unverified_checks'].pop()
        if bad=='reviewer':data['reviewer']=' '
        if bad=='text':data['acceptance_text']=''
        if bad=='timestamp':data['reviewed_at']='2000-01-01T00:00:00+00:00'
        if bad=='future':data['reviewed_at']='2099-01-01T00:00:00+00:00'
        if bad=='run':data['run_id']='wrong'
        if bad=='draft':data['draft_identity']['sha256']='a'*64
        if bad=='upstream':data['images_identity']['sha256']='a'*64
        if bad=='missing':data['entries'].pop()
        if bad=='extra':data['entries'].append(deepcopy(data['entries'][0]))
        if bad=='reorder':data['entries'].reverse()
        if bad=='association':data['entries'][0]['clip_shot_id']='shot_0002'
        if bad=='source':data['entries'][0]['actual_artifact']['sha256']='a'*64
        if bad=='range':data['entries'][0]['local_frames']['end']=3
        if bad=='bool':data['entries'][0]['requirement_index']=False
        if bad=='verdict':data['entries'][0]['verdict']='passed'
        if bad=='unknown':data['global_verdict']='passed'
        write(path,data)
        with pytest.raises((ValueError,OSError)):f.sc.review(f.run,path,draft,hash_file(f.run/'source-clips-draft.json'))


def test_user_acceptance_freshly_binds_each_actual_source(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import hash_file
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    path,_=user_acceptance(f.run);draft=json.loads((f.run/'source-clips-draft.json').read_text(encoding='utf-8'))
    target=f.run/'shots/shot_0007/source.mp4';stamp=target.stat().st_mtime_ns
    os.utime(target,ns=(stamp,stamp+10_000_000))
    with pytest.raises(OSError):f.sc.review(f.run,path,draft,hash_file(f.run/'source-clips-draft.json'))
    assert not (f.run/'source-clips.json').exists()


def test_user_acceptance_cannot_bypass_rehashed_bad_media_commands(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime.timeline_checks import _artifact
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    draft_path=f.run/'source-clips-draft.json';draft=json.loads(draft_path.read_text(encoding='utf-8'))
    name=next(n for n in draft['clips'][0]['evidence_identities'] if '/video-' in n)
    record=json.loads((f.run/name).read_text(encoding='utf-8'));record['commands'][2]['args'].remove('-xerror')
    write(f.run/name,record);draft['request_evidence'][name]=thaw(hash_file(f.run/name));write(draft_path,draft)
    f.store.record_stage('source_clips','running',artifacts=[_artifact(hash_file(draft_path))])
    path,_=user_acceptance(f.run)
    result=f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path)
    assert result.status=='failed' and not result.ready_for_upscale and result.clip_count==7
    assert not (f.run/'source-clips.json').exists()


def test_original_human_agent_review_still_needs_process_and_continuity(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import hash_file,thaw
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    path,original=review(f.run);draft=json.loads((f.run/'source-clips-draft.json').read_text(encoding='utf-8'))
    note_path=Path(original['entries'][0]['evidence_identity']['path']);note=json.loads(note_path.read_text(encoding='utf-8'))
    for method in ('human_video','agent_video'):
        for bad in ('process','continuity'):
            observation=deepcopy(note);data=deepcopy(original)
            observation['review_method']=data['review_method']=method
            if bad=='process':observation['entries'][0]['process_observation']=''
            else:
                row=next(r for r in observation['entries'] if r['clip_shot_id']=='shot_0004' and r['role']=='primary')
                row['quality_observation']='TEST ONLY generic quality; no explicit comparison'
            write(note_path,observation)
            for row in data['entries']:row['evidence_identity']=thaw(hash_file(note_path))
            write(path,data)
            with pytest.raises(ValueError):f.sc.review(f.run,path,draft,hash_file(f.run/'source-clips-draft.json'))
