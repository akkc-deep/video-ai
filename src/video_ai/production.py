"""Public automatic production entry with durable generation and composition."""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from types import MappingProxyType
import traceback
from uuid import uuid4

from .config import ConfigError, ProjectConfig, load_config
from .runtime.manifest import ManifestStore, create_manifest, hash_file, thaw, validate_run_dir
from .runtime.paths import RuntimePaths, create_run, resolve_cli_path
from .runtime.production_inputs import (DEFAULT_CONFIG, _save_bytes, check_stage_space, freeze_inputs,
                                        load_frozen_inputs, production_preflight, read_script, validate_supported)
from .runtime.production_state import (STAGES, ProductionRefused, ProductionStateStore, RunLock,
                                       absolute_path, object_fields, run_path, validate_error, write_exclusive)

TECHNICAL_CHECKS = ('source_text_coverage', 'audio_samples', 'frame_mapping', 'subtitles', 'final_media')


@dataclass(frozen=True)
class ProductionResult:
    schema_version: int = 1
    run_id: str | None = None
    run_dir: Path | None = None
    status: str = 'blocked'
    active_stage: str | None = None
    movie: Path | None = None
    subtitle: Path | None = None
    receipt_path: Path | None = None
    log_dir: Path | None = None
    technical_checks: Mapping[str, str] = field(default_factory=lambda: {key: 'unverified' for key in TECHNICAL_CHECKS})
    human_review: str = 'unverified'
    error: Mapping | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1: raise ValueError('schema_version must be integer 1')
        if self.status not in ('delivered', 'failed', 'blocked', 'interrupted'): raise ValueError('invalid production result status')
        if self.active_stage is not None and self.active_stage not in STAGES: raise ValueError('invalid active_stage')
        if self.human_review != 'unverified': raise ValueError('human review must remain unverified')
        checks = dict(self.technical_checks)
        object_fields(checks, TECHNICAL_CHECKS, 'technical_checks')
        if any(v not in ('passed', 'failed', 'unverified') for v in checks.values()): raise ValueError('invalid technical check')
        object.__setattr__(self, 'technical_checks', MappingProxyType(checks))
        for name in ('run_dir', 'movie', 'subtitle', 'receipt_path', 'log_dir'):
            value = getattr(self, name)
            if value is not None: object.__setattr__(self, name, absolute_path(str(value)))
        if self.run_dir is not None:
            validate_run_dir(self.run_dir)
            if self.run_id != self.run_dir.name: raise ValueError('result run identity differs')
            if self.log_dir is not None: run_path(self.run_dir, self.log_dir)
        elif self.run_id is not None or self.log_dir is not None: raise ValueError('result has no run directory')
        if self.error is not None:
            error = thaw(self.error); object_fields(error, ('kind', 'message', 'evidence_paths'), 'result error')
            if not isinstance(error['kind'], str) or not error['kind'] or not isinstance(error['message'], str) or not error['message']:
                raise ValueError('error kind/message must be nonempty strings')
            if not isinstance(error['evidence_paths'], list): raise ValueError('error evidence_paths must be a list')
            if self.run_dir is not None: validate_error(error, self.run_dir)
            elif error['evidence_paths']: raise ValueError('evidence requires run')
            object.__setattr__(self, 'error', MappingProxyType(dict(error, evidence_paths=tuple(error['evidence_paths']))))
        if self.status == 'delivered':
            if self.run_dir is None or any(p is None for p in (self.movie, self.subtitle, self.receipt_path)) or self.error is not None:
                raise ValueError('delivered requires actual delivery paths and no error')
        elif any(p is not None for p in (self.movie, self.subtitle, self.receipt_path)):
            raise ValueError('undelivered result cannot expose official artifacts')
        json.dumps(self.to_dict(), allow_nan=False)

    def to_dict(self): return thaw(self)

    @property
    def exit_code(self): return {'delivered': 0, 'failed': 1, 'blocked': 2, 'interrupted': 130}[self.status]


