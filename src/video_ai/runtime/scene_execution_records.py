"""Frozen admission closure and lock-owned versioned execution budgets."""
import os
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from ..planning.production_scenes import canonical_digest
from ..planning.scene_execution import build_scene_execution_budget, validate_scene_execution_budget
from ..planning.scene_revision import identity_from_options
from ..planning.scene_video_prompts import parse_scene_rendering
from .manifest import hash_file, thaw
from .production_state import ProductionRefused, RunLock, json_bytes, object_fields, run_path, write_exclusive
from .scene_revision_records import artifact
from .verification import validation_memo, verified_read
from ._whole_scene_admission import ALGORITHM, EvidenceReader, content, load_evidence, require

_writer_admissions=ContextVar('scene_execution_writer_admissions',default=None)


def _protect_whole_inputs(function):
    @wraps(function)
    def protected(frozen,*args,**kwargs):
        if rendering_mode(frozen)!='whole_scene_v1':return function(frozen,*args,**kwargs)
        from .verification import whole_input_protection
        with whole_input_protection():return function(frozen,*args,**kwargs)
    return protected


def verified_scene_execution_write(function):
    """Keep immutable input digests for an explicit writer's read window.

    Windows mandatory read handles prevent mutation throughout the invocation;
    each guard still validates its metadata and all unprotected file bytes.
    The historical rendering branches retain their original call behavior.
    """
    @wraps(function)
    @_protect_whole_inputs
    def wrapped(frozen,*args,**kwargs):
        if rendering_mode(frozen) is None:return function(frozen,*args,**kwargs)
        from .verification import validation_session,writable_validation_session
        options=getattr(frozen,'options',{})
        scope=lambda: writable_validation_session(_run(frozen)) if 'script_path' in options else validation_session()
        if _writer_admissions.get() is not None:
            with scope():return function(frozen,*args,**kwargs)
        token=_writer_admissions.set({})
        try:
            with scope():return function(frozen,*args,**kwargs)
        finally:_writer_admissions.reset(token)
    return wrapped


def rendering_mode(frozen):
    # Historical public refusal paths may carry only strategy/options before
    # preparation validation. Keep an explicit frozen mode if one is available.
    raw=getattr(getattr(frozen,'config',None),'raw',None)
    if raw is None:
        raw=getattr(frozen,'options',{}).get('config_snapshot',{}).get('raw',{})
    if 'scene_rendering' not in raw:return None
    settings=raw['scene_rendering']
    return parse_scene_rendering(settings).get('mode')


def _run(frozen):return Path(frozen.options['script_path']).parent.parent


def _path(frozen,name):
    run=_run(frozen)
    return run_path(run,run/'production/scene-rendering'/name)


def load_whole_scene_evidence(path,*,reader=None):
    """Return root Artifact, assessment, case, graph, actual read artifacts,
    directory inventories, original root bytes and a recheckable byte guard.
    A genuine frozen root must have its matching exact closure alongside it.
    """
    path=Path(path)
    if path.name!='whole-scene-evidence.json':return load_evidence(path,reader=reader)
    from .manifest import validate_run_dir
    run=validate_run_dir(path.parents[2])
    require(path==run/'production/scene-rendering/whole-scene-evidence.json','accepted evidence frozen path')
    evidence=load_evidence(path,reader=reader,allow_frozen=True)
    io=EvidenceReader(reader)
    closure=io.json(path.with_name('evidence-closure.json'))
    object_fields(closure,('schema_version','algorithm','root','artifacts'),'whole admission closure')
    require(type(closure['schema_version']) is int and closure['schema_version']==1 and closure['algorithm']==ALGORITHM,'closure algorithm/schema')
    require(closure['root']==evidence['root'] and closure['artifacts']==[v for v in evidence['artifacts'] if v['path']!=str(path)],'frozen external evidence closure differs')
    return evidence


