"""Reconstruct the candidate report from fresh upstream and raw media receipts."""
from datetime import datetime
from pathlib import Path
import re

from ..config import read_json
from ..planning.start_images import keys
from ..planning.source_clips import _same
from ..media.composition_video import ffmpeg, validate_probe, validate_audio_packets
from ..media.srt_validation import validate_srt
from ._composition_evidence import _same_sources
from ._composition_inputs import fresh, equal_identity
from .logging import RunLogger
from .manifest import hash_file, thaw, _timestamp
from .timeline_checks import _local, _again, _fresh
from .paths import PROJECT_ROOT
from .execution_limits import command_receipt_policy

FIELDS = 'schema_version run_id created_at status passed staging_only ready_for_review composition_identity input_identities candidate_identity subtitle_identity effective_media subtitle_events requirement_bindings cue_checks provenance validation request_evidence plan_identity execution_identity'
PLAN_FIELDS = 'schema_version run_id composition_identity expected_media subtitle_events requirement_bindings cue_checks'
EXECUTION_FIELDS = 'schema_version run_id composition_identity commands effective_media srt_check'
COMMAND_FIELDS = 'operation timeout_seconds args cwd returncode timed_out stdout_path stderr_path started_at finished_at record_path'
OPERATIONS = ('probe', 'pts', 'decode', 'decode_audio', 'audio_packets')
HISTORICAL_TTS_CONFIG = PROJECT_ROOT/'config/tts-api.yaml'


class ValidationLogger(RunLogger):
    """Adapt the existing inspector's fixed composition namespace to this stage."""
    def path(self, relative_name):
        name = str(relative_name).replace('\\', '/')
        if name.startswith('composition/'):
            name = 'validation/' + name[len('composition/'):]
        elif name.startswith(('processes/', 'errors/')):
            name = 'validation/' + name
        return super().path(name)

    def event(self, stage, unit_id, event, details):
        return super().event('validation', unit_id, event, details)


def validation():
    return dict(media_passed=True, source_frame_mapping_passed=True,
        subtitle_text_timing_passed=True, narration_samples_passed=True,
        input_associations_passed=True, actual_final_video_semantics='unverified',
        actual_final_video_sync='unverified', full_film_acceptance='unverified')


def upstream_unchanged(current, previous):
    for key in ('schema_version', 'run_id', 'created_at', 'config_snapshot', 'voice_snapshot', 'inputs', 'models', 'units', 'services', 'resources'):
        if not _same(current[key], previous[key]):
            raise OSError('candidate upstream changed: ' + key)
    for name in previous['stages']:
        if name not in ('validation', 'publish') and not _same(current['stages'][name], previous['stages'][name]):
            raise OSError('candidate upstream stage changed: ' + name)
    downstream = {'candidate_validation', 'publication_report', 'final_review', 'full_film_acceptance'}
    from .pipeline_evidence import media_workflows
    current_workflows,previous_workflows=media_workflows(current,previous)
    old = {k: v for k, v in previous_workflows.items() if k not in downstream}
    new = {k: v for k, v in current_workflows.items() if k not in downstream}
    if not _same(old, new): raise OSError('candidate upstream workflows changed')
    prefix = previous['events']
    if not _same(current['events'][:len(prefix)], prefix):
        raise OSError('candidate upstream event history changed')
    for entry in current['events'][len(prefix):]:
        if entry['stage'] not in ('validation', 'publish') and entry['action'] != 'manifest_update':
            raise OSError('candidate upstream event appended')


