"""GPU driver flow tested without a service or network."""
import importlib.util
import json
from pathlib import Path
import sys
from time import sleep


def api():
    sys.path.insert(0,str(Path(__file__).parents[2]/'scripts'))
    spec=importlib.util.spec_from_file_location('scene_gpu',Path(__file__).parents[2]/'scripts/benchmark_scene_preparation_gpu.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_candidate_prepares_next_independent_trial_and_consumes_copy(tmp_path,monkeypatch):
    module=api(); image=tmp_path/'input/source.png';image.parent.mkdir();image.write_bytes(b'image')
    graph={'n':{'inputs':{'seed':17}}}
    from video_ai.planning.production_scenes import canonical_digest
    frozen=tmp_path/'frozen';frozen.mkdir();(frozen/'original-graph.json').write_text(json.dumps(graph))
    fixture=dict(input_relative='source.png',input_sha256=module.gpu.file_sha(image),
                 source_graph_sha256=canonical_digest(graph),parameters={'steps':40})
    (tmp_path/'fixture.json').write_text(json.dumps(fixture))
    seen=[]
    def run(root,trial,**kwargs):
        seen.append(kwargs.get('prepared_original_graph'))
        sleep(.03)
        return {'trial_id':trial}
    monkeypatch.setattr(module.gpu,'run_trial',run)
    result=module.run_independent_trials(tmp_path,candidate=True)
    assert len(seen)==4 and seen[0] is None
    assert all(value==graph for value in seen[1:])
    assert result['preparation']['submitted']==3
    assert result['preparation']['consumed']==3
    assert result['preparation']['retained_bytes']==0


def test_serial_baseline_does_not_spawn_prefetch(tmp_path,monkeypatch):
    module=api();(tmp_path/'fixture.json').write_text('{}')
    seen=[]
    monkeypatch.setattr(module.gpu,'run_trial',lambda *a,**kw:seen.append(kw) or {})
    result=module.run_independent_trials(tmp_path,candidate=False)
    assert len(seen)==4
    assert result['preparation']['submitted']==0
    assert all(v['prepared_original_graph'] is None for v in seen)


def test_missing_parent_acceptance_refuses_before_service(tmp_path,monkeypatch):
    module=api()
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k: (_ for _ in ()).throw(AssertionError('started service')))
    import pytest
    with pytest.raises(ValueError,match='human acceptance'):
        module.require_parent_reviews(tmp_path)


def test_child_preparation_seals_child_on_parent_without_prepopulating_new_service(tmp_path,monkeypatch):
    module=api();parent=tmp_path/'parent';root=tmp_path/'new-child'
    (parent/'frozen').mkdir(parents=True);root.mkdir()
    fixture=dict(source_clip_id='parent_clip',requires_new_parent=False)
    (parent/'fixture.json').write_text(json.dumps(fixture))
    for name in ('original-request.json','original-graph.json'):(parent/'frozen'/name).write_text('{}')
    seen=[]
    monkeypatch.setattr(module.gpu,'prepare_child',lambda r,s:seen.append((r,s)))
    module.prepare_phase_inputs(root,tmp_path/'child-source','parent_child',parent_root=parent)
    assert json.loads((parent/'fixture.json').read_bytes())==fixture
    assert (parent/'frozen/original-graph.json').read_bytes()==b'{}'
    assert not (root/'fixture.json').exists()
    assert not (root/'frozen').exists()
    assert seen==[(parent,tmp_path/'child-source')]


def test_child_recovery_uses_parent_binding_instead_of_unbound_fixture(tmp_path,monkeypatch):
    module=api();calls=[]
    monkeypatch.setattr(module.gpu,'run_child_trial',lambda root,trial,**kw:calls.append((trial,kw)))
    monkeypatch.setattr(module.gpu,'run_trial',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('unbound child recovery')))
    module.recover_completed_trials(tmp_path,parent_root=tmp_path/'accepted-parent')
    assert [c[0] for c in calls]==list(module.TRIALS)
    assert all(c[1]['parent_root']==tmp_path/'accepted-parent' for c in calls)


