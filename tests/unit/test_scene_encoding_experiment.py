"""Encoding changes one factor; lossy pixels cannot be silently accepted."""
from copy import deepcopy
from pathlib import Path
import pytest


def test_nvenc_preserves_original_mapping_audio_subtitles_and_timing(tmp_path):
    from video_ai.experiments.scene_encoding_experiment import encoding_args
    original=encoding_args('ffmpeg',tmp_path,tmp_path/'baseline.mp4',encoder='libx264')
    candidate=encoding_args('ffmpeg',tmp_path,tmp_path/'nvenc.mp4',encoder='h264_nvenc')
    assert original[original.index('-c:v')+1:original.index('-fps_mode')]==[
        'libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p']
    assert candidate[candidate.index('-c:v')+1:candidate.index('-fps_mode')]==[
        'h264_nvenc','-preset','p4','-rc','constqp','-qp','18','-pix_fmt','yuv420p']
    assert candidate[:candidate.index('-c:v')]==original[:original.index('-c:v')]
    assert candidate[candidate.index('-fps_mode'):-1]==original[original.index('-fps_mode'):-1]
    with pytest.raises(ValueError):encoding_args('ffmpeg',tmp_path,tmp_path/'x.mp4',encoder='guessed')


def test_capability_is_not_claimed_as_driver_or_quality_validation():
    from video_ai.experiments.scene_encoding_experiment import capability_from_text
    assert capability_from_text('encoders','')['status']=='unsupported'
    result=capability_from_text('V....D h264_nvenc NVENC','preset p4 rc constqp qp')
    assert result['status']=='available_driver_unverified'
    assert result['gpu_executed'] is False
    assert capability_from_text('h264_nvenc','preset p4 rc qp')['status']=='unsupported'


def test_full_rgb_pts_color_contract_has_explicit_rejection():
    from video_ai.experiments.scene_encoding_experiment import compare_evidence
    baseline=dict(frame_rgb_sha256=['a'*64,'b'*64],pts=['0','1/16'],
        frame_count=2,width=1920,height=1080,fps='16/1',
        colors=dict(color_range='tv',color_space='bt709',color_transfer='bt709',color_primaries='bt709'))
    assert compare_evidence(baseline,deepcopy(baseline))['status']=='awaiting_human_review'
    for field,value in [('frame_rgb_sha256',['c'*64,'b'*64]),('pts',['0','1/15']),
                        ('colors',{}),('frame_count',1)]:
        changed=deepcopy(baseline);changed[field]=value
        result=compare_evidence(baseline,changed)
        assert result['status']==('rejected_pixel_contract' if field=='frame_rgb_sha256' else 'rejected_media_contract')


def test_encoded_evidence_uses_one_decode_with_actual_timebase(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    import video_ai.experiments.scene_encoding_experiment as encoding
    commands=[]
    def command(args,**kwargs):
        commands.append(args)
        if args[0]=='ffprobe':
            return SimpleNamespace(returncode=0,stdout=json.dumps({'streams':[dict(codec_type='video',
                width=1920,height=1080,avg_frame_rate='16/1',time_base='1/16384')]}).encode())
        return SimpleNamespace(returncode=0,stdout=('#tb 0: 1/16384\n0, 0, 0, 1024, 6220800, '+'a'*64+
            '\n0, 1024, 1024, 1024, 6220800, '+'b'*64+'\n').encode())
    monkeypatch.setattr(encoding.subprocess,'run',command)
    result=encoding.inspect_encoded(tmp_path/'video.mp4',ffmpeg='ffmpeg',ffprobe='ffprobe',expected_frames=2)
    assert result['pts']==['0','1/16'] and result['frame_rgb_sha256']==['a'*64,'b'*64]
    assert len(commands)==2 and '-show_frames' not in commands[0]
