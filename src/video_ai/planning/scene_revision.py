"""Pure scene revision planning: content edges never include admission gates."""
from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timezone
import re
from uuid import UUID

from .production_scenes import canonical_digest

STRATEGY = 'paragraph_jimeng_v1'
DOMAINS = ('common', 'plan', 'images', 'choices', 'image_group', 'clips',
           'clip_reviews', 'upscale', 'composition', 'final_review', 'delivery')
SNAPSHOT_FIELDS = 'source_options bible scene_plan image_choices clip_nodes upscale_nodes pending_effects'.split()
REQUEST_FIELDS = ('schema_version production_strategy revision_id source_run_id source_options_sha256 '
                  'requested_at kind scene_ids clip_ids choices config_path image_model output_path reason').split()
IDENTITY_FIELDS = ('config_sha256 image_generation reference_settings_sha256 model_stamps workflows '
                   'voice_sha256 font_sha256 planning_sha256').split()


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError(f'{label}: exact fields required')


def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('SHA256 required')


def _ids(value, known):
    if type(value) is not list or any(type(v) is not str or v not in known for v in value):
        raise ValueError('known IDs array required')
    if len(set(value)) != len(value): raise ValueError('duplicate IDs')
    return [v for v in known if v in value]


def validate_rendering_identity(value):
    """Old identities have exactly the original fields; v2 is explicit and complete."""
    modern = 'schema_version' in value or 'rendering' in value
    _fields(value, IDENTITY_FIELDS+(['schema_version','rendering'] if modern else []), 'target identity')
    if modern:
        if type(value['schema_version']) is not int or value['schema_version'] != 2:
            raise ValueError('unknown rendering identity schema')
        rendering = value['rendering']
        _fields(rendering, ('prompt_policy','prompt_contract_sha256'), 'rendering identity')
        if rendering['prompt_policy'] != 'visual_v2': raise ValueError('unknown rendering identity policy')
        _sha(rendering['prompt_contract_sha256'])
    for key in ('config_sha256','voice_sha256','font_sha256','planning_sha256'): _sha(value[key])
    if value['reference_settings_sha256'] is not None: _sha(value['reference_settings_sha256'])
    for key in ('image_generation','model_stamps','workflows'):
        if type(value[key]) is not dict: raise ValueError('identity mapping required')


def identity_from_options(options, *, reference_settings_sha256=None):
    """Describe already-validated frozen content without stat/path IO."""
    raw = options['config_snapshot']['raw']
    inputs = options['execution_policy']['input_identities']
    def content(stamp):
        return {k: deepcopy(stamp[k]) for k in ('path', 'bytes', 'sha256')}
    common = deepcopy(raw)
    for key in ('image_generation', 'reference_generation', 'reference_capabilities',
                'reference_storage', 'models', 'workflows', 'email_notification', 'selection_email',
                'output_root', 'project_root', 'cache_root', 'runtime_root', 'voice_config'):
        common.pop(key, None)
    if 'scene_rendering' in raw:
        common.pop('scene_rendering',None)
    voice=deepcopy(options['voice_snapshot']['raw'])
    for key in ('reference_audio','gpt_weights','sovits_weights','bert_root','hubert_root'):voice.pop(key,None)
    # Profile affects Wan; other media settings affect the common timeline/render.
    if isinstance(common.get('media'), dict): common['media'].pop('profile', None)
    result = dict(config_sha256=canonical_digest(raw), image_generation=deepcopy(options['image_generation']),
        reference_settings_sha256=reference_settings_sha256,
        model_stamps=deepcopy(options['model_stamps']),
        workflows={k: content(v.get('source_identity',inputs.get('workflow/'+k)))
                   for k,v in options['workflow_snapshots'].items()},
        voice_sha256=canonical_digest(dict(voice=voice,model_roots=options['execution_policy'].get('model_roots',{}),
            models={k:v for k,v in options['model_stamps'].items() if k in ('gpt_weights', 'sovits_weights')},
            inputs={k:{name:v[name] for name in ('bytes','sha256')} for k,v in inputs.items()
                    if k in ('reference', 'tts_yaml_source')})),
        font_sha256=inputs['font']['sha256'] if 'font' in inputs else canonical_digest(None),
        planning_sha256=canonical_digest(common))
    if 'scene_rendering' in raw:
        from .scene_video_prompts import parse_scene_rendering
        settings = parse_scene_rendering(raw['scene_rendering'])
        stamp = inputs.get('scene_video_prompts')
        if not isinstance(stamp,dict): raise ValueError('rendering identity requires frozen prompt SHA')
        _sha(stamp.get('sha256'))
        result.update(schema_version=2,rendering=dict(prompt_policy=settings['prompt_policy'],
            prompt_contract_sha256=stamp['sha256']))
    return result


