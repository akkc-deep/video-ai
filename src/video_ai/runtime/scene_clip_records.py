"""Immutable scene clip evidence and read-only reconstruction of native contributions."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from ..config import read_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from .manifest import hash_file, now, thaw
from .production_state import (ArtifactStamp, ProductionRefused, RunLock, integer,
                               object_fields, run_path, timestamp)
from . import image_selection_records as images
from .verification import verified_read


def equal(actual, expected, label):
    images._equal(actual, expected, 'scene clip '+label)


class SceneClipStore:
    """All writes run synchronously under the real run lock; readers never mutate."""
    def __init__(self, frozen, run_dir, *, paths=None, lock=None, clip_ids=()):
        self.frozen, self.run_dir = frozen, Path(run_dir)
        self.root = run_path(self.run_dir, self.run_dir/'production/scene-clips')
        self.paths, self.lock = paths, lock
        self.clip_ids = frozenset(clip_ids)
        self.guard_paths = {}
        self.guard_directories = {}
        self.media_cache = set()  # Invocation-local, keyed by verified bytes; never mtime or cross-call state.
        from .scene_revision_records import _context
        scope=_context.get()
        if scope is not None:
            tools={role:ArtifactStamp.read(frozen.config.tools[role]).to_dict() for role in ('ffmpeg','ffprobe')}
            cache_key=canonical_digest(dict(options=thaw(frozen.options),tools=tools))
            self.media_cache=scope.setdefault('scene_media_decode_cache',{}).setdefault(cache_key,set())
        self.revision_context = None
        if 'scene_revision' in getattr(frozen,'options',{}):
            from .scene_revision_records import require_scene_revision
            self.revision_context = require_scene_revision(frozen)

    def assert_owned(self):
        if (not isinstance(self.lock, RunLock) or self.lock.run_dir != self.run_dir
                or read_json(self.lock.path) != self.lock.owner):
            raise ProductionRefused('scene clips lost held run lock')

    def path(self, relative):
        relative = Path(relative)
        target = run_path(self.run_dir, relative if relative.is_absolute() else self.root/relative)
        if not target.is_relative_to(self.root):
            raise ProductionRefused('scene clip record escapes root')
        return target

    def read(self, relative):
        path = self.path(relative)
        if not path.exists(): return None
        return read_json(path)

    def write_bytes(self, relative, raw):
        self.assert_owned(); target = self.path(relative)
        if target.exists():
            if target.read_bytes() != raw: raise ProductionRefused('immutable scene clip bytes differ: '+str(target))
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path(target.with_name(target.name+'.'+uuid4().hex+'.tmp'))
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        self.assert_owned(); os.rename(temporary, target); self.assert_owned()
        return target

    def write(self, relative, value):
        self.assert_owned(); target = self.path(relative)
        if target.exists():
            equal(read_json(target), value, 'immutable record '+target.name)
            return target
        return self.write_bytes(target, (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode())

    def artifact(self, path):
        path = run_path(self.run_dir, path)
        from ._scene_revision_origin_clips import media_declaration
        declared=media_declaration(self.frozen,path)
        if declared is not None:return declared
        identity = hash_file(path)
        integer(identity.bytes, 'artifact bytes', 1)
        return {key: getattr(identity, key) for key in ('path', 'bytes', 'sha256')}

    def validate_artifact(self, value):
        object_fields(value, ('path', 'bytes', 'sha256'), 'scene Artifact')
        integer(value['bytes'], 'artifact bytes', 1); images._sha(value['sha256'])
        from ._scene_revision_origin_images import source_image_artifact
        declared=source_image_artifact(self.frozen,value)
        if declared is not None:return declared
        path = run_path(self.run_dir, value['path'])
        equal(self.artifact(path), value, 'artifact '+str(path))
        return path

    def clip_dir(self, clip_id):
        if clip_id not in self.clip_ids: raise ProductionRefused('clip ID outside committed plan')
        return self.path(clip_id)

    def verify_global(self):
        """Rehash the full already-admitted dependency set without repeating decoding."""
        self.assert_owned()
        if self.revision_context is not None: self.revision_context['guard'].verify_captured_bytes()
        for value in self.guard_paths.values(): self.validate_artifact(value)
        for directory,inventory in self.guard_directories.items():
            if {str(path) for path in Path(directory).rglob('*.json')}!=inventory:
                raise ProductionRefused('upstream evidence inventory changed')
        for stamp in self.frozen.options['model_stamps'].values(): ArtifactStamp.from_dict(thaw(stamp)).verify()

    def capture_guard(self, request, graph):
        """Capture bytes on caller; the network thread only rechecks immutable inputs."""
        folder = self.clip_dir(request['clip_id'])
        paths = dict(self.guard_paths)
        inventories={}
        for path in (self.root/'inputs.json', folder/'input.json', folder/'request.json', folder/'graph.json'):
            paths[str(path)] = self.artifact(path)
        def capture(value):
            if self.revision_context is not None and self.revision_context['guard'].is_registered(value):
                self.revision_context['guard'].verify_captured_bytes(); return
            if isinstance(value, dict):
                if set(value) == {'path','bytes','sha256'}:
                    self.validate_artifact(value); paths[value['path']] = deepcopy(value)
                else:
                    if {'path','bytes','sha256'} <= set(value):
                        artifact = {k:value[k] for k in ('path','bytes','sha256')}
                        self.validate_artifact(artifact); paths[artifact['path']] = artifact
                    for child in value.values(): capture(child)
            elif isinstance(value, list):
                for child in value: capture(child)
        capture(request); capture(self.read(folder/'input.json'))
        parent = request['parent']
        if parent:
            pf = self.clip_dir(parent['clip_id'])
            if self.revision_context is not None and 'clip:'+parent['clip_id'] in self.revision_context['imports']:
                self.revision_context['guard'].verify_captured_bytes()
            else:
                for name in ('clip.json','last-frame.json','observation-accepted.json'):
                    path = pf/name; paths[str(path)] = self.artifact(path)
                capture(self.read(pf/'observation-accepted.json'))
                directory=pf/'observations'
                inventories[directory]={str(path) for path in directory.glob('*.json')}
                for path in inventories[directory]: paths[path]=self.artifact(path)
        expected_request, expected_graph = canonical_digest(request), canonical_digest(graph)
        def guard():
            self.verify_global()
            for directory,inventory in inventories.items():
                if {str(path) for path in directory.glob('*.json')}!=inventory:
                    raise ProductionRefused('parent observation inventory changed before send')
            for value in paths.values(): self.validate_artifact(value)
            equal(canonical_digest(self.read(folder/'request.json')), expected_request, 'send request')
            equal(canonical_digest(self.read(folder/'graph.json')), expected_graph, 'send graph')
            for stamp in self.frozen.options['model_stamps'].values(): ArtifactStamp.from_dict(thaw(stamp)).verify()
        return guard


@verified_read
def scene_context(frozen, units, timeline, *, paths=None, lock=None):
    """Full batch preflight, also used by both read-only public entrypoints."""
    from ..planning.scene_clip_continuation import build_scene_wan_plan
    from .reference_image_records import require_reference_image_acceptance
    from .production_visual_templates import validate_fixed_visual_template, validate_production_model_paths
    from .workflows import WorkflowTemplate
    run = images._run(frozen)
    bible, plan = images.load_committed_plan(frozen, units, timeline)
    wan = require_reference_image_acceptance(frozen, units, timeline)
    validate_production_model_paths(frozen.config)
    for stamp in frozen.options['model_stamps'].values(): ArtifactStamp.from_dict(thaw(stamp)).verify()
    template = WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['wan']['path']),
        Path(frozen.options['workflow_snapshots']['wan_mapping']['path']), frozen.config.models)
    validate_fixed_visual_template(template, 'wan')
    store = SceneClipStore(frozen, run, paths=paths, lock=lock, clip_ids=[c['clip_id'] for c in plan['clips']])
    rows = build_scene_wan_plan(frozen, bible, plan, timeline, wan)
    for selected in wan['scenes']:
        from ._scene_revision_origin_images import source_image_required
        if not source_image_required(frozen,selected['scene_id']):continue
        artifact = {k:selected[k] for k in ('path','bytes','sha256')}
        path = store.validate_artifact(artifact)
        info = images._inspect_original(frozen, path)
        if info['width']*9 != info['height']*16: raise ProductionRefused('selected original must be 16:9')
    profile = frozen.config.media.profile
    size = {'fast': (768,432), 'quality': (1280,720)}.get(profile.name)
    if size is None: raise ProductionRefused('unsupported native profile')
    inputs = dict(schema_version=2, production_strategy=STRATEGY, run_id=run.name,
        algorithm='scene_wan_continuation_v1', frozen_options_sha256=canonical_digest(frozen.options),
        scene_plan_sha256=canonical_digest(plan), visual_bible_sha256=canonical_digest(bible),
        units_sha256=canonical_digest(units), timeline_sha256=canonical_digest(timeline.as_dict()),
        wan_inputs_sha256=canonical_digest(wan), profile=dict(name=profile.name, width=size[0], height=size[1], native_fps=16),
        workflow=store.artifact(frozen.options['workflow_snapshots']['wan']['path']),
        mapping=store.artifact(frozen.options['workflow_snapshots']['wan_mapping']['path']),
        model_stamps={k:thaw(frozen.options['model_stamps'][k]) for k in ('wan_high','wan_low','text_encoder','vae')})
    old = store.read('inputs.json')
    if old is not None: equal(old, inputs, 'inputs')
    for path in (run/'production/options.json', run/'production/scene-plan.json', run/'production/visual-bible.json',
                 run/'production/scene-plan-commit.json', run/'production/reference-images/wan-inputs.json',
                 Path(inputs['workflow']['path']), Path(inputs['mapping']['path'])):
        if path.exists(): store.guard_paths[str(path)] = store.artifact(path)
    # Bind every source selection/observation/provenance record, including comparison baselines.
    for directory in ('production/image-selection','production/reference-images','production/reference-storage','production/jimeng'):
        inventory={str(path) for path in (run/directory).rglob('*.json')}
        store.guard_directories[str(run/directory)]=inventory
        for path in inventory: store.guard_paths[path] = store.artifact(path)
    for selected in wan['scenes']:
        if not source_image_required(frozen,selected['scene_id']):continue
        value={k:selected[k] for k in ('path','bytes','sha256')}
        store.guard_paths[value['path']]=value
    return dict(frozen=frozen, units=units, timeline=timeline, store=store, bible=bible, plan=plan,
                wan=wan, rows=rows, inputs=inputs, template=template)


def graph_for(context, row):
    store = context['store']; budget = row['budget']; p = row['parameters']; cid = budget['clip_id']
    prefix = store.run_dir.name+'/scene_clips/'+cid+'/attempt_0001'
    graph = context['template'].instantiate(dict(positive_prompt=p['positive'],
        start_image=store.run_dir.name+'/scene_clips/'+cid+'/start.png', width=p['width'], height=p['height'],
        length=p['length'], fps=p['fps'], seed_high=p['seed_high'], seed_low=p['seed_low']), output_prefix=prefix)
    if len(json.dumps(dict(prompt=graph,client_id=str(uuid4())), ensure_ascii=False).encode()) > 32*1024*1024:
        raise ProductionRefused('Wan POST body exceeds JSON_LIMIT')
    return graph


def parent_binding(parent):
    if parent is None: return None
    return dict(clip_id=parent['clip']['clip_id'], clip_sha256=canonical_digest(parent['clip']),
        generated=parent['clip']['generated'], source=parent['clip']['source'],
        last_frame_sha256=canonical_digest(parent['last_frame']), last_frame=parent['last_frame']['image'],
        observation_acceptance_sha256=canonical_digest(parent['accepted']))


def observation_parent_records(parent):
    if parent is None:return None
    return {key:parent[key] for key in ('clip','mapping','last_frame','accepted')}


def scan_observation_sources(store,folder,template,created_at,*,now):
    """Read every durable authored source, including interrupted receipt commits."""
    from .scene_clip_observations import validate_scene_clip_observation
    rows=[]
    for path in sorted((folder/'observations').glob('*.json')):
        artifact=store.artifact(path)
        if path.name!=artifact['sha256']+'.json': raise ProductionRefused('observation original filename/SHA differs')
        value=read_json(path)
        validate_scene_clip_observation(value,dict(template=template,created_at=created_at),now=now)
        rows.append(dict(observation=artifact,observation_sha256=canonical_digest(value),value=value))
    return rows


def expected_request(context, row, input_record, parent):
    store = context['store']; budget = row['budget']
    return dict(schema_version=2, production_strategy=STRATEGY, run_id=store.run_dir.name,
        scene_id=budget['scene_id'], clip_id=budget['clip_id'], inputs_sha256=canonical_digest(context['inputs']),
        **deepcopy(row), selected_image=deepcopy(next(s for s in context['wan']['scenes'] if s['scene_id']==budget['scene_id'])),
        input_sha256=canonical_digest(input_record), parent=parent_binding(parent), graph_sha256=canonical_digest(graph_for(context,row)))


def _decode_video(store, value, *, frames, width, height):
    """Read-only complete probe/decode; no logger, temporary files or encoding."""
    from ..media.video import validate_video_probe
    path = store.validate_artifact(value)
    tool_identity=canonical_digest({k:ArtifactStamp.read(store.frozen.config.tools[k]).to_dict() for k in ('ffmpeg','ffprobe')})
    key=('video',canonical_digest(value),frames,width,height,tool_identity)
    if key in store.media_cache: return
    def execute(args):
        proc = subprocess.run([str(x) for x in args], stdin=subprocess.DEVNULL, capture_output=True,
            timeout=300, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if proc.returncode: raise ProductionRefused('scene video decode failed: '+str(path))
        return proc.stdout
    tools=store.frozen.config.tools
    probe=json.loads(execute((tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',path)))
    frame_data=json.loads(execute((tools['ffprobe'],'-v','error','-show_frames','-of','json',path)))
    info=validate_video_probe(probe,frame_data,width=width,height=height)
    execute((tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',path,'-f','null','-'))
    store.validate_artifact(value)
    if info['frames'] != frames: raise ProductionRefused('exact generated/retained frame count required')
    store.media_cache.add(key)


def validate_media_receipt(store, folder, operation, *, source=None, target=None, recipe=None, promote=False, required=False, media=True):
    value=store.read(folder/'media-ready'/(operation+'.json'))
    if value is None:
        if required: raise ProductionRefused('required media preparation receipt missing: '+operation)
        return None
    object_fields(value,'schema_version run_id clip_id operation source staging target recipe evidence created_at'.split(),'media ready')
    timestamp(value['created_at'])
    if operation not in ('input','generated','source','last_frame'): raise ProductionRefused('unknown media operation')
    equal({k:value[k] for k in ('schema_version','run_id','clip_id','operation')},
        dict(schema_version=2,run_id=store.run_dir.name,clip_id=folder.name,operation=operation),'media ready identity')
    from ._scene_revision_origin_clips import declared_artifact
    if media:store.validate_artifact(value['source'])
    else:declared_artifact(store,value['source'])
    if source is not None: equal(value['source'],source,'media source')
    if recipe is not None: equal(value['recipe'],recipe,'media recipe')
    object_fields(value['recipe'],('algorithm','parameters'),'media recipe')
    if target is not None and value['target']['path'] != str(target): raise ProductionRefused('media target path differs')
    equal({k:value['target'][k] for k in ('bytes','sha256')},
          {k:value['staging'][k] for k in ('bytes','sha256')},'media staging identity')
    if value['recipe']['algorithm'] in ('identity_copy_v1','identity_png_copy_v1'):
        equal({k:value['source'][k] for k in ('bytes','sha256')},{k:value['target'][k] for k in ('bytes','sha256')},'identity copy bytes')
    staging=run_path(store.run_dir,value['staging']['path']); final=run_path(store.run_dir,value['target']['path'])
    if not staging.is_relative_to(folder/'staging'): raise ProductionRefused('media staging escapes clip')
    if media:
        if not staging.exists() and not final.exists(): raise ProductionRefused('prepared media bytes missing')
        if staging.exists(): store.validate_artifact(value['staging'])
        if final.exists(): store.validate_artifact(value['target'])
        elif promote:
            store.assert_owned(); final.parent.mkdir(parents=True,exist_ok=True); os.rename(staging,final); store.assert_owned()
        else: raise ProductionRefused('media promotion incomplete')
    else:
        if promote:raise ProductionRefused('source metadata cannot promote media')
        declared_artifact(store,value['staging']);declared_artifact(store,value['target'])
    if not isinstance(value['evidence'],list): raise ProductionRefused('media evidence list required')
    for artifact in value['evidence']: store.validate_artifact(artifact)
    return value


def technical_recipes(row):
    b=row['budget']; p=row['parameters']; a,z=b['retained_source_start'],b['retained_source_end']
    return dict(generated=dict(algorithm='identity_copy_v1',parameters={}),
        source=dict(algorithm='trim_native16_v1',parameters=dict(start_frame=a,end_frame=z,
            filter=f'trim=start_frame={a}:end_frame={z},setpts=N/(16*TB)')),
        last_frame=dict(algorithm='native_index_rgb24_v1',parameters=dict(source_frame_index=z-1,
            expected_frames=b['generated_frames'],width=p['width'],height=p['height'],
            filter=f'select=eq(n\\,{z-1}),format=rgb24')))


def _verify_native_pixels(store,generated,image,index,width,height):
    """Read-only native decode comparison prevents a different PNG posing as the retained frame."""
    ffmpeg=store.frozen.config.tools['ffmpeg']
    store.validate_artifact(generated);store.validate_artifact(image)
    key=('native_pixels',canonical_digest(generated),canonical_digest(image),index,width,height,
        canonical_digest(ArtifactStamp.read(ffmpeg).to_dict()))
    if key in store.media_cache: return
    def decode(path,filter_value):
        args=[str(ffmpeg),'-nostdin','-v','error','-xerror','-i',str(path),'-map','0:v:0',
              '-vf',filter_value,'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-']
        result=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=300,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or len(result.stdout)!=width*height*3: raise ProductionRefused('native PNG pixel decode failed')
        return result.stdout
    if decode(generated['path'],f'select=eq(n\\,{index}),format=rgb24')!=decode(image['path'],'format=rgb24'):
        raise ProductionRefused('PNG differs from actual retained generated native frame')
    store.validate_artifact(generated);store.validate_artifact(image)
    store.media_cache.add(key)


def _validate_input(context,row,parent,*,media=True):
    from ..media.images import contain_filter
    store=context['store']; b=row['budget']; folder=store.clip_dir(b['clip_id']); value=store.read(folder/'input.json')
    if value is None: return None
    object_fields(value,'schema_version run_id clip_id kind source target rule filter width height pixel_format'.split(),'clip input')
    selected=next(s for s in context['wan']['scenes'] if s['scene_id']==b['scene_id'])
    source={k:selected[k] for k in ('path','bytes','sha256')} if parent is None else parent['last_frame']['image']
    w,h=row['parameters']['width'],row['parameters']['height']
    rule='contain_png_v1' if parent is None else 'identity_png_copy_v1'
    filter_value=contain_filter(w,h) if parent is None else None
    target=store.run_dir/'comfy/input'/store.run_dir.name/'scene_clips'/b['clip_id']/'start.png'
    expected=dict(schema_version=2,run_id=store.run_dir.name,clip_id=b['clip_id'],kind=b['input_kind'],source=source,
        target=store.artifact(target) if media else value['target'],rule=rule,filter=filter_value,width=w,height=h,pixel_format='rgb24')
    equal(value,expected,'input')
    if value['target']['path']!=str(target):raise ProductionRefused('original input target differs')
    if media:
        store.validate_artifact(source)
        info=images._inspect_original(store.frozen,target)
        if (info['width'],info['height'],info['format']) != (w,h,'png'): raise ProductionRefused('invalid native start PNG')
    if parent is not None and value['target']['sha256']!=source['sha256']: raise ProductionRefused('child input must copy parent PNG bytes')
    validate_media_receipt(store,folder,'input',source=source,target=target,
        recipe=dict(algorithm=rule,parameters=dict(filter=filter_value,width=w,height=h) if parent is None else {}),required=True,media=media)
    return value


def validate_clip(context,row,parent=None):
    """Reconstruct one original technical clip and its observation, without mutation."""
    from ._scene_revision_readers import inherited_clip_record
    imported = inherited_clip_record(context['frozen'],row['budget']['clip_id'],
        context=context['store'].revision_context,row=row,parent=parent)
    if imported is not None:return imported
    from ..planning.scene_clip_continuation import scene_clip_frame_mapping
    from .scene_comfy_transactions import validate_scene_submission,validate_scene_terminal
    from .scene_clip_observations import build_observation_template,validate_scene_clip_observation
    store=context['store']; b=row['budget']; folder=store.clip_dir(b['clip_id'])
    from ._scene_revision_origin_clips import source_clip_required,declared_artifact
    media=source_clip_required(context['frozen'],b['clip_id'])
    input_record=_validate_input(context,row,parent,media=media)
    request=store.read(folder/'request.json'); graph=store.read(folder/'graph.json')
    if request is not None:
        if input_record is None: raise ProductionRefused('request lacks original input')
        equal(request,expected_request(context,row,input_record,parent),'request')
        equal(graph,graph_for(context,row),'graph')
    elif graph is not None: raise ProductionRefused('graph lacks original request')
    clip=store.read(folder/'clip.json')
    # Replay every extant original transaction even before the technical cursor exists.
    # This is part of batch preflight and prevents a later scene's local conflict being found after a POST.
    if request is not None:
        terminal=validate_scene_terminal(store,request,graph)
        if terminal is not None:
            if clip is not None: raise ProductionRefused('terminal transaction has completed technical clip')
            return None
        submission=validate_scene_submission(store,request,graph,media=media)
    else:
        if any(store.read(folder/name) is not None for name in ('intent.json','accepted.json','submission.json','terminal.json')):
            raise ProductionRefused('transaction evidence lacks original request')
        submission=None
    if clip is None: return None
    if request is None: raise ProductionRefused('technical clip lacks request')
    if submission is None: raise ProductionRefused('technical clip lacks submission')
    object_fields(clip,('schema_version production_strategy run_id scene_id clip_id request_sha256 submission_sha256 '
        'generated source frame_mapping_sha256 last_frame_sha256 technical_evidence created_at').split(),'technical clip')
    timestamp(clip['created_at'])
    mapping=store.read(folder/'mapping.json'); last=store.read(folder/'last-frame.json')
    expected_mapping=scene_clip_frame_mapping(b,actual_generated_frames=b['generated_frames'])
    equal(mapping,expected_mapping,'mapping')
    for name,frames in (('generated',b['generated_frames']),('source',b['retained_frames'])):
        value=clip[name]
        if value['path']!=str(folder/(name+'.mp4')): raise ProductionRefused('clip media path differs')
        if media:_decode_video(store,value,frames=frames,width=row['parameters']['width'],height=row['parameters']['height'])
        else:declared_artifact(store,value)
    object_fields(last,'schema_version run_id clip_id generated source_frame_index global_output_frame_index image extraction_rule evidence'.split(),'last frame')
    last_path=folder/f"frame_{b['retained_source_end']:06d}.png"
    image=store.artifact(last_path) if media else last['image']
    if image['path']!=str(last_path):raise ProductionRefused('last native PNG path differs')
    if media:
        info=images._inspect_original(store.frozen,last_path)
        if (info['width'],info['height'],info['format']) != (row['parameters']['width'],row['parameters']['height'],'png'):
            raise ProductionRefused('invalid last native PNG')
    equal(last,dict(schema_version=2,run_id=store.run_dir.name,clip_id=b['clip_id'],generated=clip['generated'],
        source_frame_index=b['retained_source_end']-1,global_output_frame_index=b['end_frame']-1,image=image,
        extraction_rule='native_index_rgb24_v1',evidence=last['evidence']),'last frame')
    for evidence in clip['technical_evidence']+last['evidence']: store.validate_artifact(evidence)
    recipes=technical_recipes(row); receipts={}
    for op,source,target in (('generated',submission['output'],clip['generated']),('source',clip['generated'],clip['source']),('last_frame',clip['generated'],image)):
        receipts[op]=validate_media_receipt(store,folder,op,source=source,target=Path(target['path']),recipe=recipes[op],required=True,media=media)
    equal(last['evidence'],receipts['last_frame']['evidence'],'native extraction evidence')
    if media:_verify_native_pixels(store,clip['generated'],image,b['retained_source_end']-1,row['parameters']['width'],row['parameters']['height'])
    expected=dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,scene_id=b['scene_id'],clip_id=b['clip_id'],
        request_sha256=canonical_digest(request),submission_sha256=canonical_digest(submission),generated=clip['generated'],source=clip['source'],
        frame_mapping_sha256=canonical_digest(mapping),last_frame_sha256=canonical_digest(last),
        technical_evidence=sum((receipts[op]['evidence'] for op in ('generated','source','last_frame')),[]),
        created_at=receipts['last_frame']['created_at'])
    equal(clip,expected,'technical record')
    template=build_observation_template(context['frozen'],clip,request,mapping,last,observation_parent_records(parent))
    stored_template=store.read(folder/'observation-template.json')
    if stored_template is not None: equal(stored_template,template,'observation template')
    result=dict(clip=clip,request=request,mapping=mapping,last_frame=last,accepted=None,rejected=None,template=template)
    originals=scan_observation_sources(store,folder,template,clip['created_at'],now=datetime.now(timezone.utc))
    failed_originals=[row for row in originals if row['value']['verdict']=='failed']
    for name,time_key in (('observation-accepted.json','accepted_at'),('observation-rejected.json','rejected_at')):
        receipt=store.read(folder/name)
        if receipt is None: continue
        object_fields(receipt,('schema_version run_id clip_id clip_sha256 request_sha256 observation observation_sha256 '+time_key).split(),'observation receipt')
        timestamp(receipt[time_key]); original=store.validate_artifact(receipt['observation'])
        if original.parent!=folder/'observations' or original.name!=receipt['observation']['sha256']+'.json':
            raise ProductionRefused('observation original path differs')
        observation=read_json(original)
        validate_scene_clip_observation(observation,dict(template=template,created_at=clip['created_at']),now=datetime.fromisoformat(receipt[time_key]))
        expected_verdict='passed' if time_key=='accepted_at' else 'failed'
        if observation['verdict']!=expected_verdict: raise ProductionRefused('observation verdict differs from receipt')
        equal(receipt,dict(schema_version=2,run_id=store.run_dir.name,clip_id=b['clip_id'],clip_sha256=canonical_digest(clip),
            request_sha256=canonical_digest(request),observation=receipt['observation'],observation_sha256=canonical_digest(observation),
            **{time_key:receipt[time_key]}),'observation receipt')
        result['accepted' if time_key=='accepted_at' else 'rejected']=receipt
    if result['accepted'] and result['rejected']: raise ProductionRefused('conflicting accepted and rejected observation')
    if failed_originals:
        if result['accepted']: raise ProductionRefused('accepted clip has a retained explicit failed observation')
        if result['rejected'] is None:
            source=failed_originals[0]
            result['rejected']=dict(_raw_only=True,observation=source['observation'],
                                    observation_sha256=source['observation_sha256'])
    return result


@verified_read
def collect_progress(context):
    store=context['store']; scenes=[]; records={}
    for scene in context['plan']['scenes']:
        state=dict(scene_id=scene['scene_id'],status='pending',completed_clip_ids=[],accepted_clip_ids=[],waiting_clip_id=None,error=None)
        parent=None; stopped=False
        for row in [r for r in context['rows'] if r['budget']['scene_id']==scene['scene_id']]:
            cid=row['budget']['clip_id']; folder=store.clip_dir(cid)
            if stopped:
                if folder.exists() and any(folder.iterdir()): raise ProductionRefused('descendant evidence exists before parent acceptance')
                continue
            record=validate_clip(context,row,parent)
            if record:
                records[cid]=record; state['completed_clip_ids'].append(cid)
                if record['rejected']:
                    rejected=record['rejected']
                    evidence=rejected['observation']['path'] if rejected.get('_raw_only') else str(folder/'observation-rejected.json')
                    state.update(status='continuity_failed',waiting_clip_id=cid,error=dict(kind='continuity_failed',message='explicit process observation failed',evidence_paths=[evidence]))
                    stopped=True
                elif record['accepted']:
                    state['accepted_clip_ids'].append(cid); parent=record; state['status']='ready'
                else:
                    state.update(status='awaiting_continuity_review',waiting_clip_id=cid); stopped=True
            else:
                terminal=store.read(folder/'terminal.json')
                if terminal:
                    state.update(status='failed',waiting_clip_id=cid,error=dict(kind=terminal['status'],message=terminal['reason'],evidence_paths=[str(folder/'terminal.json')]))
                elif store.read(folder/'intent.json'):
                    state.update(status='submit_unknown',waiting_clip_id=cid,error=dict(kind='submit_unknown',message='original task needs recovery',evidence_paths=[str(folder/'intent.json')]))
                else: state.update(status='pending',waiting_clip_id=cid)
                stopped=True
        scenes.append(state)
    return dict(schema_version=2,run_id=store.run_dir.name,inputs_sha256=canonical_digest(context['inputs']),scenes=scenes),records


def complete_value(context,records):
    from ..planning.scene_clip_continuation import validate_scene_clip_frame_mappings
    if any(r['budget']['clip_id'] not in records or not records[r['budget']['clip_id']]['accepted'] for r in context['rows']):
        raise ProductionRefused('all source clips and process observations required')
    validate_scene_clip_frame_mappings(context['plan'],context['timeline'],[records[r['budget']['clip_id']]['mapping'] for r in context['rows']])
    inputs=context['inputs']; store=context['store']; scenes=[]; clips=[]
    for scene in context['plan']['scenes']:
        scenes.append(dict({k:deepcopy(scene[k]) for k in ('scene_id','unit_ids','start_frame','end_frame','bindings')},
            selected_image=deepcopy(next(s for s in context['wan']['scenes'] if s['scene_id']==scene['scene_id'])),
            clip_ids=[r['budget']['clip_id'] for r in context['rows'] if r['budget']['scene_id']==scene['scene_id']]))
    for row in context['rows']:
        r=records[row['budget']['clip_id']]
        clips.append(dict(clip_id=row['budget']['clip_id'],scene_id=row['budget']['scene_id'],budget=deepcopy(row['budget']),
            narration_bindings=deepcopy(row['narration_bindings']),generated=r['clip']['generated'],source=r['clip']['source'],
            frame_mapping=r['mapping'],last_frame=r['last_frame'],clip_sha256=canonical_digest(r['clip']),
            observation_acceptance_sha256=canonical_digest(r['accepted'])))
    return dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,inputs_sha256=canonical_digest(inputs),
        **{k:inputs[k] for k in ('scene_plan_sha256','visual_bible_sha256','wan_inputs_sha256','timeline_sha256')},
        total_frames=context['timeline'].total_frames,scenes=scenes,clips=clips)


def load_scene_clip_progress(frozen,units,timeline):
    context=scene_context(frozen,units,timeline)
    if context['store'].read('inputs.json') is None: raise ProductionRefused('scene clip inputs missing')
    progress,_=collect_progress(context)
    return progress


def require_scene_clip_acceptance(frozen,units,timeline):
    context=scene_context(frozen,units,timeline); store=context['store']
    if store.read('inputs.json') is None: raise ProductionRefused('scene clip inputs missing')
    _,records=collect_progress(context); expected=complete_value(context,records); value=store.read('complete.json')
    if value is None: raise ProductionRefused('complete source clip admission missing')
    equal(value,expected,'complete admission')
    return value
