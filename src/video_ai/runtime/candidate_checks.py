"""Exclusive automatic candidate validation and fresh committed consumer."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from uuid import uuid4

from ..config import ProjectConfig, load_config, read_json
from ..media.composition_video import inspect_composition
from ..media.srt_validation import validate_srt
from ..planning.source_clips import _same
from .composition_checks import load_committed_composition
from ._composition_inputs import fresh
from ._candidate_evidence import ValidationLogger, composition_context, plan, validate, validation, index_evidence, upstream_unchanged
from .manifest import ManifestStore, hash_file, thaw, now
from .paths import RuntimePaths
from .timeline_checks import _run_path, _local, _again, _artifact, _fresh
from .upscale_checks import atomic_report


class CandidateRefusal(ValueError):
    """Invalid candidate admission before validation starts (CLI exit 2)."""


@dataclass(frozen=True)
class CandidateResult:
    passed: bool
    run_dir: Path
    report_path: Path
    candidate_path: Path
    subtitle_path: Path
    total_frames: int
    total_samples: int
    ready_for_review: bool
    staging_only: bool
    status: str


def result(run, status, context=None):
    media = context['expected_media'] if context else {}
    return CandidateResult(status == 'completed', run, run/'candidate-validation.json', run/'staging/composition/candidate.mp4',
        run/'staging/composition/subtitle.srt', media.get('frames', 0), media.get('video_samples', 0), status == 'completed', True, status)


@contextmanager
def exclusive(run):
    path = _local(run, run/'.validation.lock'); owner = dict(pid=os.getpid(), token=uuid4().hex)
    try: fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except (OSError, ValueError) as exc: raise CandidateRefusal('validation lock refused: ' + str(exc)) from exc
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(owner, file); file.flush(); os.fsync(file.fileno())
        yield owner
    finally:
        try:
            if read_json(_local(run, path)) == owner: path.unlink()
        except (ValueError, OSError): pass
        except KeyboardInterrupt:
            if ManifestStore.open(run).snapshot()['stages']['validation']['status'] != 'completed': raise


def lock_unchanged(run, owner):
    if read_json(_local(run, run/'.validation.lock')) != owner: raise OSError('foreign validation lock retained')


def context_for(config, run):
    composition = load_committed_composition(run)
    return composition_context(config, run, composition, hash_file(_local(run, run/'composition.json')))


def frozen_config(config, snapshot):
    resolved = thaw(config); resolved.pop('voice'); resolved.pop('raw')
    frozen = snapshot['config_snapshot']
    if str(config.config_file) != frozen['path'] or not _same(config.raw, frozen['raw']) or not _same(resolved, frozen['resolved']):
        raise ValueError('candidate configuration differs from frozen run snapshot')


def validate_candidate(config: ProjectConfig, *, run_dir: Path) -> CandidateResult:
    try: run = _run_path(run_dir); store = ManifestStore.open(run)
    except (ValueError, OSError, TypeError) as exc: raise CandidateRefusal(str(exc)) from exc
    with exclusive(run) as owner:
        try:
            snapshot = store.snapshot(); stage = snapshot['stages']['validation']
            path = _local(run, run/'candidate-validation.json'); folder = _local(run, run/'logs/validation')
            if stage['status'] != 'pending' or stage['artifacts'] or 'candidate_validation' in snapshot['workflows'] or path.exists() or folder.exists():
                raise ValueError('pending validation without orphan report/evidence required')
            frozen_config(config, snapshot)
            context = context_for(config, run)
            _again(context['identities']); _again(context['bound_identities'])
            upstream_unchanged(store.snapshot(), snapshot); lock_unchanged(run, owner)
        except (ValueError, OSError, TypeError, KeyError) as exc: raise CandidateRefusal(str(exc)) from exc
        logger = ValidationLogger(run)
        try:
            def begin(data):
                upstream_unchanged(data, snapshot); lock_unchanged(run, owner)
                if data['stages']['validation'] != stage or 'candidate_validation' in data['workflows']:
                    raise ValueError('candidate admission state changed')
                store._record_status(data, data['stages']['validation'], 'running', [], None, 'validation', None)
            store.update(begin); folder.mkdir()
            plan_path = logger.save_json('validation/plan.json', plan(run, context))
            expected = context['expected_media']
            info, commands = inspect_composition(context['candidate_path'], fps=expected['fps'], frames=expected['frames'], channels=expected['channels'],
                config=config, paths=RuntimePaths.from_config(config), logger=logger, cwd=folder)
            media = {k: v for k, v in info.items() if k != 'identity'}
            srt = validate_srt(context['subtitle_path'], context['composition']['subtitles']['events'], total_samples=expected['video_samples'])
            execution_path = logger.save_json('validation/execution.json', dict(schema_version=1, run_id=run.name,
                composition_identity=thaw(context['composition_identity']), commands=commands, effective_media=media, srt_check=srt))
            composition = context['composition']
            report = dict(schema_version=1, run_id=run.name, created_at=now(), status='completed', passed=True,
                staging_only=True, ready_for_review=True, composition_identity=thaw(context['composition_identity']),
                input_identities=thaw(context['identities']), candidate_identity=thaw(context['candidate_identity']),
                subtitle_identity=thaw(context['subtitle_identity']), effective_media=media, subtitle_events=composition['subtitles']['events'],
                requirement_bindings=composition['requirement_bindings'], cue_checks=composition['cue_checks'], provenance=composition['provenance'],
                validation=validation(), plan_identity=thaw(hash_file(plan_path)), execution_identity=thaw(hash_file(execution_path)),
                request_evidence=index_evidence(run, plan_path, execution_path, commands))
            report_ids = validate(config, run, report, context)
            fresh_context = context_for(config, run)
            _again(report_ids); _again(fresh_context['identities']); _again(fresh_context['bound_identities'])
            upstream_unchanged(store.snapshot(), snapshot); lock_unchanged(run, owner)
            atomic_report(run, path, report)
            report_ids = validate(config, run, read_json(path), fresh_context)
            identity = hash_file(path)
            def commit(data):
                upstream_unchanged(data, snapshot); lock_unchanged(run, owner); _again(report_ids); _again({'report': identity})
                if data['stages']['validation']['status'] != 'running' or 'candidate_validation' in data['workflows']:
                    raise ValueError('validation state changed before completion')
                data['workflows']['candidate_validation'] = thaw(identity)
                store._record_status(data, data['stages']['validation'], 'completed', [_artifact(identity)], None, 'validation', None)
            store.update(commit)
            return result(run, 'completed', context)
        except BaseException as exc:
            if store.snapshot()['stages']['validation']['status'] == 'completed': return result(run, 'completed', context)
            status = 'interrupted' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed'
            evidence = []
            try:
                evidence.append(str(logger.exception('validation', None, exc)))
                evidence.append(str(logger.save_json(f'validation/diagnostic-{uuid4().hex}.json', dict(schema_version=1, run_id=run.name,
                    status=status, passed=False, ready_for_review=False, message=str(exc), created_at=now()))))
            except (ValueError, OSError, KeyboardInterrupt): pass
            error = dict(kind=status, message=str(exc), traceback_path=evidence[0] if evidence else None, evidence_paths=evidence)
            try:
                def fail(data):
                    current = data['stages']['validation']
                    if current['status'] == 'running': store._record_status(data, current, status, current['artifacts'], error, 'validation', None)
                store.update(fail)
            except (ValueError, OSError, KeyboardInterrupt): pass
            if isinstance(exc, (KeyboardInterrupt, SystemExit)): raise
            return result(run, 'failed', context)


def load_committed_candidate(run_dir: Path) -> dict:
    run = _run_path(run_dir); store = ManifestStore.open(run); snapshot = store.snapshot()
    stage = snapshot['stages']['validation']; path = _local(run, run/'candidate-validation.json')
    if stage['status'] != 'completed': raise ValueError('candidate validation is not completed')
    registered = snapshot['workflows'].get('candidate_validation')
    if registered is None: raise ValueError('candidate validation receipt missing')
    identity = fresh(registered, run=run, expected=path)
    if len(stage['artifacts']) != 1 or stage['artifacts'][0]['path'] != str(path): raise ValueError('candidate artifact missing/extra')
    artifact = _fresh(stage['artifacts'][0], run=run, expected=path)
    if artifact.sha256 != identity.sha256 or artifact.bytes != identity.bytes: raise ValueError('candidate artifact differs from receipt')
    config = load_config(Path(snapshot['config_snapshot']['path'])); frozen_config(config, snapshot)
    context = context_for(config, run)
    report = read_json(path); report_ids = validate(config, run, report, context, inspect_actual=True)
    _again(report_ids); _again({'report': identity})
    current = store.snapshot(); upstream_unchanged(current, snapshot)
    if current['stages']['validation'] != stage or current['workflows'].get('candidate_validation') != registered:
        raise OSError('candidate receipt/state changed during consumption')
    return report
