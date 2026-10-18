"""One exclusive timeline transaction over an existing, verified speech run."""
from contextlib import contextmanager
from dataclasses import dataclass, fields
from pathlib import Path
import json
import os
from uuid import uuid4
import wave

from ..config import ProjectConfig, read_json
from ..media.audio import AudioInfo
from ..planning.segments import SegmentedScript, TextSpan, segment_text, validate_segments
from ..planning.timeline import Timeline, build_timeline, validate_timeline
from .logging import RunLogger
from .manifest import ManifestStore, hash_file, now, thaw, validate_run_dir, _identity, _timestamp
from .migration import atomic_report
from .paths import PathPolicy


class TimelineRefusal(ValueError):
    """Illegal path, preexisting artifact/lock or non-pending stage (CLI exit2)."""


@dataclass(frozen=True)
class TimelineResult:
    passed: bool
    run_dir: Path
    timeline_path: Path
    total_samples: int
    total_frames: int
    listening_accepted: bool


def _run_path(path):
    try:
        original=Path(path).absolute()
        run=validate_run_dir(original)
        if original!=run: raise ValueError('redirected/noncanonical run path')
        if not run.is_dir(): raise ValueError('existing run directory required')
        return run
    except ValueError as exc: raise TimelineRefusal(str(exc)) from exc


def _local(run,path):
    original=Path(path)
    validated=PathPolicy().validate_write(original,'run')
    if not validated.is_relative_to(run) or original!=validated:
        raise ValueError('run input/evidence escapes or redirects its directory')
    return validated


@contextmanager
def _exclusive(run):
    path=_local(run,run/'.timeline.lock')
    try: fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc: raise TimelineRefusal(f'existing timeline lock: {path}') from exc
    owner=dict(pid=os.getpid(),token=uuid4().hex)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as file:
            json.dump(owner,file); file.flush(); os.fsync(file.fileno())
        yield
    finally:
        # An unknown or replaced lock belongs to somebody else; never delete it.
        try:
            if read_json(path)==owner: path.unlink()
        except (OSError,ValueError): pass
        except KeyboardInterrupt:
            if ManifestStore.open(run).snapshot()['stages']['timeline']['status']!='completed': raise
            # Completion is durable. Retry only this token's cleanup, never a foreign lock.
            try:
                if read_json(path)==owner: path.unlink()
            except (OSError,ValueError,KeyboardInterrupt): pass


def _fresh(record, *, run=None, expected=None):
    _identity(record,artifact='category' in record)
    path=Path(record['path'])
    if run is not None: path=_local(run,path)
    if expected is not None and path!=expected: raise ValueError('unexpected input identity path')
    fresh=hash_file(path)
    if (fresh.bytes!=record['bytes'] or fresh.sha256!=record['sha256']
            or ('mtime_ns' in record and fresh.mtime_ns!=record['mtime_ns'])):
        raise OSError(f'input identity changed: {path}')
    return fresh


def _again(identities):
    for original in identities.values():
        fresh=hash_file(Path(original.path))
        if (fresh.path,fresh.bytes,fresh.mtime_ns,fresh.sha256)!=(original.path,original.bytes,original.mtime_ns,original.sha256):
            raise OSError(f'timeline input changed after verification: {original.path}')


def _pcm(run,span,unit):
    uid=span['unit_id']
    expected=run/'audio'/uid/'pcm-48000.wav'
    identity=_fresh(span['pcm'],run=run,expected=expected)
    if unit['status']!='completed': raise ValueError('speech unit not completed')
    registered=[a for a in unit['artifacts'] if Path(a['path'])==expected]
    if len(registered)!=1 or (registered[0]['bytes'],registered[0]['sha256'])!=(identity.bytes,identity.sha256):
        raise ValueError('speech PCM not bound to manifest artifact')
    for name,want in [('sample_rate',48000),('channels',1),('sample_width',2)]:
        if type(span.get(name)) is not int or span[name]!=want: raise ValueError('invalid speech PCM metadata')
    samples=span['samples']
    if type(samples) is not int or samples<=0: raise ValueError('invalid speech sample count')
    with wave.open(str(expected),'rb') as f:
        if (f.getframerate(),f.getnchannels(),f.getsampwidth(),f.getcomptype(),f.getnframes())!=(48000,1,2,'NONE',samples):
            raise ValueError('speech PCM format/sample mismatch')
        remaining=samples
        while remaining:
            count=min(remaining,65536)
            if len(f.readframes(count))!=count*2: raise ValueError('truncated PCM payload')
            remaining-=count
        if f.readframes(1): raise ValueError('extra PCM payload')
    # Hash again after reading WAV so a mutation during decode cannot be accepted.
    _again({'pcm':identity})
    return AudioInfo(expected,identity.sha256,identity.bytes,48000,1,2,samples),identity


