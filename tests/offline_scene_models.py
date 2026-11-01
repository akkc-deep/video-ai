"""Tiny model identities for offline protocol tests; no inference is performed.

The real model-root and environment contract is tested separately. This seam
accepts only the exact fixture paths it creates; every file still participates
in the real frozen SHA/stamp and drift checks.
"""
from pathlib import Path
from uuid import uuid4


def model_inputs(config, patch):
    from video_ai.runtime import production_visual_templates
    from video_ai.runtime.manifest import thaw
    models=thaw(config.models)
    root=Path('D:/VideoSi/models/tests')/('offline-scene-'+uuid4().hex)
    root.mkdir(parents=True)
    replacements={}
    for role in ('wan_high','wan_low','text_encoder','vae','upscale'):
        path=root/Path(models[role]).name
        with path.open('xb') as stream:stream.write(('fixture_only identity; never loaded: '+role).encode())
        models[role]=str(path);replacements[role]=path
    original=production_visual_templates.validate_production_model_paths
    def validate_fixture_or_real(candidate):
        if all(Path(candidate.models[role])==path for role,path in replacements.items()):
            if any(not path.is_file() for path in replacements.values()):
                raise ValueError('offline fixture model missing')
            return
        return original(candidate)
    patch.setattr(production_visual_templates,'validate_production_model_paths',validate_fixture_or_real)
    return models
