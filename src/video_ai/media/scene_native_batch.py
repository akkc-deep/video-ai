"""Complete native RGB24 proofs with a single aggregate PNG inspection record."""
from pathlib import Path
from time import monotonic
import hashlib

from .frames import _command, _count, _directory, _sequence
from .images import _deadline, _remaining, _record_name
from ..runtime.execution_limits import command_timeout
from .video import _dimensions, _video_path, inspect_video
from .scene_upscale import _decode, verify_png, png_sequence_hashes
from ..runtime.manifest import hash_file, thaw
from ..runtime.timeline_checks import _again


def extract_native_scene_batch(source, directory, *, expected_frames, width, height,
                               config, paths, logger, unit_id, timeout=1200, reuse_existing=False,
                               aggregate_png=False):
    """Validate every PNG and every source pixel before returning any extraction.

    Aggregate checking decodes the complete numeric PNG sequence and compares
    every RGB24 frame digest; the historical whole-scene path retains its PNG
    checker. Both summarize evidence together, independent of frame count.
    No sampling, source re-encoding or deadline renewal occurs.
    """
    deadline = _deadline(timeout, monotonic())
    _count(expected_frames); _dimensions(width, height)
    if expected_frames > 320 and not aggregate_png:
        raise ValueError('whole scene batch exceeds 320 retained frames')
    if type(reuse_existing) is not bool:
        raise ValueError('reuse_existing must be bool')
    source = _video_path(source, logger, paths)
    directory = _directory(directory, logger, paths)
    before = hash_file(source)
    remaining = lambda: command_timeout(_remaining(deadline, monotonic()),300)
    info, evidence = inspect_video(source, width=width, height=height, config=config, paths=paths,
        logger=logger, unit_id=unit_id, stage='upscale', timeout=remaining())
    if info['frames'] != expected_frames:
        raise ValueError('retained source count differs')
    _again({'source': before})
    if not reuse_existing:
        if directory.exists() or directory.is_symlink():
            raise FileExistsError(directory)
        directory.parent.mkdir(parents=True, exist_ok=True)
        directory.mkdir()
        command = _command((config.tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-xerror',
            '-i', source, '-map', '0:v:0', '-vf', 'format=rgb24', '-fps_mode', 'passthrough',
            '-start_number', '1', directory/'frame_%06d.png'), paths=paths, logger=logger,
            unit_id=unit_id, timeout=remaining())
        evidence = [*evidence, command.stdout_path, command.stderr_path]
    def owned_sequence():
        sequence = _sequence(directory, expected_frames, logger)
        for path in sequence:
            if path.stat().st_nlink != 1:
                raise ValueError('non-aliased owned PNG required')
        return sequence
    sequence = owned_sequence()
    identities = {str(path): hash_file(path) for path in sequence}
    raw = _decode(source, config, timeout=remaining())
    size = width * height * 3
    if len(raw) != expected_frames * size:
        raise ValueError('native retained decode frame count differs')
    rows = []
    digests = (png_sequence_hashes(sequence,width=width,height=height,config=config,
        timeout=remaining(),remaining_timeout=remaining) if aggregate_png else None)
    for index, path in enumerate(sequence):
        if digests is not None:
            digest=digests[index]
            same_pixels=digest==hashlib.sha256(raw[index*size:(index+1)*size]).hexdigest()
        else:
            pixels=verify_png(path, width=width, height=height, config=config, timeout=remaining(),
                             remaining_timeout=remaining)
            digest=hashlib.sha256(pixels).hexdigest()
            same_pixels=pixels==raw[index*size:(index+1)*size]
        _remaining(deadline, monotonic())
        if not same_pixels:
            raise ValueError('PNG pixels differ from retained source frame')
        rows.append(dict(index=index, image=thaw(identities[str(path)]),
            decoded_rgb24_sha256=digest))
    def recheck():
        owned_sequence()
        _again(dict(identities, source=before))
        _remaining(deadline, monotonic())
    recheck()
    report = logger.save_json(_record_name(logger, 'native-batch', unit_id, 'upscale'),
        dict(schema_version=1, algorithm='scene_native_png_batch_v1', source=thaw(before),
             directory=str(directory), expected_frames=expected_frames, width=width, height=height,
             recovered_existing=reuse_existing, frames=rows))
    # The final actual logger write can execute a slow/drifting upstream guard.
    # Never return an accepted sequence whose bytes changed inside that guard.
    recheck()
    artifacts = [{k: getattr(identities[str(path)], k) for k in ('path','bytes','sha256')}
                 for path in sequence]
    return artifacts, [*evidence, report]
