import json
from pathlib import Path

import pytest

from unit.test_production_inputs import production_config
from unit.test_production_storyboard import visual_prefix,visual_handler
from production_helpers import model_server,config_for_server
from production_visual_helpers import comfy_server,configure_comfy,install_visual_owned


def full_prefix(config,run,paths,ollama_url,comfy_url,monkeypatch):
    from video_ai.runtime.production_storyboard import produce_storyboard
    config=configure_comfy(config_for_server(config,ollama_url,run),comfy_url,run)
    f,s,m,l,u,t,p=visual_prefix(config,run,paths,ollama_url,monkeypatch)
    install_visual_owned(monkeypatch)
    board=produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
    return f,s,m,l,t,board


def test_real_production_gate_blocks_wan_and_freezes_review_evidence(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_visuals as v
    from video_ai.runtime.production_visual_review import require_image_review,review_binding
    from video_ai.runtime.production_state import ProductionRefused,write_exclusive
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        images=v.produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        monkeypatch.setattr(v,'require_image_review',require_image_review)
        count=len(posts)
        with pytest.raises(ProductionRefused,match='visual review required'):
            v.produce_source_clips(f,b,t,images,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==count and s.snapshot()['stages']['source_clips']['status']=='pending'
        # Test-only synthetic author receipt; this tests binding and admission,
        # not the semantic quality of the test PNGs or testsrc video.
        record=dict(schema_version=1,review_method='human_image',reviewer='synthetic-test-only',viewed_images=True,
            verdict='passed',reason='Test-only receipt for admission contract.',binding=review_binding(b,images))
        review=run/'production/visual-review.json';write_exclusive(review,record)
        v.produce_source_clips(f,b,t,images,state=s,manifest=m,paths=paths,logger=l)
        saved=json.loads((run/'production/source-clips.json').read_text(encoding='utf-8'))
        assert {'visual_review','accepted_visual_review'}<=set(saved['input_records'])
        accepted=(run/'production/visual-review-accepted.json').read_bytes()
        after=len(posts);record['reason']='Changed after generation';review.write_text(json.dumps(record),encoding='utf-8')
        with pytest.raises(ProductionRefused,match='changed'):
            v.produce_source_clips(f,b,t,images,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==after and (run/'production/visual-review-accepted.json').read_bytes()==accepted


@pytest.mark.parametrize('mode',['normal','normalized_numeric'])
def test_real_http_png_wan_trim_and_zero_post_media_resume(production_config,runtime_run,monkeypatch,mode):
    from video_ai.runtime.production_visuals import produce_start_images,produce_source_clips
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True),mode=mode) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        images=produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        clips=produce_source_clips(f,b,t,images,state=s,manifest=m,paths=paths,logger=l)
        assert len(images['images'])==len(b['shots']) and len(posts)==2*len(b['shots'])
        assert s.snapshot()['active_stage']=='upscale'
        assert sum(c['source_frames'] for c in clips['clips'])==t.total_frames
        assert all((c['parameters']['width'],c['parameters']['height'])==(768,432) for c in clips['clips'])
        assert all(c['generated_frames']>=c['source_frames'] for c in clips['clips'])
        assert all('sha256' not in c['source'] for c in clips['clips'])
        media_count=len(list(l.path('process').glob('*'))) # also count immutable media evidence below
        all_paths={p for p in run.rglob('*') if p.is_file()};post_count=len(posts);get_count=len(gets)
        assert produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)==images
        assert produce_source_clips(f,b,t,images,state=s,manifest=m,paths=paths,logger=l)==clips
        assert len(posts)==post_count and len(gets)==get_count
        new={p for p in run.rglob('*') if p.is_file()}-all_paths
        assert not any(p.suffix in ('.png','.mp4') or 'processes' in p.parts for p in new)


@pytest.mark.parametrize('mode',['broken_png','wrong_size','short'])
def test_invalid_model_media_fails_and_never_second_post(production_config,runtime_run,monkeypatch,mode):
    from video_ai.runtime.production_visuals import produce_start_images,produce_source_clips
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True),mode=mode) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        if mode=='short':
            im=produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
            call=lambda:produce_source_clips(f,b,t,im,state=s,manifest=m,paths=paths,logger=l)
        else:call=lambda:produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        base=len(posts)
        for _ in range(2):
            with pytest.raises(RuntimeError):call()
        assert len(posts)==base+1


