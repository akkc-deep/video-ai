"""Read-only reference provenance and Wan start-image admission.

Signed URLs never belong to a durable logical request. Validation follows each
reference back through accepted selection, decoded original and object receipt.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import re

from ..adapters.jimeng import encode_body
from ..jimeng_config import STRATEGY, parse_image_generation
from ..planning.production_scenes import canonical_digest
from ..reference_config import parse_capability, parse_reference_storage, require_url_budget
from .manifest import thaw
from .production_state import ProductionRefused, object_fields, timestamp
from .reference_settings import load_reference_settings
from . import image_selection_records as images

REFERENCE_FIELDS = 'scene_id candidate_id sha256 bytes width height format uses object'.split()
OBJECT_FIELDS = 'bucket region endpoint key bytes sha256 content_type etag'.split()
PROVENANCE_FIELDS = ('schema_version production_strategy run_id scene_id scene_plan_sha256 visual_bible_sha256 '
                     'model_settings capability_sha256 prompt_sha256 references requests').split()
INTENT_FIELDS = ('schema_version run_id scene_id request_id logical_request_sha256 submit_body_sha256 '
                 'reference_urls created_at').split()


def build_reference_prompt(scene, bible):
    """Use only this scene's stable IDs, retaining the committed Bible order."""
    context = dict(global_style=deepcopy(bible['global_style']))
    for key, field, ids in (('entities', 'entity_id', scene['entity_ids']),
                            ('appearance_variants', 'variant_id', scene['variant_ids']),
                            ('scene_groups', 'group_id', [scene['scene_group_id']])):
        context[key] = [deepcopy(row) for row in bible[key] if row[field] in ids]
    return scene['image_prompt']+'\nVISUAL_BIBLE_JSON\n'+encode_body(context).decode('utf-8')


def resolve_reference_prompt(frozen, scene, bible, capability):
    """Choose once before submission; recover only a fully known saved format."""
    from .reference_visual_prompt import compact_reference_prompt
    full = build_reference_prompt(scene, bible)
    compact = compact_reference_prompt(scene, bible)
    run = images._run(frozen)
    root = run/'production/jimeng'/scene['scene_id']
    settings = load_reference_settings(frozen)
    model = parse_image_generation(settings['model_settings'], 'bound reference model')
    request_ids = {f'request_{i:02d}' for i in range(1, model.candidates_per_scene+1)}
    saved = []
    originals = {}
    for folder in sorted(root.glob('request_*')):
        if not folder.is_dir():
            continue
        if folder.name not in request_ids:
            if any(folder.iterdir()):
                raise ProductionRefused('unexpected reference request evidence')
            continue
        path = folder/'request.json'
        if path.exists():
            value = images._read(path)
            prompt = value.get('prompt') if isinstance(value, dict) else None
            if prompt not in (full, compact):
                raise ProductionRefused('reference request prompt is not a known exact representation')
            saved.append(prompt)
            originals[folder.name] = value
        elif any(folder.iterdir()):
            raise ProductionRefused('reference request evidence lacks original logical request')
    provenance = run/'production/reference-images'/scene['scene_id']/'provenance.json'
    if (root/'candidates.json').exists() and not provenance.exists():
        raise ProductionRefused('reference candidates lack original provenance')
    if (provenance.exists() or (root/'candidates.json').exists()) and not saved:
        raise ProductionRefused('reference provenance lacks original logical requests')
    if saved:
        if any(prompt != saved[0] for prompt in saved):
            raise ProductionRefused('reference requests use different prompt representations')
        prompt = saved[0]
        if provenance.exists():
            value = images._read(provenance)
            object_fields(value, PROVENANCE_FIELDS, 'reference provenance')
            if value['prompt_sha256'] != hashlib.sha256(prompt.encode('utf-8')).hexdigest():
                raise ProductionRefused('reference provenance prompt differs from original requests')
            if not isinstance(value['requests'], list):
                raise ProductionRefused('invalid reference provenance request coverage')
            declared = {}
            for row in value['requests']:
                object_fields(row, ('request_id', 'logical_request_sha256'), 'reference provenance request')
                rid = row['request_id']
                if not isinstance(rid, str) or rid not in request_ids or rid in declared:
                    raise ProductionRefused('invalid reference provenance request identity')
                declared[rid] = row['logical_request_sha256']
            if set(declared) != request_ids or set(originals) != request_ids:
                raise ProductionRefused('reference provenance lacks complete original logical requests')
            if any(canonical_digest(originals[rid]) != declared[rid] for rid in request_ids):
                raise ProductionRefused('reference provenance original logical request digest differs')
            for rid in request_ids:
                _completed_reference_evidence(root/rid, originals[rid], settings,
                                              require_result=(root/'candidates.json').exists())
        return prompt
    return full if len(full.encode('utf-8')) <= capability['max_prompt_bytes'] else compact


