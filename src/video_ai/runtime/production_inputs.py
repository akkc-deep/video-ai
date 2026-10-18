"""Small frozen inputs and necessary local checks, without historical consumers."""
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import MappingProxyType
from uuid import uuid4

from ..config import ProjectConfig, load_config, load_voice_config, read_json
from ..jimeng_config import STRATEGY, active_models, active_workflows, override_image_model
from ..planning.segments import SegmentedScript, segment_text
from .environment import build_child_env
from .manifest import FileIdentity, hash_file, now, thaw, validate_run_dir
from .paths import PathPolicy, RuntimePaths, resolve_cli_path
from .preflight import PreflightCheck, PreflightReport, preflight
from .production_state import (ArtifactStamp, ProductionRefused, absolute_path, integer,
                               object_fields, run_path, timestamp, write_exclusive)
from .services import port_listening
from .workflows import validate_workflow

DEFAULT_CONFIG = Path('D:/VideoSi/projects/video-ai/config/production.json')
GIB = 1024**3
OPTION_FIELDS = ('schema_version', 'execution_mode', 'run_id', 'created_at', 'input_mode',
                 'input_source', 'script_path', 'config_snapshot', 'voice_snapshot', 'tts_yaml_path',
                 'workflow_snapshots', 'model_stamps', 'output_paths', 'cpu_planner', 'execution_policy')
POLICY_FIELDS = ('ollama_request_seconds', 'media_command_seconds', 'input_identities', 'model_roots')


@dataclass(frozen=True)
class FrozenInputs:
    config: ProjectConfig
    script: SegmentedScript
    options: dict


def validate_supported(config):
    for field, expected in dict(fps=16, final_width=1920, final_height=1080, transition='cut',
                                transition_seconds=0, burn_subtitles=True, music=None).items():
        actual = getattr(config.media, field)
        if actual != expected or field != 'transition_seconds' and type(actual) is not type(expected):
            raise ProductionRefused(f'media.{field}: automatic production requires {expected!r}')
    if config.media.profile.name not in ('fast', 'quality') or config.media.profile.native_fps != 16:
        raise ProductionRefused('media.profile: requires fast/quality native16')
    if config.voice.device != 'cpu' or config.voice.is_half is not False:
        raise ProductionRefused('voice.device/is_half: requires cpu and false')


def read_script(*, script=None, text=None, raw_bytes=None):
    if (script is None) == (text is None): raise ProductionRefused('provide exactly one of script or text')
    if text is not None and not isinstance(text, str): raise ProductionRefused('text must be a string')
    raw = raw_bytes if raw_bytes is not None else (text.encode('utf-8') if text is not None else resolve_cli_path(str(script), Path.cwd()).read_bytes())
    try: decoded = raw.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc: raise ProductionRefused('script must be strict UTF-8 or UTF-8 BOM') from exc
    spans = segment_text(decoded)
    if not any(span.kind == 'speech' for span in spans): raise ProductionRefused('script has no speakable original text')
    return raw, SegmentedScript(decoded, raw.startswith(b'\xef\xbb\xbf'), spans)


def _copy_small(source, destination):
    source = Path(source).resolve(strict=True)
    with source.open('rb') as file:
        before = os.fstat(file.fileno()); raw = file.read(); after = os.fstat(file.fileno())
    current = source.stat()
    def stable(stat): return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    if stable(before) != stable(after) or stable(current) != stable(after):
        raise ProductionRefused(f'input changed while freezing: {source}')
    _save_bytes(destination, raw)
    digest = hashlib.sha256(raw).hexdigest()
    return FileIdentity(str(source), len(raw), before.st_mtime_ns, digest, now()), hash_file(destination)


def _save_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as file:
        file.write(raw); file.flush(); os.fsync(file.fileno())


def _resolved(config):
    project = thaw(config); voice = project.pop('voice'); project.pop('raw'); voice.pop('raw')
    if config.production_strategy == 'legacy':
        project.pop('production_strategy', None); project.pop('image_generation', None)
    return project, voice


def _same_json(left, right):
    def canonical(value): return json.dumps(thaw(value), sort_keys=True, allow_nan=False, separators=(',', ':'))
    return canonical(left) == canonical(right)


