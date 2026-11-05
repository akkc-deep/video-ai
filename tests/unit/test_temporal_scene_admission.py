"""Native qualification, deployment bundle and production admission are separate."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize('value', [{}, {'schema_version': True}, {'schema_version': 2},
    {'schema_version': 1, 'algorithm': 'whole_scene_v1'},
    {'schema_version': 1, 'algorithm': 'temporal_native_admission_v1', 'assessment': {'ready': False}}])
def test_incomplete_or_foreign_evidence_never_admits(value, tmp_path):
    from video_ai.runtime.temporal_scene_admission import load_temporal_evidence
    from video_ai.runtime.production_state import ProductionRefused
    path = tmp_path/'evidence.json'
    put(path, value)
    with pytest.raises(ProductionRefused): load_temporal_evidence(path)


def test_missing_evidence_and_missing_production_resource_refuse_without_output(tmp_path):
    from video_ai.runtime.temporal_scene_admission import load_temporal_evidence, finalize_temporal_evidence
    from video_ai.runtime.production_state import ProductionRefused
    with pytest.raises(ProductionRefused): load_temporal_evidence(tmp_path/'missing.json')
    output = tmp_path/'ready.json'
    with pytest.raises(ProductionRefused):
        finalize_temporal_evidence(tmp_path/'qualification.json', {}, None, target=output)
    assert not output.exists()


def tiny_qualification(tmp_path, monkeypatch):
    import video_ai.runtime.temporal_scene_admission as admission
    root = tmp_path/'qualification'
    files = []
    for index in range(27):
        relative = 'native_adapter.py' if index == 0 else f'working/longcat_video/core_{index}.py'
        item = put(root/relative, f'# fixture_only core {index}\n'.encode())
        files.append(dict(path=relative, bytes=item['bytes'], sha256=item['sha256']))
    put(root/'model-manifest.json', {'fixture_only': True})
    put(root/'download-result.json', {'fixture_only': True})
    model_root = tmp_path/'models'
    put(model_root/'LICENSE', b'fixture_only license')
    put(model_root/'weights.safetensors', b'fixture_only weights must stay in place')
    qualification = put(root/'native16-qualification-assessment.json', {'fixture_only': True})
    value = dict(root=qualification, qualification_root=root,
        case={'code_revision': '6b3f4b8582a8bc3f20f795735f5383716c4ba794'},
        software={'files': files, 'versions': {'torch': 'fixture_only'}},
        guard=SimpleNamespace(verify=lambda: None))
    monkeypatch.setattr(admission, 'MODEL_ROOT', model_root)
    # Substitute the expensive historical qualification boundary; exercise the
    # real installer, source hashing, exclusive writes and reuse below it.
    monkeypatch.setattr(admission, 'load_temporal_qualification', lambda *a, **k: value)
    return admission, root, qualification


def test_bundle_installs_exact_core_bytes_reuses_and_never_copies_weights(tmp_path, monkeypatch):
    admission, source, qualification = tiny_qualification(tmp_path, monkeypatch)
    tools = tmp_path/'tools'
    installed = admission.install_temporal_bundle(qualification['path'], tools_root=tools)
    root = Path(installed['root'])
    assert root.is_relative_to(tools)
    assert (root/'native_adapter.py').read_bytes() == b'# fixture_only core 0\n'
    assert len(list(root.rglob('*.py'))) == 27
    assert not list(root.rglob('*.safetensors'))
    assert (root/'LICENSE').read_bytes() == b'fixture_only license'
    before = {str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()}
    assert admission.install_temporal_bundle(qualification['path'], tools_root=tools) == installed
    assert {str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()} == before


def test_bundle_refuses_modified_source_or_existing_destination(tmp_path, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    admission, source, qualification = tiny_qualification(tmp_path, monkeypatch)
    installed = admission.install_temporal_bundle(qualification['path'], tools_root=tmp_path/'tools')
    target = Path(installed['root'])/'native_adapter.py'
    target.write_bytes(b'changed destination')
    with pytest.raises(ProductionRefused):
        admission.install_temporal_bundle(qualification['path'], tools_root=tmp_path/'tools')
    assert target.read_bytes() == b'changed destination'
    (source/'native_adapter.py').write_bytes(b'changed source')
    with pytest.raises(ProductionRefused):
        admission.install_temporal_bundle(qualification['path'], tools_root=tmp_path/'different-tools')


def ready_fixture(tmp_path, monkeypatch):
    admission, source, root = tiny_qualification(tmp_path, monkeypatch)
    qualified = admission.load_temporal_qualification(root['path'])
    scope = dict(cases=1, windows=4, frames=320, width=768, height=432, fps='16/1')
    model = put(source/'model-manifest.json', {'fixture_only': True})
    download = put(source/'download-result.json', {'fixture_only': True})
    qualified.update(observed_visual_scope=scope, value={'model_manifest': model, 'download_receipt': download}, artifacts=[root, model, download])
    tools = tmp_path/'tools'
    monkeypatch.setattr(admission, 'BUNDLE_TOOLS_ROOT', tools, raising=False)
    bundle = admission.install_temporal_bundle(root['path'], tools_root=tools)
    worker = put(tmp_path/'worker.py', b'# fixture_only production worker\n')
    native = put(tmp_path/'native.exe', b'fixture_only native executable')
    monkeypatch.setattr(admission, 'NATIVE_PYTHON', Path(native['path']), raising=False)
    monkeypatch.setattr(admission, '_current_worker_sources', lambda: [Path(worker['path'])], raising=False)
    resource = dict(complete=True, algorithm='temporal_native_resource_v1', production_worker=worker,
        production_sources=[worker], runtime_bundle=bundle['manifest'], model_manifest_sha256=model['sha256'],
        package_versions=qualified['software']['versions'], allocator_backend='cudaMallocAsync',
        completed_shapes=['first', 'clean_history', 'continuation', 'vae_encode_13', 'vae_decode_93'],
        output_clock_policy='predeclared_deployment_clock_16_no_model_fps_condition_v1',
        native_diffusion_calls=0, new_text_encoding_calls=0, time_limit_seconds=None, max_gpu_allocated_bytes=None,
        prepared_latent_shape=[1, 16, 24, 54, 96], clean_kv_shape=[1, 32, 5184, 128], kv_bytes=4076863488,
        vae_encode_shape=[1, 16, 4, 54, 96], vae_decode_frames_shape=[93, 432, 768, 3], deployed_output_fps=16,
        worker_import_footprint_included=True,
        startup_available=dict(physical=9*1024**3, commit=11*1024**3, gpu=19*1024**3, disk=40*1024**3),
        minima=dict(physical=3*1024**3, commit=5*1024**3, gpu=2*1024**3, disk=40*1024**3))
    return admission, qualified, bundle, worker, native, resource


def ready_document(tmp_path, qualified, bundle, worker, native, resource):
    resource_id = put(tmp_path/'resource.json', resource)
    record = dict(schema_version=1, algorithm='temporal_native_admission_v1', qualification_root=qualified['root'],
        observed_visual_scope=qualified['observed_visual_scope'], model_manifest=qualified['value']['model_manifest'],
        runtime_bundle=bundle['manifest'], native_python=native, package_versions=qualified['software']['versions'],
        production_worker=worker, production_resource=resource_id, artifacts=[],
        assessment=dict(qualification='accepted', production_resource='passed', ready=True))
    artifacts = {item['path']: item for item in qualified['artifacts']}
    for item in [bundle['manifest'], worker, native, resource_id]: artifacts[item['path']] = item
    manifest = json.loads(Path(bundle['manifest']['path']).read_bytes())
    for row in manifest['core_files']+manifest['auxiliary_files']:
        item = dict(row, path=str(Path(bundle['root'])/row['path']))
        artifacts[item['path']] = item
    for item in resource['production_sources']: artifacts[item['path']] = item
    record['artifacts'] = [artifacts[key] for key in sorted(artifacts)]
    path = tmp_path/'evidence.json'
    put(path, record)
    return path


def test_resource_binding_detects_changed_worker_record_helper(tmp_path,monkeypatch):
    import video_ai.runtime.temporal_scene_admission as module
    source_inventory=module._current_worker_sources
    admission,qualified,bundle,worker,native,resource=ready_fixture(tmp_path,monkeypatch)
    package=tmp_path/'wrapper-package'
    names=['runtime/temporal_native_worker.py','runtime/temporal_native_process.py','runtime/temporal_scene_admission.py',
        'runtime/temporal_scene_records.py','runtime/temporal_scene_observations.py','runtime/_temporal_media_check_coverage.py','runtime/temporal_scene_origins.py',
        'planning/scene_temporal.py']
    for name in names:put(package/name,('# fixture_only wrapper '+name).encode())
    monkeypatch.setattr(admission,'__file__',str(package/'runtime/temporal_scene_admission.py'))
    monkeypatch.setattr(admission,'_current_worker_sources',source_inventory)
    sources=[{key:value for key,value in put(path,Path(path).read_bytes()).items()} for path in source_inventory()]
    worker=sources[0];resource.update(production_worker=worker,production_sources=sources)
    document=ready_document(tmp_path,qualified,bundle,worker,native,resource)
    admission.load_temporal_evidence(document)
    (package/'runtime/temporal_scene_records.py').write_bytes(b'# changed worker sample validator')
    from video_ai.runtime.production_state import ProductionRefused
    with pytest.raises(ProductionRefused):admission.load_temporal_evidence(document)


@pytest.mark.parametrize('fault', ['worker_bytes', 'missing_minima', 'low_commit', 'wrong_latent', 'wrong_clock', 'wrong_core'])
def test_claimed_ready_cannot_hide_runtime_or_measured_resource_drift(fault, tmp_path, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    admission, qualified, bundle, worker, native, resource = ready_fixture(tmp_path, monkeypatch)
    if fault == 'worker_bytes':
        # A different existing worker with its own valid Artifact cannot satisfy
        # the actual current source closure in the resource receipt.
        worker = put(tmp_path/'other_worker.py', b'other fixture_only worker')
        resource['production_worker'] = worker
    elif fault == 'missing_minima': del resource['minima']
    elif fault == 'low_commit': resource['minima']['commit'] = 3*1024**3
    elif fault == 'wrong_latent': resource['prepared_latent_shape'] = [1, 16, 24, 60, 104]
    elif fault == 'wrong_clock': resource['deployed_output_fps'] = 15
    else:
        (Path(bundle['root'])/'native_adapter.py').write_bytes(b'changed installed core')
    path = ready_document(tmp_path, qualified, bundle, worker, native, resource)
    with pytest.raises(ProductionRefused): admission.load_temporal_evidence(path)


def test_valid_fixture_closure_accepts_then_guard_rejects_changed_bytes(tmp_path, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    admission, qualified, bundle, worker, native, resource = ready_fixture(tmp_path, monkeypatch)
    path = ready_document(tmp_path, qualified, bundle, worker, native, resource)
    loaded = admission.load_temporal_evidence(path)
    assert loaded['value']['assessment']['ready'] is True
    Path(worker['path']).write_bytes(b'changed after admission')
    with pytest.raises(ProductionRefused): loaded['guard'].verify()


def test_native_freeze_keeps_exact_evidence_and_rejects_orphan_or_drift(tmp_path, monkeypatch, runtime_run):
    import video_ai.runtime.temporal_scene_admission as admission
    from video_ai.runtime.production_state import ProductionRefused
    source = put(tmp_path/'source.json', {'fixture_only': True})
    bundle = put(tmp_path/'bundle.json', {'fixture_only': True, 'core': 27})
    settings = dict(mode='temporal_extension_v1', prompt_policy='visual_v2', prompt_contract='prompt.json', temporal_evidence=str(tmp_path/'source.json'))
    def load(path, **kwargs):
        raw = Path(path).read_bytes()
        return dict(root=dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()), raw=raw,
            value={'runtime_bundle': bundle}, artifacts=[bundle], guard=SimpleNamespace(verify=lambda: None))
    monkeypatch.setattr(admission, 'load_temporal_evidence', load)
    config = SimpleNamespace(raw={'scene_rendering': settings})
    run = runtime_run[0]
    identities = {}
    def save(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    admission.freeze_temporal_evidence(config, run, identities, save=save)
    assert set(identities) == {'temporal_evidence', 'temporal_evidence_closure', 'temporal_runtime_bundle'}
    assert Path(identities['temporal_evidence']['path']).read_bytes() == Path(source['path']).read_bytes()
    frozen = SimpleNamespace(config=config, options={'script_path': str(run/'production/script.txt'),
        'execution_policy': {'input_identities': identities}})
    assert admission.verify_temporal_frozen(frozen)['value']['runtime_bundle'] == bundle
    Path(identities['temporal_runtime_bundle']['path']).write_bytes(b'changed copy')
    with pytest.raises(ProductionRefused): admission.verify_temporal_frozen(frozen)
    config.raw['scene_rendering'] = dict(mode='segmented_v1', prompt_policy='visual_v2', prompt_contract='prompt.json')
    with pytest.raises(ProductionRefused): admission.verify_temporal_frozen(frozen)


def test_native_active_inputs_skip_wan_models_and_graphs():
    from video_ai.jimeng_config import active_models, active_workflows
    config = SimpleNamespace(production_strategy='paragraph_jimeng_v1',
        raw={'scene_rendering': {'mode': 'temporal_extension_v1'}},
        models={'wan_high': 'high', 'wan_low': 'low', 'text_encoder': 'wan_text', 'vae': 'wan_vae', 'upscale': 'up', 'sdxl': 'image'},
        workflows={'wan': 'wan', 'wan_mapping': 'mapping', 'upscale': 'up', 'sdxl': 'image'})
    assert active_models(config) == {'upscale': 'up'}
    assert active_workflows(config) == {'upscale': 'up'}
    config.raw['scene_rendering']['mode'] = 'whole_scene_v1'
    assert 'wan_high' in active_models(config) and 'wan' in active_workflows(config)


def test_exporter_requires_real_preflight_and_rejects_external_target(tmp_path, capsys):
    import runpy
    script = Path(__file__).resolve().parents[2]/'scripts/export_temporal_evidence.py'
    main = runpy.run_path(str(script))['main']
    target = tmp_path/'must-not-be-ready.json'
    with pytest.raises(SystemExit) as error:
        main(['--runtime', str(tmp_path/'runtime.json'), '--target', str(target)])
    assert error.value.code == 2 and not target.exists()
    assert main(['--runtime', str(tmp_path/'runtime.json'), '--production-preflight', str(tmp_path/'resource.json'),
                 '--target', 'C:/outside-native-evidence.json']) == 2
    assert not target.exists()
    assert 'refused' in capsys.readouterr().err


def frozen_native_fixture(tmp_path,monkeypatch,runtime_run):
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    admission,qualified,bundle,worker,native,resource=ready_fixture(tmp_path,monkeypatch)
    guard=EvidenceReader()
    for item in qualified['artifacts']:guard.capture(item['path'],item)
    qualified['guard']=guard
    document=ready_document(tmp_path,qualified,bundle,worker,native,resource)
    config=SimpleNamespace(raw=dict(scene_rendering=dict(mode='temporal_extension_v1',prompt_policy='visual_v2',
        prompt_contract='D:/VideoSi/fixture-prompts.json',temporal_evidence=str(document))))
    run=runtime_run[0];identities={}
    def save(path,raw):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    admission.freeze_temporal_evidence(config,run,identities,save=save)
    frozen=SimpleNamespace(config=config,options=dict(run_id=run.name,script_path=str(run/'production/script.txt'),
        execution_policy=dict(input_identities=identities)))
    return admission,frozen,bundle


def test_native_admission_reuses_semantics_in_one_operation_but_rechecks_bytes(tmp_path,monkeypatch,runtime_run):
    from video_ai.runtime.verification import validation_session
    from video_ai.runtime.production_state import ProductionRefused
    admission,frozen,bundle=frozen_native_fixture(tmp_path,monkeypatch,runtime_run)
    original=admission._production_parts;calls=[]
    def counted(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(admission,'_production_parts',counted)
    with validation_session():
        first=admission.verify_temporal_frozen(frozen)
        for _ in range(3):assert admission.verify_temporal_frozen(frozen)['root']==first['root']
        assert len(calls)==1,'one operation must not rebuild historical qualification for every origin guard'
        core=Path(bundle['root'])/'native_adapter.py';raw=core.read_bytes()
        core.write_bytes(b'# changed native adapter bytes')
        try:
            with pytest.raises(ProductionRefused):admission.verify_temporal_frozen(frozen)
        finally:core.write_bytes(raw)
    admission.verify_temporal_frozen(frozen)
    assert len(calls)==2,'operation-local reuse must not escape to a later call'