def capture_bound_identities(value, *, run):
    """Retain verified leaves through identity-bound, run-local JSON reports.

    A path string never grants authority to read another document. Only an
    exact complete FileIdentity can bind a JSON read, and external identities
    are leaves. Each report is hashed before parsing and rehashed afterwards;
    callers retain all returned identities until their final commit/read gate.
    """
    run = Path(run)
    identities = {}; by_path = {}; strict_records = {}; visited = set()
    def historical_tts(path, origin, position):
        if path != HISTORICAL_TTS_CONFIG: return False
        return (origin == run/'segments.json' and position == ('inputs', 'tts_yaml') or
            origin == run/'voice-listening.json' and position == ('voice', 'tts_yaml') or
            origin is not None and origin.parent == run/'logs/upscale' and
            re.fullmatch(r'resume-manifest-[0-9a-f]{32}\.json', origin.name) is not None and
            position == ('inputs', 'tts_yaml'))

    def capture(node, origin=None, position=()):
        if isinstance(node, dict):
            if set(node) == {'path', 'bytes', 'mtime_ns', 'sha256', 'verified_at'}:
                path = Path(node['path'])
                _timestamp(node['verified_at'])
                if datetime.fromisoformat(node['verified_at']) > datetime.now().astimezone():
                    raise ValueError('future bound input identity timestamp')
                if historical_tts(path, origin, position):
                    # Speech generation records intentionally bind historical
                    # TTS settings by bytes/SHA. Retain today's full identity
                    # so this compatibility never permits transaction drift.
                    if any(v is None for v in node.values()): raise ValueError('complete historical TTS identity required')
                    from .manifest import _identity
                    _identity(node)
                    identity = hash_file(HISTORICAL_TTS_CONFIG)
                    if (identity.bytes,identity.sha256)!=(node['bytes'],node['sha256']):
                        raise OSError('historical TTS content changed')
                    if identity.path != node['path']: raise ValueError('historical TTS path is not canonical')
                elif str(path) in strict_records:
                    if not equal_identity(strict_records[str(path)], node):
                        raise ValueError('conflicting upstream identity for one path')
                    identity = by_path[str(path)]
                else:
                    # An ordinary occurrence is always checked strictly, even
                    # when a historical occurrence was encountered first.
                    identity = fresh(node, run=run if path.is_relative_to(run) else None)
                    strict_records[str(path)] = node
                previous = by_path.get(str(path))
                if previous is not None:
                    if not equal_identity(thaw(previous), thaw(identity)):
                        raise ValueError('conflicting upstream identity for one path')
                else:
                    identities['upstream/'+str(len(identities))] = identity
                    by_path[str(path)] = identity
                if path.is_relative_to(run) and path.suffix.lower() == '.json' and str(path) not in visited:
                    visited.add(str(path))
                    document = read_json(_local(run, path))
                    # Check the originally accepted SHA/stat after the read,
                    # before using any newly discovered identity authority.
                    fresh(node, run=run, expected=path)
                    capture(document, path)
            else:
                for key, child in node.items(): capture(child, origin, (*position, key))
        elif isinstance(node, (list, tuple)):
            for index, child in enumerate(node): capture(child, origin, (*position, index))
    capture(thaw(value))
    # Imported origin JSONs are intentionally external leaves in the generic
    # walker. The import consumer explicitly supplies their validated closure.
    from .pipeline_import import import_source_identities
    imports=import_source_identities(run) if (run/'manifest.json').is_file() else {}
    for path,identity in imports.items():
        previous=by_path.get(path)
        if previous is not None and not equal_identity(thaw(previous),thaw(identity)):
            raise ValueError('conflicting imported upstream leaf')
        identities['import/'+path]=identity
    _again(identities)
    return identities


