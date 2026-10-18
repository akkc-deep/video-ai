"""Lossless PCM and once-only production composition, without model execution."""
from array import array
from dataclasses import replace
import wave

import pytest

from video_ai.config import TimelineSettings
from video_ai.planning.production_timeline import ProductionAudioInfo, build_production_timeline
from video_ai.planning.segments import SegmentedScript, segment_text
from video_ai.runtime.production_state import ArtifactStamp


def timeline_for(directory, text='甲。\r\n乙\\N{字}。', samples=(70001, 47999)):
    script = SegmentedScript(text, True, segment_text(text))
    audio = {}; payloads = {}
    for index, span in enumerate(s for s in script.spans if s.kind == 'speech'):
        count = samples[index]
        payload = array('h', ((0 if i % 7 == 0 else (index + 1) * (i % 3000 - 1500)) for i in range(count))).tobytes()
        path = directory / f'{span.unit_id}.wav'
        with wave.open(str(path), 'wb') as file:
            file.setparams((1, 2, 48000, 0, 'NONE', '')); file.writeframes(payload)
        audio[span.unit_id] = ProductionAudioInfo(ArtifactStamp.read(path), 48000, 1, 2, count)
        payloads[span.unit_id] = payload
    return build_production_timeline(script, audio, settings=TimelineSettings(.1, .2, .05, .025)), payloads


def test_pcm_keeps_every_source_byte_internal_silence_and_exact_padding(tmp_path):
    from video_ai.media.production_composition import write_production_narration
    timeline, payloads = timeline_for(tmp_path)
    target = tmp_path / 'narration.wav'
    record = write_production_narration(timeline, target)
    with wave.open(str(target), 'rb') as file:
        assert (file.getnchannels(), file.getsampwidth(), file.getframerate()) == (1, 2, 48000)
        actual = file.readframes(file.getnframes())
    cursor = 0; expected = []
    for clip in timeline.clips:
        expected += [bytes((clip.start_sample - cursor) * 2), payloads[clip.unit_id]]
        cursor = clip.end_sample
    expected.append(bytes((timeline.total_frames * 3000 - cursor) * 2))
    assert actual == b''.join(expected)
    assert record['samples'] == timeline.total_frames * 3000
    assert record['speech_samples'] == 118000
    assert record['silence_samples'] == timeline.total_silence_samples
    assert record['padding_samples'] == timeline.video_padding_samples
    assert record['clips'][0]['pcm'] == timeline.clips[0].pcm.stamp.to_dict()
    assert set(record['stamp']) == {'path', 'bytes', 'mtime_ns'}
    with pytest.raises(FileExistsError): write_production_narration(timeline, target)


def test_pcm_reader_requests_at_most_65536_samples(tmp_path, monkeypatch):
    from video_ai.media.production_composition import write_production_narration
    timeline, _ = timeline_for(tmp_path)
    original = wave.Wave_read.readframes
    sizes = []
    def readframes(file, count):
        sizes.append(count); return original(file, count)
    monkeypatch.setattr(wave.Wave_read, 'readframes', readframes)
    write_production_narration(timeline, tmp_path / 'narration.wav')
    assert sizes and max(sizes) <= 65536


@pytest.mark.parametrize('mode', ['truncated', 'extra', 'format', 'stamp'])
def test_invalid_original_pcm_is_rejected(tmp_path, mode):
    from video_ai.media.production_composition import write_production_narration
    timeline, _ = timeline_for(tmp_path)
    clip = timeline.clips[0]; path = clip.pcm.path
    if mode == 'truncated': path.write_bytes(path.read_bytes()[:-2])
    elif mode == 'extra':
        with wave.open(str(path), 'wb') as file:
            file.setparams((1, 2, 48000, 0, 'NONE', '')); file.writeframes(bytes((clip.samples + 1) * 2))
    elif mode == 'format':
        with wave.open(str(path), 'wb') as file:
            file.setparams((1, 2, 44100, 0, 'NONE', '')); file.writeframes(bytes(clip.samples * 2))
    else: path.write_bytes(path.read_bytes())
    if mode != 'stamp':
        timeline = replace(timeline, clips=(replace(clip, pcm=replace(clip.pcm, stamp=ArtifactStamp.read(path))), *timeline.clips[1:]))
    with pytest.raises((ValueError, OSError, EOFError)):
        write_production_narration(timeline, tmp_path / 'narration.wav')


