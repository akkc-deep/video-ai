"""Isolated real-media inputs and read-only counters for LVA-02."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
from unittest.mock import patch

from video_ai.config import load_config
from video_ai.runtime.manifest import thaw
import pytest


def isolated_config(base, resources):
    """Small fake model/service resources; only FFmpeg/FFprobe are executable."""
    from image_selection_helpers import save
    from uuid import uuid4
    token = 'LVA-02-'+uuid4().hex
    tools_root, models_root = resources/'tools'/token, resources/'models'/token
    config_root = resources/'config'/token; config_root.mkdir(parents=True)
    actual = load_config(Path('E:/VideoAI/shared/config/production.json'))
    tools = {}
    for role, original in base.tools.items():
        path = tools_root/role/original.name
        if role.endswith('_root'):
            path.mkdir(parents=True, exist_ok=True); (path/'entry.py').write_text('# offline fixture')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if role in ('ffmpeg', 'ffprobe'): shutil.copyfile(actual.tools[role], path)
            else: path.write_bytes(b'offline resource; never executed')
        tools[role] = path
    models = {}
    for role, original in base.models.items():
        path = models_root/original.name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'offline model; never loaded'); models[role] = path
    voice = thaw(base.voice.raw)
    for role in ('gpt_weights', 'sovits_weights', 'bert_root', 'hubert_root'):
        path = models_root/role
        if role.endswith('_root'):
            path.mkdir(parents=True, exist_ok=True); (path/'config.json').write_text('{}')
        else: path.write_bytes(b'offline voice model')
        voice[role] = str(path)
    reference = config_root/'reference.wav'; reference.write_bytes(b'offline reference')
    voice.update(reference_audio=str(reference), reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
    font = config_root/actual.media.font_file.name; shutil.copyfile(actual.media.font_file, font)
    raw = thaw(base.raw)
    raw.update(tools=thaw(tools), models=thaw(models), voice_config=str(save(config_root/'voice.json', voice)),
               workflows=thaw(base.workflows))
    raw['media']['font_file'] = str(font)
    return load_config(save(config_root/'config.json', raw))


def real_wan(runtime_run, tmp_path, monkeypatch):
    from scene_clip_helpers import prepared_wan, OfflineWan
    setup = prepared_wan(runtime_run, tmp_path, monkeypatch)
    return setup, OfflineWan(setup)


@pytest.fixture(scope='session')
def scene_validation_config(isolated_test_runtime):
    return isolated_config(load_config(Path(__file__).resolve().parents[1]/'config/production.example.json'),
                           isolated_test_runtime/'shared')


@pytest.fixture
def isolated_runtime_run(scene_validation_config):
    from video_ai.runtime.paths import RuntimePaths, create_run
    paths = RuntimePaths.from_config(scene_validation_config)
    return create_run(paths), scene_validation_config, paths


@contextmanager
def validation_counters():
    """Lightweight counters for walls; no sys profiler or extra filesystem reads."""
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import ArtifactStamp
    from video_ai.runtime import _continuity_byte_guard as byte
    from video_ai.runtime import production_scene_clips as clips
    counts = dict(artifact_entries=0, strict_validations=0, proof_hits=0,
                  inventory_scans=0, model_tool_stamp_checks=0, guard_boundaries=0,
                  producer_invocations=0)
    logical, strict, scan, stamp = (SceneClipStore.validate_artifact,
        SceneClipStore._validate_artifact_uncached, Path.rglob, ArtifactStamp.verify)
    proof_scan = byte._scan
    clip_guard, media_guard = SceneClipStore.capture_guard, SceneMediaStore.capture_guard
    media = clips._media
    def media_operation(context, row, operation, source, target, recipe, producer):
        def counted_producer(staging):
            counts['producer_invocations'] += 1
            return producer(staging)
        return media(context, row, operation, source, target, recipe, counted_producer)
    def guard_factory(original):
        def factory(self, *args, **kwargs):
            guard = original(self, *args, **kwargs)
            def checked():
                counts['guard_boundaries'] += 1
                return guard()
            return checked
        return factory
    def entry(self, value):
        counts['artifact_entries'] += 1
        before = counts['strict_validations']
        result = logical(self, value)
        counts['proof_hits'] += counts['strict_validations'] == before
        return result
    def uncached(self, value):
        counts['strict_validations'] += 1
        return strict(self, value)
    def inventory(self, pattern):
        if pattern == '*.json': counts['inventory_scans'] += 1
        return scan(self, pattern)
    def proof_inventory(spec, deadline):
        # revision_json uses rglob('*'), so avoid counting the same scan twice.
        counts['inventory_scans'] += 1
        return proof_scan(spec, deadline)
    def stamp_check(self):
        counts['model_tool_stamp_checks'] += 1
        return stamp(self)
    with (patch.object(SceneClipStore, 'validate_artifact', entry),
          patch.object(SceneClipStore, '_validate_artifact_uncached', uncached),
          patch.object(Path, 'rglob', inventory), patch.object(byte, '_scan', proof_inventory),
          patch.object(SceneClipStore, 'capture_guard', guard_factory(clip_guard)),
          patch.object(SceneMediaStore, 'capture_guard', guard_factory(media_guard)),
          patch.object(clips, '_media', media_operation),
          patch.object(ArtifactStamp, 'verify', stamp_check)):
        yield counts