def output_paths(config, run, output_path=None, *, check_existing=True):
    target = output_path if output_path is not None else config.output_root/(run.name+'.mp4')
    movie = PathPolicy().validate_write(resolve_cli_path(str(target), Path.cwd()), 'output')
    if movie.suffix.lower() != '.mp4': raise ProductionRefused('output must have .mp4 extension')
    targets = dict(movie=str(movie), subtitle=str(movie.with_suffix('.srt')), receipt=str(movie.with_suffix('.delivery.json')))
    for path in targets.values():
        path = PathPolicy().validate_write(path, 'output')
        if check_existing and (path.exists() or path.is_symlink()): raise ProductionRefused(f'output already exists: {path}')
    return targets


def freeze_inputs(config, run_dir, *, script=None, text=None, output_path=None, cpu_planner=None, raw_script_bytes=None, image_model=None):
    run = validate_run_dir(run_dir)
    validate_supported(config)
    image = override_image_model(config.image_generation, image_model)
    if cpu_planner is not None and type(cpu_planner) is not bool: raise ProductionRefused('cpu_planner must be bool or None')
    raw, parsed = read_script(script=script, text=text, raw_bytes=raw_script_bytes)
    targets = output_paths(config, run, output_path)
    paths = RuntimePaths.from_config(config); paths.validate()
    for path in config.tools.values(): paths.policy.validate_write(path, 'tool-env')
    for path in active_models(config).values(): paths.policy.validate_write(path, 'model')
    for field in ('gpt_weights', 'sovits_weights', 'bert_root', 'hubert_root'):
        paths.policy.validate_write(getattr(config.voice, field), 'model')
    directory = run_path(run, run/'production'); directory.mkdir(exist_ok=True)
    identities = {}
    script_path = run_path(run, directory/'script.txt'); _save_bytes(script_path, raw)
    identities['script'] = thaw(hash_file(script_path))
    config_id, config_copy = _copy_small(config.config_file, run_path(run, directory/'inputs/config.json'))
    voice_id, voice_copy = _copy_small(config.voice.config_file, run_path(run, directory/'inputs/voice.json'))
    # Parse the actual frozen bytes and require the caller's effective objects to match.
    voice = load_voice_config(config.voice.config_file, raw=read_json(Path(voice_copy.path)))
    canonical = load_config(config.config_file, raw=read_json(Path(config_copy.path)), voice=voice)
    if not _same_json(canonical, config): raise ProductionRefused('effective configuration differs from source raw/resolved configuration')
    identities.update(config=thaw(config_copy), voice=thaw(voice_copy))
    resolved, resolved_voice = _resolved(config)
    workflows = {}
    originals = active_workflows(config)
    originals.update(upscale_mapping=config.workflows['upscale'].with_suffix('.mapping.json'))
    if config.production_strategy != STRATEGY:
        originals['sdxl_mapping'] = config.workflows['sdxl'].with_suffix('.mapping.json')
    for role, source in originals.items():
        destination = run_path(run, directory/'workflows'/source.name)
        source_id, copied_id = _copy_small(source, destination)
        workflows[role] = dict(path=str(destination), source_identity=thaw(source_id))
        identities['workflow/'+role] = thaw(copied_id)
    yaml_source_id, yaml_copy = _copy_small(config.project_root/'config/tts-api.yaml', run_path(run, directory/'inputs/tts-api-source.yaml'))
    identities['tts_yaml_source'] = thaw(yaml_copy)
    reference_id, reference_copy = _copy_small(config.voice.reference_audio, run_path(run, directory/'inputs/reference.wav'))
    if reference_id.sha256 != config.voice.reference_sha256: raise ProductionRefused('voice.reference_sha256: reference audio mismatch')
    identities['reference'] = thaw(reference_copy)
    _, font_copy = _copy_small(config.media.font_file, run_path(run, directory/'inputs'/config.media.font_file.name))
    identities['font'] = thaw(font_copy)
    # JSON is valid YAML; the service receives its own mutable configuration in MAKE-02.
    yaml_path = run_path(run, directory/'inputs/tts-api.yaml')
    custom = dict(version='v2', device='cpu', is_half=False, t2s_weights_path=str(config.voice.gpt_weights),
                  vits_weights_path=str(config.voice.sovits_weights), bert_base_path=str(config.voice.bert_root),
                  cnhuhbert_base_path=str(config.voice.hubert_root))
    write_exclusive(yaml_path, dict(custom=custom, v2=custom))
    identities['tts_yaml'] = thaw(hash_file(yaml_path))
    models = {role: ArtifactStamp.read(path).to_dict() for role, path in active_models(config).items()}
    models.update({role: ArtifactStamp.read(getattr(config.voice, role)).to_dict() for role in ('gpt_weights', 'sovits_weights')})
    roots = {role: str(getattr(config.voice, role)) for role in ('bert_root', 'hubert_root')}
    for root in roots.values():
        if not Path(root).is_dir(): raise ProductionRefused(f'missing model directory: {root}')
    options = dict(schema_version=1, execution_mode='automatic', run_id=run.name, created_at=now(),
                   input_mode='script' if script is not None else 'text',
                   input_source=str(resolve_cli_path(str(script), Path.cwd())) if script is not None else None,
                   script_path=str(script_path),
                   config_snapshot=dict(source_path=str(config.config_file), source_identity=thaw(config_id), raw=thaw(config.raw), resolved=resolved),
                   voice_snapshot=dict(source_path=str(config.voice.config_file), source_identity=thaw(voice_id), raw=thaw(config.voice.raw), resolved=resolved_voice),
                   tts_yaml_path=str(yaml_path), workflow_snapshots=workflows, model_stamps=models, output_paths=targets,
                   cpu_planner=bool(cpu_planner), execution_policy=dict(
                       ollama_request_seconds=max(config.timeouts['ollama_request'], 1800) if cpu_planner else config.timeouts['ollama_request'],
                       media_command_seconds=300, input_identities=identities, model_roots=roots))
    if config.production_strategy == STRATEGY:
        options.update(schema_version=2, production_strategy=STRATEGY,
                       image_model_override=image_model, image_generation=thaw(image))
    write_exclusive(run_path(run, directory/'options.json'), options)
    return load_frozen_inputs(run)


