"""Literal sample expectations protect the independent production timeline."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from video_ai.config import TimelineSettings
from video_ai.planning.segments import SegmentedScript, TextSpan, segment_text
from video_ai.runtime.production_state import ArtifactStamp


def audio(samples):
    from video_ai.planning.production_timeline import ProductionAudioInfo
    return ProductionAudioInfo(ArtifactStamp('D:/pcm.wav', samples * 2 + 44, 123), 48000, 1, 2, samples)


def refined():
    text = '甲乙。\r\n丙。'
    return SegmentedScript(text, True, (
        TextSpan(0, 1, '甲', 'speech', 'phrase', 'speech_0001'),
        TextSpan(1, 3, '乙。', 'speech', 'sentence', 'speech_0002'),
        TextSpan(3, 5, '\r\n', 'skip', 'newline', None),
        TextSpan(5, 7, '丙。', 'speech', 'sentence', 'speech_0003'),
    ))


def make_timeline():
    from video_ai.planning.production_timeline import build_production_timeline
    return build_production_timeline(refined(), {
        'speech_0001': audio(4800), 'speech_0002': audio(7200), 'speech_0003': audio(9600),
    }, settings=TimelineSettings(.1, .2, .05, .025))


def test_lossless_refinement_exact_samples_and_original_pauses():
    t = make_timeline()
    assert [(c.start_sample, c.end_sample, c.pause_kind, c.pause_samples) for c in t.clips] == [
        (2400, 7200, 'none', 0), (7200, 14400, 'paragraph', 9600), (24000, 33600, 'none', 0)]
    assert [(s.kind, s.start_sample, s.end_sample) for s in t.silences] == [
        ('opening', 0, 2400), ('paragraph', 14400, 24000), ('closing', 33600, 34800)]
    assert (t.total_speech_samples, t.total_silence_samples, t.total_samples, t.total_frames, t.video_padding_samples) == (21600, 13200, 34800, 12, 1200)
    assert [(c.start_frame, c.end_frame) for c in t.clips] == [(1, 2), (2, 5), (8, 11)]
    assert t.original_text == '甲乙。\r\n丙。' and t.has_bom is True
    assert t.source_spans == refined().spans
    assert [(b.pause_end_sample, b.frame, b.boundary) for b in t.semantic_boundaries] == [(7200, 2, 'phrase'), (24000, 8, 'sentence')]


def test_production_serialization_has_real_stamp_without_sha():
    from video_ai.planning.production_timeline import ProductionTimeline, ProductionAudioInfo
    t = make_timeline()
    data = json.loads(json.dumps(t.as_dict(), allow_nan=False))
    assert data['clips'][0]['pcm'] == {'stamp': {'path': 'D:/pcm.wav', 'bytes': 9644, 'mtime_ns': 123}, 'sample_rate': 48000, 'channels': 1, 'sample_width': 2, 'samples': 4800}
    assert ProductionTimeline.from_dict(data) == t
    assert ProductionAudioInfo.from_dict(data['clips'][0]['pcm']).duration == .1
    assert t.clips[0].pcm.path == Path('D:/pcm.wav')
    assert t.clips[0].pcm.bytes == 9644


def test_old_timeline_still_rejects_refinements():
    from video_ai.media.audio import AudioInfo
    from video_ai.planning.timeline import build_timeline
    infos = {f'speech_{i:04d}': AudioInfo(Path('D:/pcm.wav'), 'a'*64, n*2+44, 48000, 1, 2, n) for i, n in enumerate((4800, 7200, 9600), 1)}
    with pytest.raises(ValueError, match='noncanonical original boundaries'):
        build_timeline(refined(), infos, settings=TimelineSettings(), fps=16)


@pytest.mark.parametrize('change', ['skip_split', 'speech_merge', 'original_boundary', 'interior_boundary'])
def test_refinement_cannot_change_original_boundaries(change):
    from video_ai.planning.production_timeline import build_production_timeline
    script = refined()
    if change == 'skip_split':
        spans = (*script.spans[:2], TextSpan(3,4,'\r','skip','newline',None), TextSpan(4,5,'\n','skip','newline',None), script.spans[-1])
    elif change == 'speech_merge':
        text = '甲，乙。'
        script = SegmentedScript(text, False, (TextSpan(0,5,text,'speech','sentence','speech_0001'),))
        spans = script.spans
    elif change == 'original_boundary':
        spans = (script.spans[0], replace(script.spans[1], boundary='phrase'), *script.spans[2:])
    else:
        spans = (replace(script.spans[0], boundary='sentence'), *script.spans[1:])
    script = replace(script, spans=tuple(spans))
    infos = {s.unit_id: audio(4800) for s in spans if s.kind == 'speech'}
    with pytest.raises(ValueError):
        build_production_timeline(script, infos, settings=TimelineSettings())


@pytest.mark.parametrize('field,value', [('schema_version', True), ('total_samples', True), ('total_frames', 13), ('has_bom', 1), ('output_fps', 24), ('video_padding_samples', 0)])
def test_reconstruction_rejects_tampered_numeric_fields(field, value):
    from video_ai.planning.production_timeline import ProductionTimeline
    data = make_timeline().as_dict()
    data[field] = value
    with pytest.raises(ValueError): ProductionTimeline.from_dict(data)


@pytest.mark.parametrize('location', ['top', 'pcm', 'stamp', 'subtitle', 'settings'])
def test_strict_nested_unknown_fields(location):
    from video_ai.planning.production_timeline import ProductionTimeline
    data = make_timeline().as_dict()
    target = {'top':data, 'pcm':data['clips'][0]['pcm'], 'stamp':data['clips'][0]['pcm']['stamp'], 'subtitle':data['subtitles'][0], 'settings':data['effective_settings']}[location]
    target['unexpected'] = 0
    with pytest.raises(ValueError): ProductionTimeline.from_dict(data)


@pytest.mark.parametrize('field,value', [('samples', True), ('sample_rate', 44100), ('channels', 2), ('sample_width', 1), ('samples', 0)])
def test_invalid_audio_rejected(field, value):
    from video_ai.planning.production_timeline import build_production_timeline
    info = replace(audio(4800), **{field:value})
    script = SegmentedScript('甲。', False, segment_text('甲。'))
    with pytest.raises(ValueError): build_production_timeline(script, {'speech_0001':info}, settings=TimelineSettings())


def test_nonfinite_seconds_and_incomplete_audio_rejected():
    from video_ai.planning.production_timeline import ProductionTimeline, build_production_timeline
    data = make_timeline().as_dict()
    data['effective_settings']['opening_seconds'] = float('nan')
    with pytest.raises(ValueError): ProductionTimeline.from_dict(data)
    with pytest.raises(ValueError): build_production_timeline(refined(), {}, settings=TimelineSettings())
