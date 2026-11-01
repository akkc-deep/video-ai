"""Real CPU media: discard exactly frame 320, preserving every earlier RGB frame."""
import importlib
import json
from pathlib import Path
import subprocess

import pytest

FFMPEG = Path('D:/VideoSi/tools/ffmpeg/bin/ffmpeg.exe')
FFPROBE = FFMPEG.with_name('ffprobe.exe')


@pytest.fixture
def media_root(tmp_path):
    root = tmp_path/'media'; (root/'output').mkdir(parents=True)
    (root/'case.json').write_text(json.dumps({'runtime': {'tools': {
        'ffmpeg': str(FFMPEG), 'ffprobe': str(FFPROBE)}}}), encoding='utf-8')
    (root/'graph.json').write_text(json.dumps({'129:98': {'inputs': {'width': 64, 'height': 32}}}), encoding='utf-8')
    return root


def make_video(root, count=321, fps=16, offset=False):
    subprocess.run([str(FFMPEG), '-nostdin', '-v', 'error', '-f', 'lavfi',
        '-i', f'testsrc2=s=64x32:r={fps}', '-frames:v', str(count),
        *(['-vf','setpts=PTS+1/TB'] if offset else []), '-c:v', 'libx264',
        '-pix_fmt','yuv420p',str(root/'output/candidate.mp4')], check=True, timeout=30)


def audit(root, **changes):
    return importlib.import_module('video_ai.experiments.whole_scene_media').audit_output(root,
        dict(filename='candidate.mp4', subfolder='', type='output', **changes))


def test_real_321_to_320_preserves_all_retained_rgb_and_pts(media_root):
    root=media_root; make_video(root)
    result=audit(root)
    assert result['generated']['frames'] == 321
    assert result['review']['frames'] == 320
    assert result['review']['duration'] == 20.0
    assert result['rgb_preserved'] is True
    assert result['full_video_observation'] == 'unverified'
    mapping=json.loads((root/'mapping.json').read_text(encoding='utf-8'))
    assert len(mapping['frames']) == 320
    assert mapping['frames'][0] == {'review_frame': 0, 'source_frame': 0, 'pts': '0/16'}
    assert mapping['frames'][-1] == {'review_frame': 319, 'source_frame': 319, 'pts': '319/16'}
    assert len(list((root/'native-frames').glob('*.png'))) == 321
    assert len(json.loads((root/'rgb-statistics.json').read_text(encoding='utf-8'))['frames']) == 321
    assert (root/'samples.png').is_file()
    # The lossless RGB audit movie is not supported by many OS H.264 decoders.
    # Every new audit must also supply a broadly supported, clearly lossy copy.
    playback=json.loads((root/'playback-review.json').read_text(encoding='utf-8'))
    p=subprocess.run([str(FFPROBE),'-v','error','-show_streams','-of','json',
                      str(root/'review-playback.mp4')],capture_output=True,text=True,check=True)
    stream=json.loads(p.stdout)['streams'][0]
    assert stream['profile']=='High'
    assert stream['pix_fmt']=='yuv420p'
    assert stream['nb_frames']=='320'
    assert stream['duration']=='20.000000'
    assert playback['lossless'] is False
    assert playback['source_frame_range']==[0,320]
    assert playback['generated_identity']==result['generated_identity']
    assert playback['lossless_review_identity']==result['review_identity']
    raw=(root/'review-playback.mp4').read_bytes()
    assert raw.index(b'moov') < raw.index(b'mdat')


@pytest.mark.parametrize('count,fps', [(320,16), (321,24), (322,16)])
def test_wrong_native_output_cannot_become_twenty_second_evidence(media_root,count,fps):
    make_video(media_root,count,fps)
    with pytest.raises(ValueError): audit(media_root)
    assert not (media_root/'media.json').exists()


def test_malicious_output_cannot_read_outside_owned_output(media_root):
    from video_ai.experiments.whole_scene_media import audit_output
    for output in [dict(filename='../outside.mp4',subfolder='',type='output'),
                   dict(filename='a.mp4',subfolder='../',type='output'),
                   dict(filename='a.mp4',subfolder='',type='input')]:
        with pytest.raises(ValueError): audit_output(media_root,output)


def test_nonzero_native_pts_origin_cannot_claim_i_over_16_mapping(media_root):
    make_video(media_root,offset=True)
    with pytest.raises(ValueError,match='PTS'): audit(media_root)


@pytest.mark.parametrize('target',['review.mp4','native-frames/frame_000319.png','mapping.json'])
def test_cached_audit_rejects_modified_review_or_native_png(media_root,target):
    make_video(media_root);audit(media_root)
    (media_root/target).write_bytes(b'changed')
    with pytest.raises(ValueError,match='identity|changed'): audit(media_root)


def test_legacy_rgb_review_gets_a_separate_playable_copy_without_overwriting_evidence(media_root):
    from video_ai.experiments.whole_scene_media import create_playback_review
    make_video(media_root); result=audit(media_root)
    # Simulate an existing, already frozen audit created before playback support.
    (media_root/'review-playback.mp4').unlink()
    (media_root/'playback-review.json').unlink()
    before={p.name:p.read_bytes() for p in [media_root/'media.json',media_root/'review.mp4',
                                          media_root/'mapping.json',media_root/'output/candidate.mp4']}
    playback=create_playback_review(media_root)
    assert playback['video']['frames']==320
    assert playback['video']['duration']==20.0
    assert playback['full_video_observation']=='unverified'
    assert playback==create_playback_review(media_root)
    after={p.name:p.read_bytes() for p in [media_root/'media.json',media_root/'review.mp4',
                                         media_root/'mapping.json',media_root/'output/candidate.mp4']}
    assert after==before
    (media_root/'review-playback.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError,match='identity|changed'): create_playback_review(media_root)
