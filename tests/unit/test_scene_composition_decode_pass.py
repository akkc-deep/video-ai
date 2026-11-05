"""Real offline media validation decodes video and audio in one ffmpeg pass."""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from video_ai.runtime import production_scene_composition as composition
from video_ai.runtime.scene_revision_records import artifact, verify_artifact


def test_candidate_validation_uses_one_complete_av_decode(runtime_run, monkeypatch):
    run, config, _ = runtime_run
    target = run/'candidate-fixture.mp4'
    subprocess.run([str(config.tools['ffmpeg']), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
        'color=c=blue:s=1920x1080:r=16', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono',
        '-frames:v', '3', '-t', '0.1875', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '1', str(target)],
        check=True, capture_output=True)
    probe = json.loads(subprocess.run([str(config.tools['ffprobe']), '-v', 'error', '-count_frames',
        '-show_streams', '-show_format', '-of', 'json', str(target)], check=True, capture_output=True).stdout)
    bound = artifact(target, root=run)
    context = dict(frozen=SimpleNamespace(config=config), timeline=SimpleNamespace(total_frames=3),
        composition_tool_stamps=[], composition_store=SimpleNamespace(media_cache=set(),
            validate_artifact=lambda value: verify_artifact(value, root=run)))
    original = subprocess.run
    decodes = []

    def counted(args, **kw):
        if Path(args[0]).name.lower() == 'ffmpeg.exe':
            decodes.append(args)
        return original(args, **kw)

    monkeypatch.setattr(composition.subprocess, 'run', counted)
    composition._inspect(context, bound, probe)
    assert len(decodes) == 1
    # The invocation admission still avoids replaying a verified unchanged film.
    composition._inspect(context, bound, probe)
    assert len(decodes) == 1
