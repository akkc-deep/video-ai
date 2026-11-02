"""Durable direct candidate composition; production stamps, no review consumers."""
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from ..config import read_json
from ..media.font_metrics import PrivateFont
from ..media.production_composition import write_production_narration
from ..media.subtitles import ass_text, plan_subtitle_events, srt_text
from ..planning.composition import CompositionSettings
from ..planning.production_timeline import validate_production_timeline
from .environment import build_child_env
from .execution_limits import historical_command_timeout, production_execution
from .manifest import now, thaw
from .processes import run_logged
from .production_inputs import check_stage_space
from .production_state import (ArtifactStamp, ProductionRefused, integer, object_fields,
    run_path, sync_file, write_exclusive)
from .production_support import (checkpoint_path, commit_checkpoint, read_report,
    recover_checkpoint, stamps, sync_manifest_stage)

TECHNICAL_CHECKS = ('source_text_coverage', 'audio_samples', 'frame_mapping', 'subtitles', 'final_media')
COMMAND_FIELDS = ('args', 'cwd', 'returncode', 'timed_out', 'stdout_path', 'stderr_path', 'started_at', 'finished_at')


def _stamp(data, run=None):
    stamp = ArtifactStamp.from_dict(data)
    if run is not None: run_path(run, stamp.path)
    stamp.verify()
    return stamp


def _copy(source, target):
    """Prefer a hard link; the fallback still creates exclusively and fsyncs."""
    source = Path(source); target = Path(target)
    try: os.link(source, target)
    except FileExistsError: raise
    except OSError:
        with source.open('rb') as infile, target.open('xb') as outfile:
            shutil.copyfileobj(infile, outfile, length=1024 * 1024)
            outfile.flush(); os.fsync(outfile.fileno())
    sync_file(target)


def _text(path, text):
    with path.open('x', encoding='utf-8', newline='\n') as file:
        file.write(text); file.flush(); os.fsync(file.fileno())


def _contribution_plan(upscaled, timeline, run):
    object_fields(upscaled, ('clips', 'frame_mappings'), 'upscaled report')
    clips, mappings = upscaled['clips'], upscaled['frame_mappings']
    if not isinstance(clips, list) or not isinstance(mappings, list) or not clips or len(clips) != len(mappings):
        raise ProductionRefused('upscaled clip/mapping coverage differs')
    expected = []; cursor = 0; ids = set()
    keys = ('shot_id','coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame',
        'native_fps','output_fps','source_frames','upscaled_frames','source_to_upscaled','output_to_upscaled')
    for clip, mapping in zip(clips, mappings, strict=True):
        object_fields(mapping, keys, 'upscaled frame mapping')
        sid = clip['shot_id']; count = clip['upscaled_frames']
        integer(count, 'upscaled_frames', 1)
        if sid in ids or sid != mapping['shot_id']: raise ProductionRefused('upscaled shot order differs')
        ids.add(sid)
        wanted = dict(shot_id=sid, coverage_start_frame=cursor, coverage_end_frame=cursor+count,
            core_start_frame=cursor, core_end_frame=cursor+count, native_fps=16, output_fps=16,
            source_frames=count, upscaled_frames=count, source_to_upscaled=list(range(count)),
            output_to_upscaled=list(range(count)))
        # JSON equality alone accepts bool as an integer. Explicitly validate every index.
        for key in keys[1:-2]: integer(mapping[key], key)
        for key in keys[-2:]:
            if not isinstance(mapping[key], list): raise ProductionRefused('frame mapping must be array')
            for value in mapping[key]: integer(value, key)
        if mapping != wanted or len(clip['frames']) != count: raise ProductionRefused('incomplete native16 cut frame mapping')
        for index, frame in enumerate(clip['frames']):
            integer(frame['frame_index'], 'frame_index', 1); integer(frame['source_frame_index'], 'source_frame_index')
            if (frame['frame_index'], frame['source_frame_index']) != (index+1, index):
                raise ProductionRefused('upscaled frame order differs')
            _stamp(frame['output'], run)
            expected.append(dict(output_frame_index=cursor+index, shot_id=sid,
                source_frame_index=index, upscaled_frame_index=index, input=frame['output']))
        cursor += count
    if cursor != timeline.total_frames: raise ProductionRefused('contributions do not cover timeline')
    return expected


