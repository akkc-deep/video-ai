"""Finite GET-only reconciliation; an unknown intent never authorizes a POST."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from urllib.parse import quote
import math
import re

from ..adapters.common import HttpClient, JSON_LIMIT, positive_timeout
from ..config import load_config, read_json
from ..planning.recovery import signature, validate_changes
from .logging import RunLogger
from .manifest import FileIdentity, ManifestStore, hash_file, thaw, validate_run_dir
from .paths import PathPolicy, _validate_spelling
from .workflows import safe_comfy_path


@dataclass(frozen=True)
class Reconciliation:
    stage: str
    unit_id: str
    attempt_id: str | None
    prompt_id: str | None
    state: str
    evidence_identities: tuple[FileIdentity, ...]
    output_identities: tuple[FileIdentity, ...]
    reason: str

    def __post_init__(self):
        if self.state not in ('completed', 'still_running', 'failed', 'unresolved'):
            raise ValueError('unknown reconciliation state')
        object.__setattr__(self, 'evidence_identities', tuple(self.evidence_identities))
        object.__setattr__(self, 'output_identities', tuple(self.output_identities))


@dataclass(frozen=True)
class ReconciliationContext:
    """Inject a read-only client and a full stage-owned checkpoint consumer.

    revalidate(stage, unit_id, submission, history_entry, actual_graph) must
    reconstruct every parameter and fully decode media from original evidence,
    then return the exact mapped output FileIdentities. It must not update the
    old manifest or submission. Absence of this consumer fails closed.
    """
    run_dir: Path
    snapshot: object
    http: object
    revalidate: object = None


@dataclass(frozen=True)
class NativeValidation:
    output_identities: tuple
    evidence_identities: tuple
    record: object


class InvalidSavedMedia(ValueError):
    """Exact inputs and graph replayed; the original mapped media is invalid."""
    def __init__(self, reason, evidence_identities):
        super().__init__(reason)
        self.evidence_identities=tuple(evidence_identities)


def _checked_saved_media(consume, *, config, run, output, inputs, leaves, logger):
    """Separate proven media defects from changed inputs and unavailable tools."""
    import json
    guarded=dict(inputs)
    for name in ('ffmpeg','ffprobe'):guarded['tool/'+name]=hash_file(config.tools[name])
    guarded['original_output']=hash_file(output)
    for path in leaves:guarded[str(path)]=hash_file(Path(path))
    from .timeline_checks import _again
    _again(guarded)
    events=logger.path('events.jsonl');offset=events.stat().st_size if events.exists() else 0
    try:return consume()
    except (ValueError,RuntimeError) as exc:
        # An operation timeout or a tool failure alone does not establish an
        # invalid model output. Only completed decoder diagnostics do so.
        commands=[]
        if events.exists():
            with events.open('rb') as file:file.seek(offset);raw=file.read()
            for line in raw.splitlines():
                event=json.loads(line)
                if event.get('event')=='command_finished':commands.append(event['details'])
        if not commands:raise
        evidence=dict(guarded)
        for command in commands:
            if command.get('timed_out') is not False or command.get('interrupted') is not False:
                raise
            if str(output) not in command['args'] or command['args'][0] not in (str(config.tools['ffprobe']),str(config.tools['ffmpeg'])):
                raise
            for key in ('stdout_path','stderr_path'):
                identity=hash_file(Path(command[key]));evidence[identity.path]=identity
        if isinstance(exc,RuntimeError):
            failed=[c for c in commands if type(c.get('returncode')) is int and c['returncode']!=0]
            markers=('invalid data found','moov atom not found','error while decoding','invalid png signature',
                     'invalid chunk','truncated','decode error','invalid nal','corrupt','error submitting packet')
            if not failed or not any(any(marker in Path(c['stderr_path']).read_text(errors='replace').lower() for marker in markers) for c in failed):
                raise
        elif any(c.get('returncode')!=0 for c in commands):raise
        _again(guarded)
        proof=logger.save_json('pipeline/invalid-media-'+__import__('uuid').uuid4().hex+'.json',
            dict(schema_version=1,output_identity=thaw(guarded['original_output']),reason=str(exc),commands=commands))
        identity=hash_file(proof);evidence[identity.path]=identity
        raise InvalidSavedMedia(str(exc),tuple(evidence.values())) from exc


def _original_post(config, run, stage, unit_id, saved, graph):
    """Bind the actual persisted request, including lost-response intents."""
    matched=[]
    for path in (run/'logs/http').glob('*.request.json'):
        request=read_json(path)
        body=request.get('json_body')
        if (request.get('method')=='POST' and request.get('url')==config.services['comfyui']+'/prompt'
                and request.get('stage')==stage and request.get('unit_id')==unit_id
                and isinstance(body,dict) and body.get('client_id')==saved['client_id']):
            if set(body)!={'prompt','client_id'} or signature(body['prompt'])!=signature(graph):
                raise ValueError('original HTTP graph/client association differs')
            budget=request.get('timeout')
            if type(budget) not in (int,float) or positive_timeout(budget)>config.timeouts['comfy_request']:
                raise ValueError('original POST operation budget differs')
            matched.append(path)
    if len(matched)!=1:
        raise ValueError('exactly one original model POST request required')
    path=matched[0];stem=path.name[:-len('.request.json')]
    leaves=[path]
    for suffix in ('.response.json','.body'):
        companion=path.parent/(stem+suffix)
        if companion.exists():leaves.append(companion)
    return leaves


def _flatten_identities(value, destination):
    value=thaw(value)
    if isinstance(value,dict):
        if {'path','bytes','sha256'}<=set(value):
            path=Path(value['path']);current=hash_file(path)
            if (current.bytes,current.sha256)!=(value['bytes'],value['sha256']):
                raise ValueError('native reconciliation input content changed')
            if 'mtime_ns' in value and current.mtime_ns!=value['mtime_ns']:
                raise ValueError('native reconciliation input metadata changed')
            destination[current.path]=current
        else:
            for child in value.values():_flatten_identities(child,destination)
    elif isinstance(value,list):
        for child in value:_flatten_identities(child,destination)


def _native_saved_validation(config, run, stage, unit_id, saved, entry, actual_graph):
    """Replay native input plans and fully decode an output without a checkpoint.

    This records fresh inspections only. It never changes saved submission,
    creates a native parent stage checkpoint, starts services or contacts a
    model. Exact origin records can be carried into a new child separately.
    """
    _require_saved_history(entry,saved,actual_graph)
    from .paths import RuntimePaths
    from .timeline_checks import _again, _local
    from ..media.images import validate_start_png
    from ..media.video import inspect_video
    snapshot=ManifestStore.open(run).snapshot()
    paths=RuntimePaths.from_config(config);logger=RunLogger(run)
    leaves=_original_post(config,run,stage,unit_id,saved,actual_graph)
    inputs={};record=None
    if stage=='start_images':
        from . import start_image_checks as owner
        from ..planning.start_images import image_parameters
        board,inputs=owner._input_files(config,run)
        shot=next(s for s in board['shots'] if s['shot_id']==unit_id)
        directions,more=owner._directions(run,board);inputs.update(more)
        revision=owner._revision(config,run)
        model,basis=owner._model(config,revision=revision) if revision is not None else owner._model(config)
        inputs['model']=model
        if revision is not None:inputs.update(revision['model_loader_identities'])
        _flatten_identities(basis,inputs)
        template=owner._template(config,revision=revision) if revision is not None else owner._template(config)
        refs=template.mapping['inputs']
        width,height=owner.validate_dimensions(*(actual_graph[refs[name]['node_id']]['inputs'][refs[name]['input']]
            for name in ('width','height')))
        parameters=image_parameters(shot,board['global_visual'],width,height,direction=directions.get(unit_id))
        expected=template.instantiate(dict(positive_prompt=parameters['positive'],negative_prompt=parameters['negative'],
            seed=parameters['seed'],width=width,height=height),output_prefix=f'{run.name}/start_images/{unit_id}')
        record=dict(shot_id=unit_id,primary_unit_id=shot['primary_unit_id'],origin='sdxl',
            width=width,height=height,format='png',pixel_format='rgb24',adaptation='none',parameters=parameters,
            model_identity=thaw(model),workflow_identity=thaw(hash_file(config.workflows['sdxl'])),
            mapping_identity=thaw(hash_file(config.workflows['sdxl'].with_suffix('.mapping.json'))),
            reference_entity_ids=list(shot['entity_ids']))
        namespace=run/'comfy/output'/run.name/'start_images';prefix=unit_id+'_';suffix='.png'
    elif stage=='source_clips':
        from . import _source_clip_inputs as owner
        context=owner.inputs(config,run);inputs=dict(context['identities']);template=context['template']
        match=re.fullmatch(r'(shot_[0-9]{4,}):attempt_([0-9]{4})',unit_id)
        if match is None:raise ValueError('source saved request requires exact attempt unit ID')
        shot_id,ordinal=match[1],int(match[2])
        if ordinal not in (1,2):raise ValueError('no third source attempt')
        plan=next(p for p in context['plans'] if p.shot_id==shot_id)
        parameters=thaw(plan.parameters);requested=parameters['length'];attempts=[]
        if ordinal==2:
            from ..planning.source_clips import supplement_frames
            prior_id=shot_id+':attempt_0001';prior=snapshot['units']['shot_attempt'][prior_id]['submission']
            if prior is None or prior.get('state')!='completed' or not prior.get('response_path'):
                raise ValueError('second source request requires original completed known-short evidence')
            prior_graph=read_json(Path(prior['request_path']))
            prior_registered=snapshot['workflows'].get(prior['attempt_id'])
            if prior_registered is None or not _same_identity(prior_registered,hash_file(Path(prior['request_path']))):
                raise ValueError('known-short first registered graph identity changed')
            wanted=owner.graph(template,run,plan,requested,'attempt_0001')
            if signature(prior_graph)!=signature(wanted):raise ValueError('first original source graph differs')
            prior_entry=read_json(Path(prior['response_path']))[prior['prompt_id']]
            metadata=_metadata(prior_entry.get('prompt'))
            if metadata is None or metadata[0]!=prior['prompt_id'] or not _matches(metadata,prior,prior_graph) or prior_entry['prompt'][0]!=prior['number']:
                raise ValueError('known-short first history prompt/client/full graph differs')
            if prior_entry.get('status',{}).get('completed') is not True or prior_entry.get('status',{}).get('status_str')!='success':
                raise ValueError('known-short first request lacks successful original history')
            prior_outputs=prior_entry['outputs'][template.mapping['output']['node_id']][template.mapping['output']['collection']]
            if len(prior_outputs)!=1:raise ValueError('known-short first request exact output required')
            prior_path=_local(run,_mapped_path(run,prior_outputs[0]));width,height=parameters['width'],parameters['height']
            if (prior_path.parent!=run/'comfy/output'/run.name/'source_clips'/shot_id or not prior_path.name.startswith('attempt_0001_')
                    or prior_path.suffix.lower()!='.mp4' or prior_path.stat().st_mtime_ns<int(datetime.fromisoformat(prior['submitted_at']).timestamp()*1e9)):
                raise ValueError('known-short first output namespace/prefix/submission time differs')
            prior_unit=snapshot['units']['shot_attempt'][prior_id];short_error=prior_unit.get('error')
            if prior_unit['status']!='failed' or not isinstance(short_error,Mapping) or short_error.get('kind')!='known_short':
                raise ValueError('second attempt requires durable original known-short receipt')
            artifacts=prior_unit['artifacts']
            if len(artifacts)!=1 or Path(artifacts[0]['path'])!=prior_path:
                raise ValueError('known-short first registered output artifact differs')
            artifact=hash_file(prior_path)
            if (artifact.bytes,artifact.sha256)!=(artifacts[0]['bytes'],artifacts[0]['sha256']):
                raise ValueError('known-short first output artifact changed')
            original_leaves=_original_post(config,run,stage,prior_id,prior,prior_graph)
            post=next(path for path in original_leaves if path.name.endswith('.request.json'));stem=post.name[:-len('.request.json')]
            acceptance=read_json(post.parent/(stem+'.body'));post_meta=read_json(post.parent/(stem+'.response.json'))
            if (post_meta.get('status')!=200 or post_meta.get('truncated') is not False or post_meta.get('error') is not None
                    or post_meta.get('method')!='POST' or post_meta.get('url')!=config.services['comfyui']+'/prompt'
                    or post_meta.get('stage')!=stage or post_meta.get('unit_id')!=prior_id
                    or type(post_meta.get('bytes')) is not int or post_meta['bytes']!=post.parent.joinpath(stem+'.body').stat().st_size
                    or acceptance.get('prompt_id')!=prior['prompt_id'] or acceptance.get('number')!=prior['number'] or not isinstance(acceptance.get('node_errors'),dict)):
                raise ValueError('known-short first actual HTTP acceptance differs')
            prior_info,more=inspect_video(prior_path,width=width,height=height,config=config,paths=paths,logger=logger,unit_id=prior_id,timeout=300)
            from ._source_clip_evidence import command
            from ..media.video import validate_video_probe
            old_paths=[_local(run,Path(path)) for path in short_error['evidence_paths']]
            observations=[path for path in old_paths if path.parent==run/'logs/source-clips' and path.name.startswith('video-'+prior_id.replace(':','_')+'-') and path.suffix=='.json']
            if len(observations)!=1:raise ValueError('known-short first independent inspection receipt missing')
            observation=read_json(observations[0]);old_info=observation['info']
            if not _same_identity(old_info['identity'],artifact) or {key:value for key,value in old_info.items() if key!='identity'}!={key:value for key,value in prior_info.items() if key!='identity'}:
                raise ValueError('known-short first receipt differs from fresh decoded output')
            if validate_video_probe(observation['probe'],observation['frames'],width=width,height=height)!={key:value for key,value in old_info.items() if key!='identity'}:
                raise ValueError('known-short first receipt differs from actual probe/PTS')
            covered={path.relative_to(run).as_posix() for path in old_paths};commands=observation['commands']
            expected_commands=((config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',prior_path),
                (config.tools['ffprobe'],'-v','error','-show_frames','-of','json',prior_path),(config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',prior_path,'-f','null','-'))
            if len(commands)!=3:raise ValueError('known-short first three original media commands required')
            for index,(record,args) in enumerate(zip(commands,expected_commands)):
                stdout=command(record,args,run,covered)
                if index<2 and read_json(stdout)!=observation['probe' if index==0 else 'frames']:raise ValueError('known-short first original raw media evidence differs')
                if index==2 and (stdout.read_bytes() or Path(record['stderr_path']).read_bytes()):raise ValueError('known-short first original full decode failed')
            if short_error.get('message')!=f"decoded {prior_info['frames']} < required {plan.budget['required_native_frames']}":
                raise ValueError('known-short first saved decoded budget receipt differs')
            leaves.extend(old_paths)
            leaves.extend([Path(prior['request_path']),Path(prior['response_path']),prior_path,*more])
            leaves.extend(original_leaves)
            requested=supplement_frames(requested_frames=requested,required_native_frames=plan.budget['required_native_frames'],actual_frames=prior_info['frames'])
            attempts.append(dict(attempt_id='attempt_0001',ordinal=1,unit_id=prior_id,requested_frames=parameters['length'],status='short',
                submission=dict(attempt_id=prior['attempt_id'],prompt_id=prior['prompt_id'],intent_identity=thaw(hash_file(Path(prior['request_path'])))),
                output_identity=prior_info['identity'],actual_frames=prior_info['frames'],evidence_identities=[str(p) for p in leaves]))
        attempt=f'attempt_{ordinal:04d}'
        expected=owner.graph(template,run,plan,requested,attempt);parameters['length']=requested
        width,height=parameters['width'],parameters['height']
        copy_path=run/'comfy/input'/run.name/'source_clips'/shot_id/'start.png';copied=hash_file(_local(run,copy_path))
        original=plan.start_image_identity
        if (copied.bytes,copied.sha256)!=(original['bytes'],original['sha256']):raise ValueError('actual Wan input copy differs from planned start image')
        inputs['saved_input_copy']=copied
        record=dict(shot_id=shot_id,primary_unit_id=plan.primary_unit_id,budget=thaw(plan.budget),
            start_image_identity=thaw(original),input_copy_identity=thaw(copied),selected_attempt_id=attempt,
            attempts=attempts,width=width,height=height,native_fps=16,source_frames=plan.budget['required_native_frames'],parameters=parameters)
        namespace=run/'comfy/output'/run.name/'source_clips'/shot_id;prefix=attempt+'_';suffix='.mp4'
    elif stage=='upscale':
        from . import _upscale_inputs as owner
        context=owner.inputs(config,run);inputs=dict(context['identities']);template=context['template']
        match=re.fullmatch(r'(shot_[0-9]{4,}):frame_([0-9]{6,})',unit_id)
        if match is None:raise ValueError('upscale saved request requires exact frame ID')
        shot_id,index=match[1],int(match[2]);plan=next(p for p in context['plans'] if p.shot_id==shot_id)
        if not 1<=index<=plan.source_frames:raise ValueError('saved upscale frame outside planned source mapping')
        expected=owner.graph(template,run,plan,index);width,height=1920,1080
        copy_path=run/'comfy/input'/run.name/'upscale'/shot_id/f'frame_{index:06d}.png'
        original_path=run/'shots'/shot_id/'frames'/f'frame_{index:06d}.png'
        original=hash_file(_local(run,original_path));copied=hash_file(_local(run,copy_path))
        if (copied.bytes,copied.sha256)!=(original.bytes,original.sha256):raise ValueError('saved upscale input copy differs')
        # Independently decode the exact source frame to raw RGB, then compare
        # with the original extracted input PNG; no new PNG/media is produced.
        from .processes import run_logged
        from .environment import build_child_env
        source=next(c for c in context['source']['clips'] if c['shot_id']==shot_id)
        args=(config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',Path(plan.source_identity['path']),
            '-vf',f'select=eq(n\\,{index-1}),format=rgb24','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','-')
        source_rgb=run_logged(tuple(str(v) for v in args),cwd=run,env=build_child_env(paths),timeout=300,logger=logger,stage='upscale',unit_id=unit_id)
        args=(config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',original_path,'-f','rawvideo','-pix_fmt','rgb24','-')
        input_rgb=run_logged(tuple(str(v) for v in args),cwd=run,env=build_child_env(paths),timeout=300,logger=logger,stage='upscale',unit_id=unit_id)
        for command in (source_rgb,input_rgb):
            if command.returncode!=0 or command.timed_out or command.stderr_path.read_bytes():raise ValueError('saved source-frame full decode failed')
            leaves.extend((command.stdout_path,command.stderr_path))
        raw_source=hash_file(source_rgb.stdout_path);raw_input=hash_file(input_rgb.stdout_path)
        if (raw_source.bytes,raw_source.sha256)!=(raw_input.bytes,raw_input.sha256) or raw_input.bytes!=source['width']*source['height']*3:
            raise ValueError('actual upscale input pixels differ from exact planned source frame')
        inputs.update(original_input=original,saved_input_copy=copied)
        record=dict(schema_version=1,run_id=run.name,shot_id=shot_id,frame_index=index,source_frame_index=index-1,
            source_identity=thaw(plan.source_identity),input_identity=thaw(original),input_copy_identity=thaw(copied),
            workflow_identity=thaw(inputs['workflow']),mapping_identity=thaw(inputs['mapping']),model_identity=thaw(inputs['model']),parameters=thaw(plan.parameters))
        namespace=run/'comfy/output'/run.name/'upscale'/shot_id;prefix=f'frame_{index:06d}_';suffix='.png'
    else:
        raise ValueError('no native saved-submission consumer for stage')
    if signature(actual_graph)!=signature(expected):raise ValueError('saved full actual graph differs from independently reconstructed parameters')
    mapping=template.mapping['output'];mapped=entry.get('outputs',{}).get(mapping['node_id'],{}).get(mapping['collection'])
    if not isinstance(mapped,list) or len(mapped)!=1:raise ValueError('exact native template output mapping required')
    output=_local(run,_mapped_path(run,mapped[0]))
    if output.parent!=namespace or not output.name.startswith(prefix) or output.suffix.lower()!=suffix:
        raise ValueError('saved output namespace differs from exact stage/unit attempt')
    if output.stat().st_mtime_ns<int(datetime.fromisoformat(saved['submitted_at']).timestamp()*1e9):
        raise ValueError('saved output predates original request')
    if stage=='source_clips':
        info,more=_checked_saved_media(lambda:inspect_video(output,width=width,height=height,config=config,paths=paths,logger=logger,unit_id=unit_id,timeout=300),
            config=config,run=run,output=output,inputs=inputs,leaves=leaves,logger=logger)
        if info['frames']!=record['parameters']['length'] or info['frames']<record['source_frames']:
            _again(inputs)
            proof=logger.save_json('pipeline/invalid-media-'+__import__('uuid').uuid4().hex+'.json',dict(info=info,
                requested_frames=record['parameters']['length'],required_frames=record['source_frames']))
            identities=tuple(hash_file(Path(path)) for path in (*leaves,output,*more,proof))
            raise InvalidSavedMedia('saved generated media does not satisfy exact requested/required frame budget',identities)
        ordinal=int(unit_id.rsplit('_',1)[1]);attempt=f'attempt_{ordinal:04d}'
        record['attempts'].append(dict(attempt_id=attempt,ordinal=ordinal,unit_id=unit_id,requested_frames=record['parameters']['length'],status='selected',
            submission=dict(attempt_id=saved['attempt_id'],prompt_id=entry['prompt'][1],intent_identity=thaw(hash_file(Path(saved['request_path'])))),
            output_identity=info['identity'],actual_frames=info['frames'],evidence_identities=[]))
        record.update(generated_identity=info['identity'],generated_frames=info['frames'])
    else:
        info,more=_checked_saved_media(lambda:validate_start_png(output,width=width,height=height,config=config,paths=paths,logger=logger,unit_id=unit_id,stage=stage,timeout=300),
            config=config,run=run,output=output,inputs=inputs,leaves=leaves,logger=logger)
        record.update(submission=dict(attempt_id=saved['attempt_id'],prompt_id=entry['prompt'][1],intent_identity=thaw(hash_file(Path(saved['request_path'])))))
        if stage=='start_images':record.update(image_identity=info['identity'],source_identity=info['identity'])
        else:record.update(output_identity=info['identity'],upscaled_frame_identity=info['identity'])
    leaves.extend([output,*more]);_flatten_identities(record,inputs)
    for name in ('ffmpeg','ffprobe'):inputs['execution_tool/'+name]=hash_file(config.tools[name])
    _again(inputs)
    if ManifestStore.open(run).snapshot()!=snapshot:raise ValueError('parent manifest changed during native saved output consumption')
    identities=dict(inputs)
    for path in leaves:identities[str(path)]=hash_file(Path(path))
    record['evidence_identities']=[identity.path for identity in identities.values()]
    return NativeValidation((hash_file(output),),tuple(identities.values()),record)


def _same_identity(expected, current):
    expected, current = thaw(expected), thaw(current)
    return all(expected.get(k) == current.get(k) for k in ('path', 'bytes', 'sha256', 'mtime_ns'))


def load_changes(path, *, run_dir, config, snapshot_identity, shot_ids):
    """Freshly read the exact changes format and all its bound identities.

    The snapshot must be an exclusive existing file under this run's pipeline
    logs. The caller remains responsible for matching its protected manifest
    content and for semantic author review of the new prompts.
    """
    run = validate_run_dir(run_dir)
    path = Path(_validate_spelling(path))
    if not path.is_absolute():
        raise ValueError('changes path must be absolute')
    identity = hash_file(path)
    value = read_json(path)
    validated = validate_changes(value, run_id=run.name, shot_ids=shot_ids,
        snapshot_identity=snapshot_identity, now=datetime.now().astimezone())
    snapshot_path = PathPolicy().validate_write(validated['base_manifest_snapshot_identity']['path'], 'run')
    if not snapshot_path.is_relative_to(run/'logs/pipeline'):
        raise ValueError('changes snapshot must belong to this run pipeline logs')
    current_config = hash_file(config.config_file)
    if not _same_identity(validated['config_identity'], current_config):
        raise ValueError('changes config identity mismatch')
    for key in ('base_manifest_snapshot_identity', 'script_identity', 'unit_review_identity', 'config_identity'):
        record = validated[key]
        if record is not None and not _same_identity(record, hash_file(Path(record['path']))):
            raise ValueError(f'changes {key} identity changed')
    if not _same_identity(identity, hash_file(path)):
        raise ValueError('changes file drifted during consumption')
    return validated, identity


def validate_failed_submission(run, stage, unit_id, submission):
    """Admit only explicit final server failure or a bound HTTP rejection.

    Returns freshly verified evidence identities. Unknown/active/ambiguous
    responses are refusals even when retry_failed was requested by the caller.
    """
    directory=validate_run_dir(run);snapshot=ManifestStore.open(directory).snapshot()
    config=load_config(Path(snapshot['config_snapshot']['path']))
    original_units=[unit for kind in _KINDS.get(stage,()) for uid,unit in snapshot['units'].get(kind,{}).items() if uid==unit_id]
    if len(original_units)!=1 or original_units[0].get('submission')!=thaw(submission):
        raise ValueError('failed submission differs from immutable original native unit')
    for artifact in original_units[0]['artifacts']:
        identity=hash_file(Path(artifact['path']))
        if (identity.bytes,identity.sha256)!=(artifact['bytes'],artifact['sha256']):
            raise ValueError('original failed result registered artifact changed')
    if submission.get('state')=='rejected' and not submission.get('prompt_id'):
        current=hash_file(Path(submission['request_path']))
        registered=snapshot['workflows'].get(submission['attempt_id'])
        if registered is None or not _same_identity(registered,current):raise ValueError('saved request graph identity changed')
        graph=read_json(Path(submission['request_path']))
        original=_original_post(config,directory,stage,unit_id,submission,graph)
        # HttpClient raises on an HTTP rejection before submit_once receives
        # its response object. Bind its persisted companions to the unique
        # original POST instead of requiring the optional response_path.
        request_path=next(path for path in original if path.name.endswith('.request.json'))
        stem=request_path.name[:-len('.request.json')]
        body=request_path.parent/(stem+'.body')
        if submission.get('response_path') and Path(submission['response_path'])!=body:
            raise ValueError('saved rejection response differs from original POST companion')
        meta=read_json(request_path.parent/(stem+'.response.json'))
        request=read_json(request_path);response=read_json(body)
        if (request.get('method')!='POST' or request.get('url')!=config.services['comfyui']+'/prompt'
                or request.get('json_body')!={'prompt':graph,'client_id':submission['client_id']}
                or meta.get('method')!='POST' or meta.get('url')!=request.get('url')
                or type(meta.get('status')) is not int or not 400<=meta['status']<500
                or meta.get('truncated') is not False or meta.get('error') is not None
                or response.get('prompt_id') is not None or not isinstance(response.get('error'),dict)
                or not response['error']):
            raise ValueError('saved rejection does not prove an unaccepted model request')
        paths=set(original)|{body,body.with_suffix('.request.json'),body.with_suffix('.response.json'),Path(submission['request_path'])}
        return tuple(hash_file(path) for path in sorted(paths))
    result=reconcile_submission(directory,stage,unit_id)
    if result.state!='failed':raise ValueError('saved failed request is still running or unresolved: '+result.reason)
    return result.evidence_identities


_KINDS = {'start_images': ('image',), 'source_clips': ('shot_attempt', 'shot'),
          'upscale': ('frame',), 'speech': ('speech',)}


def _completed_stage_validator(config, run):
    def validate(stage, unit_id, saved, entry, graph):
        if ManifestStore.open(run).snapshot()['stages'][stage]['status'] != 'completed':
            return _native_saved_validation(config,run,stage,unit_id,saved,entry,graph)
        # A fully committed stage's original consumer is sufficient and still
        # replays the entire actual graph/HTTP/media/parameters. Partial units
        # require the explicit stage-owned callback supplied by import logic.
        from .start_image_checks import load_committed_start_images
        from .source_clip_checks import load_committed_source_clips
        from .upscale_checks import load_committed_upscaled_clips
        registry = {'start_images': load_committed_start_images,
                    'source_clips': load_committed_source_clips,
                    'upscale': load_committed_upscaled_clips}
        report = registry[stage](run)
        outputs = _mapped_outputs(entry, graph)
        wanted = {_mapped_path(run, output) for output in outputs}
        found = {}

        def visit(value):
            if isinstance(value, Mapping):
                if {'path', 'bytes', 'sha256', 'mtime_ns', 'verified_at'} == set(value):
                    p = Path(value['path'])
                    if p in wanted:
                        current = hash_file(p)
                        if not _same_identity(value, current):
                            raise ValueError('mapped output identity drift')
                        found[p] = current
                else:
                    for child in value.values():
                        visit(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    visit(child)
        visit(report)
        if set(found) != wanted:
            raise ValueError('successful output is not a fully consumed committed checkpoint')
        return tuple(found[_mapped_path(run, output)] for output in outputs)
    return validate


def _context(run):
    if isinstance(run, ReconciliationContext):
        return run
    directory = validate_run_dir(run)
    store = ManifestStore.open(directory)
    snapshot = store.snapshot()
    config = load_config(Path(snapshot['config_snapshot']['path']))
    logger = RunLogger(directory)
    http = HttpClient(config.services['comfyui'], config.timeouts['comfy_request'], logger)
    return ReconciliationContext(directory, snapshot, http, _completed_stage_validator(config, directory))


def _metadata(row):
    # Real Comfy queue/history prompt: [number, id, actual_graph,
    # extra_data containing client_id, ordered output nodes].
    if not isinstance(row, (list, tuple)) or len(row) < 4:
        return None
    if (type(row[0]) not in (int,float) or not math.isfinite(row[0])
            or not isinstance(row[1], str) or not row[1] or not isinstance(row[2], Mapping) or not isinstance(row[3], Mapping)):
        return None
    return row[1], row[2], row[3].get('client_id'),row[0]


def _matches(meta, saved, graph):
    if meta is None:
        return False
    return (meta[2] == saved.get('client_id') and signature(meta[1]) == signature(graph)
        and (saved.get('prompt_id') is None or meta[0]==saved['prompt_id'])
        and (saved.get('number') is None or meta[3]==saved['number']))


def _history_matches(entry,saved,graph,*,prompt_id=None):
    if not isinstance(entry,Mapping):return False
    meta=_metadata(entry.get('prompt'));status=entry.get('status',{})
    return (_matches(meta,saved,graph) and (prompt_id is None or meta[0]==prompt_id)
        and isinstance(status,Mapping) and status.get('completed') is True and status.get('status_str')=='success')


def _require_saved_history(entry,saved,graph,*,prompt_id=None):
    if not _history_matches(entry,saved,graph,prompt_id=prompt_id):
        raise ValueError('saved history prompt/client/graph/number differs')


def _mapped_outputs(entry, graph):
    outputs = entry.get('outputs')
    if not isinstance(outputs, Mapping) or not outputs:
        raise ValueError('successful history has no output mapping')
    matches = []
    for node, record in outputs.items():
        if node not in graph or not isinstance(record, Mapping):
            raise ValueError('history output is not an actual graph node')
        for collection, values in record.items():
            if collection not in ('images', 'gifs', 'videos'):
                continue
            if not isinstance(values, list) or not values:
                raise ValueError('mapped output collection must be nonempty')
            matches.extend(values)
    # The existing image/attempt/frame APIs all bind exactly one model output.
    if len(matches) != 1:
        raise ValueError('exactly one stage-mapped model output required')
    return tuple(matches)


def _mapped_path(run, output):
    if not isinstance(output, Mapping) or not {'filename', 'subfolder', 'type'} <= set(output):
        raise ValueError('invalid mapped output metadata')
    if output['type'] != 'output':
        raise ValueError('mapped model output must have output type')
    filename = safe_comfy_path(output['filename'])
    folder = safe_comfy_path(output['subfolder'], allow_empty=True)
    if Path(filename).name != filename:
        raise ValueError('mapped output filename must be basename')
    root = Path(run)/'comfy/output'
    path = root/folder/filename
    if not path.resolve().is_relative_to(root):
        raise ValueError('mapped output path escapes original run')
    return path


def reconcile_submission(run, stage, unit_id):
    """Make exactly one bounded queue/history GET pair, preserving old intent.

    No lifecycle commands, polling loop, POST, manifest updates or inference
    from an empty queue occur here. Success is admitted only by full stage-owned
    parameter/media validation and fresh original output identities.
    """
    context = _context(run)
    saved = None
    evidence = []
    errors = []
    graph_identity = None
    for kind in _KINDS.get(stage, ()):
        row = context.snapshot.get('units', {}).get(kind, {}).get(unit_id)
        if row and row.get('submission'):
            if saved is not None:
                raise ValueError('conflicting submission records for one unit')
            saved = row['submission']
    attempt = saved.get('attempt_id') if saved else None
    prompt = saved.get('prompt_id') if saved else None

    def result(state, reason, *, outputs=(), selected=None):
        identities, seen = [], set()
        for path in evidence:
            path = Path(path)
            if path in seen:
                continue
            seen.add(path)
            try:
                identities.append(hash_file(path))
            except (OSError, ValueError) as exc:
                errors.append(f'evidence identity unavailable: {exc}')
                if state == 'completed':
                    state, outputs = 'unresolved', ()
        suffix = '; '+ '; '.join(errors) if errors else ''
        return Reconciliation(stage, unit_id, attempt, selected or prompt, state,
            tuple(identities), tuple(outputs), reason+suffix)

    if stage == 'speech':
        return result('unresolved', 'TTS has no query key; lost response remains unknown')
    if stage not in _KINDS or saved is None:
        return result('unresolved', 'no uniquely bound saved Comfy submission')
    try:
        request = Path(_validate_spelling(saved['request_path']))
        if not request.is_absolute() or not request.resolve().is_relative_to(Path(context.run_dir)):
            raise ValueError('saved request must belong to original run')
        graph_identity = context.snapshot.get('workflows', {}).get(attempt)
        current_graph_identity = hash_file(request)
        if graph_identity is None or not _same_identity(graph_identity, current_graph_identity):
            raise ValueError('saved request graph identity changed')
        evidence.append(request)
        graph = read_json(request)
        if not isinstance(saved.get('client_id'), str) or not saved['client_id']:
            raise ValueError('saved client_id missing')
        if prompt is not None and (not isinstance(prompt, str) or not prompt):
            raise ValueError('saved prompt ID invalid')
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return result('unresolved', str(exc))

    responses = {}
    routes = ('/queue', '/history/'+quote(prompt, safe='') if prompt else '/history')
    for route in routes:
        try:
            response = context.http.request('GET', route, max_bytes=JSON_LIMIT,
                timeout=min(2.0, positive_timeout(context.http.timeout)), stage=stage, unit_id=unit_id)
            path = Path(response.evidence_path)
            evidence.append(path)
            if path.suffix == '.body':
                for suffix in ('.request.json', '.response.json'):
                    companion = path.with_suffix(suffix)
                    if companion.is_file():
                        evidence.append(companion)
            responses[route] = context.http.parse_json(response, stage=stage, unit_id=unit_id)
        except Exception as exc:
            evidence.extend(getattr(exc, 'evidence_paths', ()))
            errors.append(f'{route}: {type(exc).__name__}: {exc}')
    queue = responses.get('/queue', {})
    history = responses.get(routes[1], {})
    candidates = {}
    try:
        if not isinstance(queue, Mapping) or not isinstance(history, Mapping):
            raise ValueError('queue/history response must be object')
        for key in ('queue_running', 'queue_pending'):
            rows = queue.get(key, [])
            if not isinstance(rows, list):
                raise ValueError('queue rows must be arrays')
            for row in rows:
                meta = _metadata(row)
                if _matches(meta, saved, graph) and (prompt is None or meta[0] == prompt):
                    candidates.setdefault(meta[0], {})['queued'] = True
        for pid, entry in history.items():
            if prompt is not None and pid != prompt:
                continue
            if not isinstance(entry, Mapping):
                raise ValueError('history entry must be object')
            meta = _metadata(entry.get('prompt'))
            if meta is not None and meta[0] == pid and _matches(meta, saved, graph):
                candidates.setdefault(pid, {})['entry'] = entry
            elif prompt is not None and pid == prompt:
                raise ValueError('saved prompt history metadata or actual graph differs')
        if len(candidates) != 1:
            return result('unresolved', 'no unique client_id/actual-graph queue/history match')
        selected, candidate = next(iter(candidates.items()))
        entry = candidate.get('entry')
        if entry is None:
            return result('still_running', 'matching request is still queued/running', selected=selected)
        status = entry.get('status', {})
        if not isinstance(status, Mapping):
            raise ValueError('history status must be object')
        messages = status.get('messages', [])
        if not isinstance(messages, list):
            raise ValueError('history status messages must be array')
        failure = status.get('status_str') == 'error' or any(
            isinstance(m, list) and m and m[0] == 'execution_error' for m in messages)
        if failure:
            if '/queue' not in responses:
                return result('unresolved', 'failed history cannot establish inactive request while queue is unavailable', selected=selected)
            if candidate.get('queued'):
                return result('unresolved', 'conflicting error history and active queue', selected=selected)
            return result('failed', 'same request has explicit execution failure', selected=selected)
        if status.get('completed') is True and status.get('status_str') == 'success':
            if candidate.get('queued'):
                return result('unresolved', 'conflicting success history and active queue', selected=selected)
            outputs = _mapped_outputs(entry, graph)
            paths = tuple(_mapped_path(context.run_dir, output) for output in outputs)
            if context.revalidate is None:
                raise ValueError('complete stage-owned output/media/parameter revalidation unavailable')
            try:
                validation = context.revalidate(stage, unit_id, saved, entry, graph)
            except InvalidSavedMedia as exc:
                unit=next((context.snapshot['units'][kind][unit_id] for kind in _KINDS[stage]
                    if unit_id in context.snapshot['units'].get(kind,{})),None)
                if '/queue' not in responses or unit is None or unit.get('status')!='failed' or saved.get('state')!='completed':
                    raise ValueError('invalid media does not prove an inactive original completed request') from exc
                error=unit.get('error')
                if not isinstance(error,Mapping) or not error.get('evidence_paths'):
                    raise ValueError('invalid media lacks original local failure evidence') from exc
                for path in error['evidence_paths']:
                    path=Path(path)
                    if not path.resolve().is_relative_to(Path(context.run_dir)/'logs') or not path.is_file():
                        raise ValueError('original invalid-media failure evidence unavailable')
                    evidence.append(path)
                if not _same_identity(graph_identity,hash_file(request)):
                    raise ValueError('saved graph changed during invalid media replay')
                for identity in exc.evidence_identities:
                    if not _same_identity(identity,hash_file(Path(identity.path))):raise ValueError('invalid media proof drifted')
                    evidence.append(identity.path)
                return result('failed','same completed inactive request has proven invalid media: '+str(exc),selected=selected)
            if isinstance(validation, NativeValidation):
                evidence.extend(identity.path for identity in validation.evidence_identities)
                admitted=tuple(validation.output_identities)
            else:
                admitted=tuple(validation)
            if len(admitted) != len(paths):
                raise ValueError('stage consumer did not validate exact mapped output set')
            for path, identity in zip(paths, admitted):
                if not isinstance(identity, FileIdentity) or Path(identity.path) != path:
                    raise ValueError('stage consumer output is not exact mapped original identity')
                if not _same_identity(identity, hash_file(path)):
                    raise ValueError('mapped output changed during revalidation')
            if not _same_identity(graph_identity, hash_file(request)):
                raise ValueError('saved graph changed during reconciliation')
            return result('completed', 'successful saved submission fully revalidated', outputs=admitted, selected=selected)
        if candidate.get('queued'):
            return result('still_running', 'matching request is still queued/running', selected=selected)
        return result('unresolved', 'history is neither final success nor explicit failure', selected=selected)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return result('unresolved', f'reconciliation cannot admit evidence: {exc}')