def _listening(run,segments_identity,spans,identities):
    snapshot=ManifestStore.open(run).snapshot()
    receipt=snapshot['workflows'].get('voice_acceptance')
    if receipt is not None:
        from .pipeline_reviews import fresh_identity, validate_voice_acceptance
        identity=fresh_identity(receipt,run=run)
        report=read_json(run/'segments.json')
        more=validate_voice_acceptance(run,read_json(Path(identity.path)),report,segments_identity)
        identities.update(more);identities['voice_listening']=identity
        return True,identity
    report=read_json(run/'segments.json')
    if report.get('import_identity') is not None:
        from .pipeline_import import load_pipeline_import
        from .speech_checks import load_committed_speech
        receipt=load_pipeline_import(run,identity=report['import_identity'])
        expected={s.unit_id for s in spans if s.kind=='speech'}
        if report.get('reference_replay'):expected.add('reference_replay')
        if set(report.get('reused_units',{}))==expected:
            origin=load_committed_speech(run.parent/receipt['parent_run_id'])
            if origin['accepted']:
                identities.update({'origin_acceptance/'+k:v for k,v in origin['input_identities'].items()})
                return True,origin['listening_identity']
    path=_local(run,run/'voice-listening.json')
    if not path.exists(): return False,None
    identity=hash_file(path); identities['voice_listening']=identity
    data=read_json(path)
    if type(data.get('schema_version')) is not int or data['schema_version']!=1 or any(type(data.get(k)) is not bool for k in ('listened','accepted')):
        raise ValueError('invalid listening schema/flags')
    if data['accepted'] and not data['listened']: raise ValueError('acceptance requires listening')
    if data.get('segments_identity') is not None or data['accepted']:
        bound=_fresh(data['segments_identity'],run=run,expected=run/'segments.json')
        if bound.sha256!=segments_identity.sha256: raise ValueError('listening segments mismatch')
    expected=[s for s in spans if s.kind=='speech']
    records=data['audio']
    if not isinstance(records,list) or len(records)!=len(expected): raise ValueError('listening audio coverage mismatch')
    for record,span in zip(records,expected):
        if record['unit_id']!=span.unit_id or record['text']!=span.text or type(record['samples']) is not int:
            raise ValueError('listening original text/order mismatch')
        pcm=identities['pcm/'+span.unit_id]
        audio=_fresh(record['pcm'],run=run,expected=Path(pcm.path))
        if audio.sha256!=pcm.sha256 or record['samples']!=identities['sample_counts'][span.unit_id]:
            raise ValueError('listening PCM/sample mismatch')
    if data['accepted']:
        if not isinstance(data.get('user_statement'),str) or not data['user_statement'].strip():
            raise ValueError('accepted listening requires user statement')
        _timestamp(data.get('accepted_at'))
    return data['listened'] and data['accepted'],identity


