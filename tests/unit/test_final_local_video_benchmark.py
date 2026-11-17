from copy import deepcopy

import pytest


def batch():
    return dict(batch_id='low', profile='quality_strict_serial_x264', mode='normal',
                t0=0., tend=100., fps=16,
                reviews=[dict(start=20., end=40.), dict(start=30., end=50.)],
                trials=[dict(trial=t, completed_at=end, contribution_frames=93,
                             quality_accepted=False)
                        for t, end in zip(('cold_1', 'warm_1', 'warm_2', 'warm_3'), (70., 80., 90., 100.))],
                stages=[], local_samples=[])


def test_identical_final_profile_reuses_one_matrix_and_never_sums_trial_envelopes():
    from video_ai.experiments.final_local_video_benchmark import summarize_final_results
    result = summarize_final_results([batch()])
    assert result['matrix_count'] == 1
    assert result['report_identities']['baseline'] == result['report_identities']['final']
    b = result['batches'][0]
    assert b['batch_wall_seconds'] == 100
    assert b['human_wait_seconds'] == 30
    assert b['non_human_envelope_seconds'] == 70
    assert b['cost_per_usable_video_second'] is None
    assert b['trial_scheduling_envelopes_seconds'] == [70, 80, 90, 100]


def test_quality_cost_uses_batch_only_and_groups_local_temperature():
    from video_ai.experiments.final_local_video_benchmark import summarize_final_results
    value = batch()
    for row in value['trials']: row['quality_accepted'] = True
    value['local_samples'] = [dict(stage='native_child', temperature='process_cold', mode='normal', seconds=10),
                              *[dict(stage='native_child', temperature='warm_process', mode='normal', seconds=s) for s in (2, 4, 8)]]
    result = summarize_final_results([value])
    assert result['batches'][0]['cost_per_usable_video_second'] == pytest.approx(70/(372/16))
    warm = next(g for g in result['local_groups'] if g['temperature'] == 'warm_process')
    assert warm['p50_seconds'] == 4
    assert warm['p95_seconds'] == pytest.approx(7.6)


@pytest.mark.parametrize('change', ['reverse', 'open_review', 'duplicate', 'profile'])
def test_bad_or_missing_clock_and_duplicate_batches_are_rejected(change):
    from video_ai.experiments.final_local_video_benchmark import summarize_final_results
    values = [batch()]
    if change == 'reverse': values[0]['tend'] = -1
    if change == 'open_review': values[0]['reviews'][0]['end'] = None
    if change == 'duplicate': values.append(deepcopy(values[0]))
    if change == 'profile': values[0]['profile'] = 'fast'
    with pytest.raises(ValueError): summarize_final_results(values)


class Clock:
    def __init__(self): self.now = 1000.
    def __call__(self): return self.now


