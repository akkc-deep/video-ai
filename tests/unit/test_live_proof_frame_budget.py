"""Measured continuity-check cost must fit the existing frame protocol budget."""
from test_scene_upscale_transactions import transaction,Client
import pytest


@pytest.mark.parametrize('proof_seconds,can_finish',[(15.968,False),(4.375,True)])
def test_frame_protocol_keeps_original_budget_with_measured_live_proof_cost(transaction,monkeypatch,proof_seconds,can_finish):
    from video_ai.runtime import scene_upscale_transactions as module
    store,request,graph,template=transaction
    client=Client(store,request,graph);clock=[0.0];checks=[];network=[]
    def proof():checks.append(clock[0]);clock[0]+=proof_seconds
    store.capture_guard=lambda *_:proof
    original_write,original_bytes=store.write,store.write_bytes
    writing_json=[False]
    def write(name,value):
        proof();writing_json[0]=True
        try:return original_write(name,value)
        finally:writing_json[0]=False
    def write_bytes(name,value):
        if not writing_json[0]:proof()
        return original_bytes(name,value)
    store.write,store.write_bytes=write,write_bytes
    client.ownership_check=proof
    for name in ('object_info','submit','queue','history'):
        original=getattr(client,name)
        def guarded(*args,_name=name,_original=original,**kwargs):
            client.ownership_check();network.append((_name,clock[0]))
            return _original(*args,**kwargs)
        monkeypatch.setattr(client,name,guarded)
    def ensure():proof();clock[0]+=30;proof()
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    def track():return module.recover_or_submit_scene_frame(store,request,graph,client=client,
        template=template,ensure_service=ensure,logger=None,timeout=180)
    if can_finish:
        result=track();assert result['prompt_id']==client.pid and client.posts==1
    else:
        with pytest.raises(module.SceneSubmitUnknown):track()
        assert client.posts==0
    assert checks and all(at<180 for _,at in network)
    print(dict(proof_seconds=proof_seconds,checks=len(checks),elapsed=clock[0],
               last_network=network[-1] if network else None,posts=client.posts))
