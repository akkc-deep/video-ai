from dataclasses import replace
import json

import pytest

from unit.test_jimeng_config import configured
from unit.test_production_inputs import production_config


def test_freeze_new_strategy_skips_missing_sdxl_and_locks_model(production_config, runtime_run, tmp_path):
    from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
    config = configured(production_config, tmp_path)
    # Remove paths from a valid source configuration rather than mutate only resolved objects.
    data = json.loads(config.config_file.read_text(encoding='utf-8'))
    for group in ('models', 'workflows'):
        data[group]['sdxl'] = 'D:/VideoSi/models/not-installed-sdxl' if group == 'models' else 'D:/code/py/video-ai/workflows/not-installed-sdxl.json'
    config.config_file.write_text(json.dumps(data), encoding='utf-8')
    from video_ai.config import load_config
    config = load_config(config.config_file)
    run = runtime_run[0]
    frozen = freeze_inputs(config, run, text='完整旁白。', image_model='jimeng_t2i_v31')
    assert frozen.options['schema_version'] == 2
    assert frozen.config.image_generation.req_key == 'jimeng_t2i_v31'
    assert 'sdxl' not in frozen.options['model_stamps']
    assert 'sdxl' not in frozen.options['workflow_snapshots']
    assert load_frozen_inputs(run).config.image_generation.req_key == 'jimeng_t2i_v31'
    with pytest.raises(ValueError, match='model'):
        load_frozen_inputs(run, image_model='jimeng_t2i_v40')
    config.config_file.write_text('{}', encoding='utf-8')
    assert load_frozen_inputs(run).config.image_generation.req_key == 'jimeng_t2i_v31'


def test_cli_image_model_is_forwarded(monkeypatch, capsys):
    from video_ai.cli import main
    import video_ai.production as production
    seen = {}
    def make(config, **kwargs):
        seen.update(kwargs)
        return production.ProductionResult()
    monkeypatch.setattr(production, 'make_video', make)
    assert main(['make-video', '--text', '中文', '--image-model', 'my_model', '--json']) == 2
    assert seen['image_model'] == 'my_model'


def test_new_preflight_does_not_require_sdxl(production_config, runtime_run, tmp_path):
    from video_ai.runtime.preflight import preflight
    import subprocess
    config = configured(production_config, tmp_path)
    missing = runtime_run[0]/'not-installed.safetensors'
    config = replace(config, models=dict(config.models, sdxl=missing),
                     workflows=dict(config.workflows, sdxl=missing.with_suffix('.json')))
    def runner(args, **kwargs):
        if args[-1] == '-encoders': text = ' V....D libx264 H264\n A..... aac AAC\n'
        elif args[-1] == '-filters': text = ' .. subtitles V->V render\n'
        else: text = 'fixture version\n'
        kwargs['stdout'].write(text)
        return subprocess.CompletedProcess(args, 0)
    report = preflight(config, automatic=True, runner=runner, log_dir=runtime_run[0]/'logs/jimeng-preflight')
    assert report.passed, report.as_dict()
    assert not any('sdxl' in c.name for c in report.checks)
    assert any(c.name == 'workflow.wan' for c in report.checks)


def test_new_config_can_omit_sdxl_entirely(production_config, runtime_run, tmp_path):
    from video_ai.config import load_config
    from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
    from video_ai.runtime.manifest import create_manifest
    config = configured(production_config, tmp_path)
    data = json.loads(config.config_file.read_text(encoding='utf-8'))
    for group in ('models', 'workflows'): data[group].pop('sdxl')
    config.config_file.write_text(json.dumps(data), encoding='utf-8')
    frozen = freeze_inputs(load_config(config.config_file), runtime_run[0], text='完整。')
    assert 'sdxl' not in load_frozen_inputs(runtime_run[0]).config.models
    assert create_manifest(runtime_run[0], frozen.config, inputs={}, models={}, workflows={}).snapshot()