def _narration_layout(timeline):
    return dict(samples=timeline.total_frames * 3000, speech_samples=timeline.total_speech_samples,
        silence_samples=timeline.total_silence_samples, padding_samples=timeline.video_padding_samples,
        clips=[dict(unit_id=c.unit_id, start_sample=c.start_sample, end_sample=c.end_sample,
            samples=c.samples, pcm=c.pcm.stamp.to_dict()) for c in timeline.clips])


def _verify_materialized(payload, expected, timeline, events, settings, frozen, run):
    sequence = run_path(run, payload['sequence'])
    if payload['frames'] != timeline.total_frames or payload['samples'] != timeline.total_frames * 3000:
        raise ProductionRefused('materialized timeline counts differ')
    if payload['subtitle_events'] != events: raise ProductionRefused('materialized subtitle events differ')
    narration = dict(payload['narration']); _stamp(narration.pop('stamp'), run)
    if narration != _narration_layout(timeline): raise ProductionRefused('materialized narration layout differs')
    if len(payload['contributions']) != len(expected): raise ProductionRefused('materialized contribution count differs')
    files = set()
    for row, wanted in zip(payload['contributions'], expected, strict=True):
        source = _stamp(row['input'], run); output = _stamp(row['output'], run)
        if {k:v for k,v in row.items() if k != 'output'} != wanted:
            raise ProductionRefused('materialized contributions differ from original upscaled mapping')
        target = sequence / f'frame_{row["output_frame_index"]+1:06d}.png'
        if Path(output.path) != target or output.bytes != source.bytes:
            raise ProductionRefused('materialized contribution file differs')
        files.add(target)
    if not sequence.is_dir() or set(sequence.iterdir()) != files:
        raise ProductionRefused('materialized sequence is incomplete')
    for role, expected_text in (('subtitle', srt_text(events)), ('ass', ass_text(events, settings))):
        stamp = _stamp(payload[role], run)
        if Path(stamp.path).read_bytes() != expected_text.encode('utf-8'):
            raise ProductionRefused('materialized subtitle text differs')
    font = _stamp(payload['font'], run)
    original = ArtifactStamp.read(frozen.config.media.font_file)
    if font.bytes != original.bytes: raise ProductionRefused('materialized frozen font differs')


def _materialize(frozen, timeline, expected, events, settings, *, state):
    folder = run_path(state.run_dir, state.run_dir / f'production/composition/{uuid4().hex}')
    folder.mkdir(parents=True); sequence = folder / 'frames'; sequence.mkdir()
    contributions = []
    for row in expected:
        source = _stamp(row['input'], state.run_dir)
        target = sequence / f'frame_{row["output_frame_index"]+1:06d}.png'
        _copy(source.path, target); source.verify()
        contributions.append(dict(row, output=ArtifactStamp.read(target).to_dict()))
    narration = write_production_narration(timeline, folder / 'narration.wav')
    _text(folder / 'subtitle.srt', srt_text(events)); _text(folder / 'subtitles.ass', ass_text(events, settings))
    fonts = folder / 'fonts'; fonts.mkdir()
    original = ArtifactStamp.read(frozen.config.media.font_file)
    font_path = fonts / Path(original.path).name; _copy(original.path, font_path); original.verify()
    payload = dict(frames=timeline.total_frames, samples=timeline.total_frames*3000,
        sequence=str(sequence), narration=narration, subtitle=ArtifactStamp.read(folder/'subtitle.srt').to_dict(),
        ass=ArtifactStamp.read(folder/'subtitles.ass').to_dict(), font=ArtifactStamp.read(font_path).to_dict(),
        subtitle_events=events, contributions=contributions)
    _verify_materialized(payload, expected, timeline, events, settings, frozen, state.run_dir)
    return payload


def _command_result(intent, logger):
    """Use durable run_logged completion even if the success receipt was interrupted."""
    matches = []
    event_path = logger.path('events.jsonl')
    if event_path.exists():
        with event_path.open(encoding='utf-8') as file:
            for line in file:
                event = json.loads(line)
                if event.get('stage') == 'composition' and event.get('unit_id') == intent['unit_id'] and event.get('event') == 'command_finished':
                    matches.append(event['details'])
    if not matches: return None
    if len(matches) != 1: raise ProductionRefused('media command has conflicting durable completions')
    details = matches[0]
    if (details.get('args') != intent['args'] or details.get('cwd') != intent['cwd']
            or 'timeout' not in details or not historical_command_timeout(details['timeout'])):
        raise ProductionRefused('original media command identity differs')
    if details.get('interrupted') is not False or details.get('timed_out') is not False or type(details.get('returncode')) is not int or details['returncode'] != 0:
        return None
    return {key: details[key] for key in COMMAND_FIELDS}


