"""Immutable schema-2 scene media evidence and read-only acceptance facades."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import stat
from threading import get_ident

from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from ..planning.scene_media import plan_scene_upscale
from .manifest import thaw,validate_run_dir
from .production_state import ProductionRefused, object_fields, run_path,ArtifactStamp
from .scene_clip_records import SceneClipStore, equal


@dataclass(frozen=True)
class SceneMediaResult:
    schema_version: int = 2
    production_strategy: str = STRATEGY
    run_id: str | None = None
    run_dir: Path | None = None
    status: str = 'blocked'
    active_stage: str = 'upscale'
    upscaled_clips: Path | None = None
    candidate: Path | None = None
    final_observation_template: Path | None = None
    delivery_receipt: Path | None = None
    log_dir: Path | None = None
    error: dict | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 2 or self.production_strategy != STRATEGY:
            raise ValueError('invalid scene media schema')
        if self.status not in ('upscale_ready','awaiting_final_review','final_review_ready','final_review_failed','delivered','blocked','failed','interrupted'):
            raise ValueError('invalid scene media status')
        if self.active_stage not in ('upscale','composition','final_review','delivery'): raise ValueError('invalid media stage')
        admitted=self.status in ('upscale_ready','awaiting_final_review','final_review_ready','final_review_failed','delivered')
        if admitted and self.run_dir is None: raise ValueError('admitted result requires known prepared run')
        if self.status=='upscale_ready' and self.upscaled_clips is None: raise ValueError('upscale ready requires complete acceptance path')
        if self.status in ('awaiting_final_review','final_review_ready','final_review_failed','delivered') and self.candidate is None:
            raise ValueError('final review/delivery requires candidate')
        if self.status=='delivered' and self.delivery_receipt is None: raise ValueError('delivery requires external receipt')
        if self.run_dir is None:
            if any(getattr(self,k) is not None for k in ('run_id','upscaled_clips','candidate','final_observation_template','delivery_receipt','log_dir')):
                raise ValueError('media result requires prepared run')
        else:
            run = validate_run_dir(Path(self.run_dir))
            if not run.is_absolute() or self.run_id != run.name: raise ValueError('invalid result run')
            object.__setattr__(self,'run_dir',run)
            for key in ('upscaled_clips','candidate','final_observation_template','delivery_receipt','log_dir'):
                value = getattr(self,key)
                if value is not None:
                    value = Path(value)
                    if not value.is_absolute(): raise ValueError('absolute result paths required')
                    if key != 'delivery_receipt': run_path(run,value)
                    if key != 'log_dir' and not value.is_file(): raise ValueError('result artifact missing')
                    object.__setattr__(self,key,value)
        if self.error is not None:
            object_fields(self.error,('kind','message','evidence_paths'),'media error')
            if any(not isinstance(self.error[k],str) or not self.error[k] for k in ('kind','message')):
                raise ValueError('nonempty media error kind/message required')
            if not isinstance(self.error['evidence_paths'],list) or any(not isinstance(p,str) or not Path(p).is_absolute() for p in self.error['evidence_paths']):
                raise ValueError('absolute media error evidence paths required')
        json.dumps(self.to_dict(),allow_nan=False)

    def to_dict(self): return thaw(self)

    @property
    def exit_code(self):
        return dict(upscale_ready=0,awaiting_final_review=3,final_review_ready=0,final_review_failed=2,
                    delivered=0,blocked=2,failed=1,interrupted=130)[self.status]


class SceneMediaStore(SceneClipStore):
    def __init__(self,frozen,run_dir,*,paths=None,lock=None,clip_ids=()):
        super().__init__(frozen,run_dir,paths=paths,lock=lock,clip_ids=clip_ids)
        self.root = self._lexical(self.run_dir/'production/scene-upscale')
        self.caller_thread = get_ident()
        self.guard_empty_paths = set()
        self.guard_absent_paths = set()
        self.guard_tool_stamps = {}
        self.captured_evidence_json = set()

    def _lexical(self,target):
        target=Path(target)
        if not target.is_absolute() or '..' in target.parts: raise ProductionRefused('absolute non-traversing media path required')
        for ancestor in (target,*target.parents):
            try: attributes=ancestor.lstat()
            except FileNotFoundError: continue
            if stat.S_ISLNK(attributes.st_mode) or getattr(attributes,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ProductionRefused('scene media path redirected')
        return run_path(self.run_dir,target)

    def path(self,relative):
        target=Path(relative)
        if not target.is_absolute(): target=self.root/target
        self._lexical(target)
        return super().path(target)

    def artifact(self,path):
        self._lexical(path)
        return super().artifact(path)

    def validate_artifact(self,value):
        object_fields(value,('path','bytes','sha256'),'scene media Artifact')
        self._lexical(value['path'])
        return super().validate_artifact(value)

    def verify_global(self):
        self.assert_owned()
        self.verify_captured_bytes()
        for stamp in self.frozen.options['model_stamps'].values(): ArtifactStamp.from_dict(thaw(stamp)).verify()
        self.verify_tools()

    def verify_captured_bytes(self):
        """Read-only guard audit, also valid while performing lock-free acceptance."""
        if self.revision_context is not None:self.revision_context['guard'].verify_captured_bytes()
        for artifact in self.guard_paths.values(): self.validate_artifact(artifact)
        for directory,expected in self.guard_directories.items():
            folder=self._lexical(directory)
            if {str(p) for p in folder.rglob('*.json')}!=set(expected): raise ProductionRefused('captured JSON inventory changed')
        for value in self.guard_absent_paths:
            path=self._lexical(value)
            if path.exists(): raise ProductionRefused('promoted original staging unexpectedly reappeared')
        for value in self.guard_empty_paths:
            path=self._lexical(value)
            if not path.is_file() or path.stat().st_size!=0: raise ProductionRefused('captured empty evidence changed')

    def verify_tools(self):
        for stamp in self.guard_tool_stamps.values(): stamp.verify()

    def bind_artifact(self,artifact):
        """Extend byte guards without replacing an earlier admitted identity."""
        key=artifact['path']
        if key in self.guard_absent_paths or key in self.guard_empty_paths:
            raise ProductionRefused('captured absent/empty evidence changed: '+key)
        if key in self.guard_paths:
            self.validate_artifact(self.guard_paths[key])
            equal(artifact,self.guard_paths[key],'earlier captured Artifact')
        self.validate_artifact(artifact); self.guard_paths[key]=deepcopy(artifact)

    def snapshot_json(self,*,files=(),directories=()):
        """Immutable raw JSON bytes and inventories captured before semantic admission."""
        inventories={}; names=set()
        for value in directories:
            folder=self._lexical(self.run_dir/Path(value))
            inventory=frozenset(str(p) for p in folder.rglob('*.json'))
            if str(folder) in self.guard_directories:
                equal(sorted(inventory),sorted(self.guard_directories[str(folder)]),'earlier JSON inventory snapshot')
            inventories[str(folder)]=inventory; names.update(inventory)
        capture_paths=frozenset(names)
        for value in files: names.add(str(self._lexical(self.run_dir/Path(value))))
        artifacts={}; bodies={}
        for name in sorted(names):
            path=self._lexical(name)
            if not path.is_file(): raise ProductionRefused('JSON snapshot required file missing: '+name)
            if name in self.guard_paths: self.validate_artifact(self.guard_paths[name])
            artifact=self.artifact(path); raw=path.read_bytes()
            if len(raw)!=artifact['bytes'] or hashlib.sha256(raw).hexdigest()!=artifact['sha256']:
                raise ProductionRefused('JSON snapshot changed while reading: '+name)
            artifacts[name]=artifact; bodies[name]=raw
        return dict(directories=inventories,artifacts=artifacts,bodies=bodies,capture_paths=capture_paths)

    def verify_json_snapshot(self,snapshot):
        for directory,expected in snapshot['directories'].items():
            folder=self._lexical(directory)
            if {str(p) for p in folder.rglob('*.json')}!=set(expected):
                raise ProductionRefused('JSON inventory changed after admission snapshot: '+directory)
        for path,artifact in snapshot['artifacts'].items():
            try: self.validate_artifact(artifact)
            except (ProductionRefused,OSError,ValueError) as exc:
                raise ProductionRefused('JSON snapshot bytes changed after admission: '+path+': '+str(exc)) from exc

    def adopt_json_snapshot(self,snapshot):
        from ..adapters.common import strict_json
        self.verify_json_snapshot(snapshot)
        for directory,inventory in snapshot['directories'].items():
            if directory in self.guard_directories:
                equal(sorted(inventory),sorted(self.guard_directories[directory]),'earlier JSON inventory snapshot')
            self.guard_directories[directory]=set(inventory)
        for path,artifact in snapshot['artifacts'].items(): self.bind_artifact(artifact)
        # Parse exactly the bytes the semantic validator saw; never reopen and
        # bless a later authored observation or a changed transaction index.
        # Fixed options/plan files bind their original bytes. Descriptive config
        # source identities inside options are not run-local media Artifacts.
        for path in snapshot['capture_paths']:
            raw=snapshot['bodies'][path]
            self.capture_admitted(strict_json(raw.decode('utf-8-sig').encode('utf-8')))
        self.verify_json_snapshot(snapshot)

    def capture_unhashed_inputs(self,snapshot,*,pcm_paths=()):
        """Bind original PCM and command output bytes before semantic admission."""
        from ..adapters.common import strict_json
        for path in pcm_paths: self.bind_artifact(self.artifact(path))
        for path in snapshot['capture_paths']:
            raw=snapshot['bodies'][path]
            self.capture_command_evidence(strict_json(raw.decode('utf-8-sig').encode('utf-8')))
        self.verify_json_snapshot(snapshot)

    def verify_admission_snapshot(self,snapshot):
        self.verify_json_snapshot(snapshot)
        try:
            self.verify_captured_bytes()
            for stamp in self.frozen.options['model_stamps'].values(): ArtifactStamp.from_dict(thaw(stamp)).verify()
            self.verify_tools()
        except (ProductionRefused,OSError,ValueError) as exc:
            raise ProductionRefused('admission snapshot dependency changed: '+str(exc)) from exc

    def capture_admitted(self,value):
        """Capture all raw bytes referenced by an already-validated JSON object."""
        if self.revision_context is not None and self.revision_context['guard'].is_registered(value):
            self.revision_context['guard'].verify_captured_bytes(); return
        if isinstance(value,dict):
            from .production_composition_records import COMMAND_FIELDS,command
            if set(value)==set(COMMAND_FIELDS):
                command(value,self.run_dir)
                for key in ('stdout_path','stderr_path'):
                    path=self._lexical(value[key])
                    if not path.is_file(): raise ProductionRefused('admitted command evidence missing')
                    if path.stat().st_size: self.bind_artifact(self.artifact(path))
                    else:
                        if str(path) in self.guard_paths: self.validate_artifact(self.guard_paths[str(path)])
                        self.guard_empty_paths.add(str(path))
                return
            if {'staging','target','source','recipe','operation'}<=set(value) and all(
                    isinstance(value[k],dict) and set(value[k])=={'path','bytes','sha256'} for k in ('staging','target')):
                staging=self._lexical(value['staging']['path']); target=self._lexical(value['target']['path'])
                if not staging.exists() and target.exists():
                    equal({k:value['staging'][k] for k in ('bytes','sha256')},
                          {k:value['target'][k] for k in ('bytes','sha256')},'admitted promoted staging identity')
                    self.validate_artifact(value['target']); self.guard_absent_paths.add(str(staging))
                    self.capture_admitted({k:v for k,v in value.items() if k!='staging'})
                    return
            if {'staging_directory','target_directory','staging_frames','target_frames'}<=set(value):
                staging=self._lexical(value['staging_directory']); target=self._lexical(value['target_directory'])
                if not staging.exists() and target.exists():
                    if len(value['staging_frames'])!=len(value['target_frames']): raise ProductionRefused('admitted extraction staging count differs')
                    for a,b in zip(value['staging_frames'],value['target_frames']):
                        equal({k:v for k,v in a.items() if k!='image'},{k:v for k,v in b.items() if k!='image'},'admitted extraction staging indices')
                        equal({k:a['image'][k] for k in ('bytes','sha256')},{k:b['image'][k] for k in ('bytes','sha256')},'admitted extraction staging bytes')
                    self.guard_absent_paths.add(str(staging))
                    self.capture_admitted({k:v for k,v in value.items() if k!='staging_frames'})
                    return
            if {'path','bytes','sha256'}<=set(value):
                artifact={k:value[k] for k in ('path','bytes','sha256')}
                if type(artifact['bytes']) is int and artifact['bytes']==0:
                    path=self._lexical(artifact['path'])
                    if (path.parent.name!='http' or path.suffix!='.body' or not path.is_file() or path.stat().st_size!=0
                            or artifact['sha256']!=hashlib.sha256(b'').hexdigest()):
                        raise ProductionRefused('only admitted empty HTTP body may have zero bytes')
                    self.guard_empty_paths.add(str(path))
                else:
                    self.bind_artifact(artifact)
                    path=Path(artifact['path'])
                    if path.suffix=='.json' and path.is_relative_to(self.run_dir/'logs/production') and str(path) not in self.captured_evidence_json:
                        from ..config import read_json
                        self.captured_evidence_json.add(str(path))
                        self.capture_command_evidence(read_json(path)); self.validate_artifact(artifact)
            else:
                for child in value.values(): self.capture_admitted(child)
        elif isinstance(value,(list,tuple)):
            for child in value: self.capture_admitted(child)

    def capture_admitted_inventory(self,inventory):
        from ..config import read_json
        for path in inventory: self.capture_admitted(read_json(Path(path)))

    def capture_command_evidence(self,value):
        """Log identities describe pre-promotion paths; only actual commands add live byte guards."""
        from .production_composition_records import COMMAND_FIELDS
        if isinstance(value,dict):
            if set(value)==set(COMMAND_FIELDS): self.capture_admitted(value)
            elif {'path','bytes','sha256'}<=set(value) and Path(value['path']).suffix=='.json' and Path(value['path']).is_relative_to(self.run_dir/'logs/production'):
                from ..config import read_json
                artifact={k:value[k] for k in ('path','bytes','sha256')}; self.bind_artifact(artifact)
                path=Path(artifact['path'])
                if str(path) not in self.captured_evidence_json:
                    self.captured_evidence_json.add(str(path)); self.capture_command_evidence(read_json(path))
                    self.validate_artifact(artifact)
            else:
                for child in value.values(): self.capture_command_evidence(child)
        elif isinstance(value,(list,tuple)):
            for child in value: self.capture_command_evidence(child)

    def write(self,relative,value):
        self.assert_write()
        return super().write(relative,value)

    def write_bytes(self,relative,raw):
        self.assert_write()
        return super().write_bytes(relative,raw)

    def assert_write(self):
        if get_ident()!=self.caller_thread: raise ProductionRefused('scene media writes require caller thread')
        self.assert_owned()

    def for_root(self,relative):
        other = SceneMediaStore(self.frozen,self.run_dir,paths=self.paths,lock=self.lock,clip_ids=self.clip_ids)
        other.root = self._lexical(self.run_dir/relative)
        other.guard_paths = self.guard_paths.copy(); other.guard_directories = self.guard_directories.copy()
        other.guard_empty_paths = self.guard_empty_paths.copy()
        other.guard_absent_paths = self.guard_absent_paths.copy()
        other.guard_tool_stamps = self.guard_tool_stamps.copy()
        other.caller_thread = self.caller_thread
        other.captured_evidence_json = self.captured_evidence_json.copy()
        other.media_cache = self.media_cache
        other.revision_context = self.revision_context
        return other

    def frame_dir(self,frame_id):
        if not isinstance(frame_id,str) or not re.fullmatch(r'scene_[0-9]{4,}_clip_[0-9]{4,}:frame_[0-9]{6}',frame_id):
            raise ProductionRefused('exact frame ID required')
        cid, name = frame_id.split(':')
        return self.clip_dir(cid)/name

    def capture_guard(self,request,graph):
        folder = self.frame_dir(request['frame_id'])
        captures = dict(self.guard_paths)
        def capture(value):
            if isinstance(value,dict):
                if set(value)=={'path','bytes','sha256'}:
                    self.validate_artifact(value); captures[value['path']] = deepcopy(value)
                else:
                    for child in value.values(): capture(child)
            elif isinstance(value,(list,tuple)):
                for child in value: capture(child)
        capture(request)
        for path in (self.root/'inputs.json',folder/'request.json',folder/'graph.json'):
            captures[str(path)] = self.artifact(path)
        def guard():
            self.verify_global()
            for artifact in captures.values(): self.validate_artifact(artifact)
            equal(self.read(folder/'request.json'),request,'frame send request')
            equal(self.read(folder/'graph.json'),graph,'frame send graph')
        return guard


from .verification import verified_read


@verified_read
def scene_media_context(frozen,units,timeline,*,paths=None,lock=None):
    from .scene_clip_records import require_scene_clip_acceptance
    from .image_selection_records import require_complete_image_acceptance,load_committed_plan
    from .production_visual_templates import validate_fixed_visual_template
    from .workflows import WorkflowTemplate
    from .image_selection_records import _run
    run=_run(frozen)
    tool_stamps={role:ArtifactStamp.read(frozen.config.tools[role]) for role in ('ffmpeg','ffprobe')}
    store=SceneMediaStore(frozen,run,paths=paths,lock=lock)
    plan_files = ['production/scene-plan.json','production/visual-bible.json','production/scene-plan-commit.json']
    if store.revision_context is not None and 'plan:all' in store.revision_context['imports']:
        plan_files = [store.revision_context['imports']['plan:all'][0]['view_artifact']['path']]
    snapshot=store.snapshot_json(files=('production/options.json',*plan_files,
        'production/reference-images/wan-inputs.json'),directories=(
        'production/image-selection','production/reference-images','production/reference-storage','production/jimeng','production/scene-clips'))
    store.guard_tool_stamps=tool_stamps
    store.capture_unhashed_inputs(snapshot,pcm_paths=(c.pcm.path for c in timeline.clips))
    clips = require_scene_clip_acceptance(frozen,units,timeline)
    store.verify_admission_snapshot(snapshot)
    bible,plan=load_committed_plan(frozen,units,timeline)
    images = require_complete_image_acceptance(frozen,units,timeline)
    store.verify_admission_snapshot(snapshot)
    store.clip_ids=frozenset(c['clip_id'] for c in clips['clips'])
    for stamp in tool_stamps.values(): stamp.verify()
    store.guard_tool_stamps=tool_stamps
    store.adopt_json_snapshot(snapshot)
    capture=store.capture_admitted
    capture(clips); capture(timeline.as_dict()); capture(thaw(frozen.options['execution_policy']['input_identities']))
    for narration in timeline.clips:
        store.bind_artifact(store.artifact(narration.pcm.path))
    template = WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['upscale']['path']),
        Path(frozen.options['workflow_snapshots']['upscale_mapping']['path']),frozen.config.models)
    validate_fixed_visual_template(template,'upscale')
    inputs = dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,algorithm='scene_upscale_v1',
        frozen_options_sha256=canonical_digest(frozen.options),scene_clips_sha256=canonical_digest(clips),
        image_acceptance_sha256=canonical_digest(images),timeline_sha256=canonical_digest(timeline.as_dict()),
        workflow=store.artifact(frozen.options['workflow_snapshots']['upscale']['path']),
        mapping=store.artifact(frozen.options['workflow_snapshots']['upscale_mapping']['path']),
        model_stamp=thaw(frozen.options['model_stamps']['upscale']),parameters=dict(model='RealESRGAN_x4plus.pth',
            width=1920,height=1080,method='lanczos',crop='disabled',native_fps=16,output_fps=16))
    if store.read('inputs.json') is not None: equal(store.read('inputs.json'),inputs,'upscale inputs')
    for artifact in (inputs['workflow'],inputs['mapping']): store.guard_paths[artifact['path']] = artifact
    store.verify_admission_snapshot(snapshot)
    return dict(frozen=frozen,units=units,timeline=timeline,store=store,bible=bible,plan=plan,
        image_acceptance=images,scene_clips=clips,inputs=inputs,template=template,rows=plan_scene_upscale(clips))


def require_scene_upscale_acceptance(frozen,units,timeline):
    return require_scene_upscale_acceptance_record(scene_media_context(frozen,units,timeline))


def require_scene_upscale_acceptance_record(context):
    from ._scene_upscale_records import require_upscale_record
    store=context['store']; snapshot=store.snapshot_json(directories=(store.root,))
    store.capture_unhashed_inputs(snapshot)
    value=require_upscale_record(context)
    store.verify_admission_snapshot(snapshot)
    store.adopt_json_snapshot(snapshot)
    for frame in value['frames']:
        for key in ('input','input_copy','model_output','output'):
            store.bind_artifact(frame[key])
    store.verify_admission_snapshot(snapshot)
    return value


def require_scene_composition(frozen,units,timeline):
    from .production_scene_composition import require_scene_composition_record
    return require_scene_composition_record(scene_media_context(frozen,units,timeline))


def require_scene_final_acceptance(frozen,units,timeline):
    from .production_scene_delivery import require_scene_final_acceptance_record
    return require_scene_final_acceptance_record(scene_media_context(frozen,units,timeline))


def require_scene_delivery(frozen,units,timeline):
    from .production_scene_delivery import require_scene_delivery_record
    return require_scene_delivery_record(scene_media_context(frozen,units,timeline))


def load_scene_media_progress(frozen,units,timeline):
    return _load_scene_media_progress(scene_media_context(frozen,units,timeline))


@verified_read
def _load_scene_media_progress(context):
    from ._scene_upscale_records import validate_upscale_frames, require_upscale_record
    frozen=context['frozen'];store = context['store']
    terminals=[]; frames = validate_upscale_frames(context,terminal_errors=terminals)
    def row(status='pending',record=None,completed=0,total=1,error=None):
        return dict(status=status,record=str(record) if record else None,completed_items=completed,total_items=total,error=error)
    result = dict(schema_version=2,run_id=store.run_dir.name,upscale=row(total=len(context['rows']),completed=len(frames)),
                  composition=row(),final_review=row(),delivery=row())
    if store.read('complete.json') is not None:
        require_upscale_record(context); result['upscale'] = row('ready',store.root/'complete.json',len(frames),len(context['rows']))
    elif terminals:
        terminal=terminals[0]
        result['upscale']['status']='blocked' if terminal['status']=='identity_conflict' else 'failed'
        result['upscale']['error']=dict(kind='ProductionRefused',message=terminal['reason'],evidence_paths=[v['path'] for v in terminal['evidence']])
    elif store.root.exists() and any(store.root.iterdir()): result['upscale']['status'] = 'running'
    composition = store.run_dir/'production/scene-composition'
    if composition.exists():
        from .production_scene_composition import validate_scene_composition_state
        validate_scene_composition_state(context)
        if any(composition.iterdir()): result['composition']['status']='running'
        if not (composition/'candidate-commit.json').exists() and any((composition/name).exists() for name in ('final-observations','final-observation-accepted.json','final-observation-rejected.json')):
            raise ProductionRefused('final observation lacks candidate commit')
    if (composition/'candidate-commit.json').exists():
        from .production_scene_composition import require_scene_composition_record
        context['validated_candidate']=require_scene_composition_record(context)
        result['composition'] = row('ready',composition/'candidate-commit.json',1)
        result['final_review']['status'] = 'awaiting_final_review'
    if (composition/'candidate-commit.json').exists():
        from .production_scene_delivery import final_observation_state
        state=final_observation_state(context)
        if state['accepted'] is not None:
            result['final_review'] = row('ready',composition/'final-observation-accepted.json',1)
        elif state['rejected'] is not None:
            result['final_review']['status'] = 'final_review_failed'
            rejected=state['rejected']
            observation=rejected.get('observation')
            result['final_review']['error']=dict(kind='SceneFinalObservationFailed',message='Actual final-film observation rejected this candidate',
                evidence_paths=[observation['path']] if isinstance(observation,dict) and 'path' in observation else [])
    if (store.run_dir/'production/scene-delivery').exists():
        from .production_scene_delivery import require_scene_delivery_record
        from .scene_delivery_files import validate_delivery_state
        tx = validate_delivery_state(context)
        if tx is not None and tx.get('status') == 'completed':
            receipt = require_scene_delivery_record(context)
            context['validated_delivery']=receipt
            result['delivery'] = row('delivered',frozen.options['output_paths']['receipt'],1)
        elif tx is not None: result['delivery']['status'] = 'running'
    return result
