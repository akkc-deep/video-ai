"""One complete RGB decode per encoded media, shared by quality and fast."""
import json
from pathlib import Path

from .wan_fast_profiles import write_once


def black_frame_summary(rgb, *, width, height):
    import numpy as np
    stride = width * height * 3
    if stride <= 0 or not rgb or len(rgb) % stride:
        raise ValueError('truncated RGB24 decode')
    frames = np.frombuffer(rgb, dtype=np.uint8).reshape(-1, height*width, 3)
    run = longest = 0
    for frame in frames:
        near_black = int(np.count_nonzero(np.all(frame <= 1, axis=1)))
        run = run + 1 if near_black / (width*height) >= .999 else 0
        longest = max(longest, run)
    return dict(frames=len(frames), suspect_black=longest >= 2, longest_black_run=longest)


def inspect_media(root, source, *, width, height, expected_frames, ffmpeg, ffprobe):
    from .wan_fast_experiment import baseline_api
    from video_ai.media.video import validate_video_probe
    api = baseline_api()
    root, source = Path(root), Path(source)
    source_sha = api.file_sha(source)
    probe = api.media_command(root, 'probe', [ffprobe, '-v', 'error', '-count_frames',
        '-show_streams', '-show_format', '-of', 'json', source])
    frames = api.media_command(root, 'frames', [ffprobe, '-v', 'error', '-show_frames', '-of', 'json', source])
    info = validate_video_probe(json.loads(probe), json.loads(frames), width=width, height=height)
    if info['frames'] != expected_frames:
        raise ValueError('complete generated/retained frame budget differs')
    # Same full decode also answers the black-frame signal. No second ffmpeg
    # decode, no per-frame subprocess, and no claims about NaN in encoded uint8.
    rgb = api.media_command(root, 'decode-rgb24', [ffmpeg, '-nostdin', '-v', 'error', '-xerror',
        '-i', source, '-map', '0:v:0', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    black = black_frame_summary(rgb, width=width, height=height)
    if black['frames'] != expected_frames:
        raise ValueError('full decode frame count differs')
    write_once(root/'media-checks'/(source_sha+'.json'), dict(source_sha256=source_sha,
        technical=info, **black, quality='requires_explicit_human_judgment',
        finite_check='Comfy VAE IMAGE before uint8; see fast-node-evidence.jsonl'))
    return info