def _receipt(intent_path, intent, command, output, *, logger):
    for key in ('stdout_path', 'stderr_path'):
        sync_file(run_path(logger.run_dir, command[key]))
    sync_file(run_path(logger.run_dir, output))
    result = dict(operation=intent['operation'], command=command, inputs=intent['inputs'], output=ArtifactStamp.read(output).to_dict())
    write_exclusive(intent_path.with_suffix('.success.json'), result)
    return result


def _media_operation(operation, inputs, materialized, candidate, *, frozen, state, paths, logger, recover_only=False):
    """Every attempt is exclusive; failed partials remain, successful commands are reused."""
    intents_dir = logger.path('composition/commands'); intents_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(intents_dir.glob(f'{operation}-*.intent.json')):
        intent = read_json(path)
        object_fields(intent, ('operation','unit_id','args','cwd','inputs','output'), 'media intent')
        if intent['operation'] != operation or intent['inputs'] != inputs:
            raise ProductionRefused('media operation input identity differs')
        for stamp in inputs.values(): _stamp(stamp, state.run_dir)
        wanted_args = _encode_args(frozen.config, materialized, Path(intent['cwd'])/'candidate.mp4') if operation == 'encode' else _probe_args(frozen.config, candidate)
        if intent['args'] != wanted_args: raise ProductionRefused('media command arguments were replaced')
        run_path(state.run_dir, intent['cwd'])
        if operation == 'encode' and intent['output'] != wanted_args[-1]: raise ProductionRefused('media output path differs')
        receipt_path = path.with_suffix('.success.json')
        if receipt_path.exists():
            result = read_json(receipt_path)
            object_fields(result, ('operation','command','inputs','output'), 'media success receipt')
            command = _command_result(intent, logger)
            if result['operation'] != operation or result['inputs'] != inputs or result['command'] != command:
                raise ProductionRefused('media success receipt differs from original command')
            expected_output = intent['output'] if operation == 'encode' else command['stdout_path']
            if result['output']['path'] != str(Path(expected_output).resolve()): raise ProductionRefused('media receipt output differs')
            _stamp(result['output'], state.run_dir)
            return result
        command = _command_result(intent, logger)
        if command is not None:
            output = intent['output'] if operation == 'encode' else command['stdout_path']
            return _receipt(path, intent, command, output, logger=logger)
    if recover_only: raise ProductionRefused('completed media operation lacks original success evidence')
    token = uuid4().hex
    if operation == 'encode':
        # First attempt stays with materialization; a failed retry gets a fresh directory.
        existing = list(intents_dir.glob('encode-*.intent.json'))
        folder = Path(materialized['sequence']).parent
        if existing:
            folder = run_path(state.run_dir, state.run_dir/f'production/composition/{token}'); folder.mkdir()
            _copy(materialized['ass']['path'], folder/'subtitles.ass')
            (folder/'fonts').mkdir(); _copy(materialized['font']['path'], folder/'fonts'/Path(materialized['font']['path']).name)
        output = folder/'candidate.mp4'; args = _encode_args(frozen.config, materialized, output)
    else:
        folder = Path(candidate['path']).parent; output = None; args = _probe_args(frozen.config, candidate)
    uid = f'composition:{operation}:{token}'
    intent = dict(operation=operation, unit_id=uid, args=args, cwd=str(folder), inputs=inputs, output=str(output) if output else None)
    path = write_exclusive(intents_dir/f'{operation}-{token}.intent.json', intent)
    result = run_logged(tuple(args), cwd=folder, env=build_child_env(paths), timeout=300,
        logger=logger, stage='composition', unit_id=uid)
    if type(result.returncode) is not int or result.returncode != 0 or result.timed_out:
        raise OSError(f'composition {operation} failed: {result.stderr_path}')
    return _receipt(path, intent, thaw(result), output if output else result.stdout_path, logger=logger)


def _encode_args(config, materialized, candidate):
    return [str(config.tools['ffmpeg']), '-nostdin','-n','-v','error','-xerror','-framerate','16',
        '-start_number','1','-i',str(Path(materialized['sequence'])/'frame_%06d.png'),
        '-i',materialized['narration']['stamp']['path'],'-filter_complex',
        '[0:v:0]subtitles=filename=subtitles.ass:fontsdir=fonts[v]', '-map','[v]','-map','1:a:0',
        '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',
        '-c:a','aac','-b:a','192k','-ar','48000','-ac','1','-movflags','+faststart',str(candidate)]


