"""Prepare a new frozen scene revision without changing or running its origin."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import UUID

from ..config import load_config, load_voice_config, read_json
from ..jimeng_config import STRATEGY, active_models, active_workflows, override_image_model
from ..planning.production_scenes import canonical_digest
from ..planning.scene_revision import identity_from_options, plan_scene_revision
from .manifest import now, thaw, validate_run_dir
from .production_state import ArtifactStamp, ProductionRefused, RunLock, json_bytes, object_fields
from .scene_revision_records import (artifact, safe_path, stable_bytes, token, _json,
    validate_revision_structure, require_scene_revision,revision_validation)
from ._scene_revision_copy import RevisionStore, copy_identity


def boundary(point):
    """Caller-thread transaction boundary."""


@dataclass(frozen=True)
class SceneRevisionResult:
    schema_version: int = 2
    production_strategy: str = STRATEGY
    source_run_id: str | None = None
    run_id: str | None = None
    run_dir: Path | None = None
    status: str = 'blocked'
    revision_commit: Path | None = None
    log_dir: Path | None = None
    error: dict | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version!=2 or self.production_strategy!=STRATEGY:
            raise ValueError('invalid revision result schema')
        if self.status not in ('revision_ready','blocked','failed','interrupted'): raise ValueError('invalid revision result status')
        if self.run_dir is None:
            if any(v is not None for v in (self.run_id,self.revision_commit,self.log_dir)): raise ValueError('revision result has no target')
        else:
            run = validate_run_dir(self.run_dir); object.__setattr__(self,'run_dir',run)
            if self.run_id != run.name: raise ValueError('revision target identity differs')
            for key in ('revision_commit','log_dir'):
                if getattr(self,key) is not None: safe_path(getattr(self,key),run)
        if self.error is not None: object_fields(self.error,('kind','message','evidence_paths'),'revision result error')
        if self.status=='revision_ready' and (self.revision_commit is None or self.error is not None):
            raise ValueError('ready revision requires commit and no error')

    def to_dict(self): return thaw(self)

    @property
    def exit_code(self): return dict(revision_ready=0,blocked=2,failed=1,interrupted=130)[self.status]


def configuration_identity(config, *, image_model=None, reference_sha=None):
    """Read actual effective content before any new model/cloud submission."""
    workflows = active_workflows(config)
    workflows['upscale_mapping'] = config.workflows['upscale'].with_suffix('.mapping.json')
    models = {role:ArtifactStamp.read(path).to_dict() for role,path in active_models(config).items()}
    models.update({role:ArtifactStamp.read(getattr(config.voice,role)).to_dict() for role in ('gpt_weights','sovits_weights')})
    # identity_from_options only consumes these validated immutable roles.
    inputs = {key:artifact(path) for key,path in dict(font=config.media.font_file,
        reference=config.voice.reference_audio,tts_yaml_source=config.project_root/'config/tts-api.yaml').items()}
    options = dict(config_snapshot={'raw':thaw(config.raw)},voice_snapshot={'raw':thaw(config.voice.raw)},
        image_generation=thaw(override_image_model(config.image_generation,image_model)),model_stamps=models,
        workflow_snapshots={k:{'source_identity':artifact(p)} for k,p in workflows.items()},
        execution_policy={'input_identities':dict(inputs,**{'workflow/'+k:artifact(p) for k,p in workflows.items()}),
            'model_roots':{k:str(getattr(config.voice,k)) for k in ('bert_root','hubert_root')}})
    if 'scene_rendering' in config.raw:
        from .scene_video_prompt_records import source_contract_identity
        options['execution_policy']['input_identities']['scene_video_prompts'] = source_contract_identity(config)
        if config.raw['scene_rendering'].get('mode') == 'whole_scene_v1':
            from types import SimpleNamespace
            from .scene_execution_records import load_whole_scene_evidence, verify_current_environment
            evidence=load_whole_scene_evidence(config.raw['scene_rendering']['whole_scene_evidence'])
            options['execution_policy']['input_identities']['whole_scene_evidence']=evidence['root']
            verify_current_environment(SimpleNamespace(config=config,options=options),evidence)
    return identity_from_options(options,reference_settings_sha256=reference_sha)


def _target_configuration(source,target,request):
    """Materialize inherited raw settings with absolute frozen-source paths."""
    if request['kind']=='reconfigure':
        config = load_config(Path(request['config_path']))
        if config.production_strategy!=STRATEGY: raise ProductionRefused('revision strategy must remain paragraph_jimeng_v1')
        return config, None, None
    voice_raw = thaw(source.options['voice_snapshot']['raw'])
    for role in ('gpt_weights','sovits_weights','bert_root','hubert_root','reference_audio'):
        voice_raw[role] = str(getattr(source.config.voice,role))
    voice_path = target/'production/scene-revision/voice-source.json'
    voice = load_voice_config(voice_path,raw=voice_raw)
    raw = thaw(source.options['config_snapshot']['raw'])
    raw.update(voice_config=str(voice_path),tools=thaw(source.config.tools),models=thaw(source.config.models),
               workflows=thaw(source.config.workflows))
    raw['media']['font_file'] = str(source.config.media.font_file)
    if 'scene_rendering' in raw:
        raw['scene_rendering']['prompt_contract'] = source.options['execution_policy']['input_identities']['scene_video_prompts']['path']
        if raw['scene_rendering'].get('mode') == 'whole_scene_v1':
            raw['scene_rendering']['whole_scene_evidence'] = source.options['execution_policy']['input_identities']['whole_scene_evidence']['path']
    if raw.get('reference_capabilities') is not None:
        # Preserve validated capability bytes already frozen by the source.
        for key in raw['reference_capabilities']:
            bound = source.options['execution_policy']['input_identities'].get('reference_capability/'+key)
            if bound is not None: raw['reference_capabilities'][key] = bound['path']
    path = target/'production/scene-revision/config-source.json'
    return load_config(path,raw=raw,voice=voice),json_bytes(raw),json_bytes(voice_raw)


def _snapshot(source,*,target_config=None,reference_sha=None,request=None,target_identity=None):
    if request is None:return _admitted_snapshot(source,target_config=target_config,reference_sha=reference_sha)
    from ._scene_revision_origins import common
    from .image_selection_records import load_committed_plan,_load_accepted,_choices
    from ..planning.production_timeline import ProductionTimeline
    from ._scene_revision_origin_images import origin_image_scope
    prefix=common(source);units=prefix['units'];timeline=ProductionTimeline.from_dict(prefix['timeline'])
    bible,plan=load_committed_plan(source,units,timeline)
    execution = _source_execution(source,plan,timeline)
    source_clips = execution['clips'] if execution is not None else plan['clips']
    choices=[]
    if request['kind']=='reselect_images':
        end=max(i for i,ids in enumerate(plan['batches'],1) if set(ids)&set(request['scene_ids']))
        choices=list(_choices(_load_accepted(source,units,timeline,bible,plan,before=end+1)).values())
    options=deepcopy(source.options)
    options['_scene_revision_planning']=dict(identity=identity_from_options(source.options,reference_settings_sha256=reference_sha),
        completed_image_ids=[],image_group_accepted=False,target_config=thaw(target_config.raw))
    hint=dict(source_options=options,bible=bible,scene_plan=plan,image_choices=choices,
        clip_nodes=[dict(clip_id=c['clip_id'],record=None,acceptance=None,status='pending') for c in source_clips],
        upscale_nodes=[dict(frame_id=c['clip_id']+f':frame_{i+1:06d}',record=None,status='pending') for c in source_clips for i in range(c['retained_frames'])],pending_effects=[])
    if execution is not None: hint['scene_execution'] = execution
    dirty=plan_scene_revision(hint,request,target_identity)['dirty']
    from ._scene_revision_origin_clips import origin_clip_scope
    known=[c['clip_id'] for c in source_clips]
    with origin_image_scope(source,[s['scene_id'] for s in plan['scenes'] if s['scene_id'] not in dirty['images']]),origin_clip_scope(source,[cid for cid in known if cid not in dirty['clips']],all_ids=known):
        return _admitted_snapshot(source,target_config=target_config,reference_sha=reference_sha,excluded_frames=dirty['upscale'])


def _source_execution(source,plan,timeline):
    from .scene_execution_records import rendering_mode, load_scene_execution
    return load_scene_execution(source,plan,timeline) if rendering_mode(source) is not None else None


def _image_terminal(source,scene,bible,plan,intent_path):
    """A terminal cursor alone cannot hide an unfinished original submission."""
    from .image_selection_records import _bound,_equal
    from .production_state import timestamp
    folder=intent_path.parent;run=folder.parents[3]
    request=_json(folder/'request.json',root=run);identity=canonical_digest(request)
    expected=dict(schema_version=2,run_id=run.name,scene_id=scene['scene_id'],
        request_id=folder.name,prompt=scene['image_prompt'],image_generation=thaw(source.config.image_generation))
    if scene['reference_bindings']:
        from .reference_settings import load_reference_settings
        from .reference_image_records import validate_reference_inputs,validate_reference_intent,validate_submit_evidence
        settings=load_reference_settings(source)
        model,prompt=validate_reference_inputs(source,scene,bible,plan,request['reference_inputs'],settings)
        expected.update(prompt=prompt,image_generation=thaw(model),reference_inputs=request['reference_inputs'])
        original_intent=_json(intent_path,root=run)
        validate_reference_intent(original_intent,request,settings);validate_submit_evidence(folder,request,original_intent)
    else:
        original_intent=_bound(intent_path,'schema_version identity created_at state'.split(),identity)
        timestamp(original_intent['created_at'])
        if original_intent['state']!='intent':raise ProductionRefused('invalid original image intent')
    _equal(request,expected,'original terminal image request')
    terminal=_bound(folder/'terminal.json','schema_version identity status'.split(),identity)
    if terminal['status'] not in ('expired','not_found','failed') or (folder/'result.json').exists():
        raise ProductionRefused('original image terminal conflicts with completion')
    accepted=_bound(folder/'accepted.json','schema_version identity task_id request_id diagnostic'.split(),identity)
    queries=[_bound(path,'schema_version identity task_id status request_id diagnostic'.split(),identity) for path in folder.glob('query-*.json')]
    if not any(q['task_id']==accepted['task_id'] and q['status']==terminal['status'] for q in queries):
        raise ProductionRefused('original image terminal lacks definitive query evidence')
    return terminal


def _admitted_snapshot(source,*,target_config=None,reference_sha=None,excluded_frames=()):
    from ._scene_revision_origins import common
    from .image_selection_records import load_committed_plan,load_accepted_batches,_choices
    prefix = common(source)
    from ..planning.production_timeline import ProductionTimeline
    units,timeline = prefix['units'],ProductionTimeline.from_dict(prefix['timeline'])
    bible,plan = load_committed_plan(source,units,timeline)
    execution = _source_execution(source,plan,timeline)
    source_clips = execution['clips'] if execution is not None else plan['clips']
    accepted = load_accepted_batches(source,units,timeline,bible,plan)
    choice_map=_choices(accepted)
    proof=require_scene_revision(source) if 'scene_revision' in source.options else None
    if proof is not None:
        from ._scene_revision_readers import canonical_choice
        for scene in plan['scenes']:
            sid=scene['scene_id']
            if sid not in choice_map and 'choice:'+sid in proof['imports']:
                choice_map[sid]=canonical_choice(source,sid,proof)
    choices=[choice_map[s['scene_id']] for s in plan['scenes'] if s['scene_id'] in choice_map]
    run = Path(source.options['script_path']).parent.parent
    clips,upscale,effects = [],[],[]
    context = None
    if any((run/'production/scene-clips'/c['clip_id']).exists() for c in source_clips):
        from .scene_clip_records import scene_context,validate_clip
        context = scene_context(source,units,timeline)
    parents = {};media_context=None;extractions={}
    for budget in source_clips:
        cid = budget['clip_id']; record = None
        if proof is not None and 'clip:'+cid in proof['imports']:
            from ._scene_revision_readers import inherited_clip_record
            record=inherited_clip_record(source,cid,context=proof)
            parents[cid]=record
        elif context is not None:
            row = next(r for r in context['rows'] if r['budget']['clip_id']==cid)
            parent = parents.get(budget['parent_clip_id'])
            if budget['parent_clip_id'] is None or parent is not None:
                record = validate_clip(context,row,parent)
                if record is not None and record['accepted'] is not None and record['rejected'] is None: parents[cid] = record
        status = 'accepted' if record and record['accepted'] and not record['rejected'] else 'rejected' if record and record['rejected'] else 'pending'
        clips.append(dict(clip_id=cid,record=record['clip'] if record else None,acceptance=record['accepted'] if record else None,status=status))
        folder = run/'production/scene-clips'/cid
        terminal=None
        if (folder/'terminal.json').exists():
            from .scene_comfy_transactions import validate_scene_terminal
            from .scene_clip_records import graph_for
            terminal_row=next(r for r in context['rows'] if r['budget']['clip_id']==cid)
            terminal=validate_scene_terminal(context['store'],context['store'].read(folder/'request.json'),graph_for(context,terminal_row))
        if (folder/'intent.json').exists() and record is None and terminal is None:
            effects.append(dict(node='clips:'+cid,intent_sha256=canonical_digest(read_json(folder/'intent.json')),
                status='running' if (folder/'accepted.json').exists() else 'unknown'))
        for i in range(budget['retained_frames']):
            fid = cid+f':frame_{i+1:06d}'; frame_folder = run/'production/scene-upscale'/cid/f'frame_{i+1:06d}'
            value = None;terminal=None
            has_frame=(frame_folder/'frame.json').exists() or (proof is not None and 'upscale:'+fid in proof['imports'])
            if has_frame or (frame_folder/'terminal.json').exists():
                from .scene_media_records import scene_media_context
                from ._scene_upscale_records import validate_extraction,validate_frame
                from ._scene_revision_origin_clips import source_clip_required
                if media_context is None:media_context=scene_media_context(source,units,timeline)
                frame_row=next(r for r in media_context['rows'] if r['frame_id']==fid)
                if (frame_folder/'terminal.json').exists():
                    from .scene_upscale_transactions import validate_scene_terminal
                    from ._scene_upscale_records import graph_for
                    terminal=validate_scene_terminal(media_context['store'],media_context['store'].read(frame_folder/'request.json'),graph_for(media_context,frame_row))
                    if has_frame:raise ProductionRefused('original terminal conflicts with technical frame')
                media=source_clip_required(source,cid) and fid not in excluded_frames
                if has_frame and (cid,media) not in extractions:
                    clip=next(c for c in media_context['scene_clips']['clips'] if c['clip_id']==cid)
                    extractions[cid,media]=validate_extraction(media_context,clip,media=media)
                if has_frame:value=validate_frame(media_context,frame_row,extractions[cid,media],media=media)
            upscale.append(dict(frame_id=fid,record=value,status='ready' if value else 'pending'))
            if (frame_folder/'intent.json').exists() and value is None and terminal is None:
                effects.append(dict(node='upscale:'+fid,intent_sha256=canonical_digest(read_json(frame_folder/'intent.json')),
                    status='running' if (frame_folder/'accepted.json').exists() else 'unknown'))
    for scene in plan['scenes']:
        for intent in (run/'production/jimeng'/scene['scene_id']).glob('request_*/intent.json'):
            terminal=_image_terminal(source,scene,bible,plan,intent) if intent.with_name('terminal.json').exists() else None
            if (not intent.with_name('result.json').exists() or not (intent.parent.parent/'candidates.json').exists()) and terminal is None:
                effects.append(dict(node='images:'+scene['scene_id'],intent_sha256=canonical_digest(read_json(intent)),
                    status='running' if intent.with_name('accepted.json').exists() else 'unknown'))
    from .production_image_selection import validate_notification,_attempts,_attempt_state
    for batch_path in sorted((run/'production/image-selection').glob('image_batch_*/batch.json')):
        batch=read_json(batch_path)
        unselected=[sid for sid in plan['batches'][batch['batch_index']-1] if sid not in choice_map]
        if not unselected or not (batch_path.parent/'mail/notification.json').exists():continue
        notification=validate_notification(run,batch)
        for part in notification['parts']:
            for attempt in _attempts(run,batch,part):
                status,intent=_attempt_state(run,batch,part,attempt)
                if status=='unknown':
                    effects.extend(dict(node='choices:'+sid,intent_sha256=canonical_digest(intent),status='unknown') for sid in unselected)
    from .image_selection_records import _candidates
    from ._scene_revision_origins import inherited
    completed_images=[]
    for scene in plan['scenes']:
        sid=scene['scene_id'];path=run/'production/jimeng'/sid/'candidates.json'
        if path.exists() or inherited(source,'image',sid) is not None:
            _candidates(source,scene,path);completed_images.append(sid)
    options=deepcopy(source.options)
    # A trusted in-memory snapshot annotation, never a frozen options field.
    group_accepted=False
    if (run/'production/image-selection/complete-acceptance.json').exists() or inherited(source,'image_group','all') is not None:
        from .image_selection_records import require_complete_image_acceptance
        require_complete_image_acceptance(source,units,timeline);group_accepted=True
    options['_scene_revision_planning']=dict(identity=identity_from_options(source.options,reference_settings_sha256=reference_sha),
        completed_image_ids=completed_images,image_group_accepted=group_accepted,
        target_config=thaw(target_config.raw) if target_config is not None else None)
    result = dict(source_options=options,bible=bible,scene_plan=plan,image_choices=choices,
                clip_nodes=clips,upscale_nodes=upscale,pending_effects=effects)
    if execution is not None: result['scene_execution'] = execution
    return result


def _import_order(plan,invalidation,has_reference):
    result = []
    for domain in ('common','plan'):
        if 'all' in invalidation['reusable'][domain]: result.append((domain,'all'))
    if has_reference and ('plan','all') in result: result.append(('reference_settings','all'))
    for scene in plan['scenes']:
        sid = scene['scene_id']
        if sid in invalidation['reusable']['images']: result.append(('image',sid))
        if sid in invalidation['reusable']['choices']: result.append(('choice',sid))
    if 'all' in invalidation['reusable']['image_group']: result.append(('image_group','all'))
    result += [('clip',key) for key in invalidation['reusable']['clips']]
    result += [('upscale',key) for key in invalidation['reusable']['upscale']]
    return result


def _dependencies(domain,key,plan,existing,*,execution_clips=None):
    from ._scene_revision_plan import import_dependencies
    return import_dependencies(domain,key,plan,existing,execution_clips=execution_clips)


@revision_validation
def create_scene_revision(source_run,request_path):
    source_id = None; target = None
    try:
        from .production_inputs import load_frozen_inputs,freeze_inputs,revision_freeze_scope
        from ._scene_revision_origins import capture_origin,make_import_view
        source_run = validate_run_dir(source_run)
        source = load_frozen_inputs(source_run)
        if source.config.production_strategy!=STRATEGY: raise ProductionRefused('revision requires scene strategy')
        source_id = source_run.name
        if (source_run/'.make-video.lock').exists(): raise ProductionRefused('source has a write lock; resolve it in original run')
        options_bound = artifact(source_run/'production/options.json',root=source_run)
        request_path = Path(request_path)
        raw = stable_bytes(request_path,root=request_path.parent)
        from ..adapters.common import strict_json
        request = strict_json(raw.removeprefix(b'\xef\xbb\xbf'))
        from ..planning.scene_revision import REQUEST_FIELDS
        object_fields(request,REQUEST_FIELDS,'revision request')
        if request['source_options_sha256'] != options_bound['sha256']: raise ProductionRefused('revision source options SHA differs')
        revision_id = UUID(request['revision_id'])
        if str(revision_id)!=request['revision_id']: raise ProductionRefused('canonical revision UUID required')
        date = datetime.fromisoformat(request['requested_at'])
        if date.tzinfo is None or date>datetime.now(timezone.utc): raise ProductionRefused('invalid revision timestamp')
        preliminary = load_config(Path(request['config_path'])) if request['kind']=='reconfigure' else source.config
        name = date.astimezone(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+revision_id.hex[:12]
        candidate = preliminary.project_root/'runs'/name
        safe_path(candidate,preliminary.project_root/'runs'); validate_run_dir(candidate)
        if candidate.is_relative_to(source_run) or source_run.is_relative_to(candidate):
            raise ProductionRefused('revision target overlaps the read-only source')
        config,config_raw,voice_raw = _target_configuration(source,candidate,request)
        if request['output_path'] is not None:
            from .production_inputs import output_paths
            targets=output_paths(config,candidate,request['output_path'],check_existing=False)
            if set(targets.values()) & set(source.options['output_paths'].values()):
                raise ProductionRefused('revision output must not reserve an original source output path')
        from ..selection_config import parse_selection_email
        old_email = parse_selection_email(source.config.raw.get('selection_email'))
        new_email = parse_selection_email(config.raw.get('selection_email'))
        if (old_email.sender,old_email.recipient)!=(new_email.sender,new_email.recipient): raise ProductionRefused('revision cannot change confirmed email addresses')
        from ._scene_revision_reference import source_reference_context,target_reference_digest
        source_reference=source_reference_context(source)
        source_reference_sha=source_reference['digest'] if source_reference is not None else None
        from dataclasses import replace
        from types import SimpleNamespace
        effective_image=override_image_model(config.image_generation,request['image_model'] or source.options.get('image_model_override'))
        reference_target=SimpleNamespace(config=replace(config,image_generation=effective_image),options={})
        reference_sha=target_reference_digest(reference_target,source_reference)
        identity = configuration_identity(config,image_model=request['image_model'] or source.options.get('image_model_override'),reference_sha=reference_sha)
        snapshot = _snapshot(source,target_config=config,reference_sha=source_reference_sha,request=request,target_identity=identity)
        invalidation = plan_scene_revision(snapshot,request,identity)
        if invalidation['blocked_effects']: raise ProductionRefused('original paid effects unknown/running; reconcile original run first')
        if request['kind']=='reselect_images':
            from .image_selection_records import _candidates
            for choice in request['choices']:
                scene = next(s for s in snapshot['scene_plan']['scenes'] if s['scene_id']==choice['scene_id'])
                _,candidates = _candidates(source,scene,source_run/'production/jimeng'/choice['scene_id']/'candidates.json')
                if not any(all(c[k]==choice[k] for k in ('candidate_id','sha256')) for c in candidates): raise ProductionRefused('reselection candidate is not original completed result')
        # Validate all reusable origins before target allocation or media copying.
        nodes = _import_order(snapshot['scene_plan'],invalidation,reference_sha is not None and reference_sha==source_reference_sha)
        captures = {(d,k):capture_origin(source,d,k) for d,k in nodes}
        for captured in captures.values(): captured['guard'].verify_captured_bytes()
        if artifact(source_run/'production/options.json',root=source_run)!=options_bound: raise ProductionRefused('source options changed')
        if stable_bytes(request_path,root=request_path.parent)!=raw: raise ProductionRefused('revision request changed')
        existed = candidate.exists()
        if existed and not (candidate/'production/scene-revision/intent.json').is_file(): raise ProductionRefused('unowned revision target exists')
        candidate.mkdir(parents=True,exist_ok=True); target = candidate
        with RunLock(target) as held:
            store = RevisionStore(target,held)
            from ._scene_revision_copy import preflight_copies
            allowed={str(store.root/'copy-ready'/token(d,k)/(role+'.json')) for (d,k),value in captures.items() for role,_ in value['media']}
            preflight_copies(store.root,target.name,expected=allowed);store.copies_preflighted=True
            source_request = dict(path=str(store.path('request.json')),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            intent = dict(schema_version=2,production_strategy=STRATEGY,run_id=target.name,revision_id=str(revision_id),
                source_run_id=source_id,source_run_dir=str(source_run),source_options=options_bound,request=source_request,
                target_identity=identity,invalidation=invalidation,created_at=request['requested_at'])
            store.save('intent.json',intent); boundary('intent')
            store.image('request.json',raw)
            if config_raw is not None:
                store.image('config-source.json',config_raw); store.image('voice-source.json',voice_raw)
            imports,existing,common_view = [],{},None
            for domain,key in nodes:
                iid = domain+':'+key; capture = captures[domain,key]
                dependencies = _dependencies(domain,key,snapshot['scene_plan'],existing,
                    execution_clips=snapshot.get('scene_execution',{}).get('clips'))
                mappings = []
                for role,original in capture['media']:
                    local = copy_identity(store,iid,domain,key,role,original,guard=capture['guard'])
                    mappings.append(dict(role=role,source=original,target=local))
                view = make_import_view(target,domain,key,capture['value'],mappings,common_view=common_view)
                view_path = store.save(Path('views')/domain/(token(domain,key)+'.json'),view); boundary('view')
                sidecar = dict(schema_version=2,production_strategy=STRATEGY,run_id=target.name,import_id=iid,domain=domain,key=key,
                    source_run_id=source_id,source_options_sha256=options_bound['sha256'],source_identity_sha256=canonical_digest(capture['value']),
                    dependency_import_ids=dependencies,source_json_snapshot=capture['snapshot'],raw_files=capture['raw_files'],
                    source_artifacts=[v for _,v in capture['media']],local_artifacts=mappings,view=view,
                    view_sha256=canonical_digest(view),view_artifact=artifact(view_path,root=store.root),created_at=request['requested_at'])
                path = store.save(Path('imports')/(token(domain,key)+'.json'),sidecar); boundary('import')
                imports.append(artifact(path,root=store.root)); existing[iid] = sidecar
                if domain=='common': common_view = view
            for capture in captures.values(): capture['guard'].verify_captured_bytes()
            index = store.save('imports.json',dict(schema_version=2,production_strategy=STRATEGY,run_id=target.name,revision_id=str(revision_id),imports=imports))
            invalidation_path = store.save('invalidation.json',invalidation); boundary('imports')
            commit = {k:v for k,v in intent.items() if k!='invalidation'}
            commit.update(invalidation=artifact(invalidation_path,root=store.root),imports=artifact(index,root=store.root))
            commit_path = store.save('commit.json',commit); boundary('commit')
            commit_bound = artifact(commit_path,root=store.root)
            if configuration_identity(config,image_model=request['image_model'] or source.options.get('image_model_override'),reference_sha=reference_sha)!=identity:
                raise ProductionRefused('target identity changed before freezing')
            with revision_freeze_scope(store):
                frozen = freeze_inputs(config,target,text=source.script.text,
                    raw_script_bytes=stable_bytes(source.options['script_path'],root=source_run),
                    image_model=request['image_model'] or source.options.get('image_model_override'),
                    cpu_planner=source.options['cpu_planner'],output_path=request['output_path'],scene_revision=commit_bound)
            if target_reference_digest(frozen,source_reference)!=reference_sha:
                raise ProductionRefused('target reference identity changed while freezing')
            boundary('options')
            validate_revision_structure(frozen.options,target); require_scene_revision(frozen)
            if (frozen.config.raw.get('scene_rendering',{}).get('mode') is not None
                    and 'all' in invalidation['reusable']['common'] and 'all' in invalidation['reusable']['plan']):
                # Establish a new target budget only after imported semantic inputs
                # exist. An intermediate revision can then be revised without video.
                from .scene_revision_records import load_scene_common_prefix
                from .image_selection_records import load_committed_plan
                from .scene_execution_records import ensure_scene_execution
                target_units,target_timeline=load_scene_common_prefix(frozen)
                _,target_plan=load_committed_plan(frozen,target_units,target_timeline)
                ensure_scene_execution(frozen,target_plan,target_timeline,lock=held)
            for capture in captures.values(): capture['guard'].verify_captured_bytes()
            store.save('ready.json',dict(schema_version=2,run_id=target.name,revision_id=str(revision_id),commit=commit_bound,
                options=artifact(target/'production/options.json',root=target),created_at=frozen.options['created_at']))
            boundary('ready')
        return SceneRevisionResult(source_run_id=source_id,run_id=target.name,run_dir=target,status='revision_ready',
            revision_commit=commit_path,log_dir=target/'logs/production')
    except (Exception,KeyboardInterrupt) as exc:
        from ..adapters.jimeng import redact
        return SceneRevisionResult(source_run_id=source_id,run_id=target.name if target else None,run_dir=target,
            status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'blocked' if isinstance(exc,ValueError) else 'failed',
            log_dir=target/'logs/production' if target else None,
            error=dict(kind=type(exc).__name__,message=redact('Scene revision preparation stopped: '+(str(exc) or type(exc).__name__)),evidence_paths=[]))
