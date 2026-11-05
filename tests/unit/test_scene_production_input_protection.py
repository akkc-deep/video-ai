"""Default scene writers retain sealed input handles while outputs stay movable."""
from contextvars import copy_context
import os
from types import SimpleNamespace

import pytest

from video_ai.runtime import verification, manifest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows mandatory sharing')


def prepared(runtime_run):
    run, _, _ = runtime_run
    production = run/'production'
    production.mkdir()
    source = production/'script.txt'
    source.write_bytes(b'original script')
    mutable = production/'staging.json'
    mutable.write_bytes(b'first')
    frozen = SimpleNamespace(config=SimpleNamespace(production_strategy='paragraph_jimeng_v1'),
        options={'script_path': str(source), 'execution_policy': {'input_identities': {}}})
    return frozen, source, mutable


def test_default_scene_scope_protects_frozen_inputs_and_allows_output_promotion(runtime_run):
    frozen, source, mutable = prepared(runtime_run)
    with verification.scene_input_protection(frozen):
        first = manifest.hash_file(source)
        with pytest.raises(OSError):
            source.write_bytes(b'changed script!')
        old = manifest.hash_file(mutable)
        mutable.write_bytes(b'other')
        assert manifest.hash_file(mutable).sha256 != old.sha256
        mutable.rename(mutable.with_name('published.json'))
        assert manifest.hash_file(source).sha256 == first.sha256
    source.write_bytes(b'afterwards')


def test_scene_scope_reuses_existing_window_without_expanding_its_roots(runtime_run):
    frozen, source, mutable = prepared(runtime_run)
    with verification.whole_input_protection(immutable_roots=[source]):
        outer = verification._whole_inputs.get()
        with verification.scene_input_protection(frozen):
            assert verification._whole_inputs.get() is outer
            manifest.hash_file(source)
            manifest.hash_file(mutable)
            mutable.write_bytes(b'other')


def test_scene_scope_copied_context_cannot_reuse_released_input(runtime_run):
    frozen, source, _ = prepared(runtime_run)
    with verification.scene_input_protection(frozen):
        before = manifest.hash_file(source)
        copied = copy_context()
    source.write_bytes(b'changed script!')
    assert copied.run(manifest.hash_file, source).sha256 != before.sha256
