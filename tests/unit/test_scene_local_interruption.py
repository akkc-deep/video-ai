"""Operator reboot evidence releases revision blocking without inventing success."""
from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from test_scene_comfy_transactions import transaction
from video_ai.planning.production_scenes import canonical_digest
from video_ai.runtime.production_state import ProductionRefused
from video_ai.runtime import scene_comfy_transactions as tx


@pytest.fixture
def interrupted(transaction, monkeypatch):
    store, request, graph, template = transaction
    folder = store.clip_dir(request['clip_id'])
    intent = dict(schema_version=2, run_id=request['run_id'], clip_id=request['clip_id'],
        request_sha256=canonical_digest(request), graph_sha256=request['graph_sha256'],
        input_sha256=request['input_sha256'], parent_sha256=None, attempt_id=str(uuid4()),
        client_id=str(uuid4()), output_prefix=tx._prefix(request), created_at='2026-01-01T10:01:00+00:00')
    for name, value in [('request', request), ('graph', graph), ('intent', intent)]:
        store.write(folder/(name+'.json'), value)
    clock = ['2026-01-01T10:01:01+00:00']
    monkeypatch.setattr(tx, 'now', lambda: clock[0])
    pid = str(uuid4())
    def capture(route, value, *, status=200):
        return tx._record_http(store, request, intent, 'POST' if route=='/prompt' else 'GET', route,
            lambda _: dict(status=status, headers={'Content-Type':'application/json'}, body=json.dumps(value).encode()), 1, graph)['evidence']
    accepted = tx._accept(store, request, intent, pid, 1,
        capture('/prompt', dict(prompt_id=pid, number=1, node_errors={})))
    clock[0] = '2026-01-01T12:00:00+00:00'
    pairs = []
    for minute in (0, 1):
        clock[0] = f'2026-01-01T12:0{minute}:00+00:00'
        queue = capture('/queue', dict(queue_running=[], queue_pending=[]))
        clock[0] = f'2026-01-01T12:0{minute}:01+00:00'
        pairs.append(dict(queue=queue, history=capture('/history/'+pid, {})))
    stderr = folder/'evidence/original.stderr'
    store.write_bytes(stderr, b'Wan sampling\r 80%|######| 20/25 [00:01]\r 84%|######| 21/25 [00:02]\n')
    event = dict(time='2026-01-01T10:00:00+00:00', stage='preflight', unit_id=None,
        event='service_starting', details=dict(name='comfyui', owned=True, pid=42,
        url='http://127.0.0.1:8188', stderr_path=str(stderr),
        args=['python', '--output-directory', str(store.run_dir/'comfy/output')]))
    reboot = dict(run_id=request['run_id'], previous_service=dict(pid=42, process_absent=True),
        os_boot_time_local='2026-01-01T11:00:00+00:00',
        interrupted_clip=dict(clip_id=request['clip_id'], prompt_id=pid))
    boot = dict(boot_time=reboot['os_boot_time_local'], observed_at='2026-01-01T11:30:00+00:00',
        provenance='Win32_OperatingSystem.LastBootUpTime observed by operator')
    def artifact(name, value):
        return store.artifact(store.write(folder/('evidence/'+name+'.json'), value))
    kwargs = dict(authorization='User explicitly authorized replacement after reboot',
        service_event=artifact('service-event', event), service_stderr=store.artifact(stderr),
        reboot=artifact('reboot', reboot), boot_observation=artifact('boot', boot), absence_pairs=pairs)
    return SimpleNamespace(store=store, request=request, graph=graph, template=template,
        folder=folder, pid=pid, kwargs=kwargs, capture=capture, artifact=artifact,
        event=event, reboot=reboot, boot=boot, clock=clock)


def record(c, **overrides):
    from video_ai.runtime.scene_local_interruption import record_local_interruption
    return record_local_interruption(c.store, c.request, c.graph, **dict(c.kwargs, **overrides))


