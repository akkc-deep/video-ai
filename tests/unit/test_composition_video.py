from dataclasses import replace
from pathlib import Path
import json
import shutil
import wave
import pytest
from composition_helpers import inputs
from video_ai.planning.composition import CompositionSettings,plan_composition
from video_ai.runtime.manifest import hash_file,thaw

@pytest.fixture
def context(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.logging import RunLogger
    run,config,paths=runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config=replace(config,tools=dict(config.tools,ffmpeg=actual.tools['ffmpeg'],ffprobe=actual.tools['ffprobe']),media=replace(config.media,font_file=actual.media.font_file))
    folder=run/'staging/composition';folder.mkdir(parents=True)
    return run,folder,dict(config=config,paths=paths,logger=RunLogger(run),cwd=folder)

def module():
    from video_ai.media import composition_video
    return composition_video

def test_real_blend_uses_rational_weights_and_rounding(context):
    from image_helpers import write_png
    run,folder,kw=context
    a=write_png(folder/'a.png',width=4,height=2,color=(0,20,240))
    b=write_png(folder/'b.png',width=4,height=2,color=(255,100,0))
    out=folder/'out.png'
    record=module().blend_frame(a,b,out,left_numerator=1,right_numerator=1,denominator=2,**kw)
    data,command=module().raw_rgb(out,**kw)
    assert len(data)==24
    assert all(abs(data[i]-[128,60,120][i%3])<=1 for i in range(24))
    assert record['args'][0]==str(kw['config'].tools['ffmpeg'])

def test_real_subtitle_literals_and_chinese_render_within_margins(context):
    from video_ai.media.subtitles import ass_text,layout_text
    from video_ai.media.font_metrics import PrivateFont
    run,folder,kw=context
    settings=CompositionSettings();fontdir=folder/'fonts';fontdir.mkdir();shutil.copy2(kw['config'].media.font_file,fontdir/'font.ttc')
    text="中文 空格 ' : \\N {\\pos(0,0)} <>&"
    with PrivateFont(kw['config'].media.font_file,settings.font_name,54) as font:layout=layout_text(text,measure=font.measure,width=1788)
    events=[dict(start_cs=0,end_cs=100,layout=layout)]
    (folder/'subtitles.ass').write_text(ass_text(events,settings),encoding='utf-8')
    check=module().check_subtitle_render(events,settings,**kw)
    assert check['events'][0]['bbox'][0]>=64 and check['events'][0]['bbox'][2]<=1856
    assert check['events'][0]['line_count']==1
    assert check['events'][0]['literal_text']==text

def test_exact_sequence_rejects_extra_missing_and_nonregular(context):
    run,folder,kw=context;sequence=folder/'video-frames';sequence.mkdir()
    (sequence/'frame_000001.png').write_bytes(b'bad')
    with pytest.raises(ValueError):module().validate_sequence(sequence,2)

def test_sequence_rejects_wrong_dimensions_before_encoding(context):
    from image_helpers import write_png
    run,folder,kw=context;sequence=folder/'video-frames';sequence.mkdir()
    write_png(sequence/'frame_000001.png',width=1920,height=1080)
    write_png(sequence/'frame_000002.png',width=128,height=72)
    with pytest.raises(ValueError):module().validate_sequence(sequence,2)
    (sequence/'frame_000002.png').write_bytes(b'bad');(sequence/'extra.png').write_bytes(b'bad')
    with pytest.raises(ValueError):module().validate_sequence(sequence,2)

@pytest.mark.parametrize('fps',[16,24])
def test_real_cfr_aac_candidate_and_priming(context,fps):
    from image_helpers import write_png
    run,folder,kw=context
    seq=folder/'video-frames';seq.mkdir()
    for i in range(1,5):write_png(seq/f'frame_{i:06d}.png',width=1920,height=1080,color=(i*40,20,10))
    narration=folder/'narration.wav'
    with wave.open(str(narration),'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\0\0'*(4*(48000//fps)))
    from video_ai.media.subtitles import ass_text
    (folder/'subtitles.ass').write_text(ass_text([],CompositionSettings()),encoding='utf-8')
    (folder/'fonts').mkdir()
    info,records=module().encode_composition(seq,narration,fps=fps,frames=4,channels=1,**kw)
    assert info['frames']==4 and info['fps']==fps and info['channels']==1
    assert abs(info['audio_duration']-4/fps)<=0.1
    assert info['decoded_audio_samples']>=4*(48000//fps)
    assert info['decoded_audio_samples']-4*(48000//fps)<2048
    assert len(records)>=5

def test_probe_rejects_wrong_streams_count_fps_and_pts():
    v=module()
    probe=dict(streams=[dict(codec_type='video',codec_name='h264',pix_fmt='yuv420p',width=1920,height=1080,avg_frame_rate='16/1',r_frame_rate='16/1',nb_read_frames='2',duration='0.125'),dict(codec_type='audio',codec_name='aac',sample_rate='48000',channels=1,duration='0.125')])
    frames=dict(frames=[dict(best_effort_timestamp_time='0.000000'),dict(best_effort_timestamp_time='0.062500')])
    assert v.validate_probe(probe,frames,fps=16,total_frames=2,channels=1)['frames']==2
    for mutate in ['frames','fps','pts','streams']:
        from copy import deepcopy
        p=deepcopy(probe);f=deepcopy(frames)
        if mutate=='frames':p['streams'][0]['nb_read_frames']='1'
        if mutate=='fps':p['streams'][0]['avg_frame_rate']='24/1'
        if mutate=='pts':f['frames'][1]['best_effort_timestamp_time']='0.125'
        if mutate=='streams':p['streams'].append(dict(codec_type='subtitle'))
        with pytest.raises(ValueError):v.validate_probe(p,f,fps=16,total_frames=2,channels=1)

def test_equal_duration_audio_with_delayed_origin_is_rejected():
    probe=dict(streams=[dict(codec_type='video',codec_name='h264',pix_fmt='yuv420p',width=1920,height=1080,avg_frame_rate='16/1',r_frame_rate='16/1',nb_read_frames='2',duration='0.125',start_time='0'),dict(codec_type='audio',codec_name='aac',sample_rate='48000',channels=1,duration='0.125',start_time='2')])
    frames=dict(frames=[dict(best_effort_timestamp_time='0'),dict(best_effort_timestamp_time='0.0625')])
    with pytest.raises(ValueError):module().validate_probe(probe,frames,fps=16,total_frames=2,channels=1)

def test_aac_packet_timing_requires_contiguous_effective_sample_origin():
    from copy import deepcopy
    good=[dict(pts=-1024,duration=1024,side_data_list=[dict(side_data_type='Skip Samples',skip_samples=1024)]),dict(pts=0,duration=1024),dict(pts=1024,duration=976)]
    assert module().validate_audio_packets(good,2000)==1024
    for index,pts in [(0,48000),(1,100),(2,2048)]:
        bad=deepcopy(good);bad[index]['pts']=pts
        with pytest.raises(ValueError):module().validate_audio_packets(bad,2000)

def test_consumer_replay_reproduces_encoded_bytes(context):
    from image_helpers import write_png
    from video_ai.media.subtitles import ass_text
    from types import SimpleNamespace
    run,folder,kw=context;seq=folder/'video-frames';seq.mkdir()
    for i in range(1,5):write_png(seq/f'frame_{i:06d}.png',1920,1080,(i*40,20,10))
    audio=folder/'narration.wav'
    with wave.open(str(audio),'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\0\0'*12000)
    (folder/'fonts').mkdir();(folder/'subtitles.ass').write_text(ass_text([],CompositionSettings()),encoding='utf-8')
    module().encode_composition(seq,audio,fps=16,frames=4,channels=1,**kw)
    assert len(module().verify_encoded_bytes(SimpleNamespace(output_fps=16),channels=1,audio=audio,**kw))==2

def test_blended_pixels_are_rederived_from_originals(context):
    from image_helpers import write_png
    from types import SimpleNamespace
    run,folder,kw=context;a=write_png(folder/'a.png',4,2,(0,20,240));b=write_png(folder/'b.png',4,2,(255,100,0));target=write_png(folder/'bad.png',4,2,(10,10,10))
    contributors=[dict(frame_identity=thaw(hash_file(p)),weight_numerator=1,weight_denominator=2) for p in (a,b)]
    plan=SimpleNamespace(ordered_frame_map=[dict(output_frame=0,contributors=contributors)])
    with pytest.raises(ValueError):module().validate_blended_pixels(plan,[target],**kw)
    target.unlink()
    module().blend_frame(a,b,target,left_numerator=1,right_numerator=1,denominator=2,**kw)
    assert len(module().validate_blended_pixels(plan,[target],**kw))==3


def test_normalized_music_is_rederived_from_configured_original(context):
    run,folder,kw=context;source=folder/'original.wav';normalized=folder/'music.f32'
    with wave.open(str(source),'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\x01\x02'*1000)
    module().command([*module().ffmpeg(kw['config']),'-i',str(source),'-vn','-ar','48000','-ac','2','-c:a','pcm_f32le','-f','f32le',str(normalized)],operation='normalize_music',**kw)
    module().validate_normalized_music(source,normalized,**kw)
    normalized.write_bytes(bytes(normalized.stat().st_size))
    with pytest.raises(ValueError,match='original source'):module().validate_normalized_music(source,normalized,**kw)