def _completed_reference_evidence(folder, request, settings, *, require_result):
    """A durable provenance cannot re-enter the new-submission branch."""
    intent = images._read(folder/'intent.json')
    validate_reference_intent(intent, request, settings)
    validate_submit_evidence(folder, request, intent)
    records = {}
    identity = canonical_digest(request)
    for name, fields in (('accepted', 'schema_version identity task_id request_id diagnostic'),
                         ('result', 'schema_version identity task_id candidates')):
        path = folder/(name+'.json')
        if name == 'result' and not require_result and not path.exists():
            continue  # Recover by querying the accepted task, even after its input URLs expire.
        value = images._read(path)
        object_fields(value, fields.split(), 'completed reference '+name)
        if type(value['schema_version']) is not int or value['schema_version'] != 2 or value['identity'] != identity:
            raise ProductionRefused('completed reference evidence schema or identity differs')
        records[name] = value
    task_id = records['accepted']['task_id']
    if not isinstance(task_id, str) or re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', task_id) is None:
        raise ProductionRefused('completed reference original task differs')
    result = records.get('result')
    if result is not None and (result['task_id'] != task_id
            or not isinstance(result['candidates'], list) or not result['candidates']):
        raise ProductionRefused('completed reference original task/result differs')


def _committed(frozen, scene, bible, plan):
    run = images._run(frozen)
    from ._scene_revision_origins import inherited
    imported = inherited(frozen,'plan','all')
    if imported is not None:
        images._equal(bible,imported['bible'],'inherited reference bible')
        images._equal(plan,imported['scene_plan'],'inherited reference plan')
        images._equal(scene,next((s for s in plan['scenes'] if s['scene_id']==scene['scene_id']),None),'inherited reference scene')
        return run
    commit = images._read(run/'production/scene-plan-commit.json')
    fields = ('schema_version run_id source_sha256 units_sha256 timeline_sha256 settings '
              'visual_bible_sha256 scene_plan_sha256').split()
    object_fields(commit, fields, 'reference scene plan commit')
    expected_commit = {k: plan[k] for k in fields if k != 'scene_plan_sha256'}
    expected_commit.update(schema_version=2, run_id=run.name,
        source_sha256=frozen.options['execution_policy']['input_identities']['script']['sha256'],
        scene_plan_sha256=canonical_digest(plan))
    images._equal(commit, expected_commit, 'reference scene plan commit')
    images._equal(images._read(run/'production/scene-plan.json'), plan, 'reference committed plan')
    images._equal(images._read(run/'production/visual-bible.json'), bible, 'reference committed bible')
    images._equal(commit['scene_plan_sha256'], canonical_digest(plan), 'reference plan commit')
    images._equal(commit['visual_bible_sha256'], canonical_digest(bible), 'reference bible commit')
    expected = next((s for s in plan['scenes'] if s['scene_id'] == scene['scene_id']), None)
    images._equal(scene, expected, 'reference scene')
    return run


