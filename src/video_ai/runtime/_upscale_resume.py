"""Once-only resume admission and immutable receipt-bound execution policy.

Historical records are reconstructed now, not claimed to have been indexed earlier.
Admission uses the same raw graph/HTTP/PNG/media validators as final consumption.
"""
from copy import deepcopy
from datetime import datetime
import math
import os
from pathlib import Path
from uuid import uuid4

from ..config import read_json
from ..planning.start_images import keys
from .manifest import hash_file, thaw, now, _timestamp
from .timeline_checks import _local, _again
from ._upscale_inputs import fresh, same, evidence
from ._legacy_execution_policy import unlimited_policy,receipt_fields

POLICY_FIELDS='total_timeout_seconds frame_timeout_seconds media_command_timeout_seconds request_timeout_seconds'
RECEIPT_FIELDS='schema_version run_id created_at authorization manifest_identity unit_id reused_identities execution_policy'


def policy(config, *, legacy=False):
    value=dict(total_timeout_seconds=None,frame_timeout_seconds=config.timeouts['upscale_frame'] if legacy else None,
        media_command_timeout_seconds=300 if legacy else None,request_timeout_seconds=config.timeouts['comfy_request'])
    if not legacy:value['time_limits']='unlimited_v1'
    check_policy(value)
    return value


def check_policy(value):
    current='time_limits' in value
    keys(value,POLICY_FIELDS+(' time_limits' if current else ''),'resume execution policy')
    if current:
        if (value['time_limits']!='unlimited_v1' or value['total_timeout_seconds'] is not None
                or value['frame_timeout_seconds'] is not None or value['media_command_timeout_seconds'] is not None):
            raise ValueError('unlimited resume execution policy differs')
        request=value['request_timeout_seconds']
        if type(request) not in (int,float) or not math.isfinite(request) or request<=0:raise ValueError('finite positive request timeout required')
        return
    if value['total_timeout_seconds'] is not None or type(value['media_command_timeout_seconds']) is not int or value['media_command_timeout_seconds']!=300:
        raise ValueError('resume total/media policy differs')
    for key in ('frame_timeout_seconds','request_timeout_seconds'):
        if type(value[key]) not in (int,float) or not math.isfinite(value[key]) or value[key]<=0:raise ValueError('finite positive resume operation timeout required')


def check_config_policy(value,config):
    """Both historical and current policies replay independently of call scope."""
    check_policy(value)
    if not same(value,policy(config,legacy='time_limits' not in value)):
        raise ValueError('execution policy differs from frozen config')


def prefix(snapshot,plans=None, *, _pipeline=False,_imported=()):
    allowed=('running','failed','interrupted','ambiguous') if _pipeline else ('ambiguous',)
    if snapshot['stages']['upscale']['status'] not in allowed or snapshot['stages']['upscale']['artifacts'] or any(n in snapshot['workflows'] for n in ('upscale_resume','upscale_report')):
        raise ValueError('one stopped ambiguous upscale stage without report/receipt required')
    units=snapshot['units']['frame'];order=list(units)
    canonical=[f'{p.shot_id}:frame_{i:06d}' for p in plans for i in range(1,p.source_frames+1)] if plans is not None else sorted(order)
    native_order=[uid for uid in order if uid not in _imported]
    native_canonical=[uid for uid in canonical if uid not in _imported]
    if set(_imported)-set(canonical) or native_order!=native_canonical[:len(native_order)]:raise ValueError('canonical contiguous completed frame prefix required')
    tail=None
    for uid,unit in units.items():
        if unit['status']=='completed':
            if tail is not None or (unit['submission'] is None if uid not in _imported else unit['submission'] is not None) or unit['submission'] is not None and unit['submission']['state']!='completed':raise ValueError('completed prefix submission differs')
        elif uid==order[-1] and unit['status'] in (allowed if _pipeline else ('ambiguous',)) and (unit['submission'] is None or _pipeline and (unit['submission']['state'] in ('failed','rejected') or unit['status']=='failed' and unit['submission']['state']=='completed')) and not unit['artifacts']:
            tail=uid
        else:raise ValueError('resume forbids any submitted/nonempty terminal tail')
    return tail


