from uuid import uuid4

import pytest

from video_ai.experiments import wan_wrapper_backend as b,wan_wrapper_matrix as m
from tests.unit.test_wan_wrapper_matrix import ps,f


def experiment(tmp_path,transport):
    root=tmp_path/'groups/high-control';p=ps()
    m.freeze_group(root,p,f(),matrix_root=tmp_path,group='high-control',matrix_sha256='e'*64)
    return root,b.WrapperExperimentClient(root,profile_digest=p['control'].digest(),port=8297,http=transport),m.graph(p['control'],f(),'cold_1')


def test_matrix_response_loss_recovers_original_without_another_post(tmp_path):
    calls=[];pid=str(uuid4())
    def transport(method,route,payload=None):
        calls.append(method)
        if method=='POST':raise TimeoutError('lost response')
        intent=b.read(root/'trials/cold_1/intent.json')
        return {pid:{'prompt':[0,pid,graph,{'client_id':intent['client_id']}]}} if route=='/history' else {}
    root,c,graph=experiment(tmp_path,transport)
    with pytest.raises(TimeoutError):c.submit('cold_1',graph)
    assert c.recover('cold_1',graph)==pid
    assert calls.count('POST')==1


def test_unknown_matrix_intent_never_allocates_new_request(tmp_path):
    calls=[]
    def transport(method,*args):
        calls.append(method)
        if method=='POST':raise TimeoutError()
        return {}
    root,c,graph=experiment(tmp_path,transport)
    with pytest.raises(TimeoutError):c.submit('cold_1',graph)
    before=b.read(root/'trials/cold_1/intent.json')
    for _ in range(2):
        with pytest.raises(Exception,match='unknown'):c.recover('cold_1',graph)
    assert b.read(root/'trials/cold_1/intent.json')==before
    assert calls.count('POST')==1


def test_matrix_client_cannot_submit_other_mode_or_fifth_trial(tmp_path):
    root,c,graph=experiment(tmp_path,lambda *args:pytest.fail('must refuse before HTTP'))
    with pytest.raises(ValueError):c.submit('warm_4',graph)
    other=b.WrapperExperimentClient(root,profile_digest=ps()['fast'].digest(),port=8297,http=lambda *a:pytest.fail('HTTP'))
    with pytest.raises(ValueError):other.submit('cold_1',m.graph(ps()['fast'],f(),'cold_1'))


def test_control_gate_cannot_use_previous_task_review(tmp_path):
    root=tmp_path/'groups/high-fast';p=ps()
    m.freeze_group(root,p,f(),matrix_root=tmp_path,group='high-fast',matrix_sha256='e'*64)
    b.write_once(root/'reviews/control_1.json',dict(decision='accepted',human_evidence='old acceptance'))
    with pytest.raises((FileNotFoundError,ValueError)):m.require_fast_review(root)


def test_missing_parent_never_creates_child_intent(tmp_path):
    root=tmp_path/'groups/child-control';p=ps();fixture=f('child')
    m.freeze_group(root,p,fixture,matrix_root=tmp_path,group='child-control',matrix_sha256='e'*64)
    c=b.WrapperExperimentClient(root,profile_digest=p['control'].digest(),port=8297,http=lambda *a:pytest.fail('HTTP'))
    with pytest.raises(ValueError,match='parent'):c.submit('cold_1',m.graph(p['control'],fixture,'cold_1'))
    assert not (root/'trials/cold_1/intent.json').exists()


def test_matrix_cli_requires_authorization_before_any_gpu_action(tmp_path):
    import importlib.util
    path=b.SOURCE/'scripts/benchmark_wan_wrapper_matrix.py'
    spec=importlib.util.spec_from_file_location('matrix_cli_test',path);cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    with pytest.raises((ValueError,FileNotFoundError)):
        cli.main(['run','--root',str(tmp_path),'--group','low-control','--trial','cold_1'])
    assert not (tmp_path/'groups').exists()


def test_matrix_cli_report_never_creates_missing_service_or_intent(tmp_path):
    import importlib.util
    path=b.SOURCE/'scripts/benchmark_wan_wrapper_matrix.py'
    spec=importlib.util.spec_from_file_location('matrix_cli_report_test',path);cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    with pytest.raises((ValueError,FileNotFoundError)):cli.main(['recover','--root',str(tmp_path),'--group','low-control','--trial','cold_1'])
    assert list(tmp_path.iterdir())==[]


