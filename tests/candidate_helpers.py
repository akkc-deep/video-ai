"""TEST ONLY candidate fixture; only the expensive upstream consumer is mocked."""
from dataclasses import replace
import json
from pathlib import Path
import wave

from composition_helpers import inputs
from video_ai.config import load_config
from video_ai.media.composition_video import command, ffmpeg, inspect_composition
from video_ai.media.subtitles import plan_subtitles, srt_text
from video_ai.planning.composition import CompositionSettings, plan_composition
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.manifest import create_manifest, hash_file, thaw, now
from video_ai.runtime.paths import RuntimePaths
from video_ai.runtime.timeline_checks import _artifact


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


def make_candidate_fixture(runtime_run, monkeypatch, *, fps=16):
    run, original, paths = runtime_run
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    raw = thaw(original.raw)
    raw['voice_config'] = str(original.voice.config_file)
    raw['workflows'] = {k: str(v) for k, v in original.workflows.items()}
    raw['tools'] = {k: str(actual.tools[k]) if k in ('ffmpeg', 'ffprobe') else str(v) for k, v in original.tools.items()}
    raw['media']['font_file'] = str(actual.media.font_file)
    raw['media']['fps'] = fps
    raw['media']['timeline'] = {k: 0 for k in ('sentence_pause_seconds', 'paragraph_pause_seconds', 'opening_seconds', 'closing_seconds')}
    config = load_config(write(run/'fixture-config.json', raw))
    timeline, storyboard, upscaled, timing = inputs(fps=fps)
    clips = []
    for clip in timeline.clips:
        path = run/'audio'/clip.unit_id/'pcm-48000.wav'
        path.parent.mkdir(parents=True)
        with wave.open(str(path), 'wb') as out:
            out.setparams((1, 2, 48000, 0, 'NONE', ''))
            out.writeframes(b'\x01\x00'*clip.samples)
        identity = hash_file(path)
        clips.append(replace(clip, pcm=replace(clip.pcm, path=path, bytes=identity.bytes, sha256=identity.sha256)))
    timeline = replace(timeline, clips=tuple(clips))
    plan = plan_composition(timeline, storyboard, upscaled, timing, settings=CompositionSettings())
    events = plan_subtitles(timeline, CompositionSettings(), measure=lambda text: len(text)*32)
    folder = run/'staging/composition'
    folder.mkdir(parents=True)
    candidate = folder/'candidate.mp4'
    kw = dict(config=config, paths=RuntimePaths.from_config(config), logger=RunLogger(run), cwd=folder)
    command([*ffmpeg(config), '-f', 'lavfi', '-i', f'color=c=blue:s=1920x1080:r={fps}', '-f', 'lavfi', '-i', 'sine=frequency=500:sample_rate=48000:duration=3', '-frames:v', str(plan.total_frames), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '1', str(candidate)], operation='TEST ONLY candidate', **kw)
    info, _ = inspect_composition(candidate, fps=fps, frames=plan.total_frames, channels=1, **kw)
    (folder/'subtitle.srt').write_bytes(srt_text(events).encode('utf-8'))
    write(run/'timeline.json', timeline.as_dict())
    (run/'script.txt').write_text(timeline.original_text, encoding='utf-8')
    ids = {k: thaw(hash_file(p)) for k, p in [('config', config.config_file), ('voice', config.voice.config_file), ('timeline', run/'timeline.json'), ('script_copy', run/'script.txt'), ('font', config.media.font_file), ('ffmpeg', config.tools['ffmpeg']), ('ffprobe', config.tools['ffprobe'])]}
    ids.update({'pcm/'+c.unit_id: thaw(hash_file(c.pcm.path)) for c in timeline.clips})
    composition = dict(schema_version=1, run_id=run.name, created_at=now(), status='completed', passed=True, staging_only=True,
        input_identities=ids, candidate_identity=info.pop('identity'), effective_media=info,
        subtitles=dict(srt_identity=thaw(hash_file(folder/'subtitle.srt')), events=events),
        frame_mappings=thaw(plan.ordered_frame_map), requirement_bindings=thaw(plan.requirement_bindings), cue_checks=thaw(plan.cue_checks),
        provenance=dict(source_validation={'video_text_semantics_passed': False}, source_review_method='user_acceptance', timing_basis={'method': 'human_audio', 'actual_video_sync': 'unverified'}))
    # The expensive source-frame consumer is mocked, but every identity it
    # returns still refers to an owned real file for the final freshness gate.
    mapped = {}
    def real_upstream(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'bytes', 'mtime_ns', 'sha256', 'verified_at'}:
                if value['path'] not in mapped:
                    path = run/'fixture-upstream'/f'input-{len(mapped):04d}.bin'
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'TEST ONLY mocked upstream frame/media')
                    mapped[value['path']] = thaw(hash_file(path))
                return dict(mapped[value['path']])
            return {k: real_upstream(v) for k, v in value.items()}
        if isinstance(value, list): return [real_upstream(v) for v in value]
        return value
    for key in ('frame_mappings', 'requirement_bindings', 'cue_checks'):
        composition[key] = real_upstream(composition[key])
    write(run/'composition.json', composition)
    store = create_manifest(run, config, inputs={'config': hash_file(config.config_file), 'voice': hash_file(config.voice.config_file)}, models={}, workflows={})
    for stage in ('speech', 'timeline', 'storyboard', 'start_images', 'source_clips', 'upscale'):
        store.record_stage(stage, 'running'); store.record_stage(stage, 'completed')
    store.record_stage('composition', 'running')
    def complete(data):
        identity = hash_file(run/'composition.json')
        data['workflows']['composition_report'] = thaw(identity)
        store._record_status(data, data['stages']['composition'], 'completed', [_artifact(identity)], None, 'composition', None)
    store.update(complete)
    from video_ai.runtime import candidate_checks
    def upstream(run_dir):
        # Mock only the complete upstream reconstruction; keep report and every
        # input identity real and fresh so drift tests exercise disk evidence.
        from video_ai.runtime._composition_inputs import fresh
        current = json.loads((run_dir/'composition.json').read_text(encoding='utf-8'))
        for record in current['input_identities'].values(): fresh(record)
        fresh(current['candidate_identity']); fresh(current['subtitles']['srt_identity'])
        return current
    monkeypatch.setattr(candidate_checks, 'load_committed_composition', upstream)
    return run, config, store, composition
