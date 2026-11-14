"""Complete Wan conditioning from guarded revisions, without mutating plans."""
from pathlib import Path

from .production_state import ProductionRefused


def _renderer_identity(frozen):
    """Compare renderer content, ignoring relocated frozen snapshot paths."""
    options = frozen.options
    inputs = options.get('execution_policy', {}).get('input_identities', {})
    workflows = options.get('workflow_snapshots', {})
    def content(stamp):
        return None if stamp is None else (stamp.get('bytes'), stamp.get('sha256'))
    return (
        tuple(content(workflows.get(role, {}).get('source_identity', inputs.get('workflow/'+role)))
              for role in ('wan', 'wan_mapping')),
        tuple(content(options.get('model_stamps', {}).get(role))
              for role in ('wan_high', 'wan_low', 'text_encoder', 'vae')))


def effective_clip_prompt_overrides(frozen) -> dict[str, str]:
    """Resolve nearest explicit text once, across unchanged legacy plan imports."""
    from .scene_revision_records import require_scene_revision, _json
    from ..planning.scene_revision import validate_revision_request_fields
    effective, guards = {}, []
    current = frozen
    while 'scene_revision' in current.options:
        proof = require_scene_revision(current)
        run = Path(current.options['script_path']).parent.parent
        request = _json(proof['commit']['request']['path'], root=run/'production/scene-revision')
        validate_revision_request_fields(request)
        guards.append(proof['guard'])
        changes = request.get('clip_prompt_overrides', {})
        if 'scene_rendering' in current.config.raw:
            if changes: raise ProductionRefused('clip prompt overrides require legacy Wan rendering')
            break
        if any(cid not in proof['invalidation']['dirty']['clips'] for cid in changes):
            raise ProductionRefused('clip prompt override lacks clip invalidation')
        for cid, text in changes.items(): effective.setdefault(cid, text)
        if 'plan:all' not in proof['imports']: break
        origin = proof['source_frozen']
        if ('scene_rendering' in origin.config.raw
                or _renderer_identity(current) != _renderer_identity(origin)):
            break
        current = origin
    # Reuse the established byte guards, including the request artifacts just read.
    for guard in guards: guard.verify_captured_bytes()
    return effective
