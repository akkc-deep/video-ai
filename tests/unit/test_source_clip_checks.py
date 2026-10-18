import json
from pathlib import Path
import pytest
from source_clip_helpers import setup,review,write


def test_source_clip_api_exists():
    from importlib.util import find_spec
    assert find_spec('video_ai.runtime.source_clip_checks') is not None
    from video_ai.runtime import source_clip_checks as sc
    assert callable(getattr(sc,'prepare_source_clips',None))
    assert callable(getattr(sc,'finalize_source_clips',None))
    assert callable(getattr(sc,'load_committed_source_clips',None))


@pytest.mark.parametrize('bad',['lock','draft','report','unit','attempt','generated','source','copy','config','model','image','path'])
def test_entry_guards_preserve_pending_without_post(runtime_run,monkeypatch,bad):
    f=setup(runtime_run,monkeypatch)
    if bad=='lock':write(f.run/'.source-clips.lock',{'token':'foreign'})
    if bad in ('draft','report'):write(f.run/('source-clips-draft.json' if bad=='draft' else 'source-clips.json'),{})
    if bad in ('unit','attempt'):f.store.record_unit('shot' if bad=='unit' else 'shot_attempt','shot_0001' if bad=='unit' else 'shot_0001:attempt_0001','running')
    if bad in ('generated','source'):(f.run/'shots/shot_0001'/f'{bad}.mp4').write_bytes(b'orphan')
    if bad=='copy':write(f.run/'comfy/input'/f.run.name/'source_clips/shot_0001/start.png',{})
    if bad=='config':f.config.config_file.write_text('{}')
    if bad=='model':f.config.models['wan_high'].write_bytes(b'changed')
    if bad=='image':(f.run/'shots/shot_0001/start.png').write_bytes(b'changed')
    path=f.run/'..'/f.run.name if bad=='path' else f.run
    with pytest.raises(f.sc.SourceClipRefusal):f.sc.prepare_source_clips(f.config,run_dir=path)
    assert f.store.snapshot()['stages']['source_clips']['status']=='pending'
    assert f.requests==[] and f.actions==[]


def test_seven_media_checkpoints_all13_review_and_atomic_commit(runtime_run,monkeypatch):
    from video_ai.runtime import resources,services
    def forbidden(*a,**kw):raise AssertionError('GPU resource monitoring/lease/free is forbidden')
    monkeypatch.setattr(services,'gpu_guard',forbidden)
    monkeypatch.setattr(resources,'gpu_guard',forbidden)
    f=setup(runtime_run,monkeypatch)
    before=f.store.snapshot()
    result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert (result.status,result.passed,result.clip_count,result.ready_for_upscale)==('review_required',False,7,False)
    assert f.requests==[69,45,49,85,57,29,93] and f.actions==['start','stop']
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'))
    assert [c['source_frames'] for c in draft['clips']]==[68,45,47,84,55,27,93]
    assert len(draft['requirement_clips'])==13
    assert all((f.run/'logs/source-clips'/f'clip-shot_{i:04d}.json').is_file() for i in range(1,8))
    snap=f.store.snapshot()
    assert all(u['status']=='running' and u['submission'] is None for u in snap['units']['shot'].values())
    assert all(u['status']=='completed' for u in snap['units']['shot_attempt'].values())
    with pytest.raises(ValueError):f.sc.load_committed_source_clips(f.run)
    path,_=review(f.run)
    assert f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    report=f.sc.load_committed_source_clips(f.run)
    assert report['passed'] and report['validation']['ready_for_upscale']
    assert report['validation']['final_video_sync']==report['validation']['full_film_acceptance']=='unverified'
    after=f.store.snapshot()
    assert all(u['status']=='completed' for u in after['units']['shot'].values())
    assert after['units']['shot_attempt']==snap['units']['shot_attempt']
    for stage in ('speech','timeline','storyboard','start_images'):assert before['stages'][stage]==after['stages'][stage]
    f.store.record_stage('upscale','running')
    assert f.sc.load_committed_source_clips(f.run)['passed']