def receipt(run,identity,snapshot, *, replay):
    record=thaw(identity);actual=fresh(record,run=run);path=Path(actual.path)
    if path.parent!=run/'logs/upscale' or not path.name.startswith('resume-') or path.name.startswith('resume-manifest-') or path.suffix!='.json':raise ValueError('canonical resume receipt required')
    token=path.stem[len('resume-'):]
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('resume receipt token differs')
    value=read_json(path);keys(value,RECEIPT_FIELDS,'resume receipt')
    if type(value['schema_version']) is not int or value['schema_version']!=1 or value['run_id']!=run.name or value['authorization']!='user_continue_no_total_timeout':raise ValueError('resume receipt authorization/schema differs')
    _timestamp(value['created_at']);check_policy(value['execution_policy'])
    old_path=run/'logs/upscale'/f'resume-manifest-{token}.json'
    old_id=fresh(value['manifest_identity'],run=run,expected=old_path);old=read_json(old_path)
    from .manifest import _validate
    _validate(old,run)
    from ..planning.upscale import plan_upscale
    plans=plan_upscale(read_json(_local(run,run/'source-clips.json')))
    if prefix(old,plans)!=value['unit_id']:raise ValueError('receipt old unsubmitted tail differs')
    created=datetime.fromisoformat(value['created_at']).timestamp()
    if created<datetime.fromisoformat(old['updated_at']).timestamp() or created>actual.mtime_ns/1e9 or old_id.mtime_ns>actual.mtime_ns:
        raise ValueError('stale or reversed resume receipt')
    ids={'resume':actual,'resume_manifest':old_id}
    index=value['reused_identities']
    if not isinstance(index,dict) or not index:raise ValueError('complete frozen reused identity index required')
    for name,entry in index.items():
        if type(name) is not str or '\\' in name or Path(name).is_absolute() or Path(name).as_posix()!=name or any(p in ('','.','..') for p in name.split('/')):raise ValueError('resume reused evidence alias')
        ids['reused/'+name]=fresh(entry) if name.startswith('inputs/') else fresh(entry,run=run,expected=_local(run,run/name))
    if not {'inputs/config','inputs/source_clips','inputs/source_review','inputs/model','inputs/workflow','inputs/mapping'}<=set(index):raise ValueError('complete reused input identity index required')
    if not replay and snapshot!=old:raise ValueError('resume old snapshot differs')
    _again(ids)
    return value,old,ids


def reject_historical_posts(run,request_paths,completed_frames, *, failed_evidence=None):
    """Every old POST must belong to a validated completed-frame checkpoint."""
    allowed={f"{frame['shot_id']}:frame_{frame['frame_index']:06d}":
        {run/name for name in frame['evidence_identities'] if name.startswith('logs/http/') and name.endswith('.request.json')}
        for frame in completed_frames}
    for uid,identities in (failed_evidence or {}).items():
        allowed[uid]={Path(identity.path) for identity in identities if identity.path.endswith('.request.json')}
    for path in request_paths:
        path=_local(run,Path(path));request=read_json(path)
        if request.get('stage')=='upscale' and request.get('method')=='POST' and path not in allowed.get(request.get('unit_id'),set()):
            raise ValueError('historical upscale POST lacks validated completed-frame evidence; no resubmission')


