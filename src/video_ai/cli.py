"""Task-two CLI: environment inspection with explicit limits on evidence."""
import argparse
import json
from pathlib import Path
import sys

from .config import ConfigError, load_config
from .runtime.paths import _validate_spelling, resolve_cli_path
from .runtime.preflight import preflight


def _load_cli_config(value: str, invocation_cwd: Path):
    try:
        return load_config(resolve_cli_path(value, invocation_cwd))
    except ConfigError as exc:
        if isinstance(exc.__cause__ or exc.__context__, OSError):
            raise OSError(str(exc)) from exc
        raise


def _lexical_cli_path(value: str, invocation_cwd: Path) -> Path:
    path = Path(_validate_spelling(value))
    return path if path.is_absolute() else invocation_cwd / path


def main(argv: list[str] | None = None) -> int:
    invocation_cwd = Path.cwd()
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='video-ai', description='AI video orchestration: local environment preflight')
    commands = parser.add_subparsers(dest='command', required=True)
    automatic = commands.add_parser('make-video', help='automatically produce from UTF-8 text, or resume its frozen run')
    input_group = automatic.add_mutually_exclusive_group(required=True)
    for name in ('script', 'text', 'run-dir'):
        input_group.add_argument('--'+name, metavar='TEXT' if name == 'text' else 'PATH')
    automatic.add_argument('--config', metavar='PATH')
    automatic.add_argument('--output', metavar='PATH')
    automatic.add_argument('--cpu-planner', action='store_true', default=None)
    automatic.add_argument('--image-model', metavar='REQ_KEY', help='image model for a new Jimeng run')
    automatic.add_argument('--json', action='store_true')
    for name in ('run', 'resume'):
        flow = commands.add_parser(name, help='coordinate stages with fresh recovery and explicit author checkpoints')
        flow.add_argument('--config', required=True, metavar='PATH')
        flow.add_argument('--json', action='store_true')
        flow.add_argument('--output', metavar='PATH')
        if name == 'run':
            flow.add_argument('--script', required=True, metavar='PATH')
            flow.add_argument('--unit-review', required=True, metavar='PATH')
            flow.add_argument('--image-inputs', metavar='PATH')
            flow.add_argument('--settings', metavar='PATH')
            flow.add_argument('--cpu-planner', action='store_true')
        else:
            flow.add_argument('--run-dir', required=True, metavar='PATH')
            flow.add_argument('--reviews', metavar='PATH')
            flow.add_argument('--changes', metavar='PATH')
            flow.add_argument('--retry-failed', action='store_true')
            flow.add_argument('--publish', action='store_true')
    doctor = commands.add_parser('doctor', help='check paths, local resources and FFmpeg capabilities')
    doctor.add_argument('--config', required=True, metavar='PATH')
    doctor.add_argument('--script', metavar='PATH')
    doctor.add_argument('--output', metavar='PATH')
    doctor.add_argument('--json', action='store_true', help='emit a versioned JSON report')
    migration = commands.add_parser('migrate',help='copy and verify inventoried dependencies')
    migration.add_argument('--inventory',required=True,metavar='PATH')
    mode = migration.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run',action='store_true')
    mode.add_argument('--execute',action='store_true')
    components = commands.add_parser('verify-components',help='verify components from migrated locations')
    components.add_argument('--config',required=True,metavar='PATH')
    components.add_argument('--only',choices=('environment','ollama','tts','sdxl','wan','upscale','media'))
    speech = commands.add_parser('synthesize-speech', help='generate and validate fixed-voice speech from original UTF-8 text')
    speech.add_argument('--config', required=True, metavar='PATH')
    speech.add_argument('--script', required=True, metavar='PATH')
    speech.add_argument('--json', action='store_true')
    timeline = commands.add_parser('plan-timeline', help='build sample/frame timeline from verified speech in an existing run')
    timeline.add_argument('--config', required=True, metavar='PATH')
    timeline.add_argument('--run-dir', required=True, metavar='PATH')
    timeline.add_argument('--json', action='store_true')
    for command,flag in [('plan-storyboard','--timing-review'),('finalize-storyboard','--review')]:
        storyboard=commands.add_parser(command,help='plan visual draft or finalize its bound text review')
        storyboard.add_argument('--config',required=True,metavar='PATH')
        storyboard.add_argument('--run-dir',required=True,metavar='PATH')
        storyboard.add_argument(flag,required=True,metavar='PATH')
        storyboard.add_argument('--json',action='store_true')
        if command=='plan-storyboard':storyboard.add_argument('--cpu-planner',action='store_true',help='disable Ollama GPU offload; bounded 600-second CPU request budget')
    for command in ('prepare-start-images','finalize-start-images'):
        image=commands.add_parser(command,help='prepare reviewed 16:9 start images or commit their visual review')
        image.add_argument('--config',required=True,metavar='PATH')
        image.add_argument('--run-dir',required=True,metavar='PATH')
        image.add_argument('--json',action='store_true')
        if command=='prepare-start-images':
            image.add_argument('--image-inputs',metavar='PATH')
            image.add_argument('--image-width',type=int,default=1280)
            image.add_argument('--image-height',type=int,default=720)
        else:image.add_argument('--review',required=True,metavar='PATH')
    for command in ('prepare-source-clips','finalize-source-clips'):
        source=commands.add_parser(command,help='prepare native16 Wan sources or commit continuous-video review')
        source.add_argument('--config',required=True,metavar='PATH')
        source.add_argument('--run-dir',required=True,metavar='PATH')
        source.add_argument('--json',action='store_true')
        if command=='finalize-source-clips':source.add_argument('--review',required=True,metavar='PATH')
    for command in ('prepare-upscaled-clips','resume-upscaled-clips','finalize-upscaled-clips'):
        upscale=commands.add_parser(command,help='prepare native16 PyTorch 1080p clips or commit source/new video review')
        upscale.add_argument('--config',required=True,metavar='PATH')
        upscale.add_argument('--run-dir',required=True,metavar='PATH')
        upscale.add_argument('--json',action='store_true')
        if command=='finalize-upscaled-clips':upscale.add_argument('--review',required=True,metavar='PATH')
    composition=commands.add_parser('compose-clips',help='compose verified clips, original narration and subtitles to staging')
    composition.add_argument('--config',required=True,metavar='PATH')
    composition.add_argument('--run-dir',required=True,metavar='PATH')
    composition.add_argument('--settings',metavar='PATH')
    composition.add_argument('--json',action='store_true')
    for command in ('validate-candidate', 'publish-candidate'):
        final = commands.add_parser(command, help='validate staging candidate or publish the exact human-accepted bytes')
        final.add_argument('--config', required=True, metavar='PATH')
        final.add_argument('--run-dir', required=True, metavar='PATH')
        final.add_argument('--json', action='store_true')
        if command == 'publish-candidate':
            final.add_argument('--review', required=True, metavar='PATH')
            final.add_argument('--acceptance', required=True, metavar='PATH')
            final.add_argument('--output', metavar='PATH')
    options=None
    try:
        options = parser.parse_args(argv)
        if options.command == 'make-video':
            from .production import make_video
            result = make_video(options.config, script=options.script, text=options.text, run_dir=options.run_dir,
                                output_path=options.output, cpu_planner=options.cpu_planner, image_model=options.image_model)
            if options.json:
                print(json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False))
            else:
                print(f'{result.status}: stage={result.active_stage}; run={result.run_dir}')
                if result.movie is not None: print(f'MP4: {result.movie}\nSRT: {result.subtitle}\nReceipt: {result.receipt_path}')
                if result.error is not None: print(result.error['message'], file=sys.stderr)
                if result.run_dir is not None:
                    print(f'Resume: video-ai make-video --run-dir "{result.run_dir}"')
            return result.exit_code
        if options.command in ('run', 'resume'):
            from .pipeline import run_pipeline, resume_pipeline
            from .runtime.manifest import thaw
            config = _load_cli_config(options.config, invocation_cwd)
            output = _lexical_cli_path(options.output, invocation_cwd) if options.output else None
            if options.command == 'run':
                result = run_pipeline(config, script=_lexical_cli_path(options.script, invocation_cwd),
                    unit_review_path=_lexical_cli_path(options.unit_review, invocation_cwd),
                    image_inputs_path=_lexical_cli_path(options.image_inputs, invocation_cwd) if options.image_inputs else None,
                    settings_path=_lexical_cli_path(options.settings, invocation_cwd) if options.settings else None,
                    output_path=output, cpu_planner=options.cpu_planner)
            else:
                result = resume_pipeline(config, run_dir=_lexical_cli_path(options.run_dir, invocation_cwd),
                    reviews_path=_lexical_cli_path(options.reviews, invocation_cwd) if options.reviews else None,
                    changes_path=_lexical_cli_path(options.changes, invocation_cwd) if options.changes else None,
                    retry_failed=options.retry_failed, publish=options.publish, output_path=output)
            data = dict(schema_version=1, **thaw(result))
            if result.report_path is not None:
                from .config import read_json
                data['validation'] = read_json(result.report_path)['validation']
            else:
                data['validation'] = {key:'unverified' for key in
                    ('actual_final_video_semantics','actual_final_video_sync','full_film_acceptance')}
            if options.json: print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print(f'{result.status}: {result.run_dir}; stage={result.active_stage}; published={str(result.published).lower()}')
                if result.waiting_for: print('waiting_for='+', '.join(result.waiting_for))
                if result.report_path: print(f'report={result.report_path}')
            return {'candidate_ready':0, 'published':0, 'awaiting_review':3, 'awaiting_acceptance':3,
                'failed':1, 'refused':2, 'interrupted':130}[result.status]
        if options.command in ('validate-candidate', 'publish-candidate'):
            from .runtime.manifest import thaw
            config = _load_cli_config(options.config, invocation_cwd)
            run = _lexical_cli_path(options.run_dir, invocation_cwd)
            if options.command == 'validate-candidate':
                from .runtime.candidate_checks import validate_candidate
                result = validate_candidate(config, run_dir=run)
            else:
                from .runtime.publication import publish_candidate
                result = publish_candidate(config, run_dir=run,
                    review_path=_lexical_cli_path(options.review, invocation_cwd),
                    acceptance_path=_lexical_cli_path(options.acceptance, invocation_cwd),
                    output_path=_lexical_cli_path(options.output, invocation_cwd) if options.output else None)
            accepted = options.command == 'publish-candidate' and result.passed
            limits = {key: 'passed' if accepted else 'unverified' for key in
                ('actual_final_video_semantics', 'actual_final_video_sync', 'full_film_acceptance')}
            limits.update({key: True if result.passed else 'unverified' for key in
                ('media_passed', 'source_frame_mapping_passed', 'subtitle_text_timing_passed',
                 'narration_samples_passed', 'input_associations_passed')})
            if options.json:
                print(json.dumps(dict(thaw(result), validation=limits), ensure_ascii=False, indent=2))
            else:
                print(f'{result.status}: {result.report_path}; staging_only={str(result.staging_only).lower()}; '
                    f'technical_media/source_frames/subtitles/narration/inputs={"passed" if result.passed else "unverified"}; '
                    f'final_video_semantics/sync/full_film_acceptance={"passed" if accepted else "unverified"}')
            return 0 if result.passed else 1
        if options.command=='compose-clips':
            from .runtime.composition_checks import compose_clips
            from .runtime.manifest import thaw
            config=_load_cli_config(options.config,invocation_cwd)
            result=compose_clips(config,run_dir=_lexical_cli_path(options.run_dir,invocation_cwd),settings_path=_lexical_cli_path(options.settings,invocation_cwd) if options.settings else None)
            if options.json:
                from .runtime.composition_checks import validation
                limits={k:v for k,v in validation().items() if k in ('actual_final_video_semantics','actual_final_video_sync','full_film_acceptance')}
                print(json.dumps(dict(thaw(result),validation=limits),ensure_ascii=False,indent=2))
            else:print(f'{result.status}: frames={result.total_frames}; staging_only=true; final_video_semantics/sync/full_film_acceptance=unverified; {result.candidate_path}; {result.subtitle_path}')
            return 0 if result.passed else 1
        if options.command in ('prepare-upscaled-clips','resume-upscaled-clips','finalize-upscaled-clips'):
            from .runtime.upscale_checks import prepare_upscaled_clips,resume_upscaled_clips,finalize_upscaled_clips
            from .runtime.manifest import thaw
            config=_load_cli_config(options.config,invocation_cwd)
            run=_lexical_cli_path(options.run_dir,invocation_cwd)
            if options.command=='prepare-upscaled-clips':result=prepare_upscaled_clips(config,run_dir=run)
            elif options.command=='resume-upscaled-clips':result=resume_upscaled_clips(config,run_dir=run)
            else:result=finalize_upscaled_clips(config,run_dir=run,review_path=_lexical_cli_path(options.review,invocation_cwd))
            if options.json:print(json.dumps(thaw(result),ensure_ascii=False,indent=2))
            else:print(f'{result.status}: clips={result.clip_count}; ready_for_composition={str(result.ready_for_composition).lower()}; {result.clips_path}')
            return 0 if result.passed else 1
        if options.command in ('prepare-source-clips','finalize-source-clips'):
            from .runtime.source_clip_checks import prepare_source_clips,finalize_source_clips
            from .runtime.manifest import thaw
            config=_load_cli_config(options.config,invocation_cwd)
            run=_lexical_cli_path(options.run_dir,invocation_cwd)
            if options.command=='prepare-source-clips':result=prepare_source_clips(config,run_dir=run)
            else:result=finalize_source_clips(config,run_dir=run,review_path=_lexical_cli_path(options.review,invocation_cwd))
            if options.json:print(json.dumps(thaw(result),ensure_ascii=False,indent=2))
            else:print(f'{result.status}: clips={result.clip_count}; ready_for_upscale={str(result.ready_for_upscale).lower()}; {result.clips_path}')
            return 0 if result.passed else 1
        if options.command in ('prepare-start-images','finalize-start-images'):
            from .runtime.start_image_checks import prepare_start_images,finalize_start_images
            from .runtime.manifest import thaw
            from .runtime.paths import _validate_spelling
            try:config=load_config(resolve_cli_path(options.config,invocation_cwd))
            except ConfigError as exc:
                if isinstance(exc.__cause__ or exc.__context__,OSError):raise OSError(str(exc)) from exc
                raise
            def image_path(value):
                path=Path(_validate_spelling(value))
                return path if path.is_absolute() else invocation_cwd/path
            run=image_path(options.run_dir)
            if options.command=='prepare-start-images':
                result=prepare_start_images(config,run_dir=run,image_inputs_path=image_path(options.image_inputs) if options.image_inputs else None,
                    width=options.image_width,height=options.image_height)
            else:result=finalize_start_images(config,run_dir=run,review_path=image_path(options.review))
            if options.json:print(json.dumps(thaw(result),ensure_ascii=False,indent=2))
            else:print(f'{result.status}: images={result.image_count}; ready_for_source_clips={str(result.ready_for_source_clips).lower()}; {result.images_path}')
            return 0 if result.passed else 1
        if options.command in ('plan-storyboard','finalize-storyboard'):
            from .runtime.storyboard_checks import plan_storyboard,finalize_storyboard
            from .runtime.manifest import thaw
            from .runtime.paths import _validate_spelling
            try:config=load_config(resolve_cli_path(options.config,invocation_cwd))
            except ConfigError as exc:
                if isinstance(exc.__cause__ or exc.__context__,OSError):raise OSError(str(exc)) from exc
                raise
            def supplied_path(value):
                path=Path(_validate_spelling(value))
                return path if path.is_absolute() else invocation_cwd/path
            run=supplied_path(options.run_dir)
            if options.command=='plan-storyboard':
                result=plan_storyboard(config,run_dir=run,timing_review_path=supplied_path(options.timing_review),cpu_planner=options.cpu_planner)
            else:
                result=finalize_storyboard(config,run_dir=run,review_path=supplied_path(options.review))
            if options.json:print(json.dumps(thaw(result),ensure_ascii=False,indent=2))
            else:print(f'{result.status}: shots={result.shot_count}; ready_for_images={str(result.ready_for_images).lower()}; {result.storyboard_path}')
            return 0 if result.passed else 1
        if options.command == 'plan-timeline':
            from .runtime.timeline_checks import plan_timeline
            from .runtime.manifest import thaw
            from .runtime.paths import _validate_spelling
            try:config = load_config(resolve_cli_path(options.config, invocation_cwd))
            except ConfigError as exc:
                cause=exc.__cause__ or exc.__context__
                if isinstance(cause,OSError):raise OSError(str(exc)) from exc
                raise
            # Preserve lexical path until runtime verifies it against redirects.
            supplied = Path(_validate_spelling(options.run_dir))
            run = supplied if supplied.is_absolute() else invocation_cwd / supplied
            result = plan_timeline(config, run_dir=run)
            if options.json:
                print(json.dumps(thaw(result), ensure_ascii=False, indent=2))
            else:
                print(f'{"PASS" if result.passed else "FAIL"} timeline: {result.timeline_path}')
                print(f'samples={result.total_samples}; frames={result.total_frames}; listening_accepted={str(result.listening_accepted).lower()}')
            return 0 if result.passed else 1
        if options.command == 'synthesize-speech':
            from .runtime.speech_checks import synthesize_script
            from .runtime.paths import RuntimePaths, create_run
            from .runtime.manifest import thaw
            config = load_config(resolve_cli_path(options.config, invocation_cwd))
            script = resolve_cli_path(options.script, invocation_cwd)
            result = synthesize_script(config, script, run_dir=create_run(RuntimePaths.from_config(config)))
            if options.json:
                print(json.dumps(thaw(result),ensure_ascii=False,indent=2))
            else:
                print(f'{"PASS" if result.passed else "FAIL"} speech: {result.segments_path}')
                print(f'samples={result.total_speech_samples}; listened={str(result.listened).lower()}')
            return 0 if result.passed else 1
        if options.command == 'migrate':
            from .runtime import migration as copy
            from .runtime.paths import SOURCE_ROOT, RuntimePaths, create_run
            from .runtime.manifest import create_manifest, hash_file
            from .runtime.logging import RunLogger
            config = load_config(SOURCE_ROOT/'config/production.example.json')
            run = create_run(RuntimePaths.from_config(config))
            inventory = resolve_cli_path(options.inventory,invocation_cwd)
            store = create_manifest(run,config,inputs={'inventory':hash_file(inventory/'files.json')},models={},workflows={})
            logger = RunLogger(run)
            store.record_stage('preflight','running')
            try:
                entries = copy.build_copy_plan(inventory)
                logger.save_json('copy-plan.json',entries)
                capacity = copy.check_capacity(entries,reserve_bytes=20*copy.GIB)
                logger.save_json('capacity.json',capacity)
                report = dict(run_dir=str(run),capacity=capacity,passed=capacity['passed'],dry_run=options.dry_run)
                if capacity['passed'] and options.execute:
                    report['migration'] = copy.migrate(entries,logger=logger,report_path=run/'migration.json')
                    report['passed'] = report['migration']['passed']
                copy.atomic_report(run/'migration-result.json',report)
            except BaseException as exc:
                error = dict(kind=type(exc).__name__,message=str(exc),
                             traceback_path=str(logger.exception('preflight',None,exc)),evidence_paths=[])
                store.record_stage('preflight','interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=error)
                report = dict(run_dir=str(run),passed=False,dry_run=options.dry_run,error=error)
                copy.atomic_report(run/'migration-result.json',report)
                print(json.dumps(report,ensure_ascii=False,indent=2))
                raise
            store.record_stage('preflight','completed' if report['passed'] else 'failed')
            print(json.dumps(report,ensure_ascii=False,indent=2))
            return 0 if report['passed'] else 1
        if options.command == 'verify-components':
            from .runtime.component_checks import verify_components
            from .runtime.paths import RuntimePaths,create_run
            config=load_config(resolve_cli_path(options.config,invocation_cwd))
            report=verify_components(config,run_dir=create_run(RuntimePaths.from_config(config)),only=options.only)
            print(json.dumps(report,ensure_ascii=False,indent=2))
            return 0 if report['passed'] else 1
        config_file = resolve_cli_path(options.config, invocation_cwd)
        config = load_config(config_file)
        script = resolve_cli_path(options.script, invocation_cwd) if options.script else None
        output = resolve_cli_path(options.output, invocation_cwd) if options.output else None
        report = preflight(config, script=script, output=output)
        if options.json:
            print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        else:
            for check in report.checks:
                print(f'{"PASS" if check.passed else "FAIL"} {check.name}: {check.details}')
            print(f'Logs: {report.log_dir or "no subprocesses started"}')
            print('inference_verified=false; full_run_space_checked=false; fast_profile_verified=false')
        return 0 if report.passed else 1
    except SystemExit as exc:
        if exc.code and effective_argv and effective_argv[0] == 'make-video' and '--json' in effective_argv:
            from .production import ProductionResult
            result = ProductionResult(error=dict(kind='ArgumentError', message='Invalid make-video arguments; see stderr.', evidence_paths=[]))
            print(json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False))
        return int(exc.code)
    except KeyboardInterrupt:
        if options is not None and options.command in ('run','resume') and options.json:
            print(json.dumps(dict(schema_version=1,run_dir=str(_lexical_cli_path(options.run_dir,invocation_cwd)) if options.command=='resume' else None,
                parent_run_dir=None,status='interrupted',active_stage=None,waiting_for=[],candidate_path=None,subtitle_path=None,
                published=False,report_path=None,validation={key:'unverified' for key in
                    ('actual_final_video_semantics','actual_final_video_sync','full_film_acceptance')}),ensure_ascii=False,indent=2))
        print('Interrupted', file=sys.stderr)
        return 130
    except (ConfigError, ValueError) as exc:
        if options is not None and options.command in ('run','resume') and options.json:
            print(json.dumps(dict(schema_version=1,run_dir=str(_lexical_cli_path(options.run_dir,invocation_cwd)) if options.command=='resume' else None,
                parent_run_dir=None,status='refused',active_stage=None,waiting_for=[],candidate_path=None,subtitle_path=None,
                published=False,report_path=None,error=str(exc),validation={key:'unverified' for key in
                    ('actual_final_video_semantics','actual_final_video_sync','full_film_acceptance')}),ensure_ascii=False,indent=2))
        print(f'Configuration/argument error: {exc}', file=sys.stderr)
        return 2
    except OSError as exc:
        if options is not None and options.command in ('run','resume') and options.json:
            print(json.dumps(dict(schema_version=1,run_dir=str(_lexical_cli_path(options.run_dir,invocation_cwd)) if options.command=='resume' else None,
                parent_run_dir=None,status='failed',active_stage=None,waiting_for=[],candidate_path=None,subtitle_path=None,
                published=False,report_path=None,error=str(exc),validation={key:'unverified' for key in
                    ('actual_final_video_semantics','actual_final_video_sync','full_film_acceptance')}),ensure_ascii=False,indent=2))
        print(f'Preflight I/O failure: {exc}', file=sys.stderr)
        return 1