def _verify_identity(data, run=None):
    from .manifest import _identity
    _identity(data)
    path = absolute_path(data['path'])
    if run is not None: run_path(run, path)
    fresh = hash_file(path)
    if (fresh.bytes, fresh.sha256) != (data['bytes'], data['sha256']):
        raise ProductionRefused(f'frozen input changed: {path}')


def load_frozen_inputs(run_dir, *, config=None, output_path=None, cpu_planner=None, image_model=None):
    run = validate_run_dir(run_dir); options = read_json(run_path(run, run/'production/options.json'))
    modern = type(options.get('schema_version')) is int and options['schema_version'] == 2
    fields = OPTION_FIELDS + ('production_strategy', 'image_model_override', 'image_generation') if modern else OPTION_FIELDS
    object_fields(options, fields, 'production options')
    if type(options['schema_version']) is not int or options['schema_version'] not in (1, 2) or options['execution_mode'] != 'automatic' or options['run_id'] != run.name:
        raise ProductionRefused('invalid automatic options identity')
    if modern and options['production_strategy'] != STRATEGY: raise ProductionRefused('invalid frozen strategy')
    timestamp(options['created_at'])
    if options['input_mode'] not in ('script', 'text') or type(options['cpu_planner']) is not bool:
        raise ProductionRefused('invalid input mode/cpu_planner')
    if options['input_mode'] == 'script': absolute_path(options['input_source'])
    elif options['input_source'] is not None: raise ProductionRefused('text mode source must be null')
    script_path = run_path(run, options['script_path'])
    if script_path != run/'production/script.txt': raise ProductionRefused('frozen script path differs')
    policy = options['execution_policy']; object_fields(policy, POLICY_FIELDS, 'execution policy')
    if type(policy['media_command_seconds']) is not int or policy['media_command_seconds'] != 300:
        raise ProductionRefused('media command deadline must be 300')
    records = policy['input_identities']
    roles = ('wan', 'wan_mapping', 'upscale', 'upscale_mapping') if modern else ('sdxl', 'wan', 'wan_mapping', 'upscale', 'sdxl_mapping', 'upscale_mapping')
    required = {'script', 'config', 'voice', 'tts_yaml_source', 'tts_yaml', 'reference', 'font'} | {'workflow/'+role for role in roles}
    object_fields(records, required, 'frozen input identities')
    for record in records.values(): _verify_identity(record, run)
    if records['script']['path'] != str(script_path): raise ProductionRefused('script identity path differs')
    for label in ('config', 'voice'):
        snap = options[label+'_snapshot']
        object_fields(snap, ('source_path', 'source_identity', 'raw', 'resolved'), label+' snapshot')
        from .manifest import _identity
        _identity(snap['source_identity'])
        if snap['source_identity']['path'] != snap['source_path']: raise ProductionRefused('snapshot source path differs')
        if not _same_json(read_json(Path(records[label]['path'])), snap['raw']): raise ProductionRefused('snapshot raw differs from frozen copy')
    voice = load_voice_config(absolute_path(options['voice_snapshot']['source_path']), raw=options['voice_snapshot']['raw'])
    frozen = load_config(absolute_path(options['config_snapshot']['source_path']), raw=options['config_snapshot']['raw'], voice=voice)
    if not _same_json(_resolved(frozen), (options['config_snapshot']['resolved'], options['voice_snapshot']['resolved'])):
        raise ProductionRefused('frozen raw/resolved configuration differs')
    validate_supported(frozen)
    if modern != (frozen.production_strategy == STRATEGY): raise ProductionRefused('strategy/schema mismatch')
    expected_timeout = max(frozen.timeouts['ollama_request'], 1800) if options['cpu_planner'] else frozen.timeouts['ollama_request']
    if type(policy['ollama_request_seconds']) not in (int, float) or policy['ollama_request_seconds'] != expected_timeout:
        raise ProductionRefused('frozen Ollama request deadline differs')
    object_fields(policy['model_roots'], ('bert_root', 'hubert_root'), 'model roots')
    for role, path in policy['model_roots'].items():
        if path != str(getattr(voice, role)) or not Path(path).is_dir(): raise ProductionRefused('model root changed')
    expected_models = dict(active_models(frozen), gpt_weights=voice.gpt_weights, sovits_weights=voice.sovits_weights)
    object_fields(options['model_stamps'], expected_models.keys(), 'model stamps')
    for role, record in options['model_stamps'].items():
        stamp = ArtifactStamp.from_dict(record)
        if stamp.path != str(expected_models[role]): raise ProductionRefused('model stamp path differs')
        stamp.verify()
    workflows = options['workflow_snapshots']
    object_fields(workflows, roles, 'workflow snapshots')
    for role, record in workflows.items():
        object_fields(record, ('path', 'source_identity'), 'workflow snapshot')
        run_path(run, record['path']); _identity(record['source_identity'])
        if record['path'] != records['workflow/'+role]['path']: raise ProductionRefused('workflow copy path differs')
    for role in (('wan', 'upscale') if modern else ('sdxl', 'wan', 'upscale')):
        mapping_role = 'wan_mapping' if role == 'wan' else role+'_mapping'
        validate_workflow(Path(workflows[role]['path']), Path(workflows[mapping_role]['path']), frozen.models)
    if options['tts_yaml_path'] != records['tts_yaml']['path']: raise ProductionRefused('TTS YAML path differs')
    if output_paths(frozen, run, options['output_paths'].get('movie'), check_existing=False) != options['output_paths']:
        raise ProductionRefused('output paths differ')
    if config is not None:
        config = config if isinstance(config, ProjectConfig) else load_config(resolve_cli_path(str(config), Path.cwd()))
        if not _same_json(config.raw, options['config_snapshot']['raw']) or not _same_json(_resolved(config), _resolved(frozen)) or not _same_json(config.voice.raw, options['voice_snapshot']['raw']):
            raise ProductionRefused('explicit configuration differs from frozen configuration')
    if output_path is not None and output_paths(frozen, run, output_path, check_existing=False) != options['output_paths']:
        raise ProductionRefused('explicit output differs from frozen target')
    if cpu_planner is not None and (type(cpu_planner) is not bool or cpu_planner != options['cpu_planner']):
        raise ProductionRefused('cpu_planner differs from frozen setting')
    image = override_image_model(frozen.image_generation, options['image_model_override'] if modern else None)
    if modern and not _same_json(thaw(image), options['image_generation']): raise ProductionRefused('frozen image model configuration differs')
    if image_model is not None and (image is None or image_model != image.req_key):
        raise ProductionRefused('image model differs from frozen model; create a new run')
    effective = replace(frozen, workflows=MappingProxyType({role: Path(workflows[role]['path']) for role in active_workflows(frozen)}),
                        image_generation=image,
                        voice=replace(voice, reference_audio=Path(records['reference']['path'])),
                        media=replace(frozen.media, font_file=Path(records['font']['path'])))
    return FrozenInputs(effective, SegmentedScript.read(script_path), options)


