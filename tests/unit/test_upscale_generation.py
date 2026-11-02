import json
import pytest
from upscale_helpers import setup


@pytest.mark.parametrize('profile',['fast','quality'])
def test_serial_frame_checkpoints_and_owned_stop_preserve_source(runtime_run,monkeypatch,profile):
    f=setup(runtime_run,monkeypatch,profile=profile);before=f.store.snapshot();result=f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required' and result.clip_count==1 and not result.passed
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'));clip=draft['clips'][0]
    assert [r['source_frame_index'] for r in clip['frames']]==[0,1]
    assert len(f.requests)==2 and len({r['submission']['attempt_id'] for r in clip['frames']})==2
    assert f.actions==['start','stop'] and f.process.poll()==0 and len(f.calls)==2
    for index,row in enumerate(clip['frames'],1):
        assert row['frame_index']==index and row['parameters']['model_scale']==4
        assert row['input_identity']['sha256']==row['input_copy_identity']['sha256']
        assert row['output_identity']['sha256']==row['upscaled_frame_identity']['sha256']
        unit=f.store.snapshot()['units']['frame'][f'shot_0001:frame_{index:06d}']
        assert unit['status']=='completed' and unit['submission']['state']=='completed'
        assert [a['path'] for a in unit['artifacts']]==[row['checkpoint_identity']['path'],row['input_identity']['path'],row['upscaled_frame_identity']['path']]
    assert f.store.snapshot()['units']['shot']==before['units']['shot']
    assert f.store.snapshot()['stages']['source_clips']==before['stages']['source_clips']
    assert draft['source_review_method']=='user_acceptance' and draft['source_validation']==f.source['validation']
    assert draft['validation']['upscale_quality_passed'] is False


def test_generated_inputs_skip_recursive_integrity_checks_but_submit_once(runtime_run,monkeypatch):
    from video_ai.runtime import _pipeline_model_paths
    f=setup(runtime_run,monkeypatch)
    def forbidden(*args,**kwargs):
        raise AssertionError('recursive integrity verification must be disabled')
    monkeypatch.setattr(f.ui,'load_committed_source_clips',forbidden)
    monkeypatch.setattr(_pipeline_model_paths,'prepare_or_consume_model_binding',forbidden)
    monkeypatch.setattr(f.uc,'validate',forbidden)
    monkeypatch.setattr(f.ug,'before_post',forbidden)
    result=f.uc.prepare_upscaled_clips(f.config,run_dir=f.run,
        execution_policy='pipeline',verify_integrity=False)
    assert result.status=='review_required' and result.clip_count==1
    assert len(f.requests)==2 and f.actions==['start','stop']
    assert not f.calls
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'))
    assert draft['validation']['upscale_quality_passed'] is False
    assert f.store.snapshot()['units']['frame']['shot_0001:frame_000002']['status']=='completed'


def test_generated_manifest_does_not_rescan_all_history_on_each_frame(runtime_run,monkeypatch):
    from video_ai.runtime import manifest
    f=setup(runtime_run,monkeypatch)
    before=f.store.snapshot()
    def forbidden(*args,**kwargs):
        raise AssertionError('full manifest verification must be disabled for generated records')
    monkeypatch.setattr(manifest,'_validate',forbidden)
    store=manifest.ManifestStore.open(f.run,verify_integrity=False)
    store.record_unit('frame','shot_0001:frame_000001','running')
    store.record_unit('frame','shot_0001:frame_000001','completed')
    assert store.snapshot()['units']['frame']['shot_0001:frame_000001']['status']=='completed'
    assert store.snapshot()['units']['shot']==before['units']['shot']
    with pytest.raises(ValueError,match='immutable run_id'):
        store.update(lambda data:data.update(run_id='changed'))


@pytest.mark.parametrize('mode',['lost','later_fail','two','prefix','url','stale','corrupt','size','external','stop_failure','remote_missing'])
def test_failure_keeps_once_only_intent_and_successes(runtime_run,monkeypatch,mode):
    f=setup(runtime_run,monkeypatch,mode);result=f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and not result.draft_path.exists()
    assert len(f.requests)==(0 if mode in ('external','remote_missing') else 2 if mode in ('later_fail','stop_failure') else 1)
    assert f.actions==(['start'] if mode=='external' else ['start','stop'])
    if mode=='later_fail':
        assert (f.run/'logs/upscale/frame-shot_0001-000001.json').exists()
        assert f.store.snapshot()['units']['frame']['shot_0001:frame_000001']['status']=='completed'
    if mode in ('lost','later_fail'):
        assert list(f.store.snapshot()['units']['frame'].values())[-1]['submission']['state']=='ambiguous'


def test_clip_and_frame_deadlines_are_absolute_and_http_capped(runtime_run,monkeypatch):
    import time
    f=setup(runtime_run,monkeypatch)
    base=f.ug.DeadlineHttp.set_deadlines
    monkeypatch.setattr(f.ug.DeadlineHttp,'set_deadlines',lambda self,*a:base(self,time.monotonic()+.000001,time.monotonic()+.000001))
    # Historical bounded component execution remains characterized independently.
    result=f.uc.prepare_upscaled_clips.__wrapped__(f.config,run_dir=f.run)
    assert result.status=='failed' and not f.requests and f.actions==['start','stop']


@pytest.mark.parametrize('change',['graph','mapping','source','config','model'])
def test_loaded_or_actual_input_drift_before_post_refuses(runtime_run,monkeypatch,change):
    f=setup(runtime_run,monkeypatch);base=f.ug.graph
    def changed(*args):
        actual=base(*args)
        if change=='graph':actual['4']['inputs']['image']=['1',0]
        elif change=='mapping':args[0].mapping['inputs']['image']['node_id']='4'
        elif change=='source':(f.run/'shots/shot_0001/source.mp4').write_bytes(b'TEST ONLY drift')
        elif change=='config':f.config.config_file.write_bytes(b'TEST ONLY drift')
        else:f.config.models['upscale'].write_bytes(b'TEST ONLY drift')
        return actual
    monkeypatch.setattr(f.ug,'graph',changed)
    result=f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and not f.requests


def test_accepted_loss_at_deadline_persists_ambiguous_intent_without_repost(runtime_run,monkeypatch):
    import time
    f=setup(runtime_run,monkeypatch);original=f.transport.handler
    def route(request,timeout):
        if request.method=='POST':
            f.requests.append(json.loads(request.data)['prompt'])
            time.sleep(1.1)
            raise ConnectionResetError('TEST ONLY accepted response lost at deadline')
        return original(request,timeout)
    f.transport.handler=route
    original_deadline=f.ug.DeadlineHttp.set_deadlines
    # Leave time for the recording reserve, then lose the sole accepted POST
    # after the finite frame deadline. The once-only assertions stay unchanged.
    monkeypatch.setattr(f.ug.DeadlineHttp,'set_deadlines',lambda self,c,e:original_deadline(self,c,time.monotonic()+1))
    result=f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and len(f.requests)==1
    unit=f.store.snapshot()['units']['frame']['shot_0001:frame_000001']
    assert unit['submission']['state']=='ambiguous'
