from pathlib import Path

import pytest

from production_helpers import model_server,install_owned_services
from production_visual_helpers import comfy_server
from unit.test_production_inputs import production_config
from unit.test_production_storyboard import visual_handler
from unit.test_production_visuals import full_prefix


def upscale_prefix(config,run,paths,url,cu,monkeypatch):
    import json
    from video_ai.config import read_json,load_config
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.production_visuals import produce_start_images,produce_source_clips
    raw=read_json(config.config_file)
    raw['media']['timeline']=dict(sentence_pause_seconds=0,paragraph_pause_seconds=0,opening_seconds=0,closing_seconds=0)
    config_file=run/'short-upscale-test-config.json';config_file.write_text(json.dumps(raw),encoding='utf-8')
    f,s,m,l,t,b=full_prefix(load_config(config_file),run,paths,url,cu,monkeypatch)
    im=produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
    source=produce_source_clips(f,b,t,im,state=s,manifest=m,paths=paths,logger=l)
    manager=install_owned_services(monkeypatch)
    monkeypatch.setattr(v,'ServiceManager',manager);monkeypatch.setattr(v,'port_listening',lambda *a:False)
    return f,s,m,l,source,manager


def test_real_http_each_frame_checkpoint_and_zero_media_resume(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.logging import RunLogger
    from video_ai.config import read_json
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,manager=upscale_prefix(production_config,run,paths,url,cu,monkeypatch)
        baseline=len(posts);scans=[];original_glob=Path.glob
        def glob(path,pattern,*args,**kw):
            if path==l.path('http') and pattern=='*.request.json':scans.append(path)
            return original_glob(path,pattern,*args,**kw)
        monkeypatch.setattr(Path,'glob',glob)
        result=v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(scans)==1
        total=sum(c['source_frames'] for c in source['clips'])
        assert len(posts)==baseline+total and s.snapshot()['active_stage']=='composition'
        assert [c['upscaled_frames'] for c in result['clips']]==[c['source_frames'] for c in source['clips']]
        for clip in result['clips']:
            for i,row in enumerate(clip['frames'],1):
                assert row['frame_index']==i and row['source_frame_index']==i-1
                cp=read_json(Path(row['checkpoint_path']))
                assert cp['unit_id']==f'{clip["shot_id"]}:frame_{i:06d}'
                assert Path(row['checkpoint_path']).name==f'{clip["shot_id"]}_frame_{i:06d}.json'
                assert cp['payload']['parameters']['model_name']=='RealESRGAN_x4plus.pth'
                assert cp['outputs']['output']==row['output']
                assert row['submission']['prompt_id'] in h
        before_posts=len(posts);before_gets=len(gets);before={p for p in run.rglob('*') if p.is_file()}
        monkeypatch.setattr(v,'run_logged',lambda *a,**kw:pytest.fail('completed prefix must not extract/decode'))
        monkeypatch.setattr(v,'validate_start_png',lambda *a,**kw:pytest.fail('completed PNG must not decode'))
        assert v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)==result
        assert len(scans)==2
        assert len(posts)==before_posts and len(gets)==before_gets
        assert not any(p.suffix in ('.png','.mp4') for p in ({p for p in run.rglob('*') if p.is_file()}-before))


def test_external_service_refused_without_post_or_stop(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,manager=upscale_prefix(production_config,run,paths,url,cu,monkeypatch)
        count=len(posts);stops=len(manager.stopped)
        monkeypatch.setattr(v,'port_listening',lambda *a:True)
        with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count and len(manager.stopped)==stops


def test_input_copy_changed_during_startup_is_refused_before_post(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,manager=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        original=manager.ensure
        def ensure(self,spec):
            handle=original(self,spec)
            path=run/f'comfy/input/{run.name}/upscale/shot_0001/frame_000001.png'
            path.write_bytes(b'changed during service startup')
            return handle
        monkeypatch.setattr(manager,'ensure',ensure)
        with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count


def test_input_copy_changed_during_intent_refuses_before_post(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        original=s.record_unit
        def record(stage,uid,**kw):
            result=original(stage,uid,**kw)
            if stage=='upscale' and uid=='shot_0001:frame_000001' and kw.get('request',{}).get('state')=='intent':
                (run/f'comfy/input/{run.name}/upscale/shot_0001/frame_000001.png').write_bytes(b'changed during intent commit')
            return result
        monkeypatch.setattr(s,'record_unit',record)
        with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count
        with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count


def test_output_changed_after_decode_cannot_be_registered(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch)
        original=v.validate_start_png
        def validate(path,**kw):
            result=original(path,**kw)
            if Path(path).is_relative_to(run/'comfy/output'):Path(path).write_bytes(b'changed after verified full decode')
            return result
        monkeypatch.setattr(v,'validate_start_png',validate)
        with pytest.raises((ValueError,OSError)):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert not (run/'logs/production/checkpoints/upscale/shot_0001_frame_000001.json').exists()


def test_extracted_frame_changed_after_decode_refuses_before_post(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        original=v.validate_start_png
        def validate(path,**kw):
            result=original(path,**kw)
            if 'input-frames' in Path(path).parts:Path(path).write_bytes(b'changed after verified extraction decode')
            return result
        monkeypatch.setattr(v,'validate_start_png',validate)
        with pytest.raises((ValueError,OSError)):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count
        assert not (run/'logs/production/checkpoints/upscale/shot_0001_extract.json').exists()


def test_frozen_graph_changed_during_object_info_refuses_before_post(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        original=ComfyClient.validate_template
        def validate(client,template):
            result=original(client,template)
            Path(f.options['workflow_snapshots']['upscale']['path']).write_bytes(b'changed during object_info')
            return result
        monkeypatch.setattr(ComfyClient,'validate_template',validate)
        with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count


@pytest.mark.parametrize('change',['graph','input_copy'])
def test_input_identity_changed_during_wait_cannot_complete_frame(production_config,runtime_run,monkeypatch,change):
    import video_ai.runtime.production_upscale as v
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        original=ComfyClient.wait_for
        def wait(client,*args,**kw):
            result=original(client,*args,**kw)
            target=Path(f.options['workflow_snapshots']['upscale']['path']) if change=='graph' else run/f'comfy/input/{run.name}/upscale/shot_0001/frame_000001.png'
            target.write_bytes(b'changed during model wait')
            return result
        monkeypatch.setattr(ComfyClient,'wait_for',wait)
        with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count+1
        assert not (run/'logs/production/checkpoints/upscale/shot_0001_frame_000001.json').exists()


@pytest.mark.parametrize('mode',['upscale_broken_png','upscale_wrong_size','upscale_failed'])
def test_invalid_upscale_result_terminal_no_second_post(production_config,runtime_run,monkeypatch,mode):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True),mode=mode) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        for _ in range(2):
            with pytest.raises(RuntimeError):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count+1
        assert s.snapshot()['units']['upscale']['shot_0001:frame_000001']['status']=='failed'
