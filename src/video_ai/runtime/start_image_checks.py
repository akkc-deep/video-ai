"""Start-image preparation, visual review commit, and fresh downstream consumption."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import struct
import time
from uuid import uuid4
import zlib

from ..adapters.common import AdapterError,FailureKind,HttpClient
from ..adapters.comfyui import ComfyClient
from ..config import load_config,read_json
from ..media.images import inspect_image,adapt_image,validate_start_png
from ..planning.start_images import (keys,validate_dimensions,validate_input_map,contain_filter,
    image_parameters,requirement_images,validate_directions)
from .component_checks import output_path
from .environment import build_child_env
from .logging import RunLogger
from .manifest import ManifestStore,hash_file,thaw,now,_timestamp
from .paths import RuntimePaths,SOURCE_ROOT,_validate_spelling
from .service_specs import build_service_specs
from .services import ServiceManager,ServiceConflictError
from .storyboard_checks import load_committed_storyboard,atomic_report
from .timeline_checks import _run_path,_local,_fresh,_again,_artifact
from .workflows import WorkflowTemplate
from .execution_limits import execution_deadline,production_execution


class StartImageRefusal(ValueError):
    """Invocation/state refusal; no overwrite or retry."""


@dataclass(frozen=True)
class StartImagesResult:
    passed: bool
    run_dir: Path
    draft_path: Path
    images_path: Path
    image_count: int
    ready_for_source_clips: bool
    status: str


def _result(run,status,count=0):
    done=status=='completed'
    return StartImagesResult(done,run,run/'images-draft.json',run/'images.json',count,done,status)


def _validation(ready):
    return dict(structure_passed=True,media_passed=True,image_text_semantics_passed=ready,
        ready_for_source_clips=ready,motion_semantics='unverified',sync='unverified')


@contextmanager
def _exclusive(run):
    path=_local(run,run/'.start-images.lock');owner=dict(pid=os.getpid(),token=uuid4().hex)
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc:raise StartImageRefusal('existing start-images lock; no takeover') from exc
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(owner,f);f.flush();os.fsync(f.fileno())
        yield owner
    finally:
        try:
            if read_json(path)==owner:path.unlink()
        except (OSError,ValueError):pass
        except KeyboardInterrupt:
            if ManifestStore.open(run).snapshot()['stages']['start_images']['status']!='completed':raise


def _review_path(run,path):
    try:
        local=_local(run,Path(path).absolute())
        if local!=run/'logs/start-images/semantic-review.json':raise ValueError('review must be canonical logs/start-images/semantic-review.json')
        return local
    except ValueError as exc:raise StartImageRefusal(str(exc)) from exc


def _same(a,b):
    return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def _input_files(config,run):
    board=load_committed_storyboard(run)
    from .pipeline_import import stage_draft_path,fresh_origin_review
    store=ManifestStore.open(run);snapshot=store.snapshot()
    if config.config_file!=Path(snapshot['config_snapshot']['path']) or thaw(config.raw)!=snapshot['config_snapshot']['raw']:
        raise OSError('image config differs from frozen run config')
    identities=dict(storyboard=hash_file(run/'storyboard.json'),config=_fresh(snapshot['inputs']['config'],expected=config.config_file),
        storyboard_draft=hash_file(stage_draft_path(run,'storyboard',board)),storyboard_review=fresh_origin_review(run,board,board['review_identity']),
        ffmpeg=hash_file(config.tools['ffmpeg']),ffprobe=hash_file(config.tools['ffprobe']))
    contract=run/'logs/storyboard/visual-contract.json'
    if contract.exists():identities['visual_contract']=hash_file(_local(run,contract))
    _,direction_ids=_directions(run,board);identities.update(direction_ids)
    _again(identities)
    return board,identities


def _directions(run,board):
    path=_local(run,run/'logs/start-images/visual-directions.json')
    if not path.exists():return {},{}
    identity=hash_file(path);data=read_json(path);directions=validate_directions(data,board)
    storyboard=_fresh(data['storyboard_identity'],run=run,expected=run/'storyboard.json')
    basis=_fresh(data['review_basis_identity']);review=read_json(Path(basis.path))
    if review.get('global_verdict')!='failed' or not isinstance(review.get('entries'),list):
        raise ValueError('directions require an unchanged failed visual review basis')
    for shot in board['shots']:
        if shot['shot_id'] not in directions:continue
        requirements=[r for r in shot['visual_requirements'] if r['unit_id']==shot['primary_unit_id']]
        for req in requirements:
            matches=[e for e in review['entries'] if all(e.get(k)==req[k] for k in ('requirement_id','unit_id','source_quote'))]
            if len(matches)!=1 or matches[0].get('verdict') not in ('failed','unverified'):
                raise ValueError('direction has no exact failed/unverified source requirement')
    return directions,dict(visual_directions=identity,direction_storyboard=storyboard,direction_basis=basis)


def _read_map(run,board,path):
    identity=None
    if path is None:data=dict(schema_version=1,run_id=run.name,shots={},entities={})
    else:
        path=Path(_validate_spelling(str(path)))
        if not path.is_absolute():raise ValueError('absolute input map required')
        identity=hash_file(path);data=read_json(path)
    validate_input_map(data,board)
    canonical=dict(schema_version=1,run_id=run.name,shots={},entities={});sources={}
    for kind in ('shots','entities'):
        for uid,name in data[kind].items():
            source=Path(_validate_spelling(name)).resolve(strict=True)
            if not source.is_file():raise ValueError('source must be a file')
            canonical[kind][uid]=str(source);sources[kind+'/'+uid]=hash_file(source)
    if identity is not None:sources['input_map_source']=identity
    return canonical,sources


def _copy(run,source,target):
    target=_local(run,target);target.parent.mkdir(parents=True,exist_ok=True)
    before=hash_file(source)
    with Path(source).open('rb') as src,target.open('xb') as dst:
        shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
    identity=hash_file(target);_again({'source':before})
    if (identity.bytes,identity.sha256)!=(before.bytes,before.sha256):raise OSError('copied image differs from source')
    return identity


def _archive_path(run,kind,uid,source,board):
    if kind=='shots':folder=uid
    else:folder=f'entity_{1+next(i for i,e in enumerate(board["global_visual"]["entities"]) if e["entity_id"]==uid):04d}'
    return run/'references/user'/folder/Path(source).name


def _evidence(run,evidence,paths):
    names=[]
    for path in paths:
        path=_local(run,path)
        if not path.is_relative_to(run/'logs') and not path.is_relative_to(run/'workflows'):
            raise ValueError('image evidence outside run logs/workflows')
        name=path.relative_to(run).as_posix()
        if name not in evidence:evidence[name]=thaw(hash_file(path))
        if name not in names:names.append(name)
    return names


TASK4_ACCEPTANCE=Path('D:/VideoSi/projects/video-ai/runs/20261004-040653-a0fcd961cc58/task4-acceptance.json')


def _revision(config,run):
    from ._pipeline_model_admission import revised_files
    return revised_files(config,run,dict(model=config.models['sdxl'],workflow=config.workflows['sdxl'],
        mapping=config.workflows['sdxl'].with_suffix('.mapping.json')),model_stage='sdxl')


def _model(config, *, revision=None):
    baseline=TASK4_ACCEPTANCE
    baseline_identity=hash_file(baseline);acceptance=read_json(baseline)
    if acceptance.get('passed') is not True or acceptance['components']['sdxl'].get('passed') is not True:
        raise ValueError('SDXL migration acceptance required')
    inventory_identity=_fresh(acceptance['provenance']['sdxl']['before'])
    inventory=read_json(Path(inventory_identity.path));path=config.models['sdxl'].resolve(strict=True)
    record=thaw(revision['model']) if revision is not None else inventory.get(str(path))
    if record is None:raise ValueError('SDXL target absent from accepted inventory')
    model=_fresh(record,expected=path)
    pinned={}
    for name,source in (('workflow',config.workflows['sdxl']),('mapping',config.workflows['sdxl'].with_suffix('.mapping.json'))):
        record=thaw(revision[name]) if revision is not None else inventory.get(str(source.resolve(strict=True)))
        if record is None:raise ValueError('SDXL workflow/mapping absent from accepted inventory')
        pinned[name]=thaw(_fresh(record,expected=source))
    if revision is not None:
        pinned['revision_authorization']=thaw(_fresh(thaw(revision['revision_authorization'])))
        if 'model_loader_binding' in revision:pinned['model_loader_binding']=thaw(_fresh(thaw(revision['model_loader_binding'])))
    _again({'baseline':baseline_identity,'inventory':inventory_identity})
    return model,dict(acceptance=thaw(baseline_identity),inventory=thaw(inventory_identity),model=thaw(model),**pinned)


def _template(config, *, revision=None):
    workflow=config.workflows['sdxl'];mapping=workflow.with_suffix('.mapping.json')
    template=WorkflowTemplate.load(workflow,mapping,config.models)
    if not _same(template.graph,read_json(workflow)) or not _same(template.mapping,read_json(mapping)):
        raise ValueError('SDXL in-memory template/mapping differs from pinned file')
    if revision is not None:
        from ._pipeline_model_admission import fixed_graph
        baseline=SOURCE_ROOT/'workflows/sdxl_api.json'
        fixed_graph(template,read_json(baseline),read_json(baseline.with_suffix('.mapping.json')))
    return template


class _DeadlineHttp(HttpClient):
    """Finite transport requests with optional legacy per-image execution end."""
    def set_deadline(self,seconds):self.end=execution_deadline(seconds,time.monotonic())
    def remaining(self):
        if self.end is None:return None
        remaining=self.end-time.monotonic()
        if remaining<=0:raise AdapterError(FailureKind.ambiguous,'image request deadline exhausted')
        return remaining
    def request(self,*args,**kwargs):
        left=self.remaining();cap=min(kwargs.get('timeout') or self.timeout,self.timeout)
        kwargs['timeout']=cap if left is None else min(cap,left)
        return super().request(*args,**kwargs)


def _generate_owned(config,run,store,logger,board,missing,width,height,evidence):
    from ._pipeline_model_paths import prepare_or_consume_model_binding
    prepare_or_consume_model_binding(config,run,'sdxl',create=True)
    paths=RuntimePaths.from_config(config);revision=_revision(config,run)
    model,basis=_model(config,revision=revision) if revision is not None else _model(config)
    directions,direction_ids=_directions(run,board)
    workflow=config.workflows['sdxl'];mapping=workflow.with_suffix('.mapping.json')
    template=_template(config,revision=revision) if revision is not None else _template(config)
    identities=dict(model=model,workflow=hash_file(workflow),mapping=hash_file(mapping))
    if revision is not None:
        identities.update(revision['model_loader_identities'])
        _evidence(run,evidence,[Path(revision['model_loader_binding'].path)])
    identities.update(direction_ids)
    if directions:_evidence(run,evidence,[Path(direction_ids['visual_directions'].path)])
    # Pin all fixed nodes/parameters, rather than accepting a substituted template.
    samplers=[v['inputs'] for v in template.graph.values() if v['class_type']=='KSampler']
    latents=[v['inputs'] for v in template.graph.values() if v['class_type']=='EmptyLatentImage']
    if len(samplers)!=1 or len(latents)!=1 or any(samplers[0].get(k)!=v for k,v in
        dict(steps=25,cfg=7,sampler_name='dpmpp_2m',scheduler='karras',denoise=1).items()) or latents[0].get('batch_size')!=1:
        raise ValueError('fixed SDXL sampling baseline changed')
    baseline_note=logger.save_json('start-images/model-baseline.json',basis)
    _evidence(run,evidence,[baseline_note])
    manager=ServiceManager(paths,store,logger);handle=None;images={}
    specs=build_service_specs(config,run,**({'model_stage':'sdxl'} if revision is not None else {}))
    for name in ('input','output','temp','user'):
        _local(run,run/'comfy'/name).mkdir(parents=True,exist_ok=True)
    try:
        handle=manager.ensure(specs['comfyui'])
        if not handle.owned:raise ServiceConflictError('external 8188 ComfyUI; refuse takeover')
        for shot in missing:
            uid=shot['shot_id'];params=image_parameters(shot,board['global_visual'],width,height,direction=directions.get(uid))
            http=_DeadlineHttp(config.services['comfyui'],config.timeouts['comfy_request'],logger)
            http.set_deadline(config.timeouts['comfy_request']);client=ComfyClient(http,store,logger)
            before=set((run/'logs/http').glob('*')) if (run/'logs/http').exists() else set()
            client.validate_template(template)
            graph=template.instantiate(dict(positive_prompt=params['positive'],negative_prompt=params['negative'],
                seed=params['seed'],width=width,height=height),output_prefix=f'{run.name}/start_images/{uid}')
            _again(identities)
            if revision is not None:prepare_or_consume_model_binding(config,run,'sdxl')
            submission=client.submit_once(graph,stage='start_images',kind='image',unit_id=uid)
            history=client.wait_for(submission,deadline_seconds=http.remaining())
            if len(history.outputs)!=1:raise ValueError('expected exactly one generated PNG')
            source=output_path(run,history.outputs[0]);source=_local(run,source)
            if source.parent!=run/'comfy/output'/run.name/'start_images' or not source.name.startswith(uid+'_') or source.suffix.lower()!='.png':
                raise ValueError('generated image path/prefix differs from this shot')
            saved=store.snapshot()['units']['image'][uid]['submission']
            if source.stat().st_mtime < datetime.fromisoformat(saved['submitted_at']).timestamp():
                raise ValueError('generated output predates submission')
            _,source_logs=validate_start_png(source,width=width,height=height,config=config,paths=paths,logger=logger,unit_id=uid)
            target=run/'shots'/uid/'start.png';identity=_copy(run,source,target)
            _,target_logs=validate_start_png(target,width=width,height=height,config=config,paths=paths,logger=logger,unit_id=uid)
            names=_evidence(run,evidence,source_logs+target_logs+[history.evidence_path,Path(saved['request_path']),baseline_note]+
                sorted(set((run/'logs/http').glob('*'))-before))
            images[uid]=dict(shot_id=uid,primary_unit_id=shot['primary_unit_id'],origin='sdxl',image_identity=thaw(identity),
                source_identity=thaw(hash_file(source)),width=width,height=height,format='png',pixel_format='rgb24',adaptation='none',
                parameters=params,workflow_identity=thaw(identities['workflow']),mapping_identity=thaw(identities['mapping']),
                model_identity=thaw(model),submission=dict(attempt_id=submission.attempt_id,prompt_id=submission.prompt_id,
                intent_identity=thaw(hash_file(Path(saved['request_path'])))),reference_entity_ids=list(shot['entity_ids']),evidence_identities=names)
    finally:
        from .owned_cleanup import stop_owned_preserving_exception
        stop_owned_preserving_exception(manager,handle,logger,'start_images',require_stopped=True)
    _again(identities)
    return images


def _references(board,images,user_references):
    result=[]
    for entity in board['global_visual']['entities']:
        eid=entity['entity_id'];used=[s for s in board['shots'] if eid in s['entity_ids']]
        if eid in user_references:
            identity,source=user_references[eid]
            result.append(dict(entity_id=eid,source_kind='user',identity=identity,source_identity=source,
                reference_usage='comparison_only',reference_shot_id=None))
        elif len(used)>1:
            uid=used[0]['shot_id']
            result.append(dict(entity_id=eid,source_kind='generated',identity=images[uid]['image_identity'],source_identity=None,
                reference_usage='comparison_only',reference_shot_id=uid))
    return result


def _check_lock(run,owner):
    if read_json(_local(run,run/'.start-images.lock'))!=owner:raise OSError('start-images lock replaced; retained')


def _unchanged(store,snapshot,identities,run,owner):
    _check_lock(run,owner);_again(identities)
    current=store.snapshot()
    for stage in ('speech','timeline','storyboard','start_images'):
        if current['stages'][stage]!=snapshot['stages'][stage]:raise OSError(f'{stage} changed during image transaction')
    if current['units'].get('image',{})!=snapshot['units'].get('image',{}):raise OSError('image units changed concurrently')


def _failure(run,store,logger,exc,count=0):
    # Durable completion is the authority, including exceptions after atomic commit.
    if store.snapshot()['stages']['start_images']['status']=='completed':return _result(run,'completed',count)
    status='interrupted' if isinstance(exc,KeyboardInterrupt) else ('ambiguous' if isinstance(exc,AdapterError) and exc.kind==FailureKind.ambiguous else 'failed')
    paths=[]
    try:paths.append(logger.exception('start_images',None,exc))
    except (OSError,ValueError,KeyboardInterrupt):pass
    error=dict(kind=status,message=str(exc),traceback_path=str(paths[0]) if paths else None,evidence_paths=[str(p) for p in paths])
    try:
        snap=store.snapshot()
        if snap['stages']['start_images']['status']=='running':store.record_stage('start_images',status,error=error)
        for uid,unit in snap['units'].get('image',{}).items():
            if unit['status']=='running':store.record_unit('image',uid,status,error=error)
    except (OSError,ValueError,KeyboardInterrupt):pass
    if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise exc
    return _result(run,status,count)


@production_execution
def prepare_start_images(config, *, run_dir:Path,image_inputs_path:Path|None=None,width:int=1280,height:int=720)->StartImagesResult:
    run=_run_path(run_dir)
    try:validate_dimensions(width,height)
    except ValueError as exc:raise StartImageRefusal(str(exc)) from exc
    store=ManifestStore.open(run)
    with _exclusive(run) as owner:
        snapshot=store.snapshot()
        if snapshot['stages']['start_images']['status']!='pending' or any((run/p).exists() for p in ('images-draft.json','images.json')):
            raise StartImageRefusal('start_images already started or orphan report exists')
        logger=RunLogger(run);paths=RuntimePaths.from_config(config)
        try:
            board,identities=_input_files(config,run);mapping,sources=_read_map(run,board,image_inputs_path)
            identities.update(sources)
            kwargs=dict(config=config,paths=paths,logger=logger)
            for key,identity in sources.items():
                if key!='input_map_source':inspect_image(Path(identity.path),unit_id=key.split('/')[1],**kwargs)
            # Refuse orphan targets before mutating the stage or submitting.
            for shot in board['shots']:
                if (run/'shots'/shot['shot_id']/'start.png').exists():raise StartImageRefusal('orphan start.png; no overwrite')
            _again(identities);_check_lock(run,owner)
            store.record_stage('start_images','running');evidence={};images={};user_references={}
            map_path=logger.save_json('start-images/input-map.json',mapping);map_identity=hash_file(map_path)
            _evidence(run,evidence,[map_path])
            if 'visual_directions' in identities:_evidence(run,evidence,[Path(identities['visual_directions'].path)])
            for kind in ('entities','shots'):
                for uid,name in mapping[kind].items():
                    copy=_copy(run,Path(name),_archive_path(run,kind,uid,name,board));source=sources[kind+'/'+uid]
                    if kind=='entities':user_references[uid]=(thaw(copy),thaw(source));continue
                    target=run/'shots'/uid/'start.png'
                    info,logs=adapt_image(Path(copy.path),target,width=width,height=height,unit_id=uid,**kwargs)
                    shot=next(s for s in board['shots'] if s['shot_id']==uid)
                    images[uid]=dict(shot_id=uid,primary_unit_id=shot['primary_unit_id'],origin='user',image_identity=info['identity'],
                        source_identity=thaw(source),width=width,height=height,format='png',pixel_format='rgb24',adaptation='contain_black_pad',
                        parameters=dict(filter=contain_filter(width,height),output_pixel_format='rgb24',frame_limit=1,overwrite=False),
                        workflow_identity=None,mapping_identity=None,model_identity=None,submission=None,
                        reference_entity_ids=list(shot['entity_ids']),evidence_identities=_evidence(run,evidence,logs))
                    store.record_unit('image',uid,'running')
            missing=[s for s in board['shots'] if s['shot_id'] not in images]
            if missing:images.update(_generate_owned(config,run,store,logger,board,missing,width,height,evidence))
            references=_references(board,images,user_references)
            provenance=dict(config_identity=thaw(identities['config']),input_map_source_identity=thaw(sources.get('input_map_source')),
                ffmpeg_identity=thaw(identities['ffmpeg']),ffprobe_identity=thaw(identities['ffprobe']),
                storyboard_draft_identity=thaw(identities['storyboard_draft']),storyboard_review_identity=thaw(identities['storyboard_review']),
                visual_contract_identity=thaw(identities.get('visual_contract')))
            report=dict(schema_version=1,run_id=run.name,created_at=now(),status='review_required',passed=False,
                storyboard_identity=thaw(identities['storyboard']),input_map_identity=thaw(map_identity),
                effective_image_settings=dict(width=width,height=height,aspect_ratio='16:9',adaptation='contain_black_pad'),
                global_visual=board['global_visual'],references=references,images=[images[s['shot_id']] for s in board['shots']],
                requirement_images=requirement_images(board,{uid:item['image_identity'] for uid,item in images.items()}),
                provenance=provenance,validation=_validation(False),request_evidence=evidence)
            current=store.snapshot();verified=_validate_draft(config,run,report,board,current)
            _unchanged(store,current,dict(identities,**verified),run,owner)
            atomic_report(run/'images-draft.json',report)
            if not _same(read_json(run/'images-draft.json'),report):raise OSError('image draft readback differs')
            store.record_stage('start_images','running',artifacts=[_artifact(hash_file(run/'images-draft.json'))])
            return _result(run,'review_required',len(images))
        except StartImageRefusal:raise
        except BaseException as exc:return _failure(run,store,logger,exc)


def _png(path,width,height):
    """Fresh structural RGB PNG decode without creating new consumer logs."""
    raw=path.read_bytes()
    if raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('invalid PNG header')
    pos=8;payload=[];header=None;ended=False
    while pos<len(raw):
        if pos+12>len(raw):raise ValueError('truncated PNG chunk')
        size=struct.unpack('>I',raw[pos:pos+4])[0];kind=raw[pos+4:pos+8];body=raw[pos+8:pos+8+size]
        if pos+12+size>len(raw) or zlib.crc32(kind+body)&0xffffffff!=struct.unpack('>I',raw[pos+8+size:pos+12+size])[0]:
            raise ValueError('PNG chunk CRC/size mismatch')
        if kind==b'IHDR':
            if header is not None or pos!=8:raise ValueError('duplicate/misordered PNG header')
            header=struct.unpack('>IIBBBBB',body)
        if kind==b'acTL':raise ValueError('animated PNG refused')
        if kind==b'IDAT':payload.append(body)
        pos+=size+12
        if kind==b'IEND':ended=True;break
    if not ended or pos!=len(raw) or header!=(width,height,8,2,0,0,0):raise ValueError('PNG must be exact target-size noninterlaced RGB24')
    decoder=zlib.decompressobj();limit=(width*3+1)*height
    pixels=decoder.decompress(b''.join(payload),limit+1)
    if not decoder.eof or decoder.unused_data or len(pixels)!=limit or any(pixels[i*(width*3+1)]>4 for i in range(height)):
        raise ValueError('PNG pixel payload mismatch')


def _validate_draft(config,run,draft,board,snapshot):
    imported=type(draft.get('schema_version')) is int and draft['schema_version']==2
    extra=' import_identity reused_units' if imported else ''
    keys(draft,'schema_version run_id created_at status passed storyboard_identity input_map_identity effective_image_settings global_visual references images requirement_images provenance validation request_evidence'+extra,'images draft')
    if type(draft['schema_version']) is not int or draft['schema_version'] not in (1,2) or draft['run_id']!=run.name or draft['status']!='review_required' or draft['passed'] is not False:
        raise ValueError('invalid image draft schema/state')
    _timestamp(draft['created_at'])
    if not _same(draft['validation'],_validation(False)):raise ValueError('invalid static/motion/sync validation')
    settings=draft['effective_image_settings'];keys(settings,'width height aspect_ratio adaptation','image settings')
    width,height=validate_dimensions(settings['width'],settings['height'])
    if settings['aspect_ratio']!='16:9' or settings['adaptation']!='contain_black_pad':raise ValueError('invalid image settings')
    if not _same(draft['global_visual'],board['global_visual']):raise ValueError('global descriptions changed')
    directions,identities=_directions(run,board)
    def bind(key,record,expected=None,local=False):
        identity=_fresh(record,run=run if local else None,expected=expected)
        # FileIdentity requires mtime as well as byte identity at this boundary.
        if identity.mtime_ns!=record['mtime_ns']:raise OSError('file mtime changed')
        identities[key]=identity;return identity
    bind('storyboard',draft['storyboard_identity'],run/'storyboard.json',True)
    keys(draft['provenance'],'config_identity input_map_source_identity ffmpeg_identity ffprobe_identity storyboard_draft_identity storyboard_review_identity visual_contract_identity','image provenance')
    from .pipeline_import import stage_draft_path
    expected_paths=dict(config_identity=config.config_file,ffmpeg_identity=config.tools['ffmpeg'],ffprobe_identity=config.tools['ffprobe'],
        storyboard_draft_identity=stage_draft_path(run,'storyboard',board),storyboard_review_identity=Path(board['review_identity']['path']))
    for key,path in expected_paths.items():bind(key,draft['provenance'][key],path,path.is_relative_to(run))
    contract=run/'logs/storyboard/visual-contract.json';record=draft['provenance']['visual_contract_identity']
    if contract.exists() != (record is not None):raise ValueError('visual contract presence drift')
    if record is not None:bind('visual_contract',record,contract,True)
    map_identity=bind('input_map',draft['input_map_identity'],run/'logs/start-images/input-map.json',True)
    mapping=read_json(Path(map_identity.path));validate_input_map(mapping,board)
    original=draft['provenance']['input_map_source_identity']
    original_path=Path(bind('input_map_source',original).path) if original is not None else None
    rebuilt,sources=_read_map(run,board,original_path)
    if not _same(mapping,rebuilt):raise ValueError('input map differs from original/default')
    identities.update(sources)
    evidence=draft['request_evidence']
    if not isinstance(evidence,dict) or not evidence:raise ValueError('image evidence map required')
    if directions and 'logs/start-images/visual-directions.json' not in evidence:
        raise ValueError('visual direction evidence missing')
    aliases=set()
    for name,identity in evidence.items():
        if not isinstance(name,str) or '\\' in name or Path(name).is_absolute() or Path(name).drive or Path(name).root or Path(name).as_posix()!=name or name.casefold() in aliases:
            raise ValueError('evidence alias/collision')
        aliases.add(name.casefold());path=_local(run,run/name)
        if not path.is_relative_to(run/'logs') and not path.is_relative_to(run/'workflows'):raise ValueError('invalid image evidence location')
        bind('evidence/'+name,identity,path,True)
    images=draft['images']
    if not isinstance(images,list) or [i.get('shot_id') for i in images] != [s['shot_id'] for s in board['shots']]:
        raise ValueError('image order/coverage mismatch')
    image_map={};model=None;template=None
    reused,origin_ids=_verified_reused_images(config,run,board,snapshot,draft['import_identity'],draft['reused_units']) if imported else ({},{})
    identities.update(origin_ids)
    for image,shot in zip(images,board['shots']):
        keys(image,'shot_id primary_unit_id origin image_identity source_identity width height format pixel_format adaptation parameters workflow_identity mapping_identity model_identity submission reference_entity_ids evidence_identities','image')
        uid=shot['shot_id'];expected=run/'shots'/uid/'start.png'
        image_id=bind('image/'+uid,image['image_identity'],expected,True);_png(expected,width,height);image_map[uid]=image
        if image['primary_unit_id']!=shot['primary_unit_id'] or not _same(image['reference_entity_ids'],shot['entity_ids']):raise ValueError('image association changed')
        if not _same([image['width'],image['height'],image['format'],image['pixel_format']],[width,height,'png','rgb24']):raise ValueError('image metadata mismatch')
        if uid in reused:
            if not _same(image,reused[uid]):raise ValueError('reused image differs from verified original record')
            continue
        names=image['evidence_identities']
        if not isinstance(names,list) or not names or any(not isinstance(n,str) or n not in evidence for n in names) or len(set(names))!=len(names):raise ValueError('image evidence missing/duplicated')
        unit=snapshot['units'].get('image',{}).get(uid)
        if unit is None or unit['status'] not in ('running','completed'):raise ValueError('image unit not prepared')
        if uid in mapping['shots']:
            if image['origin']!='user' or image['adaptation']!='contain_black_pad' or any(image[k] is not None for k in ('workflow_identity','mapping_identity','model_identity','submission')):
                raise ValueError('user image must have priority and no SDXL submission')
            if unit['submission'] is not None:raise ValueError('user image has unexpected submission')
            source=bind('source/'+uid,image['source_identity'],Path(mapping['shots'][uid]))
            copy=_archive_path(run,'shots',uid,source.path,board);copy_id=hash_file(_local(run,copy));identities['copy/'+uid]=copy_id
            if (copy_id.bytes,copy_id.sha256)!=(source.bytes,source.sha256):raise ValueError('archived user image differs')
            if not _same(image['parameters'],dict(filter=contain_filter(width,height),output_pixel_format='rgb24',frame_limit=1,overwrite=False)):
                raise ValueError('user adaptation parameters changed')
        else:
            if image['origin']!='sdxl' or image['adaptation']!='none':raise ValueError('missing image must use SDXL')
            if not _same(image['parameters'],image_parameters(shot,board['global_visual'],width,height,direction=directions.get(uid))):raise ValueError('SDXL parameters changed')
            if model is None:
                revision=_revision(config,run)
                model,_=_model(config,revision=revision) if revision is not None else _model(config)
                if revision is not None:identities.update(revision['model_loader_identities'])
            bound=bind('model/'+uid,image['model_identity'],config.models['sdxl'])
            if (model.sha256,model.bytes)!=(bound.sha256,bound.bytes):raise ValueError('SDXL differs from accepted model')
            bind('workflow/'+uid,image['workflow_identity'],config.workflows['sdxl'])
            bind('mapping/'+uid,image['mapping_identity'],config.workflows['sdxl'].with_suffix('.mapping.json'))
            if template is None:template=_template(config,revision=revision) if revision is not None else _template(config)
            submission=image['submission'];keys(submission,'attempt_id prompt_id intent_identity','image submission')
            saved=unit['submission']
            if saved is None or saved['state']!='completed' or saved['attempt_id']!=submission['attempt_id'] or saved['prompt_id']!=submission['prompt_id']:
                raise ValueError('image submission not bound to completed history')
            intent=bind('intent/'+uid,submission['intent_identity'],Path(saved['request_path']),True)
            registered=snapshot['workflows'].get(saved['attempt_id'])
            if registered is None or registered['sha256']!=intent.sha256:raise ValueError('actual workflow missing from manifest')
            params=image['parameters'];graph=template.instantiate(dict(positive_prompt=params['positive'],negative_prompt=params['negative'],
                seed=params['seed'],width=width,height=height),output_prefix=f'{run.name}/start_images/{uid}')
            if not _same(graph,read_json(Path(intent.path))):raise ValueError('actual workflow differs from recorded parameters')
            source=bind('source/'+uid,image['source_identity'],local=True);source_path=Path(source.path)
            if source_path.parent!=run/'comfy/output'/run.name/'start_images' or not source_path.name.startswith(uid+'_') or source_path.suffix.lower()!='.png':raise ValueError('SDXL source path mismatch')
            if (source.bytes,source.sha256)!=(image_id.bytes,image_id.sha256):raise ValueError('SDXL output copy differs')
            history=read_json(_local(run,Path(saved['response_path'])))
            entry=history.get(saved['prompt_id'],{})
            if entry.get('status',{}).get('completed') is not True or entry.get('status',{}).get('status_str')!='success':raise ValueError('SDXL history is not successful')
            outputs=entry.get('outputs',{}).get(template.mapping['output']['node_id'],{}).get('images')
            if not isinstance(outputs,list) or len(outputs)!=1 or output_path(run,outputs[0])!=source_path:raise ValueError('SDXL history source mismatch')
            if Path(saved['response_path']).relative_to(run).as_posix() not in names or Path(intent.path).relative_to(run).as_posix() not in names:
                raise ValueError('history/workflow image evidence missing')
        _media_evidence(config,run,image,board,evidence)
    if set(snapshot['units'].get('image',{}))!=set(image_map):raise ValueError('unexpected image units')
    reference_inputs={}
    for eid,name in mapping['entities'].items():
        source=sources['entities/'+eid];copy_path=_archive_path(run,'entities',eid,name,board)
        copy=hash_file(_local(run,copy_path));identities['reference/'+eid]=copy
        if (copy.bytes,copy.sha256)!=(source.bytes,source.sha256):raise ValueError('user reference copy differs')
        reference_inputs[eid]=(thaw(copy),thaw(source))
    references=draft['references']
    if not isinstance(references,list) or len(references)!=len(_references(board,image_map,reference_inputs)):raise ValueError('reference coverage mismatch')
    for item,expected in zip(references,_references(board,image_map,reference_inputs)):
        keys(item,'entity_id source_kind identity source_identity reference_usage reference_shot_id','reference')
        bound=bind('reference/'+item['entity_id'],item['identity'],Path(expected['identity']['path']),True)
        if bound.sha256!=expected['identity']['sha256'] or any(not _same(item[k],expected[k]) for k in ('entity_id','source_kind','reference_usage','reference_shot_id')):
            raise ValueError('reference association changed')
        if item['source_kind']=='user':bind('reference_source/'+item['entity_id'],item['source_identity'],Path(expected['source_identity']['path']))
        elif item['source_identity'] is not None:raise ValueError('generated comparison reference has no user source')
    if not _same(draft['requirement_images'],requirement_images(board,{uid:i['image_identity'] for uid,i in image_map.items()})):
        raise ValueError('requirement image association/coverage changed')
    _again(identities);return identities


def _media_evidence(config,run,image,board,evidence):
    uid=image['shot_id'];names=set(image['evidence_identities']);width=image['width'];height=image['height']
    target=Path(image['image_identity']['path'])
    source=Path(image['source_identity']['path'])
    if image['origin']=='user':source=_archive_path(run,'shots',uid,source,board)
    expected={source,target};inspected=set();converted=False
    def command(record,args):
        keys(record,'args cwd returncode timed_out stdout_path stderr_path started_at finished_at','image command evidence')
        if type(record['returncode']) is not int or record['returncode']!=0 or record['timed_out'] is not False or record['cwd']!=str(run) or not _same(record['args'],[str(a) for a in args]):
            raise ValueError('image command evidence mismatch/failure')
        _timestamp(record['started_at']);_timestamp(record['finished_at'])
        if datetime.fromisoformat(record['finished_at'])<datetime.fromisoformat(record['started_at']):raise ValueError('command evidence time reversed')
        for key in ('stdout_path','stderr_path'):
            path=_local(run,Path(record[key]))
            if path.relative_to(run).as_posix() not in names:raise ValueError('image probe/decode/convert logs not covered')
        return Path(record['stdout_path'])
    for name in names:
        path=run/name
        if path.parent!=run/'logs/start-images' or not path.name.startswith(('media-'+uid+'-','convert-'+uid+'.')) or path.suffix!='.json':continue
        record=read_json(path)
        if path.name.startswith('media-'):
            keys(record,'info probe commands','image inspection evidence');info=record['info']
            keys(info,'identity width height format pixel_format','image inspection info')
            actual=_fresh(info['identity'],run=run);image_path=Path(actual.path)
            if image_path not in expected:raise ValueError('media evidence belongs to another image')
            commands=record['commands']
            if not isinstance(commands,list) or len(commands)!=2:raise ValueError('probe and full decode evidence required')
            stdout=command(commands[0],(config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',image_path))
            if not _same(read_json(stdout),record['probe']):raise ValueError('probe raw evidence differs')
            streams=record['probe'].get('streams')
            if not isinstance(streams,list) or len(streams)!=1 or streams[0].get('nb_read_frames')!='1' or streams[0].get('codec_type')!='video':raise ValueError('single image probe evidence required')
            stream=streams[0]
            if not _same([stream.get(k) for k in ('width','height','codec_name','pix_fmt')],[info[k] for k in ('width','height','format','pixel_format')]):raise ValueError('inspection metadata differs from probe')
            if image_path==target and not _same([info['width'],info['height'],info['format'],info['pixel_format']],[width,height,'png','rgb24']):raise ValueError('target image probe mismatch')
            command(commands[1],(config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',image_path,'-f','null','-'))
            inspected.add(image_path)
        else:
            keys(record,'source target filter command','image conversion evidence')
            if image['origin']!='user' or record['filter']!=contain_filter(width,height):raise ValueError('conversion must be exact contain filter')
            _fresh(record['source']['identity'],run=run,expected=source);_fresh(record['target']['identity'],run=run,expected=target)
            command(record['command'],(config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',source,'-vf',contain_filter(width,height),
                '-frames:v','1','-pix_fmt','rgb24',target));converted=True
    if inspected!=expected or image['origin']=='user' and not converted:raise ValueError('source/target probe, full decode and conversion evidence required')
    if image['origin']=='sdxl':
        saved=image['submission'];graph=read_json(Path(saved['intent_identity']['path']))
        post=False;remote=False;tracking=False
        for name in names:
            if not name.startswith('logs/http/') or not name.endswith('.request.json'):continue
            request=read_json(run/name)
            stem=name[:-len('.request.json')]
            required={stem+'.request.json',stem+'.response.json',stem+'.body'}
            if not required<=names:raise ValueError('incomplete HTTP request/response evidence')
            response=read_json(run/(stem+'.response.json'))
            if response.get('status')!=200 or response.get('truncated') is not False or response.get('error') is not None:continue
            if request.get('url')==config.services['comfyui']+'/prompt' and request.get('method')=='POST':
                if not _same(request.get('json_body',{}).get('prompt'),graph):raise ValueError('actual HTTP graph differs')
                accepted=read_json(run/(stem+'.body'))
                if accepted.get('prompt_id')!=saved['prompt_id']:raise ValueError('HTTP acceptance prompt mismatch')
                post=True
            if request.get('url')==config.services['comfyui']+'/object_info':remote=True
            if request.get('url')==config.services['comfyui']+'/history/'+saved['prompt_id']:tracking=True
        if not (post and remote and tracking):raise ValueError('remote validation/submission/history HTTP evidence missing')


def _visual_note(run,path,draft,data,entry):
    note=read_json(path)
    keys(note,'schema_version run_id draft_identity review_method reviewer viewed_at references entries','direct image observation')
    if type(note['schema_version']) is not int or note['schema_version']!=1 or note['run_id']!=run.name or note['review_method']!=data['review_method'] or note['reviewer']!=data['reviewer']:
        raise ValueError('direct observation schema/run/reviewer mismatch')
    _timestamp(note['viewed_at'])
    viewed=datetime.fromisoformat(note['viewed_at'])
    if not datetime.fromisoformat(draft['created_at'])<=viewed<=datetime.fromisoformat(data['reviewed_at']):raise ValueError('observation outside review time')
    _fresh(note['draft_identity'],run=run,expected=run/'images-draft.json')
    if not _same(note['references'],draft['references']):raise ValueError('direct observation reference mismatch')
    records=note['entries']
    if not isinstance(records,list) or not records:raise ValueError('actual image observation entries required')
    matched=False;seen=set();expected_items=draft['requirement_images']
    for item in records:
        keys(item,'shot_id requirement_id requirement_index unit_id source_quote image_shot_id role image_identity observation','direct observation item')
        binding={key:item[key] for key in expected_items[0]}
        if type(item['requirement_index']) is not int or not any(_same(binding,expected) for expected in expected_items):raise ValueError('observation PNG/original requirement mismatch')
        key=(item['shot_id'],item['requirement_index'])
        if key in seen:raise ValueError('duplicate direct observation');
        seen.add(key)
        if not isinstance(item['observation'],str) or not item['observation'].strip():raise ValueError('actual static observation required')
        if _same(binding,{key:entry[key] for key in binding}):matched=True
    if not matched:raise ValueError('review entry has no directly bound image observation')


def _review(run,path,draft,draft_identity):
    identity=hash_file(path);data=read_json(path)
    keys(data,'schema_version run_id draft_identity storyboard_identity review_method reviewer reviewed_at global_verdict reason entries','visual review')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name or data['review_method'] not in ('agent_visual','human_visual'):
        raise ValueError('visual review schema/run/method mismatch')
    for field in ('reviewer','reason'):
        if not isinstance(data[field],str) or not data[field].strip():raise ValueError('visual review text required')
    _timestamp(data['reviewed_at'])
    if datetime.fromisoformat(data['reviewed_at'])<datetime.fromisoformat(draft['created_at']):raise ValueError('review predates images')
    identities=dict(review=identity,draft=_fresh(data['draft_identity'],run=run,expected=run/'images-draft.json'),
        storyboard=_fresh(data['storyboard_identity'],run=run,expected=run/'storyboard.json'))
    if identities['draft'].sha256!=draft_identity.sha256 or identities['storyboard'].sha256!=draft['storyboard_identity']['sha256']:
        raise ValueError('review source identity differs')
    if data['global_verdict']!='passed':raise ValueError('global image review not passed')
    entries=data['entries']
    if not isinstance(entries,list) or len(entries)!=len(draft['requirement_images']):raise ValueError('visual review missing requirements')
    for index,(entry,expected) in enumerate(zip(entries,draft['requirement_images'])):
        keys(entry,'shot_id requirement_id requirement_index unit_id source_quote image_shot_id role image_identity evidence_identity verdict reason','visual review entry')
        if type(entry['requirement_index']) is not int or not _same({k:entry[k] for k in expected},expected):raise ValueError('visual review image/source/association changed')
        if entry['verdict']!='passed' or not isinstance(entry['reason'],str) or not entry['reason'].strip():raise ValueError('required static image review not passed')
        note=_fresh(entry['evidence_identity'],run=run)
        if not Path(note.path).is_relative_to(run/'logs/start-images') or Path(note.path) in (path,run/'logs/start-images/input-map.json'):
            raise ValueError('direct image review evidence must be in logs/start-images')
        if note.bytes==0:raise ValueError('empty image review evidence')
        _visual_note(run,Path(note.path),draft,data,entry)
        identities[f'note/{index}']=note
    _again(identities);return identities


@production_execution
def finalize_start_images(config, *, run_dir:Path,review_path:Path)->StartImagesResult:
    run=_run_path(run_dir);review_path=_review_path(run,review_path);store=ManifestStore.open(run)
    with _exclusive(run) as owner:
        snapshot=store.snapshot();stage=snapshot['stages']['start_images'];draft_path=run/'images-draft.json'
        if stage['status']!='running' or not draft_path.is_file() or (run/'images.json').exists():
            raise StartImageRefusal('running image draft required; no completed/orphan overwrite')
        logger=RunLogger(run);count=0
        try:
            board,identities=_input_files(config,run)
            artifacts=[a for a in stage['artifacts'] if Path(a['path'])==draft_path]
            if len(artifacts)!=1:raise ValueError('image draft not registered')
            draft_id=_fresh(artifacts[0],run=run,expected=draft_path);draft=read_json(draft_path)
            identities.update(_validate_draft(config,run,draft,board,snapshot));identities['draft']=draft_id
            identities.update(_review(run,review_path,draft,draft_id));count=len(draft['images'])
            report=dict(draft,status='completed',passed=True,validation=_validation(True),review_identity=thaw(identities['review']))
            _unchanged(store,snapshot,identities,run,owner)
            atomic_report(run/'images.json',report);identity=hash_file(run/'images.json')
            if not _same(read_json(run/'images.json'),report):raise OSError('images final readback differs')
            _unchanged(store,snapshot,identities,run,owner);_again({'images':identity})
            # All units and the stage become terminal in one manifest transaction.
            def commit(data):
                for image in draft['images']:
                    if image['shot_id'] in draft.get('reused_units',{}):continue
                    record=data['units']['image'][image['shot_id']]
                    store._record_status(data,record,'completed',[_artifact(identity),_artifact(hash_file(Path(image['image_identity']['path']))),
                        _artifact(identities['review'])],None,'start_images',image['shot_id'])
                store._record_status(data,data['stages']['start_images'],'completed',[_artifact(identity)],None,'start_images',None)
            store.update(commit)
            return _result(run,'completed',count)
        except BaseException as exc:return _failure(run,store,logger,exc,count)


from .verification import verified_read


@verified_read
def load_committed_start_images(run_dir:Path)->dict:
    run=_run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['start_images']
    if (run/'images.json').is_file() and read_json(run/'images.json').get('schema_version')==2 and not (run/'images-draft.json').is_file():
        from .pipeline_import import load_imported_stage
        return load_imported_stage(run,'start_images')
    if stage['status']!='completed':raise ValueError('start_images not completed')
    artifacts=[a for a in stage['artifacts'] if Path(a['path'])==run/'images.json']
    if len(artifacts)!=1:raise ValueError('images artifact missing/duplicated')
    identity=_fresh(artifacts[0],run=run,expected=run/'images.json');report=read_json(run/'images.json')
    config=load_config(Path(snapshot['config_snapshot']['path']));board,identities=_input_files(config,run)
    draft_identity=hash_file(_local(run,run/'images-draft.json'));draft=read_json(run/'images-draft.json')
    identities.update(_validate_draft(config,run,draft,board,snapshot));identities['draft']=draft_identity
    review_path=_review_path(run,Path(report['review_identity']['path']));review_id=_fresh(report['review_identity'],run=run,expected=review_path)
    identities.update(_review(run,review_path,draft,draft_identity));identities['images']=identity
    if review_id.sha256!=identities['review'].sha256:raise ValueError('review drift')
    expected=dict(draft,status='completed',passed=True,validation=_validation(True),review_identity=report['review_identity'])
    if not _same(report,expected):raise ValueError('images report differs from reviewed draft')
    for image in report['images']:
        unit=snapshot['units']['image'][image['shot_id']]
        if unit['status']!='completed':raise ValueError('image unit not completed')
        if image['shot_id'] in report.get('reused_units',{}):
            if unit['submission'] is not None:raise ValueError('reused image cannot claim a child POST')
            continue
        wanted=[run/'images.json',Path(image['image_identity']['path']),review_path]
        if [Path(a['path']) for a in unit['artifacts']]!=wanted:raise ValueError('image unit artifacts differ')
        for item in unit['artifacts']:_fresh(item,run=run)
    _again(identities)
    current=store.snapshot()
    if current['stages']['start_images']!=stage or current['stages']['storyboard']!=snapshot['stages']['storyboard'] or current['units']['image']!=snapshot['units']['image']:
        raise OSError('image/storyboard state changed during consume')
    return report


def image_import_inventory(parent_run_dir,run_dir,unit_ids=None):
    """Select only already reviewed, fully consumed original static images."""
    from .pipeline_import import collect_report_sources,content_signature
    parent,run=_run_path(parent_run_dir),_run_path(run_dir)
    report=load_committed_start_images(parent);snapshot=ManifestStore.open(parent).snapshot();source_id=hash_file(parent/'images.json')
    all_ids=tuple(i['shot_id'] for i in report['images']);selected=all_ids if unit_ids is None else tuple(unit_ids)
    if not selected or selected!=tuple(uid for uid in all_ids if uid in selected):raise ValueError('image reuse IDs must be exact stable reviewed subset')
    sources=collect_report_sources(report,parent);sources[source_id.path]=thaw(source_id);copies=[];units=[]
    for image in report['images']:
        uid=image['shot_id']
        if uid not in selected:continue
        original=hash_file(Path(image['image_identity']['path']))
        copies.append(dict(original_identity=thaw(original),copy_path=run/'shots'/uid/'start.png',role='start_image',stage='start_images',unit_id=uid))
        old=report.get('reused_units',{}).get(uid)
        units.append(dict(id=uid,source_record=snapshot['units']['image'][uid],imported_record=dict(stage='start_images',
            origin_run_id=old['origin_run_id'] if old else parent.name,source_report_identity=old['source_report_identity'] if old else thaw(source_id),
            source_unit_id=old['source_unit_id'] if old else uid),signature=old['signature'] if old else content_signature(image),origin='reused_verified'))
    for ref in report['references']:
        if ref['source_kind']=='user':
            original=hash_file(Path(ref['identity']['path']))
            copies.append(dict(original_identity=thaw(original),copy_path=run/Path(original.path).relative_to(parent),
                role='user_reference',stage='start_images',unit_id=None))
    stage=dict(id='start_images',source_record=snapshot['stages']['start_images'],imported_record=dict(source_report_identity=thaw(source_id)),
        signature=content_signature(report),origin='reused_verified')
    return dict(source_identities=sources,copies=copies,stage=stage,units=units)


def _verified_reused_images(config,run,board,snapshot,import_identity,reused_units):
    from .pipeline_import import load_pipeline_import,import_source_identities,same_identity,fresh
    from collections.abc import Mapping
    if not isinstance(reused_units,Mapping) or not reused_units:raise ValueError('image reuse origin map required')
    registered=snapshot['workflows'].get('pipeline_import')
    if registered is None or not same_identity(registered,import_identity):raise ValueError('image import not registered')
    receipt=load_pipeline_import(run,identity=import_identity)
    stage_rows=[r for r in receipt['stages'] if r['id']=='start_images']
    if len(stage_rows)!=1:raise ValueError('image original reviewed stage missing')
    parent=run.parent/receipt['parent_run_id'];original=None
    if stage_rows[0]['origin']!='completed_saved_submission':
        original=load_committed_start_images(parent)
        source_id=stage_rows[0]['imported_record']['source_report_identity']
        if not same_identity(hash_file(parent/'images.json'),source_id):raise ValueError('original reviewed image report differs')
    parent_board=load_committed_storyboard(parent)
    if not _same(board['global_visual'],parent_board['global_visual']):raise ValueError('reused image global visual meaning changed')
    rows={r['id']:r for r in receipt['units'] if r['imported_record'].get('stage')=='start_images'}
    if set(rows)!=set(reused_units):raise ValueError('image reuse coverage differs from import')
    result={};original_reports={}
    for uid,reused in reused_units.items():
        keys(thaw(reused),'origin_run_id source_report_identity source_unit_id signature import_identity','reused image')
        row=rows[uid];origin=row['imported_record']
        if any(not _same(thaw(reused[k]),thaw(origin[k])) for k in ('origin_run_id','source_report_identity','source_unit_id')) or reused['signature']!=row['signature'] or not same_identity(reused['import_identity'],import_identity):
            raise ValueError('image original origin/signature differs')
        current=[s for s in board['shots'] if s['shot_id']==uid];prior=[s for s in parent_board['shots'] if s['shot_id']==origin['source_unit_id']]
        if len(current)!=1 or len(prior)!=1:raise ValueError('reused image shot missing')
        for field in ('image_prompt','primary_unit_id','entity_ids','visual_requirements'):
            if not _same(current[0][field],prior[0][field]):raise ValueError('reused original image requirement changed')
        if row['origin']=='completed_saved_submission':
            from ._pipeline_saved_import import consume_reconciled_unit
            image=consume_reconciled_unit(parent,row)
        else:
            if stage_rows[0]['origin']=='completed_saved_submission':
                origin_run=run.parent/origin['origin_run_id']
                if origin_run.name not in original_reports:original_reports[origin_run.name]=load_committed_start_images(origin_run)
                reviewed=original_reports[origin_run.name]
                if not same_identity(hash_file(origin_run/'images.json'),origin['source_report_identity']):raise ValueError('nested original reviewed image report differs')
            else:
                if original is None:original=load_committed_start_images(parent)
                reviewed=original
            image=next(i for i in reviewed['images'] if i['shot_id']==origin['source_unit_id'])
        if image['origin']=='sdxl':
            for label,key,path in (('model','model_identity',config.models['sdxl']),
                    ('workflow','workflow_identity',config.workflows['sdxl']),
                    ('mapping','mapping_identity',config.workflows['sdxl'].with_suffix('.mapping.json'))):
                prior_identity=fresh(image[key]);current_identity=hash_file(path)
                if (prior_identity.bytes,prior_identity.sha256)!=(current_identity.bytes,current_identity.sha256):
                    raise ValueError(f'current SDXL {label} content differs from reused original')
                _again({label:current_identity})
        copied=[r for r in receipt['copies'] if r['stage']=='start_images' and r['unit_id']==uid and r['role']=='start_image']
        if len(copied)!=1 or not same_identity(copied[0]['original_identity'],image['image_identity']):raise ValueError('image original copy association differs')
        identity=fresh(copied[0]['copy_identity']);expected=run/'shots'/uid/'start.png'
        if Path(identity.path)!=expected:raise ValueError('image copy canonical target differs')
        unit=snapshot['units']['image'].get(uid)
        if unit is None or unit['status']!='completed' or unit['submission'] is not None:raise ValueError('reused image must retain completed original with no child submission')
        artifacts=[a for a in unit['artifacts'] if a['path']==identity.path]
        if len(artifacts)!=1 or artifacts[0]['sha256']!=identity.sha256 or artifacts[0]['bytes']!=identity.bytes:raise ValueError('reused PNG not registered')
        _png(expected,image['width'],image['height']);result[uid]=dict(image,image_identity=thaw(copied[0]['copy_identity']))
    return result,{'image-import/'+path:identity for path,identity in import_source_identities(run).items()}


@production_execution
def resume_start_images(config, *, run_dir, reuse_context):
    """Prepare a mixed native/imported draft; complete visual review remains required."""
    from .pipeline_import import verify_reuse_context,load_pipeline_import
    run=_run_path(run_dir);store=ManifestStore.open(run)
    with _exclusive(run) as owner:
        snapshot=store.snapshot()
        if snapshot['stages']['start_images']['status']!='pending' or any((run/p).exists() for p in ('images-draft.json','images.json')):
            raise StartImageRefusal('image recovery requires independent pending stage')
        board,identities=_input_files(config,run);unit_ids=tuple(s['shot_id'] for s in board['shots'])
        verified=verify_reuse_context(run,reuse_context,stage='start_images',unit_ids=unit_ids,current_input_identities=identities)
        images,origin_ids=_verified_reused_images(config,run,board,snapshot,verified.import_identity,verified.verified_units)
        identities.update(origin_ids)
        if set(snapshot['units']['image'])!=set(images):raise StartImageRefusal('remaining images contain unknown or submitted units')
        for uid in verified.remaining_units:
            if (run/'shots'/uid/'start.png').exists():raise StartImageRefusal('remaining image has orphan PNG; no overwrite')
        receipt=load_pipeline_import(run,identity=verified.import_identity);parent=run.parent/receipt['parent_run_id']
        if any(r['origin']=='completed_saved_submission' for r in receipt['units'] if r['imported_record'].get('stage')=='start_images'):
            from ._pipeline_saved_import import reconciled_image_context
            source=reconciled_image_context(parent,[r for r in receipt['units'] if r['imported_record'].get('stage')=='start_images'])
        else:source=load_committed_start_images(parent)
        settings=source['effective_image_settings'];width,height=validate_dimensions(settings['width'],settings['height'])
        logger=RunLogger(run);paths=RuntimePaths.from_config(config)
        try:
            _again(identities);_check_lock(run,owner);store.record_stage('start_images','running')
            user_refs={r['entity_id']:r for r in source['references'] if r['source_kind']=='user'}
            mapping=dict(schema_version=1,run_id=run.name,shots={},entities={eid:r['source_identity']['path'] for eid,r in user_refs.items()})
            source_map=logger.save_json('start-images/resume-inputs.json',mapping)
            mapping,map_sources=_read_map(run,board,source_map);identities.update(map_sources)
            map_path=logger.save_json('start-images/input-map.json',mapping);evidence={};_evidence(run,evidence,[map_path])
            references={}
            for eid,name in mapping['entities'].items():
                target=_archive_path(run,'entities',eid,name,board)
                identity=hash_file(target) if target.exists() else _copy(run,Path(name),target)
                source_id=map_sources['entities/'+eid]
                if (identity.bytes,identity.sha256)!=(source_id.bytes,source_id.sha256):raise ValueError('original shared reference differs')
                references[eid]=(thaw(identity),thaw(source_id))
            missing=[s for s in board['shots'] if s['shot_id'] in verified.remaining_units]
            if missing:images.update(_generate_owned(config,run,store,logger,board,missing,width,height,evidence))
            report=dict(schema_version=2,run_id=run.name,created_at=now(),status='review_required',passed=False,
                storyboard_identity=thaw(identities['storyboard']),input_map_identity=thaw(hash_file(map_path)),effective_image_settings=settings,
                global_visual=board['global_visual'],references=_references(board,images,references),images=[images[s['shot_id']] for s in board['shots']],
                requirement_images=requirement_images(board,{uid:i['image_identity'] for uid,i in images.items()}),
                provenance=dict(config_identity=thaw(identities['config']),input_map_source_identity=thaw(hash_file(source_map)),
                    ffmpeg_identity=thaw(identities['ffmpeg']),ffprobe_identity=thaw(identities['ffprobe']),
                    storyboard_draft_identity=thaw(identities['storyboard_draft']),storyboard_review_identity=thaw(identities['storyboard_review']),
                    visual_contract_identity=thaw(identities.get('visual_contract'))),validation=_validation(False),request_evidence=evidence,
                import_identity=thaw(verified.import_identity),reused_units=thaw(verified.verified_units))
            current=store.snapshot();validated=_validate_draft(config,run,report,board,current)
            _unchanged(store,current,dict(identities,**validated),run,owner)
            atomic_report(run/'images-draft.json',report)
            if not _same(read_json(run/'images-draft.json'),report):raise OSError('mixed image draft readback differs')
            _unchanged(store,current,dict(identities,**validated),run,owner)
            store.record_stage('start_images','running',artifacts=[_artifact(hash_file(run/'images-draft.json'))])
            return _result(run,'review_required',len(images))
        except BaseException as exc:return _failure(run,store,logger,exc,len(images))
