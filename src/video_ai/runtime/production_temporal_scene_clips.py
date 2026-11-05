"""Native scene production and streaming assembly, with separate playback admission."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from ..adapters.common import strict_json, JSON_LIMIT
from ..planning.production_scenes import canonical_digest
from .manifest import now
from .production_state import ProductionRefused
from .temporal_scene_records import (collect_temporal_progress, complete_temporal_value, expected_temporal_request,
    temporal_chain_sources, temporal_workflow, validate_temporal_window)
from .temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation
from .temporal_native_worker import artifact, checked_artifact, prepare_native_input, write_record, _rgb


def commit_native_png(path, frame):
    """OpenCV is already the local continuity dependency; RGB stays explicit."""
    import cv2
    import numpy as np
    path = Path(path)
    if path.exists():
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None or not np.array_equal(image[:, :, ::-1], frame): raise ProductionRefused('native PNG pixel drift')
        return artifact(path)
    ok, data = cv2.imencode('.png', np.ascontiguousarray(frame[:, :, ::-1]))
    if not ok: raise ProductionRefused('native PNG encoding failed')
    from .temporal_scene_admission import _write_exact
    _write_exact(path, data.tobytes())
    return artifact(path)


def _movie(store, target, frames, *, lossless):
    """Stream one RGB frame at a time; never load an arbitrarily long chain."""
    from .processes import stop_process
    from .scene_clip_records import _decode_video
    from .execution_limits import command_timeout
    import numpy as np
    if target.exists():
        _decode_video(store, artifact(target), frames=len(frames), width=768, height=432)
        return artifact(target)
    temp = target.with_name(target.stem+'.'+uuid4().hex+'.pending.mp4')
    command = [str(store.frozen.config.tools['ffmpeg']), '-nostdin', '-n', '-v', 'error', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s:v', '768x432', '-r', '16', '-i', 'pipe:0', '-an', '-c:v',
        'libx264rgb' if lossless else 'libx264', '-crf', '0' if lossless else '18', '-preset', 'medium',
        '-threads', '2', '-pix_fmt', 'rgb24' if lossless else 'yuv420p', str(temp)]
    process = None
    with target.with_name(target.name+'.'+uuid4().hex+'.stderr.log').open('xb') as stderr:
        try:
            store.assert_owned()
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for index, frame in enumerate(frames):
                if index % 80 == 0: store.assert_owned()
                process.stdin.write(np.ascontiguousarray(frame).tobytes())
            process.stdin.close()
            if process.wait(timeout=command_timeout(300)) != 0: raise ProductionRefused('native chain encoding failed')
        finally:
            if process is not None: stop_process(process)
    _decode_video(store, artifact(temp), frames=len(frames), width=768, height=432)
    store.assert_owned()
    if target.exists(): raise ProductionRefused('native movie destination appeared')
    os.rename(temp, target)
    return artifact(target)


def _verify_rgb_movie(store, path, frames):
    """Complete lossless pixel proof with constant-size decode reads."""
    from .processes import stop_process
    import numpy as np
    command = [str(store.frozen.config.tools['ffmpeg']), '-nostdin', '-v', 'error', '-xerror', '-i', str(path),
        '-map', '0:v:0', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1']
    process = None; size = 432*768*3
    with Path(path).with_name('pixel-proof-'+uuid4().hex+'.stderr.log').open('xb') as stderr:
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            for index, frame in enumerate(frames):
                if index % 80 == 0: store.assert_owned()
                data = bytearray()
                while len(data) < size:
                    chunk = process.stdout.read(size-len(data))
                    if not chunk: raise ProductionRefused('native RGB decode ended early')
                    data.extend(chunk)
                if data != np.ascontiguousarray(frame).tobytes(): raise ProductionRefused('native RGB chain pixels differ')
            if process.stdout.read(1): raise ProductionRefused('native RGB decode has extra frames')
            if process.wait(timeout=None): raise ProductionRefused('native RGB decode failed')
        finally:
            if process is not None: stop_process(process)


def assemble_temporal_chain(context, scene_id, windows):
    import numpy as np
    from .temporal_scene_records import validate_temporal_chain
    store = context['store']; store.assert_owned()
    if not windows or any(window['status'] != 'static_ready' for window in windows):
        raise ProductionRefused('chain assembly requires actual static screenings')
    from .temporal_scene_origins import inherited_temporal_chain
    inherited=inherited_temporal_chain(context,scene_id,windows)
    if inherited is not None:return strict_json(Path(inherited['result']['path']).read_bytes())
    folder = store.path(Path('chains')/scene_id); folder.mkdir(parents=True, exist_ok=True)
    if (folder/'result.json').exists():
        validate_temporal_chain(context, scene_id, windows)
        return store.read(folder/'result.json')
    sources = temporal_chain_sources(windows)
    start, end = sources[0]['chain_frame_range'][0], sources[-1]['chain_frame_range'][1]
    count = end-start
    if shutil.disk_usage(folder).free < 32*1024**3+count*432*768*3*4:
        raise ProductionRefused('insufficient real free disk for complete native chain')
    final_frames = folder/'frames.npy'
    temporary = folder/('frames-'+uuid4().hex+'.pending.npy')
    frames = np.lib.format.open_memmap(temporary, mode='w+', dtype=np.uint8, shape=(count,432,768,3))
    cursor = 0
    for window in windows:
        store.assert_owned(); budget = window['budget']
        if budget['scene_id'] != scene_id or budget['start_frame'] != start+cursor:
            raise ProductionRefused('native chain mapping gap/scene mismatch')
        raw = _rgb(checked_artifact(window['raw_frames']), (93,432,768,3))
        retained = raw[budget['retained_source_start']:budget['retained_source_end']]
        frames[cursor:cursor+len(retained)] = retained; cursor += len(retained)
        del retained, raw
    if cursor != count: raise ProductionRefused('native chain frame contribution differs')
    frames.flush(); del frames
    if final_frames.exists():
        if artifact(final_frames)['sha256'] != artifact(temporary)['sha256']: raise ProductionRefused('native partial assembly differs')
        temporary.unlink()
    else: os.rename(temporary, final_frames)
    frames = _rgb(final_frames, (count,432,768,3))
    raw_movie = _movie(store, folder/'raw.mp4', frames, lossless=True)
    _verify_rgb_movie(store, Path(raw_movie['path']), frames)
    viewing = _movie(store, folder/'viewing.mp4', frames, lossless=False)
    mapping = dict(schema_version=1, protocol='longcat_native16_v1', fps='16/1', frame_range=[start,end], windows=sources,
        history_output_once=True, blend_interpolate_repeat_or_retime=False)
    mapping_id = write_record(folder/'mapping.json', mapping)
    diagnostics = write_record(folder/'diagnostics.json', dict(algorithm='native_chain_lossless_full_pixel_proof_v1',
        pixels_exact=True, frames=count, visual_acceptance='unverified', scope='technical mapping only'))
    result = dict(schema_version=1, algorithm='longcat_native_scene_chain_v1', scene_id=scene_id,
        inputs_sha256=canonical_digest(context['inputs']), frames=count, fps='16/1', frame_range=[start,end],
        boundary_frames=[item['chain_frame_range'][0] for item in sources[1:]], windows=sources,
        artifacts=dict(frames=artifact(final_frames), raw_movie=raw_movie, viewing_movie=viewing, mapping=mapping_id, diagnostics=diagnostics),
        technical=dict(raw=dict(frames=count,fps='16/1',width=768,height=432,pixel_exact=True),
            viewing=dict(frames=count,fps='16/1',width=768,height=432,pixel_exact=False)), history_output_once=True,
        blend_interpolate_repeat_or_retime=False, new_model_calls=0, created_at=now())
    store.assert_owned(); store.write(folder/'result.json', result)
    return result


def _scenes(context, progress):
    result = []
    for scene in context['plan']['scenes']:
        windows = [window for window in progress['records'] if window['budget']['scene_id'] == scene['scene_id']]
        chain = next((chain for chain in progress['chains'] if chain['scene_id']==scene['scene_id']), None)
        result.append(dict(scene_id=scene['scene_id'], status=progress['status'],
            completed_clip_ids=[window['budget']['clip_id'] for window in windows if 'result' in window],
            accepted_clip_ids=[window['budget']['clip_id'] for window in windows] if chain and chain['status']=='accepted' else [],
            waiting_clip_id=next((window['budget']['clip_id'] for window in windows if window['status']!='static_ready'), None), error=None))
    return result


def finish_temporal_clips(context):
    from .production_scene_clips import _result, _error
    from .scene_continuity_records import require_scene_continuity_acceptance, SceneContinuityPending
    store = context['store']; store.verify_global()
    progress = collect_temporal_progress(context); templates = []
    for window in progress['records']:
        if window['status'] == 'awaiting_static':
            template = build_temporal_observation_template(context,window,scope='temporal_window_static')
            templates.append(str(store.write(store.clip_dir(window['budget']['clip_id'])/'observation-template.json',template)))
    for chain in progress['chains']:
        if chain['status'] == 'awaiting_chain_review':
            template = build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')
            templates.append(str(store.write(Path('chains')/chain['scene_id']/'observation-template.json',template)))
    status = 'awaiting_continuity_review' if templates else 'failed' if progress['status'] in ('failed','rejected') else 'blocked'
    error = None
    if progress['source_clips_ready']:
        value = complete_temporal_value(context,progress['records'])
        try: require_scene_continuity_acceptance(context['frozen'],context['units'],context['timeline'])
        except SceneContinuityPending as exc: status,error = 'awaiting_continuity_review',_error(exc)
        else:
            store.write('complete.json',value); status='source_clips_ready'
    return _result(store.run_dir,status,scenes=_scenes(context,progress),templates=templates,error=error)


def consume_temporal_observation(context, observation_path):
    store = context['store']; store.assert_owned()
    raw = Path(observation_path).read_bytes()
    if len(raw)>JSON_LIMIT: raise ProductionRefused('native observation exceeds JSON limit')
    value = strict_json(raw)
    progress = collect_temporal_progress(context)
    if value.get('scope') == 'temporal_window_static':
        record = next((window for window in progress['records'] if window['budget']['clip_id']==value.get('binding',{}).get('clip_id')),None)
        if record is None or 'result' not in record: raise ProductionRefused('native observation requires actual technical window')
        folder = store.clip_dir(record['budget']['clip_id']); terminal = ('static-accepted.json','static-rejected.json')
        algorithm = 'temporal_window_static_acceptance_v1'
    elif value.get('scope') == 'scene_temporal_chain_process':
        record = next((chain for chain in progress['chains'] if chain['scene_id']==value.get('binding',{}).get('scene_id')),None)
        if record is None or 'result' not in record: raise ProductionRefused('native observation requires complete assembled chain')
        folder = store.path(Path('chains')/record['scene_id']); terminal = ('accepted.json','rejected.json')
        algorithm = 'temporal_chain_acceptance_v1'
    else: raise ProductionRefused('unknown native observation scope')
    template = build_temporal_observation_template(context,record,scope=value['scope'])
    at = now()
    validate_temporal_observation(value,dict(template=template,created_at=record['created_at']),at)
    from .temporal_scene_observations import retained_temporal_observations
    for original in retained_temporal_observations(context,folder,template,record['created_at'],at):
        if original['verdict'] in ('acceptable','passed','rejected','failed') and canonical_digest(original)!=canonical_digest(value):
            raise ProductionRefused('retained native terminal observation cannot be replaced')
    for name in terminal:
        previous = store.read(folder/name)
        if previous is not None:
            old = strict_json(store.validate_artifact(previous['observation']).read_bytes())
            if canonical_digest(old) != canonical_digest(value): raise ProductionRefused('native terminal observation cannot be replaced')
            return finish_temporal_clips(context)
    original = store.write_bytes(folder/'observations'/(hashlib.sha256(raw).hexdigest()+'.json'),raw)
    store.verify_global()
    if value['verdict'] in ('acceptable','rejected','passed','failed'):
        accepted = value['verdict'] in ('acceptable','passed')
        receipt = dict(schema_version=1, algorithm=algorithm, result_sha256=record['result']['sha256'],
            template_sha256=canonical_digest(template), observation=store.artifact(original), verdict=value['verdict'], accepted_at=at)
        if value['scope']=='temporal_window_static':
            receipt.update(request_sha256=record['request_sha256'],allow_next_window=value['allow_next_window'])
        store.write(folder/terminal[0 if accepted else 1],receipt)
    return finish_temporal_clips(context)


def produce_temporal_clips(context, *, paths, logger, worker_factory=None):
    from .temporal_native_process import recover_or_start_native_window,recover_or_prepare_native_cache
    from .resources import GpuLease
    from .gpu_desktop import desktop_policy
    from .manifest import ManifestStore, create_manifest, hash_file
    from .production_scene_clips import _result,_error
    store = context['store']; store.verify_global()
    store.write('inputs.json',context['inputs'])
    progress = collect_temporal_progress(context)
    pending = [window for window in progress['records'] if window['status'] in ('pending','waiting_parent','sampled_decode_pending')]
    required = sum((4076863488 if window['budget']['ordinal']>1 else 0)+93*432*768*3*4 for window in pending)
    if pending and shutil.disk_usage(store.run_dir).free < 32*1024**3+required:
        raise ProductionRefused('insufficient real disk for all remaining native windows')
    lease = None
    try:
        parents = {}
        for row in context['rows']:
            budget = row['budget']; parent = parents.get(budget['parent_clip_id'])
            if budget['parent_clip_id'] is not None and (parent is None or parent['status']!='static_ready'): break
            window = validate_temporal_window(context,row,parent)
            if window['status']=='static_ready': parents[budget['clip_id']]=window; continue
            if window['status'] not in ('pending','sampled_decode_pending'): break
            selected = next(image for image in context['wan']['scenes'] if image['scene_id']==budget['scene_id'])
            prepared = prepare_native_input(store,row,selected,parent)
            request = expected_temporal_request(context,row,prepared,parent); workflow = temporal_workflow(context,row)
            folder = store.clip_dir(budget['clip_id'])
            store.write(folder/'workflow.json',workflow); store.write(folder/'request.json',request)
            if lease is None:
                manifest_path = store.run_dir/'manifest.json'
                manifest = (ManifestStore.open(store.run_dir,verify_integrity=False) if manifest_path.exists() else
                    create_manifest(store.run_dir,context['frozen'].config,inputs={'script':hash_file(Path(context['frozen'].options['script_path']))},models={},workflows={}))
                lease = GpuLease(paths,manifest,logger,resource_policy=desktop_policy).acquire('source_clips','temporal_extension_v1')
                store.gpu_lease = lease
            if window['status']=='pending':
                prepared_cache=recover_or_prepare_native_cache(store,request,workflow,worker_factory=worker_factory)
                if prepared_cache['status']!='prepared':
                    raise ProductionRefused('native prompt cache '+prepared_cache['status']+'; original cache job must be reconciled before video intent')
            recover_or_start_native_window(store,request,workflow,worker_factory=worker_factory)
            break  # The actual new contact sheet must be screened before any successor.
        progress = collect_temporal_progress(context)
        if progress['records'] and all(window['status']=='static_ready' for window in progress['records']):
            for scene in context['plan']['scenes']:
                assemble_temporal_chain(context,scene['scene_id'],[w for w in progress['records'] if w['budget']['scene_id']==scene['scene_id']])
        return finish_temporal_clips(context)
    except ProductionRefused: raise
    except Exception as exc: return _result(store.run_dir,'failed',error=_error(exc))
    finally:
        if lease is not None: lease.release()