def resolve_reference_bindings(frozen, bible, plan, scene, accepted_batches):
    """Return (candidate, uses) in Bible order, merging identical originals."""
    run = _committed(frozen, scene, bible, plan)
    choices = images._choices(accepted_batches)
    declared = {}
    for binding in scene['reference_bindings']:
        for use in binding['uses']:
            key = (use['kind'], use['id'])
            if key in declared: raise ProductionRefused('duplicate reference baseline use')
            declared[key] = binding['source_scene_id']
    rows = []; by_original = {}; found = set(); verified = {}
    scenes = {s['scene_id']: s for s in plan['scenes']}
    for baseline in bible['baselines']:
        key = (baseline['kind'], baseline['id'])
        if key not in declared: continue
        sid = baseline['scene_id']; found.add(key)
        if declared[key] != sid or sid not in choices:
            raise ProductionRefused('reference baseline lacks exact accepted original')
        if sid not in verified:
            _, candidates = images._candidates(frozen, scenes[sid], run/'production/jimeng'/sid/'candidates.json')
            choice = choices[sid]
            candidate = next((c for c in candidates if c['candidate_id'] == choice['candidate_id']), None)
            if candidate is None: raise ProductionRefused('accepted reference original missing')
            images._equal(choice, dict(scene_id=sid, **{k: candidate[k] for k in images.ACCEPTED_CHOICE_FIELDS
                                                       if k != 'scene_id'}), 'accepted reference original')
            verified[sid] = candidate
        candidate = verified[sid]
        identity = (sid, candidate['candidate_id'], candidate['sha256'])
        if identity not in by_original:
            by_original[identity] = len(rows)
            rows.append((dict(candidate, scene_id=sid), []))
        rows[by_original[identity]][1].append(dict(kind=key[0], id=key[1]))
    if found != set(declared): raise ProductionRefused('unknown reference baseline use')
    return rows


def _prior(frozen, bible, plan, scene):
    index = next((i for i, ids in enumerate(plan['batches'], 1) if scene['scene_id'] in ids), None)
    if index is None: raise ProductionRefused('reference scene has no committed batch')
    return images._load_accepted(frozen, None, None, bible, plan, before=index)


def _format(value):
    return {'mjpeg': 'jpeg', 'jpg': 'jpeg'}.get(value, value)


def _object(frozen, candidate, record, storage, accepted_sources):
    object_fields(record, OBJECT_FIELDS, 'reference object')
    run = images._run(frozen)
    expected = dict(bucket=storage['bucket'], region=storage['region'], endpoint=storage['endpoint'],
        key=storage['key_prefix']+'/'+run.name+'/'+candidate['sha256']+'.original',
        bytes=candidate['bytes'], sha256=candidate['sha256'], content_type='image/'+_format(candidate['format']))
    images._equal({k: record[k] for k in expected}, expected, 'reference object identity')
    images._nonempty(record['etag'], 'reference object etag')
    folder = run/'production/reference-storage'/candidate['sha256']
    intent = images._read(folder/'intent.json')
    object_fields(intent, 'schema_version run_id object source created_at'.split(), 'object upload intent')
    timestamp(intent['created_at'])
    source = intent['source']
    object_fields(source, 'path bytes sha256'.split(), 'object upload source')
    source_path = images.run_path(run, source['path'])
    if not any(source == {k: selected[k] for k in ('path', 'bytes', 'sha256')}
               for selected in accepted_sources):
        raise ProductionRefused('object upload source is not a previously accepted original')
    from ._scene_revision_origin_images import source_image_required
    required=source_image_required(frozen,candidate['scene_id'])
    fresh = images.hash_file(source_path) if required else None
    if (source['bytes'], source['sha256']) != (candidate['bytes'], candidate['sha256']) or (required and (
            fresh.bytes, fresh.sha256) != (source['bytes'], source['sha256'])):
        raise ProductionRefused('object upload source original identity differs')
    images._equal(intent, dict(schema_version=2, run_id=run.name, object=expected,
        source=source, created_at=intent['created_at']), 'object upload intent')
    receipt = images._read(folder/'object.json')
    object_fields(receipt, 'schema_version run_id intent_sha256 object verified_at'.split(), 'object receipt')
    timestamp(receipt['verified_at'])
    images._equal(receipt, dict(schema_version=2, run_id=run.name, intent_sha256=canonical_digest(intent),
                               object=record, verified_at=receipt['verified_at']), 'reference object receipt')


