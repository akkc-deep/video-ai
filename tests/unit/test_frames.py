"""Real tiny videos exercise numeric extraction, strict PNG sets and encoding."""
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import pytest

from image_helpers import write_png
from unit.test_video import make_video


@pytest.fixture
def media_context(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.logging import RunLogger
    run,config,paths=runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config=replace(config,tools=dict(config.tools,ffmpeg=actual.tools['ffmpeg'],ffprobe=actual.tools['ffprobe']))
    return run,dict(config=config,paths=paths,logger=RunLogger(run),unit_id='shot_0001')


def api():
    from video_ai.media import frames
    return frames


def pngs(run,n=3,width=1920,height=1080):
    directory=run/'shots/shot_0001/upscaled-frames';directory.mkdir(parents=True)
    for i in range(n,0,-1):write_png(directory/f'frame_{i:06d}.png',width,height)
    return directory


def fixture_command(context,args):
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.processes import run_logged
    run,kwargs=context
    result=run_logged(tuple(str(a) for a in args),cwd=run,
        env=build_child_env(kwargs['paths']),timeout=30,logger=kwargs['logger'],
        stage='test_fixture',unit_id=kwargs['unit_id'])
    assert result.returncode==0 and not result.timed_out,result.stderr_path.read_text()
    return result


def decoded_colors(context,path,*,frames,width=1920,height=1080):
    """Independently full-decode RGB bytes, without a frame cap or media API."""
    result=fixture_command(context,[context[1]['config'].tools['ffmpeg'],
        '-nostdin','-v','error','-xerror','-i',path,'-map','0:v:0',
        '-pix_fmt','rgb24','-fps_mode','passthrough','-f','rawvideo','-'])
    raw=result.stdout_path.read_bytes();size=width*height*3
    assert len(raw)==frames*size,'independent RGB decode frame count differs'
    colors=[]
    for index in range(frames):
        frame=raw[index*size:(index+1)*size]
        colors.append(tuple(sum(frame[channel::3])/(width*height) for channel in range(3)))
    context[1]['logger'].save_json(f'color-order/{path.name}.json',
        dict(path=path,frames=frames,mean_rgb=colors,decode=result))
    return colors


def assert_color_order(observed,expected):
    # Allow eight RGB levels per channel for two lossy H.264/YUV420 round trips.
    # Distinct dominant channels differ by 224 levels, far beyond this tolerance.
    assert len(observed)==len(expected)
    for index,(actual,wanted) in enumerate(zip(observed,expected),1):
        assert all(abs(a-b)<=8 for a,b in zip(actual,wanted)),(
            f'frame {index}: decoded RGB {actual} differs from expected {wanted}')


def assert_file_identity(identity,path):
    from video_ai.runtime.manifest import hash_file
    fresh=hash_file(path)
    # verified_at records each inspection time; file identity uses stable fields.
    assert all(identity[key]==getattr(fresh,key) for key in ('path','bytes','mtime_ns','sha256'))


def test_real_frame_content_order_survives_extraction_and_encoding(media_context):
    """Catch content reversal even when names, counts and timestamps remain valid."""
    from video_ai.media.video import inspect_video
    from video_ai.runtime.manifest import hash_file,thaw
    run,kwargs=media_context;expected=((240,16,16),(16,240,16),(16,16,240))
    originals=run/'color-source';originals.mkdir()
    creation_order=[]
    for index in (3,2,1):
        path=originals/f'frame_{index:06d}.png'
        write_png(path,1920,1080,color=expected[index-1]);creation_order.append(path.name)
    assert creation_order==['frame_000003.png','frame_000002.png','frame_000001.png']
    source=run/'color-source.mp4'
    fixture_command(media_context,[kwargs['config'].tools['ffmpeg'],'-nostdin','-n',
        '-v','error','-xerror','-framerate','16','-start_number','1','-i',
        originals/'frame_%06d.png','-an','-c:v','libx264','-crf','18',
        '-pix_fmt','yuv420p','-fps_mode','passthrough',source])
    source_identity=thaw(hash_file(source))
    source_info,source_evidence=inspect_video(source,width=1920,height=1080,
        stage='test_fixture',timeout=30,**kwargs)
    assert_file_identity(source_info['identity'],source)
    assert_color_order(decoded_colors(media_context,source,frames=3),expected)
    directory=run/'shots/shot_0001/frames'
    rows,extract_evidence=api().extract_video_frames(source,directory,expected_frames=3,
        width=1920,height=1080,timeout=30,**kwargs)
    assert [row['index'] for row in rows]==[1,2,3]
    assert [row['source_frame_index'] for row in rows]==[0,1,2]
    assert all(p.is_file() for p in extract_evidence)
    extract_record=json.loads(extract_evidence[0].read_text())
    assert extract_record['frames']==rows
    assert_file_identity(extract_record['source_identity'],source)
    extracted=[]
    for index,row in enumerate(rows,1):
        path=directory/f'frame_{index:06d}.png'
        assert_file_identity(row['identity'],path)
        extracted.extend(decoded_colors(media_context,path,frames=1))
    assert_color_order(extracted,expected)
    inputs=run/'shots/shot_0001/upscaled-frames';inputs.mkdir()
    encode_creation_order=[]
    for index in (3,2,1):
        name=f'frame_{index:06d}.png'
        (inputs/name).write_bytes((directory/name).read_bytes())
        assert (inputs/name).read_bytes()==(directory/name).read_bytes()
        encode_creation_order.append(name)
    assert encode_creation_order==['frame_000003.png','frame_000002.png','frame_000001.png']
    target=run/'shots/shot_0001/upscaled.mp4'
    info,encode_evidence=api().encode_video_frames(inputs,target,frames=3,timeout=30,**kwargs)
    assert_file_identity(info['identity'],target)
    assert_color_order(decoded_colors(media_context,target,frames=3),expected)
    assert_file_identity(source_identity,source)
    encode_record=json.loads(encode_evidence[0].read_text())
    assert [row['index'] for row in encode_record['frames']]==[1,2,3]
    assert [row['source_frame_index'] for row in encode_record['frames']]==[0,1,2]
    for index,row in enumerate(encode_record['frames'],1):
        assert_file_identity(row['identity'],inputs/f'frame_{index:06d}.png')
    for video_info,evidence in ((source_info,source_evidence),(info,encode_evidence)):
        assert (video_info['fps'],video_info['frames'])==(16,3)
        record=next(json.loads(p.read_text()) for p in evidence if p.name.startswith('video-'))
        time_base=Fraction(record['probe']['streams'][0]['time_base'])
        assert [frame['best_effort_timestamp']*time_base for frame in record['frames']['frames']]==[
            Fraction(0),Fraction(1,16),Fraction(2,16)]
        assert all(p.is_file() for p in evidence)
    kwargs['logger'].save_json('color-order/summary.json',dict(expected_rgb=expected,
        tolerance_rgb=8,source_creation_order=creation_order,encode_creation_order=encode_creation_order,
        source=source_info,extracted=rows,encoded=info))


def test_real_extraction_keeps_every_native_frame_in_numeric_order(media_context):
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    before=source.read_bytes();directory=run/'shots/shot_0001/frames'
    result,evidence=api().extract_video_frames(source,directory,expected_frames=3,width=128,height=72,timeout=30,**kwargs)
    assert [r['index'] for r in result]==[1,2,3]
    assert [r['source_frame_index'] for r in result]==[0,1,2]
    assert all(set(r)=={'index','source_frame_index','identity'} for r in result)
    assert [Path(r['identity']['path']).name for r in result]==['frame_000001.png','frame_000002.png','frame_000003.png']
    assert source.read_bytes()==before and all(p.is_file() for p in evidence)
    record=json.loads(evidence[0].read_text());args=record['command']['args']
    assert args[1:]==['-nostdin','-n','-v','error','-xerror','-i',str(source),'-map','0:v:0',
        '-vf','format=rgb24','-fps_mode','passthrough','-start_number','1',str(directory/'frame_%06d.png')]
    assert record['frames']==result
    inspections=[json.loads(p.read_text()) for p in evidence if p.name.startswith('media-')]
    assert len(inspections)==3
    assert all((r['info']['width'],r['info']['height'],r['info']['format'],r['info']['pixel_format'])==(128,72,'png','rgb24') for r in inspections)
    assert all(len(r['commands'])==2 for r in inspections)
    assert [r['identity'] for r in result]==[r['info']['identity'] for r in inspections]
    events=[json.loads(l) for l in (run/'logs/events.jsonl').read_text().splitlines()]
    assert {e['stage'] for e in events}=={'test_fixture','upscale'}


@pytest.mark.parametrize('expected,width,height',[(2,128,72),(4,128,72),(3,144,72)])
def test_extraction_rejects_extra_missing_or_wrong_size_frames(media_context,expected,width,height):
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    with pytest.raises(ValueError):api().extract_video_frames(source,run/'shots/shot_0001/frames',
        expected_frames=expected,width=width,height=height,timeout=30,**kwargs)


def test_real_encoding_validates_pngs_and_all_video_pts(media_context):
    run,kwargs=media_context;directory=pngs(run);target=run/'shots/shot_0001/upscaled.mp4'
    info,evidence=api().encode_video_frames(directory,target,frames=3,timeout=30,**kwargs)
    assert set(info)=={'identity','width','height','codec','pixel_format','fps','frames','duration'}
    assert (info['width'],info['height'],info['codec'],info['pixel_format'],info['fps'],info['frames'])==(1920,1080,'h264','yuv420p',16,3)
    assert abs(info['duration']-.1875)<=.1
    record=json.loads(evidence[0].read_text());args=record['command']['args']
    assert args[1:]==['-nostdin','-n','-v','error','-xerror','-framerate','16','-start_number','1','-i',
        str(directory/'frame_%06d.png'),'-an','-c:v','libx264','-preset','medium','-crf','18',
        '-pix_fmt','yuv420p','-fps_mode','passthrough',str(target)]
    assert len([p for p in evidence if p.name.startswith('media-')])==3
    video_record=[json.loads(p.read_text()) for p in evidence if p.name.startswith('video-')][0]
    assert len(video_record['frames']['frames'])==3 and len(video_record['commands'])==3
    assert all(p.is_file() for p in evidence)
    with pytest.raises(FileExistsError):api().encode_video_frames(directory,target,frames=3,timeout=30,**kwargs)


@pytest.mark.parametrize('fault',['extra_png','extra_file','gap','alias_name','wrong_size','corrupt'])
def test_encoding_refuses_invalid_png_sequence_before_creating_video(media_context,fault):
    run,kwargs=media_context;directory=pngs(run);target=run/'upscaled.mp4'
    if fault=='extra_png':write_png(directory/'frame_000004.png',1920,1080)
    elif fault=='extra_file':(directory/'junk.txt').write_text('reject')
    elif fault=='gap':(directory/'frame_000002.png').unlink()
    elif fault=='alias_name':(directory/'frame_000002.png').rename(directory/'frame_2.png')
    elif fault=='wrong_size':write_png(directory/'frame_000002.png',1280,720)
    else:(directory/'frame_000002.png').write_bytes(b'broken')
    with pytest.raises((ValueError,RuntimeError)):api().encode_video_frames(directory,target,frames=3,timeout=30,**kwargs)
    assert not target.exists()


@pytest.mark.parametrize('n',[True,0,-1,3.0])
def test_frame_functions_reject_invalid_counts_before_commands(media_context,n):
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    before=set((run/'logs/processes').iterdir())
    with pytest.raises(ValueError):api().extract_video_frames(source,run/'frames',expected_frames=n,width=128,height=72,timeout=30,**kwargs)
    with pytest.raises(ValueError):api().encode_video_frames(run/'missing',run/'upscaled.mp4',frames=n,timeout=30,**kwargs)
    assert set((run/'logs/processes').iterdir())==before


def test_existing_directory_and_unsafe_paths_are_refused_before_commands(media_context):
    run,kwargs=media_context;source=make_video(media_context,frames=3);directory=run/'frames';directory.mkdir()
    before=set((run/'logs/processes').iterdir())
    with pytest.raises(FileExistsError):api().extract_video_frames(source,directory,expected_frames=3,width=128,height=72,timeout=30,**kwargs)
    for bad in (run/'..'/'escape',run/'sub'/'..'/'frames',run/'frames:alias'):
        with pytest.raises(ValueError):api().extract_video_frames(source,bad,expected_frames=3,width=128,height=72,timeout=30,**kwargs)
    assert set((run/'logs/processes').iterdir())==before


def test_source_identity_drift_after_extraction_is_refused(media_context,monkeypatch):
    run,kwargs=media_context;source=make_video(media_context,frames=3);module=api();original=module.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);source.write_bytes(source.read_bytes()+b'drift');return result
    monkeypatch.setattr(module,'run_logged',command)
    with pytest.raises(OSError):module.extract_video_frames(source,run/'frames',expected_frames=3,width=128,height=72,timeout=30,**kwargs)