def test_session_resume_does_not_recount_spans_and_binds_real_decision(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalBenchmarkSession
    from video_ai.experiments.wan_fast_profiles import artifact, write_once
    clock = Clock()
    session = FinalBenchmarkSession(tmp_path, 'a'*64, utc=clock, monotonic=clock)
    session.record_selection_handoff()
    session.enter_phase('native_parent')
    clock.now += 10
    session.finish_phase('native_parent')
    media = tmp_path/'video.mp4'; media.write_bytes(b'actual video')
    subjects = [artifact(media).identity_dict()]
    session.begin_review('parent', subjects)
    clock.now += 20
    restored = FinalBenchmarkSession(tmp_path, 'a'*64, utc=clock, monotonic=clock)
    restored.resume_original()
    decision = tmp_path/'decision.json'
    write_once(decision, dict(task_id='LVA-06', kind='parent', decision='accepted',
                             media_artifacts=subjects, user_evidence='actual explicit user message'))
    restored.finish_review(artifact(decision).identity_dict())
    assert restored.snapshot()['reviews'][0]['end'] == 1030
    assert len(restored.snapshot()['stages']) == 1
    with pytest.raises(ValueError, match='identity'):
        FinalBenchmarkSession(tmp_path, 'b'*64, utc=clock)


def test_session_refuses_missing_clock_and_drift_and_active_review(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalBenchmarkSession
    from video_ai.experiments.wan_fast_profiles import artifact, write_once
    clock = Clock(); s = FinalBenchmarkSession(tmp_path, 'a'*64, utc=clock, monotonic=clock)
    s.record_selection_handoff(); s.enter_phase('native')
    with pytest.raises(ValueError): s.begin_review('native', [])
    clock.now -= 1
    with pytest.raises(ValueError, match='clock'): s.finish_phase('native')


def test_plan_is_deeply_immutable_and_pure_data(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalBenchmarkPlan, TRIALS, PROFILE
    from video_ai.experiments.wan_fast_profiles import artifact
    source = tmp_path/'source'; source.write_bytes(b'123')
    assets = {'source': artifact(source).identity_dict()}
    fixtures = dict(low={'parameters': {'steps': 40}}, high={}, chain={})
    p = FinalBenchmarkPlan(1, 'LVA-06', PROFILE, assets, fixtures, TRIALS)
    before = p.digest(); assets.clear(); fixtures['low']['parameters']['steps'] = 4
    v = p.identity_dict(); v['fixtures'].clear()
    assert p.digest() == before
    with pytest.raises((ValueError, TypeError)):
        FinalBenchmarkPlan(1, 'LVA-06', PROFILE, {}, {'low': object()}, TRIALS)


def client_root(tmp_path):
    from video_ai.experiments.wan_fast_profiles import artifact, digest, write_once
    from video_ai.experiments.final_local_video_benchmark import PROFILE
    model = tmp_path/'model'; model.write_bytes(b'abcd')
    plan = dict(schema_version=1, task_id='LVA-06', profile=PROFILE,
                assets={'model': artifact(model).identity_dict()})
    sha = digest(plan)
    write_once(tmp_path/'frozen/final-plan.json', plan)
    write_once(tmp_path/'experiment.json', dict(kind='LVA-06', port=8189, profile_sha256=sha))
    return plan, sha, model


def test_unknown_client_only_finds_original_id_and_no_second_post(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalExperimentClient
    from video_ai.experiments.upscale_experiment import baseline_api
    plan, sha, _ = client_root(tmp_path)
    pid = '00112233-4455-6677-8899-aabbccddeeff'; graph = {'1': {'inputs': {}}}
    calls = []
    def http(method, route, payload=None):
        calls.append((method, route))
        if method == 'POST': raise TimeoutError('lost response')
        intent = baseline_api().read(tmp_path/'trials/cold_1/intent.json')
        return {pid: {'prompt': [1, pid, graph, {'client_id': intent['client_id']}]}} if route == '/history' else {}
    c = FinalExperimentClient(tmp_path, plan_sha256=sha, http=http)
    with pytest.raises(TimeoutError): c.submit('cold_1', graph)
    assert c.submit('cold_1', graph) == pid
    assert [x[0] for x in calls].count('POST') == 1
    assert calls[1:] == [('GET', '/history'), ('GET', '/queue')]


def test_client_drift_same_size_mtime_rollback_refuses_before_post(tmp_path):
    import os
    from video_ai.experiments.final_local_video_benchmark import FinalExperimentClient
    plan, sha, model = client_root(tmp_path); before = model.stat()
    model.write_bytes(b'bad!'); os.utime(model, ns=(before.st_atime_ns, before.st_mtime_ns))
    calls = []
    c = FinalExperimentClient(tmp_path, plan_sha256=sha, http=lambda *a: calls.append(a))
    with pytest.raises(ValueError, match='drift'): c.submit('cold_1', {})
    assert calls == []


def test_observer_accepts_only_real_lva06_identity(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import validate_final_launch
    from video_ai.experiments.wan_fast_profiles import write_once
    plan, sha, _ = client_root(tmp_path)
    write_once(tmp_path/'frozen/service-launch.json', dict(profile_sha256=sha, port=8189))
    assert validate_final_launch(tmp_path, sha, 8189) == plan
    with pytest.raises(ValueError): validate_final_launch(tmp_path, 'b'*64, 8189)


def test_command_receipt_reuses_known_success_and_refuses_unknown_output(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalMediaCommands
    from video_ai.experiments.upscale_experiment import baseline_api
    calls = []
    target = tmp_path/'result.mp4'; source = tmp_path/'source'; source.write_bytes(b'input')
    def command(argv, **kwargs):
        calls.append(argv); target.write_bytes(b'encoded'); return b''
    runner = FinalMediaCommands(tmp_path, 'a'*64, execute=command)
    args = ['fake-ffmpeg', '-n', str(target)]
    runner.produce('compose', args, [source], target)
    runner.produce('compose', args, [source], target)
    assert len(calls) == 1
    (tmp_path/'commands/compose.complete.json').unlink()
    with pytest.raises(baseline_api().OutcomeUnknown): runner.produce('compose', args, [source], target)
    assert len(calls) == 1


def test_stage_parent_gate_and_temperatures_cannot_cross_processes():
    from video_ai.experiments.final_local_video_benchmark import stage_schedule
    low = stage_schedule('low'); chain = stage_schedule('chain')
    assert [s['name'] for s in low] == ['native_low', 'upscale_low']
    assert [s['name'] for s in chain] == ['native_parent', 'native_child', 'upscale_chain']
    assert chain[1]['requires_review'] == 'parent'
    assert chain[2]['requires_review'] == 'child_continuity'
    for s in chain:
        assert s['temperatures'] == ['process_cold', 'warm_process', 'warm_process', 'warm_process']


def test_review_rejects_same_bytes_without_actual_bound_user_decision(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalBenchmarkSession
    from video_ai.experiments.wan_fast_profiles import artifact, write_once
    s = FinalBenchmarkSession(tmp_path, 'a'*64); s.record_selection_handoff()
    media = tmp_path/'media'; media.write_bytes(b'new')
    subjects = [artifact(media).identity_dict()]; s.begin_review('parent', subjects)
    bad = tmp_path/'decision'; write_once(bad, dict(task_id='LVA-06', kind='parent', decision='accepted', media_artifacts=subjects))
    with pytest.raises(ValueError, match='decision'): s.finish_review(artifact(bad).identity_dict())


def test_coordinator_lock_is_exclusive_and_reusable(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import batch_lock
    with batch_lock(tmp_path):
        with pytest.raises((OSError, RuntimeError)):
            with batch_lock(tmp_path): pass
    with batch_lock(tmp_path): pass


def test_current_native_image_change_refuses_http_before_post(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalExperimentClient
    from video_ai.experiments.wan_fast_profiles import artifact, write_once
    plan,sha,_=client_root(tmp_path)
    p=tmp_path/'input/start.png';p.parent.mkdir();p.write_bytes(b'good')
    write_once(tmp_path/'fixture.json',dict(input_relative='start.png',input_sha256=artifact(p).sha256))
    p.write_bytes(b'bad!');calls=[]
    c=FinalExperimentClient(tmp_path,plan_sha256=sha,http=lambda *a:calls.append(a))
    with pytest.raises(ValueError,match='input'):c.submit('cold_1',{'97':{'inputs':{'image':'start.png'}}})
    assert calls==[]


def test_existing_file_hash_and_media_work_is_counted_without_new_reads(tmp_path):
    import hashlib
    import subprocess
    import sys
    from video_ai.experiments.final_local_video_execution import RealFinalBackend
    from video_ai.experiments.wan_fast_profiles import artifact
    file=tmp_path/'raw';file.write_bytes(b'four')
    # A CPU executable stub stands in only for command classification.
    plan=dict(assets=dict(ffmpeg=dict(path=sys.executable),ffprobe=dict(path=str(tmp_path/'ffprobe'))))
    b=RealFinalBackend(plan,'a'*64)
    with b.measure():
        with file.open('rb') as stream:hashlib.file_digest(stream,'sha256')
        subprocess.run([sys.executable,'-c','pass','-f','null'],check=True)
    assert b.counters['actual_sha_calls']==1 and b.counters['actual_sha_bytes']==4
    assert b.counters['decode']==1
