"""All-frame native proofs with bounded persistent evidence, including orphan recovery."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import pytest

from unit.test_frames import media_context, make_video


def api():
    from video_ai.media.scene_native_batch import extract_native_scene_batch
    return extract_native_scene_batch


def test_real_native_batch_checks_every_frame_and_aggregates_evidence(media_context):
    from video_ai.config import read_json
    from video_ai.media.scene_upscale import verify_scene_frame_pixels
    run, kwargs = media_context
    source = make_video(media_context, frames=3)
    images, evidence = api()(source, run/'batch', expected_frames=3, width=128, height=72, **kwargs)
    assert [Path(r['path']).name for r in images] == [f'frame_{i:06d}.png' for i in range(1,4)]
    verify_scene_frame_pixels(source, [r['path'] for r in images], expected_frames=3,
        width=128, height=72, config=kwargs['config'])
    report = read_json(evidence[-1])
    assert report['algorithm'] == 'scene_native_png_batch_v1'
    assert report['recovered_existing'] is False
    assert [r['index'] for r in report['frames']] == [0,1,2]
    assert all(len(r['decoded_rgb24_sha256']) == 64 for r in report['frames'])
    assert len(evidence) < 20  # Evidence writes do not scale with PNG count.


@pytest.mark.parametrize('fault',['missing','extra','wrong_size','last_corrupt','reordered'])
def test_existing_batch_refuses_incomplete_or_wrong_native_pixels(media_context,fault):
    from image_helpers import write_png
    run, kwargs = media_context
    source = make_video(media_context, frames=3)
    images,_ = api()(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    folder=run/'batch';last=Path(images[-1]['path'])
    if fault=='missing':last.unlink()
    elif fault=='extra':(folder/'extra.txt').write_bytes(b'extra')
    elif fault=='wrong_size':write_png(last,64,72)
    elif fault=='last_corrupt':last.write_bytes(b'not png')
    else:
        # The video fixture moves; substitute a valid frame in the wrong index.
        last.write_bytes(Path(images[0]['path']).read_bytes())
    with pytest.raises((ValueError,OSError,RuntimeError)):
        api()(source,folder,expected_frames=3,width=128,height=72,reuse_existing=True,**kwargs)


def test_existing_batch_never_runs_another_extraction(media_context,monkeypatch):
    import video_ai.media.scene_native_batch as module
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    first,_=api()(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    def forbidden(*args,**kw):raise AssertionError('existing extraction must not rerun FFmpeg extraction')
    monkeypatch.setattr(module,'_command',forbidden)
    second,_=api()(source,run/'batch',expected_frames=3,width=128,height=72,reuse_existing=True,**kwargs)
    assert second==first


def test_mutation_during_last_evidence_guard_is_not_accepted(media_context):
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    original=kwargs['logger']
    class MutatingLogger:
        def __getattr__(self,name):return getattr(original,name)
        def save_json(self,name,value):
            if value.get('algorithm')=='scene_native_png_batch_v1':
                Path(value['frames'][-1]['image']['path']).write_bytes(b'changed in evidence write guard')
            return original.save_json(name,value)
    with pytest.raises((ValueError,OSError)):
        api()(source,run/'batch',expected_frames=3,width=128,height=72,
            **dict(kwargs,logger=MutatingLogger()))


def test_219_frames_keep_shared_1200_second_budget_with_slow_write_guard(media_context,monkeypatch):
    from image_helpers import write_png
    import video_ai.media.scene_native_batch as module
    run,kwargs=media_context;source=make_video(media_context,frames=1)
    folder=run/'batch';folder.mkdir()
    for i in range(1,220):write_png(folder/f'frame_{i:06d}.png',2,2)
    clock=[0.0];checked=[];writes=[];original=kwargs['logger']
    class CostlyLogger:
        def __getattr__(self,name):return getattr(original,name)
        def save_json(self,name,value):
            clock[0]+=6.3;writes.append(name);return original.save_json(name,value)
    monkeypatch.setattr(module,'monotonic',lambda:clock[0])
    monkeypatch.setattr(module,'inspect_video',lambda *a,**k:({'frames':219},[]))
    monkeypatch.setattr(module,'_decode',lambda *a,**k:bytes(219*12))
    def verify(path,**kw):
        assert 0 < kw['timeout'] <= 300
        checked.append(Path(path).name);clock[0]+=0.1;return bytes(12)
    monkeypatch.setattr(module,'verify_png',verify)
    rows,_=api()(source,folder,expected_frames=219,width=2,height=2,reuse_existing=True,
        timeout=1200,**dict(kwargs,logger=CostlyLogger()))
    assert len(rows)==len(checked)==219 and len(writes)==1
    assert clock[0]<1200
    assert rows[-1]['sha256']==hashlib.sha256((folder/'frame_000219.png').read_bytes()).hexdigest()


def test_shared_deadline_expires_before_next_png(media_context,monkeypatch):
    import video_ai.media.scene_native_batch as module
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    api()(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    clock=[0.0];original=module.verify_png;count=[]
    monkeypatch.setattr(module,'monotonic',lambda:clock[0])
    def slow(*a,**kw):
        count.append(1);value=original(*a,**kw);clock[0]+=700;return value
    monkeypatch.setattr(module,'verify_png',slow)
    with pytest.raises(TimeoutError,match='media budget expired'):
        api()(source,run/'batch',expected_frames=3,width=128,height=72,reuse_existing=True,**kwargs)
    assert len(count)==2


@pytest.mark.parametrize('mode',['whole_scene_v1','segmented_v1',None])
def test_production_selects_batch_only_for_explicit_whole(runtime_run,monkeypatch,mode):
    import video_ai.runtime.production_scene_upscale as producer
    import video_ai.media.scene_upscale as legacy
    import video_ai.media.scene_native_batch as batch
    class Selected(Exception):pass
    def old(*a,**k):raise Selected('legacy')
    def new(*a,**k):raise Selected('batch')
    monkeypatch.setattr(legacy,'extract_scene_frames',old)
    monkeypatch.setattr(batch,'extract_native_scene_batch',new)
    monkeypatch.setattr(producer,'validate_extraction',lambda *a,**k:None)
    run=runtime_run[0];folder=run/'production/scene-upscale/scene_0001_clip_0001'
    raw={} if mode is None else dict(scene_rendering=dict(mode=mode))
    store=SimpleNamespace(clip_dir=lambda _:folder,verify_global=lambda:None,paths=runtime_run[2])
    config=SimpleNamespace(raw=raw,media=SimpleNamespace(profile=SimpleNamespace(width=128,height=72)))
    context=dict(store=store,frozen=SimpleNamespace(config=config))
    clip=dict(clip_id='scene_0001_clip_0001',source=dict(path=str(run/'source.mp4')),budget=dict(retained_frames=3))
    with pytest.raises(Selected,match='batch' if mode=='whole_scene_v1' else 'legacy'):
        producer._extract(context,clip,None)


@pytest.mark.parametrize('fault',['none','relative','outside','bad_name','legacy'])
def test_explicit_recovery_directory_is_exact_owned_whole_child(runtime_run,monkeypatch,fault):
    import video_ai.runtime.production_scene_upscale as producer
    import video_ai.media.scene_native_batch as batch
    from video_ai.runtime.production_state import ProductionRefused
    class Selected(Exception):pass
    run=runtime_run[0];folder=run/'production/scene-upscale/scene_0001_clip_0001'
    stage=folder/('extraction-'+'a'*32)
    if fault=='relative':stage=Path('relative')
    if fault=='outside':stage=run/('extraction-'+'a'*32)
    if fault=='bad_name':stage=folder/'untracked'
    def new(source,directory,**kw):
        assert directory==stage and kw['reuse_existing'] is True
        raise Selected('recovered same directory')
    monkeypatch.setattr(batch,'extract_native_scene_batch',new)
    monkeypatch.setattr(producer,'validate_extraction',lambda *a,**k:None)
    store=SimpleNamespace(clip_dir=lambda _:folder,verify_global=lambda:None,paths=runtime_run[2],
        _lexical=lambda p:p)
    config=SimpleNamespace(raw=dict(scene_rendering=dict(mode='segmented_v1' if fault=='legacy' else 'whole_scene_v1')),
        media=SimpleNamespace(profile=SimpleNamespace(width=128,height=72)))
    context=dict(store=store,frozen=SimpleNamespace(config=config))
    clip=dict(clip_id='scene_0001_clip_0001',source=dict(path=str(run/'source.mp4')),budget=dict(retained_frames=3))
    error=Selected if fault=='none' else ProductionRefused
    with pytest.raises(error):producer._extract(context,clip,None,recovery_directory=stage)


@pytest.mark.parametrize('fault',['source','png'])
def test_mutation_during_png_validation_refuses_batch(media_context,monkeypatch,fault):
    import video_ai.media.scene_native_batch as module
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    api()(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    original=module.verify_png
    def mutate(path,**kw):
        value=original(path,**kw)
        if Path(path).name=='frame_000003.png':
            (source if fault=='source' else run/'batch/frame_000001.png').write_bytes(b'changed after validation')
        return value
    monkeypatch.setattr(module,'verify_png',mutate)
    with pytest.raises((ValueError,OSError)):
        api()(source,run/'batch',expected_frames=3,width=128,height=72,reuse_existing=True,**kwargs)


def test_prior_per_png_logged_path_exhausts_same_1200_second_budget(media_context,monkeypatch):
    from image_helpers import write_png
    from video_ai.runtime.manifest import hash_file,thaw
    import video_ai.media.frames as frames
    run,kwargs=media_context;folder=run/'batch';folder.mkdir();paths=[];clock=[0.0]
    for i in range(1,220):
        path=folder/f'frame_{i:06d}.png';write_png(path,2,2);paths.append(path)
    checked=[]
    def inspect(path,**kw):
        checked.append(path);clock[0]+=56.3
        return dict(width=2,height=2,format='png',pixel_format='rgb24',identity=thaw(hash_file(path))),[]
    monkeypatch.setattr(frames,'monotonic',lambda:clock[0])
    monkeypatch.setattr(frames,'inspect_image',inspect)
    with pytest.raises(TimeoutError,match='media budget expired'):
        frames._images(paths,width=2,height=2,deadline=1200,**kwargs)
    assert 20<=len(checked)<=22
