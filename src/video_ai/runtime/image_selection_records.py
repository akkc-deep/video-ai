"""Read-only, strict version-2 image selection and admission records.

These validators never generate images, infer an observation, or persist data.
JSON identities use canonical JSON; originals and submissions use raw bytes.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import subprocess

from ..config import parse_scene_planning, read_json
from ..adapters.common import strict_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest, validate_scene_plan
from .manifest import hash_file, thaw, validate_run_dir
from .production_inputs import _same_json, load_frozen_inputs
from .execution_limits import command_timeout
from .production_state import ProductionRefused, integer, object_fields, run_path, timestamp


CANDIDATE_FIELDS = 'candidate_id request_id task_id req_key path bytes sha256 width height format'.split()
CHOICE_FIELDS = 'scene_id candidate_id sha256'.split()
ACCEPTED_CHOICE_FIELDS = CHOICE_FIELDS + 'path bytes req_key request_id task_id'.split()
BATCH_FIELDS = ('schema_version production_strategy run_id batch_id batch_index source_sha256 units_sha256 '
                'timeline_sha256 scene_plan_sha256 visual_bible_sha256 baseline_bindings scenes delivery').split()
SELECTION_FIELDS = ('schema_version run_id batch_id scene_manifest_sha256 scene_plan_sha256 '
                    'visual_bible_sha256 baseline_bindings intent selections observation').split()
ACCEPTED_FIELDS = ('schema_version production_strategy run_id batch_id scene_manifest_sha256 scene_plan_sha256 '
                   'visual_bible_sha256 selections baseline_bindings source_submission_sha256').split()
COMPLETE_FIELDS = ('schema_version production_strategy run_id scene_plan_sha256 visual_bible_sha256 '
                   'accepted_batches selections baseline_bindings observation observation_submission_sha256').split()


def _equal(left, right, label):
    if canonical_digest(left) != canonical_digest(right):
        raise ProductionRefused(label+' identity differs')


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ProductionRefused('expected lowercase SHA256')
    return value


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ProductionRefused(label+': expected nonempty string')


def _read(path):
    try:
        return read_json(path)
    except (OSError, ValueError) as exc:
        raise ProductionRefused('required image selection record unavailable: '+str(path)) from exc


def _run(frozen):
    run = validate_run_dir(Path(frozen.options['script_path']).parent.parent)
    if frozen.options['run_id'] != run.name or frozen.config.production_strategy != STRATEGY:
        raise ProductionRefused('image selection frozen run/strategy differs')
    if not _same_json(load_frozen_inputs(run), frozen):
        raise ProductionRefused('image selection frozen inputs differ')
    return run


def batch_directory(frozen, batch_id):
    if not isinstance(batch_id, str) or not re.fullmatch(r'image_batch_[0-9]{4,}', batch_id):
        raise ProductionRefused('safe image batch ID required')
    return run_path(_run(frozen), _run(frozen)/'production/image-selection'/batch_id)


def load_committed_plan(frozen, units, timeline):
    """Require all three JIM-02 outputs, then rederive the committed plan."""
    from ._scene_revision_origins import inherited,run_of
    inherited_plan = inherited(frozen,'plan','all')
    if inherited_plan is not None:
        run = run_of(frozen)
        if any((run/'production'/name).exists() for name in ('visual-bible.json','scene-plan.json','scene-plan-commit.json')):
            raise ProductionRefused('owned scene plan competes with revision import')
        prefix = inherited(frozen,'common','all')
        if prefix is None or canonical_digest(units)!=canonical_digest(prefix['units']) or canonical_digest(timeline.as_dict())!=canonical_digest(prefix['timeline']):
            raise ProductionRefused('inherited scene plan common inputs differ')
        return inherited_plan['bible'],inherited_plan['scene_plan']
    run = _run(frozen); folder = run/'production'
    bible = _read(folder/'visual-bible.json'); plan = _read(folder/'scene-plan.json')
    commit = _read(folder/'scene-plan-commit.json')
    fields = 'schema_version run_id source_sha256 units_sha256 timeline_sha256 settings visual_bible_sha256 scene_plan_sha256'.split()
    object_fields(commit, fields, 'scene plan commit')
    if not isinstance(units, dict) or 'run_id' in units or 'source_sha256' in units:
        raise ProductionRefused('units cannot override frozen scene identities')
    source = frozen.options['execution_policy']['input_identities']['script']['sha256']
    raw = (b'\xef\xbb\xbf' if frozen.script.has_bom else b'')+frozen.script.text.encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != source:
        raise ProductionRefused('frozen original script SHA256 differs')
    try:
        settings = parse_scene_planning(commit['settings'])
        expected = dict(schema_version=2, run_id=run.name, source_sha256=source,
            units_sha256=canonical_digest(units), timeline_sha256=canonical_digest(timeline.as_dict()),
            settings=asdict(settings), visual_bible_sha256=canonical_digest(bible),
            scene_plan_sha256=canonical_digest(plan))
        _equal(commit, expected, 'scene plan commit')
        explicit = thaw(frozen.config.raw.get('scene_planning'))
        if explicit is not None:
            for key, value in explicit.items(): _equal(value, commit['settings'][key], 'frozen scene settings')
        validate_scene_plan(frozen.script, dict(units, run_id=run.name, source_sha256=source),
                            timeline, bible, plan, settings=settings)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ProductionRefused('invalid committed scene plan structure') from exc
    return bible, plan


def _inspect_original(frozen, path):
    """Full local decode with bounded commands and no log or media writes."""
    from .scene_revision_records import _context
    scope=_context.get();cache=None;cache_key=None
    if scope is not None:
        from .production_state import ArtifactStamp
        try:
            before=hash_file(path)
            tools=tuple((str(frozen.config.tools[k]),tuple(ArtifactStamp.read(frozen.config.tools[k]).to_dict().values()))
                        for k in ('ffmpeg','ffprobe'))
        except OSError as exc:raise ProductionRefused('original image decode unavailable') from exc
        cache=scope.setdefault('image_decode_cache',{})
        cache_key=(before.bytes,before.sha256,tools)
        if cache_key in cache:return deepcopy(cache[cache_key])
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    def execute(args):
        try:
            result = subprocess.run([str(arg) for arg in args], stdin=subprocess.DEVNULL,
                capture_output=True, timeout=command_timeout(60), check=False, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProductionRefused('original image decode unavailable') from exc
        if result.returncode:
            raise ProductionRefused('original image cannot be completely decoded')
        return result.stdout
    try:
        data = json.loads(execute((frozen.config.tools['ffprobe'], '-v', 'error', '-count_frames',
            '-show_streams', '-of', 'json', path)))
        streams = data['streams']
        if len(streams) != 1: raise ValueError()
        stream = streams[0]
        if stream.get('codec_type') != 'video' or stream.get('nb_read_frames') != '1': raise ValueError()
        if stream.get('codec_name') not in {'png','mjpeg','webp','bmp','tiff','gif','jpeg2000','targa','ppm','pgm'}:
            raise ValueError()
        for field in ('width', 'height'): integer(stream.get(field), 'decoded '+field, 1)
        execute((frozen.config.tools['ffmpeg'], '-nostdin', '-v', 'error', '-xerror', '-i', path, '-f', 'null', '-'))
        value=dict(width=stream['width'], height=stream['height'], format=stream['codec_name'])
        if cache is not None:
            after=hash_file(path)
            if (after.bytes,after.sha256)!=(before.bytes,before.sha256):raise ProductionRefused('original changed during decode')
            cache[cache_key]=deepcopy(value)
        return value
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionRefused('invalid original still image') from exc


def _bound(path, fields, identity):
    value = _read(path); object_fields(value, fields, 'Jimeng backing record')
    if type(value['schema_version']) is not int or value['schema_version'] != 2 or value['identity'] != identity:
        raise ProductionRefused('Jimeng backing record schema/identity differs')
    return value


def _candidates(frozen, scene, manifest_path, *, _reference=None):
    from ._scene_revision_origins import inherited,run_of
    imported = inherited(frozen,'image',scene['scene_id'])
    if imported is not None:
        from .scene_revision_records import require_scene_revision
        proof = require_scene_revision(frozen)
        sidecar,_ = proof['imports']['image:'+scene['scene_id']]
        run = run_of(frozen)
        canonical = run/'production/jimeng'/scene['scene_id']/'candidates.json'
        if Path(manifest_path) not in (canonical,Path(sidecar['view_artifact']['path'])):
            raise ProductionRefused('candidate path is not the registered inherited view')
        if canonical.parent.exists() and any(canonical.parent.iterdir()): raise ProductionRefused('owned image competes with import')
        return deepcopy(sidecar['view_artifact']),imported['candidates']
    from ._scene_revision_origin_images import source_candidate_metadata
    metadata=source_candidate_metadata(frozen,scene,manifest_path)
    if metadata is not None:return metadata
    run = _run(frozen); settings = frozen.config.image_generation
    folder = run/'production/jimeng'/scene['scene_id']
    expected_path = run_path(run, folder/'candidates.json')
    if run_path(run, manifest_path) != expected_path:
        raise ProductionRefused('candidate manifest is outside exact scene path')
    stamp = hash_file(expected_path); manifest = _read(expected_path)
    object_fields(manifest, 'schema_version run_id scene_id identity candidates'.split(), 'candidate manifest')
    requests = [dict(schema_version=2, run_id=run.name, scene_id=scene['scene_id'], request_id=f'request_{i:02d}',
                     prompt=scene['image_prompt'], image_generation=thaw(settings))
                for i in range(1, settings.candidates_per_scene+1)]
    first_request = folder/'request_01/request.json'
    if _reference is None and first_request.exists() and 'reference_inputs' in _read(first_request):
        from .reference_image_records import reference_candidates
        return reference_candidates(frozen, scene, manifest_path)
    if _reference is not None:
        settings, requests, reference_settings = _reference
    combined = []
    for request in requests:
        rid = request['request_id']; directory = folder/rid; identity = canonical_digest(request)
        _equal(_read(directory/'request.json'), request, 'original image request')
        if _reference is not None:
            from .reference_image_records import validate_reference_intent
            validate_reference_intent(_read(directory/'intent.json'), request, reference_settings)
        else:
            intent = _bound(directory/'intent.json', 'schema_version identity created_at state'.split(), identity)
            timestamp(intent['created_at'])
            if intent['state'] != 'intent': raise ProductionRefused('invalid Jimeng submission intent')
        accepted = _bound(directory/'accepted.json', 'schema_version identity task_id request_id diagnostic'.split(), identity)
        task = accepted['task_id']
        if not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', task):
            raise ProductionRefused('invalid Jimeng task identity')
        _nonempty(accepted['request_id'], 'official request ID')
        if not isinstance(accepted['diagnostic'], dict): raise ProductionRefused('invalid official diagnostic')
        result = _bound(directory/'result.json', 'schema_version identity task_id candidates'.split(), identity)
        if result['task_id'] != task or not isinstance(result['candidates'], list) or not result['candidates']:
            raise ProductionRefused('invalid candidate result/task identity')
        outputs = _bound(directory/'outputs.json', 'schema_version identity sources'.split(), identity)
        if not isinstance(outputs['sources'], list) or len(outputs['sources']) != len(result['candidates']):
            raise ProductionRefused('original candidate output ordering differs')
        for sha in outputs['sources']: _sha(sha)
        for index, candidate in enumerate(result['candidates'], 1):
            object_fields(candidate, CANDIDATE_FIELDS, 'candidate')
            cid = f'{rid}_image_{index:02d}'; original = run_path(run, directory/(cid+'.original'))
            expected = dict(candidate, candidate_id=cid, request_id=rid, task_id=task,
                            req_key=settings.req_key, path=str(original))
            _equal(candidate, expected, 'candidate model/task/path')
            for key in ('bytes','width','height'): integer(candidate[key], 'candidate '+key, 1)
            _sha(candidate['sha256']); _nonempty(candidate['format'], 'candidate format')
            fresh = hash_file(original)
            if (candidate['bytes'], candidate['sha256']) != (fresh.bytes, fresh.sha256):
                raise ProductionRefused('original candidate SHA256 differs')
            receipt = _bound(directory/(cid+'.download.json'), 'schema_version identity candidate_id bytes sha256'.split(), identity)
            _equal(receipt, dict(schema_version=2, identity=identity, candidate_id=cid, bytes=fresh.bytes, sha256=fresh.sha256), 'download receipt')
            _equal(_read(directory/(cid+'.json')), candidate, 'candidate metadata')
            info = _inspect_original(frozen, original)
            _equal(info, {k: candidate[k] for k in ('width','height','format')}, 'decoded original')
            if (candidate['width'], candidate['height']) != (settings.output_width, settings.output_height):
                raise ProductionRefused('original dimensions differ from frozen model')
            after = hash_file(original)
            if (fresh.bytes, fresh.sha256) != (after.bytes, after.sha256):
                raise ProductionRefused('original changed during decoding')
            combined.append(candidate)
    _equal(manifest, dict(schema_version=2, run_id=run.name, scene_id=scene['scene_id'],
                         identity=canonical_digest(requests), candidates=combined), 'candidate manifest')
    after = hash_file(expected_path)
    if (stamp.bytes, stamp.sha256) != (after.bytes, after.sha256):
        raise ProductionRefused('candidate manifest changed during validation')
    return dict(path=str(expected_path), bytes=stamp.bytes, sha256=stamp.sha256), deepcopy(combined)


def _choices(accepted_batches):
    result = {}
    for accepted in accepted_batches:
        for choice in accepted['selections']:
            sid = choice['scene_id']
            if sid in result: raise ProductionRefused('duplicate accepted scene identity')
            result[sid] = choice
    return result


def _baselines(bible, choices, uses=None):
    return [dict(row, candidate_id=choices[row['scene_id']]['candidate_id'], sha256=choices[row['scene_id']]['sha256'])
            for row in bible['baselines'] if row['scene_id'] in choices
            and (uses is None or (row['kind'], row['id']) in uses)]


def _expected_batch(frozen, units, timeline, bible, plan, manifests, index, accepted):
    integer(index, 'batch index', 1)
    if index > len(plan['batches']): raise ProductionRefused('batch index outside committed plan')
    ids = plan['batches'][index-1]
    if not isinstance(manifests, (list, tuple)) or len(manifests) != len(ids):
        raise ProductionRefused('candidate scene coverage differs from batch')
    choices = _choices(accepted); rows = []; dependencies = set(); uses = set()
    scenes = {s['scene_id']: s for s in plan['scenes']}
    for sid, manifest in zip(ids, manifests):
        scene = scenes[sid]
        for reference in scene['reference_bindings']:
            uses.update((use['kind'],use['id']) for use in reference['uses'])
            dependency = reference['source_scene_id']
            if dependency not in choices: raise ProductionRefused('required earlier baseline has no accepted original')
            if dependency not in dependencies:
                _, baseline_candidates = _candidates(frozen, scenes[dependency],
                    _run(frozen)/'production/jimeng'/dependency/'candidates.json')
                chosen = choices[dependency]
                candidate = next((c for c in baseline_candidates if c['candidate_id'] == chosen['candidate_id']), None)
                if candidate is None: raise ProductionRefused('accepted baseline candidate no longer exists')
                expected_choice = dict(scene_id=dependency, **{k: candidate[k] for k in ACCEPTED_CHOICE_FIELDS if k != 'scene_id'})
                _equal(chosen, expected_choice, 'accepted baseline original')
            dependencies.add(dependency)
        identity, candidates = _candidates(frozen, scene, manifest)
        row = {k: deepcopy(scene[k]) for k in ('scene_id','summary','unit_ids','text_start','text_end','reference_bindings')}
        row.update(original_text=frozen.script.text[scene['text_start']:scene['text_end']],
                   candidate_manifest=identity, candidates=candidates)
        rows.append(row)
    from ..selection_config import parse_selection_email
    settings = parse_selection_email(frozen.config.raw.get('selection_email'))
    return dict(schema_version=2, production_strategy=STRATEGY, run_id=frozen.options['run_id'],
        batch_id=f'image_batch_{index:04d}', batch_index=index, source_sha256=plan['source_sha256'],
        units_sha256=plan['units_sha256'], timeline_sha256=plan['timeline_sha256'],
        scene_plan_sha256=canonical_digest(plan), visual_bible_sha256=canonical_digest(bible),
        baseline_bindings=_baselines(bible, choices, uses), scenes=rows,
        delivery=dict(sender=settings.sender, recipient=settings.recipient, max_mime_bytes=settings.max_mime_bytes))


def build_batch(frozen, units, timeline, candidate_manifests, *, batch_index):
    bible, plan = load_committed_plan(frozen, units, timeline)
    accepted = _load_accepted(frozen, units, timeline, bible, plan, before=batch_index)
    return _expected_batch(frozen, units, timeline, bible, plan, candidate_manifests, batch_index, accepted)


def validate_batch(frozen, units, timeline, bible, plan, batch):
    committed = load_committed_plan(frozen, units, timeline)
    _equal([bible, plan], list(committed), 'supplied committed plan')
    object_fields(batch, BATCH_FIELDS, 'image batch')
    integer(batch['batch_index'], 'batch index', 1)
    accepted = _load_accepted(frozen, units, timeline, bible, plan, before=batch['batch_index'])
    manifests = [s['candidate_manifest']['path'] for s in batch['scenes']]
    _equal(batch, _expected_batch(frozen, units, timeline, bible, plan, manifests, batch['batch_index'], accepted), 'image batch')


def selection_template(batch):
    return dict(schema_version=2, run_id=batch['run_id'], batch_id=batch['batch_id'],
        scene_manifest_sha256=canonical_digest(batch), scene_plan_sha256=batch['scene_plan_sha256'],
        visual_bible_sha256=batch['visual_bible_sha256'], baseline_bindings=deepcopy(batch['baseline_bindings']),
        intent='draft', selections=[], observation=None)


def _choice_rows(rows):
    if not isinstance(rows, list): raise ProductionRefused('selection rows must be an array')
    result = {}
    for row in rows:
        object_fields(row, CHOICE_FIELDS, 'selection row')
        for key in CHOICE_FIELDS: _nonempty(row[key], key)
        _sha(row['sha256'])
        if row['scene_id'] in result: raise ProductionRefused('duplicate selected scene')
        result[row['scene_id']] = deepcopy(row)
    return result


def _observation(value, current, all_choices):
    if value is None: return None
    fields = 'scope review_method reviewer viewed_images subject_consistency style_consistency verdict issues reason'.split()
    object_fields(value, fields, 'image observation')
    if value['scope'] not in ('current_batch', 'all_selected_images'):
        raise ProductionRefused('invalid observation scope')
    if value['review_method'] not in ('human_image','agent_image'):
        raise ProductionRefused('observation requires actual image review')
    for key in ('reviewer','reason'): _nonempty(value[key], key)
    for key in ('subject_consistency','style_consistency','verdict'):
        if value[key] not in ('passed','failed','unverified'): raise ProductionRefused('invalid observation verdict')
    if not isinstance(value['issues'], list): raise ProductionRefused('observation issues must be an array')
    for issue in value['issues']: _nonempty(issue, 'observation issue')
    if value['verdict'] == 'passed' and (value['subject_consistency'] != 'passed'
            or value['style_consistency'] != 'passed' or value['issues']):
        raise ProductionRefused('passed observation has failed/unverified checks or issues')
    if value['verdict'] == 'failed' and not value['issues']:
        raise ProductionRefused('failed observation needs concrete issues')
    viewed = _choice_rows(value['viewed_images'])
    expected = current if value['scope'] == 'current_batch' else all_choices
    simple = {sid: {key: row[key] for key in CHOICE_FIELDS} for sid, row in expected.items()}
    _equal(viewed, simple, 'observation exact viewed image coverage')
    result = deepcopy(value)
    result['viewed_images'] = [viewed[sid] for sid in simple]
    return result


def validate_selection(frozen, bible, plan, batch, value, *, accepted_batches):
    object_fields(batch, BATCH_FIELDS, 'image batch')
    object_fields(value, SELECTION_FIELDS, 'image selection')
    if value['observation'] is not None and not isinstance(value['observation'], dict):
        raise ProductionRefused('image observation must be an object or null')
    template = selection_template(batch)
    for key in SELECTION_FIELDS:
        if key not in ('intent','selections','observation'): _equal(value[key], template[key], 'selection '+key)
    if value['intent'] not in ('draft','accept'): raise ProductionRefused('selection intent must be draft or accept')
    _equal(batch['scene_plan_sha256'], canonical_digest(plan), 'selection plan')
    _equal(batch['visual_bible_sha256'], canonical_digest(bible), 'selection bible')
    _equal(batch['run_id'], _run(frozen).name, 'selection run')
    integer(batch['batch_index'], 'batch index', 1)
    prior = [a for a in accepted_batches if a['batch_id'] != batch['batch_id']]
    manifests = [scene['candidate_manifest']['path'] for scene in batch['scenes']]
    expected = _expected_batch(frozen, None, None, bible, plan, manifests, batch['batch_index'], prior)
    _equal(batch, expected, 'selection batch')
    selected = _choice_rows(value['selections']); ids = [s['scene_id'] for s in batch['scenes']]
    if set(selected)-set(ids) or (value['intent'] == 'accept' and set(selected) != set(ids)):
        raise ProductionRefused('selection scene coverage differs from current batch')
    existing = _choices(accepted_batches)
    for scene in batch['scenes']:
        candidates = scene['candidates']
        sid = scene['scene_id']
        if sid in selected:
            choice = selected[sid]
            match = next((c for c in candidates if c['candidate_id'] == choice['candidate_id']), None)
            if match is None or match['sha256'] != choice['sha256']:
                raise ProductionRefused('unknown candidate or changed original SHA256')
            if sid in existing:
                _equal(choice, {k: existing[sid][k] for k in CHOICE_FIELDS}, 'immutable accepted selection')
            from ._scene_revision_origins import inherited
            imported = inherited(frozen,'choice',sid)
            if imported is not None:
                _equal(choice, {k: imported[k] for k in CHOICE_FIELDS}, 'immutable inherited selection')
    all_choices = dict(existing); all_choices.update(selected)
    ordered = {s['scene_id']: all_choices[s['scene_id']] for s in plan['scenes'] if s['scene_id'] in all_choices}
    current = {sid: selected[sid] for sid in ids if sid in selected}
    if value['observation'] is not None and value['observation'].get('scope') == 'all_selected_images':
        if len(ordered) != len(plan['scenes']): raise ProductionRefused('all selected images observation requires every scene')
    observation = _observation(value['observation'], current, ordered)
    return dict(selections=list(current.values()), observation=observation)


def build_accepted(batch, normalized, *, source_submission_sha256, bible, accepted_batches):
    _sha(source_submission_sha256)
    selected = _choice_rows(normalized['selections'])
    if set(selected) != {s['scene_id'] for s in batch['scenes']}:
        raise ProductionRefused('accepted batch requires exactly one choice per scene')
    enriched = []
    for scene in batch['scenes']:
        choice = selected[scene['scene_id']]
        candidate = next((row for row in scene['candidates'] if row['candidate_id'] == choice['candidate_id']), None)
        if candidate is None or candidate['sha256'] != choice['sha256']: raise ProductionRefused('invalid accepted candidate')
        enriched.append(dict(choice, **{k: candidate[k] for k in ('path','bytes','req_key','request_id','task_id')}))
    choices = _choices(accepted_batches)
    choices.update({row['scene_id']: row for row in enriched})
    return dict(schema_version=2, production_strategy=STRATEGY, run_id=batch['run_id'], batch_id=batch['batch_id'],
        scene_manifest_sha256=canonical_digest(batch), scene_plan_sha256=batch['scene_plan_sha256'],
        visual_bible_sha256=batch['visual_bible_sha256'], selections=enriched,
        baseline_bindings=_baselines(bible, choices), source_submission_sha256=source_submission_sha256)


def _submission(folder, sha):
    _sha(sha); path = folder/'submissions'/(sha+'.json')
    try: raw = path.read_bytes()
    except OSError as exc: raise ProductionRefused('accepted source submission missing') from exc
    if hashlib.sha256(raw).hexdigest() != sha: raise ProductionRefused('source submission SHA256 differs')
    try:
        value = strict_json(raw.removeprefix(b'\xef\xbb\xbf'))
        if not isinstance(value, dict): raise ValueError('submission object required')
        return value
    except (UnicodeError, ValueError) as exc:
        raise ProductionRefused('invalid original source submission JSON') from exc


def _load_accepted(frozen, units, timeline, bible, plan, *, before=None):
    run = _run(frozen); result = []; missing = False
    for index, ids in enumerate(plan['batches'], 1):
        if before is not None and index >= before: break
        folder = run/'production/image-selection'/f'image_batch_{index:04d}'
        path = folder/'accepted.json'
        if not path.exists():
            from ._scene_revision_readers import inherited_batch
            imported = inherited_batch(frozen,bible,plan,index,result)
            if imported is not None:
                if missing: raise ProductionRefused('inherited accepted batches contain a gap')
                result.append(imported); continue
            missing = True; continue
        if missing: raise ProductionRefused('accepted batches contain a gap')
        accepted = _read(path); object_fields(accepted, ACCEPTED_FIELDS, 'accepted image batch')
        batch = _read(folder/'batch.json'); object_fields(batch, BATCH_FIELDS, 'accepted image batch manifest')
        manifests = [scene['candidate_manifest']['path'] for scene in batch['scenes']]
        expected = _expected_batch(frozen, units, timeline, bible, plan, manifests, index, result)
        _equal(batch, expected, 'accepted batch manifest')
        value = _submission(folder, accepted['source_submission_sha256'])
        if value.get('intent') != 'accept': raise ProductionRefused('accepted source submission has no accept intent')
        normalized = validate_selection(frozen, bible, plan, batch, value, accepted_batches=result)
        rebuilt = build_accepted(batch, normalized, source_submission_sha256=accepted['source_submission_sha256'],
                                 bible=bible, accepted_batches=result)
        _equal(accepted, rebuilt, 'accepted image batch')
        # Transport backing is part of acceptance, including on disk re-entry.
        # The late import keeps the pure builders usable by the coordinator.
        from .production_image_selection import notification_delivery_state
        if notification_delivery_state(run, batch) != 'accepted':
            raise ProductionRefused('accepted image batch lacks complete SMTP receipts')
        result.append(accepted)
    root = run/'production/image-selection'
    expected_ids = {f'image_batch_{i:04d}' for i in range(1, len(plan['batches'])+1)}
    if root.exists():
        for path in root.glob('*/accepted.json'):
            if path.parent.name not in expected_ids: raise ProductionRefused('foreign accepted batch')
    return result


def load_accepted_batches(frozen, units, timeline, bible=None, plan=None):
    committed = load_committed_plan(frozen, units, timeline)
    if bible is not None: _equal(bible, committed[0], 'supplied visual bible')
    if plan is not None: _equal(plan, committed[1], 'supplied scene plan')
    return _load_accepted(frozen, units, timeline, *committed)


def build_complete_acceptance(frozen, bible, plan, accepted_batches, observation, *, observation_submission_sha256):
    _sha(observation_submission_sha256)
    choices = _choices(accepted_batches)
    if [b['batch_id'] for b in accepted_batches] != [f'image_batch_{i:04d}' for i in range(1,len(plan['batches'])+1)]:
        raise ProductionRefused('complete acceptance requires all accepted batches in order')
    if set(choices) != {s['scene_id'] for s in plan['scenes']}:
        raise ProductionRefused('complete acceptance requires every selected scene')
    ordered = {s['scene_id']: choices[s['scene_id']] for s in plan['scenes']}
    observation = _observation(observation, {}, ordered)
    if observation is None or observation['scope'] != 'all_selected_images' or observation['verdict'] != 'passed':
        raise ProductionRefused('complete acceptance requires explicit passed all selected images observation')
    return dict(schema_version=2, production_strategy=STRATEGY, run_id=frozen.options['run_id'],
        scene_plan_sha256=canonical_digest(plan), visual_bible_sha256=canonical_digest(bible),
        accepted_batches=[dict(batch_id=b['batch_id'], accepted_sha256=canonical_digest(b)) for b in accepted_batches],
        selections=list(ordered.values()), baseline_bindings=_baselines(bible, choices), observation=observation,
        observation_submission_sha256=observation_submission_sha256)


def require_complete_image_acceptance(frozen, units, timeline):
    bible, plan = load_committed_plan(frozen, units, timeline)
    from ._scene_revision_readers import inherited_image_group
    imported = inherited_image_group(frozen,units,timeline,bible,plan)
    if imported is not None:return imported
    run = _run(frozen); receipt = _read(run/'production/image-selection/complete-acceptance.json')
    object_fields(receipt, COMPLETE_FIELDS, 'complete image acceptance')
    accepted = _load_accepted(frozen, units, timeline, bible, plan)
    sha = _sha(receipt['observation_submission_sha256']); normalized = None
    for item in accepted:
        folder = run/'production/image-selection'/item['batch_id']
        if (folder/'submissions'/(sha+'.json')).exists():
            value = _submission(folder, sha)
            if value.get('intent') != 'accept': raise ProductionRefused('whole set observation requires accept intent')
            normalized = validate_selection(frozen, bible, plan, _read(folder/'batch.json'), value, accepted_batches=accepted)
            break
    if normalized is None: raise ProductionRefused('whole set observation source submission unavailable')
    expected = build_complete_acceptance(frozen, bible, plan, accepted, normalized['observation'],
                                         observation_submission_sha256=sha)
    _equal(receipt, expected, 'complete image acceptance')
    return receipt