def _validate_request(request, snapshot, target):
    _fields(request, REQUEST_FIELDS, 'revision request')
    if type(request['schema_version']) is not int or request['schema_version'] != 2 or request['production_strategy'] != STRATEGY:
        raise ValueError('revision schema/strategy differs')
    if str(UUID(request['revision_id'])) != request['revision_id']: raise ValueError('canonical UUID required')
    if request['source_run_id'] != snapshot['source_options']['run_id']: raise ValueError('source run differs')
    _sha(request['source_options_sha256'])
    date = datetime.fromisoformat(request['requested_at'])
    if date.tzinfo is None or date > datetime.now(timezone.utc): raise ValueError('revision time must be past and timezone aware')
    if type(request['reason']) is not str or not request['reason'].strip(): raise ValueError('reason required')
    scenes = [s['scene_id'] for s in snapshot['scene_plan']['scenes']]
    clips = [c['clip_id'] for c in snapshot['scene_plan']['clips']]
    sids, cids = _ids(request['scene_ids'], scenes), _ids(request['clip_ids'], clips)
    if type(request['choices']) is not list: raise ValueError('choices array required')
    chosen = {}
    for row in request['choices']:
        _fields(row, ('scene_id', 'candidate_id', 'sha256'), 'revision choice')
        _sha(row['sha256'])
        if row['scene_id'] in chosen or row['scene_id'] not in sids: raise ValueError('unknown or duplicate choice scene')
        if type(row['candidate_id']) is not str or not re.fullmatch(r'request_[0-9]{2}_image_[0-9]{2}', row['candidate_id']):
            raise ValueError('invalid candidate ID')
        chosen[row['scene_id']] = row
    kind = request['kind']
    if kind == 'reconfigure':
        if sids or cids or chosen or type(request['config_path']) is not str or not re.match(r'^(?:[A-Za-z]:[/\\]|/)', request['config_path']):
            raise ValueError('reconfigure requires only absolute config path and optional overrides')
        for key in ('image_model', 'output_path'):
            if request[key] is not None and (type(request[key]) is not str or not request[key].strip()):
                raise ValueError('invalid configuration override')
    else:
        if any(request[k] is not None for k in ('config_path', 'image_model', 'output_path')):
            raise ValueError('configuration overrides require reconfigure')
        if kind == 'reselect_images':
            if not sids or cids or set(chosen) != set(sids): raise ValueError('reselection coverage differs')
            old = {r['scene_id']:r for r in snapshot['image_choices']}
            if any(sid not in old for sid in sids): raise ValueError('reselect requires accepted original choice')
            if all(all(old[sid][k] == chosen[sid][k] for k in ('candidate_id', 'sha256')) for sid in sids):
                raise ValueError('reselection makes no change')
        elif kind == 'regenerate_images':
            if not sids or cids or chosen: raise ValueError('image regeneration targets differ')
        elif kind == 'regenerate_clips':
            if not cids or sids or chosen: raise ValueError('clip regeneration targets differ')
        else: raise ValueError('unknown revision kind')
    validate_rendering_identity(target)
    return sids, cids


