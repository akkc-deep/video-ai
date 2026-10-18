import pytest

from production_helpers import model_server
from production_visual_helpers import comfy_server
from unit.test_production_inputs import production_config
from unit.test_production_storyboard import visual_handler
from unit.test_production_upscale import upscale_prefix


def test_three_completed_frames_interrupt_and_do_not_extract_or_decode_prefix(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,manager=upscale_prefix(production_config,run,paths,url,cu,monkeypatch)
        count=len(posts);original=s.record_unit
        completed=[]
        def stop(stage,uid,**kw):
            result=original(stage,uid,**kw)
            if stage=='upscale' and ':frame_' in uid and kw['status']=='completed':
                completed.append(uid)
                if len(completed)==3:raise KeyboardInterrupt('three durable frames')
            return result
        monkeypatch.setattr(s,'record_unit',stop)
        with pytest.raises(KeyboardInterrupt):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count+3 and len(completed)==3
        prefix={uid:s.snapshot()['units']['upscale'][uid] for uid in completed}
        monkeypatch.setattr(s,'record_unit',original)
        original_validate=v.validate_start_png
        def validate(path,**kw):
            assert kw['unit_id'] not in completed
            return original_validate(path,**kw)
        monkeypatch.setattr(v,'validate_start_png',validate)
        monkeypatch.setattr(v,'run_logged',lambda *a,**kw:pytest.fail('durable extraction must not repeat'))
        result=v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count+sum(c['source_frames'] for c in source['clips'])
        assert all(s.snapshot()['units']['upscale'][uid]==record for uid,record in prefix.items())
        assert sum(c['upscaled_frames'] for c in result['clips'])==sum(c['source_frames'] for c in source['clips'])


@pytest.mark.parametrize('point',['extract_checkpoint','frame_checkpoint','frame_copy','report'])
def test_durable_interruption_recovers_original_model_and_preserves_partial(production_config,runtime_run,monkeypatch,point):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,manager=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        if point in ('extract_checkpoint','frame_checkpoint'):
            original=s.write_checkpoint
            def write(stage,uid,**kw):
                result=original(stage,uid,**kw)
                if stage=='upscale' and (uid.endswith('_extract') if point=='extract_checkpoint' else ':frame_' in uid):
                    raise KeyboardInterrupt('checkpoint durable, cursor behind')
                return result
            monkeypatch.setattr(s,'write_checkpoint',write)
        elif point=='frame_copy':
            original=v._copy
            def copy(run,source,target):
                result=original(run,source,target)
                if 'output-frames' in target.parts:raise KeyboardInterrupt('copy durable, checkpoint absent')
                return result
            monkeypatch.setattr(v,'_copy',copy)
        else:
            original=s.complete_stage
            def complete(stage):
                if stage=='upscale':raise KeyboardInterrupt('report durable, cursor behind')
                return original(stage)
            monkeypatch.setattr(s,'complete_stage',complete)
        with pytest.raises(KeyboardInterrupt):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        preserved={p:p.read_bytes() for p in (run/'production/upscale').rglob('*.png')}
        if point in ('extract_checkpoint','frame_checkpoint'):monkeypatch.setattr(s,'write_checkpoint',original)
        elif point=='frame_copy':monkeypatch.setattr(v,'_copy',original)
        else:monkeypatch.setattr(s,'complete_stage',original)
        result=v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count+sum(c['source_frames'] for c in source['clips'])
        assert all(p.read_bytes()==raw for p,raw in preserved.items())
        assert s.snapshot()['stages']['upscale']['status']=='completed'
        if point=='frame_copy':
            assert len(list((run/'production/upscale/shot_0001').glob('*/output-frames/frame_000001.png')))==2
        assert sum(c['upscaled_frames'] for c in result['clips'])==sum(c['source_frames'] for c in source['clips'])


@pytest.mark.parametrize('mode',['upscale_lost','upscale_missing','upscale_multiple','upscale_malformed','upscale_malformed_json','upscale_invalid_utf8'])
def test_unknown_frame_unique_identity_get_recovery_without_repost(production_config,runtime_run,monkeypatch,mode):
    import video_ai.runtime.production_upscale as v
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True),mode=mode) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count+1
        if mode in ('upscale_lost','upscale_malformed','upscale_malformed_json','upscale_invalid_utf8'):
            original=s.record_unit
            def stop(stage,uid,**kw):
                if stage=='upscale' and uid=='shot_0001:frame_000002' and kw.get('request') is not None:raise KeyboardInterrupt()
                return original(stage,uid,**kw)
            monkeypatch.setattr(s,'record_unit',stop)
            with pytest.raises(KeyboardInterrupt):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
            assert s.snapshot()['units']['upscale']['shot_0001:frame_000001']['status']=='completed'
        else:
            with pytest.raises(ProductionRefused):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count+1 and '/history' in gets


def test_accepted_frame_resumes_original_prompt_id(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_upscale as v
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,_),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,source,_=upscale_prefix(production_config,run,paths,url,cu,monkeypatch);count=len(posts)
        original=ComfyClient.wait_for
        monkeypatch.setattr(ComfyClient,'wait_for',lambda *a,**kw:(_ for _ in ()).throw(KeyboardInterrupt('accepted')))
        with pytest.raises(KeyboardInterrupt):v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        saved=s.snapshot()['units']['upscale']['shot_0001:frame_000001']['request']['prompt_id']
        monkeypatch.setattr(ComfyClient,'wait_for',original)
        result=v.produce_upscaled_clips(f,source,state=s,manifest=m,paths=paths,logger=l)
        assert result['clips'][0]['frames'][0]['submission']['prompt_id']==saved
        assert len(posts)==count+sum(c['source_frames'] for c in source['clips'])