def test_complete_real_matrix_media_recovers_offline_without_second_decode(tmp_path,monkeypatch):
    import numpy as np
    from video_ai.experiments import wan_wrapper_media as media
    root=tmp_path/'groups/high-control';p=ps();fixture=f();pid=str(uuid4())
    for mode,profile in p.items():
        value=profile.identity_dict();value['common']['tool']=dict(ffmpeg={'path':media.DEFAULT_FFMPEG},ffprobe={'path':media.DEFAULT_FFPROBE})
        p[mode]=b.WrapperProfile.from_dict(value)
    m.freeze_group(root,p,fixture,matrix_root=tmp_path,group='high-control',matrix_sha256='e'*64)
    graph=m.graph(p['control'],fixture,'cold_1');target=root/'output/lva07/control/cold_1.mp4'
    images=np.full((93,432,768,3),.4,dtype=np.float32)
    partial=media.encode_frames(root,target,images)
    media.promote_encoded(root,target,partial,save_frames=True)
    client=b.WrapperExperimentClient(root,profile_digest=p['control'].digest(),port=8297,http=lambda *a:pytest.fail('completed must be offline'))
    client.bind('cold_1',graph);folder=root/'trials/cold_1'
    intent=dict(client_id=str(uuid4()),graph=graph,graph_sha256=b.digest(graph))
    b.write_once(folder/'intent.json',intent);b.write_once(folder/'accepted.json',dict(prompt_id=pid,recovered=True))
    b.write_once(folder/'history.completed.json',{pid:dict(prompt=[0,pid,graph,{'client_id':intent['client_id']}],status={'completed':True},
        outputs={'108':{'images':[dict(filename='cold_1.mp4',subfolder='lva07/control',type='output')]}})})
    original=media.baseline_api
    def api():
        obj=original();command=obj.media_command
        def no_decode(root,name,*args,**kw):
            if name=='decode-rgb24':pytest.fail('no repeat full decode during completed recovery')
            return command(root,name,*args,**kw)
        obj.media_command=no_decode;return obj
    monkeypatch.setattr(media,'baseline_api',api)
    result=client.recover('cold_1',graph)
    assert result['generated_frames']==93 and result['retained_frames']==93 and len(result['frames'])==93
    assert client.recover('cold_1',graph)==result
    # A separate review process has no in-memory proof; one fresh decode may rebuild it.
    monkeypatch.setattr(media,'baseline_api',original)
    media.clear_proofs()
    assert client.recover('cold_1',graph)==result
    changed=dict(result,frames=list(reversed(result['frames'])))
    with pytest.raises(ValueError):media.validate_result(root,changed,profile=p['control'])


def test_early_prepare_does_not_persist_unsent_intent(tmp_path,monkeypatch):
    root,c,graph=experiment(tmp_path,lambda *a:pytest.fail('not ready; no transport'))
    c.injected=False
    # Isolate readiness from the separately tested real-model profile guard.
    monkeypatch.setattr(c,'_verify',lambda:(ps()['control'],f()))
    monkeypatch.setattr(c.delegate,'assert_owned_service',lambda:(_ for _ in ()).throw(ValueError('not ready')))
    with pytest.raises((ValueError,FileNotFoundError)):c.prepare_text()
    assert not (root/'text/client-intent.json').exists()


def test_early_control_run_does_not_persist_unsent_intent(tmp_path,monkeypatch):
    root,c,graph=experiment(tmp_path,lambda *a:pytest.fail('not ready; no transport'))
    c.injected=False
    monkeypatch.setattr(c,'_verify',lambda:(ps()['control'],f()))
    # Binding/physical content is exercised separately; isolate pre-intent readiness.
    monkeypatch.setattr(c,'bind',lambda *args:None)
    monkeypatch.setattr(c.delegate,'assert_owned_service',lambda:(_ for _ in ()).throw(ValueError('not ready')))
    with pytest.raises((ValueError,FileNotFoundError)):c.submit('cold_1',graph)
    assert not (root/'trials/cold_1/intent.json').exists()


def test_matrix_report_distinguishes_failed_unknown_and_accepted(tmp_path,monkeypatch):
    manifest=dict(task_id='LVA-07-06',groups=list(m.GROUPS),trials=list(m.TRIALS))
    monkeypatch.setattr(m,'matrix_manifest',lambda _:dict(matrix_sha256='e'*64,manifest=manifest))
    folder=tmp_path/'groups/high-control/trials'
    b.write_once(folder/'cold_1/intent.json',dict(client_id=str(uuid4())))
    b.write_once(folder/'warm_1/intent.json',dict(client_id=str(uuid4())))
    b.write_once(folder/'warm_1/accepted.json',dict(prompt_id=str(uuid4())))
    b.write_once(folder/'warm_2/history.failed.json',dict(error='original sampler failed'))
    rows=m.report(tmp_path)['groups']['high-control']['rows']
    assert [row['status'] for row in rows]==['SUBMIT_UNKNOWN','ACCEPTED_PENDING','FAILED','NOT_RUN']


def test_rejected_video_stops_all_new_production(tmp_path):
    b.write_once(tmp_path/'groups/low-control/reviews/cold_1.json',dict(decision='rejected',human_evidence='visible failure'))
    with pytest.raises(ValueError):m.require_no_rejection(tmp_path)


def test_recovery_timing_uses_original_submission_instead_of_recovery_start(tmp_path):
    b.write_once(tmp_path/'trials/warm_1/submission-start.json',dict(started_at_utc='2026-11-20T00:00:00+00:00',started_monotonic=10))
    value=m.record_trial_timing(tmp_path,'warm_1','recover',observed_monotonic=28)
    assert value['original_submit_to_technical_seconds']==18
    assert m.record_trial_timing(tmp_path,'warm_1','recover',observed_monotonic=100)==value
