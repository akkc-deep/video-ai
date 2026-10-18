"""TEST ONLY author-bound service commands and inherited environment binding."""
import json
from pathlib import Path
import pytest


@pytest.mark.parametrize('name', ['comfyui', 'tts', 'ollama'])
def test_explicit_service_revision_constructs_exact_local_child_binding(runtime_run, monkeypatch, name):
    from upscale_helpers import setup
    from unit.test_pipeline_revision_resume import authorization, current_files
    from video_ai.config import load_config
    from video_ai.runtime.manifest import create_manifest, hash_file, thaw
    from video_ai.runtime.paths import create_run, RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import
    from video_ai.runtime.service_specs import build_service_specs
    from video_ai.runtime.services import service_environment, ServiceSpec
    f = setup(runtime_run, monkeypatch, frames=1)
    data = thaw(f.config.raw)
    data['voice_config'] = str(f.config.voice.config_file)
    data['services'][name] = {'comfyui':'http://127.0.0.1:8190',
        'tts':'http://127.0.0.1:9882', 'ollama':'http://127.0.0.1:11437'}[name]
    path = f.run/'TEST-ONLY-service-config.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    config = load_config(path)
    changes = authorization(f, config)
    child = create_run(RuntimePaths.from_config(config))
    create_manifest(child, config, inputs={'config':hash_file(config.config_file)}, models={}, workflows={})
    sources = {str(p):thaw(hash_file(p)) for p in current_files(config).values()}
    create_pipeline_import(config, run_dir=child, parent_run_dir=f.run,
        reason='TEST ONLY explicit service revision', changes_identity=hash_file(changes),
        copies=[], source_identities=sources)
    specs = build_service_specs(config, child)
    spec = specs[name]
    assert spec.url == config.services[name]
    flag = '--port' if name == 'comfyui' else '-p'
    if name != 'ollama':
        assert spec.args[spec.args.index(flag)+1] == config.services[name].rsplit(':',1)[1]
    else:
        assert service_environment(RuntimePaths.from_config(config), spec)['OLLAMA_HOST'] == '127.0.0.1:11437'
        from dataclasses import replace
        tampered = replace(spec, env_overrides={'OLLAMA_HOST':'127.0.0.1:11439'})
        with pytest.raises(ValueError):
            service_environment(RuntimePaths.from_config(config), tampered)
        forged = ServiceSpec('ollama', spec.url, spec.args, spec.cwd, spec.start_timeout,
            {'OLLAMA_HOST':'127.0.0.1:11437'})
        with pytest.raises(ValueError):
            service_environment(RuntimePaths.from_config(config), forged)
    grandchild = create_run(RuntimePaths.from_config(config))
    create_manifest(grandchild, config, inputs={'config':hash_file(config.config_file)}, models={}, workflows={})
    sources[str(changes)] = thaw(hash_file(changes))
    create_pipeline_import(config, run_dir=grandchild, parent_run_dir=child,
        reason='TEST ONLY unchanged operational recovery', copies=[], source_identities=sources)
    inherited = build_service_specs(config, grandchild)[name]
    assert inherited.url == spec.url
    if name == 'ollama':
        assert service_environment(RuntimePaths.from_config(config), inherited)['OLLAMA_HOST'] == '127.0.0.1:11437'
    changes.write_bytes(changes.read_bytes()+b'TEST ONLY drift')
    with pytest.raises((ValueError, OSError)):
        build_service_specs(config, grandchild)
