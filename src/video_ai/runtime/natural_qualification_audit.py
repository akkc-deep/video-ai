"""Replay delivered development evidence without inventing natural labels or qualification."""
import hashlib
import json
import os
from pathlib import Path
from time import monotonic
from uuid import uuid4

from ..config import load_config
from ..media.natural_repair_statistics import natural_bias_statistics
from ..media.research_pair_report import validate_research_pair_report
from ._scene_continuity_io import artifact, local, verify
from .manifest import now
from .research_material_baseline import measure_natural_manifest
from .research_material_records import ResearchReader, load_research_material_context

AUDIT_ROOT = Path('D:/VideoSi/projects/video-ai/vco06-natural-qualification')
THRESHOLDS = ('noop_bias_ceiling', 'minimum_bias_improvement', 'maximum_frame_bias_regression',
              'maximum_off_axis_residual', 'maximum_temporal_bias_increase')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _replay_identity(value):
    """Match the original producer's compact bytes without retaining a second decoded baseline."""
    digest = hashlib.sha256()
    size = 0
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    for part in encoder.iterencode(value):
        raw = part.encode('utf-8')
        size += len(raw)
        if size + 1 > 16 * 1024**2:
            raise ValueError('resource_limit: replay baseline JSON')
        digest.update(raw)
    digest.update(b'\n')
    return size + 1, digest.hexdigest()


def audit_natural_qualification(delivery_path, *, timeout=300):
    """Revalidate the real source and pixels, then diagnose three axes without fitting a repair."""
    reader = ResearchReader(timeout)
    delivery_ref = reader.capture(delivery_path)
    delivery = reader.read(delivery_ref)
    _require(type(delivery.get('schema_version')) is int and delivery['schema_version'] == 1
        and delivery.get('task_id') == 'VCO-06' and delivery.get('status') == 'research_input_ready'
        and delivery.get('source_kind') == 'research_wan_material_v1', 'unsupported delivered research input')
    _require(delivery.get('ready_for_propose') is False and delivery.get('production_eligible') is False
        and delivery.get('production_ready') is False and delivery.get('qualification') == 'awaiting_qualification'
        and delivery.get('full_video_observation') == 'unverified'
        and delivery.get('natural_profile') is None and delivery.get('operation') is None,
        'audit only accepts explicitly unqualified development input')
    run = local(delivery['run_dir'], exists=False)
    context = load_research_material_context(run, reader=reader)
    _require(run.name == context['run_id'] and delivery['material_id'] == context['material_id'],
             'delivery research producer differs')
    for name in ('source', 'selected_image', 'commit', 'epoch', 'assessment', 'frame_map'):
        _require(delivery[name] == context[name], 'delivery/context identity differs: ' + name)
    _require(context['assessment'] is not None, 'complete current assessment required')
    assessment = reader.read(context['assessment'])
    _require(delivery['report'] == assessment['report'], 'delivery report differs from current assessment')
    baseline_ref = reader.capture(delivery['natural_baseline'])
    _require(Path(baseline_ref['path']) == run/'research/continuity/natural-baseline.json',
             'foreign natural baseline producer')
    options = reader.read(run/'research/options.json')
    config = load_config(Path(reader.capture(options['config'], package=True)['path']))
    manifest = reader.read(assessment['manifest'])
    verified_report = validate_research_pair_report(assessment['report'], manifest=manifest,
        config=config, timeout=reader.remaining())
    # Own the complete report read window, including every shard, across pixel
    # replay and the final audit commit. Nested validators do not grant a cache.
    for identity in verified_report['closure']:
        kept = reader.capture(identity, package=True)
        if Path(kept['path']).suffix.lower() in ('.json', '.body'):
            reader.json_paths[kept['path']] = kept['bytes']
    if sum(reader.json_paths.values()) > 256 * 1024**2:
        raise ValueError('resource_limit: qualification deduplicated JSON')
    del verified_report
    replay = measure_natural_manifest(manifest, assessment['report'], config=config, timeout=reader.remaining())
    replay.update(commit=context['commit'], assessment=context['assessment'])
    size, digest = _replay_identity(replay)
    _require((size, digest) == (baseline_ref['bytes'], baseline_ref['sha256']),
             'saved natural baseline differs from complete source/pixel replay')
    _require(replay.get('all_frames_supported') is True, 'complete natural support required')
    frames = replay['frames']
    native_count = delivery['native']['frames']
    _require(type(native_count) is int and native_count == len(frames), 'delivery native frame coverage differs')
    statistics = {}
    for operation in ('exposure', 'wb_r', 'wb_g'):
        reader.check()
        statistics[operation] = natural_bias_statistics(frames, operation=operation)
    for identity in replay['implementation']:
        reader.capture(identity, package=True)
    del replay
    for path in (Path(__file__), Path(__file__).parent.parent/'media/natural_repair_statistics.py'):
        reader.capture(path, package=True)
    reader.verify_all()
    return dict(schema_version=1, kind='natural_qualification_readiness_audit_v1', created_at=now(),
        delivery=delivery_ref, run_dir=str(run), material_id=context['material_id'],
        commit=context['commit'], epoch=context['epoch'], assessment=context['assessment'],
        report=assessment['report'], baseline=baseline_ref, baseline_replayed=True, native_frames=native_count,
        statistics=statistics, status='awaiting_qualification',
        known_development_sources=1, natural_positive_cases=0, new_holdout_cases=0,
        empirical_scope='only the supplied previously viewed development material; no accepted natural labels',
        requirements=dict(development_videos=12, holdout_videos=12, groups_per_split=4,
            natural_cases_per_direction_per_split=4, groups_per_direction_per_split=4),
        blockers=['independent_preregistered_development_and_holdout_inputs_missing',
            'actual_complete_playback_natural_labels_missing',
            'known_axis_color_issue_precheck_missing',
            'development_threshold_seal_and_once_only_holdout_evaluation_missing'],
        thresholds=dict.fromkeys(THRESHOLDS), qualified_directions=[], natural_profile=None,
        operation=None, candidate_generated=False, improvement_accepted=False,
        full_video_observation='unverified', production_eligible=False, production_ready=False,
        ready_for_propose=False, closure=[reader.frozen[key] for key in sorted(reader.frozen)])


