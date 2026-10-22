"""Current-run admission adapters for explicitly proven inherited content."""
from copy import deepcopy
from pathlib import Path

from ..planning.production_scenes import canonical_digest
from .production_state import ProductionRefused
from .scene_revision_records import require_scene_revision,require_revision_import


def proof_for(frozen,domain,key,*,context=None):
    if 'scene_revision' not in frozen.options: return None
    proof = context if context is not None else require_scene_revision(frozen)
    if domain+':'+key not in proof['imports']: return None
    return proof


def canonical_choice(frozen,key,proof):
    from ._scene_revision_origins import inherited
    choice = require_revision_import(frozen,'choice',key,context=proof)
    image = require_revision_import(frozen,'image',key,context=proof)
    candidate = next((c for c in image['candidates'] if c['candidate_id']==choice['candidate_id'] and c['sha256']==choice['sha256']),None)
    if candidate is None: raise ProductionRefused('inherited choice lacks matching imported original')
    return dict(choice,path=candidate['path'])


def inherited_batch(frozen,bible,plan,index,prior):
    if 'scene_revision' not in frozen.options: return None
    proof = require_scene_revision(frozen); ids = plan['batches'][index-1]
    if any('choice:'+sid not in proof['imports'] for sid in ids): return None
    from . import image_selection_records as images
    choices = [canonical_choice(frozen,sid,proof) for sid in ids]
    manifests = [Path(frozen.options['script_path']).parent/'jimeng'/sid/'candidates.json' for sid in ids]
    batch = images._expected_batch(frozen,None,None,bible,plan,manifests,index,prior)
    all_choices = images._choices(prior); all_choices.update({r['scene_id']:r for r in choices})
    # This is an in-memory inherited admission view, never an owned accepted.json
    # or a newly authored observation/submission. The import hashes name its proof.
    return dict(schema_version=2,production_strategy=frozen.options['production_strategy'],run_id=frozen.options['run_id'],
        batch_id=f'image_batch_{index:04d}',scene_manifest_sha256=canonical_digest(batch),
        scene_plan_sha256=canonical_digest(plan),visual_bible_sha256=canonical_digest(bible),selections=choices,
        baseline_bindings=images._baselines(bible,all_choices),
        source_submission_sha256=canonical_digest([proof['imports']['choice:'+sid][1] for sid in ids]))


def inherited_image_group(frozen,units,timeline,bible,plan):
    proof = proof_for(frozen,'image_group','all')
    if proof is None:return None
    root = Path(frozen.options['script_path']).parent/'image-selection'
    if (root/'complete-acceptance.json').exists(): raise ProductionRefused('owned image group competes with inherited acceptance')
    from . import image_selection_records as images
    original = require_revision_import(frozen,'image_group','all',context=proof)
    accepted = images._load_accepted(frozen,units,timeline,bible,plan)
    choices = images._choices(accepted)
    observation = images._observation(original['observation'],{},choices)
    if observation['verdict']!='passed': raise ProductionRefused('inherited group lacks passed observation')
    resolved = dict(original,run_id=frozen.options['run_id'],scene_plan_sha256=canonical_digest(plan),
        visual_bible_sha256=canonical_digest(bible),selections=[choices[s['scene_id']] for s in plan['scenes']],
        baseline_bindings=images._baselines(bible,choices),
        accepted_batches=[dict(batch_id=b['batch_id'],accepted_sha256=canonical_digest(b)) for b in accepted])
    proof['guard'].register('image_group:all#resolved',resolved)
    return resolved


def inherited_clip_record(frozen,key,*,context=None,row=None,parent=None):
    proof = proof_for(frozen,'clip',key,context=context)
    if proof is None:return None
    run = Path(frozen.options['script_path']).parent.parent
    folder = run/'production/scene-clips'/key
    if folder.exists() and any(folder.iterdir()): raise ProductionRefused('owned clip competes with imported clip')
    from .production_inputs import load_frozen_inputs
    from ._scene_revision_origins import source_clip_record,remap_media
    source = load_frozen_inputs(proof['source_run'])
    record = source_clip_record(source,key)
    sidecar = proof['imports']['clip:'+key][0]
    if row is not None:
        request = record['request']
        for field in ('budget','parameters','narration_bindings'):
            if canonical_digest(row[field])!=canonical_digest(request[field]): raise ProductionRefused('inherited clip parameters/coverage differ')
        if parent is not None and request['parent']['clip_id']!=parent['clip']['clip_id']:
            raise ProductionRefused('inherited continuation parent differs')
    record = remap_media(record,sidecar['local_artifacts'])
    record['clip'] = require_revision_import(frozen,'clip',key,context=proof)
    for name in ('request','last_frame','accepted','template'):
        if record.get(name) is not None: proof['guard'].register('clip:'+key+'#'+name,record[name])
    proof['guard'].verify_captured_bytes()
    return record


def inherited_frame(context,row):
    store = context['store']; frozen = context['frozen']; key = row['frame_id']
    proof = proof_for(frozen,'upscale',key,context=getattr(store,'revision_context',None))
    if proof is None:return None
    folder = store.frame_dir(key)
    if folder.exists() and any(folder.iterdir()): raise ProductionRefused('owned frame competes with import')
    result = require_revision_import(frozen,'upscale',key,context=proof)
    from ._scene_upscale_records import mapping
    if canonical_digest(result['mapping'])!=canonical_digest(mapping(row)): raise ProductionRefused('inherited frame mapping differs')
    return result


def final_comparison_request(context,clip_id):
    store = context['store']; frozen = context['frozen']
    record = inherited_clip_record(frozen,clip_id,context=getattr(store,'revision_context',None))
    if record is None:
        from ..config import read_json
        return read_json(store.run_dir/'production/scene-clips'/clip_id/'request.json')
    proof = store.revision_context
    from ._scene_revision_origins import remap_media
    mappings = [m for sidecar,_ in proof['imports'].values() for m in sidecar['local_artifacts']]
    request = remap_media(record['request'],mappings)
    proof['guard'].register('clip:'+clip_id+'#comparison',request)
    return request
