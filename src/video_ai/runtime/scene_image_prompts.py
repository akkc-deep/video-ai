"""Effective image text from byte-bound user revisions; base plans stay immutable."""
from pathlib import Path

from .production_state import ProductionRefused


def effective_image_prompt(frozen, scene):
    from .scene_revision_records import require_scene_revision, _json
    from ..planning.scene_revision import validate_revision_request_fields
    if 'scene_revision' not in frozen.options:
        return scene['image_prompt']
    proof = require_scene_revision(frozen)
    run = Path(frozen.options['script_path']).parent.parent
    request = _json(proof['commit']['request']['path'], root=run/'production/scene-revision')
    overrides = validate_revision_request_fields(request)
    if scene['scene_id'] in overrides:
        if scene['scene_id'] not in proof['invalidation']['dirty']['images']:
            raise ProductionRefused('image prompt override lacks image invalidation')
        return overrides[scene['scene_id']]
    # A fresh layout has new scene identities; only imported plans inherit text.
    if 'plan:all' in proof['imports']:
        from .production_inputs import load_frozen_inputs
        origin = load_frozen_inputs(proof['source_run'])
        return effective_image_prompt(origin, scene)
    return scene['image_prompt']