def write_qualification_audit(delivery_path, output_path, *, timeout=300):
    """Create one independent, immutable audit; never write into delivered runs or bundles."""
    deadline = monotonic() + timeout
    output = local(output_path, exists=False)
    _require(output.is_relative_to(AUDIT_ROOT) and output != AUDIT_ROOT,
             'qualification audit output requires the independent audit root')
    delivery_file = local(delivery_path)
    _require(not output.is_relative_to(delivery_file.parent),
             'qualification audit output cannot be inside the delivered input bundle')
    if output.exists():
        raise FileExistsError('qualification audit output already exists')
    temporary = local(output.with_name(output.name + '.' + uuid4().hex + '.tmp'), exists=False)
    result = audit_natural_qualification(delivery_path, timeout=timeout)
    raw = (json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
    _require(len(raw) <= 16*1024**2, 'resource_limit: qualification audit output JSON')
    if monotonic() >= deadline:
        raise TimeoutError('qualification audit deadline expired')
    output.parent.mkdir(parents=True, exist_ok=True)
    local(output, exists=False)
    local(temporary, exists=False)
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    for identity in result['closure']:
        if monotonic() >= deadline:
            raise TimeoutError('qualification audit deadline expired before commit')
        verify(identity, runtime=Path(identity['path']).is_relative_to(Path('D:/VideoSi')), empty=True)
    local(output, exists=False)
    local(temporary)
    # Native Windows rename refuses a destination created by a concurrent writer.
    if output.exists():
        raise FileExistsError('qualification audit output appeared before commit')
    os.rename(temporary, output)
    return dict(schema_version=1, status=result['status'], audit=artifact(output),
                native_frames=result['native_frames'], ready_for_propose=False)
