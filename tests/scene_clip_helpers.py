"""Authentic admitted images and caller-created native media for offline Wan tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import get_ident
from uuid import uuid4
import wave

from image_selection_helpers import save


def prepared_wan(runtime_run, tmp_path, monkeypatch, *, long_scene=False, original_format='png', model_patch=None):
    from integration.test_jimeng_reference_flow import (
        prepared_baseline, configured_cloud, produce, accept_reference_batch)
    import video_ai.planning.production_timeline as timeline_module
    from video_ai.runtime.production_state import ArtifactStamp
    from video_ai.runtime.manifest import thaw
    from video_ai.config import load_config
    original = timeline_module.build_production_timeline
    run = runtime_run[0]
    config = runtime_run[1]; raw = thaw(config.raw)
    from offline_scene_models import model_inputs
    raw['models']=model_inputs(config,model_patch if model_patch is not None else monkeypatch)
    raw.update(voice_config=str(config.voice.config_file), workflows=thaw(config.workflows))
    raw['media']['timeline'] = dict(sentence_pause_seconds=.02,paragraph_pause_seconds=.04,
                                  opening_seconds=.03,closing_seconds=.01)
    config_path = save(run/'scene-fixture-config.json',raw)
    runtime_run = (run,load_config(config_path),runtime_run[2])
    def actual_pcm(script, audio, **kwargs):
        if all(info.stamp.path != 'D:/pcm.wav' for info in audio.values()):
            return original(script, audio, **kwargs)
        first = original(script, audio, **kwargs)
        samples = [c.samples for c in first.clips]
        if long_scene:
            extra = 600000-first.clips[2].start_sample
            samples[0] += extra//2; samples[1] += extra-extra//2
        changed = {}
        for clip, count in zip(first.clips, samples):
            path = run/'audio'/clip.unit_id/'pcm.wav'; path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 48000, 0, 'NONE', '')); stream.writeframes(b'\0\0'*count)
            changed[clip.unit_id] = replace(audio[clip.unit_id], stamp=ArtifactStamp.read(path), samples=count)
        return original(script, changed, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(timeline_module, 'build_production_timeline', actual_pcm)
        setup = prepared_baseline(runtime_run, tmp_path, original_format=original_format)
    cloud, smtp, kwargs = configured_cloud(setup, monkeypatch)
    pending = produce(setup, **kwargs)
    assert pending.status == 'awaiting_image_selection', pending.error
    accepted = accept_reference_batch(setup, pending, observation=True)
    assert accepted.all_images_accepted, accepted.error
    assert produce(setup, **kwargs).status == 'images_ready'
    setup.update(reference_cloud=cloud, reference_smtp=smtp)
    if long_scene:
        assert setup['plan']['scenes'][0]['end_frame'] == 200
        assert [c['retained_frames'] for c in setup['plan']['clips'][:3]] == [93,92,15]
    return setup


class OfflineWan:
    """Memory HTTP responses; all synthetic outputs are built on the caller thread."""
    def __init__(self, setup):
        from unit.test_workflows import remote_info
        from video_ai.runtime.workflows import WorkflowTemplate
        self.setup = setup; self.posts = []; self.gets = []; self.history_entries = {}
        self.ensures = 0; self.closes = 0; self.factories = 0; self.owner = get_ident()
        self.mode = 'normal'; self.before_send = None
        self.template = WorkflowTemplate.load(
            Path(setup['frozen'].options['workflow_snapshots']['wan']['path']),
            Path(setup['frozen'].options['workflow_snapshots']['wan_mapping']['path']), setup['frozen'].config.models)
        self.remote_info = remote_info(self.template)
        self.outputs = {}
        for budget in setup['plan']['clips']:
            cid = budget['clip_id']; prefix = f'{setup["run"].name}/scene_clips/{cid}/attempt_0001'
            target = setup['run']/'comfy/output'/(prefix+'_00001.mp4')
            target.parent.mkdir(parents=True, exist_ok=True)
            self._create_video(target, budget['generated_frames'])
            self.outputs[cid] = target

    def _create_video(self, target, frames):
        from video_ai.runtime.environment import build_child_env
        from video_ai.runtime.processes import run_logged
        assert get_ident() == self.owner
        s = self.setup; profile = s['frozen'].config.media.profile
        args = [s['frozen'].config.tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-f', 'lavfi',
            '-i', f'testsrc2=size={profile.width}x{profile.height}:rate=16', '-frames:v', str(frames),
            '-an', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-fps_mode', 'passthrough', target]
        result = run_logged(tuple(map(str,args)), cwd=s['run'], env=build_child_env(s['paths']), timeout=60,
            logger=s['logger'], stage='test_fixture', unit_id='scene-media')
        assert result.returncode == 0 and not result.timed_out, result.stderr_path.read_text()

    @staticmethod
    def response(value, status=200):
        return dict(status=status, headers={'Content-Type':'application/json'},
                    body=json.dumps(value, ensure_ascii=False, allow_nan=False).encode())

    def factory(self, base_url, *, request_timeout, ownership_check):
        assert get_ident() == self.owner
        self.factories += 1
        backend = self
        class Client:
            def __init__(self): self.ownership_check = ownership_check
            def object_info(self, *, timeout):
                self.ownership_check(); backend.gets.append('/object_info')
                return backend.response(backend.remote_info)
            def system_stats(self, *, timeout):
                self.ownership_check(); backend.gets.append('/system_stats'); return backend.response({})
            def submit(self, graph, *, client_id, timeout):
                if backend.before_send: backend.before_send(graph)
                self.ownership_check(); assert get_ident() == backend.owner
                prefix = graph['108']['inputs']['filename_prefix']; cid = Path(prefix).parent.name
                target = backend.outputs[cid]
                pid = str(uuid4()); number = len(backend.posts)+1
                backend.posts.append(dict(prompt=deepcopy(graph), client_id=client_id))
                backend.history_entries[pid] = dict(prompt=[number,pid,deepcopy(graph),dict(client_id=client_id),['108']],
                    status=dict(status_str='success',completed=True,messages=[]), outputs={'108':{'images':[
                        dict(filename=target.name,subfolder=target.parent.relative_to(backend.setup['run']/'comfy/output').as_posix(),type='output')]}})
                if backend.mode == 'lost_response': raise ConnectionError('synthetic response lost after acceptance')
                if backend.mode == 'rejected': return backend.response(dict(node_errors={'97': 'synthetic rejection'}), 400)
                return backend.response(dict(prompt_id=pid,number=number,node_errors={}))
            def queue(self, *, timeout):
                self.ownership_check(); backend.gets.append('/queue')
                return backend.response(dict(queue_running=[],queue_pending=[]))
            def history(self, prompt_id=None, *, timeout):
                self.ownership_check(); backend.gets.append('/history'+('/'+prompt_id if prompt_id else ''))
                values = backend.history_entries
                return backend.response(values if prompt_id is None else {k:v for k,v in values.items() if k==prompt_id})
        return Client()

    def service_factory(self, frozen, paths, logger, lock):
        backend = self
        class Service:
            def ensure(self):
                assert get_ident() == backend.owner; backend.ensures += 1
            def close(self):
                assert get_ident() == backend.owner; backend.closes += 1
        return Service()

    @property
    def kwargs(self): return dict(client_factory=self.factory, service_factory=self.service_factory)


def generate(setup, backend):
    from video_ai.runtime.production_scene_clips import produce_scene_clips
    return produce_scene_clips(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],
        logger=setup['logger'],**backend.kwargs)


def observation(setup, template, *, verdict='passed'):
    from video_ai.runtime.production_scene_clips import consume_scene_clip_observation
    value = json.loads(Path(template).read_text(encoding='utf-8'))
    value.update(review_method='human_video',reviewer='Synthetic fixture author; no model quality claim',
        viewed_at=datetime.now(timezone.utc).isoformat(),verdict=verdict)
    for key in ('start_observation','process_observation','end_observation','quality_observation','continuity_observation','reason'):
        value[key] = 'Synthetic complete playback observation for admission structure, including selected image, baselines and exact retained PNG.'
    value['checks'] = {key:(None if state is None else 'passed') for key,state in value['checks'].items()}
    if verdict != 'passed':
        value['checks']['motion_process'] = verdict
        if verdict == 'failed': value['issues'] = [dict(check='motion_process',frames=[0,1],description='Synthetic explicit failure')]
    path = save(setup['run']/'authored-observations'/(value['clip_id']+'-'+uuid4().hex+'.json'), value)
    result = consume_scene_clip_observation(setup['frozen'],setup['units'],setup['timeline'],path,
        paths=setup['paths'],logger=setup['logger'])
    return result, path, value


def admit_all(setup, backend, *, result=None):
    result = result or generate(setup,backend)
    for _ in range(len(setup['plan']['clips'])+1):
        if result.status == 'source_clips_ready': return result
        assert result.status == 'awaiting_continuity_review', result.error
        for template in result.observation_templates:
            accepted, _, _ = observation(setup,template)
            assert accepted.status in ('awaiting_continuity_review','source_clips_ready','blocked'),accepted.error
        result = generate(setup,backend)
    raise AssertionError('scene chain failed to finish')
