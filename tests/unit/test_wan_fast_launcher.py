import importlib.util
from pathlib import Path

import pytest


def api():
    path = Path(__file__).parents[2]/'scripts/observe_fast_comfy.py'
    spec = importlib.util.spec_from_file_location('fast_launcher_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launch_is_local_bounded_and_unsupported_never_launches(tmp_path, monkeypatch):
    module = api()
    with pytest.raises(ValueError, match='LVA-04'):
        module.validate_root(tmp_path/'old-production')
    argv = module.native_arguments(tmp_path, 8189)
    assert argv[argv.index('--listen')+1] == '127.0.0.1'
    assert '--disable-all-custom-nodes' in argv
    assert '--highvram' not in argv and '--use-sage-attention' not in argv


def test_backend_environment_digest_covers_device_options():
    module = api()
    assert module.environment_binding({'PATH':'a','CUDA_VISIBLE_DEVICES':'0'}) != module.environment_binding({'PATH':'a','CUDA_VISIBLE_DEVICES':'1'})
    assert 'SECRET' not in str(module.environment_binding({'SECRET':'private'}))


def test_phase_failure_requests_stop_for_only_its_owned_pid(tmp_path, monkeypatch):
    import json
    path = Path(__file__).parents[2]/'scripts/benchmark_wan_fast.py'
    spec = importlib.util.spec_from_file_location('fast_benchmark_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = tmp_path/'LVA-04-test'; (root/'frozen').mkdir(parents=True)
    (root/'frozen/profile.json').write_text(json.dumps({'profile_sha256':'a'*64}))
    (root/'service-owner.json').write_text(json.dumps({'pid':123}))
    monkeypatch.setattr(module, 'launcher_api', lambda: type('Launcher', (), {'validate_root': staticmethod(lambda p:p)}))
    def fail(*a, **kw): raise RuntimeError('original inference failure')
    monkeypatch.setattr(module, 'run_trial', fail)
    with pytest.raises(RuntimeError, match='original inference failure'):
        module.run_phase(root, port=8189)
    assert json.loads((root/'stop.request.json').read_text()) == {'pid':123}


def test_launcher_rejects_unprofiled_python_or_comfy_tree(tmp_path):
    from types import SimpleNamespace
    module = api()
    profiled_python = tmp_path/'python.exe'; profiled_python.write_bytes(b'profiled')
    profiled_comfy = tmp_path/'comfy'; profiled_comfy.mkdir()
    (profiled_comfy/'main.py').write_text('# original')
    profile = SimpleNamespace(environment_json=__import__('json').dumps(dict(
        comfy_root=str(profiled_comfy.resolve()), python_executable=str(profiled_python.resolve()))))
    module.verify_installation(profile, profiled_comfy, profiled_python)
    with pytest.raises(ValueError, match='profiled installation'):
        module.verify_installation(profile, tmp_path/'another-comfy', profiled_python)
    with pytest.raises(ValueError, match='profiled installation'):
        module.verify_installation(profile, profiled_comfy, tmp_path/'another-python.exe')


def test_manifest_keeps_distinct_parent_and_child_sources(tmp_path):
    import json
    path = Path(__file__).parents[2]/'scripts/benchmark_wan_fast.py'
    spec = importlib.util.spec_from_file_location('fast_manifest_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    cases=[]
    for name, child in (('parent',False),('child',True)):
        root=tmp_path/name;root.mkdir()
        (root/'fixture.json').write_text(json.dumps({'requires_new_parent':child}))
        cases.append({'fixture_id':'parent_child','root':str(root)})
    assert module.baseline_sources(cases) == {'parent_child':str(tmp_path/'parent'),'child':str(tmp_path/'child')}