def verify_current_environment(frozen,evidence):
    """Bind this run's current models, workflow and tools to the accepted case."""
    cfg=frozen.config;case=evidence['case'];dependencies=case['dependencies']
    # Current run inputs are independently frozen roles, not historical external
    # evidence leaves. Retain their captures in the guard without changing the
    # historical closure's serialized artifact list.
    environment=EvidenceReader()
    require(cfg.media.profile.name=='fast' and cfg.media.profile.width==768 and cfg.media.profile.height==432 and cfg.media.profile.native_fps==16,'whole requires fast 768x432 native16')
    require(thaw(cfg.raw.get('scene_continuity'))==dict(schema_version=1,policy='advisory_v1'),'whole requires advisory continuity')
    for role in ('wan_high','wan_low','text_encoder','vae'):
        expected=dependencies['model/'+role]
        require(Path(cfg.models[role])==Path(expected['path']),'current model path differs: '+role)
        evidence['guard'].capture(cfg.models[role],expected)
    for role in ('comfy_python','ffmpeg','ffprobe'):
        expected=dependencies['tool/'+role]
        require(Path(cfg.tools[role])==Path(expected['path']),'current tool path differs: '+role)
        evidence['guard'].capture(cfg.tools[role],expected)
    require(Path(cfg.tools['comfy_root'])==Path(case['runtime']['tools']['comfy_root']),'current Comfy root differs')
    from .paths import SOURCE_ROOT
    source_inventory=evidence['guard'].values[case['source_inventory']['path']]
    for role in ('wan','wan_mapping'):
        configured=Path(cfg.workflows[role])
        records=getattr(frozen,'options',{}).get('execution_policy',{}).get('input_identities',{})
        if 'workflow/'+role in records:
            expected={k:records['workflow/'+role][k] for k in ('path','bytes','sha256')}
            require(Path(expected['path'])==configured,'frozen workflow path differs')
            environment.capture(configured,expected)
        original_name='wan22_i2v_14b_api'+('.mapping.json' if role=='wan_mapping' else '.json')
        originals=[v for v in source_inventory if Path(v['path']).name==original_name and 'workflows' in Path(v['path']).parts]
        require(len(originals)==1,'original inference workflow identity missing')
        for current in {configured,SOURCE_ROOT/'workflows'/original_name}:
            actual=environment.capture(current)
            require(all(actual[k]==originals[0][k] for k in ('bytes','sha256')),'current inference workflow bytes differ')
    from ..experiments.whole_scene_case import validate_model_loading
    from .production_visual_templates import validate_production_model_paths
    from .workflows import WorkflowTemplate
    from .production_visual_templates import validate_fixed_visual_template
    validate_production_model_paths(cfg)
    validate_model_loading(cfg.models,case['runtime']['model_root'],cfg.tools['comfy_root'])
    # These template bytes are part of this run's frozen identity. Validate the
    # same fixed sampling/connectivity contract as the original experiment.
    template=WorkflowTemplate.load(cfg.workflows['wan'],cfg.workflows['wan_mapping'],cfg.models)
    validate_fixed_visual_template(template,'wan')
    environment.verify()
    evidence['guard'].guards.append(environment)
    evidence['environment_guard']=environment


def freeze_whole_scene_evidence(config,run,identities,*,save):
    settings=parse_scene_rendering(config.raw.get('scene_rendering')) if 'scene_rendering' in config.raw else {}
    if settings.get('mode')!='whole_scene_v1':return
    evidence=load_whole_scene_evidence(settings['whole_scene_evidence'])
    from types import SimpleNamespace
    verify_current_environment(SimpleNamespace(config=config),evidence)
    path=run_path(run,run/'production/scene-rendering/whole-scene-evidence.json')
    save(path,evidence['raw'])
    root=artifact(path,root=run)
    # The input root can itself be a prior run's identical frozen copy. It is
    # replaced by this run's root; the external closure remains anchored to the
    # original pinned assessment, never to a chain of copied root aliases.
    from ._whole_scene_admission import PINNED_ROOT
    copied_source=evidence['root']['path'] if Path(evidence['root']['path'])!=PINNED_ROOT/'final-assessment.json' else None
    closure=dict(schema_version=1,algorithm=ALGORITHM,root=root,
        artifacts=[v for v in evidence['artifacts'] if v['path'] not in (str(path),copied_source)])
    destination=run_path(run,run/'production/scene-rendering/evidence-closure.json')
    save(destination,json_bytes(closure))
    identities['whole_scene_evidence']=thaw(hash_file(path))
    identities['whole_scene_evidence_closure']=thaw(hash_file(destination))
    evidence['guard'].verify()