def test_pure_subtitle_events_preserve_original_coverage_and_ass_escapes(tmp_path):
    from video_ai.media.subtitles import plan_subtitle_events, plan_subtitles, ass_text, decode_ass_literal, srt_text
    from video_ai.planning.composition import CompositionSettings
    timeline, _ = timeline_for(tmp_path)
    settings = CompositionSettings()
    events = plan_subtitle_events(timeline.subtitles, settings, measure=lambda text: len(text) * 40)
    assert [e['text'] for e in events] == [c.text for c in timeline.clips]
    assert all(''.join(e['layout']['lines']) == e['text'] for e in events)
    assert '乙\\N{字}。' in srt_text(events)
    dialogues = [line.split(',,', 2)[-1] for line in ass_text(events, settings).splitlines() if line.startswith('Dialogue:')]
    assert [decode_ass_literal(line) for line in dialogues] == [c.text for c in timeline.clips]
    with pytest.raises(ValueError): plan_subtitles(timeline, settings, measure=len)


def runtime_case(runtime_run, production_config, monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import now, thaw
    from video_ai.runtime.processes import CommandResult
    from video_ai.runtime.production_state import validate_checkpoint, validate_report, write_exclusive
    import video_ai.runtime.production_composition as module
    run, _, paths = runtime_run
    (run / 'production').mkdir(exist_ok=True)
    timeline, _ = timeline_for(run)
    for name in ('options', 'units', 'timeline', 'upscaled-clips'):
        write_exclusive(run / f'production/{name}.json', {})
    frames = []
    for i in range(timeline.total_frames):
        path = run / f'input-{i}.png'; path.write_bytes(f'distinct-frame-{i}'.encode())
        frames.append(dict(frame_index=i+1, source_frame_index=i, output=ArtifactStamp.read(path).to_dict()))
    count = len(frames)
    mapping = dict(shot_id='shot_0001', coverage_start_frame=0, coverage_end_frame=count,
        core_start_frame=0, core_end_frame=count, native_fps=16, output_fps=16,
        source_frames=count, upscaled_frames=count, source_to_upscaled=list(range(count)), output_to_upscaled=list(range(count)))
    upscaled = dict(clips=[dict(shot_id='shot_0001', upscaled_frames=count, frames=frames)], frame_mappings=[mapping])
    class Store:
        run_dir = run
        status = 'pending'
        records = {}
        def snapshot(self): return dict(stages={'composition':dict(status=self.status)}, units={'composition': self.records})
        def start_stage(self, stage): self.status = 'running'
        def record_unit(self, stage, uid, **fields):
            self.records[uid] = dict(status=fields['status'], request=fields.get('request'), outputs=fields.get('outputs', {}), checkpoint_path=str(fields.get('checkpoint_path', '')))
        def write_checkpoint(self, stage, uid, **fields):
            record = dict(schema_version=1, execution_mode='automatic', run_id=run.name, stage=stage,
                unit_id=uid, created_at=now(), status='completed', **fields)
            validate_checkpoint(record, run, stage, uid)
            return write_exclusive(run / f'logs/production/checkpoints/{stage}/{uid}.json', record)
        def write_report(self, stage, payload, input_records):
            record = dict(schema_version=1, execution_mode='automatic', run_id=run.name, stage=stage,
                created_at=now(), status='completed', input_records=input_records, payload=payload)
            validate_report(record, run, stage)
            return write_exclusive(run / 'production/composition.json', record)
        def complete_stage(self, stage):
            assert (run / 'production/technical-checks.json').is_file()
            self.status = 'completed'
    class Font:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def measure(self, text): return len(text) * 20
    calls = []
    def execute(args, *, cwd, logger, stage, unit_id, **kwargs):
        calls.append(tuple(args)); token = str(len(calls))
        stdout = logger.save_bytes(f'processes/{token}.stdout', b'')
        stderr = logger.save_bytes(f'processes/{token}.stderr', b'')
        if '-count_frames' in args:
            duration = count / 16
            probe = dict(streams=[dict(codec_type='video', codec_name='h264', pix_fmt='yuv420p', width=1920,
                height=1080, avg_frame_rate='16/1', r_frame_rate='16/1', nb_read_frames=str(count),
                duration=str(duration), start_time='0'), dict(codec_type='audio', codec_name='aac',
                sample_rate='48000', channels=1, duration=str(duration), start_time='0')], format=dict(duration=str(duration),start_time='0'))
            import json
            stdout.write_text(json.dumps(probe), encoding='utf-8')
        else:
            from pathlib import Path
            Path(args[-1]).write_bytes(b'candidate-video')
        result = CommandResult(tuple(args), cwd, 0, False, stdout, stderr, now(), now())
        logger.event(stage, unit_id, 'command_finished', dict(thaw(result), timeout=300, interrupted=False))
        return result
    monkeypatch.setattr(module, 'PrivateFont', Font)
    monkeypatch.setattr(module, 'run_logged', execute)
    monkeypatch.setattr(module, 'check_stage_space', lambda *a, **k: None)
    monkeypatch.setattr(module, 'sync_manifest_stage', lambda *a: None)
    return module, SimpleNamespace(config=production_config), Store(), paths, RunLogger(run, production=True), timeline, upscaled, calls


from unit.test_production_inputs import production_config


def test_direct_encode_one_probe_then_zero_media_resume(runtime_run, production_config, monkeypatch):
    module, frozen, state, paths, logger, timeline, upscaled, calls = runtime_case(runtime_run, production_config, monkeypatch)
    units = dict(decoded_text=timeline.original_text, has_bom=timeline.has_bom, spans=[dict(start=s.start,end=s.end,text=s.text,kind=s.kind,boundary=s.boundary,unit_id=s.unit_id) for s in timeline.source_spans])
    result = module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert len(calls) == 2 and '-filter_complex' in calls[0] and '-count_frames' in calls[1]
    assert '-shortest' not in calls[0] and not any('video-base' in a for a in calls[0])
    assert result['samples'] == timeline.total_frames * 3000
    assert module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger) == result
    assert len(calls) == 2