def test_explicit_receipt_preserves_unknown_and_is_restart_safe(interrupted):
    from video_ai.runtime.scene_local_interruption import validate_local_interruption
    c = interrupted
    original = {p: p.read_bytes() for p in c.folder.rglob('*') if p.is_file()}
    assert validate_local_interruption(c.store, c.request, c.graph) is None
    receipt = record(c)
    assert receipt['classification']=='owned_service_rebooted_before_output'
    assert record(c)==receipt
    assert validate_local_interruption(c.store, c.request, c.graph)==receipt
    assert all(p.read_bytes()==raw for p, raw in original.items())
    assert not any((c.folder/n).exists() for n in ('submission.json','clip.json','terminal.json'))
    with pytest.raises(ProductionRefused): record(c, authorization='Different authorization')
    # Unrelated subsequent GETs do not change the exact static evidence binding.
    c.clock[0]='2026-01-02T12:00:00+00:00'
    c.capture('/queue', dict(queue_running=[], queue_pending=[]))
    assert validate_local_interruption(c.store, c.request, c.graph)==receipt
    class Client:
        request_timeout=1
        def queue(self, **kw): return dict(status=200,headers={'Content-Type':'application/json'},body=b'{"queue_running":[],"queue_pending":[]}')
        def history(self, *args, **kw): return dict(status=200,headers={'Content-Type':'application/json'},body=b'{}')
    with pytest.raises(tx.SceneSubmitUnknown):
        tx.recover_or_submit_scene_clip(c.store,c.request,c.graph,client=Client(),template=c.template,
            ensure_service=lambda:None,logger=None,timeout=1)
    assert tx.validate_scene_submission(c.store,c.request,c.graph) is None


@pytest.mark.parametrize('kind', ['authorization','remote','external','pid','event_time','run','clip','prompt',
    'boot_before_intent','boot_observation','complete_progress','no_progress','output','clip_record',
    'submission','terminal','one_pair','duplicate','queue_active','history_exists','malformed_queue',
    'failed_http','malformed_http','preboot_pair','wrong_artifact','extra_field'])
def test_rejects_unproven_interruption_without_publishing(interrupted, kind):
    c = interrupted; kw = deepcopy(c.kwargs)
    if kind=='authorization': kw['authorization']='  '
    elif kind in ('remote','external','pid','event_time'):
        event=deepcopy(c.event)
        if kind=='remote': event['details']['url']='https://example.com:8188'
        if kind=='external': event['details']['owned']=False
        if kind=='pid': event['details']['pid']=43
        if kind=='event_time': event['time']='2026-01-01T10:02:00+00:00'
        kw['service_event']=c.artifact(kind,event)
    elif kind in ('run','clip','prompt','boot_before_intent'):
        reboot=deepcopy(c.reboot)
        if kind=='run': reboot['run_id']='another'
        if kind=='clip': reboot['interrupted_clip']['clip_id']='other'
        if kind=='prompt': reboot['interrupted_clip']['prompt_id']=str(uuid4())
        if kind=='boot_before_intent': reboot['os_boot_time_local']='2026-01-01T09:00:00+00:00'
        kw['reboot']=c.artifact(kind,reboot)
    elif kind=='boot_observation': kw['boot_observation']=c.artifact(kind,dict(c.boot,boot_time='2026-01-01T09:00:00+00:00'))
    elif kind in ('complete_progress','no_progress'):
        p=c.folder/'evidence/other.stderr'; p.write_bytes(b'100%|######| 25/25 [00:02]' if kind=='complete_progress' else b'no progress')
        kw['service_stderr']=c.store.artifact(p)
        kw['service_event']=c.artifact(kind,dict(c.event,details=dict(c.event['details'],stderr_path=str(p))))
    elif kind=='output':
        p=c.store.run_dir/'comfy/output'/tx._prefix(c.request); p.parent.mkdir(parents=True,exist_ok=True); p.with_name(p.name+'_00001.mp4').write_bytes(b'output')
    elif kind in ('clip_record','submission','terminal'): c.store.write(c.folder/({'clip_record':'clip'}.get(kind,kind)+'.json'),{})
    elif kind=='one_pair': kw['absence_pairs']=kw['absence_pairs'][:1]
    elif kind=='duplicate': kw['absence_pairs']=[kw['absence_pairs'][0]]*2
    elif kind in ('queue_active','history_exists','malformed_queue','failed_http','malformed_http','preboot_pair'):
        if kind=='preboot_pair': c.clock[0]='2026-01-01T10:30:00+00:00'
        q=dict(queue_running=[],queue_pending=[]); h={}
        if kind=='queue_active': q['queue_running']=[[1,c.pid,c.graph,{},['108']]]
        if kind=='history_exists': h={c.pid:{}}
        if kind=='malformed_queue': q['queue_running']=[['malformed']]
        if kind=='malformed_http': q=[]
        kw['absence_pairs'][1]=dict(queue=c.capture('/queue',q,status=503 if kind=='failed_http' else 200),history=c.capture('/history/'+c.pid,h))
    elif kind=='wrong_artifact': kw['absence_pairs'][0]['queue']=kw['reboot']
    elif kind=='extra_field': kw['absence_pairs'][0]['extra']=True
    with pytest.raises((ProductionRefused, AssertionError)): record(c,**kw)
    assert not (c.folder/'local-interruption.json').exists()