@verified_read
@_protect_whole_inputs
def _whole_scene_admission_cache(frozen):
    admissions=_writer_admissions.get()
    if admissions is None:admissions=validation_memo('whole_scene_admission')
    key=canonical_digest(dict(options=thaw(frozen.options),raw=thaw(frozen.config.raw))) if admissions is not None else None
    return admissions,key


def cached_whole_scene_admission_guard(frozen):
    """Read the current operation's existing guard binding without admission/I/O."""
    if rendering_mode(frozen)!='whole_scene_v1':return None
    admissions,key=_whole_scene_admission_cache(frozen)
    evidence=None if admissions is None else admissions.get(key)
    return evidence.get('guard') if isinstance(evidence,dict) else None


def verify_whole_scene_frozen(frozen,*,reader=None):
    """Rebuild the external semantic closure, inventories and current environment.

    The returned guard has verify() for byte/inventory rechecks. Only within a
    writer invocation or validation session may authenticated semantics be reused;
    every reuse still hashes captured bytes and checks directory inventories.
    """
    records=frozen.options['execution_policy']['input_identities']
    roles={'whole_scene_evidence','whole_scene_evidence_closure'}
    if rendering_mode(frozen)!='whole_scene_v1':
        require(not roles.intersection(records),'orphan whole evidence roles')
        return None
    require(roles<=set(records),'whole evidence roles missing')
    admissions,key=_whole_scene_admission_cache(frozen)
    if admissions is not None and key in admissions:
        evidence=admissions[key]
        evidence['guard'].verify()
        return evidence
    io=EvidenceReader(reader)
    for role,name in (('whole_scene_evidence','whole-scene-evidence.json'),('whole_scene_evidence_closure','evidence-closure.json')):
        require(Path(records[role]['path'])==_path(frozen,name),'frozen evidence path differs')
        io.capture(records[role]['path'],content({k:records[role][k] for k in ('path','bytes','sha256')}))
    closure=io.json(records['whole_scene_evidence_closure']['path'])
    object_fields(closure,('schema_version','algorithm','root','artifacts'),'whole admission closure')
    require(type(closure['schema_version']) is int and closure['schema_version']==1 and closure['algorithm']==ALGORITHM,'closure algorithm/schema')
    root=io.capture(records['whole_scene_evidence']['path'])
    require(closure['root']==root,'closure root differs')
    evidence=load_evidence(root['path'],reader=reader,allow_frozen=True)
    expected=[v for v in evidence['artifacts'] if v['path']!=root['path']]
    require(closure['artifacts']==expected,'external evidence closure differs')
    verify_current_environment(frozen,evidence)
    evidence['guard'].guards.append(io)
    evidence['guard'].verify()
    if admissions is not None:admissions[key]=evidence
    return evidence


def _identity(frozen):
    mode=rendering_mode(frozen)
    evidence=verify_whole_scene_frozen(frozen) if mode=='whole_scene_v1' else None
    return dict(run_id=frozen.options['run_id'],mode=mode or 'segmented_v1',
        rendering_identity_sha256=canonical_digest(identity_from_options(thaw(frozen.options)) if mode is not None else thaw(frozen.options)),
        admission=evidence['root'] if evidence is not None else None)


