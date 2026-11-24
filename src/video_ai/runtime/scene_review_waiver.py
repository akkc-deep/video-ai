"""Explicit run-local user authorization to proceed without playback review.

This is production admission, never evidence that a clip was watched or passed.
Existing accepted/rejected observations remain authoritative and unchanged.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ..planning.production_scenes import canonical_digest
from .production_state import ProductionRefused, object_fields, run_path, timestamp


def load_review_waiver(run, scope='clip_playback'):
    run = Path(run)
    path = run/'production/review-waiver.json'
    if not path.is_file():
        return None
    path = run_path(run, path)
    raw = path.read_bytes()
    value = json.loads(raw)
    object_fields(value, ('schema_version run_id options_sha256 authorized_by user_request '
                         'authorized_at scopes').split(), 'review waiver')
    if (type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['run_id'] != run.name or value['authorized_by'] != 'user'
            or not isinstance(value['user_request'], str) or not value['user_request'].strip()
            or value['scopes'] != ['clip_playback', 'final_playback']):
        raise ProductionRefused('invalid explicit user review waiver')
    timestamp(value['authorized_at'])
    if datetime.fromisoformat(value['authorized_at']) > datetime.now(timezone.utc):
        raise ProductionRefused('future user review waiver')
    if scope not in value['scopes']:
        raise ProductionRefused('review waiver does not authorize this scope')
    options = run_path(run, run/'production/options.json')
    if hashlib.sha256(options.read_bytes()).hexdigest() != value['options_sha256']:
        raise ProductionRefused('review waiver belongs to different frozen options')
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def apply_clip_waiver(run, record):
    if record is None or record['accepted'] is not None or record['rejected'] is not None:
        return record
    authorization = load_review_waiver(run)
    if authorization is None:
        return record
    result = deepcopy(record)
    result['accepted'] = dict(schema_version=1, admission='user_review_waiver',
        visual_review='unverified', run_id=Path(run).name, clip_id=record['clip']['clip_id'],
        clip_sha256=canonical_digest(record['clip']), request_sha256=canonical_digest(record['request']),
        authorization=authorization)
    return result


def final_waiver_acceptance(run, candidate):
    authorization = load_review_waiver(run, 'final_playback')
    if authorization is None:
        return None
    return dict(schema_version=1, admission='user_review_waiver', scope='final_playback',
        visual_review='unverified', audio_review='unverified', run_id=Path(run).name,
        composition_sha256=canonical_digest(candidate), authorization=authorization)


def capture_waived_origin(frozen, domain, key):
    """Trust completed history for an explicitly waived ordinary-Wan revision.

    Capture the current node and authorization, rather than repeatedly walking
    every historical revision. The existing copy writer still verifies each
    new media copy against its saved identity.
    """
    from .resume_materials import trusting_materials, saved_revision, saved_clip
    if not trusting_materials() or frozen.config.raw.get('scene_rendering', {}).get('mode') is not None:
        return None
    run = Path(frozen.options['script_path']).parent.parent
    if load_review_waiver(run) is None:
        return None
    from ._scene_revision_origins import require_origin_node, media_for_node
    from .scene_revision_records import RevisionGuard
    if domain == 'clip':
        record = saved_clip(run, key)
        if record is None or record['accepted'] is None or record['rejected'] is not None:
            raise ProductionRefused('saved clip lacks production admission for revision')
        value = record['clip']
        media = [('generated',value['generated']), ('source',value['source']),
                 ('last_frame',record['last_frame']['image'])]
    else:
        value = require_origin_node(frozen, domain, key)
        media = media_for_node(frozen, domain, key, value)
    files = {run/'production/options.json', run/'production/review-waiver.json'}
    for name in ('units.json', 'timeline.json', 'scene-plan.json', 'visual-bible.json',
                 'scene-plan-commit.json', 'reference-images/wan-inputs.json', 'scene-clips/inputs.json'):
        path = run/'production'/name
        if path.is_file(): files.add(path)
    if 'scene_revision' in frozen.options:
        proof = saved_revision(frozen.options, run)
        root = run/'production/scene-revision'
        files.update((root/'commit.json', root/'imports.json'))
        imported = proof['imports'].get(domain+':'+key)
        if imported is not None:
            sidecar, bound = imported
            files.add(Path(bound['path']))
            if 'view_artifact' in sidecar: files.add(Path(sidecar['view_artifact']['path']))
    if domain == 'clip':
        files.update((run/'production/scene-clips'/key).rglob('*.json'))
    guard = RevisionGuard(frozen)
    snapshots = [guard.capture(path, root=run) for path in sorted(files)]
    absent = run/'.make-video.lock'
    guard.capture_absent(absent, root=run)
    for _, artifact in media:
        guard.capture(artifact['path'], root=run, expected=artifact)
    guard.verify_captured_bytes()
    return dict(value=value, media=media, guard=guard, raw_files=[],
                snapshot=dict(files=snapshots, inventories=[], absent_paths=[str(absent)]))


def trusted_upscale_complete(context):
    """Consume an already committed upscale result without replaying its HTTP.

    The original writer checked each new frame before committing this index.
    On an explicitly waived trusted resume, check current inputs, frame order
    and required output files. The final encoder will read every output PNG.
    """
    from .resume_materials import existing_file, read_saved, remember, require_file
    from ._scene_upscale_records import complete_value, mapping
    from .scene_clip_records import equal
    store = context['store']
    path = store.root/'complete.json'
    if not getattr(store, '_trusted_waived_inputs', False) or not existing_file(path):
        return None
    equal(read_saved(store.root/'inputs.json'), context['inputs'], 'saved upscale inputs')
    value = read_saved(path)
    frames = value.get('frames')
    if not isinstance(frames, list) or len(frames) != len(context['rows']):
        raise ProductionRefused('saved upscale frame count differs')
    equal(value, complete_value(context, frames), 'saved upscale complete header')
    for frame, row in zip(frames, context['rows'], strict=True):
        equal(frame['frame_id'], row['frame_id'], 'saved upscale frame order')
        equal(frame['mapping'], mapping(row), 'saved upscale frame mapping')
        target = store._lexical(frame['output']['path'])
        if target != store.frame_dir(row['frame_id'])/'output.png':
            from ._scene_revision_readers import inherited_frame
            inherited = inherited_frame(context, row)
            if inherited is None:
                raise ProductionRefused('saved upscale output path differs')
            equal(frame['output'], inherited['output'], 'saved inherited upscale output')
        require_file(target)
    remember(value)
    return deepcopy(value)