def test_extraction_uses_one_remaining_budget_through_every_png(media_context,monkeypatch):
    run,kwargs=media_context;source=make_video(media_context,frames=3);module=api()
    from video_ai.media import images
    clock=[100.];original=module.run_logged;image_command=images.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);clock[0]+=1;return result
    def image(*args,**kw):
        result=image_command(*args,**kw);clock[0]+=1;return result
    monkeypatch.setattr(module,'run_logged',command)
    monkeypatch.setattr(images,'run_logged',image)
    monkeypatch.setattr(module,'monotonic',lambda:clock[0],raising=False)
    monkeypatch.setattr(images,'monotonic',lambda:clock[0])
    module.extract_video_frames(source,run/'frames',expected_frames=3,width=128,height=72,timeout=10,**kwargs)
    events=[json.loads(l) for l in (run/'logs/events.jsonl').read_text().splitlines()]
    starts=[e for e in events if e['stage']=='upscale' and e['event']=='command_started']
    assert [e['details']['timeout'] for e in starts]==[10,9,8,7,6,5,4]


def test_encoding_detects_png_drift_during_command(media_context,monkeypatch):
    run,kwargs=media_context;directory=pngs(run);module=api();original=module.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);p=directory/'frame_000001.png';p.write_bytes(p.read_bytes()+b'drift');return result
    monkeypatch.setattr(module,'run_logged',command)
    with pytest.raises(OSError):module.encode_video_frames(directory,run/'upscaled.mp4',frames=3,timeout=30,**kwargs)


