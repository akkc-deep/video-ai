"""Pure, immutable recovery decisions over freshly consumed evidence.

This module never reads files, contacts services or changes a manifest. The
runtime collector owns validation; a plan is a description, not authorization
to execute without another fresh collection.
"""
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

from ..runtime.manifest import FileIdentity, STAGES


def _freeze(value):
    if is_dataclass(value) and not isinstance(value, FileIdentity):
        return _freeze({f.name: getattr(value, f.name) for f in fields(value)})
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        raise ValueError('unordered inventory sets are not supported')
    return value


def _plain(value):
    if is_dataclass(value):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


_IDENTITY_KEYS = {'path', 'bytes', 'sha256', 'mtime_ns', 'verified_at'}


def _content(value, graph_roles=None, path=()):
    if graph_roles and path in graph_roles:
        role = graph_roles[path]
        # Only graph namespace fields can be replaced, never sampling inputs.
        if (len(path) < 3 or path[-2] != 'inputs' or
                path[-1] not in ('image', 'filename_prefix', 'output_prefix') or
                not isinstance(value, str) or not isinstance(role, str) or not role):
            raise ValueError('graph role must identify an input/output namespace field')
        return {'namespace_role': role}
    if isinstance(value, FileIdentity):
        value = _plain(value)
    elif is_dataclass(value):
        value = _plain(value)
    if isinstance(value, Mapping):
        if set(value) == _IDENTITY_KEYS:
            if (type(value['bytes']) is not int or value['bytes'] < 0 or
                    not isinstance(value['sha256'], str) or
                    not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
                raise ValueError('signature requires verified content identity')
            return {'bytes': value['bytes'], 'sha256': value['sha256']}
        return {k: _content(v, graph_roles, path+(k,)) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_content(v, graph_roles, path+(i,)) for i, v in enumerate(value)]
    if isinstance(value, Path):
        return str(value)
    return value


def signature(projection, *, graph_roles=None):
    """Hash all semantic fields; only identities and declared namespaces normalize.

    graph_roles maps exact tuple paths to stable role names, e.g.
    {('graph', '7', 'inputs', 'filename_prefix'): 'source_output'}. Callers
    must include the complete actual graph and pure plan in the projection.
    """
    roles = dict(graph_roles or {})
    normalized = _content(projection, roles)
    # Typos must not silently leave a caller's intended normalization unapplied.
    for path in roles:
        value = projection
        try:
            for part in path:
                value = value[part]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError('graph namespace role path does not exist') from exc
    raw = json.dumps(normalized, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ValidatedInventory:
    run_dir: Path
    snapshot: object
    config_projection: object
    input_identities: object
    stage_records: object
    unit_records: object
    checkpoints: object
    signatures: object
    submissions: object
    reviews: object

    def __post_init__(self):
        object.__setattr__(self, 'run_dir', Path(self.run_dir))
        for field in fields(self):
            if field.name != 'run_dir':
                object.__setattr__(self, field.name, _freeze(getattr(self, field.name)))
        if not isinstance(self.stage_records, Mapping) or set(self.stage_records) != set(STAGES):
            raise ValueError('inventory requires every fixed stage')
        object.__setattr__(self, 'stage_records', _freeze({s: self.stage_records[s] for s in STAGES}))


@dataclass(frozen=True)
class ChangedKey:
    field: str
    old_value: object
    new_value: object

    def __post_init__(self):
        object.__setattr__(self, 'old_value', _freeze(self.old_value))
        object.__setattr__(self, 'new_value', _freeze(self.new_value))


@dataclass(frozen=True)
class RecoveryItem:
    stage: str
    unit_id: str | None
    reason: str
    signature: str | None


@dataclass(frozen=True)
class RecoveryOperation:
    action: str
    stage: str
    unit_id: str | None
    source_identity: object
    required_review_roles: tuple[str, ...]

    def __post_init__(self):
        if self.action not in ('consume', 'prepare', 'finalize', 'wait', 'reconcile', 'derive', 'publish'):
            raise ValueError('unknown recovery action')
        if self.stage not in STAGES:
            raise ValueError('unknown recovery stage')
        object.__setattr__(self, 'source_identity', _freeze(self.source_identity))
        object.__setattr__(self, 'required_review_roles', tuple(self.required_review_roles))


@dataclass(frozen=True)
class RecoveryPlan:
    run_dir: Path
    parent_snapshot_identity: object
    input_identities: object
    changed_keys: tuple[ChangedKey, ...]
    invalidated: tuple[RecoveryItem, ...]
    reused: tuple[RecoveryItem, ...]
    operations: tuple[RecoveryOperation, ...]
    waiting_for: tuple[str, ...]
    requires_child_run: bool
    refusal_reasons: tuple[str, ...]

    def __post_init__(self):
        for name in ('parent_snapshot_identity', 'input_identities'):
            object.__setattr__(self, name, _freeze(getattr(self, name)))
        for name in ('changed_keys', 'invalidated', 'reused', 'operations', 'waiting_for', 'refusal_reasons'):
            object.__setattr__(self, name, tuple(getattr(self, name)))


_CHANGES_KEYS = frozenset(('schema_version', 'base_run_id', 'base_manifest_snapshot_identity',
    'created_at', 'reason', 'script_identity', 'unit_review_identity', 'config_identity', 'shot_changes'))


def _check_identity(value):
    value = _plain(value)
    if not isinstance(value, dict) or set(value) != _IDENTITY_KEYS:
        raise ValueError('changes require complete FileIdentity')
    for key in ('bytes', 'mtime_ns'):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError('changes require verified identity metadata')
    if not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ValueError('changes require verified SHA256')
    if not isinstance(value['path'], str) or not Path(value['path']).is_absolute():
        raise ValueError('changes require absolute identity path')
    stamp = datetime.fromisoformat(value['verified_at'])
    if stamp.tzinfo is None:
        raise ValueError('identity verification timestamp requires timezone')
    return value


def validate_changes(value, *, run_id, shot_ids, snapshot_identity=None, now=None):
    """Validate the exact author format without reading identities from disk.

    Runtime must freshly validate all identities and snapshot placement before
    applying this pure result. Extra keys cannot modify unit text or bindings.
    """
    value = _plain(value)
    if not isinstance(value, dict) or set(value) != _CHANGES_KEYS:
        raise ValueError('invalid changes fields')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('unsupported changes schema')
    if value['base_run_id'] != run_id:
        raise ValueError('changes base run mismatch')
    stamp = datetime.fromisoformat(value['created_at'])
    if stamp.tzinfo is None or (now is not None and stamp > now):
        raise ValueError('invalid changes creation timestamp')
    if not isinstance(value['reason'], str) or not value['reason'].strip():
        raise ValueError('changes reason required')
    for key in ('base_manifest_snapshot_identity', 'config_identity', 'script_identity', 'unit_review_identity'):
        if value[key] is None:
            if key not in ('script_identity', 'unit_review_identity'):
                raise ValueError('changes required identity missing')
        else:
            _check_identity(value[key])
    if snapshot_identity is not None:
        wanted = _plain(snapshot_identity)
        if any(value['base_manifest_snapshot_identity'][k] != wanted[k]
               for k in ('path','bytes','mtime_ns','sha256')):
            raise ValueError('changes manifest snapshot identity mismatch')
    rows = value['shot_changes']
    if not isinstance(rows, list):
        raise ValueError('shot_changes must be an ordered array')
    known, seen = set(shot_ids), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'shot_id', 'image_prompt', 'video_prompt', 'reason'}:
            raise ValueError('invalid shot change fields')
        if row['shot_id'] not in known or row['shot_id'] in seen:
            raise ValueError('unknown or duplicate shot change')
        seen.add(row['shot_id'])
        if not isinstance(row['reason'], str) or not row['reason'].strip():
            raise ValueError('shot change reason required')
        for key in ('image_prompt', 'video_prompt'):
            if row[key] is not None and (not isinstance(row[key], str) or not row[key].strip()):
                raise ValueError('prompt must be nonempty text or null')
        if row['image_prompt'] is None and row['video_prompt'] is None:
            raise ValueError('at least one repaired prompt required')
    return _freeze(value)


def _diff(old, new, prefix=''):
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        result = []
        for key in sorted(set(old) | set(new)):
            name = f'{prefix}.{key}' if prefix else key
            if key not in old or key not in new:
                result.append(ChangedKey(name, old.get(key), new.get(key)))
            else:
                result.extend(_diff(old[key], new[key], name))
        return result
    if old != new:
        return [ChangedKey(prefix, old, new)]
    return []


def _change_stage(field):
    parts = field.split('.')
    if field in ('voice.config_file', 'voice_config'):
        return None
    if parts[0] in ('services', 'timeouts', 'logs', 'logging', 'config_file',
                    'runtime_root', 'project_root', 'output_root', 'cache_root', 'schema_version'):
        return None
    if parts[0] in ('voice', 'speech', 'tts', 'script', 'segmentation', 'unit_review', 'voice_config'):
        return 'speech'
    if parts[0] == 'media':
        if len(parts) > 1 and parts[1] in ('timeline', 'fps', 'cue'):
            return 'timeline'
        if len(parts) > 1 and parts[1] == 'profile':
            return 'storyboard'
        return 'composition'
    if parts[0] in ('timeline', 'cue', 'timing'):
        return 'timeline'
    if parts[0] in ('global_visual', 'visual', 'subject_references', 'storyboard'):
        return 'storyboard'
    if parts[0] in ('models', 'workflows') and len(parts) > 1:
        if parts[1] == 'sdxl':
            return 'storyboard'
        if parts[1].startswith('wan') or parts[1] in ('text_encoder', 'vae'):
            return 'source_clips'
        if parts[1] == 'upscale':
            return 'upscale'
    if parts[0] == 'tools' and len(parts) > 1:
        if parts[1] in ('ffmpeg', 'ffprobe'):
            return 'speech'  # PCM is also made and consumed with these tools.
        if parts[1].startswith('tts'):
            return 'speech'
        if parts[1].startswith('ollama'):
            return 'storyboard'
        if parts[1].startswith('comfy'):
            return 'start_images'
    if parts[0] in ('composition', 'settings', 'subtitles', 'font', 'music', 'encoding', 'mix'):
        return 'composition'
    if parts[0] in ('reviews', 'final_review', 'full_film_acceptance'):
        return 'publish'
    # A complete validated projection can introduce a new semantic field. Do
    # not silently miss it; conservatively invalidate the full media chain.
    return 'speech'


def _stage_units(inventory, stage):
    return tuple(_unit_rows(inventory, stage))


def _unit_rows(inventory, stage):
    rows = inventory.unit_records.get(stage, {})
    result = dict(rows) if isinstance(rows, Mapping) else {r['unit_id']: r for r in rows}
    receipt = inventory.stage_records[stage].get('receipt', {})
    field = {'storyboard':'shots', 'start_images':'images', 'source_clips':'clips', 'upscale':'clips'}.get(stage)
    formal = receipt.get(field, ()) if field and isinstance(receipt, Mapping) else ()
    if isinstance(formal, Mapping):
        formal = tuple(dict(value, shot_id=key) for key, value in formal.items())
    for row in formal:
        uid = row['shot_id']
        # Frame granularity is kept when the collector provides native units.
        if stage == 'upscale' and any(key.startswith(uid+':frame_') for key in result):
            continue
        result[uid] = dict(result.get(uid, {}), **row)
        result[uid].setdefault('status', inventory.stage_records[stage].get('status'))
    if not result and stage in ('start_images', 'source_clips', 'upscale'):
        # A formal storyboard is the authoritative set for future pending work.
        result = {uid: {'shot_id':uid, 'status':'pending'} for uid in _stage_units(inventory, 'storyboard')}
    return result


def _shot_for_unit(uid, row):
    return row.get('shot_id', uid.split(':', 1)[0])


def _transition_review_peers(inventory, changed_shots):
    receipt = inventory.stage_records['composition'].get('receipt', {})
    if not isinstance(receipt, Mapping):
        return set()
    plan = receipt.get('plan', receipt.get('composition_plan', receipt))
    if not isinstance(plan, Mapping):
        return set()
    peer_edges = []
    for frame in plan.get('ordered_frame_map', plan.get('frame_mappings', ())):
        peers = {c['shot_id'] for c in frame.get('contributors', ()) if c.get('weight_numerator', 0) > 0}
        if len(peers) > 1:
            peer_edges.append(peers)
    affected = set(changed_shots)
    while True:
        grown = affected | set().union(*(edge for edge in peer_edges if edge & affected)) if peer_edges else affected
        if grown == affected:
            return affected - set(changed_shots)
        affected = grown


def _references(value, known):
    if isinstance(value, str):
        return {value} if value in known else set()
    if isinstance(value, Mapping):
        out = set()
        for key, val in value.items():
            if key in ('shot_id', 'source_shot_id', 'unit_id', 'source_unit_id', 'id',
                       'references', 'reference_shots', 'depends_on', 'context_sources',
                       'resolved_references', 'reference', 'reference_index', 'subject_references'):
                out.update(_references(val, known))
            elif key in ('visual_requirements', 'source_facts', 'facts', 'requirements'):
                out.update(_references(val, known))
        return out
    if isinstance(value, (list, tuple)):
        out = set()
        for item in value:
            out.update(_references(item, known))
        return out
    return set()


def _shared_closure(inventory, seeds):
    known = set(_stage_units(inventory, 'storyboard')) | set(_stage_units(inventory, 'start_images'))
    affected = set(seeds)
    dependencies = {}
    board = inventory.stage_records['storyboard'].get('receipt', {})
    board_rows = board.get('shots', ()) if isinstance(board, Mapping) else ()
    rows = dict(_unit_rows(inventory, 'storyboard'))
    if isinstance(board_rows, Mapping):
        rows.update(board_rows)
    else:
        rows.update({r['shot_id']: r for r in board_rows})
    primary = {}
    for uid, row in rows.items():
        if row.get('primary_unit_id'):
            primary.setdefault(row['primary_unit_id'], set()).add(uid)
    for stage in ('storyboard', 'start_images'):
        stage_rows = rows if stage == 'storyboard' else _unit_rows(inventory, stage)
        for uid, row in stage_rows.items():
            dependencies.setdefault(uid, set()).update(_references(row, known)-{uid})
            source_units = _references(row, set(primary))
            for source_unit in source_units:
                dependencies[uid].update(primary[source_unit]-{uid})
    images = inventory.stage_records['start_images'].get('receipt', {})
    if isinstance(images, Mapping):
        index = images.get('reference_index', images.get('references', ()))
        image_rows = images.get('images', {})
        if isinstance(image_rows, (tuple, list)):
            image_rows = {r['shot_id']: r for r in image_rows}
        if isinstance(index, Mapping):
            index = tuple(index.values())
        for reference in index:
            source = reference.get('reference_shot_id')
            entity = reference.get('entity_id')
            if source in known and entity:
                for uid, row in image_rows.items():
                    if entity in row.get('reference_entity_ids', ()):
                        dependencies.setdefault(uid, set()).add(source)
    while True:
        grown = affected | {uid for uid, refs in dependencies.items() if refs & affected}
        if grown == affected:
            return affected
        affected = grown


_FINAL_ROLES = ('final_review', 'full_film_acceptance')
_FINALIZE_ROLES = {'storyboard': ('storyboard',), 'start_images': ('start_images',),
                   'source_clips': ('source_clips',), 'upscale': ('upscale',)}
_PREPARE_ROLES = {'timeline': ('voice_acceptance',), 'storyboard': ('timing',)}
_INVALID_REVIEW_ROLES = {
    'speech': ('voice_acceptance',), 'timeline': ('timing',),
    'storyboard': ('storyboard', 'visual_contract'), 'start_images': ('start_images',),
    'source_clips': ('source_clips',), 'upscale': ('upscale',),
    'composition': _FINAL_ROLES, 'validation': _FINAL_ROLES,
}


def build_recovery_plan(inventory, *, config_projection=None, changes=None,
                        retry_failed=False, publish=False, reviews=None):
    """Describe ordered consumption and the first next action/checkpoint.

    Records, signatures, checkpoints and submissions are stage-keyed mappings;
    unit mappings preserve the collector's stable unit order. A running stage
    checkpoint may contain draft_complete=True only after its full draft was
    consumed. Unit reference fields carry explicit shared dependencies.
    """
    if not isinstance(inventory, ValidatedInventory):
        raise TypeError('planner requires ValidatedInventory')
    if type(retry_failed) is not bool or type(publish) is not bool:
        raise ValueError('recovery flags must be boolean')
    old = _content(inventory.config_projection)
    current = old if config_projection is None else _content(config_projection)
    changed = _diff(old, current)
    refusals, invalid, operations, waiting = [], {}, [], []
    review_set = dict(inventory.reviews)
    if reviews is not None:
        review_set.update(reviews)
    snapshot = inventory.snapshot
    parent_identity = snapshot.get('identity') if isinstance(snapshot, Mapping) else snapshot
    run_id = snapshot.get('run_id', inventory.run_dir.name) if isinstance(snapshot, Mapping) else inventory.run_dir.name

    def invalidate(stage, reason, units=None):
        for downstream in STAGES[STAGES.index(stage):]:
            if stage=='speech' and units is not None:
                scope=tuple(units) if downstream=='speech' else (None,)
            else:
                scope = (tuple(units) if units is not None and downstream in
                         ('storyboard', 'start_images', 'source_clips', 'upscale') else (None,))
            ordered = [u for u, row in _unit_rows(inventory, downstream).items()
                       if u in scope or _shot_for_unit(u, row) in scope]
            if scope == (None,):
                ordered = [None]
            for uid in ordered:
                invalid.setdefault((downstream, uid), reason)
            for role in _INVALID_REVIEW_ROLES.get(downstream, ()):
                review_set.pop(role, None)

    if reviews is not None:
        for role, new_review in reviews.items():
            previous = inventory.reviews.get(role)
            if previous is not None and _content(previous) != _content(new_review):
                changed.append(ChangedKey(f'reviews.{role}', _content(previous), _content(new_review)))
                if role == 'timing':
                    invalidate('timeline', 'changed timing/cue observations')
                else:
                    invalidate('publish', f'changed {role} observations')
                if role != 'full_film_acceptance':
                    review_set.pop('full_film_acceptance', None)
                # This is an explicit freshly consumed author record.
                review_set[role] = new_review

    if publish and (changes is not None or retry_failed):
        refusals.append('publish is incompatible with changes or retry_failed')
    if publish and any(inventory.stage_records[s].get('status') != 'completed' for s in STAGES[:-1]):
        refusals.append('publication requires freshly consumed validation and every completed upstream stage')
    parsed = None
    if changes is not None:
        try:
            # The runtime has consumed the author's exclusive snapshot. The
            # live manifest is independently guarded in inventory.snapshot.
            parent_identity = changes['base_manifest_snapshot_identity']
            parsed = validate_changes(changes, run_id=run_id,
                shot_ids=_stage_units(inventory, 'storyboard'), snapshot_identity=parent_identity)
        except (ValueError, TypeError) as exc:
            refusals.append(str(exc))
    for row in changed:
        if row.field.startswith('reviews.'):
            continue
        first = _change_stage(row.field)
        if first is not None:
            if parsed is None:
                refusals.append(f'explicit changes required for {row.field}')
            else:
                invalidate(first, f'changed {row.field}')
    if parsed is not None:
        for name, stage in (('script_identity', 'speech'), ('unit_review_identity', 'speech')):
            if parsed[name] is not None:
                previous = inventory.input_identities.get(name.removesuffix('_identity'))
                if _content(previous) != _content(parsed[name]):
                    changed.append(ChangedKey(name, _content(previous), _content(parsed[name])))
                    invalidate(stage, f'changed {name}')
        for row in parsed['shot_changes']:
            uid = row['shot_id']
            for name, first in (('image_prompt', 'start_images'), ('video_prompt', 'source_clips')):
                if row[name] is not None:
                    previous = _unit_rows(inventory, 'storyboard').get(uid, {}).get(name)
                    changed.append(ChangedKey(f'shots.{uid}.{name}', previous, row[name]))
                    affected = _shared_closure(inventory, {uid}) if name == 'image_prompt' else {uid}
                    invalidate(first, f'explicit {name} repair', affected)
                    for peer in _transition_review_peers(inventory, affected):
                        invalid.setdefault(('composition', peer), 'transition contribution requires renewed review')
                    # Original meaning must be reviewed for either new prompt.
                    review_set.pop('storyboard', None)

    unknown = []
    for uid,row in _unit_rows(inventory,'speech').items():
        if row.get('durable_tts_intent') is True or (row.get('status')=='ambiguous' and not inventory.submissions.get('speech',{}).get(uid)):
            unknown.append(('speech',uid))
    if not unknown and inventory.stage_records['speech'].get('status')=='ambiguous' and not _unit_rows(inventory,'speech'):
        unknown.append(('speech','reference_replay'))
    for stage in STAGES:
        for uid, submission in inventory.submissions.get(stage, {}).items():
            state = submission.get('state')
            if state in ('intent', 'ambiguous', 'accepted', 'still_running', 'unresolved'):
                unknown.append((stage, uid))
            elif state in ('failed', 'rejected'):
                if retry_failed:
                    invalidate(stage, 'explicit failed-attempt retry', (uid,))
                else:
                    refusals.append(f'{stage}/{uid}: failed attempt requires retry_failed')
    partial = False
    for stage in STAGES:
        checkpoint = inventory.checkpoints.get(stage, {})
        for uid in checkpoint.get('known_failed_units',{}):
            if (stage,uid) in unknown:continue
            if retry_failed:
                invalidate(stage,'explicit failed verified-media retry',(uid,))
            else:
                refusals.append(f'{stage}/{uid}: proven failed result requires retry_failed')
        for uid, row in _unit_rows(inventory, stage).items():
            if (stage,uid) in unknown:continue
            if row.get('status') == 'failed' and not inventory.submissions.get(stage, {}).get(uid):
                unit_unsent = (checkpoint.get('unsent_verified') is True and
                               uid in checkpoint.get('remaining_units', ()) and
                               'verified_units' in checkpoint and
                               uid not in checkpoint['verified_units'])
                if unit_unsent:
                    continue
                if retry_failed:
                    invalidate(stage, 'explicit failed local-unit retry', (uid,))
                else:
                    refusals.append(f'{stage}/{uid}: failed unit requires retry_failed')
        record = inventory.stage_records[stage]
        status = record.get('status')
        if status in ('failed', 'interrupted', 'ambiguous'):
            partial = True
            checkpoint = inventory.checkpoints.get(stage, {})
            proven_unsent = (checkpoint.get('unsent_verified') is True and
                            'verified_units' in checkpoint and 'remaining_units' in checkpoint)
            # Unknown submission is a hard wait, independent of retry request.
            if status == 'failed' and not retry_failed and not proven_unsent and not any(s == stage for s, _ in unknown):
                refusals.append(f'{stage}: failed stage requires retry_failed')
        elif status == 'running' and not inventory.checkpoints.get(stage, {}).get('draft_complete'):
            partial = True

    def sig(stage, uid):
        item = inventory.signatures.get(stage)
        if isinstance(item, Mapping):
            return item.get(uid) if uid is not None else item.get('__stage__', item.get('stage', item.get(None)))
        return item

    invalidated, reused = [], []
    for stage in STAGES:
        if (stage, None) in invalid:
            invalidated.append(RecoveryItem(stage, None, invalid[(stage, None)], sig(stage, None)))
        for uid in _stage_units(inventory, stage):
            if (stage, uid) in invalid:
                invalidated.append(RecoveryItem(stage, uid, invalid[(stage, uid)], sig(stage, uid)))
            elif (stage, None) not in invalid and _unit_rows(inventory, stage)[uid].get('status') == 'completed':
                reused.append(RecoveryItem(stage, uid, 'freshly verified unit', sig(stage, uid)))
        for (other_stage, uid), reason in invalid.items():
            if other_stage == stage and uid is not None and uid not in _stage_units(inventory, stage):
                invalidated.append(RecoveryItem(stage, uid, reason, sig(stage, uid)))
        if (stage, None) not in invalid and inventory.stage_records[stage].get('status') == 'completed':
            if not any(s == stage for s, _ in invalid):
                reused.append(RecoveryItem(stage, None, 'freshly consumed stage', sig(stage, None)))

    changed_configuration = any(not row.field.startswith('reviews.') for row in changed)
    child = (changed_configuration or any(stage != 'publish' for stage, _ in invalid) or partial or
             (('publish', None) in invalid and inventory.stage_records['publish'].get('status') == 'completed'))
    if not refusals:
        if unknown:
            stage, uid = unknown[0]
            # Never derive an unknown intent into a new POST budget.
            for prior in STAGES[:STAGES.index(stage)]:
                if inventory.stage_records[prior].get('status') == 'completed' and not any(s == prior for s, _ in invalid):
                    operations.append(RecoveryOperation('consume', prior, None, None, ()))
            operations.append(RecoveryOperation('reconcile', stage, uid, None, ()))
            waiting.append(f'{stage}/{uid}:submission')
            child = False
        else:
            if child:
                operations.append(RecoveryOperation('derive', 'preflight', None, parent_identity, ()))
            for stage in STAGES:
                record = inventory.stage_records[stage]
                status = record.get('status')
                stale = any(s == stage for s, _ in invalid)
                if stage == 'publish':
                    if status == 'completed' and not stale:
                        operations.append(RecoveryOperation('consume', stage, None, None, ()))
                    else:
                        missing = tuple(role for role in _FINAL_ROLES if not review_set.get(role))
                        if publish and not missing:
                            operations.append(RecoveryOperation('publish', stage, None, None, _FINAL_ROLES))
                        else:
                            waiting.extend(missing or ('publish',))
                            operations.append(RecoveryOperation('wait', stage, None, None, tuple(waiting)))
                            if publish:
                                refusals.append('publication requires final_review and full_film_acceptance')
                    break
                if status == 'completed' and not stale:
                    operations.append(RecoveryOperation('consume', stage, None, record.get('identity'), ()))
                    continue
                checkpoint = inventory.checkpoints.get(stage, {})
                draft = status == 'running' and checkpoint.get('draft_complete') and not stale
                roles = _FINALIZE_ROLES.get(stage, ()) if draft else _PREPARE_ROLES.get(stage, ())
                if stale and stage in ('start_images', 'source_clips') and parsed and parsed['shot_changes']:
                    roles = ('storyboard',) + roles
                missing = tuple(r for r in roles if not review_set.get(r))
                if missing:
                    waiting.extend(missing)
                    operations.append(RecoveryOperation('wait', stage, None, checkpoint.get('identity', checkpoint.get('draft_identity')), missing))
                else:
                    operations.append(RecoveryOperation('finalize' if draft else 'prepare', stage, None,
                        checkpoint.get('identity', checkpoint.get('draft_identity')) if draft else None, roles))
                break
    return RecoveryPlan(inventory.run_dir, parent_identity, inventory.input_identities,
        tuple(changed), tuple(invalidated), tuple(reused), tuple(operations),
        tuple(waiting), child, tuple(dict.fromkeys(refusals)))
