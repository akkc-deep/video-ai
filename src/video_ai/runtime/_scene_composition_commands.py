"""Unique bounded encode/probe commands and exact original-completion recovery."""
import json
from pathlib import Path
from uuid import UUID, uuid4

from ..config import read_json
from ..planning.production_scenes import canonical_digest
from .environment import build_child_env
from .execution_limits import historical_command_timeout
from .manifest import now, thaw
from .production_composition import COMMAND_FIELDS
from .production_composition_records import command as validate_command
from .production_scene_clips import _GuardedLogger
from .production_state import ProductionRefused, object_fields, run_path, timestamp, sync_file
from .scene_clip_records import equal

INTENT_FIELDS='schema_version run_id operation inputs_sha256 args cwd output created_at'.split()
SUCCESS_FIELDS='schema_version run_id intent_sha256 command output evidence created_at'.split()


def encode_args(context,output):
    materialized=context['materialized']; folder=Path(materialized['ass']['path']).parent
    return [str(context['frozen'].config.tools['ffmpeg']),'-nostdin','-n','-v','error','-xerror',
        '-framerate','16','-start_number','1','-i',str(folder/'frames'/'frame_%06d.png'),
        '-i',materialized['narration']['audio']['path'],'-filter_complex',
        '[0:v:0]subtitles=filename=subtitles.ass:fontsdir=fonts[v]','-map','[v]','-map','1:a:0',
        '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',
        '-c:a','aac','-b:a','192k','-ar','48000','-ac','1','-movflags','+faststart',str(output)]


def probe_args(context,encoded):
    return [str(context['frozen'].config.tools['ffprobe']),'-v','error','-count_frames',
            '-show_streams','-show_format','-of','json',encoded['path']]


def _unit(operation,token): return 'scene_composition:'+operation+':'+token


def _identity(context,operation,token,encoded):
    store=context['composition_store']; folder=Path(context['materialized']['ass']['path']).parent
    output=store.path('encodes')/token/'candidate.mp4' if operation=='encode' else store.path('probes')/(token+'.json')
    args=encode_args(context,output) if operation=='encode' else probe_args(context,encoded)
    # Bind the complete original materialization, including its stage-input digest;
    # probe additionally binds the original encoded bytes it actually inspects.
    identity=dict(materialized=context['materialized'])
    if operation=='probe': identity['encoded']=encoded
    return dict(schema_version=2,run_id=store.run_dir.name,operation=operation,
                inputs_sha256=canonical_digest(identity),args=args,cwd=str(folder),output=str(output))


def _completion(context,intent,token):
    store=context['composition_store']; path=run_path(store.run_dir,store.run_dir/'logs/production/events.jsonl')
    matches=[]
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                event=json.loads(line)
                if (event.get('stage')=='scene_composition' and event.get('unit_id')==_unit(intent['operation'],token)
                        and event.get('event')=='command_finished'):
                    matches.append(event['details'])
    if not matches: return None
    if len(matches)!=1: raise ProductionRefused('scene media command has conflicting durable completions')
    value=matches[0]
    if (value.get('args')!=intent['args'] or value.get('cwd')!=intent['cwd']
            or 'timeout' not in value or not historical_command_timeout(value['timeout'])):
        raise ProductionRefused('scene media command completion identity differs')
    if (value.get('interrupted') is not False or value.get('timed_out') is not False
            or type(value.get('returncode')) is not int or value['returncode']!=0): return None
    result={key:value[key] for key in COMMAND_FIELDS}; validate_command(result,store.run_dir)
    return result


def bind_command_completion_proof(context,encode,probe):
    """Freeze original completion proof only after encode and probe may append logs."""
    store=context['composition_store']
    events=run_path(store.run_dir,store.run_dir/'logs/production/events.jsonl')
    if not events.is_file(): raise ProductionRefused('original media command event log missing')
    snapshot=store.artifact(events)
    for operation,(receipt_path,receipt) in (('encode',encode),('probe',probe)):
        receipt_path=run_path(store.run_dir,receipt_path)
        prefix=operation+'-'; suffix='.success.json'
        if not receipt_path.name.startswith(prefix) or not receipt_path.name.endswith(suffix):
            raise ProductionRefused('original completion receipt path differs')
        token=receipt_path.name[len(prefix):-len(suffix)]
        try:
            if str(UUID(token))!=token: raise ValueError()
        except ValueError as exc: raise ProductionRefused('original completion attempt UUID differs') from exc
        intent_path=receipt_path.with_name(prefix+token+'.intent.json')
        intent=read_json(intent_path)
        object_fields(intent,INTENT_FIELDS,'original completion intent')
        equal(read_json(receipt_path),receipt,'stable original command receipt')
        if intent['operation']!=operation: raise ProductionRefused('original completion operation differs')
        equal(canonical_digest(intent),receipt['intent_sha256'],'original completion intent digest')
        command=_completion(context,intent,token)
        if command is None: raise ProductionRefused('original successful media completion missing')
        equal(command,receipt['command'],'original successful command completion')
    # The same bytes must cover both revalidated rows; changes during the scans
    # cannot become the new authority for later acceptance or publishing.
    store.validate_artifact(snapshot)
    previous=store.guard_paths.get(snapshot['path'])
    if previous is not None: equal(previous,snapshot,'previous original completion event log')
    store.bind_artifact(snapshot)
    return snapshot


