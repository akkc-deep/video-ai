"""Fixed-input LVA-01 experiments in a NEW authorized, owned Comfy directory.

Raw frozen requests stay local. Summaries never contain prompt text. Durable
intents/accepted IDs survive interruption; an unknown POST is never repeated.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from video_ai.runtime.paths import RUNTIME_ROOT


class OutcomeUnknown(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_once(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError('immutable experiment evidence differs: '+path.name)
        return
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
        stream.flush(); os.fsync(stream.fileno())


def rebind_graph(graph, image, prefix):
    result = deepcopy(graph)
    result['97']['inputs']['image'] = image
    result['108']['inputs']['filename_prefix'] = prefix
    return result


def prepare(root, source_folder, fixture_id):
    root, source_folder = Path(root), Path(source_folder)
    directory = root/'frozen'; directory.mkdir(exist_ok=False)
    original = read(source_folder/'request.json')
    graph = read(source_folder/'graph.json')
    # Existing canonical graph digests use repository JSON serialization.
    from video_ai.planning.production_scenes import canonical_digest
    if canonical_digest(graph) != original['graph_sha256']:
        raise ValueError('source graph does not match original request')
    parameters = original['parameters']
    if parameters['steps'] != 40 or parameters['cfg'] != 3.5 or parameters['lora_enabled']:
        raise ValueError('original 40-step quality request required')
    input_record = read(source_folder/'input.json')
    image = Path(input_record['target']['path'])
    image_bytes = image.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != input_record['target']['sha256']:
        raise ValueError('selected native input differs from recorded content')
    target = root/'input'/fixture_id/'start.png'; target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(image_bytes); stream.flush(); os.fsync(stream.fileno())
    (directory/'original-request.json').write_bytes((source_folder/'request.json').read_bytes())
    (directory/'original-graph.json').write_bytes((source_folder/'graph.json').read_bytes())
    # Preserve a selected-image identity, not private prompt text, in the summary.
    fixture = dict(schema_version=1, fixture_id=fixture_id, source_clip_id=original['clip_id'],
        source_request_sha256=file_sha(source_folder/'request.json'), source_graph_sha256=original['graph_sha256'],
        input_relative=str(target.relative_to(root/'input')).replace('\\', '/'), input_sha256=hashlib.sha256(image_bytes).hexdigest(),
        selected_image_sha256=original['selected_image']['sha256'], prompt_sha256=digest(dict(positive=parameters['positive'], negative=parameters['negative'])),
        budget=original['budget'], parameters={k: v for k, v in parameters.items() if k not in ('positive', 'negative')},
        requires_new_parent=original['parent'] is not None,
        source_observation_accepted=(source_folder/'observation-accepted.json').exists())
    write_once(root/'fixture.json', fixture)
    return fixture


class ExperimentClient:
    def __init__(self, root, *, port=8189, http=None):
        self.root, self.port = Path(root), port
        marker = self.root/'experiment.json'
        if marker.exists() and read(marker)['port'] != port:
            raise ValueError('requested port differs from original experiment port')
        self._http = http or self.http

    def assert_owned_service(self):
        from video_ai.runtime.production_state import process_started_at
        from video_ai.experiments.whole_scene_runner import _listener_owned
        marker, owner = read(self.root/'experiment.json'), read(self.root/'service-owner.json')
        if (marker['port'] != self.port or owner['port'] != self.port
                or Path(owner['experiment_root']).resolve() != self.root.resolve()
                or process_started_at(owner['pid']) != owner['process_started_at']):
            raise OutcomeUnknown('owned experimental service identity differs; no POST')
        _listener_owned(self.port, owner['pid'])

    def http(self, method, route, payload=None):
        if method == 'POST':
            self.assert_owned_service()
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if payload is not None else None
        request = Request(f'http://127.0.0.1:{self.port}'+route, data=body, method=method,
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with urlopen(request, timeout=45) as response:
                raw=response.read(32*1024*1024)
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            value = json.loads(exc.read(32*1024*1024))
            raise RuntimeError('Comfy rejected experiment request; no retry: '+str(exc.code)) from exc

    def submit(self, trial_id, graph):
        folder = self.root/'trials'/trial_id
        folder.mkdir(parents=True, exist_ok=True)
        intent_path = folder/'intent.json'
        fresh = not intent_path.exists()
        if fresh:
            intent = dict(client_id=str(uuid4()), graph_sha256=digest(graph), graph=graph)
            write_once(intent_path, intent)
        else:
            intent = read(intent_path)
            if intent['graph_sha256'] != digest(graph):
                raise ValueError('experiment graph drift on resume')
        accepted = folder/'accepted.json'
        if accepted.exists():
            return read(accepted)['prompt_id']
        post = folder/'post.response.json'
        if fresh:
            value = self._http('POST', '/prompt', dict(prompt=graph, client_id=intent['client_id']))
            write_once(post, value)
        elif not post.exists():
            candidates = set()
            history = self._http('GET', '/history')
            for pid, entry in history.items():
                row = entry.get('prompt', [])
                if len(row) > 3 and row[2] == graph and row[3].get('client_id') == intent['client_id']:
                    candidates.add(pid)
            queue = self._http('GET', '/queue')
            for key in ('queue_running', 'queue_pending'):
                for row in queue.get(key, []):
                    if len(row) > 3 and row[2] == graph and row[3].get('client_id') == intent['client_id']:
                        candidates.add(row[1])
            if len(candidates) != 1:
                raise OutcomeUnknown('original experiment outcome unknown; no re-POST')
            pid = candidates.pop()
            write_once(accepted, dict(prompt_id=pid, recovered=True))
            return pid
        else:
            value = read(post)
        pid = value.get('prompt_id')
        if not isinstance(pid, str) or str(UUID(pid)) != pid or value.get('node_errors') != {}:
            raise OutcomeUnknown('original POST has no unique valid acceptance; no re-POST')
        write_once(accepted, dict(prompt_id=pid, recovered=False))
        return pid

    def wait(self, trial_id, graph, *, timeout=7200, output_node='108', poll_seconds=3):
        folder = self.root/'trials'/trial_id
        pid = self.submit(trial_id, graph)
        intent = read(folder/'intent.json')
        started = time.monotonic()
        while time.monotonic()-started < timeout:
            history = self._http('GET', '/history/'+pid)
            entry = history.get(pid)
            if entry is not None:
                row = entry.get('prompt', [])
                if len(row) < 4 or row[2] != graph or row[3].get('client_id') != intent['client_id']:
                    raise OutcomeUnknown('original history graph/client differs')
                status = entry.get('status', {})
                if status.get('status_str') == 'error':
                    write_once(folder/'history.failed.json', history)
                    raise RuntimeError('original experiment execution failed; retained, no new POST')
                if status.get('completed'):
                    outputs = entry.get('outputs', {}).get(output_node, {}).get('images', [])
                    if len(outputs) != 1 or outputs[0].get('type') != 'output':
                        raise ValueError('one owned completed output required')
                    target = (self.root/'output'/outputs[0].get('subfolder', '')/outputs[0]['filename']).resolve()
                    if not target.is_relative_to((self.root/'output').resolve()) or not target.is_file():
                        raise ValueError('completed output escapes experiment or is missing')
                    write_once(folder/'history.completed.json', history)
                    return target, pid
            time.sleep(poll_seconds)
        raise OutcomeUnknown('original experiment tracking timeout; resume original ID only')


def media_command(root, name, argv, *, source_sha256=None, output=None):
    started = time.perf_counter()
    result = subprocess.run(list(map(str, argv)), capture_output=True, timeout=600, shell=False)
    evidence = root/'media-commands'; evidence.mkdir(exist_ok=True)
    token = name+'-'+uuid4().hex[:8]
    (evidence/(token+'.stdout')).write_bytes(result.stdout)
    (evidence/(token+'.stderr')).write_bytes(result.stderr)
    receipt = dict(args=list(map(str, argv)), returncode=result.returncode,
        seconds=time.perf_counter()-started, source_sha256=source_sha256)
    if not result.returncode and output is not None:
        receipt['output'] = dict(path=str(output), sha256=file_sha(output))
        write_once(Path(str(output)+'.produced.json'), receipt)
    write_once(evidence/(token+'.json'), receipt)
    if result.returncode:
        raise RuntimeError('experiment media command failed: '+token)
    return result.stdout


def require_partial_receipt(target, argv, source_sha256):
    receipt = Path(str(target)+'.produced.json')
    if not receipt.exists():
        raise OutcomeUnknown('partial media lacks completed owned producer receipt; no automatic overwrite')
    value = read(receipt)
    if (value['returncode'] != 0 or value['source_sha256'] != source_sha256
            or value['args'] != list(map(str, argv)) or value['output']['sha256'] != file_sha(target)):
        raise ValueError('existing partial media producer/source/content differs')


def validate_completed(result):
    for key in ('generated', 'retained', 'last_frame'):
        if file_sha(result[key]) != result[key+'_sha256']:
            raise ValueError('completed experiment '+key+' media changed')


def inspect_media(root, source, *, width, height, expected_frames, ffmpeg, ffprobe):
    from video_ai.media.video import validate_video_probe
    probe = media_command(root, 'probe', [ffprobe, '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', source])
    frames = media_command(root, 'frames', [ffprobe, '-v', 'error', '-show_frames', '-of', 'json', source])
    info = validate_video_probe(json.loads(probe), json.loads(frames), width=width, height=height)
    if info['frames'] != expected_frames:
        raise ValueError('complete generated/retained frame budget differs')
    media_command(root, 'decode', [ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', source, '-f', 'null', '-'])
    return info


def prepare_child(root, source_folder):
    root, source_folder = Path(root), Path(source_folder)
    req = read(source_folder/'request.json'); graph = read(source_folder/'graph.json')
    from video_ai.planning.production_scenes import canonical_digest
    if req['parent'] is None or canonical_digest(graph) != req['graph_sha256']:
        raise ValueError('bound original child graph required')
    p = req['parameters']
    if p['steps'] != 40 or p['cfg'] != 3.5 or p['lora_enabled']:
        raise ValueError('original child quality parameters required')
    parent = read(root/'fixture.json')
    if req['budget']['parent_clip_id'] != parent['source_clip_id']:
        raise ValueError('child does not continue this fixture parent')
    write_once(root/'frozen/child-original-request.json', req)
    write_once(root/'frozen/child-original-graph.json', graph)
    fixture = dict(schema_version=1, fixture_id='parent_child', source_clip_id=req['clip_id'],
        source_graph_sha256=req['graph_sha256'], graph_file='child-original-graph.json',
        selected_image_sha256=req['selected_image']['sha256'], budget=req['budget'],
        parameters={k:v for k,v in p.items() if k not in ('positive','negative')}, requires_new_parent=True)
    write_once(root/'child-fixture.json', fixture)
    return fixture


def run_child_trial(root, parent_trial_id, *, port=8189, parent_root=None):
    root = Path(root); parent_root=Path(parent_root) if parent_root is not None else root
    parent_folder = parent_root/'trials'/parent_trial_id
    parent = read(parent_folder/'technical-complete.json')
    approval = parent_folder/'observation-accepted.json'
    if not approval.exists():
        raise ValueError('new parent video requires explicit human acceptance before child submission')
    accepted = read(approval)
    if (accepted.get('decision') != 'accepted' or
            any(accepted.get(key+'_sha256') != parent[key+'_sha256'] for key in ('generated','retained','last_frame'))):
        raise ValueError('human acceptance does not bind these exact parent media')
    validate_completed(parent)
    fixture = read(parent_root/'child-fixture.json')
    if parent_root.resolve()!=root.resolve():
        for name in ('child-original-request.json','child-original-graph.json'):
            write_once(root/'frozen'/name,read(parent_root/'frozen'/name))
        write_once(root/'frozen/original-request.json',read(parent_root/'frozen/child-original-request.json'))
        write_once(root/'child-fixture.json',fixture)
        write_once(root/'fixture.json',dict(fixture,input_sha256=None,input_relative=None,
            input_policy='Per-trial exact accepted new-parent retained last PNG'))
        if (parent_root/'narration-source.json').exists():
            narration_source=read(parent_root/'narration-source.json')
            narration_source['original_request_sha256']=file_sha(root/'frozen/original-request.json')
            write_once(root/'narration-source.json',narration_source)
        if (parent_root/'render-font.json').exists():
            write_once(root/'render-font.json',read(parent_root/'render-font.json'))
    child_id = parent_trial_id+'_child'
    image = root/'input/parent_child'/child_id/'start.png'
    image.parent.mkdir(parents=True, exist_ok=True)
    if image.exists():
        if file_sha(image) != parent['last_frame_sha256']:
            raise ValueError('new child input differs from accepted parent last frame')
    else:
        with image.open('xb') as stream:
            stream.write(Path(parent['last_frame']).read_bytes()); stream.flush(); os.fsync(stream.fileno())
    binding = dict(parent_root=str(parent_root),parent_trial=parent_trial_id, parent_generated_sha256=parent['generated_sha256'],
        parent_last_frame_sha256=parent['last_frame_sha256'], human_acceptance_sha256=file_sha(approval),
        input_relative=str(image.relative_to(root/'input')).replace('\\','/'))
    write_once(root/'trials'/child_id/'parent-binding.json', binding)
    fixture.update(input_relative=binding['input_relative'], input_sha256=parent['last_frame_sha256'],
                   requires_new_parent=False, parent_binding=binding)
    return run_trial(root, child_id, port=port, fixture_override=fixture)


def original_quality_graph(root, fixture, prepared=None):
    original = (read(Path(root)/'frozen'/fixture.get('graph_file','original-graph.json'))
                if prepared is None else deepcopy(prepared))
    from video_ai.planning.production_scenes import canonical_digest
    if canonical_digest(original) != fixture['source_graph_sha256']:
        raise ValueError('frozen original quality graph drift')
    return original


def run_trial(root, trial_id, *, port=8189, fixture_override=None, prepared_original_graph=None):
    root = Path(root)
    fixture = fixture_override or read(root/'fixture.json')
    if fixture['requires_new_parent']:
        raise ValueError('child fixture requires a newly accepted parent binding; standalone submission forbidden')
    folder = root/'trials'/trial_id
    complete = folder/'technical-complete.json'
    if complete.exists():
        result = read(complete)
        validate_completed(result)
        return result
    image = root/'input'/fixture['input_relative']
    if file_sha(image) != fixture['input_sha256']:
        raise ValueError('frozen experimental input changed')
    original_graph = original_quality_graph(root,fixture,prepared_original_graph)
    graph = rebind_graph(original_graph, fixture['input_relative'], fixture['fixture_id']+'/'+trial_id)
    recovering = (folder/'intent.json').exists()
    origin = folder/'timing-origin.json'
    if not origin.exists() and not recovering:
        write_once(origin, dict(started_at_unix=time.time(), mode='normal'))
    started_at, start = time.time(), time.perf_counter()
    client = ExperimentClient(root, port=port)
    generated, pid = client.wait(trial_id, graph)
    gpu_done = time.perf_counter()
    from video_ai.config import load_config
    config = load_config(Path(__file__).resolve().parents[1]/'config/production.example.json')
    ffmpeg, ffprobe = config.tools['ffmpeg'], config.tools['ffprobe']
    p, b = fixture['parameters'], fixture['budget']
    generated_sha256 = file_sha(generated)
    inspect_media(root, generated, width=p['width'], height=p['height'], expected_frames=b['generated_frames'], ffmpeg=ffmpeg, ffprobe=ffprobe)
    retained = folder/'retained.mp4'
    trim_args = [ffmpeg, '-nostdin', '-n', '-v', 'error', '-xerror', '-i', generated,
        '-map', '0:v:0', '-vf', f'trim=start_frame={b["retained_source_start"]}:end_frame={b["retained_source_end"]},setpts=N/(16*TB)',
        '-an', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-fps_mode', 'passthrough', retained]
    if not retained.exists():
        media_command(root, 'trim', trim_args, source_sha256=generated_sha256, output=retained)
    else:
        require_partial_receipt(retained, trim_args, generated_sha256)
    inspect_media(root, retained, width=p['width'], height=p['height'], expected_frames=b['retained_frames'], ffmpeg=ffmpeg, ffprobe=ffprobe)
    last = folder/f'frame_{b["retained_source_end"]:06d}.png'
    last_args = [ffmpeg, '-nostdin', '-n', '-v', 'error', '-xerror', '-i', generated,
        '-map', '0:v:0', '-vf', f'select=eq(n\\,{b["retained_source_end"]-1}),format=rgb24',
        '-frames:v', '1', '-fps_mode', 'passthrough', last]
    if not last.exists():
        media_command(root, 'last-frame', last_args, source_sha256=generated_sha256, output=last)
    else:
        require_partial_receipt(last, last_args, generated_sha256)
    from video_ai.media.scene_upscale import _check_png
    _check_png(last, width=p['width'], height=p['height'])
    result = dict(schema_version=1, trial_id=trial_id, fixture_id=fixture['fixture_id'], prompt_id=pid,
        graph_sha256=digest(graph), input_sha256=fixture['input_sha256'], started_at_unix=started_at,
        mode='recovery' if recovering else 'normal',
        submit_to_output_seconds=None if recovering else gpu_done-start, technical_seconds=time.perf_counter()-gpu_done,
        wall_seconds=None if recovering else time.perf_counter()-start,
        tracking_invocation_seconds=time.perf_counter()-start,
        original_timing_origin=read(origin) if origin.exists() else None,
        generated=str(generated), generated_sha256=generated_sha256,
        retained=str(retained), retained_sha256=file_sha(retained), last_frame=str(last), last_frame_sha256=file_sha(last),
        generated_frames=b['generated_frames'], retained_frames=b['retained_frames'], quality_status='awaiting_human_review',
        usable_video_seconds=None, temperature='cold' if trial_id.startswith('cold_1') else 'warm_process',
        limitations='Node wall time, device-wide sampled VRAM; model residency and quality require evidence, not labels.')
    write_once(complete, result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'prepare-child', 'run', 'run-child'))
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--source-folder', type=Path)
    parser.add_argument('--fixture-id', choices=('low_motion', 'high_motion', 'parent_child'))
    parser.add_argument('--trial', choices=('cold_1', 'warm_1', 'warm_2', 'warm_3', 'all'), default='all')
    parser.add_argument('--port', type=int, default=8189)
    parser.add_argument('--parent-root',type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or not (root/'experiment.json').is_file():
        parser.error('existing NEW experiment launcher root required, never a production run')
    if args.parent_root is not None:
        parent_root=args.parent_root.resolve()
        if not parent_root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or not (parent_root/'experiment.json').is_file():
            parser.error('parent-root must be an existing NEW experiment, never old production')
    if args.action == 'prepare-child':
        if args.source_folder is None:
            parser.error('child source-folder required')
        print(json.dumps(prepare_child(root,args.source_folder),ensure_ascii=False),flush=True)
    elif args.action == 'prepare':
        if args.source_folder is None or args.fixture_id is None:
            parser.error('source-folder and fixture-id required')
        print(json.dumps(prepare(root, args.source_folder, args.fixture_id), ensure_ascii=False), flush=True)
    else:
        if not (root/'system-stats.json').exists():
            write_once(root/'system-stats.json', ExperimentClient(root, port=args.port)._http('GET', '/system_stats'))
        for trial in ('cold_1', 'warm_1', 'warm_2', 'warm_3') if args.trial=='all' else (args.trial,):
            if args.action == 'run-child':
                run_child_trial(root, trial, port=args.port,parent_root=args.parent_root)
            else:
                run_trial(root, trial, port=args.port)


if __name__ == '__main__':
    main()
