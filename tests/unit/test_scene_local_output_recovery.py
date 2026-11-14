"""Explicit local output proof never invents original server completion."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_scene_comfy_transactions import transaction, Client
from video_ai.planning.production_scenes import canonical_digest
from video_ai.runtime.production_state import ProductionRefused


@pytest.fixture
def local_case(transaction, runtime_run, monkeypatch):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    from video_ai.runtime.manifest import now
    from video_ai.runtime.processes import CommandResult
    store, request, graph, template = transaction
    graph['108']['inputs'].update(fps=16, seed=9007199254740993)
    graph['97'] = dict(class_type='LoadImage', inputs=dict(image='run/scene_clips/scene_0001_clip_0001/start.png'))
    request['graph_sha256']=canonical_digest(graph)
    store.frozen.config = runtime_run[1]; store.paths = runtime_run[2]
    image = store.run_dir/'comfy/input'/request['run_id']/'scene_clips'/request['clip_id']/'start.png'
    image.parent.mkdir(parents=True); image.write_bytes(b'original input image')
    input_record = dict(schema_version=2, run_id=request['run_id'], clip_id=request['clip_id'], target=store.artifact(image))
    store.write(store.clip_dir(request['clip_id'])/'input.json', input_record)
    request['input_sha256'] = canonical_digest(input_record)
    client = Client(store, request, graph)
    client.queue = lambda **kw: client.response(dict(queue_running=[[1,client.pid,graph,dict(client_id=client.cid),['108']]],queue_pending=[]))
    client.history = lambda *a,**kw: (_ for _ in ()).throw(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    calls = []; probes = []; embedded = deepcopy(graph)
    def queue(**kw):
        calls.append('queue'); return client.response(dict(queue_running=[],queue_pending=[]))
    def history(*a,**kw):
        calls.append('history'); return client.response({})
    client.queue=queue; client.history=history
    def probe(args, *, cwd, env, timeout, logger, stage, unit_id):
        probes.append(args)
        stdout=logger.save_bytes('metadata.stdout',json.dumps(dict(format=dict(tags=dict(prompt=json.dumps(embedded))))).encode())
        stderr=logger.save_bytes('metadata.stderr',b'')
        return CommandResult(tuple(args),cwd,0,False,stdout,stderr,now(),now())
    monkeypatch.setattr('video_ai.runtime.processes.run_logged',probe)
    return SimpleNamespace(store=store,request=request,graph=graph,client=client,template=template,calls=calls,probes=probes,embedded=embedded,image=image)


def recover(case, **kwargs):
    from video_ai.runtime.scene_local_output_recovery import recover_local_scene_output
    return recover_local_scene_output(case.store,case.request,case.graph,client=case.client,logger=None,authorization='User approved local recovery on 2026-11-13',**kwargs)


def test_local_receipt_success_and_replay_without_network_or_probe(local_case):
    from video_ai.runtime.scene_comfy_transactions import validate_scene_submission
    c=local_case; result=recover(c)
    assert set(result)==set('schema_version run_id clip_id intent_sha256 accepted_sha256 prompt_id local_recovery_evidence output'.split())
    assert result['output']==c.store.artifact(c.client.output)
    receipt=json.loads(Path(result['local_recovery_evidence']['path']).read_bytes())
    assert receipt['algorithm']=='owned_output_metadata_v1'
    assert len(receipt['absence_evidence'])==2 and receipt['authorization']
    assert c.calls==['queue','history','queue','history'] and len(c.probes)==1 and c.client.posts==1
    assert validate_scene_submission(c.store,c.request,c.graph)==result
    assert validate_scene_submission(c.store,c.request,c.graph,media=False)==result
    assert recover(c)==result
    assert len(c.calls)==4 and len(c.probes)==1


@pytest.mark.parametrize('kind',['active','complete_history','wrong_client','wrong_number','wrong_prompt','missing_queue','terminal','wrong_input','ambiguous','wrong_prefix','graph','bool','lossy_seed','no_authorization'])
def test_refuses_unproven_or_live_original(local_case,kind):
    c=local_case; directory=c.store.clip_dir(c.request['clip_id'])
    if kind=='active':
        c.client.queue=lambda **kw:c.client.response(dict(queue_running=[[1,c.client.pid,c.graph,dict(client_id=c.client.cid),['108']]],queue_pending=[]))
    elif kind=='complete_history':
        c.client.history=lambda *a,**kw:Client.history(c.client,*a,**kw)
    elif kind in ('wrong_client','wrong_number','wrong_prompt','missing_queue'):
        for path in (directory/'http').glob('*.body'):
            value=json.loads(path.read_bytes() or b'{}')
            if 'queue_running' not in value:continue
            if kind=='missing_queue':value['queue_running']=[]
            elif kind=='wrong_client':value['queue_running'][0][3]['client_id']='wrong'
            elif kind=='wrong_number':value['queue_running'][0][0]=2
            else:value['queue_running'][0][1]='wrong'
            path.write_text(json.dumps(value))
            meta=path.with_name(path.name.removesuffix('.body')+'.response.json'); row=json.loads(meta.read_bytes()); row['body']=c.store.artifact(path);meta.write_text(json.dumps(row))
    elif kind=='terminal':
        from video_ai.runtime.manifest import now
        intent=c.store.read(directory/'intent.json')
        c.store.write(directory/'terminal.json',dict(schema_version=2,run_id='run',clip_id=c.request['clip_id'],intent_sha256=canonical_digest(intent),status='invalid_media',evidence=[],reason='retained failure'))
    elif kind=='wrong_input':c.image.write_bytes(b'changed image')
    elif kind=='ambiguous':c.client.output.with_name('attempt_0001_00002.mp4').write_bytes(b'another output')
    elif kind=='wrong_prefix':c.client.output.rename(c.client.output.with_name('other_00001.mp4'))
    elif kind=='graph':c.embedded['108']['inputs']['seed']=5
    elif kind=='bool':c.embedded['108']['inputs']['fps']=True
    elif kind=='lossy_seed':c.embedded['108']['inputs']['seed']=float(9007199254740993)
    elif kind=='no_authorization':
        from video_ai.runtime.scene_local_output_recovery import recover_local_scene_output
        with pytest.raises(ProductionRefused):recover_local_scene_output(c.store,c.request,c.graph,client=c.client,logger=None,authorization='')
        return
    with pytest.raises((ProductionRefused,AssertionError)):
        recover(c)
    assert c.store.read(directory/'submission.json') is None and c.client.posts==1


@pytest.mark.parametrize('kind',['output','input','metadata','receipt','http','command'])
def test_readonly_reconstruction_rejects_tampering(local_case,kind):
    from video_ai.runtime.scene_comfy_transactions import validate_scene_submission
    c=local_case; result=recover(c); receipt=Path(result['local_recovery_evidence']['path'])
    value=json.loads(receipt.read_bytes())
    if kind=='output':c.client.output.write_bytes(b'changed output')
    elif kind=='input':c.image.write_bytes(b'changed input')
    elif kind=='receipt':receipt.write_text('{}')
    elif kind=='http':
        response=Path(value['absence_evidence'][0]['queue']['path']); body=json.loads(response.read_bytes())['body']['path'];Path(body).write_bytes(b'{}')
    elif kind=='command':Path(value['metadata_evidence']['path']).write_text('{}')
    else:
        command=json.loads(Path(value['metadata_evidence']['path']).read_bytes());Path(command['stdout']['path']).write_bytes(b'{}')
    with pytest.raises((ProductionRefused,AssertionError)):
        validate_scene_submission(c.store,c.request,c.graph)
    assert len(c.probes)==1


def test_normal_history_stays_normal(local_case):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    c=local_case; c.client.history=lambda *a,**kw:Client.history(c.client,*a,**kw)
    result=recover_or_submit_scene_clip(c.store,c.request,c.graph,client=c.client,template=c.template,ensure_service=lambda:None,logger=None,timeout=1)
    assert 'history_evidence' in result and 'local_recovery_evidence' not in result
    assert recover(c)==result and not c.probes


def test_exact_numeric_metadata_normalization_and_unrelated_active_jobs(local_case):
    c=local_case; c.embedded['108']['inputs']['fps']=16.0
    c.client.queue=lambda **kw:c.client.response(dict(queue_running=[[4,'unrelated',{},dict(client_id='other'),[]]],queue_pending=[]))
    assert recover(c)['output']==c.store.artifact(c.client.output)


def test_receipt_recovers_interrupted_submission_write_without_new_probe(local_case):
    c=local_case; original=c.store.write
    def interrupted(path, value):
        if Path(path).name=='submission.json':raise KeyboardInterrupt()
        return original(path,value)
    c.store.write=interrupted
    with pytest.raises(KeyboardInterrupt):recover(c)
    c.store.write=original
    assert recover(c)['output']==c.store.artifact(c.client.output)
    assert len(c.probes)==1 and len(c.calls)==4


def test_metadata_only_read_does_not_require_original_media_bytes(local_case):
    from video_ai.runtime.scene_comfy_transactions import validate_scene_submission
    c=local_case; result=recover(c)
    c.image.unlink();c.client.output.unlink()
    assert validate_scene_submission(c.store,c.request,c.graph,media=False)==result
    assert len(c.probes)==1


def rebind_receipt(c, submission, receipt):
    path=Path(submission['local_recovery_evidence']['path']);path.write_text(json.dumps(receipt))
    submission['local_recovery_evidence']=c.store.artifact(path)
    (c.store.clip_dir(c.request['clip_id'])/'submission.json').write_text(json.dumps(submission))


def test_rebound_metadata_stream_boolean_size_is_not_valid_evidence(local_case):
    from video_ai.runtime.scene_comfy_transactions import validate_scene_submission
    c=local_case; submission=recover(c)
    receipt=json.loads(Path(submission['local_recovery_evidence']['path']).read_bytes())
    command_path=Path(receipt['metadata_evidence']['path']);command=json.loads(command_path.read_bytes())
    command['stderr']['bytes']=False
    command_path.write_text(json.dumps(command));receipt['metadata_evidence']=c.store.artifact(command_path)
    rebind_receipt(c,submission,receipt)
    with pytest.raises(ProductionRefused):validate_scene_submission(c.store,c.request,c.graph)


def test_comfy_loadimage_fingerprint_matches_owned_input(local_case):
    c=local_case
    c.embedded['97']['is_changed']=[c.store.artifact(c.image)['sha256']]
    assert recover(c)['output']==c.store.artifact(c.client.output)


@pytest.mark.parametrize('kind',['wrong_hash','wrong_node','extra_field'])
def test_unproven_comfy_fingerprint_or_extra_graph_field_is_rejected(local_case,kind):
    c=local_case
    if kind=='wrong_hash':c.embedded['97']['is_changed']=['0'*64]
    elif kind=='wrong_node':c.embedded['108']['is_changed']=[c.store.artifact(c.image)['sha256']]
    else:c.embedded['97']['other_runtime_field']='unproven'
    with pytest.raises(ProductionRefused):recover(c)


def test_metadata_only_interruption_replays_original_evidence(local_case):
    c=local_case; original=c.store.write
    def interrupted(path,value):
        if Path(path).name=='local-output-recovery.json':raise KeyboardInterrupt()
        return original(path,value)
    c.store.write=interrupted
    with pytest.raises(KeyboardInterrupt):recover(c)
    c.store.write=original
    assert recover(c)['output']==c.store.artifact(c.client.output)
    assert len(c.probes)==1 and len(c.calls)==4