def test_external_comfy_is_rejected_without_post_or_stop(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_visuals as v
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        monkeypatch.setattr(v,'port_listening',lambda *a:True)
        with pytest.raises(ProductionRefused):v.produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        assert posts==[] and gets==[]


def test_cli_coordinator_reaches_upscale_and_resume_zero_requests(production_config,runtime_run,monkeypatch,capsys):
    import video_ai.runtime.production_upscale as upscale
    from video_ai.runtime.production_state import ProductionRefused
    def stop_at_upscale(*args,**kwargs):
        raise ProductionRefused('MAKE-03 source prefix fixture')
    monkeypatch.setattr(upscale,'produce_upscaled_clips',stop_at_upscale)
    from video_ai.cli import main
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        before=len(op)
        assert main(['make-video','--run-dir',str(run),'--json'])==2
        result=json.loads(capsys.readouterr().out)
        assert result['active_stage']=='upscale' and result['status']=='blocked'
        assert result['technical_checks']['frame_mapping']=='passed'
        assert result['human_review']=='unverified' and result['movie'] is None
        assert len(op)==before and len(posts)==2*len(b['shots'])
        count=len(posts);get_count=len(gets);files={p for p in run.rglob('*') if p.is_file()}
        assert main(['make-video','--run-dir',str(run),'--json'])==2
        again=json.loads(capsys.readouterr().out)
        assert again['active_stage']=='upscale'
        assert len(op)==before and len(posts)==count and len(gets)==get_count
        assert not any(p.suffix in ('.png','.mp4') for p in ({p for p in run.rglob('*') if p.is_file()}-files))


@pytest.mark.parametrize('point',['report','checkpoint','conversion'])
def test_technical_interrupt_preserves_model_output_and_recovers_without_repost(production_config,runtime_run,monkeypatch,point):
    import video_ai.runtime.production_visuals as v
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,op),comfy_server(production_config,run,paths,RunLogger(run,production=True)) as (cu,posts,gets,h):
        f,s,m,l,t,b=full_prefix(production_config,run,paths,url,cu,monkeypatch)
        im=v.produce_start_images(f,b,state=s,manifest=m,paths=paths,logger=l)
        baseline=len(posts)
        if point=='report':
            original=s.complete_stage
            def interrupt(stage):
                if stage=='source_clips':raise OSError('cursor interrupted after durable report')
                return original(stage)
            monkeypatch.setattr(s,'complete_stage',interrupt)
        elif point=='checkpoint':
            original=s.record_unit
            def interrupt(stage,uid,**kwargs):
                if stage=='source_clips' and kwargs['status']=='completed':raise OSError('cursor interrupted after checkpoint')
                return original(stage,uid,**kwargs)
            monkeypatch.setattr(s,'record_unit',interrupt)
        else:
            original=v.trim_production_video
            def interrupt(*args,**kwargs):
                original(*args,**kwargs)
                raise OSError('technical conversion completed but checkpoint not written')
            monkeypatch.setattr(v,'trim_production_video',interrupt)
        with pytest.raises(OSError):v.produce_source_clips(f,b,t,im,state=s,manifest=m,paths=paths,logger=l)
        before=len(posts)
        if point=='report':monkeypatch.setattr(s,'complete_stage',original)
        elif point=='checkpoint':monkeypatch.setattr(s,'record_unit',original)
        else:monkeypatch.setattr(v,'trim_production_video',original)
        result=v.produce_source_clips(f,b,t,im,state=s,manifest=m,paths=paths,logger=l)
        assert s.snapshot()['active_stage']=='upscale'
        assert len(posts)==baseline+len(b['shots'])
        assert sum(c['source_frames'] for c in result['clips'])==t.total_frames
        assert len(list((run/'production/visuals/shot_0001').glob('*/generated.mp4'))) == (2 if point=='conversion' else 1)