def replay(config,run,draft,snapshot):
    value=draft['execution_policy'];keys(value,POLICY_FIELDS+' resume_identity'+(' time_limits' if 'time_limits' in value else ''),'schema2 execution policy')
    check_config_policy({k:v for k,v in value.items() if k!='resume_identity'},config)
    if not same(value['resume_identity'],snapshot['workflows'].get('upscale_resume')):raise ValueError('resume policy receipt is not registered')
    proof,old,ids=receipt(run,value['resume_identity'],snapshot,replay=True)
    check_config_policy(proof['execution_policy'],config)
    if not same(proof['execution_policy'],{k:v for k,v in value.items() if k!='resume_identity'}):raise ValueError('receipt and draft policies differ')
    if prefix(old)!=proof['unit_id']:raise ValueError('old tail differs')
    for key in ('schema_version','run_id','created_at','inputs','models','config_snapshot','voice_snapshot'):
        if old[key]!=snapshot[key]:raise ValueError('resume frozen original manifest changed: '+key)
    for stage in ('preflight','speech','timeline','storyboard','start_images','source_clips'):
        if old['stages'][stage]!=snapshot['stages'][stage]:raise ValueError('resume original upstream stage changed')
    for kind,units in old['units'].items():
        if kind!='frame' and snapshot['units'].get(kind)!=units:raise ValueError('resume upstream units changed')
        for uid,unit in units.items():
            if kind!='frame' or unit['status']=='completed':
                if snapshot['units'][kind].get(uid)!=unit:raise ValueError('resume completed/upstream record changed')
    for key,entry in old['workflows'].items():
        if snapshot['workflows'].get(key)!=entry:raise ValueError('resume old workflow receipt changed')
    events=snapshot['events'];n=len(old['events'])
    if events[:n]!=old['events'] or len(events)<=n:raise ValueError('resume old events changed')
    event=events[n]
    if event['action']!='resume_unsubmitted_upscale' or event['unit_id']!=proof['unit_id'] or event['evidence_paths']!=[value['resume_identity']['path']]:raise ValueError('resume transaction event differs')
    # Only frozen historical paths belong here: current logs include the legitimate
    # new tail POST after resume. Revalidate their semantics independently of admission.
    completed={uid for uid,unit in old['units']['frame'].items() if unit['status']=='completed'}
    old_frames=[frame for clip in draft['clips'] for frame in clip['frames']
        if f"{frame['shot_id']}:frame_{frame['frame_index']:06d}" in completed]
    reject_historical_posts(run,[run/name for name in proof['reused_identities']
        if name.startswith('logs/http/') and name.endswith('.request.json')],old_frames)
    return ids


class StagedServiceStore:
    """Keep service admission from mutating the stopped manifest before commit."""
    def __init__(self,store):self.store=store;self.run_dir=store.run_dir;self.pending=[];self.active=False;self.preview=store.snapshot()
    def update(self,mutator):
        def checked(data):
            original=deepcopy(data);mutator(data)
            if any(data.get(k)!=v for k,v in original.items() if k!='services') or set(data)!=set(original):
                raise ValueError('service admission proxy permits only services updates')
            from .manifest import _validate
            _validate(data,self.run_dir)
        if self.active:self.store.update(checked)
        else:
            candidate=deepcopy(self.preview);checked(candidate);self.preview=candidate;self.pending.append(checked)
    def activate(self):
        self.active=True
        for mutator in self.pending:self.store.update(mutator)
        self.pending.clear()


def draft_data(run,context,clips,records, *, execution_policy=None):
    from ..planning.upscale import upscale_frame_mapping
    from ._upscale_evidence import validation, requirements
    value=dict(schema_version=1 if execution_policy is None else 2,run_id=run.name,created_at=now(),status='review_required',passed=False,
        source_clips_identity=thaw(context['identities']['source_clips']),source_review_identity=thaw(context['identities']['source_review']),
        source_review_method=context['source_review_method'],source_validation=context['source']['validation'],effective_media=context['source']['effective_media'],
        clips=clips,requirement_clips=requirements(context['source'],clips) if execution_policy is not None else [],
        frame_mappings=[upscale_frame_mapping(m,upscaled_identity=c['upscaled_identity']) for m,c in zip(context['source']['frame_mappings'],clips)] if execution_policy is not None else [],
        model_identity=thaw(context['identities']['model']),workflow_identity=thaw(context['identities']['workflow']),mapping_identity=thaw(context['identities']['mapping']),
        provenance=context['provenance'],validation=validation(False),request_evidence=records)
    if execution_policy is not None:value['execution_policy']=execution_policy
    return value


