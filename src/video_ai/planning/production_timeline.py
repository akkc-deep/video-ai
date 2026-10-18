"""Stamp-based, lossless refined narration timeline without review consumers."""
from dataclasses import dataclass, fields
import json
from pathlib import Path
from typing import Mapping

from ..config import TimelineSettings
from ..runtime.manifest import thaw
from ..runtime.production_state import ArtifactStamp
from .segments import SegmentedScript, TextSpan, segment_text, validate_segments
from .timeline import (
    SettingSamples, SubtitleEvent, SilenceInterval, SemanticBoundary,
    _assemble_timeline, _integer,
)


def _object(data, kind):
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(kind)}:
        raise ValueError(f'invalid {kind.__name__} fields')
    return dict(data)


def _array(data, name):
    if not isinstance(data, (list, tuple)):
        raise ValueError(f'{name}: expected array')
    return data


def _strict_json(value):
    return json.dumps(thaw(value), sort_keys=True, allow_nan=False)


@dataclass(frozen=True)
class ProductionAudioInfo:
    stamp: ArtifactStamp
    sample_rate: int
    channels: int
    sample_width: int
    samples: int

    @property
    def path(self) -> Path: return Path(self.stamp.path)

    @property
    def bytes(self) -> int: return self.stamp.bytes

    @property
    def duration(self) -> float: return self.samples / self.sample_rate

    def as_dict(self): return thaw(self)

    @classmethod
    def from_dict(cls, data):
        try:
            d = _object(data, cls)
            d['stamp'] = ArtifactStamp(**_object(d['stamp'], ArtifactStamp))
            result = cls(**d)
            _validate_audio(result)
            return result
        except (TypeError, KeyError, AttributeError) as exc:
            raise ValueError('invalid production audio structure') from exc


def _validate_audio(info):
    if not isinstance(info, ProductionAudioInfo) or not isinstance(info.stamp, ArtifactStamp):
        raise ValueError('invalid production audio info')
    # Reconstruct the stamp without touching the filesystem: this is a pure planner.
    ArtifactStamp(**vars(info.stamp))
    for name in ('sample_rate', 'channels', 'sample_width', 'samples', 'bytes'):
        _integer(getattr(info, name), name, 1)
    if (info.sample_rate, info.channels, info.sample_width) != (48000, 1, 2):
        raise ValueError('expected 48kHz mono PCM16')
    if info.bytes < info.samples * 2:
        raise ValueError('PCM stamp too short')


@dataclass(frozen=True)
class ProductionNarrationClip:
    unit_id: str
    span_index: int
    text_start: int
    text_end: int
    text: str
    pcm: ProductionAudioInfo
    samples: int
    start_sample: int
    end_sample: int
    pause_kind: str
    pause_samples: int
    pause_end_sample: int
    start_frame: int
    end_frame: int


@dataclass(frozen=True)
class ProductionTimeline:
    schema_version: int
    sample_rate: int
    channels: int
    sample_width: int
    native_fps: int
    output_fps: int
    frame_rate_conversion: bool
    effective_settings: TimelineSettings
    setting_samples: SettingSamples
    original_text: str
    has_bom: bool
    source_spans: tuple[TextSpan, ...]
    clips: tuple[ProductionNarrationClip, ...]
    subtitles: tuple[SubtitleEvent, ...]
    silences: tuple[SilenceInterval, ...]
    total_speech_samples: int
    total_silence_samples: int
    total_samples: int
    total_frames: int
    video_padding_samples: int
    semantic_boundaries: tuple[SemanticBoundary, ...]

    def as_dict(self): return thaw(self)

    @classmethod
    def from_dict(cls, data):
        try:
            d = _object(data, cls)
            d['effective_settings'] = TimelineSettings(**_object(d['effective_settings'], TimelineSettings))
            d['setting_samples'] = SettingSamples(**_object(d['setting_samples'], SettingSamples))
            for name, kind in (
                ('source_spans', TextSpan), ('subtitles', SubtitleEvent),
                ('silences', SilenceInterval), ('semantic_boundaries', SemanticBoundary),
            ):
                d[name] = tuple(kind(**_object(item, kind)) for item in _array(d[name], name))
            clips = []
            for item in _array(d['clips'], 'clips'):
                clip = _object(item, ProductionNarrationClip)
                clip['pcm'] = ProductionAudioInfo.from_dict(clip['pcm'])
                clips.append(ProductionNarrationClip(**clip))
            d['clips'] = tuple(clips)
            result = cls(**d)
            validate_production_timeline(result)
            return result
        except (TypeError, KeyError, AttributeError) as exc:
            raise ValueError('invalid production timeline structure') from exc


def _validate_refinement(script):
    if not isinstance(script, SegmentedScript) or type(script.has_bom) is not bool:
        raise ValueError('invalid script')
    if not isinstance(script.text, str) or not isinstance(script.spans, tuple):
        raise ValueError('invalid script fields')
    validate_segments(script.text, script.spans)
    position = 0
    for original in segment_text(script.text):
        children = []
        while position < len(script.spans) and script.spans[position].start < original.end:
            child = script.spans[position]
            if child.start < original.start or child.end > original.end:
                raise ValueError('refinement merges original boundaries')
            children.append(child)
            position += 1
        if not children or children[0].start != original.start or children[-1].end != original.end:
            raise ValueError('incomplete original boundary coverage')
        if original.kind == 'skip':
            if children != [original]: raise ValueError('original skip must remain unchanged')
        elif (any(c.kind != 'speech' or c.boundary != 'phrase' for c in children[:-1])
              or children[-1].kind != 'speech' or children[-1].boundary != original.boundary):
            raise ValueError('refinement changes original speech boundary')
    if position != len(script.spans): raise ValueError('extra refined spans')


def build_production_timeline(script: SegmentedScript, audio: Mapping[str, ProductionAudioInfo],
                              *, settings: TimelineSettings, fps: int = 16) -> ProductionTimeline:
    _validate_refinement(script)
    if type(fps) is not int or fps != 16: raise ValueError('production fps must be 16')
    if not isinstance(settings, TimelineSettings): raise ValueError('invalid timeline settings')
    settings = TimelineSettings(**vars(settings))
    units = [s for s in script.spans if s.kind == 'speech']
    if not units or not isinstance(audio, Mapping) or set(audio) != {s.unit_id for s in units}:
        raise ValueError('speech audio must match every unit exactly')
    for info in audio.values(): _validate_audio(info)
    return _assemble_timeline(script, audio, settings=settings, fps=fps,
                              clip_type=ProductionNarrationClip, timeline_type=ProductionTimeline)


def validate_production_timeline(timeline: ProductionTimeline) -> None:
    if not isinstance(timeline, ProductionTimeline): raise ValueError('expected ProductionTimeline')
    try:
        ids = [c.unit_id for c in timeline.clips]
        if len(set(ids)) != len(ids): raise ValueError('duplicate production timeline clip')
        expected = build_production_timeline(
            SegmentedScript(timeline.original_text, timeline.has_bom, timeline.source_spans),
            {c.unit_id:c.pcm for c in timeline.clips},
            settings=timeline.effective_settings, fps=timeline.output_fps,
        )
        if _strict_json(expected) != _strict_json(timeline):
            raise ValueError('production timeline differs from canonical sample coverage')
    except (TypeError, AttributeError, KeyError) as exc:
        raise ValueError('invalid production timeline field') from exc
