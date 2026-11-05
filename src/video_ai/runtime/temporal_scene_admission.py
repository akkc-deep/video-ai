"""Pinned native qualification and independent production-wrapper admission."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from ..planning.production_scenes import canonical_digest
from ..planning.scene_temporal import CLOCK_POLICY, PROTOCOL
from ._whole_scene_admission import EvidenceReader, content, require
from .manifest import thaw
from .production_state import ProductionRefused, json_bytes, object_fields
from .verification import verified_read, validation_memo

QUALIFICATION_ROOT = Path('D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification/allocator-async-candidate-v1')
QUALIFICATION_SHA256 = 'afeee7f892bb36329a6d7afd4ffa297931ae3683c3149847b4d6602dbb40c947'
MODEL_ROOT = Path('D:/VideoSi/models/vco08-longcat/03b55529b1d1d4045f5fbe14d65c8c6e8116b278')
MODEL_REVISION = '03b55529b1d1d4045f5fbe14d65c8c6e8116b278'
CODE_REVISION = '6b3f4b8582a8bc3f20f795735f5383716c4ba794'
ALGORITHM = 'temporal_native_admission_v1'
EVIDENCE_FIELDS = ('schema_version algorithm qualification_root observed_visual_scope model_manifest runtime_bundle '
                   'native_python package_versions production_worker production_resource artifacts assessment').split()
GIB = 1024**3
NATIVE_PYTHON = Path('D:/VideoSi/tools/ComfyUI_windows_portable/python_embeded/python.exe')
BUNDLE_TOOLS_ROOT = Path('D:/VideoSi/tools/video-ai-temporal-native')


def _refused(function):
    from functools import wraps
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except ProductionRefused: raise
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProductionRefused('native temporal evidence refused: '+str(exc)) from exc
    return checked


def _source_path(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and '..' not in path.parts and path.suffix == '.py', 'relative core Python source required')
    target = Path(root)/path
    require(target.is_relative_to(Path(root)), 'core source escapes root')
    return target


@_refused
def load_temporal_qualification(path, *, reader=None) -> dict:
    """Read historical real qualification, never start a model or encode text."""
    path = Path(path)
    require(path == QUALIFICATION_ROOT/'native16-qualification-assessment.json', 'unrecognized qualification root')
    io = EvidenceReader(reader)
    root = io.capture(path)
    require(root['sha256'] == QUALIFICATION_SHA256, 'qualification root SHA differs')
    value = io.json(path)
    fields = ('schema_version algorithm recorded_at_utc qualification_root case software model_manifest download_receipt '
              'text_cache text_binding resource_admission layout final_admission windows chain_result chain_integrity '
              'dynamic_review viewing_movie observed_visual_scope assessment new_downloads new_text_encoding_calls model_weights_copied').split()
    object_fields(value, fields, 'temporal qualification')
    require(type(value['schema_version']) is int and value['schema_version'] == 1
            and value['algorithm'] == 'longcat_native16_qualification_v1', 'qualification schema/algorithm')
    require(Path(value['qualification_root']) == QUALIFICATION_ROOT, 'qualification directory differs')
    require(value['assessment'] == dict(technical='passed', actual_static='screened', complete_dynamic='accepted',
                                      production_wrapper_resources='unverified', production_enabled=False), 'qualification assessment')
    require(all(type(value[key]) is int and value[key] == 0 for key in
                ('new_downloads', 'new_text_encoding_calls', 'model_weights_copied')), 'qualification reuse provenance')
    case = io.linked(value['case'])
    software = io.linked(value['software'])
    require(case['model_revision'] == MODEL_REVISION and case['code_revision'] == CODE_REVISION, 'pinned model/code revision')
    require(software['case_sha256'] == value['case']['sha256'] and len(software['files']) == 27, 'qualification software/case')
    require((case['width'], case['height'], case['fps'], case['num_frames'], case['num_cond_frames']) == (768, 432, 16, 93, 13), 'qualification shape')
    require(case['append_frames'] == [93, 80, 80, 67] and case['cumulative_frames'] == [93, 173, 253, 320], 'qualification mapping')
    require(case['allocator_backend'] == 'cudaMallocAsync' and case['output_clock_policy'] == CLOCK_POLICY, 'qualification backend/clock')
    require(case['num_inference_steps'] == 50 and case['guidance_scale'] == 4.0, 'qualification sampling')
    for row in software['files']:
        io.capture(_source_path(QUALIFICATION_ROOT, row['path']),
                   dict(path=str(QUALIFICATION_ROOT/row['path']), bytes=row['bytes'], sha256=row['sha256']))
    io.capture(value['model_manifest']['path'], value['model_manifest'])
    require(value['model_manifest']['sha256'] == case['model_manifest_sha256'], 'model manifest binding')
    download = io.linked(value['download_receipt'])
    require(download['complete'] is True and download['manifest_sha256'] == value['model_manifest']['sha256'], 'fixed completed download')
    io.capture(value['text_cache']['path'], value['text_cache'])
    io.linked(value['text_binding'])
    require(value['text_cache']['sha256'] == '53c254856bcb45c0fd1cb8081bb5391538a9c0b672687e1605c1ef13404e77c5', 'qualification cache identity')
    resource = io.linked(value['resource_admission'])
    require(resource['complete'] is True and resource['allocator_backend'] == 'cudaMallocAsync'
            and resource['completed_shapes'] == ['first', 'clean_history', 'continuation', 'vae_encode_13', 'vae_decode_93'], 'qualification five-stage resources')
    require(resource['kv_bytes'] == 4076863488 and resource['prepared_latent_shape'] == [1, 16, 24, 54, 96], 'qualification actual resource shape')
    io.linked(value['layout'])
    final = io.linked(value['final_admission'])
    require(final['complete'] is True and final['case_sha256'] == value['case']['sha256']
            and final['software_sha256'] == value['software']['sha256'], 'qualification final admission')
    require(len(value['windows']) == 4, 'all four qualification windows required')
    from ..planning.scene_temporal import derive_temporal_clips
    expected_clips = derive_temporal_clips(dict(total_frames=320, scenes=[dict(scene_id='scene_0001', start_frame=0, end_frame=320)]), dict(total_frames=320))
    previous_result = previous_frames = None
    for stage, (row, clip) in enumerate(zip(value['windows'], expected_clips), 1):
        require(row['window'] == stage, 'ordered qualification windows')
        folder = QUALIFICATION_ROOT/'trial-001'/f'window-{stage:03d}'
        require(Path(row['result']['path']) == folder/'result.json', 'qualification window source')
        result = io.linked(row['result'])
        integrity = io.linked(row['integrity'])
        require(result['technical_complete'] is True and result['native_diffusion_attempts_recorded'] == 1, 'actual once-only window')
        require(result['case_sha256'] == value['case']['sha256'] and result['software_sha256'] == value['software']['sha256'], 'window source identity')
        require(integrity['result_sha256'] == row['result']['sha256'] and integrity['all_artifacts_full_sha_verified'] is True, 'window full integrity')
        require(integrity['actual_kv_layers'] == (48 if stage > 1 else 0)
                and integrity['actual_kv_bytes'] == (4076863488 if stage > 1 else 0), 'actual qualification KV')
        require(result['mapping']['append_source_range'] == [clip['retained_source_start'], clip['retained_source_end']]
                and result['mapping']['chain_range'] == [clip['start_frame'], clip['end_frame']], 'window retained contribution')
        intent = io.json(folder/'intent.json')
        require(intent['parent_result_sha256'] == previous_result and intent['parent_frames_sha256'] == previous_frames, 'real parent chain')
        require(intent['history_pixels'] == (1 if stage == 1 else 13) and intent['history_latents'] == (1 if stage == 1 else 4), 'real history protocol')
        sample = io.json(folder/'sample-complete.json')
        require(io.capture(folder/'intent.json')['sha256'] == result['intent_sha256'] == sample['intent_sha256']
                and io.capture(folder/'sample-complete.json')['sha256'] == result['sample_complete_sha256']
                and sample['native_diffusion_completed'] is True, 'committed sample binding')
        for item in result['artifacts'].values(): io.capture(item['path'], item)
        require(result['technical']['raw']['pixel_exact'] is True and result['technical']['raw']['fps'] == '16/1', 'native raw pixels/clock')
        screening = io.linked(row['screening'])
        io.linked(row['static_observation'])
        require(screening['parent_result_sha256'] == row['result']['sha256']
                and screening['allow_next_window'] is (stage < 4), 'actual static screening')
        if stage > 1:
            banks = list(folder.glob('kv-workspace-*'))
            require(len(banks) == 1 and integrity['kv_full_sha_verified'] is True, 'real KV bank')
            total = 0
            for layer in range(48):
                pair = io.json(banks[0]/f'layer-{layer:03d}.json')
                require(isinstance(pair, list) and len(pair) == 2, 'KV key/value pair')
                for kind, item in zip(('k', 'v'), pair):
                    require(Path(item['path']) == banks[0]/f'layer-{layer:03d}-{kind}.bf16'
                            and item['dtype'] == 'BF16' and item['shape'] == [1, 32, 5184, 128], 'KV actual shape/source')
                    io.capture(item['path'], {key: item[key] for key in ('path', 'bytes', 'sha256')})
                    total += item['bytes']
            require(total == 4076863488, 'KV exact byte count')
        previous_result, previous_frames = row['result']['sha256'], result['artifacts']['frames']['sha256']
    chain = io.linked(value['chain_result'])
    integrity = io.linked(value['chain_integrity'])
    require(chain['frames'] == 320 and chain['fps'] == '16/1' and chain['boundary_frames'] == [93, 173, 253], 'complete qualification chain')
    require(integrity['result_sha256'] == value['chain_result']['sha256'] and integrity['retained_pixels_exact'] is True
            and integrity['history_output_once'] is True, 'qualification chain integrity')
    for item in chain['artifacts'].values(): io.capture(item['path'], item)
    review = io.linked(value['dynamic_review'])
    require(review['accepted'] is True and review['review_method'] == 'human_video'
            and review['playback_frame_range'] == [0, 320]
            and review['result_sha256'] == value['chain_result']['sha256']
            and review['viewing_movie_sha256'] == value['viewing_movie']['sha256'], 'new complete human review')
    scope = value['observed_visual_scope']
    require((scope['cases'], scope['windows'], scope['frames'], scope['width'], scope['height'], scope['fps']) == (1, 4, 320, 768, 432, '16/1')
            and scope['protocol'] == PROTOCOL and scope['clock_policy'] == CLOCK_POLICY, 'honest observed scope')
    return dict(root=root, qualification_root=QUALIFICATION_ROOT, value=value, case=case, software=software,
                observed_visual_scope=scope, guard=io, artifacts=list(io.artifacts.values()))


def _write_exact(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, 'existing native deployment bytes differ')
        return
    temporary = path.with_name(path.name+'.'+uuid4().hex+'.pending')
    with temporary.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(not path.exists(), 'native deployment appeared during commit')
    os.rename(temporary, path)


@_refused
def install_temporal_bundle(qualification, *, tools_root) -> dict:
    qualified = load_temporal_qualification(qualification)
    source = Path(qualified['qualification_root'])
    core, copied = [], {}
    for row in qualified['software']['files']:
        path = _source_path(source, row['path'])
        raw = path.read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'core source changed')
        copied[row['path']] = raw
        core.append(dict(path=row['path'], bytes=len(raw), sha256=row['sha256']))
    auxiliary = []
    for name, path in (('model-manifest.json', source/'model-manifest.json'),
                       ('download-result.json', source/'download-result.json'), ('LICENSE', MODEL_ROOT/'LICENSE')):
        raw = path.read_bytes(); copied[name] = raw
        auxiliary.append(dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    manifest = dict(schema_version=1, algorithm='longcat_native16_bundle_v1', qualification=qualified['root'],
        code_revision=qualified['case']['code_revision'], core_files=core, auxiliary_files=auxiliary,
        package_versions=qualified['software']['versions'])
    root = Path(tools_root)/canonical_digest(manifest)
    for relative, raw in copied.items(): _write_exact(root/relative, raw)
    _write_exact(root/'bundle.json', json_bytes(manifest))
    io = EvidenceReader()
    identity = io.capture(root/'bundle.json')
    return dict(root=str(root), manifest=identity, core_file_count=len(core), copied_model_weights=0,
                new_downloads=0, new_text_encoding_calls=0)


def _current_worker_sources():
    package = Path(__file__).resolve().parent.parent
    return [package/'runtime'/name for name in ('temporal_native_worker.py', 'temporal_native_process.py',
            'temporal_scene_admission.py','temporal_scene_records.py','temporal_scene_observations.py',
            '_temporal_media_check_coverage.py','temporal_scene_origins.py')] + [package/'planning/scene_temporal.py']


def _production_parts(value, qualified, io):
    require(Path(value['native_python']['path']) == NATIVE_PYTHON, 'current native Python path differs')
    io.capture(value['native_python']['path'], value['native_python'])
    bundle = io.linked(value['runtime_bundle'])
    object_fields(bundle, ('schema_version', 'algorithm', 'qualification', 'code_revision', 'core_files',
                          'auxiliary_files', 'package_versions'), 'native runtime bundle')
    require(type(bundle['schema_version']) is int and bundle['schema_version'] == 1
            and bundle['algorithm'] == 'longcat_native16_bundle_v1', 'native bundle schema')
    require(bundle['qualification'] == qualified['root'] and bundle['code_revision'] == CODE_REVISION
            and bundle['package_versions'] == qualified['software']['versions'], 'bundle qualification/runtime source')
    root = Path(value['runtime_bundle']['path']).parent
    require(root.parent == BUNDLE_TOOLS_ROOT and root.name == canonical_digest(bundle), 'versioned native bundle path')
    expected_core = [{key: row[key] for key in ('path', 'bytes', 'sha256')} for row in qualified['software']['files']]
    require(bundle['core_files'] == expected_core and len(expected_core) == 27, 'bundle numeric core differs')
    for item in bundle['core_files']:
        io.capture(_source_path(root, item['path']), dict(item, path=str(root/item['path'])))
    auxiliary = bundle['auxiliary_files']
    require(isinstance(auxiliary, list) and [item['path'] for item in auxiliary] == ['model-manifest.json', 'download-result.json', 'LICENSE'], 'bundle auxiliary inventory')
    for item in auxiliary: io.capture(root/item['path'], dict(item, path=str(root/item['path'])))
    require(auxiliary[0]['sha256'] == qualified['value']['model_manifest']['sha256']
            and auxiliary[1]['sha256'] == qualified['value']['download_receipt']['sha256'], 'bundle model/download provenance')
    sources = [io.capture(path) for path in _current_worker_sources()]
    require(sources and content(value['production_worker']) == sources[0], 'current production worker differs')
    resource = io.linked(value['production_resource'])
    require(resource.get('complete') is True and resource.get('algorithm') == 'temporal_native_resource_v1', 'independent production resources missing')
    require(resource.get('production_worker') == value['production_worker'] and resource.get('production_sources') == sources
            and resource.get('runtime_bundle') == value['runtime_bundle'], 'production resource/source binding')
    require(resource.get('model_manifest_sha256') == value['model_manifest']['sha256']
            and resource.get('package_versions') == value['package_versions'], 'production resource/model/runtime binding')
    require(resource.get('completed_shapes') == ['first', 'clean_history', 'continuation', 'vae_encode_13', 'vae_decode_93']
            and resource.get('allocator_backend') == 'cudaMallocAsync' and resource.get('output_clock_policy') == CLOCK_POLICY, 'production resource protocol')
    require(resource.get('native_diffusion_calls') == 0 and resource.get('new_text_encoding_calls') == 0
            and 'time_limit_seconds' in resource and resource['time_limit_seconds'] is None
            and 'max_gpu_allocated_bytes' in resource and resource['max_gpu_allocated_bytes'] is None, 'production preflight boundary')
    for key, shape in dict(prepared_latent_shape=[1, 16, 24, 54, 96], clean_kv_shape=[1, 32, 5184, 128],
                           vae_encode_shape=[1, 16, 4, 54, 96], vae_decode_frames_shape=[93, 432, 768, 3]).items():
        require(resource.get(key) == shape and all(type(item) is int for item in resource[key]), 'production actual '+key)
    require(resource.get('kv_bytes') == 4076863488 and resource.get('deployed_output_fps') == 16
            and resource.get('worker_import_footprint_included') is True, 'production actual cache/clock/footprint')
    for field, limits in (
        ('startup_available', dict(physical=8*GIB, commit=10*GIB, gpu=18*GIB, disk=32*GIB)),
        ('minima', dict(physical=2*GIB, commit=4*GIB, gpu=GIB, disk=32*GIB))):
        observed = resource.get(field)
        object_fields(observed, limits, 'native measured '+field)
        require(all(type(observed[key]) is int and observed[key] >= limit for key, limit in limits.items()), 'native actual free-capacity reserves')


@_refused
def load_temporal_evidence(path, *, reader=None) -> dict:
    io = EvidenceReader(reader)
    value = io.json(path)
    object_fields(value, EVIDENCE_FIELDS, 'native admission')
    require(type(value['schema_version']) is int and value['schema_version'] == 1
            and value['algorithm'] == ALGORITHM, 'native admission schema/algorithm')
    require(value['assessment'] == dict(qualification='accepted', production_resource='passed', ready=True), 'native production admission not ready')
    qualification = load_temporal_qualification(content(value['qualification_root'])['path'], reader=reader)
    require(content(value['qualification_root']) == qualification['root'], 'qualification source changed')
    require(value['observed_visual_scope'] == qualification['observed_visual_scope'], 'observation scope cannot be expanded')
    require(content(value['model_manifest']) == content(qualification['value']['model_manifest']), 'native model differs')
    require(value['package_versions'] == qualification['software']['versions'], 'native dependency versions differ')
    _production_parts(value, qualification, io)
    expected = {item['path']: item for item in qualification['artifacts']}
    expected.update({key: item for key, item in io.artifacts.items() if key != str(Path(path))})
    require(value['artifacts'] == [expected[key] for key in sorted(expected)], 'native evidence closure differs')
    io.guards.append(qualification['guard'])
    return dict(root=io.capture(path), raw=Path(path).read_bytes(), value=value, qualification=qualification,
                artifacts=[expected[key] for key in sorted(expected)], guard=io)


@_refused
def finalize_temporal_evidence(qualification, runtime, production_preflight, *, target) -> dict:
    require(production_preflight is not None, 'production resource preflight required before ready')
    # Final assembly is implemented with the production worker's actual resource
    # producer. No caller may convert installation alone into ready admission.
    require(isinstance(runtime, dict) and {'runtime_bundle', 'native_python', 'package_versions', 'production_worker'} <= set(runtime), 'complete production runtime required')
    qualified = load_temporal_qualification(qualification)
    io = EvidenceReader()
    preflight = io.capture(production_preflight)
    record = dict(schema_version=1, algorithm=ALGORITHM, qualification_root=qualified['root'],
        observed_visual_scope=deepcopy(qualified['observed_visual_scope']), model_manifest=content(qualified['value']['model_manifest']),
        **{key: deepcopy(runtime[key]) for key in ('runtime_bundle', 'native_python', 'package_versions', 'production_worker')},
        production_resource=preflight, artifacts=[], assessment=dict(qualification='accepted', production_resource='passed', ready=True))
    artifacts = {item['path']: item for item in qualified['artifacts']}
    _production_parts(record, qualified, io)
    artifacts.update(io.artifacts)
    record['artifacts'] = [artifacts[key] for key in sorted(artifacts)]
    temporary = Path(target).with_name(Path(target).name+'.'+uuid4().hex+'.pending')
    _write_exact(temporary, json_bytes(record))
    checked = load_temporal_evidence(temporary)
    _write_exact(target, checked['raw'])
    return load_temporal_evidence(target)


def _settings(config):
    from ..planning.scene_video_prompts import parse_scene_rendering
    raw = getattr(config, 'raw', {})
    return parse_scene_rendering(raw['scene_rendering']) if 'scene_rendering' in raw else {}


@_refused
def freeze_temporal_evidence(config, run, identities, *, save):
    settings = _settings(config)
    if settings.get('mode') != 'temporal_extension_v1': return
    from .manifest import hash_file
    from .production_state import run_path
    evidence = load_temporal_evidence(settings['temporal_evidence'])
    run = Path(run)
    folder = run_path(run, run/'production/scene-rendering')
    path = folder/'temporal-evidence.json'
    save(path, evidence['raw'])
    io = EvidenceReader()
    root = io.capture(path)
    closure = dict(schema_version=1, algorithm=ALGORITHM, root=root, artifacts=evidence['artifacts'])
    closure_path = folder/'temporal-evidence-closure.json'
    save(closure_path, json_bytes(closure))
    runtime = evidence['value']['runtime_bundle']
    io.capture(runtime['path'], runtime)
    runtime_path = folder/'temporal-runtime-bundle.json'
    save(runtime_path, io.raw(runtime['path']))
    for role, target in (('temporal_evidence', path), ('temporal_evidence_closure', closure_path),
                         ('temporal_runtime_bundle', runtime_path)):
        identities[role] = thaw(hash_file(target))
    evidence['guard'].verify()


def _cached_temporal_contract(evidence):
    from ._scene_media_check_coverage import _reader_contract
    return canonical_digest(dict(root=evidence['root'],value=evidence['value'],artifacts=evidence['artifacts'],
        raw_sha256=hashlib.sha256(evidence['raw']).hexdigest(),guard=_reader_contract(evidence['guard'])))


@_refused
@verified_read
def verify_temporal_frozen(frozen, *, reader=None) -> dict:
    from .production_state import run_path
    records = frozen.options['execution_policy']['input_identities']
    roles = {'temporal_evidence', 'temporal_evidence_closure', 'temporal_runtime_bundle'}
    if _settings(frozen.config).get('mode') != 'temporal_extension_v1':
        require(not roles.intersection(records), 'orphan native admission roles')
        return None
    require(roles <= set(records), 'native frozen admission roles missing')
    cache=validation_memo('temporal_native_admission') if reader is None else None
    key=canonical_digest(dict(options=thaw(frozen.options),raw=thaw(frozen.config.raw))) if cache is not None else None
    if cache is not None and key in cache:
        evidence,contract=cache[key]
        require(_cached_temporal_contract(evidence)==contract,'cached native admission contract changed')
        evidence['guard'].verify()
        return evidence
    run = Path(frozen.options['script_path']).parent.parent
    io = EvidenceReader(reader)
    for role, name in (('temporal_evidence', 'temporal-evidence.json'),
                       ('temporal_evidence_closure', 'temporal-evidence-closure.json'),
                       ('temporal_runtime_bundle', 'temporal-runtime-bundle.json')):
        expected = run_path(run, run/'production/scene-rendering'/name)
        require(Path(records[role]['path']) == expected, 'native frozen evidence path differs')
        io.capture(expected, {key: records[role][key] for key in ('path', 'bytes', 'sha256')})
    closure = io.json(records['temporal_evidence_closure']['path'])
    object_fields(closure, ('schema_version', 'algorithm', 'root', 'artifacts'), 'native frozen closure')
    require(type(closure['schema_version']) is int and closure['schema_version'] == 1
            and closure['algorithm'] == ALGORITHM, 'native closure schema/algorithm')
    root = io.capture(records['temporal_evidence']['path'])
    require(closure['root'] == root, 'native frozen root differs')
    evidence = load_temporal_evidence(root['path'], reader=reader)
    require(closure['artifacts'] == evidence['artifacts'], 'native frozen external closure differs')
    runtime = evidence['value']['runtime_bundle']
    require(records['temporal_runtime_bundle']['sha256'] == runtime['sha256']
            and records['temporal_runtime_bundle']['bytes'] == runtime['bytes'], 'native frozen runtime differs')
    evidence['guard'].guards.append(io) if isinstance(evidence['guard'], EvidenceReader) else None
    if cache is not None:
        from ._scene_media_check_coverage import _Unsupported
        try:contract=_cached_temporal_contract(evidence)
        except _Unsupported:pass  # Foreign/custom readers keep the full original path.
        else:cache[key]=(evidence,contract)
    return evidence