def reconstruct(config,run,snapshot,context, *, _receipt_paths=(), _pipeline=False):
    from ._upscale_evidence import validate, CLIP_FIELDS
    policy_identity=snapshot['workflows'].get('upscale_execution_policy');execution=None
    if policy_identity is not None:
        actual=fresh(policy_identity,run=run);execution=read_json(Path(actual.path))
        check_config_policy(execution,config)
    failed_evidence={};inherited={};inherited_clips={};origin_rows={}
    if _pipeline:
        from .pipeline_import import imported_unit_map,reused_upscale_frames,reused_upscale_clips,import_source_identities
        reuse_map,origin_rows=imported_unit_map(run,'upscale')
        if reuse_map:
            inherited=reused_upscale_frames(config,run,reuse_map,context)
            inherited_clips=reused_upscale_clips(config,run,reuse_map,context,inherited)
    if _pipeline:
        from .pipeline_recovery import validate_failed_submission
        for uid,unit in snapshot['units']['frame'].items():
            if unit['submission'] is not None and (unit['submission']['state'] in ('failed','rejected') or unit['status']=='failed' and unit['submission']['state']=='completed'):
                failed_evidence[uid]=validate_failed_submission(run,'upscale',uid,unit['submission'])
    unit_id=prefix(snapshot,context['plans'],_pipeline=_pipeline,_imported=inherited);records={};clips=[];partial={};completed=[]
    def index(paths):return evidence(run,records,paths)
    failure_sources={}
    if inherited:failure_sources.update({path:thaw(identity) for path,identity in import_source_identities(run).items()})
    for identities in failed_evidence.values():
        index([Path(identity.path) for identity in identities if Path(identity.path).is_relative_to(run)])
        failure_sources.update({identity.path:thaw(identity) for identity in identities if not Path(identity.path).is_relative_to(run)})
    for uid in failed_evidence:
        saved=snapshot['units']['frame'][uid]['submission']
        if saved['response_path'] is None:continue
        body=_local(run,Path(saved['response_path']));entry=read_json(body).get(saved['prompt_id'])
        request=body.with_suffix('.request.json');response=body.with_suffix('.response.json')
        sent=read_json(_local(run,request));received=read_json(_local(run,response))
        from .pipeline_recovery import _matches,_metadata
        if (not isinstance(entry,dict) or not _matches(_metadata(entry.get('prompt')),saved,read_json(Path(saved['request_path'])))
                or sent.get('method')!='GET' or sent.get('unit_id')!=uid or sent.get('url')!=config.services['comfyui']+'/history/'+saved['prompt_id']
                or received.get('status')!=200 or received.get('error') is not None or received.get('truncated') is not False):
            raise ValueError('failed unit original history transport binding differs')
        index([body,request,response])
    allowed=set();all_clips=[]
    for plan,source in zip(context['plans'],context['source']['clips']):
        uid=plan.shot_id;checkpoint=run/'logs/upscale'/f'clip-{uid}.json'
        if uid in inherited_clips:
            clips.append(inherited_clips[uid]);all_clips.append(inherited_clips[uid]);completed.append(uid)
            continue
        frames=[]
        for i in range(1,plan.source_frames+1):
            name=f'{uid}:frame_{i:06d}';unit=snapshot['units']['frame'].get(name)
            if unit is None or unit['status']!='completed':break
            if name in inherited:
                frames.append(inherited[name]);continue
            path=run/'logs/upscale'/f'frame-{uid}-{i:06d}.json'
            if not unit['artifacts'] or Path(unit['artifacts'][0]['path'])!=path:raise ValueError('retained frame checkpoint artifact missing')
            checkpoint_id=thaw(hash_file(_local(run,path)))
            checkpoint_id['verified_at']=unit['artifacts'][0]['verified_at']
            frame=read_json(path);frame=dict(frame,checkpoint_identity=checkpoint_id)
            index([run/n for n in frame['evidence_identities']]+[path]);frames.append(frame);allowed.add(path)
        directory=_local(run,run/'shots'/uid/'frames')
        if checkpoint.exists():
            clip=read_json(_local(run,checkpoint));keys(clip,CLIP_FIELDS+receipt_fields(clip),'retained clip')
            if any(f"{uid}:frame_{i+1:06d}" in inherited for i in range(len(frames))):
                extracts=list((run/'logs/upscale').glob(f'extract-{uid}-*.json'))
                if len(extracts)!=1:raise ValueError('one current extraction required for inherited frames')
                extracted=read_json(_local(run,extracts[0]))['frames']
                for i,frame in enumerate(frames):
                    name=f'{uid}:frame_{i+1:06d}'
                    if name in inherited:frames[i]=dict(frame,input_identity=extracted[i]['identity']);inherited[name]=frames[i]
            if clip['frames']!=frames:raise ValueError('retained clip frame checkpoints differ')
            index([run/n for n in clip['evidence_identities']]+[checkpoint]);clips.append(clip);completed.append(uid);allowed.add(checkpoint)
        elif directory.exists():
            if partial:raise ValueError('more than one partial extracted clip')
            extracts=list((run/'logs/upscale').glob(f'extract-{uid}-*.json'))
            if len(extracts)!=1:raise ValueError('one retained ordered extraction required')
            extraction=read_json(_local(run,extracts[0]));rows=extraction['frames'];base=index([extracts[0]])
            for frame_index,frame in enumerate(frames):
                name=f'{uid}:frame_{frame_index+1:06d}'
                if name in inherited:
                    frames[frame_index]=dict(frame,input_identity=rows[frame_index]['identity']);inherited[name]=frames[frame_index]
            for row in rows:base+=index([Path(row['identity']['path'])])
            for key in ('stdout_path','stderr_path'):base+=index([Path(extraction['command'][key])])
            for path in (run/'logs/upscale').glob('media-*.json'):
                data=read_json(_local(run,path));target=Path(data['info']['identity']['path'])
                if target.parent==directory:
                    base+=index([path]+[Path(c[k]) for c in data['commands'] for k in ('stdout_path','stderr_path')])
            clip=dict(shot_id=uid,primary_unit_id=plan.primary_unit_id,budget=thaw(plan.budget),source_identity=thaw(plan.source_identity),
                upscaled_identity=None,width=1920,height=1080,native_fps=16,source_frames=plan.source_frames,upscaled_frames=plan.source_frames,
                parameters=thaw(plan.parameters),frames=frames,evidence_identities=list(dict.fromkeys(base+[n for f in frames if f"{uid}:frame_{f['frame_index']:06d}" not in inherited for n in f['evidence_identities']]+[Path(f['checkpoint_identity']['path']).relative_to(run).as_posix() for f in frames if f"{uid}:frame_{f['frame_index']:06d}" not in inherited])))
            if execution is not None and execution.get('time_limits')=='unlimited_v1':clip['execution_policy']=unlimited_policy()
            partial[uid]=dict(rows=rows,base=list(dict.fromkeys(base)),frames=frames)
            if (run/'shots'/uid/'upscaled.mp4').exists():raise ValueError('orphan partially encoded video')
        else:
            if frames or checkpoint.exists() or (run/'shots'/uid/'upscaled-frames').exists() or (run/'shots'/uid/'upscaled.mp4').exists():raise ValueError('orphan upscale targets')
            continue
        all_clips.append(clip)
    # Discovery is only for rejection. Every admitted file must already be associated
    # through checkpoint/extraction/command identities, never glob order.
    logs=_local(run,run/'logs/upscale')
    for path in logs.iterdir():
        _local(run,path)
        if path.name.startswith(('resume-','resume-manifest-')) and path not in _receipt_paths:raise ValueError('orphan previous resume receipt')
        if path.name.startswith(('frame-','clip-')) and path not in allowed:raise ValueError('orphan frame/clip checkpoint')
        if path.name.startswith(('extract-','encode-','media-','video-')) and path.relative_to(run).as_posix() not in records:raise ValueError('unassociated historical media evidence')
    for record in [snapshot['stages']['upscale'],*snapshot['units']['frame'].values()]:
        error=record['error']
        if error is not None:
            paths=error.get('evidence_paths',[])
            if error.get('traceback_path') is not None:paths=[*paths,error['traceback_path']]
            index([_local(run,Path(path)) for path in paths])
    draft=draft_data(run,context,all_clips,records)
    if policy_identity is not None:
        index([Path(actual.path)])
        draft.update(schema_version=3,import_identity=None,reused_units={},execution_policy=execution,request_evidence=records)
    if inherited and draft['schema_version']==1:
        draft.update(schema_version=3,import_identity=None,reused_units={},execution_policy=policy(config))
    validate(config,run,draft,context,snapshot,_partial=True,_reused_frames=inherited or None,_reused_clips=inherited_clips or None)
    copy_id=None
    if unit_id is not None:
        uid,index_number=unit_id.split(':frame_');copy_path=_local(run,run/'comfy/input'/run.name/'upscale'/uid/f'frame_{index_number}.png')
        if copy_path.exists():
            original=run/'shots'/uid/'frames'/copy_path.name
            copy_id=thaw(hash_file(copy_path));source_id=hash_file(_local(run,original))
            if (copy_id['bytes'],copy_id['sha256'])!=(source_id.bytes,source_id.sha256):raise ValueError('retained unsubmitted copy differs')
            if copy_id['mtime_ns']/1e9>datetime.fromisoformat(snapshot['units']['frame'][unit_id]['finished_at']).timestamp():raise ValueError('retained input copy postdates stopped frame')
            index([copy_path])
    for namespace in ('input','output'):
        root=_local(run,run/'comfy'/namespace/run.name/'upscale')
        if root.exists():
            allowed_dirs=set()
            for name in records:
                target=run/name
                if target.is_relative_to(root):
                    allowed_dirs.update(p for p in target.parents if p.is_relative_to(root))
            for path in root.rglob('*'):
                _local(run,path)
                if path.is_file() and path.relative_to(run).as_posix() not in records:raise ValueError('orphan Comfy upscale file')
                if path.is_dir() and path not in allowed_dirs:raise ValueError('orphan Comfy upscale prefix')
    request_paths=list((run/'logs/http').glob('*.request.json'))
    for path in request_paths:
        request=read_json(_local(run,path))
        if (request.get('stage')=='upscale' and request.get('unit_id') in failed_evidence
                and request.get('method')=='GET' and request.get('url')==config.services['comfyui']+'/object_info'):
            response=path.with_name(path.name.replace('.request.json','.response.json'))
            body=path.with_name(path.name.replace('.request.json','.body'))
            metadata=read_json(_local(run,response))
            if metadata.get('status')!=200 or metadata.get('error') is not None or metadata.get('truncated') is not False:
                raise ValueError('failed original remote-template response is not complete')
            from ._upscale_inputs import validate_remote
            validate_remote(context['template'],read_json(_local(run,body)))
            index([path,response,body])
    # Run independently of indexing: old error evidence can already cover a POST.
    # This also runs inside resume_unsubmitted_upscale's locked reconstruction.
    reject_historical_posts(run,request_paths,[frame for clip in all_clips for frame in clip['frames'] if f"{frame['shot_id']}:frame_{frame['frame_index']:06d}" not in inherited],failed_evidence=failed_evidence)
    for path in request_paths:
        req=read_json(_local(run,path))
        if req.get('stage')=='upscale' and path.relative_to(run).as_posix() not in records:raise ValueError('unassociated historical upscale HTTP: '+path.name)
    return dict(unit_id=unit_id,input_copy=copy_id,completed_clips=completed,partial=partial,**({'known_failed_units':{uid:thaw(ids) for uid,ids in failed_evidence.items()},'failure_source_identities':failure_sources,'inherited_frames':inherited,'origin_rows':origin_rows} if _pipeline else {})),records,clips


def freeze(run,snapshot,records,config,context):
    token=uuid4().hex;old=run/'logs/upscale'/f'resume-manifest-{token}.json';path=run/'logs/upscale'/f'resume-{token}.json'
    original=_local(run,run/'manifest.json').read_bytes()
    if read_json(run/'manifest.json')!=snapshot:raise ValueError('manifest changed before resume snapshot')
    for target,content in ((old,original),):
        with _local(run,target).open('xb') as file:file.write(content);file.flush();os.fsync(file.fileno())
    data=dict(schema_version=1,run_id=run.name,created_at=now(),authorization='user_continue_no_total_timeout',
        manifest_identity=thaw(hash_file(old)),unit_id=prefix(snapshot),reused_identities=dict(deepcopy(records),**{'inputs/'+name:thaw(entry) for name,entry in context['identities'].items()}),execution_policy=policy(config))
    from .upscale_checks import atomic_report
    atomic_report(run,path,data)
    return hash_file(path)
