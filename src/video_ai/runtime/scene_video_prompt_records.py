"""Frozen reviewed prompt bytes and proven binding across inherited scene views."""
from pathlib import Path

from ..adapters.common import strict_json
from ..planning.production_scenes import canonical_digest
from ..planning.scene_video_prompts import parse_scene_rendering, validate_scene_video_prompt_contract
from .manifest import hash_file, thaw
from .production_state import ProductionRefused, run_path


def contract_source(config):
    settings = parse_scene_rendering(config.raw['scene_rendering'])
    path = Path(settings['prompt_contract'])
    return path if path.is_absolute() else config.config_file.parent/path


def parse_contract_bytes(raw):
    return validate_scene_video_prompt_contract(strict_json(raw.removeprefix(b'\xef\xbb\xbf')))


def source_contract_identity(config):
    """Read one stable snapshot, including text admission, before revision allocation."""
    from .scene_revision_records import stable_bytes
    path = contract_source(config).resolve(strict=True)
    raw = stable_bytes(path,root=path.parent)
    contract = parse_contract_bytes(raw)
    validate_contract_mode(contract, config.raw['scene_rendering'])
    import hashlib
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def validate_contract_mode(contract, settings):
    settings = parse_scene_rendering(settings)
    if (contract['schema_version'] == 2) != (settings.get('mode') == 'whole_scene_v1'):
        raise ProductionRefused('prompt schema differs from frozen rendering mode')
    return contract


def load_prompt_contract(frozen):
    """Rehash the frozen file on every entry, even when the FrozenInputs is cached."""
    raw = frozen.config.raw
    records = frozen.options['execution_policy']['input_identities']
    if 'scene_rendering' not in raw:
        if 'scene_video_prompts' in records: raise ProductionRefused('orphan frozen prompt identity')
        return None,None
    parse_scene_rendering(raw['scene_rendering'])
    bound = records.get('scene_video_prompts')
    if bound is None: raise ProductionRefused('frozen visual prompt identity missing')
    run = Path(frozen.options['script_path']).parent.parent
    path = run_path(run,bound['path'])
    if path != run/'production/scene-video-prompts.json': raise ProductionRefused('frozen prompt path differs')
    # Read and hash the very bytes parsed, then verify that the file is still fresh.
    from .scene_revision_records import stable_bytes
    import hashlib
    content = stable_bytes(path,root=run)
    artifact = dict(path=str(path),bytes=len(content),sha256=hashlib.sha256(content).hexdigest())
    if any(artifact[k] != bound[k] for k in artifact): raise ProductionRefused('frozen visual prompt bytes changed')
    value = parse_contract_bytes(content)
    validate_contract_mode(value, raw['scene_rendering'])
    fresh = hash_file(path)
    if (fresh.bytes,fresh.sha256) != (artifact['bytes'],artifact['sha256']):
        raise ProductionRefused('visual prompt changed while reading')
    return value,artifact


def prompt_binding_context(frozen,contract,bible,plan,wan_inputs):
    """A revision may retain exact source bindings only for fully proven imports.

    Imported views change run IDs/paths. The review remains bound to original
    admitted bytes; it is never silently re-signed against the remapped view.
    """
    current = frozen
    while True:
        expected = dict(scene_plan_sha256=canonical_digest(thaw(plan)),
            visual_bible_sha256=canonical_digest(thaw(bible)),wan_inputs_sha256=canonical_digest(thaw(wan_inputs)))
        if contract.get('schema_version') == 2:
            from types import SimpleNamespace
            from ..planning.scene_execution import derive_scene_execution_clips
            clips = derive_scene_execution_clips(plan, SimpleNamespace(total_frames=plan['total_frames']), mode='whole_scene_v1')
            expected.update(rendering_mode='whole_scene_v1', execution_clips_sha256=canonical_digest(clips))
        if thaw(contract['binding']) == expected:
            context = dict(bible=bible,plan=plan,wan_inputs=wan_inputs,script=current.script)
            validate_scene_video_prompt_contract(contract,**context)
            return context
        if 'scene_revision' not in current.options:
            raise ProductionRefused('prompt binding differs from admitted scene inputs')
        from .scene_revision_records import require_scene_revision,load_scene_common_prefix
        proof = require_scene_revision(current)
        required = {'common:all','plan:all','image_group:all'} | {'choice:'+s['scene_id'] for s in plan['scenes']}
        if not required <= set(proof['imports']):
            raise ProductionRefused('prompt source binding requires unchanged imported plan and selections')
        from .production_inputs import load_frozen_inputs
        from .image_selection_records import load_committed_plan
        from .reference_image_records import require_reference_image_acceptance,build_reference_image_acceptance
        current = load_frozen_inputs(proof['source_run'])
        units,timeline = load_scene_common_prefix(current)
        bible,plan = load_committed_plan(current,units,timeline)
        source_run = Path(current.options['script_path']).parent.parent
        wan_path = source_run/'production/reference-images/wan-inputs.json'
        if wan_path.exists():
            wan_inputs = require_reference_image_acceptance(current,units,timeline)
        else:
            # An intermediate revision can be revised again before its pipeline
            # writes derived aggregates. Reconstruct only fully imported images;
            # an extant (possibly corrupted) record always takes the strict path.
            if 'scene_revision' not in current.options:
                raise ProductionRefused('source Wan admission record missing')
            inherited = require_scene_revision(current)
            required = {'common:all','plan:all','image_group:all'} | {'choice:'+s['scene_id'] for s in plan['scenes']}
            if not required <= set(inherited['imports']):
                raise ProductionRefused('missing source Wan view lacks complete import proof')
            inherited['guard'].capture_absent(wan_path,root=source_run)
            wan_inputs = build_reference_image_acceptance(current,units,timeline)
            inherited['guard'].verify_captured_bytes()
        proof['guard'].verify_captured_bytes()