def _inputs(config,run,snapshot):
    if snapshot['stages']['speech']['status']!='completed': raise ValueError('speech stage not completed')
    identities={}
    segments_path=_local(run,run/'segments.json')
    registered=[a for a in snapshot['stages']['speech']['artifacts'] if Path(a['path'])==segments_path]
    if len(registered)!=1: raise ValueError('speech report artifact missing/duplicate')
    identities['segments']=_fresh(registered[0],run=run,expected=segments_path)
    report=read_json(segments_path)
    if (type(report.get('schema_version')) is not int or report['schema_version'] not in (1,2)
            or report.get('status')!='completed' or report.get('passed') is not True or report.get('coverage_verified') is not True
            or report.get('run_dir')!=str(run)):
        raise ValueError('speech report is unverified or belongs to another run')
    identities['source']=_fresh(report['source'])
    identities['script_copy']=_fresh(report['script_copy'],run=run,expected=run/'script.txt')
    if identities['source'].sha256!=identities['script_copy'].sha256: raise ValueError('original/copied script mismatch')
    if snapshot['inputs'].get('script') is None: raise ValueError('manifest missing original script')
    frozen_source=_fresh(snapshot['inputs']['script'],expected=Path(identities['source'].path))
    if frozen_source.sha256!=identities['source'].sha256: raise ValueError('manifest script mismatch')
    script=SegmentedScript.read(run/'script.txt')
    if script.text!=report['decoded_text'] or type(report['has_bom']) is not bool or script.has_bom!=report['has_bom']:
        raise ValueError('original text/BOM mismatch')
    span_fields=[f.name for f in fields(TextSpan)]
    spans=tuple(TextSpan(**{k:item[k] for k in span_fields}) for item in report['spans'])
    validate_segments(script.text,spans)
    if report['schema_version']==1:
        if spans!=segment_text(script.text): raise ValueError('noncanonical speech boundaries')
    elif report.get('import_identity') is not None:
        from .speech_checks import verify_speech_import
        identities.update(verify_speech_import(run,report,script,spans))
    else:
        from .pipeline_reviews import fresh_identity,load_unit_review
        review_identity=fresh_identity(report['segmentation_identity'],run=run,expected=run/'logs/pipeline/unit-review.json')
        reviewed=load_unit_review(Path(review_identity.path),script_path=Path(identities['source'].path),run_dir=run)
        if reviewed.script.spans!=spans:raise ValueError('speech differs from author reviewed boundaries')
        identities['segmentation']=review_identity
        expected_policy=dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300,
            tts_request_timeout_seconds=config.timeouts['tts_request'])
        if report['execution_policy']!=expected_policy:raise ValueError('speech execution policy mismatch')
    script=SegmentedScript(script.text,script.has_bom,spans)
    for name,path,raw in [('config',config.config_file,config.raw),('voice',config.voice.config_file,config.voice.raw)]:
        snapshot_name='config_snapshot' if name=='config' else 'voice_snapshot'
        frozen=snapshot[snapshot_name]
        if Path(frozen['path'])!=path or frozen['raw']!=thaw(raw) or read_json(path)!=thaw(raw):
            raise OSError('current config/voice differs from immutable raw snapshot')
        identities[name]=_fresh(snapshot['inputs'][name],expected=path)
        _fresh(report['inputs'][name],expected=path)
    units=snapshot['units']['speech']
    expected={span.unit_id for span in spans if span.kind=='speech'}
    if not expected or set(units)-{'reference_replay'}!=expected: raise ValueError('speech unit set mismatch')
    audio={}
    for span,item in zip(spans,report['spans']):
        if span.kind=='skip':
            if item.get('status')!='skip' or any(k in item for k in ('pcm','samples','raw')):
                raise ValueError('skip cannot contain audio')
            continue
        if item['status']!='completed': raise ValueError('speech segment not completed')
        info,identity=_pcm(run,item,units[span.unit_id])
        audio[span.unit_id]=info; identities['pcm/'+span.unit_id]=identity
    if type(report['total_speech_samples']) is not int or report['total_speech_samples']!=sum(a.samples for a in audio.values()):
        raise ValueError('speech sample total mismatch')
    # Counts are temporary listening inputs, not file identities.
    identities['sample_counts']={uid:a.samples for uid,a in audio.items()}
    accepted,listening=_listening(run,identities['segments'],spans,identities)
    identities.pop('sample_counts')
    _again(identities)
    return script,audio,identities,accepted,listening


def _artifact(identity):
    result=thaw(identity); result.pop('mtime_ns'); result['category']='run'; return result


from .verification import verified_read


@verified_read
def load_committed_timeline(run_dir: Path) -> Timeline:
    """Readers need both the completed stage and its freshly hashed artifact."""
    run=_run_path(run_dir)
    store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['timeline']
    if stage['status']!='completed': raise ValueError('timeline stage is not completed')
    path=run/'timeline.json'
    artifacts=[a for a in stage['artifacts'] if Path(a['path'])==path]
    if len(artifacts)!=1: raise ValueError('timeline artifact missing/duplicate')
    identity=_fresh(artifacts[0],run=run,expected=path)
    report=read_json(path)
    timeline=_read_timeline(report,run)
    from ..config import load_config
    config=load_config(Path(snapshot['config_snapshot']['path']))
    script,audio,identities,accepted,listening=_inputs(config,run,snapshot)
    rebuilt=build_timeline(script,audio,settings=config.media.timeline,fps=config.media.fps)
    if rebuilt!=timeline:raise ValueError('committed timeline differs from original samples/settings')
    provenance=report['provenance']
    for key in ('source','script_copy','segments','config','voice'):
        bound=_fresh(provenance[key],expected=Path(identities[key].path))
        if (bound.bytes,bound.sha256)!=(identities[key].bytes,identities[key].sha256):raise ValueError('timeline provenance differs')
    if set(provenance['pcm'])!=set(audio):raise ValueError('timeline PCM coverage mismatch')
    for uid,record in provenance['pcm'].items():
        bound=_fresh(record,run=run,expected=audio[uid].path)
        if bound.sha256!=audio[uid].sha256:raise ValueError('timeline PCM identity mismatch')
    if provenance['voice_listening'] is not None:
        if listening is None:raise ValueError('timeline listening provenance lost')
        bound=_fresh(provenance['voice_listening'],expected=Path(listening.path))
        if bound.sha256!=listening.sha256:raise ValueError('timeline listening provenance changed')
    if report['validation']['listening_accepted']!=accepted:raise ValueError('timeline audio acceptance changed')
    if provenance['speech_evidence']!=snapshot['stages']['speech']:raise ValueError('timeline speech snapshot changed')
    _again(identities)
    _again({'timeline':identity})
    if store.snapshot()['stages']['timeline']!=stage:raise OSError('timeline stage changed during consume')
    return timeline


