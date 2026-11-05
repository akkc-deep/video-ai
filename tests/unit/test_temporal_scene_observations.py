"""A static window review never substitutes for a complete native-chain review."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from types import SimpleNamespace

import pytest

NOW = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)
CHECKS = ('subject', 'color', 'composition', 'camera', 'motion')


def put(path, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps({'fixture_only': label}).encode())
    return dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def fixture(runtime_run, *, terminal=False, stage=1):
    from video_ai.planning.scene_temporal import derive_temporal_clips
    run = runtime_run[0]
    root = run/'production/scene-clips'
    selected = put(root/'selected.png', 'selected image')
    clips = derive_temporal_clips(dict(total_frames=320, scenes=[dict(scene_id='scene_0001', start_frame=0, end_frame=320)]), dict(total_frames=320))
    windows = []
    for index, budget in enumerate(clips, 1):
        folder = root/budget['clip_id']
        windows.append(dict(budget=budget, result=put(folder/'native-result.json', f'result{index}'),
                            raw_frames=put(folder/'frames.npy', f'frames{index}')))
    window = dict(windows[stage-1], request_sha256='a'*64, selected_image=selected,
                  contact_sheet=put(root/'contact.png', 'contact sheet'), created_at='2026-11-03T00:00:00+00:00',
                  terminal=terminal, parent=None)
    if stage > 1:
        window['parent'] = dict(result=windows[stage-2]['result'], raw_frames=windows[stage-2]['raw_frames'],
            condition_frames=put(root/'condition13.npy', '13 distinct history frames'), source_frame_range=[80, 93])
    chain = dict(scene_id='scene_0001', result=put(root/'chain/result.json', 'chain receipt'),
        viewing=put(root/'chain/viewing.mp4', 'viewing movie'), selected_image=selected, windows=windows,
        created_at='2026-11-03T00:00:00+00:00')
    context = dict(frozen=SimpleNamespace(options=dict(run_id=run.name, script_path=str(run/'production/script.txt'))),
                   store=SimpleNamespace(run_dir=run), inputs={'fixture_only': True})
    return context, window, chain


def author(template):
    value = deepcopy(template)
    static = template['scope'] == 'temporal_window_static'
    value.update(review_method='agent_image' if static else 'human_video', reviewer='fixture_only reviewer',
                 viewed_at=NOW.isoformat(), verdict='acceptable' if static else 'passed',
                 reason='fixture_only observation; no real model or visual claim')
    value['checks'] = {key: 'acceptable' if static else 'passed' for key in CHECKS}
    value['allow_next_window'] = static and not template['binding']['terminal']
    return value


def test_unauthored_template_is_not_an_observation(runtime_run):
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation
    from video_ai.runtime.production_state import ProductionRefused
    context, window, _ = fixture(runtime_run)
    template = build_temporal_observation_template(context, window, scope='temporal_window_static')
    assert template['verdict'] == 'unverified' and template['review_method'] is None
    with pytest.raises(ProductionRefused):
        validate_temporal_observation(template, {'template': template, 'created_at': window['created_at']}, NOW)


def test_static_only_controls_next_window_and_cannot_pass_chain(runtime_run):
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation
    from video_ai.runtime.production_state import ProductionRefused
    context, window, chain = fixture(runtime_run, stage=2)
    template = build_temporal_observation_template(context, window, scope='temporal_window_static')
    value = author(template)
    value['checks']['camera'] = value['checks']['motion'] = 'unverified'
    accepted = validate_temporal_observation(value, {'template': template, 'created_at': window['created_at']}, NOW)
    assert accepted['verdict'] == 'acceptable' and accepted['allow_next_window'] is True
    assert accepted['binding']['parent']['source_frame_range'] == [80, 93]
    dynamic = build_temporal_observation_template(context, chain, scope='scene_temporal_chain_process')
    with pytest.raises(ProductionRefused):
        validate_temporal_observation(value, {'template': dynamic, 'created_at': chain['created_at']}, NOW)


def test_terminal_static_acceptable_with_no_next_window_can_assemble(runtime_run):
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation
    context, window, _ = fixture(runtime_run, terminal=True, stage=4)
    template = build_temporal_observation_template(context, window, scope='temporal_window_static')
    value = author(template)
    accepted = validate_temporal_observation(value, {'template': template, 'created_at': window['created_at']}, NOW)
    assert accepted['verdict'] == 'acceptable' and accepted['allow_next_window'] is False


def test_one_complete_chain_review_binds_all_four_windows_and_boundaries(runtime_run):
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation
    context, _, chain = fixture(runtime_run)
    template = build_temporal_observation_template(context, chain, scope='scene_temporal_chain_process')
    assert template['playback'] == [0, 320]
    assert template['binding']['boundary_frames'] == [93, 173, 253]
    assert [row['source_frame_range'] for row in template['binding']['windows']] == [[0, 93], [13, 93], [13, 93], [13, 80]]
    value = author(template)
    assert validate_temporal_observation(value, {'template': template, 'created_at': chain['created_at']}, NOW) == value


@pytest.mark.parametrize('fault', ['static_method', 'partial_playback', 'unverified_camera', 'future_time',
    'before_generation', 'result_drift', 'movie_drift', 'extra', 'wrong_scope'])
def test_dynamic_pass_refuses_partial_stale_or_changed_evidence(fault, runtime_run):
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation
    from video_ai.runtime.production_state import ProductionRefused
    context, _, chain = fixture(runtime_run)
    template = build_temporal_observation_template(context, chain, scope='scene_temporal_chain_process')
    value = author(template)
    if fault == 'static_method': value['review_method'] = 'agent_image'
    elif fault == 'partial_playback': value['playback'] = [0, 319]
    elif fault == 'unverified_camera': value['checks']['camera'] = 'unverified'
    elif fault == 'future_time': value['viewed_at'] = (NOW+timedelta(seconds=1)).isoformat()
    elif fault == 'before_generation': value['viewed_at'] = '2026-11-02T23:59:59+00:00'
    elif fault == 'result_drift': value['binding']['result']['sha256'] = 'f'*64
    elif fault == 'movie_drift':
        from pathlib import Path
        Path(chain['viewing']['path']).write_bytes(b'changed')
    elif fault == 'extra': value['extra'] = 1
    else: value['scope'] = 'temporal_window_static'
    with pytest.raises(ProductionRefused):
        validate_temporal_observation(value, {'template': template, 'created_at': chain['created_at']}, NOW)