def _probe_args(config, candidate):
    return [str(config.tools['ffprobe']), '-v','error','-count_frames','-show_streams','-show_format','-of','json',candidate['path']]


def _validate_probe(probe, frames):
    try:
        streams = probe['streams']
        if not isinstance(streams, list) or len(streams) != 2: raise ValueError('exactly two media streams required')
        videos = [s for s in streams if s.get('codec_type') == 'video']; audios = [s for s in streams if s.get('codec_type') == 'audio']
        if len(videos) != 1 or len(audios) != 1: raise ValueError('one video and one audio required')
        video, audio = videos[0], audios[0]
        if (video.get('codec_name'),video.get('pix_fmt'),video.get('width'),video.get('height')) != ('h264','yuv420p',1920,1080): raise ValueError('wrong video format')
        if Fraction(video['avg_frame_rate']) != 16 or Fraction(video['r_frame_rate']) != 16 or str(video['nb_read_frames']) != str(frames): raise ValueError('wrong video frame count/rate')
        if (audio.get('codec_name'),str(audio.get('sample_rate')),audio.get('channels')) != ('aac','48000',1): raise ValueError('wrong audio format')
        if Fraction(video['start_time']) != 0 or Fraction(audio['start_time']) != 0: raise ValueError('media origin must be zero')
        video_duration = Fraction(video['duration']); audio_duration = Fraction(audio['duration'])
        if abs(video_duration-Fraction(frames,16)) > Fraction(1,100000) or abs(video_duration-audio_duration) > Fraction(1,10): raise ValueError('audio/video duration differs')
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RuntimeError(f'composition final media validation failed: {exc}') from exc


def _technical_record(state, report_path):
    from .production_composition_records import validate_technical_checks
    path = run_path(state.run_dir, state.run_dir/'production/technical-checks.json')
    fields = dict(schema_version=1, execution_mode='automatic', run_id=state.run_dir.name,
        composition_report=ArtifactStamp.read(report_path).to_dict(),
        technical_checks={name:'passed' for name in TECHNICAL_CHECKS}, human_review='unverified')
    if path.exists():
        record = read_json(path); validate_technical_checks(record, state.run_dir)
        if {k:v for k,v in record.items() if k != 'created_at'} != fields: raise ProductionRefused('technical checks differ from composition report')
    else:
        record = dict(fields, created_at=now()); validate_technical_checks(record, state.run_dir); write_exclusive(path, record)
    return record