def _finish_prefix(frozen, state, manifest):
    snapshot = state.snapshot()
    backing = manifest.snapshot()['stages']['preflight']['status']
    if backing == 'completed' and snapshot['stages']['preflight']['status'] != 'completed':
        raise ProductionRefused('manifest preflight cursor is ahead of production state')
    if backing not in ('pending', 'running', 'completed'):
        raise ProductionRefused('manifest preflight has incompatible terminal state')
    if snapshot['active_stage'] == 'preflight':
        state.start_stage('preflight')
        if manifest.snapshot()['stages']['preflight']['status'] == 'pending': manifest.record_stage('preflight', 'running')
        path = run_path(state.run_dir, state.run_dir/'production/preflight.json')
        if not path.exists():
            report = production_preflight(frozen.config, state.run_dir)
            if not report.passed:
                failures = [c for c in report.checks if not c.passed]
                message = '; '.join(f'{c.name}: {c.details}' for c in failures)
                if any(c.name == 'production.space' or c.name.startswith('ffmpeg-') or c.name == 'ffprobe-version' for c in failures):
                    raise OSError(message)
                raise ProductionRefused(message)
            state.write_report('preflight', {'checks': [dict(name=c.name, passed=c.passed, details=c.details) for c in report.checks]})
        # A prior fsync'ed report is reusable if the cursor was not committed.
        state.complete_stage('preflight')
    if state.snapshot()['stages']['preflight']['status'] == 'completed':
        if manifest.snapshot()['stages']['preflight']['status'] == 'pending':
            manifest.record_stage('preflight', 'running')
        if manifest.snapshot()['stages']['preflight']['status'] == 'running':
            path = run_path(state.run_dir, state.run_dir/'production/preflight.json')
            identity = hash_file(path)
            manifest.record_stage('preflight', 'completed', artifacts=[dict(path=str(path), category='run',
                bytes=identity.bytes, sha256=identity.sha256, verified_at=identity.verified_at)])
    check_stage_space(frozen.config)


