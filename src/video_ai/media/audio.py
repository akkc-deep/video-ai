"""Full WAV validation and non-trimming PCM standardization."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import wave
from uuid import uuid4

from ..runtime.environment import build_child_env
from ..runtime.manifest import hash_file, thaw, validate_unit
from ..runtime.processes import run_logged


@dataclass(frozen=True)
class SpeechLimits:
    min_seconds: float = .05
    max_seconds: float = 120

    def __post_init__(self):
        if (any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0
                for v in (self.min_seconds,self.max_seconds)) or self.max_seconds < self.min_seconds):
            raise ValueError('speech duration limits must be positive finite and ordered')


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    sha256: str
    bytes: int
    sample_rate: int
    channels: int
    sample_width: int
    samples: int

    @property
    def duration(self): return self.samples / self.sample_rate


def audio_command(args, *, paths, logger, unit_id, timeout=300):
    result = run_logged(tuple(str(a) for a in args), cwd=logger.run_dir, env=build_child_env(paths),
                        timeout=timeout, logger=logger, stage='speech', unit_id=unit_id)
    if result.returncode != 0 or result.timed_out:
        raise RuntimeError(f'{unit_id}: audio command failed; {result.stderr_path}')
    return result


def _probe(path, *, config, paths, logger, unit_id):
    result = audio_command((config.tools['ffprobe'], '-v','error','-show_streams','-show_format','-of','json',path),
                           paths=paths, logger=logger, unit_id=unit_id)
    data = json.loads(result.stdout_path.read_text(encoding='utf-8'))
    streams = data.get('streams', [])
    if len(streams) != 1 or streams[0].get('codec_type') != 'audio':
        raise ValueError(f'{unit_id}: expected exactly one audio stream')
    stream = streams[0]
    rate, channels = int(stream.get('sample_rate',0)), stream.get('channels',0)
    if rate <= 0 or type(channels) is not int or channels <= 0:
        raise ValueError(f'{unit_id}: invalid sample rate/channels')
    return data, rate, channels, result


def _decode(path, *, config, paths, logger, unit_id):
    return audio_command((config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',path,'-f','null','-'),
                         paths=paths, logger=logger, unit_id=unit_id)


def _wave_duration(path, *, require_audio=False):
    try:
        with wave.open(str(path),'rb') as f:
            frames, size, rate = f.getnframes(), f.getsampwidth()*f.getnchannels(), f.getframerate()
            if frames <= 0 or rate <= 0 or f.getcomptype() != 'NONE': raise ValueError('empty/compressed WAV')
            # Prove the declared payload exists; ffmpeg may tolerate a short RIFF body.
            remaining = frames
            audible = False
            while remaining:
                count = min(remaining, 65536)
                data = f.readframes(count)
                if len(data) != count*size: raise ValueError('truncated WAV frames')
                if require_audio and any(data): audible = True
                remaining -= count
            if require_audio and not audible: raise ValueError('all-silent PCM speech')
            return frames/rate
    except wave.Error:
        return None  # Compressed WAV still needs reliable probe duration plus full decode.


def standardize_wav(raw: Path, target: Path, *, config, paths, logger, unit_id, limits: SpeechLimits) -> AudioInfo:
    return _standardize_wav(raw,target,config=config,paths=paths,logger=logger,unit_id=unit_id,
                           limits=limits,identity=hash_file,make_info=_sha_audio_info,production=False)


def _sha_audio_info(identity,samples):
    return AudioInfo(Path(identity.path),identity.sha256,identity.bytes,48000,1,2,samples)


def standardize_production_wav(raw: Path, target: Path, *, config, paths, logger, unit_id, limits: SpeechLimits):
    """Normalize the full WAV with stable stamps, without calculating any SHA."""
    from ..runtime.production_state import ArtifactStamp
    from ..planning.production_timeline import ProductionAudioInfo
    return _standardize_wav(raw,target,config=config,paths=paths,logger=logger,unit_id=unit_id,
        limits=limits,identity=ArtifactStamp.read,
        make_info=lambda stamp,samples:ProductionAudioInfo(stamp,48000,1,2,samples),production=True)


def _sync_audio(path):
    with path.open('r+b') as file:
        file.flush()
        os.fsync(file.fileno())


def _standardize_wav(raw,target,*,config,paths,logger,unit_id,limits,identity,make_info,production):
    validate_unit('speech', unit_id)
    raw = paths.policy.validate_write(raw, 'run')
    target = paths.policy.validate_write(target, 'run')
    if not all(p.is_relative_to(logger.run_dir) for p in (raw,target)):
        raise ValueError('audio must stay in the current run')
    if target.exists(): raise FileExistsError(target)
    with raw.open('rb') as file: header = file.read(12)
    if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WAVE':
        raise ValueError(f'{unit_id}: invalid WAV header')
    if production: _sync_audio(raw)
    source_identity = identity(raw)
    source_wave_duration = _wave_duration(raw)
    source, rate, channels, source_probe = _probe(raw, config=config, paths=paths, logger=logger, unit_id=unit_id)
    try:
        source_duration = float(source['streams'][0].get('duration', source.get('format',{}).get('duration')))
        if not math.isfinite(source_duration) or source_duration <= 0: raise ValueError('invalid duration')
    except (TypeError,ValueError):
        source_duration = source_wave_duration
    if source_duration is None: raise ValueError(f'{unit_id}: source duration cannot be proven')
    source_decode = _decode(raw, config=config, paths=paths, logger=logger, unit_id=unit_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    conversion = audio_command((config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',raw,
                                '-ar','48000','-ac','1','-c:a','pcm_s16le',target),
                               paths=paths, logger=logger, unit_id=unit_id)
    if production: _sync_audio(target)
    target_identity = identity(target) if production else None
    target_data, _, _, target_probe = _probe(target, config=config, paths=paths, logger=logger, unit_id=unit_id)
    target_decode = _decode(target, config=config, paths=paths, logger=logger, unit_id=unit_id)
    with wave.open(str(target),'rb') as file:
        if (file.getframerate(),file.getnchannels(),file.getsampwidth(),file.getcomptype()) != (48000,1,2,'NONE'):
            raise ValueError(f'{unit_id}: expected 48kHz mono PCM16')
        samples = file.getnframes()
    duration = _wave_duration(target,require_audio=production)
    if samples <= 0 or duration is None or not limits.min_seconds <= duration <= limits.max_seconds:
        raise ValueError(f'{unit_id}: abnormal speech duration {duration}; limits {limits}')
    tolerance = max(1/rate,1/48000)+1/48000
    if abs(source_duration-duration) > tolerance or (source_wave_duration is not None and abs(source_wave_duration-duration) > tolerance):
        raise ValueError(f'{unit_id}: source/PCM duration changed; possible truncation')
    fresh = identity(raw)
    if (fresh != source_identity if production else fresh.sha256 != source_identity.sha256):
        raise OSError(f'{unit_id}: raw WAV changed')
    final_identity = identity(target)
    if production and final_identity != target_identity: raise OSError(f'{unit_id}: PCM WAV changed')
    info = make_info(final_identity,samples)
    validation_name=(f'audio/{unit_id}/{uuid4().hex}.validation.json' if production else f'audio/{unit_id}.validation.json')
    logger.save_json(validation_name, dict(raw=thaw(source_identity), pcm=thaw(info),
        duration=duration, source_duration=source_duration, source_sample_rate=rate, source_channels=channels,
        limits=thaw(limits), source_probe=source, pcm_probe=target_data,
        commands=[thaw(c) for c in (source_probe,source_decode,conversion,target_probe,target_decode)]))
    return info