def test_nested_png_validation_keeps_full_budget_while_commands_are_capped(media_context,monkeypatch):
    run,kwargs=media_context;source=make_video(media_context,frames=1);module=api()
    from video_ai.media import images
    clock=[100.];original=module.run_logged;image_command=images.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);clock[0]+=150;return result
    def image(*args,**kw):
        result=image_command(*args,**kw);clock[0]+=150;return result
    monkeypatch.setattr(module,'run_logged',command)
    monkeypatch.setattr(images,'run_logged',image)
    monkeypatch.setattr(module,'monotonic',lambda:clock[0])
    monkeypatch.setattr(images,'monotonic',lambda:clock[0])
    result,_=module.extract_video_frames(source,run/'frames',expected_frames=1,width=128,height=72,timeout=1000,**kwargs)
    assert len(result)==1
    events=[json.loads(l) for l in (run/'logs/events.jsonl').read_text().splitlines()]
    starts=[e for e in events if e['stage']=='upscale' and e['event']=='command_started']
    assert [e['details']['timeout'] for e in starts]==[300,300,300]


@pytest.mark.parametrize('kind',['extract','encode'])
def test_reported_subprocess_timeout_never_counts_as_success(media_context,monkeypatch,kind):
    run,kwargs=media_context;module=api();original=module.run_logged
    def command(*args,**kw):return replace(original(*args,**kw),timed_out=True)
    monkeypatch.setattr(module,'run_logged',command)
    if kind=='extract':
        source=make_video(media_context,frames=1)
        call=lambda:module.extract_video_frames(source,run/'frames',expected_frames=1,width=128,height=72,timeout=30,**kwargs)
    else:
        directory=pngs(run,n=1)
        call=lambda:module.encode_video_frames(directory,run/'upscaled.mp4',frames=1,timeout=30,**kwargs)
    with pytest.raises(RuntimeError,match='command failed'):call()