def plan_scene_revision(snapshot, request, target_identity):
    """Return deterministic dirty/reusable nodes; no effects or source mutation."""
    _fields(snapshot, SNAPSHOT_FIELDS, 'revision snapshot')
    sids, cids = _validate_request(request, snapshot, target_identity)
    plan = snapshot['scene_plan']
    scenes = [s['scene_id'] for s in plan['scenes']]
    classification=snapshot['source_options'].get('_scene_revision_planning')
    if classification is not None:
        _fields(classification,('identity','completed_image_ids','image_group_accepted','target_config'),'validated planning context')
        validate_rendering_identity(classification['identity'])
        completed_images=_ids(classification['completed_image_ids'],scenes)
        if type(classification['image_group_accepted']) is not bool:raise ValueError('image group acceptance must be bool')
        if classification['target_config'] is not None and canonical_digest(classification['target_config'])!=target_identity['config_sha256']:
            raise ValueError('validated target configuration digest differs')
    else:completed_images=[r['scene_id'] for r in snapshot['image_choices']]
    clips = [c['clip_id'] for c in plan['clips']]
    clip_nodes = {}
    for row in snapshot['clip_nodes']:
        _fields(row, ('clip_id', 'record', 'acceptance', 'status'), 'clip node')
        key = row['clip_id']
        if key not in clips or key in clip_nodes or row['status'] not in ('accepted','rejected','pending','unknown','running'):
            raise ValueError('invalid clip node')
        clip_nodes[key] = row
    frames = []
    frame_clip = {}
    for clip in plan['clips']:
        for i in range(clip['retained_frames']):
            fid = f'{clip["clip_id"]}:frame_{i+1:06d}'
            frames.append(fid); frame_clip[fid] = clip['clip_id']
    upscale_nodes = {}
    for row in snapshot['upscale_nodes']:
        _fields(row, ('frame_id', 'record', 'status'), 'upscale node')
        if row['frame_id'] not in frame_clip or row['frame_id'] in upscale_nodes or row['status'] not in ('ready','terminal','pending','unknown','running'):
            raise ValueError('invalid upscale node')
        upscale_nodes[row['frame_id']] = row
    nodes = {d:['all'] for d in DOMAINS}
    nodes.update(images=scenes, choices=scenes, clips=clips, clip_reviews=clips, upscale=frames)
    edges, gates = [], []
    seen_content,seen_admission=set(),set()
    def edge(a, b, *, admission=False):
        target = gates if admission else edges
        seen=seen_admission if admission else seen_content
        row = dict(source=a, target=b)
        if (a,b) not in seen:target.append(row);seen.add((a,b))
    def node(domain, key): return domain+':'+key
    for scene in plan['scenes']:
        sid = scene['scene_id']
        for binding in scene['reference_bindings']:
            origin = binding['source_scene_id']
            if origin not in scenes or scenes.index(origin) >= scenes.index(sid): raise ValueError('invalid reference ancestry')
            edge(node('choices', origin), node('images', sid))
        edge('common:all', 'plan:all'); edge('plan:all', node('images', sid))
        edge(node('images', sid), node('choices', sid))
        edge(node('choices', sid), 'image_group:all')
    for clip in plan['clips']:
        cid, sid, parent = clip['clip_id'], clip['scene_id'], clip['parent_clip_id']
        if sid not in scenes: raise ValueError('unknown clip scene')
        edge(node('choices', sid), node('clips', cid))
        if parent:
            ancestors = [c for c in plan['clips'] if c['clip_id'] == parent]
            if len(ancestors) != 1 or ancestors[0]['scene_id'] != sid or clips.index(parent) >= clips.index(cid):
                raise ValueError('invalid continuation ancestry')
            edge(node('clips', parent), node('clips', cid))
        edge(node('clips', cid), node('clip_reviews', cid))
        edge('image_group:all', node('clips', cid), admission=True)
        edge(node('clip_reviews',cid),'admission:source_clips_ready',admission=True)
    for fid in frames:
        edge(node('clips', frame_clip[fid]), node('upscale', fid))
        edge(node('upscale', fid), 'composition:all')
        edge('admission:source_clips_ready',node('upscale',fid),admission=True)
        edge(node('upscale',fid),'admission:upscale_ready',admission=True)
    edge('admission:upscale_ready','composition:all',admission=True)
    edge('common:all', 'composition:all')
    edge('composition:all', 'final_review:all'); edge('final_review:all', 'delivery:all')
    edge('final_review:all', 'delivery:all', admission=True)
    roots = ['composition:all']
    kind = request['kind']
    if kind == 'reselect_images': roots += [node('choices', sid) for sid in sids]
    elif kind == 'regenerate_images': roots += [node('images', sid) for sid in sids]
    elif kind == 'regenerate_clips': roots += [node('clips', cid) for cid in cids]
    else:
        source = classification['identity'] if classification is not None else identity_from_options(snapshot['source_options'])
        if source == target_identity: raise ValueError('reconfigure makes no effective change')
        if source.get('rendering') != target_identity.get('rendering'):
            roots += [node('clips',cid) for cid in clips]
        if any(source[k] != target_identity[k] for k in ('voice_sha256','font_sha256','planning_sha256')):
            roots.append('common:all')
        if source['image_generation'] != target_identity['image_generation']:
            roots += [node('images', sid) for sid in scenes]
        if source['reference_settings_sha256'] != target_identity['reference_settings_sha256']:
            roots += [node('images', s['scene_id']) for s in plan['scenes'] if s['reference_bindings']]
        for role in set(source['model_stamps']) | set(target_identity['model_stamps']):
            if source['model_stamps'].get(role) == target_identity['model_stamps'].get(role): continue
            domain = 'upscale' if role == 'upscale' else 'common' if role in ('gpt_weights', 'sovits_weights') else 'clips'
            roots += [node(domain, key) for key in nodes[domain]]
        for role in set(source['workflows']) | set(target_identity['workflows']):
            if source['workflows'].get(role) != target_identity['workflows'].get(role):
                domain = 'upscale' if role.startswith('upscale') else 'clips'
                roots += [node(domain, key) for key in nodes[domain]]
        if classification is not None and classification['target_config'] is not None:
            old_raw=snapshot['source_options']['config_snapshot']['raw'];new_raw=classification['target_config']
            if old_raw.get('media',{}).get('profile')!=new_raw.get('media',{}).get('profile'):
                roots += [node('clips',cid) for cid in clips]
        # Unknown effective config changes cannot silently preserve all content.
        if classification is None and roots == ['composition:all'] and source['config_sha256'] != target_identity['config_sha256']:
            roots.append('common:all')
    children = defaultdict(list)
    for e in edges: children[e['source']].append(e['target'])
    queue, dirty, reasons = deque((n, 'explicit '+kind) for n in dict.fromkeys(roots)), set(), []
    while queue:
        n, cause = queue.popleft()
        if n in dirty: continue
        dirty.add(n); reasons.append(dict(node=n, cause=cause))
        queue.extend((child, n) for child in children[n])
    choices = {r['scene_id']:r for r in snapshot['image_choices']}
    if len(choices) != len(snapshot['image_choices']) or set(choices)-set(scenes): raise ValueError('invalid accepted choices')
    accepted = {'common':{'all'}, 'plan':{'all'}, 'images':set(completed_images), 'choices':set(choices),
        'image_group':{'all'} if set(choices) == set(scenes) and (classification is None or classification['image_group_accepted']) else set(),
        'clips':{k for k,r in clip_nodes.items() if r['status']=='accepted' and r['record'] is not None and r['acceptance'] is not None},
        'upscale':{k for k,r in upscale_nodes.items() if r['status']=='ready' and r['record'] is not None}}
    accepted['clip_reviews'] = accepted['clips']
    reusable = {d:[k for k in nodes[d] if node(d,k) not in dirty and k in accepted.get(d,set())] for d in DOMAINS}
    blocked = []
    for effect in snapshot['pending_effects']:
        _fields(effect, ('node','intent_sha256','status'), 'pending effect')
        _sha(effect['intent_sha256'])
        if effect['status'] not in ('unknown','running'): raise ValueError('invalid pending effect state')
        n = effect['node']
        if type(n) is not str or ':' not in n: raise ValueError('logical effect node required')
        domain, key = n.split(':',1)
        if domain not in nodes or key not in nodes[domain]: raise ValueError('unknown pending node')
        if n in dirty or key not in reusable[domain]: blocked.append(deepcopy(effect))
    return dict(schema_version=2, algorithm='scene_revision_v1', source_run_id=request['source_run_id'],
        request_sha256=canonical_digest(request), target_identity_sha256=canonical_digest(target_identity),
        content_edges=edges, admission_edges=gates,
        dirty={d:[k for k in nodes[d] if node(d,k) in dirty] for d in DOMAINS},
        reusable=reusable, blocked_effects=blocked, reasons=reasons)