def _run_generation(frozen,state,manifest):
    if frozen.config.production_strategy == 'paragraph_jimeng_v1':
        raise ProductionRefused('paragraph_jimeng_v1 scene coordinator is not yet implemented; use the JIM-01 candidate API')
    from .runtime.logging import RunLogger
    from .runtime.production_storyboard import produce_units,produce_storyboard
    from .runtime.production_visuals import produce_start_images,produce_source_clips
    from .runtime.production_upscale import produce_upscaled_clips
    from .runtime.production_composition import produce_composition
    from .runtime.production_speech import produce_speech
    from .runtime.production_timeline import produce_timeline
    from .runtime.production_delivery import produce_delivery
    paths=RuntimePaths.from_config(frozen.config)
    logger=RunLogger(state.run_dir,production=True)
    if state.snapshot()['stages']['composition']['status']=='completed':
        from .runtime.production_completed import validate_completed_prefix
        validate_completed_prefix(frozen,state,manifest,logger)
        return produce_delivery(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('units')
    units=produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('speech')
    audio=produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('timeline')
    timeline,slots=produce_timeline(frozen,units,audio,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('storyboard')
    board=produce_storyboard(frozen,units,timeline,slots,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('start_images')
    images=produce_start_images(frozen,board,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('source_clips')
    sources=produce_source_clips(frozen,board,timeline,images,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('upscale')
    upscaled=produce_upscaled_clips(frozen,sources,state=state,manifest=manifest,paths=paths,logger=logger)
    logger.progress('composition')
    produce_composition(frozen,units,timeline,upscaled,state=state,manifest=manifest,paths=paths,logger=logger)
    return produce_delivery(frozen,state=state,manifest=manifest,paths=paths,logger=logger)


def _record_error(run, state, exc):
    paths = [str(p) for p in getattr(exc,'evidence_paths',()) if run is not None and Path(p).is_file() and Path(p).is_relative_to(run)]
    message = str(exc) or ('Interrupted' if isinstance(exc, KeyboardInterrupt) else type(exc).__name__)
    owned=True
    if state is not None and hasattr(state,'_assert_owned'):
        try:state._assert_owned()
        except (OSError,ValueError):owned=False
    if run is not None and not owned:
        paths.extend(str(p) for p in (run/'.make-video.lock',run/'production/production-state.json') if p.is_file())
    if run is not None and owned:
        try:
            path = run_path(run, run/f'logs/production/errors/{uuid4().hex}.txt')
            _save_bytes(path, ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).encode('utf-8'))
            paths.append(str(path))
        except (OSError, ValueError): pass
    error = dict(kind=type(exc).__name__, message=message, evidence_paths=paths)
    status = 'interrupted' if isinstance(exc, KeyboardInterrupt) else ('blocked' if isinstance(exc, ValueError) else 'failed')
    if state is not None and owned:
        try: state.set_invocation(status, error)
        except (OSError, ValueError): pass  # Keep the original exception and intact previous cursor.
    active = None
    checks = {key:'unverified' for key in TECHNICAL_CHECKS}
    if state is not None:
        try:
            snapshot=state.snapshot();active=snapshot['active_stage']
            if snapshot['stages']['units']['status']=='completed': checks['source_text_coverage']='passed'
            if snapshot['stages']['speech']['status']=='completed': checks['audio_samples']='passed'
            if snapshot['stages']['source_clips']['status']=='completed': checks['frame_mapping']='passed'
            if snapshot['stages']['composition']['status']=='completed':
                from .config import read_json
                from .runtime.production_composition_records import validate_technical_checks
                from .runtime.production_state import ArtifactStamp
                technical=read_json(run_path(run,run/'production/technical-checks.json'))
                validate_technical_checks(technical,run)
                ArtifactStamp.from_dict(technical['composition_report']).verify()
                checks=dict(technical['technical_checks'])
        except (OSError, ValueError): pass
    return ProductionResult(run_id=run.name if run else None, run_dir=run, status=status,
                            active_stage=active, log_dir=run/'logs/production' if run else None, error=error,technical_checks=checks)


def make_video(config=None, *, script=None, text=None, run_dir=None, output_path=None, cpu_planner=None, image_model=None) -> ProductionResult:
    run = state = result = None
    try:
        if sum(v is not None for v in (script, text, run_dir)) != 1:
            raise ProductionRefused('provide exactly one of script, text, or run_dir')
        if run_dir is None:
            raw, _ = read_script(script=script, text=text)
            config = config if isinstance(config, ProjectConfig) else load_config(
                resolve_cli_path(str(config), Path.cwd()) if config is not None else DEFAULT_CONFIG)
            validate_supported(config)
            from .jimeng_config import override_image_model
            override_image_model(config.image_generation, image_model)
            if output_path is not None:
                from .runtime.production_inputs import output_paths
                # Reject invalid or occupied output before allocating a new run.
                output_paths(config, config.project_root/'runs'/'new', output_path)
            run = create_run(RuntimePaths.from_config(config))
        else:
            run = validate_run_dir(resolve_cli_path(str(run_dir), Path.cwd()))
            if not run.is_dir(): raise ProductionRefused('production run does not exist')
        # Catch invocation failures inside the lock so state/error evidence cannot race a resume.
        with RunLock(run) as run_lock:
            try:
                if run_dir is None:
                    frozen = freeze_inputs(config, run, script=script, text=text, output_path=output_path,
                                           cpu_planner=cpu_planner, raw_script_bytes=raw, image_model=image_model)
                    state = ProductionStateStore.create(run)
                    inputs = {role: identity for role, identity in frozen.options['execution_policy']['input_identities'].items()}
                    manifest = create_manifest(run, frozen.config, inputs=inputs, models={}, workflows={}, verify_integrity=False)
                else:
                    frozen = load_frozen_inputs(run, config=config, output_path=output_path, cpu_planner=cpu_planner, image_model=image_model)
                    state = ProductionStateStore.open(run)
                    manifest = ManifestStore.open(run, verify_integrity=False)
                    state._run_lock_owner=dict(run_lock.owner)
                    state.set_invocation('running')
                state._run_lock_owner=dict(run_lock.owner)
                _finish_prefix(frozen, state, manifest)
                targets=frozen.options['output_paths']
                expected=ProductionResult(run_id=run.name,run_dir=run,status='delivered',active_stage=None,
                    movie=targets['movie'],subtitle=targets['subtitle'],receipt_path=targets['receipt'],
                    log_dir=run/'logs/production',technical_checks={key:'passed' for key in TECHNICAL_CHECKS})
                json.dumps(expected.to_dict(),ensure_ascii=False,allow_nan=False)
                receipt=_run_generation(frozen,state,manifest)
                snapshot=state.snapshot()
                if snapshot['invocation_status']!='delivered' or snapshot['active_stage'] is not None or receipt['run_id']!=run.name:
                    raise ProductionRefused('delivery result requires persisted final state')
                result=expected
            except (Exception, KeyboardInterrupt) as exc:
                result = _record_error(run, state, exc)
            invocation = run_path(run, run/f'logs/production/invocations/{uuid4().hex}.json')
            from .config import read_json
            if not run_lock.path.is_file() or read_json(run_lock.path)!=run_lock.owner:
                raise ProductionRefused('cannot record invocation after losing held run lock')
            write_exclusive(invocation, result.to_dict())
        return result
    except (Exception, KeyboardInterrupt) as exc:
        if result is not None:
            # The inner invocation has already failed: preserve its cause, evidence and exit code.
            if result.error is None:
                return ProductionResult(run_id=run.name,run_dir=run,
                    status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'blocked' if isinstance(exc,ValueError) else 'failed',
                    log_dir=run/'logs/production',technical_checks=result.technical_checks,
                    error=dict(kind=type(exc).__name__,message=str(exc) or type(exc).__name__,evidence_paths=[]))
            error = thaw(result.error)
            error['message'] += f'; finalization also failed: {type(exc).__name__}: {exc}'
            return replace(result, error=error)
        # In particular, a rejected lock never authorizes writing into another owner's run.
        if isinstance(exc, ConfigError) and isinstance(exc.__cause__ or exc.__context__, OSError):
            exc = OSError(str(exc))
        return ProductionResult(run_id=run.name if run else None, run_dir=run,
            status='interrupted' if isinstance(exc, KeyboardInterrupt) else ('blocked' if isinstance(exc, ValueError) else 'failed'),
            error=dict(kind=type(exc).__name__, message=str(exc) or type(exc).__name__, evidence_paths=[]))