def check_stage_space(config, *, frames=0, audio_bytes=0, encoded_bytes=0, disk_usage=shutil.disk_usage):
    for name, value in dict(frames=frames, audio_bytes=audio_bytes, encoded_bytes=encoded_bytes).items(): integer(value, name)
    profile = config.media.profile
    required = frames*(profile.width*profile.height*4 + 1920*1080*4) + audio_bytes + encoded_bytes + GIB
    usage = disk_usage(config.runtime_root)
    if usage.free < required: raise OSError(f'D: insufficient space: free={usage.free}, required={required}')
    return dict(free_bytes=usage.free, required_bytes=required, frames=frames)


def production_preflight(config, run_dir, *, runner=subprocess.run, port_probe=port_listening, disk_usage=shutil.disk_usage):
    run = validate_run_dir(run_dir); checks = []
    validate_supported(config)
    from .production_visual_templates import validate_production_model_paths
    try:
        validate_production_model_paths(config)
        checks.append(PreflightCheck('production.comfy_model_paths',True,'configured models match actual Comfy model root'))
    except ProductionRefused as exc:
        return PreflightReport((PreflightCheck('production.comfy_model_paths',False,str(exc)),))
    for name, url in config.services.items():
        try:
            # Windows may take about two seconds to return WSAECONNREFUSED.
            if port_probe(url, 3): raise ProductionRefused(f'external service listening at {url}; cannot claim ownership')
            checks.append(PreflightCheck('ports.'+name, True, f'available: {url}'))
        except (OSError, ValueError, RuntimeError) as exc: checks.append(PreflightCheck('ports.'+name, False, str(exc)))
    if not all(c.passed for c in checks): return PreflightReport(tuple(checks))
    core = preflight(config, runner=runner, disk_usage=disk_usage, automatic=True,
                     log_dir=run_path(run, run/f'logs/production/preflight/{uuid4().hex}'))
    checks.extend(core.checks)
    try:
        capacity = check_stage_space(config, disk_usage=disk_usage)
        checks.append(PreflightCheck('production.space', True, json.dumps(capacity)))
    except OSError as exc: checks.append(PreflightCheck('production.space', False, str(exc)))
    # Verify the default subtitle face against the actual file and Windows GDI.
    try:
        from ..media.font_metrics import PrivateFont
        from ..planning.composition import CompositionSettings
        settings = CompositionSettings()
        with PrivateFont(config.media.font_file, settings.font_name, settings.font_size) as font:
            font.measure('湖水白鸟')
        checks.append(PreflightCheck('production.font', True, f'private font usable: {config.media.font_file}'))
    except (OSError, ValueError) as exc: checks.append(PreflightCheck('production.font', False, str(exc)))
    if core.log_dir is not None:
        source = run_path(run, run/'production/inputs/tts-api-source.yaml')
        if not source.exists(): source = config.project_root/'config/tts-api.yaml'
        stdout_path = run_path(run, core.log_dir/'tts-yaml.stdout.json')
        stderr_path = run_path(run, core.log_dir/'tts-yaml.stderr.txt')
        args = [str(config.tools['tts_python']), '-B', '-c',
                'import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1],encoding="utf-8-sig"))))', str(source)]
        command = dict(args=args, cwd=str(core.log_dir), timeout_seconds=30, stdout=str(stdout_path),
                       stderr=str(stderr_path), returncode=None, timed_out=False, error=None)
        try:
            with stdout_path.open('x', encoding='utf-8') as stdout, stderr_path.open('x', encoding='utf-8') as stderr:
                result = runner(args, cwd=str(core.log_dir), env=build_child_env(RuntimePaths.from_config(config)),
                                timeout=30, stdout=stdout, stderr=stderr, text=True, encoding='utf-8', errors='replace')
            command['returncode'] = result.returncode
            if result.returncode != 0: raise OSError(f'TTS YAML parser exit {result.returncode}; stderr: {stderr_path}')
            installed = read_json(stdout_path)
            custom = installed.get('custom')
            if not isinstance(custom, dict): raise ProductionRefused('tts_yaml.custom: missing installed voice route')
            for name, expected in dict(version='v2', device='cpu', is_half=False).items():
                if type(custom.get(name)) is not type(expected) or custom[name] != expected:
                    raise ProductionRefused(f'tts_yaml.custom.{name}: automatic production requires {expected!r}')
            checks.append(PreflightCheck('production.tts_yaml', True, f'installed CPU/v2/non-half route: {stdout_path}'))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            command['error'] = str(exc); command['timed_out'] = isinstance(exc, subprocess.TimeoutExpired)
            checks.append(PreflightCheck('production.tts_yaml', False, str(exc)))
        write_exclusive(run_path(run, core.log_dir/'tts-yaml-command.json'), command)
    report = PreflightReport(tuple(checks), core.log_dir)
    if core.log_dir is not None: write_exclusive(run_path(run, core.log_dir/'production-report.json'), report.as_dict())
    return report
