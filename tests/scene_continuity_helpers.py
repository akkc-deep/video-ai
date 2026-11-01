"""Real tiny CPU media; fixture_only technical admission and authored declarations.

The scene context/technical collector are explicit test substitutes because the
production Wan contract uses larger fixed profiles. FFmpeg bytes, VCO-02
sidecars/analysis frames, ordinary VCO-03 analysis and runtime continuity records
remain real. Synthetic observation text tests schema/state handling and asserts
no actual human/agent playback or visual accuracy.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import uuid4


AUTHOR = 'fixture_only synthetic playback author; no actual playback claim'
POLICY = {'schema_version': 1, 'policy': 'advisory_v1'}


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return path


def artifact(path):
    from video_ai.runtime.manifest import hash_file, thaw
    value = thaw(hash_file(Path(path)))
    return {key: value[key] for key in ('path', 'bytes', 'sha256')}


def snapshot(root):
    return {str(p): artifact(p) for p in Path(root).rglob('*') if p.is_file()}


def tiny_scene_context(runtime_run, monkeypatch, *, count=3, image=None, source_transform=None):
    from continuity_helpers import texture
    from video_ai.config import load_config
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import hash_file, now, thaw
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.scene_clip_observations import build_observation_template, AUTHORED_FIELDS
    from video_ai.media.colorimetry import inspect_color_asset, decode_analysis_frame
    from video_ai.media._continuity_audit import png_bytes
    from video_ai.runtime import scene_clip_records as clips
    from video_ai.runtime import production_scene_clips as production_clips

    def forbidden(*args, **kwargs):
        raise AssertionError('fixture_only continuity work must not contact services, models, SMTP, or network')
    monkeypatch.setattr('socket.socket.connect', forbidden)
    monkeypatch.setattr('smtplib.SMTP', forbidden)
    monkeypatch.setattr('video_ai.runtime.services.ServiceManager.ensure', forbidden)
    monkeypatch.setattr('video_ai.adapters.scene_comfy.SceneComfyClient.submit', forbidden)
    monkeypatch.setattr('video_ai.adapters.jimeng.JimengClient.submit', forbidden)

    run, base, paths = runtime_run
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    raw = thaw(base.raw)
    raw.update(production_strategy='paragraph_jimeng_v1', scene_continuity=POLICY)
    config = replace(base, raw=raw, production_strategy='paragraph_jimeng_v1', tools=dict(
        base.tools, ffmpeg=actual.tools['ffmpeg'], ffprobe=actual.tools['ffprobe']))
    policy = save(run/'production/scene-continuity/policy.json', POLICY)
    script = run/'production/script.txt'
    script.write_text('fixture_only: six synthetic frames.', encoding='utf-8')
    frozen = SimpleNamespace(config=config, options=dict(run_id=run.name, script_path=str(script),
        schema_version=2, model_stamps={}, execution_policy=dict(input_identities={
            'scene_continuity_policy': thaw(hash_file(policy))})))
    save(run/'production/options.json', frozen.options)
    source_logger = RunLogger(run, production=True)
    color_logger = RunLogger(create_run(paths))
    kw = dict(config=config, paths=paths, logger=color_logger)
    ids = [f'scene_0001_clip_{i:04d}' for i in range(1, count+1)]
    inputs = dict(visual_bible_sha256=canonical_digest({'fixture_only': True}))
    save(run/'production/scene-clips/inputs.json', inputs)
    rgb = texture(64, 36) if image is None else image
    selected = run/'selected.png'
    selected.write_bytes(png_bytes(rgb))
    records, rows, all_frames, sidecars = {}, [], [], []
    previous = None
    for number, cid in enumerate(ids):
        folder = run/'production/scene-clips'/cid
        folder.mkdir(parents=True)
        raw_path = folder/'fixture.rgb'
        frame_rgb = rgb+number if source_transform is None else source_transform(rgb.copy(),number)
        raw_path.write_bytes(frame_rgb.tobytes()*2)
        generated = folder/'generated.mp4'
        args = [str(config.tools['ffmpeg']), '-nostdin', '-n', '-v', 'error', '-threads', '1',
            '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '64x36', '-framerate', '16',
            '-i', str(raw_path), '-frames:v', '2', '-an', '-c:v', 'libx264', '-crf', '0',
            '-pix_fmt', 'yuv444p', '-colorspace', 'bt709', '-color_primaries', 'bt709',
            '-color_trc', 'iec61966-2-1', '-color_range', 'tv', '-x264-params',
            'colorprim=bt709:transfer=iec61966-2-1:colormatrix=bt709', str(generated)]
        command = run_logged(args, cwd=run, env=build_child_env(paths), timeout=60,
            logger=source_logger, stage='fixture_only_media', unit_id=cid)
        assert command.returncode == 0 and not command.timed_out, command.stderr_path.read_text()
        source = folder/'source.mp4'
        shutil.copyfile(generated, source)
        mapping = dict(schema_version=2, clip_id=cid, retained_frames=2, generated_frames=2,
            retained_source_start=0, retained_source_end=2, start_frame=number*2, end_frame=(number+1)*2,
            generated_to_retained=list(range(2)), retained_to_generated=list(range(2)))
        save(folder/'mapping.json', mapping)
        last_png = folder/'last-frame.png'
        extraction = run_logged([str(config.tools['ffmpeg']), '-nostdin', '-n', '-v', 'error',
            '-i', str(source), '-vf', 'select=eq(n\\,1)', '-frames:v', '1', '-pix_fmt', 'rgb24', str(last_png)],
            cwd=run, env=build_child_env(paths), timeout=60, logger=source_logger,
            stage='fixture_only_tail', unit_id=cid)
        assert extraction.returncode == 0 and not extraction.timed_out, extraction.stderr_path.read_text()
        last = dict(image=artifact(last_png))
        save(folder/'last-frame.json', last)
        parent = None if previous is None else dict(clip_id=previous['clip']['clip_id'],
            clip_sha256=canonical_digest(previous['clip']), generated=previous['clip']['generated'],
            source=previous['clip']['source'], last_frame_sha256=canonical_digest(previous['last_frame']),
            last_frame=previous['last_frame']['image'],
            observation_acceptance_sha256=canonical_digest(previous['accepted']))
        request = dict(scene_id='scene_0001', clip_id=cid, inputs_sha256=canonical_digest(inputs),
            selected_image=artifact(selected), comparison_images=[], parent=parent)
        save(folder/'request.json', request)
        clip = dict(schema_version=2, production_strategy='paragraph_jimeng_v1', run_id=run.name,
            scene_id='scene_0001', clip_id=cid, request_sha256=canonical_digest(request),
            generated=artifact(generated), source=artifact(source), created_at=now())
        save(folder/'clip.json', clip)
        template = build_observation_template(frozen, clip, request, mapping, last,
            None if previous is None else {key: previous[key] for key in ('clip', 'mapping', 'last_frame', 'accepted')})
        observation = deepcopy(template)
        observation.update(review_method='human_video', reviewer=AUTHOR, viewed_at=now(), verdict='passed')
        observation['checks'] = {key: None if state is None else 'passed' for key, state in template['checks'].items()}
        observation.update({key: 'fixture_only synthetic declaration; no actual playback or quality claim' for key in AUTHORED_FIELDS})
        authored = save(folder/'observations'/('fixture_only_'+uuid4().hex+'.json'), observation)
        accepted = dict(schema_version=2, run_id=run.name, clip_id=cid,
            clip_sha256=canonical_digest(clip), request_sha256=canonical_digest(request),
            observation=artifact(authored), observation_sha256=canonical_digest(observation), accepted_at=now())
        save(folder/'observation-accepted.json', accepted)
        record = dict(clip=clip, request=request, mapping=mapping, last_frame=last,
            template=template, accepted=accepted, rejected=None)
        records[cid] = previous = record
        rows.append(dict(budget=dict(clip_id=cid, scene_id='scene_0001', retained_frames=2,
            generated_frames=2, retained_source_start=0, retained_source_end=2,
            start_frame=number*2, end_frame=(number+1)*2,
            parent_clip_id=ids[number-1] if number else None)))
        mapping_rows = [dict(asset_frame_index=i, clip_id=cid, generated_frame_index=i,
            retained_frame_index=i, output_frame_index=number*2+i, pts=i*1024, time_base='1/16384')
            for i in range(2)]
        proof = save(folder/'vco02-mapping-proof.json', dict(source=thaw(hash_file(source)), rows=mapping_rows))
        entry = dict(asset_id='retained_'+str(number), stage='retained', path=str(source),
            mapping=dict(rows=mapping_rows, evidence=[thaw(hash_file(proof))]),
            processing=dict(operation='fixture_only exact source bytes', upstream_ids=[], command_records=[]))
        sidecar, _ = inspect_color_asset(entry, **kw)
        sidecars.append(sidecar)
        frame_rows = []
        for index in range(2):
            decode_analysis_frame(sidecar, frame_index=index, **kw)
            frame_rows.append(dict(frame_id=f'clip_{number}_frame_{index}', record=thaw(hash_file(
                color_logger.root/f'colorimetry/retained_{number}/analysis/frame_{index:06d}.json'))))
        all_frames.append(dict(clip_id=cid, frames=frame_rows))
        if number == 0:
            reference_entry = dict(entry, asset_id='fixed_reference')
            reference_sidecar, _ = inspect_color_asset(reference_entry, **kw)
            decode_analysis_frame(reference_sidecar, frame_index=0, **kw)
            reference = dict(frame_id='fixed_reference', record=thaw(hash_file(
                color_logger.root/'colorimetry/fixed_reference/analysis/frame_000000.json')))

    regions = save(run/'fixture_only-regions.json', dict(schema_version=1, author='fixture_only',
        reviewed_at=now(), regions=[dict(region_id=rid, role=rid, identity_note='fixture_only texture',
            anchors=[dict(frame=row['frames'][0]['record'], rect=[0., 0., 1., 1.]) for row in all_frames]
                + [dict(frame=reference['record'], rect=[0., 0., 1., 1.])]) for rid in ('subject', 'background')]))

    def context_factory(frozen_arg, units, timeline, *, paths=None, lock=None):
        assert frozen_arg is frozen
        return dict(frozen=frozen, store=SceneClipStore(frozen, run, paths=paths, lock=lock, clip_ids=ids),
            rows=rows, inputs=inputs, plan=dict(scenes=[dict(scene_id='scene_0001')]))

    def collect(context):
        for cid, record in records.items():
            folder = context['store'].clip_dir(cid)
            for key, name in (('accepted', 'observation-accepted.json'), ('rejected', 'observation-rejected.json')):
                path = folder/name
                record[key] = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        return dict(schema_version=2, run_id=run.name, scenes=[]), records

    monkeypatch.setattr(clips, 'scene_context', context_factory)
    monkeypatch.setattr(clips, 'collect_progress', collect)
    monkeypatch.setattr(production_clips, 'scene_context', context_factory)
    monkeypatch.setattr(production_clips, 'collect_progress', collect)
    # Full Wan source aggregation cannot consume this explicitly smaller fixture
    # context. Retain the original observation validator and receipt consumer.
    monkeypatch.setattr(production_clips, '_finish', lambda *a, **k:
        SimpleNamespace(status='awaiting_continuity_review', error=None))
    return dict(run=run, frozen=frozen, config=config, paths=paths, logger=source_logger,
        color_logger=color_logger, units=[], timeline=SimpleNamespace(), records=records,
        rows=rows, all_frames=all_frames, reference=reference, regions=thaw(hash_file(regions)),
        sidecars=sidecars, context=context_factory)


def manifest_for(setup, count=3):
    from video_ai.runtime.manifest import hash_file, thaw
    frames = deepcopy(setup['all_frames'][:count])
    region_value = json.loads(Path(setup['regions']['path']).read_text(encoding='utf-8'))
    allowed = {f['record']['path'] for row in frames for f in row['frames']}
    allowed.add(setup['reference']['record']['path'])
    for region in region_value['regions']:
        region['anchors'] = [a for a in region['anchors'] if a['frame']['path'] in allowed]
    regions = save(setup['run']/f'fixture_only-regions-prefix-{count}.json', region_value)
    comparisons = []
    def pair(kind, left, right):
        comparisons.append(dict(comparison_id=f'comparison_{len(comparisons)}', kind=kind,
            left=left, right=right, region_ids=['subject', 'background']))
    for row in frames:
        ids = [f['frame_id'] for f in row['frames']]
        for left, right in zip(ids, ids[1:]):
            pair('adjacent', left, right)
    for previous, current in zip(frames, frames[1:]):
        pair('parent_join', previous['frames'][-1]['frame_id'], current['frames'][0]['frame_id'])
    for frame in [f for row in frames for f in row['frames']][1:]:
        pair('reference', setup['reference']['frame_id'], frame['frame_id'])
    return dict(schema_version=1, algorithm='continuity_cv_v1', scope='scene', scene_id='scene_0001',
        domain=dict(genre='animation', source_kind='generated'), timeline=dict(fps_num=16, fps_den=1),
        clips=frames, references=[deepcopy(setup['reference'])], regions=thaw(hash_file(regions)),
        comparisons=comparisons, context=None, profile=None)


def analysis_request(setup, epoch, *, count=3, manifest=None):
    value = manifest if manifest is not None else manifest_for(setup, count)
    aid = str(uuid4())
    path = save(setup['run']/f'fixture_only-manifest-{aid}.json', value)
    return save(setup['run']/f'fixture_only-analysis-{aid}.json', dict(schema_version=1,
        run_id=setup['run'].name, assessment_id=aid, epoch=epoch,
        clip_id=setup['rows'][count-1]['budget']['clip_id'], manifest=artifact(path)))


def review_request(setup, assessment_path, *, disposition='not_observed_in_full_playback',
                   prefix_author=AUTHOR, omit_response=False):
    from video_ai.runtime.manifest import now
    assessment_path = Path(assessment_path)
    assessment = json.loads(assessment_path.read_text(encoding='utf-8'))
    record = setup['records'][assessment['clip_id']]
    video = record['accepted']['observation']
    prefix = video
    if len(assessment['binding']['clips']) >= 3:
        prefix = artifact(save(setup['run']/f'fixture_only-prefix-{uuid4()}.json', dict(schema_version=1,
            run_id=setup['run'].name, assessment_id=assessment['assessment_id'],
            assessment=artifact(assessment_path), review_method='human_video', reviewer=prefix_author,
            viewed_at=now(), playback=[{key: row[key] for key in ('clip_id', 'source', 'source_frames', 'output_frames')}
                for row in assessment['binding']['clips']], start_observation='fixture_only synthetic start',
            process_observation='fixture_only synthetic complete process', end_observation='fixture_only synthetic end',
            quality_observation='fixture_only synthetic quality; no actual playback claim',
            checks={key: 'passed' for key in ('subject_identity', 'color_lighting', 'motion_process', 'camera_path', 'cumulative_color')},
            verdict='passed', issues=[])))
    responses = [dict(concern_id=c['concern_id'], disposition=disposition,
        reason='fixture_only response for software state verification; no visual accuracy claim', references=[])
        for c in assessment['concerns']]
    if omit_response:
        assert responses, 'unprofiled report must retain unverified concerns'
        responses.pop()
    return save(setup['run']/f'fixture_only-review-{uuid4()}.json', dict(schema_version=1,
        run_id=setup['run'].name, assessment_id=assessment['assessment_id'], assessment=artifact(assessment_path),
        video_observation=video, prefix_observation=prefix, reviewer=AUTHOR, reviewed_at=now(), responses=responses))
