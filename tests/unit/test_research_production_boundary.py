"""Research run markers must reject automatic production before any write."""
from dataclasses import replace
from types import SimpleNamespace
import pytest

from scene_continuity_helpers import save
from video_ai.runtime.production_state import ProductionRefused


def test_research_run_cannot_be_frozen_as_ordinary_production(runtime_run):
    from video_ai.runtime.production_inputs import freeze_inputs
    run, config, _ = runtime_run
    save(run / 'research/options.json', dict(schema_version=1, execution_mode='research'))
    with pytest.raises(ProductionRefused, match='research'):
        freeze_inputs(config, run, text='Research material must not become production.')
    assert not (run / 'production').exists()


def test_research_options_cannot_be_loaded_as_ordinary_production(runtime_run):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    run, _, _ = runtime_run
    save(run / 'research/options.json', dict(schema_version=1, execution_mode='research'))
    with pytest.raises(ProductionRefused, match='research'):
        load_frozen_inputs(run)


def test_research_config_rejected_before_production_checks(runtime_run):
    from video_ai.runtime.production_inputs import validate_supported
    _, config, _ = runtime_run
    config = replace(config, raw=dict(config.raw, scene_research_material=dict(schema_version=1)))
    with pytest.raises(ProductionRefused, match='research'):
        validate_supported(config)