@production_execution
def produce_composition(frozen, units, timeline, upscaled, *, state, manifest, paths, logger):
    validate_production_timeline(timeline)
    if (units['decoded_text'], units['has_bom'], units['spans']) != (timeline.original_text, timeline.has_bom, thaw(timeline.source_spans)):
        raise ProductionRefused('composition original units differ from timeline')
    for clip in timeline.clips: clip.pcm.stamp.verify()
    expected = _contribution_plan(upscaled, timeline, state.run_dir)
    settings = CompositionSettings()
    with PrivateFont(frozen.config.media.font_file, settings.font_name, settings.font_size) as font:
        events = plan_subtitle_events(timeline.subtitles, settings, measure=font.measure)
    inputs = stamps({name:state.run_dir/f'production/{file}.json' for name,file in
        [('options','options'),('units','units'),('timeline','timeline'),('upscaled','upscaled-clips')]})
    report = read_report(state, 'composition')
    complete = state.snapshot()['stages']['composition']['status'] == 'completed'
    if not complete:
        state.start_stage('composition')
        check_stage_space(frozen.config, frames=timeline.total_frames,
            audio_bytes=timeline.total_frames*3000*2+44,
            encoded_bytes=timeline.total_frames*1920*1080*4)
    elif report is None: raise ProductionRefused('completed composition has no report')
    materialized = recover_checkpoint(state, 'composition', 'materialized')
    if materialized is None:
        if report or complete: raise ProductionRefused('composition lacks materialized checkpoint')
        state.record_unit('composition','materialized',status='running')
        payload = _materialize(frozen,timeline,expected,events,settings,state=state)
        outputs = dict(inputs, subtitle=payload['subtitle'], ass=payload['ass'], font=payload['font'], narration=payload['narration']['stamp'])
        outputs.update({f'contribution_{i:06d}':row['output'] for i,row in enumerate(payload['contributions'])})
        outputs.update({f'input_{i:06d}':row['input'] for i,row in enumerate(payload['contributions'])})
        materialized = commit_checkpoint(state,'composition','materialized',outputs=outputs,payload=payload)
    payload = materialized['payload']
    for name,stamp in inputs.items():
        if materialized['outputs'].get(name) != stamp: raise ProductionRefused('materialized input records differ')
    _verify_materialized(payload,expected,timeline,events,settings,frozen,state.run_dir)
    materialized_stamp = ArtifactStamp.read(checkpoint_path(state,'composition','materialized')).to_dict()
    encoded = recover_checkpoint(state,'composition','encoded')
    if encoded is None:
        if report or complete: raise ProductionRefused('composition lacks encoded checkpoint')
        state.record_unit('composition','encoded',status='running')
        receipt = _media_operation('encode',{'materialized':materialized_stamp},payload,None,
            frozen=frozen,state=state,paths=paths,logger=logger)
        encoded_payload = dict(candidate=receipt['output'],encoding=receipt['command'],materialized_checkpoint=materialized_stamp)
        outputs = dict(candidate=receipt['output'], materialized_checkpoint=materialized_stamp,
            **stamps({key:receipt['command'][key] for key in ('stdout_path','stderr_path')}))
        encoded = commit_checkpoint(state,'composition','encoded',outputs=outputs,payload=encoded_payload)
    if encoded['payload']['materialized_checkpoint'] != materialized_stamp: raise ProductionRefused('encoded materialization differs')
    candidate = encoded['payload']['candidate']; _stamp(candidate,state.run_dir)
    encode_receipt = _media_operation('encode',{'materialized':materialized_stamp},payload,None,
        frozen=frozen,state=state,paths=paths,logger=logger,recover_only=True)
    if encoded['payload']['encoding'] != encode_receipt['command'] or candidate != encode_receipt['output']:
        raise ProductionRefused('encoded checkpoint differs from original successful command')
    final = recover_checkpoint(state,'composition','final')
    if final is None:
        if report or complete: raise ProductionRefused('composition lacks final checkpoint')
        state.record_unit('composition','final',status='running')
        receipt = _media_operation('probe',{'candidate':candidate},payload,candidate,
            frozen=frozen,state=state,paths=paths,logger=logger)
        try: probe = read_json(Path(receipt['command']['stdout_path']))
        except ValueError as exc: raise RuntimeError('invalid final ffprobe JSON') from exc
        _validate_probe(probe,timeline.total_frames)
        final_payload = dict(candidate=candidate,subtitle=payload['subtitle'],frames=timeline.total_frames,
            samples=timeline.total_frames*3000,subtitle_events=events,encoding=encoded['payload']['encoding'],probe=probe)
        outputs = dict(candidate=candidate,subtitle=payload['subtitle'],materialized=materialized_stamp,
            encoded=ArtifactStamp.read(checkpoint_path(state,'composition','encoded')).to_dict(),
            **stamps({key:receipt['command'][key] for key in ('stdout_path','stderr_path')}))
        final = commit_checkpoint(state,'composition','final',outputs=outputs,payload=final_payload)
    probe_receipt = _media_operation('probe',{'candidate':candidate},payload,candidate,
        frozen=frozen,state=state,paths=paths,logger=logger,recover_only=True)
    if final['payload']['probe'] != read_json(Path(probe_receipt['command']['stdout_path'])):
        raise ProductionRefused('final checkpoint differs from original successful probe')
    result = final['payload']; _validate_probe(result['probe'],timeline.total_frames)
    if (result['candidate'],result['subtitle'],result['frames'],result['samples'],result['subtitle_events'],result['encoding']) != (
        candidate,payload['subtitle'],timeline.total_frames,timeline.total_frames*3000,events,encoded['payload']['encoding']):
        raise ProductionRefused('final composition differs from original checkpoints')
    if report:
        if report['payload'] != result or report['input_records'] != inputs: raise ProductionRefused('composition report differs from original checkpoints')
    else: state.write_report('composition',result,input_records=inputs)
    report_path = state.run_dir/'production/composition.json'
    _technical_record(state,report_path)
    if not complete: state.complete_stage('composition')
    sync_manifest_stage(manifest,'composition',report_path)
    return result