def composition_context(config, run, composition, composition_identity):
    media = composition['effective_media']
    fps, frames = media['fps'], media['frames']
    if type(fps) is not int or fps != config.media.fps or fps not in (16, 24) or type(frames) is not int or frames < 1:
        raise ValueError('candidate frame/fps budget differs from frozen configuration')
    channels = 2 if config.media.music else 1
    expected = dict(width=1920, height=1080, codec='h264', pixel_format='yuv420p', fps=fps, frames=frames,
        audio_codec='aac', sample_rate=48000, channels=channels, video_samples=frames*(48000//fps))
    if not _same({k: media[k] for k in expected if k != 'video_samples'}, {k: v for k, v in expected.items() if k != 'video_samples'}):
        raise ValueError('upstream candidate format differs')
    candidate = _local(run, run/'staging/composition/candidate.mp4')
    subtitle = _local(run, run/'staging/composition/subtitle.srt')
    ids = {k: fresh(record) for k, record in composition['input_identities'].items()}
    if 'composition' in ids: raise ValueError('reserved composition identity key')
    ids['composition'] = composition_identity
    candidate_id = fresh(composition['candidate_identity'], run=run, expected=candidate)
    subtitle_id = fresh(composition['subtitles']['srt_identity'], run=run, expected=subtitle)
    bound_ids = capture_bound_identities(composition, run=run)
    return dict(composition=composition, composition_identity=composition_identity, identities=ids,
        candidate_identity=candidate_id, subtitle_identity=subtitle_id, expected_media=expected,
        candidate_path=candidate, subtitle_path=subtitle, bound_identities=bound_ids)


def plan(run, context):
    composition = context['composition']
    return dict(schema_version=1, run_id=run.name, composition_identity=thaw(context['composition_identity']),
        expected_media=context['expected_media'], subtitle_events=composition['subtitles']['events'],
        requirement_bindings=composition['requirement_bindings'], cue_checks=composition['cue_checks'])


def index_evidence(run, plan_path, execution_path, commands):
    paths = [plan_path, execution_path]
    paths += [Path(r[k]) for r in commands for k in ('record_path', 'stdout_path', 'stderr_path')]
    if len(set(paths)) != len(paths): raise ValueError('duplicate candidate evidence paths')
    return {p.relative_to(run).as_posix(): thaw(hash_file(_local(run, p))) for p in sorted(paths)}


def expected_argv(config, candidate):
    return dict(
        probe=[config.tools['ffprobe'], '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', candidate],
        pts=[config.tools['ffprobe'], '-v', 'error', '-select_streams', 'v:0', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', candidate],
        decode=[*ffmpeg(config), '-i', candidate, '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'],
        decode_audio=[*ffmpeg(config), '-i', candidate, '-map', '0:a:0', '-f', 's16le', '-acodec', 'pcm_s16le', 'pipe:1'],
        audio_packets=[config.tools['ffprobe'], '-v', 'error', '-select_streams', 'a:0', '-show_packets', '-of', 'json', candidate])


def commands_media(config, run, commands, context, evidence):
    if not isinstance(commands, list) or len(commands) != len(OPERATIONS):
        raise ValueError('missing/extra candidate commands')
    expected = expected_argv(config, context['candidate_path'])
    seen = set(); receipts = {}
    for operation, record in zip(OPERATIONS, commands):
        keys(record, COMMAND_FIELDS+(' time_limits' if 'time_limits' in record else ''), 'candidate command')
        if record['operation'] != operation or record['args'] != [str(x) for x in expected[operation]]:
            raise ValueError('candidate command order/arguments differ')
        if type(record['returncode']) is not int or record['returncode'] != 0 or record['timed_out'] is not False or not command_receipt_policy(record) or record['cwd'] != str(run/'logs/validation'):
            raise ValueError('failed/invalid candidate command execution policy')
        for k in ('started_at', 'finished_at'): _timestamp(record[k])
        start, end = (datetime.fromisoformat(record[k]) for k in ('started_at', 'finished_at'))
        elapsed=(end-start).total_seconds()
        if elapsed<0 or record['timeout_seconds'] is not None and elapsed>301 or end > datetime.now().astimezone():
            raise ValueError('candidate command timestamps differ')
        for key in ('record_path', 'stdout_path', 'stderr_path'):
            path = _local(run, Path(record[key])); name = path.relative_to(run).as_posix()
            if name in seen or name not in evidence or not name.startswith('logs/validation/'):
                raise ValueError('candidate command evidence duplicate/missing/external')
            seen.add(name)
        stored = read_json(Path(record['record_path']))
        if not _same(stored, {k: v for k, v in record.items() if k != 'record_path'}):
            raise ValueError('candidate command differs from raw receipt')
        if Path(record['stderr_path']).read_bytes(): raise ValueError('candidate command stderr is not empty')
        receipts[operation] = record
    expected_media = context['expected_media']
    media = validate_probe(read_json(Path(receipts['probe']['stdout_path'])), read_json(Path(receipts['pts']['stdout_path'])),
        fps=expected_media['fps'], total_frames=expected_media['frames'], channels=expected_media['channels'])
    decoded = Path(receipts['decode_audio']['stdout_path']).stat().st_size
    unit = expected_media['channels']*2; samples = decoded//unit
    if decoded % unit or not 0 <= samples-expected_media['video_samples'] < 2048:
        raise ValueError('candidate decoded AAC sample budget differs')
    packets = read_json(Path(receipts['audio_packets']['stdout_path']))
    priming = validate_audio_packets(packets['packets'], expected_media['video_samples'])
    media.update(decoded_audio_samples=samples, tail_padding_samples=samples-expected_media['video_samples'], priming_samples=priming)
    if Path(receipts['decode']['stdout_path']).read_bytes(): raise ValueError('unexpected candidate decode stdout')
    return media


def validate(config, run, report, context, *, inspect_actual=False):
    keys(report, FIELDS, 'candidate validation report')
    if type(report['schema_version']) is not int or report['schema_version'] != 1 or report['run_id'] != run.name or report['status'] != 'completed':
        raise ValueError('candidate schema/run/status differs')
    _timestamp(report['created_at'])
    if datetime.fromisoformat(report['created_at']) > datetime.now().astimezone(): raise ValueError('future candidate timestamp')
    if any(report[k] is not True for k in ('passed', 'ready_for_review', 'staging_only')) or not _same(report['validation'], validation()):
        raise ValueError('candidate validation facts differ')
    composition = context['composition']
    associations = dict(composition_identity=thaw(context['composition_identity']), input_identities=thaw(context['identities']),
        candidate_identity=thaw(context['candidate_identity']), subtitle_identity=thaw(context['subtitle_identity']),
        subtitle_events=composition['subtitles']['events'], requirement_bindings=composition['requirement_bindings'],
        cue_checks=composition['cue_checks'], provenance=composition['provenance'])
    if not _same_sources({k: report[k] for k in associations}, associations):
        raise ValueError('candidate input associations/provenance differ')
    plan_path = _local(run, run/'logs/validation/plan.json')
    execution_path = _local(run, run/'logs/validation/execution.json')
    ids = dict(context['identities'], **context['bound_identities'])
    ids['candidate'] = context['candidate_identity']; ids['subtitle'] = context['subtitle_identity']
    ids['plan'] = fresh(report['plan_identity'], run=run, expected=plan_path)
    ids['execution'] = fresh(report['execution_identity'], run=run, expected=execution_path)
    actual_plan = read_json(plan_path); keys(actual_plan, PLAN_FIELDS, 'candidate plan')
    if not _same_sources(actual_plan, plan(run, context)): raise ValueError('candidate plan differs from upstream')
    execution = read_json(execution_path); keys(execution, EXECUTION_FIELDS, 'candidate execution')
    if type(execution['schema_version']) is not int or execution['schema_version'] != 1 or execution['run_id'] != run.name or not equal_identity(execution['composition_identity'], thaw(context['composition_identity'])):
        raise ValueError('candidate execution association differs')
    evidence = report['request_evidence']
    if not isinstance(evidence, dict): raise ValueError('candidate evidence index required')
    for name, identity in evidence.items():
        if type(name) is not str or '\\' in name or Path(name).is_absolute() or Path(name).as_posix() != name or any(part in ('.', '..') for part in name.split('/')):
            raise ValueError('candidate evidence key alias/escape')
        ids['evidence/'+name] = fresh(identity, run=run, expected=_local(run, run/name))
    wanted = index_evidence(run, plan_path, execution_path, execution['commands'])
    if not _same_sources(evidence, wanted): raise ValueError('candidate evidence missing/extra/different')
    media = commands_media(config, run, execution['commands'], context, evidence)
    if not _same(media, execution['effective_media']) or not _same(media, report['effective_media']) or not _same(media, composition['effective_media']):
        raise ValueError('candidate effective media differs from raw evidence/upstream')
    srt = validate_srt(context['subtitle_path'], composition['subtitles']['events'], total_samples=context['expected_media']['video_samples'])
    if not _same(srt, execution['srt_check']): raise ValueError('candidate SRT evidence differs')
    if inspect_actual:
        from .candidate_checks import inspect_composition
        from .paths import RuntimePaths
        actual, _ = inspect_composition(context['candidate_path'], fps=media['fps'], frames=media['frames'], channels=media['channels'],
            config=config, paths=RuntimePaths.from_config(config), logger=ValidationLogger(run), cwd=run/'logs/validation')
        if not _same({k: v for k, v in actual.items() if k != 'identity'}, media):
            raise ValueError('fresh candidate media differs from committed evidence')
    _again(ids)
    return ids