def test_candidate_resumes_after_authoritative_write_interruption(interrupted, monkeypatch):
    c=interrupted; original=c.store.write
    def stop(path,value):
        if path.name=='local-interruption.json': raise KeyboardInterrupt()
        return original(path,value)
    monkeypatch.setattr(c.store,'write',stop)
    with pytest.raises(KeyboardInterrupt): record(c)
    candidate=c.store.read(c.folder/'local-interruption-candidate.json')
    assert candidate and not (c.folder/'local-interruption.json').exists()
    monkeypatch.setattr(c.store,'write',original)
    assert record(c)==candidate


@pytest.mark.parametrize('receipt_state',['absent','valid','malformed'])
def test_revision_snapshot_only_releases_valid_interruption_and_never_reuses_clip(interrupted, monkeypatch, receipt_state):
    from video_ai.runtime import production_scene_revision as revision
    from video_ai.runtime import _scene_revision_origins as origins
    from video_ai.runtime import image_selection_records as images
    from video_ai.runtime import scene_clip_records as clips
    from video_ai.planning.production_timeline import ProductionTimeline
    c=interrupted
    if receipt_state=='valid': record(c)
    if receipt_state=='malformed': c.store.write(c.folder/'local-interruption.json',dict(classification='owned_service_rebooted_before_output'))
    budget=dict(clip_id=c.request['clip_id'],parent_clip_id=None,retained_frames=0)
    plan=dict(scenes=[],clips=[budget],batches=[])
    context=dict(store=c.store,rows=[dict(budget=budget)])
    source=SimpleNamespace(options=dict(script_path=str(c.store.run_dir/'inputs/script.txt')))
    monkeypatch.setattr(origins,'common',lambda _:dict(units=[],timeline={}))
    monkeypatch.setattr(origins,'inherited',lambda *a:None)
    monkeypatch.setattr(ProductionTimeline,'from_dict',lambda _:None)
    monkeypatch.setattr(images,'load_committed_plan',lambda *a:({},plan))
    monkeypatch.setattr(images,'load_accepted_batches',lambda *a:[])
    monkeypatch.setattr(images,'_choices',lambda _: {})
    monkeypatch.setattr(revision,'_source_execution',lambda *a:None)
    monkeypatch.setattr(revision,'identity_from_options',lambda *a,**k:{})
    monkeypatch.setattr(clips,'scene_context',lambda *a:context)
    monkeypatch.setattr(clips,'validate_clip',lambda *a:None)
    monkeypatch.setattr(clips,'graph_for',lambda *a:c.graph)
    monkeypatch.setattr(c.store,'write',lambda *a:pytest.fail('snapshot validator wrote a record'))
    if receipt_state=='malformed':
        with pytest.raises(ProductionRefused): revision._admitted_snapshot(source)
    else:
        snapshot=revision._admitted_snapshot(source)
        assert snapshot['clip_nodes']==[dict(clip_id=c.request['clip_id'],record=None,acceptance=None,status='pending')]
        assert len(snapshot['pending_effects'])==(0 if receipt_state=='valid' else 1)


@pytest.mark.parametrize('field',['request_sha256','graph_sha256','intent_sha256','accepted_sha256','prompt_id','extra'])
def test_receipt_tampering_is_rejected_readonly(interrupted, monkeypatch, field):
    from video_ai.runtime.scene_local_interruption import validate_local_interruption
    c=interrupted; receipt=record(c); receipt[field]='altered'
    (c.folder/'local-interruption.json').write_text(json.dumps(receipt),encoding='utf-8')
    monkeypatch.setattr(c.store,'write',lambda *a:pytest.fail('validator wrote'))
    with pytest.raises(ProductionRefused): validate_local_interruption(c.store,c.request,c.graph)


def test_retained_preboot_original_history_cannot_be_reclassified(interrupted):
    c=interrupted; c.clock[0]='2026-01-01T10:30:00+00:00'
    c.capture('/history/'+c.pid,{c.pid:dict(prompt=[1,c.pid,c.graph,{},['108']],outputs={})})
    with pytest.raises(ProductionRefused,match='history'): record(c)


def test_later_unbound_malformed_or_failed_views_do_not_invalidate_bound_absence(interrupted):
    from video_ai.runtime.scene_local_interruption import validate_local_interruption
    c=interrupted; receipt=record(c)
    c.clock[0]='2026-01-02T12:00:00+00:00'
    c.capture('/queue',{})
    c.capture('/history/'+c.pid,[],status=503)
    assert validate_local_interruption(c.store,c.request,c.graph)==receipt