@pytest.mark.parametrize('bad',['missing','unverified','static','partial','quality','failed','unknown','bool','drift','time'])
def test_reviews_require_every_bound_continuous_motion_and_quality_observation(runtime_run,monkeypatch,bad):
    from video_ai.runtime.manifest import hash_file,thaw
    f=setup(runtime_run,monkeypatch)
    assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    path,data=review(f.run)
    if bad=='missing':data['entries'].pop()
    if bad in ('unverified','failed'):data['entries'][0]['verdict']=bad
    if bad=='static':data['review_method']='agent_visual'
    if bad=='unknown':data['extra']=True
    if bad=='bool':data['entries'][0]['local_frames']['start']=False
    if bad=='drift':Path(data['entries'][0]['actual_artifact']['path']).write_bytes(b'changed')
    if bad=='time':data['reviewed_at']='2000-01-01T00:00:00+00:00'
    if bad in ('partial','quality'):
        note=Path(data['entries'][0]['evidence_identity']['path']);n=json.loads(note.read_text(encoding='utf-8'))
        if bad=='partial':n['entries'][0]['playback_frames']['end']=3
        else:n['entries'][0]['quality_observation']=''
        write(note,n)
        for row in data['entries']:row['evidence_identity']=thaw(hash_file(note))
    write(path,data)
    result=f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path)
    assert not result.passed and not result.ready_for_upscale and result.clip_count==7
    assert not (f.run/'source-clips.json').exists()
    if bad in ('missing','unverified'):assert result.status=='review_required'


@pytest.mark.parametrize('changed',['source','generated','input','model','evidence','review','config','draft','report'])
def test_fresh_consumer_rejects_mtime_only_committed_drift(runtime_run,monkeypatch,changed):
    import os
    f=setup(runtime_run,monkeypatch);f.sc.prepare_source_clips(f.config,run_dir=f.run)
    path,_=review(f.run);assert f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    report=f.sc.load_committed_source_clips(f.run)
    targets=dict(source=f.run/'shots/shot_0001/source.mp4',generated=f.run/'shots/shot_0001/generated.mp4',input=f.run/'shots/shot_0001/start.png',
        model=f.config.models['wan_high'],
        evidence=Path(next(iter(report['request_evidence'].values()))['path']),review=path,config=f.config.config_file,draft=f.run/'source-clips-draft.json',report=f.run/'source-clips.json')
    target=targets[changed]
    before=target.read_bytes();stamp=target.stat().st_mtime_ns
    os.utime(target,ns=(stamp,stamp+10_000_000))
    try:
        with pytest.raises((ValueError,OSError)):f.sc.load_committed_source_clips(f.run)
    finally:os.utime(target,ns=(stamp,stamp))