def validate_reference_inputs(frozen, scene, bible, plan, references, settings):
    """Local preflight, including source decode and capability; performs no I/O to cloud."""
    _committed(frozen, scene, bible, plan)
    images._equal(settings, load_reference_settings(frozen), 'bound reference settings')
    model = parse_image_generation(settings['model_settings'], 'reference_generation')
    cap = parse_capability(settings['capability'], req_key=model.req_key)
    storage = parse_reference_storage(settings['storage']); require_url_budget(model, storage)
    prior = _prior(frozen, bible, plan, scene)
    resolved = resolve_reference_bindings(frozen, bible, plan, scene, prior)
    accepted_sources = [row for batch in prior for row in batch['selections']]
    if not isinstance(references, list) or not resolved or len(references) != len(resolved):
        raise ProductionRefused('reference input original coverage differs')
    if len(references) > cap['max_images']: raise ProductionRefused('reference image count exceeds capability')
    for row, (candidate, uses) in zip(references, resolved):
        object_fields(row, REFERENCE_FIELDS, 'reference input')
        expected = {k: candidate[k] for k in REFERENCE_FIELDS if k not in ('uses', 'object')}
        expected.update(uses=uses, object=row['object'])
        images._equal(row, expected, 'reference source and uses')
        if (_format(row['format']) not in cap['formats'] or row['bytes'] > cap['max_image_bytes']
                or not cap['min_width'] <= row['width'] <= cap['max_width']
                or not cap['min_height'] <= row['height'] <= cap['max_height']):
            raise ProductionRefused('reference image exceeds verified model capability')
        _object(frozen, candidate, row['object'], storage, accepted_sources)
    prompt = resolve_reference_prompt(frozen, scene, bible, cap)
    if len(prompt.encode('utf-8')) > cap['max_prompt_bytes']:
        raise ProductionRefused('reference prompt exceeds verified capability')
    return model, prompt


def reference_requests(frozen, scene, prompt, references, model):
    return [dict(schema_version=2, run_id=frozen.options['run_id'], scene_id=scene['scene_id'],
        request_id=f'request_{i:02d}', prompt=prompt, image_generation=thaw(model), reference_inputs=deepcopy(references))
        for i in range(1, model.candidates_per_scene+1)]


def validate_reference_intent(value, request, settings):
    object_fields(value, INTENT_FIELDS, 'reference submission intent')
    for key in ('schema_version', 'run_id', 'scene_id', 'request_id'):
        images._equal(value[key], request[key], 'reference submission '+key)
    images._equal(value['logical_request_sha256'], canonical_digest(request), 'reference logical request')
    images._sha(value['submit_body_sha256']); timestamp(value['created_at'])
    urls = value['reference_urls']
    if not isinstance(urls, list) or len(urls) != len(request['reference_inputs']):
        raise ProductionRefused('reference URL evidence ordering/coverage differs')
    model = parse_image_generation(settings['model_settings'], 'reference_generation')
    needed = require_url_budget(model, settings['storage'])
    created = datetime.fromisoformat(value['created_at'])
    for row in urls:
        object_fields(row, 'sha256 issued_at expires_at'.split(), 'reference URL evidence')
        images._sha(row['sha256']); timestamp(row['issued_at']); timestamp(row['expires_at'])
        issued, expires = (datetime.fromisoformat(row[k]) for k in ('issued_at', 'expires_at'))
        if created < issued or (expires-created).total_seconds() < needed:
            raise ProductionRefused('reference submission URL lifetime evidence is insufficient')


def submit_evidence(request, intent):
    """Independent immutable anchor for the URL/body evidence in an intent."""
    return dict(schema_version=2, run_id=request['run_id'], scene_id=request['scene_id'],
        request_id=request['request_id'], logical_request_sha256=canonical_digest(request),
        intent_sha256=canonical_digest(intent))


def validate_submit_evidence(folder, request, intent):
    actual = images._read(folder/'submit-evidence.json')
    expected = submit_evidence(request, intent)
    object_fields(actual, expected.keys(), 'reference submit evidence')
    images._equal(actual, expected, 'reference submit evidence')


