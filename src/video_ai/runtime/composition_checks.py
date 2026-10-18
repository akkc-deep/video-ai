"""One exclusive staging composition transaction and reconstructing consumer."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from ..config import load_config,read_json
from ..media.composition_audio import write_narration,mix_music
from ..media.font_metrics import PrivateFont
from ..media.subtitles import plan_subtitles,srt_text,ass_text
from ..media.composition_video import command,ffmpeg,materialize_frames,encode_composition,check_subtitle_render
from .manifest import ManifestStore,hash_file,now,thaw
from .logging import RunLogger
from .timeline_checks import _run_path,_local,_again,_artifact,_fresh
from .upscale_checks import atomic_report
from ._composition_inputs import inputs,required_capacity,upstream_unchanged,shutil as capacity


class CompositionRefusal(ValueError):
    """Invalid path/state/input before a stage starts (CLI exit2)."""


@dataclass(frozen=True)
class CompositionResult:
    passed: bool
    run_dir: Path
    report_path: Path
    candidate_path: Path
    subtitle_path: Path
    total_frames: int
    total_samples: int
    staging_only: bool
    status: str


def result(run,status,plan=None):
    folder=run/'staging/composition'
    return CompositionResult(status=='completed',run,run/'composition.json',folder/'candidate.mp4',folder/'subtitle.srt',plan.total_frames if plan else 0,plan.video_samples if plan else 0,True,status)


@contextmanager
def exclusive(run):
    path=_local(run,run/'.composition.lock');owner=dict(pid=os.getpid(),token=uuid4().hex)
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except (OSError,ValueError) as exc:raise CompositionRefusal('composition lock refused: '+str(exc)) from exc
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(owner,f);f.flush();os.fsync(f.fileno())
        yield owner
    finally:
        try:
            if read_json(path)==owner:path.unlink()
        except (ValueError,OSError):pass
        except KeyboardInterrupt:
            if ManifestStore.open(run).snapshot()['stages']['composition']['status']!='completed':raise


def lock_unchanged(run,owner):
    if read_json(_local(run,run/'.composition.lock'))!=owner:raise OSError('foreign composition lock retained')


def validation():
    return dict(input_associations_passed=True,narration_samples_passed=True,subtitles_passed=True,frame_mapping_passed=True,media_passed=True,actual_final_video_semantics='unverified',actual_final_video_sync='unverified',full_film_acceptance='unverified')


def _text_file(path,text):
    with path.open('x',encoding='utf-8',newline='\n') as f:f.write(text);f.flush();os.fsync(f.fileno())


def compose_clips(config,*,run_dir,settings_path=None):
    from ._composition_evidence import validate,index_evidence
    try:run=_run_path(run_dir);store=ManifestStore.open(run)
    except (ValueError,OSError,TypeError) as exc:raise CompositionRefusal(str(exc)) from exc
    with exclusive(run) as owner:
        try:
            snapshot=store.snapshot();folder=_local(run,run/'staging/composition')
            if snapshot['stages']['composition']['status']!='pending' or 'composition_report' in snapshot['workflows'] or (run/'composition.json').exists() or folder.exists() or folder.is_symlink():raise ValueError('pending composition without orphan staging/report required')
            if (run/'logs/composition').exists():raise ValueError('orphan composition evidence directory')
            context=inputs(config,run,settings_path);plan=context['plan'];paths=context['paths']
            if capacity.disk_usage(run).free<required_capacity(plan):raise ValueError('insufficient composition disk capacity')
            with PrivateFont(config.media.font_file,context['settings'].font_name,context['settings'].font_size) as font:
                events=plan_subtitles(context['timeline'],context['settings'],measure=font.measure)
                metrics=dict(requested_face=font.name,selected_face=font.selected_face,size=font.size)
            _again(context['identities']);upstream_unchanged(store.snapshot(),snapshot);lock_unchanged(run,owner)
        except (ValueError,OSError,TypeError,KeyError) as exc:raise CompositionRefusal(str(exc)) from exc
        logger=RunLogger(run)
        try:
            def begin(data):
                upstream_unchanged(data,snapshot)
                store._record_status(data,data['stages']['composition'],'running',[],None,'composition',None)
            store.update(begin)
            folder.parent.mkdir(parents=True,exist_ok=True);folder.mkdir()
            kw=dict(config=config,paths=paths,logger=logger,cwd=folder)
            frames,commands=materialize_frames(plan,**kw)
            audio_plan=write_narration(context['timeline'],folder/'narration.wav')
            mixed_id=normalized_id=mixed_plan=None;audio=folder/'narration.wav'
            if config.media.music:
                normalized=folder/'music.f32'
                commands.append(command([*ffmpeg(config),'-i',str(config.media.music),'-vn','-ar','48000','-ac','2','-c:a','pcm_f32le','-f','f32le',str(normalized)],operation='normalize_music',**kw))
                normalized_id=thaw(hash_file(normalized));audio=folder/'mixed.wav'
                mixed_plan=mix_music(folder/'narration.wav',normalized,audio,settings=context['settings']);mixed_id=thaw(hash_file(audio))
            fonts=folder/'fonts';fonts.mkdir()
            with config.media.font_file.open('rb') as source,(fonts/'font.ttc').open('xb') as out:shutil.copyfileobj(source,out)
            _text_file(folder/'subtitle.srt',srt_text(events));_text_file(folder/'subtitles.ass',ass_text(events,context['settings']))
            render=check_subtitle_render(events,context['settings'],**kw);commands.extend(render['commands'])
            info,more=encode_composition(folder/'video-frames',audio,fps=plan.output_fps,frames=plan.total_frames,channels=2 if mixed_id else 1,**kw);commands.extend(more)
            plan_path=logger.save_json('composition/plan.json',plan)
            execution=dict(schema_version=1,run_id=run.name,plan_identity=thaw(hash_file(plan_path)),output_frames=frames,audio_plan=audio_plan,normalized_music_identity=normalized_id,mixed_audio_plan=mixed_plan,subtitle_render=render,font_metrics=metrics,commands=commands)
            execution_path=logger.save_json('composition/execution.json',execution)
            report=dict(schema_version=1,run_id=run.name,created_at=now(),status='completed',passed=True,staging_only=True,input_identities=thaw(context['identities']),settings=thaw(context['settings']),settings_identity=thaw(context['settings_identity']),plan_identity=execution['plan_identity'],frame_mappings=thaw(plan.ordered_frame_map),requirement_bindings=thaw(plan.requirement_bindings),cue_checks=thaw(plan.cue_checks),narration_identity=thaw(hash_file(folder/'narration.wav')),mixed_audio_identity=mixed_id,subtitles=dict(srt_identity=thaw(hash_file(folder/'subtitle.srt')),ass_identity=thaw(hash_file(folder/'subtitles.ass')),events=events),candidate_identity=info['identity'],effective_media={k:v for k,v in info.items() if k!='identity'},provenance=context['provenance'],validation=validation(),request_evidence=index_evidence(run,folder,plan_path,execution_path,commands))
            validate(config,run,report,context,inspect_actual=False)
            fresh_context=inputs(config,run,settings_path)
            _again(context['identities']);_again(fresh_context['identities']);upstream_unchanged(store.snapshot(),snapshot);lock_unchanged(run,owner)
            atomic_report(run,run/'composition.json',report)
            # Re-read exactly the bytes that will be bound in the same manifest transaction.
            saved=read_json(run/'composition.json');validate(config,run,saved,fresh_context,inspect_actual=False)
            identity=hash_file(run/'composition.json')
            def commit(data):
                upstream_unchanged(data,snapshot);lock_unchanged(run,owner);_again(context['identities'])
                _again({'report':identity})
                if data['stages']['composition']['status']!='running' or 'composition_report' in data['workflows']:raise ValueError('composition state changed before completion')
                data['workflows']['composition_report']=thaw(identity)
                store._record_status(data,data['stages']['composition'],'completed',[_artifact(identity)],None,'composition',None)
            store.update(commit)
            return result(run,'completed',plan)
        except BaseException as exc:
            if store.snapshot()['stages']['composition']['status']=='completed':return result(run,'completed',plan)
            status='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed'
            evidence=[]
            try:
                trace=logger.exception('composition',None,exc);evidence.append(str(trace))
                diagnostic=logger.save_json(f'composition/diagnostic-{uuid4().hex}.json',dict(status=status,error=str(exc),traceback_path=str(trace),created_at=now()));evidence.append(str(diagnostic))
            except (ValueError,OSError,KeyboardInterrupt):pass
            error=dict(kind=status,message=str(exc),traceback_path=evidence[0] if evidence else None,evidence_paths=evidence)
            try:
                def fail(data):
                    stage=data['stages']['composition']
                    if stage['status']=='running':store._record_status(data,stage,status,stage['artifacts'],error,'composition',None)
                store.update(fail)
            except (ValueError,OSError,KeyboardInterrupt):pass
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
            return result(run,'failed',plan)


def load_committed_composition(run_dir):
    from ._composition_evidence import validate
    from ._composition_inputs import fresh
    run=_run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['composition']
    if stage['status']!='completed':raise ValueError('composition is not completed')
    path=_local(run,run/'composition.json')
    registered=snapshot['workflows'].get('composition_report')
    if registered is None:raise ValueError('composition receipt missing')
    identity=fresh(registered,run=run,expected=path)
    artifacts=stage['artifacts']
    if len(artifacts)!=1 or Path(artifacts[0]['path'])!=path:raise ValueError('composition artifact missing/extra')
    artifact=_fresh(artifacts[0],run=run,expected=path)
    if artifact.sha256!=identity.sha256:raise ValueError('composition artifact differs from receipt')
    report=read_json(path);config=load_config(Path(snapshot['config_snapshot']['path']))
    settings_path=Path(report['settings_identity']['path']) if report.get('settings_identity') else None
    context=inputs(config,run,settings_path)
    validate(config,run,report,context,inspect_actual=True)
    _again(context['identities']);_again({'composition':identity})
    current=store.snapshot();upstream_unchanged(current,snapshot)
    if current['stages']['composition']!=stage or current['workflows']['composition_report']!=registered:raise OSError('composition receipt changed during consumption')
    return report
