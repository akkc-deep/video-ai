import json
from image_helpers import write_png
from storyboard_helpers import mock_generation, review_for, write_review


def make_images_run(storyboard_run,monkeypatch):
    from video_ai.runtime.storyboard_checks import plan_storyboard,finalize_storyboard,load_committed_storyboard
    from video_ai.runtime.manifest import hash_file,thaw
    run,config,store,_,timing=storyboard_run;mock_generation(monkeypatch)
    plan_storyboard(config,run_dir=run,timing_review_path=timing)
    assert finalize_storyboard(config,run_dir=run,review_path=write_review(run,review_for(run))).passed
    board=load_committed_storyboard(run)
    source=write_png(run/'user.png',1280,720)
    mapping=dict(schema_version=1,run_id=run.name,shots={s['shot_id']:str(source) for s in board['shots']},entities={})
    path=run/'user-inputs.json';path.write_text(json.dumps(mapping),encoding='utf-8')
    return run,config,store,path


def fake_media(monkeypatch):
    from video_ai.runtime import start_image_checks as sc
    from video_ai.runtime.manifest import hash_file,thaw,now
    from video_ai.planning.start_images import contain_filter
    from uuid import uuid4
    def command(args,stdout,kwargs,label):
        logger=kwargs['logger'];token=uuid4().hex;uid=kwargs['unit_id']
        out=logger.save_bytes(f'start-images/{label}-{uid}-{token}.stdout',stdout)
        err=logger.save_bytes(f'start-images/{label}-{uid}-{token}.stderr',b'')
        return dict(args=[str(a) for a in args],cwd=str(logger.run_dir),returncode=0,timed_out=False,
            stdout_path=str(out),stderr_path=str(err),started_at=now(),finished_at=now()),[out,err]
    def inspect(path,**kwargs):
        info=dict(identity=thaw(hash_file(path)),width=1280,height=720,format='png',pixel_format='rgb24')
        probe=dict(streams=[dict(codec_type='video',nb_read_frames='1',width=1280,height=720,codec_name='png',pix_fmt='rgb24')])
        config=kwargs['config']
        a,logs1=command((config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',path),json.dumps(probe).encode(),kwargs,'probe')
        b,logs2=command((config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',path,'-f','null','-'),b'',kwargs,'decode')
        note=kwargs['logger'].save_json(f'start-images/media-{kwargs["unit_id"]}-{uuid4().hex}.json',dict(info=info,probe=probe,commands=[a,b]))
        return info,[note]+logs1+logs2
    def adapt(source,target,**kwargs):
        source_info,logs=inspect(source,**kwargs)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        target_info,more=inspect(target,**kwargs)
        filter_value=contain_filter(kwargs['width'],kwargs['height'])
        c,command_logs=command((kwargs['config'].tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',source,'-vf',filter_value,
            '-frames:v','1','-pix_fmt','rgb24',target),b'',kwargs,'convert')
        record=kwargs['logger'].save_json(f'start-images/convert-{kwargs["unit_id"]}.json',dict(source=source_info,target=target_info,filter=filter_value,command=c))
        return target_info,logs+more+command_logs+[record]
    monkeypatch.setattr(sc,'inspect_image',inspect);monkeypatch.setattr(sc,'adapt_image',adapt);monkeypatch.setattr(sc,'validate_start_png',inspect)


def image_review(run):
    from video_ai.runtime.manifest import hash_file,thaw,now
    draft=json.loads((run/'images-draft.json').read_text(encoding='utf-8'))
    note=run/'logs/start-images/test-review-note.json'
    note.write_text(json.dumps(dict(schema_version=1,run_id=run.name,draft_identity=thaw(hash_file(run/'images-draft.json')),
        review_method='agent_visual',reviewer='test fixture',viewed_at=now(),references=draft['references'],
        entries=[dict(item,observation='TEST ONLY: static fixture') for item in draft['requirement_images']])),encoding='utf-8')
    data=dict(schema_version=1,run_id=run.name,draft_identity=thaw(hash_file(run/'images-draft.json')),
        storyboard_identity=draft['storyboard_identity'],review_method='agent_visual',reviewer='test fixture',reviewed_at=now(),
        global_verdict='passed',reason='TEST ONLY: not real visual review',entries=[dict(item,
            evidence_identity=thaw(hash_file(note)),verdict='passed',reason='TEST ONLY: static fixture') for item in draft['requirement_images']])
    path=run/'logs/start-images/semantic-review.json';path.write_text(json.dumps(data),encoding='utf-8')
    return path,data