@pytest.mark.parametrize('point', ['encoded', 'final', 'report', 'cursor'])
def test_durable_success_recovers_without_reencode_or_reprobe(runtime_run, production_config, monkeypatch, point):
    module, frozen, state, paths, logger, timeline, upscaled, calls = runtime_case(runtime_run, production_config, monkeypatch)
    units = dict(decoded_text=timeline.original_text, has_bom=timeline.has_bom, spans=[dict(start=s.start,end=s.end,text=s.text,kind=s.kind,boundary=s.boundary,unit_id=s.unit_id) for s in timeline.source_spans])
    method = 'write_checkpoint' if point in ('encoded', 'final') else 'write_report' if point == 'report' else 'complete_stage'
    original = getattr(state, method)
    interrupted = False
    def fail_once(*args, **kwargs):
        nonlocal interrupted
        if not interrupted and (point not in ('encoded', 'final') or args[1] == point):
            interrupted = True; raise OSError('interrupted commit')
        return original(*args, **kwargs)
    monkeypatch.setattr(state, method, fail_once)
    with pytest.raises(OSError, match='interrupted commit'):
        module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    monkeypatch.setattr(state, method, original)
    module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert len(calls) == 2


@pytest.mark.parametrize('operation', ['encode', 'probe'])
def test_successful_process_log_recovers_before_success_receipt(runtime_run, production_config, monkeypatch, operation):
    module, frozen, state, paths, logger, timeline, upscaled, calls = runtime_case(runtime_run, production_config, monkeypatch)
    units = dict(decoded_text=timeline.original_text, has_bom=timeline.has_bom, spans=[dict(start=s.start,end=s.end,text=s.text,kind=s.kind,boundary=s.boundary,unit_id=s.unit_id) for s in timeline.source_spans])
    original = module._receipt
    def interrupt(path, intent, *args, **kwargs):
        if intent['operation'] == operation: raise OSError('receipt interrupted')
        return original(path, intent, *args, **kwargs)
    monkeypatch.setattr(module, '_receipt', interrupt)
    with pytest.raises(OSError, match='receipt interrupted'):
        module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    monkeypatch.setattr(module, '_receipt', original)
    module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert len(calls) == 2


def test_completed_encoded_command_replacement_is_rejected_without_media(runtime_run, production_config, monkeypatch):
    import json
    module, frozen, state, paths, logger, timeline, upscaled, calls = runtime_case(runtime_run, production_config, monkeypatch)
    units = dict(decoded_text=timeline.original_text, has_bom=timeline.has_bom, spans=[dict(start=s.start,end=s.end,text=s.text,kind=s.kind,boundary=s.boundary,unit_id=s.unit_id) for s in timeline.source_spans])
    original = state.write_checkpoint
    def fail_final(stage, uid, **fields):
        if uid == 'final': raise OSError('stop before final')
        return original(stage, uid, **fields)
    monkeypatch.setattr(state, 'write_checkpoint', fail_final)
    with pytest.raises(OSError): module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    path = state.run_dir / 'logs/production/checkpoints/composition/encoded.json'
    data = json.loads(path.read_text(encoding='utf-8')); data['payload']['encoding']['args'][1] = '-y'
    path.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setattr(state, 'write_checkpoint', original)
    with pytest.raises(ValueError):
        module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert len(calls) == 2


