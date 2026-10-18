import json
import pytest
from source_clip_helpers import setup,review


def test_known_short65_requests69_then73_once_and_selects_independent_second(runtime_run,monkeypatch):
    f=setup(runtime_run,monkeypatch,'short');result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert result.status=='review_required' and result.clip_count==7
    assert f.requests==[69,73,45,49,85,57,29,93]
    clip=json.loads(result.draft_path.read_text(encoding='utf-8'))['clips'][0]
    assert clip['selected_attempt_id']=='attempt_0002' and clip['parameters']['length']==73 and clip['budget']['wan_frames']==69
    assert [(a['attempt_id'],a['actual_frames'],a['status']) for a in clip['attempts']]==[('attempt_0001',65,'short'),('attempt_0002',73,'selected')]
    snap=f.store.snapshot()['units']['shot_attempt']
    assert snap['shot_0001:attempt_0001']['status']=='failed' and snap['shot_0001:attempt_0001']['submission']['state']=='completed'
    assert clip['attempts'][0]['submission']['attempt_id']!=clip['attempts'][1]['submission']['attempt_id']
    path,_=review(f.run);assert f.sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
    assert f.sc.load_committed_source_clips(f.run)['clips'][0]['generated_frames']==73


@pytest.mark.parametrize('mode',['lost','two','prefix','url','stale','mismatch','twice_short','external','stop_failure'])
def test_failure_never_reposts_except_single_proven_short(runtime_run,monkeypatch,mode):
    f=setup(runtime_run,monkeypatch,mode);result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert not result.passed and not (f.run/'source-clips-draft.json').exists()
    assert len(f.requests)==(0 if mode=='external' else 2 if mode=='twice_short' else 7 if mode=='stop_failure' else 1)
    assert f.actions==(['start'] if mode=='external' else ['start','stop'])
    if mode=='lost':
        assert f.store.snapshot()['units']['shot_attempt']['shot_0001:attempt_0001']['submission']['state']=='ambiguous'
        assert result.status=='failed'


def test_later_failure_retains_first_terminal_checkpoint_and_reports_count(runtime_run,monkeypatch):
    f=setup(runtime_run,monkeypatch,'later_fail');result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and result.clip_count==1
    assert (f.run/'shots/shot_0001/source.mp4').is_file()
    assert (f.run/'logs/source-clips/clip-shot_0001.json').is_file()
    snap=f.store.snapshot()
    assert snap['units']['shot_attempt']['shot_0001:attempt_0001']['status']=='completed'
    assert snap['units']['shot_attempt']['shot_0002:attempt_0001']['submission']['state']=='ambiguous'


@pytest.mark.parametrize('change',['node','negative','mapping','memory'])
def test_whole_graph_and_loaded_mapping_checked_before_any_post(runtime_run,monkeypatch,change):
    f=setup(runtime_run,monkeypatch)
    base=f.ci.WorkflowTemplate.load
    def replaced(*a):
        t=base(*a)
        if change=='node':t.graph['129:104']['inputs']['shift']=9
        if change=='negative':t.graph['129:89']['inputs']['text']='replacement'
        if change=='mapping':t.mapping['inputs']['width']=dict(node_id='129:128',input='value')
        if change=='memory':t.graph['129:93']['_meta']['title']='changed'
        return t
    monkeypatch.setattr(f.ci.WorkflowTemplate,'load',replaced)
    with pytest.raises(f.sc.SourceClipRefusal):f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert f.requests==[] and f.actions==[]


def test_remote_validation_exhausts_shared_deadline_without_post(runtime_run,monkeypatch):
    import time
    f=setup(runtime_run,monkeypatch)
    def tiny(self,seconds):self.end=time.monotonic()+.000001
    monkeypatch.setattr(f.cg.DeadlineHttp,'set_deadline',tiny)
    result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and f.requests==[] and f.actions==['start','stop']
    assert len(f.store.snapshot()['units']['shot_attempt'])==1


def test_source_identity_drift_between_attempts_prevents_supplement_post(runtime_run,monkeypatch):
    f=setup(runtime_run,monkeypatch,'short');base=f.cg.supplement_frames
    def changed(**kw):
        result=base(**kw);(f.run/'shots/shot_0001/start.png').write_bytes(b'changed');return result
    monkeypatch.setattr(f.cg,'supplement_frames',changed)
    result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and f.requests==[69]
    assert f.store.snapshot()['units']['shot_attempt']['shot_0001:attempt_0001']['submission']['state']=='completed'


def test_post_checkpoint_manifest_write_error_reports_prepared_clip_count(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import ManifestStore
    f=setup(runtime_run,monkeypatch);base=ManifestStore._write
    def completed_then_error(self,data):
        base(self,data)
        if data['units'].get('shot_attempt',{}).get('shot_0001:attempt_0001',{}).get('status')=='completed' and data['stages']['source_clips']['status']=='running':
            raise OSError('diagnostic write error after durable attempt checkpoint')
    monkeypatch.setattr(ManifestStore,'_write',completed_then_error)
    result=f.sc.prepare_source_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and result.clip_count==1
    assert f.store.snapshot()['units']['shot_attempt']['shot_0001:attempt_0001']['status']=='completed'
    assert (f.run/'logs/source-clips/clip-shot_0001.json').is_file()
