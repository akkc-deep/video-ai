"""Only new explicit whole frames prepare owned service before frame tracking."""
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('mode,pending,replay,prepared',[
    ('whole_scene_v1',False,False,True),
    ('segmented_v1',False,False,False),
    ('whole_scene_v1',True,False,False),
    ('whole_scene_v1',False,True,False),
])
def test_service_phase_precedes_only_fresh_whole_tracking(tmp_path,monkeypatch,mode,pending,replay,prepared):
    import video_ai.runtime.production_scene_upscale as producer
    import video_ai.runtime.scene_upscale_transactions as protocol
    import video_ai.runtime.production_inputs as inputs
    import video_ai.runtime._scene_revision_readers as revisions
    import video_ai.adapters.scene_comfy as adapter
    clock=[0.];entries=[];services=[];calls=[];saved={}
    clip={'clip_id':'scene_0001_clip_0001'};row={'frame_id':clip['clip_id']+':frame_000001','retained_frame_index':0}
    class Store:
        run_dir=tmp_path;root=tmp_path/'production/scene-upscale';paths=None;lock=object()
        def assert_write(self):pass
        def verify_global(self):pass
        def read(self,name):
            if Path(name).name=='intent.json':return {'original':'pending'} if pending else None
            return saved.get(str(name))
        def write(self,name,value):saved[str(name)]=value
        def frame_dir(self,frame):return self.root/'frame_000001'
        def capture_guard(self,*args):return lambda:None
    store=Store();frozen=SimpleNamespace(config=SimpleNamespace(
        raw={'scene_rendering':{'mode':mode}},timeouts={'upscale_frame':180,'comfy_request':180},
        services={'comfyui':'http://127.0.0.1:8188'}))
    context=dict(store=store,frozen=frozen,rows=[row],scene_clips={'clips':[clip]},inputs={},template=object())
    class Service:
        def __init__(self,*args):self.ready=False;self.closed=False;services.append(self)
        def ensure(self):
            calls.append('ensure')
            if not self.ready:clock[0]+=78;self.ready=True
        def close(self):self.closed=True
    class Client:
        def __init__(self,*args,**kwargs):self.options=kwargs
    monkeypatch.setattr(adapter,'SceneComfyClient',Client)
    monkeypatch.setattr(inputs,'check_stage_space',lambda *a,**kw:None)
    monkeypatch.setattr(revisions,'inherited_frame',lambda *a:None)
    monkeypatch.setattr(producer,'graph_for',lambda *a:{'5':{}})
    monkeypatch.setattr(producer,'clip_rows',lambda *a:[row])
    monkeypatch.setattr(producer,'validate_upscale_frames',lambda *a,**kw:[])
    monkeypatch.setattr(producer,'validate_frame',lambda *a,**kw:{'complete':True} if replay else None)
    monkeypatch.setattr(producer,'_extract',lambda *a:{'frames':[{'image':{}}]})
    monkeypatch.setattr(producer,'_copy',lambda *a:{'target':{}})
    monkeypatch.setattr(producer,'expected_request',lambda *a:{'frame_id':row['frame_id']})
    monkeypatch.setattr(producer,'validate_png',lambda *a,**kw:None)
    monkeypatch.setattr(producer,'complete_value',lambda *a:{})
    monkeypatch.setattr(producer,'_result',lambda context,status:status)
    def tracking(store,request,graph,*,client,ensure_service,timeout,**kwargs):
        entries.append((clock[0],timeout,client.options))
        ensure_service();return {'output':{}}
    monkeypatch.setattr(protocol,'recover_or_submit_scene_frame',tracking)
    assert producer._produce(context,SimpleNamespace(),None,Service)=='upscale_ready'
    if replay:
        assert entries==services==[] and calls==[]
    else:
        assert entries[0][0]==(78 if prepared else 0)
        assert entries[0][1]==180
        assert entries[0][2].get('send_checks_only',False)==(mode=='whole_scene_v1')
        assert len(calls)==(2 if prepared else 1)
        assert len(services)==1 and services[0].closed