def test_trial_diagnostic_error_preserves_original_exception(tmp_path,monkeypatch):
    module=api();(tmp_path/'fixture.json').write_text('{}');original=ValueError('ORIGINAL_TRIAL_ERROR')
    def fail(*a,**kw):raise original
    def no_disk(*a,**kw):raise OSError('DIAGNOSTIC_DISK_ERROR')
    monkeypatch.setattr(module.gpu,'run_trial',fail);monkeypatch.setattr(module.gpu,'write_once',no_disk)
    import pytest
    with pytest.raises(ValueError) as caught:module.run_independent_trials(tmp_path,candidate=False)
    assert caught.value is original
    assert any('diagnostic' in note for note in original.__notes__)


def test_stop_request_error_still_waits_and_preserves_trial_exception(tmp_path,monkeypatch):
    module=api();original=ValueError('original');calls=[]
    def no_disk(root):raise OSError('stop disk unavailable')
    monkeypatch.setattr(module,'request_stop',no_disk)
    service=type('Service',(),{'wait':lambda self,timeout:calls.append(timeout)})()
    module.close_owned_service(service,tmp_path,original=original)
    assert calls==[20]
    assert any('stop request' in note for note in original.__notes__)


def test_consumed_payload_released_before_submitting_next(tmp_path,monkeypatch):
    module=api();(tmp_path/'fixture.json').write_text('{}')
    from video_ai.runtime.scene_stage_preparation import PreparedSceneInput
    import weakref
    refs=[]
    class Pool:
        def __init__(self,**kw):pass
        def submit(self,job):
            assert all(r() is None for r in refs),'previous source payload still retained'
            return True
        def take(self,job):
            value=PreparedSceneInput((),b'source','sha',b'{}',.1)
            refs.append(weakref.ref(value));return value
        def close(self):pass
        def report(self):return {}
    monkeypatch.setattr(module,'ScenePreparationPool',Pool)
    monkeypatch.setattr(module,'job_for',lambda *a:type('Job',(),{'clip_id':'scene_0001_clip_0001'})())
    monkeypatch.setattr(module.gpu,'run_trial',lambda *a,**kw:{})
    module.run_independent_trials(tmp_path,candidate=True)
    assert all(r() is None for r in refs)


def test_sampled_idle_spans_are_explicit_and_do_not_cross_gaps(tmp_path):
    module=api()
    events=[dict(kind='session',started_at_unix=100)]
    for offset,util in [(0,80),(2,0),(4,5),(6,80),(20,0),(22,0)]:
        events.append(dict(kind='gpu',offset_seconds=offset,devices=[dict(utilization_percent=util)]))
    (tmp_path/'node-metrics.jsonl').write_text('\n'.join(json.dumps(v) for v in events))
    result=module.sampled_idle_evidence(tmp_path)
    assert result['threshold_percent']==5
    assert [(v['start_seconds'],v['end_seconds']) for v in result['intervals']]==[(2,4),(20,22)]
    assert result['observed_idle_span_seconds']==4
    assert result['physical_model_load_count']=='未测得物理装载次数'


def test_direct_http_and_media_counters_separate_recovery(monkeypatch):
    module=api()
    class Client:
        def http(self,method,route,payload=None):return {'ok':True}
    monkeypatch.setattr(module.gpu,'ExperimentClient',Client)
    monkeypatch.setattr(module.gpu,'media_command',lambda *a,**kw:None)
    with module.observe_gpu_calls() as counts:
        client=module.gpu.ExperimentClient()
        client.http('POST','/prompt');client.http('GET','/history/id')
        module.gpu.media_command(None,'trim',[],output='output.mp4')
        assert counts=={'post':1,'get':1,'media_commands':1,'media_producers':1}
    assert module.gpu.ExperimentClient is Client