@pytest.mark.parametrize('mode', ['nonzero', 'timeout'])
def test_failed_encode_retains_partial_and_retries_in_new_directory(runtime_run, production_config, monkeypatch, mode):
    from pathlib import Path
    from video_ai.runtime.manifest import now, thaw
    from video_ai.runtime.processes import CommandResult
    module, frozen, state, paths, logger, timeline, upscaled, calls = runtime_case(runtime_run, production_config, monkeypatch)
    units = dict(decoded_text=timeline.original_text, has_bom=timeline.has_bom, spans=[dict(start=s.start,end=s.end,text=s.text,kind=s.kind,boundary=s.boundary,unit_id=s.unit_id) for s in timeline.source_spans])
    original = module.run_logged
    partials = []
    def fail_first(args, *, cwd, logger, stage, unit_id, **kwargs):
        if not partials:
            candidate = Path(args[-1]); candidate.write_bytes(b'partial-encode'); partials.append(candidate)
            stdout = logger.save_bytes('processes/failed.stdout', b'')
            stderr = logger.save_bytes('processes/failed.stderr', b'injected encode error')
            result = CommandResult(tuple(args), cwd, 1, mode == 'timeout', stdout, stderr, now(), now())
            logger.event(stage,unit_id,'command_finished',dict(thaw(result),timeout=300,interrupted=False))
            return result
        return original(args,cwd=cwd,logger=logger,stage=stage,unit_id=unit_id,**kwargs)
    monkeypatch.setattr(module, 'run_logged', fail_first)
    with pytest.raises(OSError):
        module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert not (state.run_dir / 'production/technical-checks.json').exists()
    result = module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert partials[0].read_bytes() == b'partial-encode'
    assert Path(result['candidate']['path']).parent != partials[0].parent
    assert len(calls) == 2


@pytest.mark.parametrize('mode', ['missing_audio','wrong_frames','duration','bad_json'])
def test_bad_final_probe_never_completes_or_repeats_successful_commands(runtime_run, production_config, monkeypatch, mode):
    import json
    from pathlib import Path
    module, frozen, state, paths, logger, timeline, upscaled, calls = runtime_case(runtime_run, production_config, monkeypatch)
    units = dict(decoded_text=timeline.original_text, has_bom=timeline.has_bom, spans=[dict(start=s.start,end=s.end,text=s.text,kind=s.kind,boundary=s.boundary,unit_id=s.unit_id) for s in timeline.source_spans])
    original = module.run_logged
    def bad_probe(args, **kwargs):
        result = original(args, **kwargs)
        if '-count_frames' in args:
            path = Path(result.stdout_path); probe = json.loads(path.read_text(encoding='utf-8'))
            if mode == 'missing_audio': probe['streams'].pop()
            elif mode == 'wrong_frames': probe['streams'][0]['nb_read_frames'] = '1'
            elif mode == 'duration': probe['streams'][1]['duration'] = str(timeline.total_frames/16 + .1001)
            if mode == 'bad_json': path.write_text('broken', encoding='utf-8')
            else: path.write_text(json.dumps(probe), encoding='utf-8')
        return result
    monkeypatch.setattr(module, 'run_logged', bad_probe)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert len(calls) == 2 and state.status != 'completed'
    assert not (state.run_dir/'production/technical-checks.json').exists()


@pytest.mark.parametrize('partial', [False, True])
def test_incomplete_technical_command_uses_fresh_attempt_directory(runtime_run, production_config, monkeypatch, partial):
    from pathlib import Path
    module, frozen, state, paths, logger, timeline, upscaled, calls = runtime_case(runtime_run, production_config, monkeypatch)
    units = dict(decoded_text=timeline.original_text, has_bom=timeline.has_bom, spans=[dict(start=s.start,end=s.end,text=s.text,kind=s.kind,boundary=s.boundary,unit_id=s.unit_id) for s in timeline.source_spans])
    original = module.run_logged; prior = []
    def interrupt(args, **kwargs):
        prior.append(Path(args[-1]))
        if partial: prior[-1].write_bytes(b'unfinished-encode')
        raise OSError('lost technical command')
    monkeypatch.setattr(module, 'run_logged', interrupt)
    with pytest.raises(OSError): module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    monkeypatch.setattr(module, 'run_logged', original)
    result = module.produce_composition(frozen, units, timeline, upscaled, state=state, manifest=None, paths=paths, logger=logger)
    assert Path(result['candidate']['path']).parent != prior[0].parent
    if partial: assert prior[0].read_bytes() == b'unfinished-encode'
    assert len(calls) == 2
