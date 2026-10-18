import pytest
from production_visual_helpers import comfy_server
from production_helpers import model_server
from unit.test_production_storyboard import visual_handler
from unit.test_production_visuals import full_prefix
from unit.test_production_inputs import production_config


@pytest.mark.parametrize('mode',['lost','missing','multiple'])
def test_ambiguous_comfy_unique_graph_client_only_get_recovery(production_config,runtime_run,monkeypatch,mode):
    from video_ai.runtime.production_visuals import produce_start_images
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True),mode=mode) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        with pytest.raises(ProductionRefused):produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==1
        if mode=='lost':
            # Finish only the original shot before cancelling the next unit.
            original=s.record_unit
            def stop_next(stage,uid,**kw):
                if uid=='shot_0002' and kw.get('request') is not None:raise KeyboardInterrupt()
                return original(stage,uid,**kw)
            monkeypatch.setattr(s,'record_unit',stop_next)
            with pytest.raises(KeyboardInterrupt):produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
            assert s.snapshot()['units']['start_images']['shot_0001']['status']=='completed'
            assert s.snapshot()['units']['start_images']['shot_0001']['request']['prompt_id'] in h
        else:
            with pytest.raises(ProductionRefused):produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==1 and '/history' in gets


def test_local_history_key_must_equal_embedded_original_prompt(production_config,runtime_run,monkeypatch):
    import json
    from uuid import uuid4
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.production_visuals import produce_start_images
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        original=ComfyClient.wait_for
        def interrupt(*a,**kw):
            original(*a,**kw)
            raise KeyboardInterrupt('complete history but no checkpoint')
        monkeypatch.setattr(ComfyClient,'wait_for',interrupt)
        with pytest.raises(KeyboardInterrupt):produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        monkeypatch.setattr(ComfyClient,'wait_for',original)
        target=next(p for p in l.path('http').glob('*.request.json') if '/history/' in json.loads(p.read_bytes())['url'])
        token=target.name.removesuffix('.request.json');body=target.with_name(token+'.body');meta=target.with_name(token+'.response.json')
        data=json.loads(body.read_bytes());entry=next(iter(data.values()));raw=json.dumps({str(uuid4()):entry}).encode();body.write_bytes(raw)
        metadata=json.loads(meta.read_bytes());metadata['bytes']=len(raw);meta.write_text(json.dumps(metadata),encoding='utf-8')
        with pytest.raises(ProductionRefused):produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==1


def test_changed_original_http_request_blocks_accepted_recovery(production_config,runtime_run,monkeypatch):
    import json
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.production_visuals import produce_start_images
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        original=ComfyClient.wait_for
        monkeypatch.setattr(ComfyClient,'wait_for',lambda *a,**kw:(_ for _ in ()).throw(KeyboardInterrupt('after acceptance')))
        with pytest.raises(KeyboardInterrupt):produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        monkeypatch.setattr(ComfyClient,'wait_for',original)
        target=next(p for p in l.path('http').glob('*.request.json') if json.loads(p.read_bytes())['url']==cu+'/prompt')
        data=json.loads(target.read_bytes());data['json_body']['client_id']='foreign replacement';target.write_text(json.dumps(data),encoding='utf-8')
        with pytest.raises(ProductionRefused):produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==1