def execution_artifact(frozen):
    if rendering_mode(frozen) is None:raise ProductionRefused('legacy execution has no persisted budget Artifact')
    path=_path(frozen,'execution-budget.json')
    if not path.exists():raise ProductionRefused('execution budget missing')
    return artifact(path,root=_run(frozen))


def _validate(value,frozen,plan,timeline,expected):
    try:return validate_scene_execution_budget(value,plan,timeline,expected=expected)
    except (TypeError,KeyError,ValueError) as exc:raise ProductionRefused('execution budget differs from frozen inputs') from exc


@verified_read
def load_scene_execution(frozen,plan,timeline,*,reader=None):
    if rendering_mode(frozen) is None:
        # Historical callers continue consuming the semantic clips directly;
        # this in-memory view has no filesystem side effects.
        return build_scene_execution_budget(plan,timeline,**_identity(frozen))
    path=_path(frozen,'execution-budget.json')
    if not path.is_file():raise ProductionRefused('execution budget missing; readonly recovery refused')
    expected=_identity(frozen)
    io=EvidenceReader(reader)
    return _validate(io.json(path),frozen,plan,timeline,expected)


def _owned(frozen,lock):
    run=_run(frozen)
    if not isinstance(lock,RunLock) or lock.run_dir!=run:
        raise ProductionRefused('execution budget requires held run lock')
    io=EvidenceReader()
    if not lock.path.is_file() or io.json(lock.path)!=lock.owner:
        raise ProductionRefused('execution budget lost held run lock')


def _downstream(frozen):
    run=_run(frozen)
    for pattern in ('scene-clip*','scene-upscale*','scene-composition*','scene-final*','scene-delivery*'):
        for entry in (run/'production').glob(pattern):
            if entry.is_file() or entry.is_dir() and any(entry.rglob('*')):
                raise ProductionRefused('execution budget missing with persisted downstream records')
    for relative in ('production/scene-clips','production/scene-upscale','production/scene-composition',
        'production/scene-observations','production/scene-continuity','comfy/output','logs/production/scene-clips',
        'logs/production/scene-clips','logs/production/scene-upscale','production/scene-delivery'):
        folder=run/relative
        if folder.is_dir() and any(folder.rglob('*')):
            # The frozen continuity policy is an input, not a downstream record.
            if relative=='production/scene-continuity' and list(folder.rglob('*'))==[folder/'policy.json']:continue
            raise ProductionRefused('execution budget missing with persisted downstream records')


@verified_read
def ensure_scene_execution(frozen,plan,timeline,*,lock,reader=None):
    if rendering_mode(frozen) is None:return load_scene_execution(frozen,plan,timeline,reader=reader)
    _owned(frozen,lock)
    path=_path(frozen,'execution-budget.json')
    if path.exists():return load_scene_execution(frozen,plan,timeline,reader=reader)
    expected=_identity(frozen)
    try:value=build_scene_execution_budget(plan,timeline,**expected)
    except (TypeError,KeyError,ValueError) as exc:raise ProductionRefused('execution budget derivation refused') from exc
    _downstream(frozen)
    temporary=_path(frozen,'execution-budget.'+lock.owner['token']+'.tmp')
    # A previous invocation can leave an exact deterministic budget after fsync.
    # Validate and preserve it; only this owner's fresh temporary is promoted.
    leftovers=EvidenceReader(reader)
    for previous in path.parent.glob('execution-budget.*.tmp'):
        if previous!=temporary:_validate(leftovers.json(previous),frozen,plan,timeline,expected)
    if temporary.exists():
        io=EvidenceReader(reader)
        _validate(io.json(temporary),frozen,plan,timeline,expected)
        # Only the current owner's exact complete temporary may be recovered.
        from .production_state import sync_file
        sync_file(temporary)
    else:write_exclusive(temporary,value)
    _owned(frozen,lock)
    if path.exists():raise ProductionRefused('execution budget appeared during commit')
    os.rename(temporary,path)
    _owned(frozen,lock)
    return load_scene_execution(frozen,plan,timeline,reader=reader)
