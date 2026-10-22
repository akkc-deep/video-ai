"""Immutable schema-2 scene candidate composition, awaiting actual film review."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
from uuid import uuid4

from ..jimeng_config import STRATEGY
from ..media.composition_video import validate_probe, validate_audio_packets
from ..planning.production_scenes import canonical_digest
from ..planning.scene_media import plan_scene_contributions
from ..planning.production_timeline import validate_production_timeline
from .manifest import now, thaw
from .processes import run_logged
from .production_inputs import check_stage_space
from .production_composition_records import probe as validate_original_probe
from .production_state import ProductionRefused, RunLock, json_bytes, object_fields, run_path, timestamp
from .image_selection_records import _run
from .scene_clip_records import equal
from .scene_media_records import SceneMediaResult, scene_media_context, require_scene_upscale_acceptance_record
from ._scene_composition_materialized import (subtitle_layout, materialize, verify_materialized, copy_bytes)
from ._scene_composition_commands import media_operation, bind_command_completion_proof

TECHNICAL_CHECKS=('source_text_coverage','audio_samples','frame_mapping','subtitles','final_media')
COMMIT_FIELDS=('schema_version production_strategy run_id inputs_sha256 contributions_sha256 materialized_sha256 '
    'candidate subtitle ass narration encode_receipt probe_receipt technical_checks created_at').split()
COMPOSITION_RECORDS=('inputs.json','contributions.json','materialized-ready.json','materialized.json',
                     'media-ready/candidate.json','candidate-commit.json')
COMPOSITION_DIRECTORIES=('commands','probes','media-ready')


def boundary(point):
    """An interruption boundary after durable evidence; intentionally empty in production."""


def _command_inventory(store):
    for path in store.path('commands').glob('*.json'):
        if not re.fullmatch(r'(encode|probe)-[0-9a-f-]{36}\.(intent|success)\.json',path.name):
            raise ProductionRefused('unknown scene composition command evidence')


def _prepare(context):
    """Derive all composition inputs from fully admitted original scene evidence."""
    if 'composition_inputs' in context: return context
    frozen=context['frozen']; timeline=context['timeline']; units=context['units']
    context['composition_tool_stamps']=list(context['store'].guard_tool_stamps.values())
    validate_production_timeline(timeline)
    equal((units['decoded_text'],units['has_bom'],units['spans']),
          (timeline.original_text,timeline.has_bom,thaw(timeline.source_spans)),'composition original text')
    upscaled=require_scene_upscale_acceptance_record(context); context['upscaled']=upscaled
    store=context['store'].for_root('production/scene-composition'); context['composition_store']=store
    settings,events=subtitle_layout(context); context['subtitle_settings']=settings; context['subtitle_events']=events
    inputs=dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,
        algorithm='scene_composition_v1',frozen_options_sha256=canonical_digest(frozen.options),
        scene_clips_sha256=canonical_digest(context['scene_clips']),upscale_sha256=canonical_digest(upscaled),
        image_acceptance_sha256=canonical_digest(context['image_acceptance']),timeline_sha256=canonical_digest(timeline.as_dict()),
        units_sha256=canonical_digest(units),pcm=[dict(unit_id=c.unit_id,text_start=c.text_start,text_end=c.text_end,
            text=c.text,start_sample=c.start_sample,end_sample=c.end_sample,audio=store.artifact(c.pcm.path)) for c in timeline.clips],
        font=store.artifact(frozen.config.media.font_file),settings=dict(media=dict(output_fps=16,width=1920,height=1080,
            transition='cut',transition_seconds=0,burn_subtitles=True,music=None),subtitles=thaw(settings)))
    contributions=dict(schema_version=2,run_id=store.run_dir.name,inputs_sha256=canonical_digest(inputs),
        total_frames=timeline.total_frames,frames=plan_scene_contributions(context['scene_clips'],upscaled,timeline))
    context['composition_inputs']=inputs; context['contributions']=contributions
    for name,value in (('inputs.json',inputs),('contributions.json',contributions)):
        existing=store.read(name)
        if existing is not None: equal(existing,value,'composition '+name)
    for value in [inputs['font']]+[c['audio'] for c in inputs['pcm']]: store.bind_artifact(value)
    return context


def _capture(store,value):
    if isinstance(value,dict):
        if set(value)=={'path','bytes','sha256'}:
            store.bind_artifact(value)
        else:
            for child in value.values(): _capture(store,child)
    elif isinstance(value,(list,tuple)):
        for child in value: _capture(store,child)


def _bind_inventory(store,directory,inventory):
    key=str(directory)
    if key in store.guard_directories:
        equal(sorted(inventory),sorted(store.guard_directories[key]),'previous composition JSON inventory')
    store.guard_directories.setdefault(key,set(inventory))


def _capture_composition_guard(context,candidate):
    """Give downstream guards every admitted composition byte without freezing review writes."""
    store=context['composition_store']; base=context['store']
    if store.lock is not None:
        store.verify_global()
        base.verify_global()
    else:
        store.verify_captured_bytes()
        base.verify_captured_bytes()
    _capture(store,candidate); _capture(store,context['materialized'])
    _capture(store,context.get('composition_command_events'))
    store.capture_admitted(store.read('media-ready/candidate.json'))
    for relative in COMPOSITION_RECORDS:
        path=store.path(relative); store.bind_artifact(store.artifact(path))
    for relative in COMPOSITION_DIRECTORIES:
        directory=store.path(relative); inventory={str(path) for path in directory.rglob('*.json')}
        _bind_inventory(store,directory,inventory)
        for path in inventory: store.bind_artifact(store.artifact(path))
    from .scene_read_admission import merge_bound_guards
    merge_bound_guards(base,store)
    for key,stamp in store.guard_tool_stamps.items():
        if key in base.guard_tool_stamps and base.guard_tool_stamps[key]!=stamp:
            raise ProductionRefused('previous composition tool stamp changed')
        base.guard_tool_stamps.setdefault(key,stamp)
    store.verify_captured_bytes()
    base.verify_captured_bytes()


def _inspect(context,artifact,probe):
    """Complete read-only validation: all frames, CFR timestamps and decoded AAC."""
    store=context['composition_store']; source=store.validate_artifact(artifact)
    for stamp in context['composition_tool_stamps']: stamp.verify()
    key=('scene-composition',canonical_digest(artifact),context['timeline'].total_frames)
    if key in store.media_cache: return
    tools=context['frozen'].config.tools
    def execute(args):
        for stamp in context['composition_tool_stamps']: stamp.verify()
        try:
            result=subprocess.run([str(a) for a in args],stdin=subprocess.DEVNULL,capture_output=True,timeout=300,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.SubprocessError) as exc:
            raise ProductionRefused('candidate validation tool failed: '+str(exc)) from exc
        if result.returncode: raise ProductionRefused('candidate full media validation failed: '+result.stderr.decode(errors='replace'))
        for stamp in context['composition_tool_stamps']: stamp.verify()
        return result.stdout
    frames=context['timeline'].total_frames
    pts=json.loads(execute((tools['ffprobe'],'-v','error','-select_streams','v:0','-show_frames',
        '-show_entries','frame=best_effort_timestamp_time','-of','json',source)))
    try:
        validate_original_probe(probe,frames)
        validate_probe(probe,pts,fps=16,total_frames=frames,channels=1)
        execute((tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',source,'-map','0:v:0','-map','0:a:0','-f','null','-'))
        audio=execute((tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',source,'-map','0:a:0',
                       '-f','s16le','-acodec','pcm_s16le','pipe:1'))
        samples=len(audio)//2
        if len(audio)%2 or not frames*3000<=samples<frames*3000+2048:
            raise ValueError('candidate AAC decoded sample coverage differs')
        packets=json.loads(execute((tools['ffprobe'],'-v','error','-select_streams','a:0','-show_packets','-of','json',source)))
        validate_audio_packets(packets['packets'],frames*3000)
    except (ValueError,KeyError,TypeError) as exc: raise ProductionRefused(str(exc)) from exc
    store.validate_artifact(artifact); store.media_cache.add(key)


def _candidate_ready(context,encoded,encode_path,probe_path,*,write,promote_required=True):
    store=context['composition_store']; ready=store.read('media-ready/candidate.json'); target=store.path('candidate.mp4')
    recipe=dict(algorithm='identity_mp4_copy_v1',parameters={})
    if ready is None:
        if not write: raise ProductionRefused('candidate preparation receipt missing')
        if target.exists(): raise ProductionRefused('candidate bytes exist without original preparation ownership')
        staging=store.path('staging')/(str(uuid4())+'.mp4'); store.verify_global(); staging.parent.mkdir(parents=True,exist_ok=True)
        copied=copy_bytes(store,encoded,staging)
        ready=dict(schema_version=2,run_id=store.run_dir.name,operation='candidate',source=encoded,staging=copied,
            target=dict(copied,path=str(target)),recipe=recipe,evidence=[store.artifact(encode_path),store.artifact(probe_path)],created_at=now())
        store.verify_global(); path=store.write('media-ready/candidate.json',ready)
        store.bind_artifact(store.artifact(path)); boundary('candidate_ready')
    object_fields(ready,'schema_version run_id operation source staging target recipe evidence created_at'.split(),'candidate media ready')
    timestamp(ready['created_at'])
    equal({k:ready[k] for k in ('schema_version','run_id','operation','source','recipe','evidence')},
          dict(schema_version=2,run_id=store.run_dir.name,operation='candidate',source=encoded,recipe=recipe,
               evidence=[store.artifact(encode_path),store.artifact(probe_path)]),'candidate preparation binding')
    staging=run_path(store.run_dir,ready['staging']['path'])
    if staging.parent!=store.path('staging') or ready['target']['path']!=str(target):
        raise ProductionRefused('candidate preparation paths differ')
    for artifact in (ready['staging'],ready['target']):
        equal({k:artifact[k] for k in ('bytes','sha256')},{k:encoded[k] for k in ('bytes','sha256')},'candidate identity copy')
    store.validate_artifact(encoded)
    receipt_path=store.path('media-ready/candidate.json')
    if str(receipt_path) not in store.guard_paths:
        store.bind_artifact(store.artifact(receipt_path))
    if staging.exists(): store.validate_artifact(ready['staging'])
    if target.exists(): store.validate_artifact(ready['target'])
    elif write:
        store.validate_artifact(ready['staging']); store.verify_global(); os.rename(staging,target); store.verify_global()
        store.validate_artifact(ready['target']); boundary('candidate_promoted')
    elif promote_required: raise ProductionRefused('candidate media promotion incomplete')
    elif not staging.exists(): raise ProductionRefused('candidate preparation bytes missing')
    return ready


def _commit(context,*,write,logger=None):
    store=context['composition_store']
    _command_inventory(store)
    accepted=store.read('candidate-commit.json') is not None or store.read('media-ready/candidate.json') is not None
    for name,wanted in (('inputs.json',context['composition_inputs']),('contributions.json',context['contributions'])):
        if write: store.verify_global(); store.write(name,wanted)
        else:
            if store.read(name) is None: raise ProductionRefused('required composition '+name+' missing')
            equal(store.read(name),wanted,'composition '+name)
        store.bind_artifact(store.artifact(store.path(name)))
    if write:
        if accepted and store.read('materialized.json') is None and store.read('materialized-ready.json') is None:
            raise ProductionRefused('accepted candidate lacks original materialization evidence')
        value=materialize(context)
    else:
        value=store.read('materialized.json'); ready=store.read('materialized-ready.json')
        if value is None or ready is None: raise ProductionRefused('required materialized commit/ready missing')
        equal(value,ready,'materialized exact ready'); verify_materialized(context,value)
    context['materialized']=value; _capture(store,value)
    for relative in ('materialized-ready.json','materialized.json'):
        path=store.path(relative); store.bind_artifact(store.artifact(path))
    if write: boundary('materialized')
    encode_path,encode=media_operation(context,'encode',write=write,runner=run_logged,logger=logger,retry=not accepted)
    _capture(store,encode); store.bind_artifact(store.artifact(encode_path))
    boundary('encode_success') if write else None
    probe_path,probe=media_operation(context,'probe',encoded=encode['output'],write=write,runner=run_logged,logger=logger,retry=not accepted)
    _capture(store,probe); store.bind_artifact(store.artifact(probe_path))
    context['composition_command_events']=bind_command_completion_proof(context,(encode_path,encode),(probe_path,probe))
    boundary('probe_success') if write else None
    raw=store.validate_artifact(probe['output']); _inspect(context,encode['output'],json.loads(raw.read_bytes()))
    ready=_candidate_ready(context,encode['output'],encode_path,probe_path,write=write)
    commit=dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,
        inputs_sha256=canonical_digest(context['composition_inputs']),contributions_sha256=canonical_digest(context['contributions']),
        materialized_sha256=canonical_digest(value),candidate=ready['target'],subtitle=value['subtitle'],ass=value['ass'],
        narration=value['narration']['audio'],encode_receipt=store.artifact(encode_path),probe_receipt=store.artifact(probe_path),
        technical_checks={key:'passed' for key in TECHNICAL_CHECKS},created_at=ready['created_at'])
    _capture(store,commit)
    commit_path=store.path('candidate-commit.json')
    original_commit=store.artifact(commit_path) if commit_path.is_file() else None
    old=store.read('candidate-commit.json')
    if old is not None:
        if original_commit is None: raise ProductionRefused('candidate commit appeared during validation')
        object_fields(old,COMMIT_FIELDS,'candidate commit'); equal(old,commit,'candidate technical commit')
        store.bind_artifact(original_commit)
    elif write:
        raw=json_bytes(commit)
        store.verify_global(); path=store.write('candidate-commit.json',commit)
        store.bind_artifact(dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        boundary('candidate_commit')
    else: raise ProductionRefused('required candidate commit missing')
    return commit


def require_scene_composition_record(context):
    """Rebuild every original binding without writing missing records or media."""
    try:
        from .scene_read_admission import cached_admission,remember_admission
        cached=cached_admission(context,'composition')
        if cached is not None:return cached
        _prepare(context)
        store=context['composition_store']
        snapshot=store.snapshot_json(files=tuple(store.path(name) for name in COMPOSITION_RECORDS),
            directories=tuple(store.path(name) for name in COMPOSITION_DIRECTORIES))
        candidate=_commit(context,write=False)
        store.verify_admission_snapshot(snapshot)
        store.adopt_json_snapshot(snapshot)
        _capture_composition_guard(context,candidate)
        store.verify_admission_snapshot(snapshot)
        remember_admission(context,'composition',candidate)
        return candidate
    except ProductionRefused: raise
    except (OSError,ValueError,TypeError,KeyError,AttributeError,subprocess.SubprocessError) as exc:
        raise ProductionRefused('scene composition evidence unavailable or invalid: '+str(exc)) from exc


def _validate_partial_composition_state(context):
    """Validate a legal unfinished prefix read-only; never promote or repair evidence."""
    _prepare(context); store=context['composition_store']
    _command_inventory(store)
    if store.path('candidate.mp4').exists() and store.read('media-ready/candidate.json') is None:
        raise ProductionRefused('candidate exists without preparation ownership')
    if store.read('candidate-commit.json') is not None: return require_scene_composition_record(context)
    inputs=store.read('inputs.json'); contributions=store.read('contributions.json')
    if inputs is None:
        if any(store.root.rglob('*.json')): raise ProductionRefused('composition evidence lacks input identity')
        return None
    equal(inputs,context['composition_inputs'],'partial composition inputs')
    if contributions is None:
        if (store.read('materialized-ready.json') is not None or store.read('materialized.json') is not None
                or any(store.path('commands').glob('*.json')) or store.read('media-ready/candidate.json') is not None):
            raise ProductionRefused('materialized composition lacks contributions')
        return None
    equal(contributions,context['contributions'],'partial contributions')
    ready=store.read('materialized-ready.json'); materialized=store.read('materialized.json')
    if materialized is not None and ready is None: raise ProductionRefused('materialized commit lacks ready receipt')
    if ready is not None: verify_materialized(context,ready)
    if materialized is not None: equal(materialized,ready,'partial materialized commit')
    commands=store.path('commands')
    has_commands=commands.exists() and any(commands.glob('*.json'))
    if materialized is None:
        if has_commands or store.read('media-ready/candidate.json') is not None:
            raise ProductionRefused('command evidence lacks materialized commit')
        return None
    context['materialized']=materialized
    encoded=media_operation(context,'encode',optional=True)
    if encoded is None:
        if (commands.exists() and any(commands.glob('probe-*.json'))) or store.read('media-ready/candidate.json') is not None:
            raise ProductionRefused('probe/candidate evidence lacks encode acceptance')
        return None
    encode_path,encode=encoded
    probed=media_operation(context,'probe',encoded=encode['output'],optional=True)
    if probed is None:
        if store.read('media-ready/candidate.json') is not None:
            raise ProductionRefused('candidate preparation lacks probe acceptance')
        return None
    probe_path,probe=probed
    _inspect(context,encode['output'],json.loads(store.validate_artifact(probe['output']).read_bytes()))
    if store.read('media-ready/candidate.json') is not None:
        _candidate_ready(context,encode['output'],encode_path,probe_path,write=False,promote_required=False)
    elif store.path('candidate.mp4').exists(): raise ProductionRefused('candidate exists without preparation ownership')
    return None


def validate_scene_composition_state(context):
    """Public read-only partial validator with the same refusal contract as require."""
    try: return _validate_partial_composition_state(context)
    except ProductionRefused: raise
    except (OSError,ValueError,TypeError,KeyError,AttributeError,subprocess.SubprocessError) as exc:
        raise ProductionRefused('partial scene composition evidence unavailable or invalid: '+str(exc)) from exc


def _produce(context,logger):
    _prepare(context); store=context['composition_store']; timeline=context['timeline']
    # A completed candidate must validate before any recovery/creation is allowed.
    existing=store.read('candidate-commit.json')
    if existing is not None:
        object_fields(existing,COMMIT_FIELDS,'candidate commit')
        complete=all(store.path(name).is_file() for name in COMPOSITION_RECORDS)
        receipts=all(isinstance(existing[key],dict) and isinstance(existing[key].get('path'),str)
            and run_path(store.run_dir,existing[key]['path']).is_file() for key in ('encode_receipt','probe_receipt'))
        # Only outer immutable markers/receipts may be recovered from their exact original evidence.
        candidate=require_scene_composition_record(context) if complete and receipts else _commit(context,write=True,logger=logger)
    else:
        check_stage_space(context['frozen'].config,frames=timeline.total_frames,
            audio_bytes=timeline.total_frames*6000+44,encoded_bytes=timeline.total_frames*1920*1080*4)
        candidate=_commit(context,write=True,logger=logger)
    _capture_composition_guard(context,candidate)
    from .scene_final_observations import build_scene_final_observation_template
    clips=context['scene_clips']['clips']
    from ._scene_revision_readers import final_comparison_request
    requests=[final_comparison_request(context,c['clip_id']) for c in clips]
    template=build_scene_final_observation_template(context['frozen'],context['units'],timeline,candidate,
        context['scene_clips'],context['upscaled'],context['image_acceptance'],requests)
    store.verify_global(); path=store.write('final-observation-template.json',template)
    from .production_scene_delivery import final_observation_state
    state=final_observation_state(context,candidate=candidate)
    status='final_review_ready' if state['accepted'] else 'final_review_failed' if state['rejected'] else 'awaiting_final_review'
    return SceneMediaResult(run_id=store.run_dir.name,run_dir=store.run_dir,status=status,
        active_stage='final_review',upscaled_clips=store.run_dir/'production/scene-upscale/complete.json',
        candidate=Path(candidate['candidate']['path']),final_observation_template=path,log_dir=logger.root)


from .scene_revision_records import revision_validation


@revision_validation
def produce_scene_composition(frozen,units,timeline,*,paths,logger,lock=None):
    run=None; acquired=None; result=None; status='failed'; error=None
    try:
        # Complete frozen preparation validation precedes assigning any run/log identity or lock.
        candidate=_run(frozen)
        if not candidate.is_dir() or not (candidate/'production/options.json').is_file():
            raise ProductionRefused('unknown prepared scene composition run')
        if logger.run_dir!=candidate or not logger.production:
            raise ProductionRefused('scene composition requires matching production logger')
        run=candidate
        if lock is None: acquired=RunLock(run); acquired.__enter__(); lock=acquired
        context=scene_media_context(frozen,units,timeline,paths=paths,lock=lock); context['store'].assert_owned()
        result=_produce(context,logger)
    except KeyboardInterrupt as exc: status='interrupted'; error=exc
    except ProductionRefused as exc: status='blocked'; error=exc
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,AttributeError,subprocess.SubprocessError) as exc:
        status='failed' if run else 'blocked'; error=exc
    finally:
        if acquired is not None:
            try: acquired.__exit__(None,None,None)
            except Exception as exc:
                message=(str(error)+'; cleanup: ' if error else '')+str(exc)
                result=SceneMediaResult(run_id=run.name,run_dir=run,status='failed',active_stage='composition',
                    log_dir=logger.root,error=dict(kind=type(exc).__name__,message=message,evidence_paths=[]))
    if result is None:
        result=SceneMediaResult(run_id=run.name if run else None,run_dir=run,status=status,active_stage='composition',
            log_dir=logger.root if run else None,error=dict(kind=type(error).__name__,message=str(error) or type(error).__name__,evidence_paths=[]))
    return result