def test_atomic_manifest_failure_leaves_orphan_report_unconsumable(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import ManifestStore
    f=setup(runtime_run,monkeypatch);f.sc.prepare_source_clips(f.config,run_dir=f.run);path,_=review(f.run)
    base=ManifestStore._write
    def fail(self,data):
        if data['stages']['source_clips']['status']=='completed':raise OSError('atomic commit failed')
        return base(self,data)
    monkeypatch.setattr(ManifestStore,'_write',fail)
    assert not f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    assert (f.run/'source-clips.json').exists()
    assert not any(u['status']=='completed' for u in f.store.snapshot()['units']['shot'].values())
    with pytest.raises(ValueError):f.sc.load_committed_source_clips(f.run)


def test_consumer_rejects_bytes_graph_mapping_and_fabricated_budget(runtime_run,monkeypatch):
    from copy import deepcopy
    from video_ai.runtime.manifest import hash_file,thaw
    f=setup(runtime_run,monkeypatch);f.sc.prepare_source_clips(f.config,run_dir=f.run)
    path,_=review(f.run);assert f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    report=f.sc.load_committed_source_clips(f.run)
    for target in [f.run/'shots/shot_0001/source.mp4',f.run/'shots/shot_0001/generated.mp4',f.run/'shots/shot_0001/start.png',
        f.config.models['wan_high'],f.config.config_file,path,Path(report['request_evidence']['logs/source-clips/input-shot_0001.json']['path'])]:
        import os
        raw=target.read_bytes();stamp=target.stat().st_mtime_ns
        target.write_bytes(raw+b'CHANGED')
        try:
            with pytest.raises((ValueError,OSError)):f.sc.load_committed_source_clips(f.run)
        finally:target.write_bytes(raw);os.utime(target,ns=(stamp,stamp))
    base=f.ci.WorkflowTemplate.load
    for changed in ('graph','mapping'):
        def replaced(*a):
            t=base(*a)
            if changed=='graph':t.graph['129:104']['inputs']['shift']=9
            else:t.mapping['inputs']['width']=dict(node_id='129:128',input='value')
            return t
        with monkeypatch.context() as patch:
            patch.setattr(f.ci.WorkflowTemplate,'load',replaced)
            with pytest.raises(ValueError):f.sc.load_committed_source_clips(f.run)
    from video_ai.runtime._source_clip_evidence import validate
    draft=json.loads((f.run/'source-clips-draft.json').read_text(encoding='utf-8'));context=f.ci.inputs(f.config,f.run)
    for kind in ('budget','mapping','parameter_bool','attempt','omitted_media','omitted_http','other_shot_media','alias'):
        bad=deepcopy(draft)
        if kind=='budget':bad['clips'][0]['budget']['required_native_frames']=69
        if kind=='mapping':bad['frame_mappings'][0]['output_to_source'][0]=1
        if kind=='parameter_bool':bad['clips'][0]['parameters']['batch']=True
        if kind=='attempt':bad['clips'][0]['attempts'][0]['submission']['attempt_id']='attempt_0001'
        if kind=='omitted_media':bad['clips'][0]['evidence_identities']=[n for n in bad['clips'][0]['evidence_identities'] if '/trim-' not in n]
        if kind=='omitted_http':bad['clips'][0]['attempts'][0]['evidence_identities']=[n for n in bad['clips'][0]['attempts'][0]['evidence_identities'] if not n.endswith('.body')]
        if kind=='other_shot_media':bad['clips'][0]['evidence_identities']=bad['clips'][1]['evidence_identities']
        if kind=='alias':
            key=next(iter(bad['request_evidence']));bad['request_evidence'][key.replace('shots/','shots/../shots/')]=bad['request_evidence'].pop(key)
        with pytest.raises((ValueError,OSError)):validate(f.config,f.run,bad,context,f.store.snapshot())


def test_rehashed_raw_http_media_and_trim_lies_fail_cross_validation(runtime_run,monkeypatch):
    from copy import deepcopy
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime._source_clip_evidence import validate
    import os
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    draft=json.loads((f.run/'source-clips-draft.json').read_text(encoding='utf-8'));context=f.ci.inputs(f.config,f.run)
    covered=draft['clips'][0]['evidence_identities']
    post=next(n for n in covered if n.endswith('.request.json') and json.loads((f.run/n).read_text())['method']=='POST')
    inspected=next(n for n in covered if '/video-' in n)
    trimmed=next(n for n in covered if '/trim-' in n)
    for kind,name in [('post_graph',post),('post_unit',post),('acceptance',post.replace('.request.json','.body')),('raw_pts',inspected),('command',inspected),('trim',trimmed)]:
        path=f.run/name;raw=path.read_bytes();stamp=path.stat().st_mtime_ns;data=json.loads(raw)
        if kind=='post_graph':data['json_body']['prompt']['129:104']['inputs']['shift']=9
        if kind=='post_unit':data['unit_id']='shot_0002:attempt_0001'
        if kind=='acceptance':data['prompt_id']='00000000-0000-0000-0000-000000000000'
        if kind=='raw_pts':data['frames']['frames'][10]['best_effort_timestamp']=0
        if kind=='command':data['commands'][2]['args'].remove('-xerror')
        if kind=='trim':data['target']['frames']=1
        write(path,data);bad=deepcopy(draft);bad['request_evidence'][name]=thaw(hash_file(path))
        try:
            with pytest.raises((ValueError,OSError)):validate(f.config,f.run,bad,context,f.store.snapshot())
        finally:path.write_bytes(raw);os.utime(path,ns=(stamp,stamp))


def test_foreign_lock_retained_and_completed_survives_post_commit_interrupt(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import ManifestStore
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    path,_=review(f.run);base=ManifestStore._write
    def interrupted(self,data):
        base(self,data)
        if data['stages']['source_clips']['status']=='completed':raise KeyboardInterrupt()
    monkeypatch.setattr(ManifestStore,'_write',interrupted)
    assert f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    assert f.sc.load_committed_source_clips(f.run)['passed']


def test_lock_replacement_cannot_publish_draft_or_delete_foreign_token(runtime_run,monkeypatch):
    f=setup(runtime_run,monkeypatch);base=f.sc.generate
    def replacement(*a,**kw):
        base(*a,**kw);write(f.run/'.source-clips.lock',{'token':'foreign'})
    monkeypatch.setattr(f.sc,'generate',replacement)
    result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert not result.passed and result.clip_count==7 and not (f.run/'source-clips-draft.json').exists()
    assert json.loads((f.run/'.source-clips.lock').read_text())=={'token':'foreign'}
    assert all(u['status']=='completed' for u in f.store.snapshot()['units']['shot_attempt'].values())


def test_quality_fade24_prepares_native16_and_bound_integer_mapping(runtime_run,monkeypatch):
    f=setup(runtime_run,monkeypatch,profile='quality',fps=24,transition='fade')
    result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert result.status=='review_required' and result.clip_count==7
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'))
    assert (draft['clips'][0]['width'],draft['clips'][0]['height'],draft['clips'][0]['native_fps'])==(1280,720,16)
    assert draft['clips'][0]['source_frames']==72 and draft['clips'][0]['generated_frames']==73
    assert draft['frame_mappings'][0]['output_to_source'][:9]==[0,0,1,2,2,3,4,4,5]
    path,_=review(f.run)
    assert f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    assert f.sc.load_committed_source_clips(f.run)['effective_media']['fps']==24


def test_continuity_labels_require_both_primary_comparisons_and_real_observation_text(runtime_run,monkeypatch):
    from copy import deepcopy
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime._source_clip_review import ReviewIncomplete
    f=setup(runtime_run,monkeypatch);assert f.sc.prepare_source_clips(f.config,run_dir=f.run).clip_count==7
    path,data=review(f.run);draft=json.loads((f.run/'source-clips-draft.json').read_text(encoding='utf-8'))
    note_path=Path(data['entries'][0]['evidence_identity']['path']);original=json.loads(note_path.read_text(encoding='utf-8'))
    primary={n:next(i for i,row in enumerate(original['entries']) if row['clip_shot_id']==f'shot_{n:04d}' and row['role']=='primary') for n in (4,6)}
    labels={4:'[continuity:shot_0003->shot_0004:passed]',6:'[continuity:shot_0005->shot_0006:passed]'}
    for n,index in primary.items():original['entries'][index]['quality_observation']=labels[n]+' TEST ONLY: previous endpoint/current start agree; no flicker or deformation.'
    for bad in ('generic','missing4','missing6','failed','unverified','wrong','edge_only','label_only','duplicate','contradictory','extra_wrong'):
        note=deepcopy(original)
        if bad=='generic':
            for index in primary.values():note['entries'][index]['quality_observation']='TEST ONLY: generic per-clip quality'
        if bad in ('missing4','missing6'):
            n=4 if bad=='missing4' else 6;note['entries'][primary[n]]['quality_observation']='TEST ONLY: generic per-clip quality'
        if bad in ('failed','unverified'):note['entries'][primary[4]]['quality_observation']=f'[continuity:shot_0003->shot_0004:{bad}] TEST ONLY: comparison not accepted.'
        if bad=='wrong':note['entries'][primary[4]]['quality_observation']=labels[6]+' TEST ONLY: wrong comparison.'
        if bad=='edge_only':
            edge=next(i for i,row in enumerate(note['entries']) if row['clip_shot_id']=='shot_0004' and row['role']=='quantization_edge_review')
            note['entries'][edge]['quality_observation']=note['entries'][primary[4]]['quality_observation']
            note['entries'][primary[4]]['quality_observation']='TEST ONLY: generic per-clip quality'
        if bad=='label_only':note['entries'][primary[6]]['quality_observation']=labels[6]+'   '
        if bad=='duplicate':note['entries'][primary[4]]['quality_observation']=labels[4]+' TEST ONLY comparison '+labels[4]
        if bad=='contradictory':note['entries'][primary[4]]['quality_observation']=labels[4]+' TEST ONLY comparison [continuity:shot_0003->shot_0004:failed]'
        if bad=='extra_wrong':note['entries'][0]['quality_observation']=labels[4]+' TEST ONLY wrong entry.'
        write(note_path,note);changed=deepcopy(data)
        for row in changed['entries']:row['evidence_identity']=thaw(hash_file(note_path))
        write(path,changed)
        expected=ReviewIncomplete if bad=='unverified' else ValueError
        with pytest.raises(expected):f.sc.review(f.run,path,draft,hash_file(f.run/'source-clips-draft.json'))


@pytest.mark.parametrize('bad',['missing','malformed','lock_path'])
@pytest.mark.parametrize('entry',['prepare','finalize'])
def test_public_entry_manifest_and_lock_failures_are_typed_refusals(runtime_run,monkeypatch,bad,entry):
    f=setup(runtime_run,monkeypatch)
    if bad=='missing':(f.run/'manifest.json').unlink()
    if bad=='malformed':(f.run/'manifest.json').write_text('{}')
    if bad=='lock_path':
        base=f.sc._local
        def invalid(run,path):
            if Path(path).name=='.source-clips.lock':raise OSError('invalid redirected lock path')
            return base(run,path)
        monkeypatch.setattr(f.sc,'_local',invalid)
    with pytest.raises(f.sc.SourceClipRefusal) as error:
        if entry=='prepare':f.sc.prepare_source_clips(f.config,run_dir=f.run)
        else:f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=f.run/'logs/source-clips/semantic-review.json')
    assert error.value.__cause__ is not None
    assert f.requests==[] and f.actions==[]
    if bad=='lock_path':assert f.store.snapshot()['stages']['source_clips']['status']=='pending'


@pytest.mark.parametrize('entry',['prepare','finalize'])
def test_public_entry_invalid_path_types_are_refusals(runtime_run,monkeypatch,entry):
    f=setup(runtime_run,monkeypatch)
    with pytest.raises(f.sc.SourceClipRefusal) as error:
        if entry=='prepare':f.sc.prepare_source_clips(f.config,run_dir=None)
        else:f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=None)
    assert isinstance(error.value.__cause__,TypeError)
    assert f.requests==[] and f.actions==[]