def _evidence(store,command):
    evidence=[]
    for role in ('stdout_path','stderr_path'):
        path=run_path(store.run_dir,command[role])
        if not path.is_file(): raise ProductionRefused('original media command log missing')
        # Empty raw logs retain their exact command paths; Artifact requires positive bytes.
        if path.stat().st_size: evidence.append(store.artifact(path))
        else: store.guard_empty_paths.add(str(path))
    return evidence


def _receipt(context,intent,command):
    store=context['composition_store']; path=run_path(store.run_dir,intent['output'])
    if intent['operation']=='probe':
        raw=run_path(store.run_dir,command['stdout_path']).read_bytes()
        if path.exists():
            if path.read_bytes()!=raw: raise ProductionRefused('original probe output differs from bound stdout')
        else: store.write_bytes(path,raw)
    if not path.is_file(): raise ProductionRefused('successful command original output missing')
    for key in ('stdout_path','stderr_path'): sync_file(run_path(store.run_dir,command[key]))
    sync_file(path)
    return dict(schema_version=2,run_id=store.run_dir.name,intent_sha256=canonical_digest(intent),
                command=command,output=store.artifact(path),evidence=_evidence(store,command),
                created_at=command['finished_at'])


def media_operation(context,operation,*,encoded=None,write=False,runner=None,logger=None,retry=True,optional=False):
    """Read validates exact success; write may recover a receipt, never reencode it."""
    store=context['composition_store']; folder=store.path('commands'); successful=[]; recoverable=[]
    intents=sorted(folder.glob(operation+'-*.intent.json')) if folder.exists() else []
    known={path.with_name(path.name.replace('.intent.json','.success.json')) for path in intents}
    if folder.exists() and set(folder.glob(operation+'-*.success.json'))-known:
        raise ProductionRefused('orphan scene media success receipt')
    for path in intents:
        token=path.name[len(operation)+1:-len('.intent.json')]
        try:
            if str(UUID(token))!=token: raise ValueError()
        except ValueError as exc: raise ProductionRefused('command attempt UUID differs') from exc
        intent=read_json(path); object_fields(intent,INTENT_FIELDS,'scene command intent'); timestamp(intent['created_at'])
        equal({k:v for k,v in intent.items() if k!='created_at'},_identity(context,operation,token,encoded),'command intent identity')
        store.bind_artifact(store.artifact(path))
        command=_completion(context,intent,token); receipt_path=path.with_name(path.name.replace('.intent.json','.success.json'))
        if receipt_path.exists():
            if command is None: raise ProductionRefused('media success lacks original successful completion')
            success=read_json(receipt_path); object_fields(success,SUCCESS_FIELDS,'scene command success'); timestamp(success['created_at'])
            # This reconstruction is strictly read-only: probe output must already exist.
            try: output=store.validate_artifact(success['output'])
            except OSError as exc: raise ProductionRefused('original accepted '+operation+' output unavailable') from exc
            if str(output)!=intent['output']: raise ProductionRefused('media command output path differs')
            expected=dict(schema_version=2,run_id=store.run_dir.name,intent_sha256=canonical_digest(intent),
                command=command,output=store.artifact(output),evidence=_evidence(store,command),created_at=command['finished_at'])
            equal(success,expected,'command success original evidence')
            if operation=='probe' and output.read_bytes()!=run_path(store.run_dir,command['stdout_path']).read_bytes():
                raise ProductionRefused('probe raw output differs from original stdout')
            successful.append((receipt_path,success))
        elif command is not None:
            _evidence(store,command)
            if operation=='encode':
                try: store.artifact(run_path(store.run_dir,intent['output']))
                except OSError as exc: raise ProductionRefused('completed encode original output unavailable') from exc
            else:
                raw=run_path(store.run_dir,command['stdout_path']).read_bytes()
                if not raw: raise ProductionRefused('completed probe original stdout missing')
                output=run_path(store.run_dir,intent['output'])
                if output.exists() and output.read_bytes()!=raw: raise ProductionRefused('completed probe raw output conflict')
            recoverable.append((receipt_path,intent,command))
    if len(successful)+len(recoverable)>1: raise ProductionRefused('multiple successful original scene media attempts')
    if successful: return successful[0]
    if not write:
        if optional: return None
        raise ProductionRefused('required '+operation+' success receipt missing')
    if recoverable:
        receipt_path,intent,command=recoverable[0]; store.verify_global()
        success=_receipt(context,intent,command); store.verify_global(); store.write(receipt_path,success)
        return receipt_path,success
    if not retry: raise ProductionRefused('accepted candidate lacks original successful '+operation+' evidence')
    token=str(uuid4()); identity=_identity(context,operation,token,encoded)
    intent=dict(identity,created_at=now()); path=folder/(operation+'-'+token+'.intent.json')
    store.verify_global(); Path(intent['output']).parent.mkdir(parents=True,exist_ok=True); store.write(path,intent)
    store.bind_artifact(store.artifact(path))
    def guarded_log_write():
        store.assert_write(); store.verify_global()
    result=runner(tuple(intent['args']),cwd=Path(intent['cwd']),env=build_child_env(store.paths),timeout=300,
        logger=_GuardedLogger(logger,guarded_log_write),stage='scene_composition',unit_id=_unit(operation,token))
    store.verify_global()
    if type(result.returncode) is not int or result.returncode!=0 or result.timed_out:
        raise OSError('scene composition '+operation+' failed: '+str(result.stderr_path))
    command=_completion(context,intent,token)
    if command is None: raise ProductionRefused('original media command did not durably finish')
    success=_receipt(context,intent,command); store.verify_global()
    receipt_path=path.with_name(path.name.replace('.intent.json','.success.json')); store.write(receipt_path,success)
    return receipt_path,success
