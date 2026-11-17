"""LVA-05 coordinator: frozen factor identity around original durable IDs."""
from dataclasses import asdict
from functools import lru_cache
import importlib.util
import json
import os
from pathlib import Path
import time
from uuid import UUID, uuid4

from .upscale_pipeline import PipelineConfig, UpscaleFrameJob, UpscalePipeline, _copy_output
from .wan_fast_profiles import Artifact, artifact, digest
from ..runtime.scene_stage_preparation import _read
from ..runtime.verification import whole_input_protection, writable_validation_session

SOURCE = Path(__file__).resolve().parents[3]
FACTORS = {'serial': PipelineConfig(), 'prefetch': PipelineConfig(prefetch=True),
           'writeback': PipelineConfig(writeback=True), 'pipeline': PipelineConfig(prefetch=True, writeback=True)}


@lru_cache(maxsize=1)
def baseline_api():
    spec = importlib.util.spec_from_file_location('_lva05_original', SOURCE/'scripts/benchmark_local_gpu.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def freeze_manifest(root, manifest):
    if manifest.get('task_id') != 'LVA-05' or manifest.get('factor') not in FACTORS:
        raise ValueError('LVA-05 factor manifest required')
    frames = manifest['frames']
    if [r['frame_id'] for r in frames] != list(range(1, len(frames)+1)) or not frames:
        raise ValueError('complete ordered source frames required')
    value = dict(manifest, pipeline_config=asdict(FACTORS[manifest['factor']]))
    # Admit complete identities once; native strong leases may reuse these hashes
    # inside one invocation. Weak platforms always rehash.
    for item in value['artifacts'].values(): Artifact(**item).verify()
    for row in frames: Artifact(**row['source']).verify()
    baseline_api().write_once(Path(root)/'frozen/manifest.json', value)
    return digest(value)


def frame_job(manifest, profile, row):
    raw = json.dumps(row['graph'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return UpscaleFrameJob(row['frame_id'], row['source'], raw, digest(manifest['parameters']), profile)


def input_path(root, graph):
    target=(root/'input'/graph['1']['inputs']['image']).resolve()
    if not target.is_relative_to(root/'input'):raise ValueError('input escapes owned directory')
    return target


def materialize_input(root, job, graph, prepared):
    """Coordinator consumes pre-read bytes instead of repeating the serial copy."""
    from threading import Event
    target=input_path(root,graph)
    expected=dict(job.source,path=str(target))
    if target.exists():Artifact(**expected).verify();return
    if prepared is None or prepared.error or prepared.job_key!=job.key:
        prepared=_read(job.preparation(),Event())
    if (prepared.error or prepared.actual_sha256!=job.source['sha256']
            or len(prepared.source_bytes)!=job.source['bytes']):
        raise ValueError('source read not proved')
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=target.parent/(target.name+'.'+uuid4().hex+'.part')
    with staging.open('xb') as stream:
        stream.write(prepared.source_bytes);stream.flush();os.fsync(stream.fileno())
    os.link(staging,target);staging.unlink()


class PipelineExperimentClient:
    def __init__(self, root, *, profile_sha256, port=8189, http=None):
        self.root, self.profile, self.port = Path(root).resolve(), profile_sha256, port
        self.api = baseline_api()
        self.delegate = self.api.ExperimentClient(self.root, port=port, http=self._http)
        self.transport, self.injected = http or self.delegate.http, http is not None
        self.metrics=dict(validation_calls=0,validation_seconds=0.,post=0,get=0)

    def verify(self):
        started=time.perf_counter()
        try:return self._verify()
        finally:
            self.metrics['validation_calls']+=1
            self.metrics['validation_seconds']+=time.perf_counter()-started

    def _verify(self):
        manifest = read(self.root/'frozen/manifest.json')
        if (digest(manifest) != self.profile or manifest.get('task_id') != 'LVA-05'
                or manifest.get('factor') not in FACTORS
                or manifest['pipeline_config'] != asdict(FACTORS[manifest['factor']])):
            raise ValueError('frozen experiment manifest drift')
        if 'root' in manifest and Path(manifest['root']).resolve()!=self.root:
            raise ValueError('frozen manifest root differs')
        for value in manifest['artifacts'].values(): Artifact(**value).verify()
        if not self.injected:
            owner = read(self.root/'service-owner.json')
            launch = read(self.root/'frozen/service-launch.json')
            if (owner.get('profile_sha256') != self.profile or launch.get('profile_sha256') != self.profile
                    or owner.get('launch_sha256') != digest(launch) or launch.get('port') != self.port):
                raise ValueError('owned service profile/launch drift')
            bound = self.root/'frozen/service-binding.json'
            if bound.exists():
                if read(bound) != owner: raise ValueError('original service owner changed')
            else:
                if list((self.root/'trials').glob('*/intent.json')):
                    raise ValueError('original service binding missing')
                self.api.write_once(bound, owner)
        return manifest

    def _http(self, method, route, payload=None):
        self.verify()
        job,graph=self._current
        Artifact(**dict(job.source,path=str(input_path(self.root,graph)))).verify()
        if not self.injected: self.delegate.assert_owned_service()
        self.metrics[method.lower()]+=1
        return self.transport(method, route, payload)

    def trial_id(self, job): return f'upscale_lva05_{job.frame_id:06d}'

    def bind(self, job, graph):
        manifest = self.verify()
        row = manifest['frames'][job.frame_id-1]
        if frame_job(manifest, self.profile, row).key != job.key or graph != row['graph']:
            raise ValueError('current frame/source/graph identity differs')
        Artifact(**job.source).verify()
        self._current=(job,graph)
        value = dict(profile_sha256=self.profile, job_key=list(job.key), graph_sha256=digest(graph))
        folder = self.root/'trials'/self.trial_id(job)
        binding = folder/'profile-binding.json'
        if (folder/'intent.json').exists() and not binding.exists():
            raise ValueError('original intent lacks profile binding')
        self.api.write_once(binding, value)
        return folder

    def original(self, job, graph):
        """Validate exact locally persisted history; never infer from a PNG."""
        folder = self.bind(job, graph)
        if not (folder/'history.completed.json').exists(): return None
        intent, accepted = read(folder/'intent.json'), read(folder/'accepted.json')
        pid = accepted['prompt_id']; history = read(folder/'history.completed.json')
        if str(UUID(pid)) != pid: raise ValueError('original accepted ID invalid')
        entry = history.get(pid, {}); prompt = entry.get('prompt', [])
        if (intent['graph'] != graph or intent['graph_sha256'] != digest(graph)
                or len(prompt) < 4 or prompt[2] != graph
                or prompt[3].get('client_id') != intent['client_id']
                or entry.get('status', {}).get('completed') is not True
                or entry['status'].get('status_str') == 'error'):
            raise ValueError('original completion graph/client/status differs')
        images = entry.get('outputs', {}).get('5', {}).get('images', [])
        if len(images) != 1 or images[0].get('type') != 'output': raise ValueError('one original PNG required')
        item = images[0]
        output = (self.root/'output'/item.get('subfolder', '')/item['filename']).resolve(strict=True)
        if not output.is_relative_to(self.root/'output'): raise ValueError('output escapes original root')
        return output, pid, dict(intent_sha256=digest(intent), accepted_sha256=digest(accepted), history_sha256=digest(history))

    def wait(self, job, graph):
        folder = self.bind(job, graph)
        original = self.original(job, graph)
        if original is None:
            self.delegate.wait(self.trial_id(job), graph, output_node='5', timeout=600, poll_seconds=.15)
            original = self.original(job, graph)
        if original is None: raise ValueError('durable original completion required')
        return original


def run_frames(root, *, profile_sha256, port=8189, http=None, pixel_proof=None, checkpoint=None):
    """Single GPU request coordinator; overlap at most the preceding PNG copy."""
    from threading import Event
    from ..media.scene_upscale import _check_png, png_sequence_hashes
    from ..config import load_config
    root = Path(root).resolve()
    client = PipelineExperimentClient(root, profile_sha256=profile_sha256, port=port, http=http)
    check = checkpoint or (lambda event, index: None)
    with whole_input_protection(immutable_roots=()), writable_validation_session(root):
        manifest = client.verify(); config = FACTORS[manifest['factor']]
        width, height = manifest['parameters']['width'], manifest['parameters']['height']
        jobs = [frame_job(manifest, profile_sha256, row) for row in manifest['frames']]
        frames = root/'frames'; frames.mkdir(exist_ok=True)
        pool = UpscalePipeline(config); rows=[]; pending=None; tracked=0.; io=0.; resumed=0;recovered=0
        input_seconds=0.;timings=[]
        files={str(p):p.stat().st_size for folder in ('input','output','private','frames')
               if (root/folder).exists() for p in (root/folder).rglob('*') if p.is_file()}
        disk_peak=sum(files.values())
        started=time.perf_counter(); failure=None

        def storage(path,size):
            nonlocal disk_peak
            files[str(path)]=size;disk_peak=max(disk_peak,sum(files.values()))

        def receipt_path(job): return root/'receipts'/f'frame_{job.frame_id:06d}.json'

        def capture(job, graph, original):
            output, pid, identity = original
            # Model output is captured only after original durable history exists.
            _check_png(output, width=width, height=height)
            value = dict(profile_sha256=profile_sha256, job_key=list(job.key), prompt_id=pid,
                         captured=artifact(output).identity_dict(), **identity)
            client.verify()
            client.api.write_once(root/'trials'/client.trial_id(job)/'captured.json', value)
            storage(output,value['captured']['bytes'])
            return value

        def validate_row(job, graph, row):
            original=client.original(job,graph)
            if original is None: raise ValueError('frame receipt missing original history')
            captured=read(root/'trials'/client.trial_id(job)/'captured.json')
            if (row.get('profile_sha256') != profile_sha256 or row.get('job_key') != list(job.key)
                    or row.get('completion') != captured or captured['prompt_id'] != original[1]
                    or any(captured[k] != v for k,v in original[2].items())
                    or captured['captured']['path'] != str(original[0])):
                raise ValueError('frame receipt original binding differs')
            Artifact(**captured['captured']).verify()
            expected=frames/f'frame_{job.frame_id:06d}.png'
            if row['artifact']['path'] != str(expected) or row['artifact']['sha256'] != captured['captured']['sha256']:
                raise ValueError('frame receipt target differs')
            Artifact(**row['artifact']).verify()
            return row

        def promote(job, captured, staged):
            nonlocal io
            before=time.perf_counter()
            if staged.error: raise ValueError('private staging not proved: '+staged.error)
            client.verify(); Artifact(**dict(staged.artifact)).verify()
            Artifact(**job.source).verify(); Artifact(**captured['captured']).verify()
            if staged.job_key != job.key or staged.artifact['sha256'] != captured['captured']['sha256']:
                raise ValueError('private staging identity differs')
            _check_png(staged.artifact['path'], width=width, height=height)
            storage(staged.artifact['path'],staged.artifact['bytes'])
            check('staged',job.frame_id)
            target=frames/f'frame_{job.frame_id:06d}.png'
            if target.exists():
                current=artifact(target).identity_dict()
                if (current['sha256'],current['bytes']) != (staged.artifact['sha256'],staged.artifact['bytes']):
                    raise ValueError('uncommitted promoted target differs from original output')
            else:
                # Atomic create without replacing a conflicting existing target.
                os.link(staged.artifact['path'], target)
            storage(target,staged.artifact['bytes'])
            Path(staged.artifact['path']).unlink()
            files.pop(staged.artifact['path'],None)
            check('promoted',job.frame_id)
            value=dict(profile_sha256=profile_sha256, job_key=list(job.key), completion=captured,
                       artifact=dict(staged.artifact, path=str(target)))
            client.verify();client.api.write_once(receipt_path(job), value)
            check('receipt',job.frame_id);io+=time.perf_counter()-before
            for timing in timings:
                if timing['frame_id']==job.frame_id:
                    timing['coordinator_complete_offset_seconds']=time.perf_counter()-started
            rows.append(value)

        def drain():
            nonlocal pending
            if pending is None:return
            job,captured=pending
            until=time.monotonic()+120
            while True:
                result=pool.finish_output(job)
                if result is not None:break
                if time.monotonic()>until:raise TimeoutError('bounded writeback drain timed out')
                time.sleep(.002)
            promote(job,captured,result);pending=None

        try:
            # Fully completed replay validates persisted identities/bytes but does
            # no HTTP or local media production/decode.
            complete=root/'upscale-complete.json'
            if complete.exists():
                value=read(complete)
                if value['profile_sha256'] != profile_sha256 or value['frame_count'] != len(jobs):
                    raise ValueError('completed batch identity differs')
                for job,row in zip(jobs,value['frames'],strict=True):
                    graph=manifest['frames'][job.frame_id-1]['graph']
                    if read(receipt_path(job)) != row:raise ValueError('completed frame receipt changed')
                    validate_row(job,graph,row)
                return value
            for index,job in enumerate(jobs):
                graph=manifest['frames'][index]['graph']
                receipt=receipt_path(job)
                if receipt.exists():
                    drain();rows.append(validate_row(job,graph,read(receipt)));resumed+=1;continue
                prepared=pool.consume(job)
                if prepared is not None and prepared.error is None: graph=json.loads(prepared.graph_bytes)
                else:pool.discard_prefetch()
                input_started=time.perf_counter();materialize_input(root,job,graph,prepared)
                input_seconds+=time.perf_counter()-input_started
                storage(input_path(root,graph),job.source['bytes'])
                del prepared
                client.bind(job,graph)
                current_trial=manifest['frames'][index].get('trial')
                next_trial=manifest['frames'][index+1].get('trial') if index+1<len(jobs) else None
                if index+1<len(jobs) and current_trial==next_trial:pool.prepare(jobs[index+1])
                # One wait at a time: at most previous write overlaps this GPU.
                recovering=(root/'trials'/client.trial_id(job)/'intent.json').exists()
                recovered+=int(recovering)
                before=time.perf_counter();started_at=time.time();original=client.wait(job,graph)
                seconds=time.perf_counter()-before;tracked+=seconds
                timings.append(dict(frame_id=job.frame_id,trial=manifest['frames'][index].get('trial'),
                    prompt_id=original[1],started_at_unix=started_at,tracking_start_offset_seconds=before-started,tracking_invocation_seconds=seconds,
                    submit_and_tracking_seconds=None if recovering else seconds,mode='recovery' if recovering else 'normal'))
                check('history',job.frame_id)
                captured=capture(job,graph,original);check('captured',job.frame_id)
                # Drain predecessor before reserving any further writeback slot.
                drain()
                staging=root/'private'/f'frame_{job.frame_id:06d}-{uuid4().hex}.part'
                if pool.stage_output(job,captured['captured'],staging):pending=(job,captured)
                else:promote(job,captured,_copy_output(job,captured['captured'],staging,Event()))
                if current_trial!=next_trial:drain()
            drain()
            rows.sort(key=lambda row:row['job_key'][0])
            client.verify()
            if pixel_proof is None:
                config_tools=load_config(SOURCE/'config/production.example.json')
                pixel_proof=lambda paths,**kw:png_sequence_hashes(paths,config=config_tools,**kw)
            pixels=pixel_proof([r['artifact']['path'] for r in rows],width=width,height=height)
            if len(pixels)!=len(jobs): raise ValueError('complete RGB frame count differs')
            value=dict(profile_sha256=profile_sha256,factor=manifest['factor'],frames=rows,
                frame_count=len(jobs),frame_rgb_sha256=pixels,width=width,height=height,
                wall_seconds=time.perf_counter()-started,tracking_seconds=tracked,coordinator_io_seconds=io,
                resumed_frames=resumed,recovered_intents=recovered,mode='recovery' if resumed or recovered else 'normal',
                submit_and_tracking_seconds=None if resumed or recovered else tracked,
                input_materialization_seconds=input_seconds,frame_timings=timings,verification=dict(client.metrics),
                disk=dict(peak_logical_file_bytes=disk_peak,current_logical_file_bytes=sum(files.values()),
                    files=len(files),scope='Actual known input/raw/private/accepted file lengths at coordinator transitions; hardlink paths counted separately.'),
                quality_status='awaiting_human_review',pipeline=pool.report())
            client.verify();client.api.write_once(complete,value)
            return value
        except BaseException as exc:failure=exc;raise
        finally:
            try:pool.close()
            except Exception as exc:
                if failure is None:raise
                failure.add_note('pipeline close failed: '+type(exc).__name__)
            try:
                client.api.write_once(root/'invocations'/(uuid4().hex+'.json'),dict(
                    profile_sha256=profile_sha256,exception_type=type(failure).__name__ if failure else None,
                    wall_seconds=time.perf_counter()-started,pipeline=pool.report(),verification=dict(client.metrics)))
            except Exception as exc:
                if failure is None:raise
                failure.add_note('invocation diagnostic failed: '+type(exc).__name__)