def verify_reference_provenance(frozen, scene, bible, plan):
    from ._scene_revision_readers import proof_for
    proof = proof_for(frozen,'image',scene['scene_id'])
    if proof is not None:
        from .production_inputs import load_frozen_inputs
        from ._scene_revision_origins import common
        from ..planning.production_timeline import ProductionTimeline
        source = load_frozen_inputs(proof['source_run']); prefix = common(source)
        old_bible,old_plan = images.load_committed_plan(source,prefix['units'],ProductionTimeline.from_dict(prefix['timeline']))
        old_scene = next(s for s in old_plan['scenes'] if s['scene_id']==scene['scene_id'])
        provenance = verify_reference_provenance(source,old_scene,old_bible,old_plan)
        proof['guard'].verify_captured_bytes()
        return provenance
    run = _committed(frozen, scene, bible, plan)
    provenance = images._read(run/'production/reference-images'/scene['scene_id']/'provenance.json')
    object_fields(provenance, PROVENANCE_FIELDS, 'reference provenance')
    settings = load_reference_settings(frozen)
    model, prompt = validate_reference_inputs(frozen, scene, bible, plan, provenance['references'], settings)
    requests = reference_requests(frozen, scene, prompt, provenance['references'], model)
    expected = dict(schema_version=2, production_strategy=STRATEGY, run_id=run.name, scene_id=scene['scene_id'],
        scene_plan_sha256=canonical_digest(plan), visual_bible_sha256=canonical_digest(bible),
        model_settings=thaw(model), capability_sha256=settings['capability_sha256'],
        prompt_sha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest(), references=provenance['references'],
        requests=[dict(request_id=r['request_id'], logical_request_sha256=canonical_digest(r)) for r in requests])
    images._equal(provenance, expected, 'reference provenance')
    for request in requests:
        folder = run/'production/jimeng'/scene['scene_id']/request['request_id']
        images._equal(images._read(folder/'request.json'), request, 'reference logical request')
        intent = images._read(folder/'intent.json')
        validate_reference_intent(intent, request, settings)
        validate_submit_evidence(folder, request, intent)
    return provenance


def reference_candidates(frozen, scene, manifest_path):
    from ._scene_revision_origins import inherited
    if inherited(frozen,'image',scene['scene_id']) is not None:
        return images._candidates(frozen,scene,manifest_path)
    run = images._run(frozen)
    imported=inherited(frozen,'plan','all')
    if imported is not None:bible,plan=imported['bible'],imported['scene_plan']
    else:bible, plan = (images._read(run/'production'/name) for name in ('visual-bible.json', 'scene-plan.json'))
    provenance = verify_reference_provenance(frozen, scene, bible, plan)
    settings = load_reference_settings(frozen)
    model = parse_image_generation(settings['model_settings'], 'reference_generation')
    requests = reference_requests(frozen, scene, resolve_reference_prompt(frozen, scene, bible, settings['capability']), provenance['references'], model)
    return images._candidates(frozen, scene, manifest_path, _reference=(model, requests, settings))


def build_reference_image_acceptance(frozen, units, timeline):
    complete = images.require_complete_image_acceptance(frozen, units, timeline)
    bible, plan = images.load_committed_plan(frozen, units, timeline)
    choices = {r['scene_id']: r for r in complete['selections']}; rows = []
    for scene in plan['scenes']:
        sid = scene['scene_id']; provenance_sha = None; bindings = []
        if scene['reference_bindings']:
            provenance = verify_reference_provenance(frozen, scene, bible, plan)
            provenance_sha = canonical_digest(provenance)
            # Recheck all result/download/original metadata, including this selection.
            _, candidates = reference_candidates(frozen, scene, images._run(frozen)/'production/jimeng'/sid/'candidates.json')
            choice = choices[sid]
            candidate = next((c for c in candidates if c['candidate_id'] == choice['candidate_id']), None)
            if candidate is None or candidate['sha256'] != choice['sha256']:
                raise ProductionRefused('Wan selected reference candidate differs')
            for ref in provenance['references']:
                for use in ref['uses']:
                    bindings.append(dict(use, scene_id=ref['scene_id'], candidate_id=ref['candidate_id'], sha256=ref['sha256']))
            order = {(b['kind'], b['id']): i for i, b in enumerate(bible['baselines'])}
            bindings.sort(key=lambda b: order[(b['kind'], b['id'])])
        rows.append(dict(choices[sid], unit_ids=deepcopy(scene['unit_ids']), baseline_bindings=bindings,
                         reference_provenance_sha256=provenance_sha))
    return dict(schema_version=2, production_strategy=STRATEGY, run_id=frozen.options['run_id'],
        scene_plan_sha256=canonical_digest(plan), visual_bible_sha256=canonical_digest(bible),
        complete_acceptance_sha256=canonical_digest(complete), scenes=rows)


def require_reference_image_acceptance(frozen, units, timeline):
    expected = build_reference_image_acceptance(frozen, units, timeline)
    actual = images._read(images._run(frozen)/'production/reference-images/wan-inputs.json')
    images._equal(actual, expected, 'Wan start-image admission')
    return actual