def _read_timeline(report,run):
    if report.get('status')!='completed' or report.get('passed') is not True or report.get('run_id')!=run.name:
        raise ValueError('timeline report status/run mismatch')
    names={f.name for f in fields(Timeline)}
    extra={'run_id','status','passed','created_at','provenance','validation'}
    if set(report)!=names|extra: raise ValueError('timeline report fields mismatch')
    return Timeline.from_dict({k:report[k] for k in names})


def _diagnose(logger,run,exc,status):
    error=dict(kind=type(exc).__name__,message=str(exc),traceback_path=None,evidence_paths=[])
    try:error['traceback_path']=str(logger.exception('timeline',None,exc))
    except (Exception,KeyboardInterrupt):pass
    try:
        failure=logger.save_json(f'timeline/{uuid4().hex}.failure.json',dict(passed=False,
            status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',manifest_status=status,error=error,run_id=run.name))
        error['evidence_paths']=[str(failure)]
    except (Exception,KeyboardInterrupt):pass
    return error


def plan_timeline(config: ProjectConfig, *, run_dir: Path) -> TimelineResult:
    run=_run_path(run_dir)
    try:store=ManifestStore.open(run)
    except (OSError,ValueError) as exc:
        # JSON readers wrap I/O as ConfigError; run evidence is still a runtime failure.
        try:_diagnose(RunLogger(run),run,exc,'unreadable')
        except (Exception,KeyboardInterrupt):pass
        return TimelineResult(False,run,run/'timeline.json',0,0,False)
    return _transaction(config,run,store)


def _transaction(config,run,store):
    path=_local(run,run/'timeline.json')
    with _exclusive(run):
        initial=store.snapshot()
        if initial['stages']['timeline']['status']!='pending' or path.exists():
            raise TimelineRefusal('timeline stage already started or artifact exists; evidence-based recovery required')
        logger=RunLogger(run)
        result=TimelineResult(False,run,path,0,0,False)
        try:
            script,audio,identities,accepted,listening=_inputs(config,run,initial)
            store.record_stage('timeline','running')
            timeline=build_timeline(script,audio,settings=config.media.timeline,fps=config.media.fps)
            validate_timeline(timeline)
            evidence=logger.save_json(f'timeline/{uuid4().hex}.validation.json',dict(
                original_coverage=True,pcm_content=True,input_identity=True,sample_coverage=True,frame_budget=True,
                identities=thaw(identities),listening_accepted=accepted))
            report=timeline.as_dict()
            report.update(run_id=run.name,status='completed',passed=True,created_at=now(),
                provenance=dict(source=thaw(identities['source']),script_copy=thaw(identities['script_copy']),
                    segments=thaw(identities['segments']),config=thaw(identities['config']),voice=thaw(identities['voice']),
                    pcm={uid:thaw(identities['pcm/'+uid]) for uid in audio},voice_listening=thaw(listening),
                    speech_evidence=initial['stages']['speech']),
                validation=dict(original_coverage=True,pcm_content=True,input_identity=True,sample_coverage=True,
                    frame_budget=True,listening_accepted=accepted,evidence_paths=[str(evidence)]))
            _again(identities)
            if store.snapshot()['stages']['speech']!=initial['stages']['speech']: raise OSError('speech stage changed')
            if path.exists(): raise OSError('timeline appeared during transaction')
            atomic_report(path,report)
            identity=hash_file(path)
            reread=read_json(path)
            if reread!=report: raise OSError('timeline readback differs from written content')
            _read_timeline(reread,run)
            _again(identities)
            _again({'timeline':identity})
            result=TimelineResult(True,run,path,timeline.total_samples,timeline.total_frames,accepted)
            store.record_stage('timeline','completed',artifacts=[_artifact(identity)])
            return result
        except BaseException as exc:
            # Persistence may have succeeded immediately before an interrupt/error.
            status=store.snapshot()['stages']['timeline']['status']
            if status=='completed':
                load_committed_timeline(run)
                return result
            error=_diagnose(logger,run,exc,status)
            if status=='running':
                try:store.record_stage('timeline','interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=error)
                except Exception:
                    # No terminal-state claim if the manifest itself is unwritable.
                    if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise exc
                    raise
            if isinstance(exc,(KeyboardInterrupt,SystemExit)): raise
            return TimelineResult(False,run,path,0,0,False)
