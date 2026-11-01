"""Authentic source admission and synthetic local PNG service for scene media tests."""
from pathlib import Path
from scene_clip_helpers import prepared_wan,OfflineWan,admit_all


class OfflineUpscale(OfflineWan):
    def __init__(self,setup):
        from threading import get_ident
        from unit.test_workflows import remote_info
        from video_ai.runtime.workflows import WorkflowTemplate
        from video_ai.planning.scene_media import plan_scene_upscale
        from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
        from video_ai.runtime.processes import run_logged
        from video_ai.runtime.environment import build_child_env
        self.setup=setup; self.posts=[]; self.gets=[]; self.history_entries={}; self.ensures=0; self.closes=0; self.factories=0
        self.owner=get_ident(); self.mode='normal'; self.before_send=None
        self.template=WorkflowTemplate.load(Path(setup['frozen'].options['workflow_snapshots']['upscale']['path']),
            Path(setup['frozen'].options['workflow_snapshots']['upscale_mapping']['path']),setup['frozen'].config.models)
        self.remote_info=remote_info(self.template)
        sample=setup['run']/'synthetic-upscaled.png'
        result=run_logged(tuple(map(str,[setup['frozen'].config.tools['ffmpeg'],'-nostdin','-n','-v','error',
            '-f','lavfi','-i','color=c=blue:s=1920x1080','-frames:v','1','-pix_fmt','rgb24',sample])),
            cwd=setup['run'],env=build_child_env(setup['paths']),timeout=60,logger=setup['logger'],stage='test_fixture',unit_id='upscale')
        assert result.returncode==0
        self.outputs={}
        from video_ai.runtime.scene_revision_records import revision_scope
        # Match the coordinator's operation-scoped proof reuse. Every hit still
        # verifies the captured byte and inventory guards.
        with revision_scope():
            clips=require_scene_clip_acceptance(setup['frozen'],setup['units'],setup['timeline'])
        for row in plan_scene_upscale(clips):
            name=f'frame_{row["retained_frame_index"]+1:06d}'
            prefix=f'{setup["run"].name}/scene_upscale/{row["clip_id"]}/{name}/attempt_0001'
            target=setup['run']/'comfy/output'/(prefix+'_00001.png'); target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(sample.read_bytes()); self.outputs[row['frame_id']]=target

    def factory(self,base_url,*,request_timeout,ownership_check):
        from copy import deepcopy
        from uuid import uuid4
        backend=self; self.factories+=1
        class Client:
            def __init__(self): self.ownership_check=ownership_check
            def object_info(self,*,timeout): self.ownership_check(); return backend.response(backend.remote_info)
            def submit(self,graph,*,client_id,timeout):
                if backend.before_send: backend.before_send(graph)
                self.ownership_check()
                prefix=graph['5']['inputs']['filename_prefix']; parts=prefix.split('/'); fid=parts[-3]+':'+parts[-2]
                target=backend.outputs[fid]; pid=str(uuid4()); number=len(backend.posts)+1
                backend.posts.append(dict(prompt=deepcopy(graph),client_id=client_id))
                backend.history_entries[pid]=dict(prompt=[number,pid,deepcopy(graph),dict(client_id=client_id),['5']],
                    status=dict(status_str='success',completed=True,messages=[]),outputs={'5':{'images':[dict(filename=target.name,
                    subfolder=target.parent.relative_to(backend.setup['run']/'comfy/output').as_posix(),type='output')]}})
                if backend.mode=='lost_response': raise ConnectionError('synthetic acceptance response lost')
                if backend.mode=='rejected': return backend.response(dict(node_errors={'2':'synthetic rejection'}),400)
                return backend.response(dict(prompt_id=pid,number=number,node_errors={}))
            def queue(self,*,timeout): self.ownership_check(); return backend.response(dict(queue_running=[],queue_pending=[]))
            def history(self,prompt_id=None,*,timeout):
                self.ownership_check(); return backend.response({k:v for k,v in backend.history_entries.items() if prompt_id is None or k==prompt_id})
        return Client()


def prepared_scene_sources(runtime_run,tmp_path,monkeypatch,*,long_scene=False):
    from dataclasses import replace
    import video_ai.planning.production_timeline as timeline_module
    original=timeline_module.build_production_timeline
    def short_authentic_pcm(script,audio,**kwargs):
        # Change fixture PCM duration before the first scene budget is committed.
        # prepared_wan then writes these real samples and derives the real timeline.
        if all(info.stamp.path=='D:/pcm.wav' for info in audio.values()):
            audio={uid:replace(info,samples=3001) for uid,info in audio.items()}
        return original(script,audio,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(timeline_module,'build_production_timeline',short_authentic_pcm)
        setup=prepared_wan(runtime_run,tmp_path,patch,long_scene=long_scene,model_patch=monkeypatch)
    wan=OfflineWan(setup); admitted=admit_all(setup,wan)
    assert admitted.status=='source_clips_ready',admitted.error
    setup['wan_backend']=wan
    return setup


def prepared_upscaled(runtime_run,tmp_path,monkeypatch,*,long_scene=False):
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    setup=prepared_scene_sources(runtime_run,tmp_path,monkeypatch,long_scene=long_scene)
    backend=OfflineUpscale(setup); setup['upscale_backend']=backend
    result=produce_scene_upscaled_clips(setup['frozen'],setup['units'],setup['timeline'],
        paths=setup['paths'],logger=setup['logger'],**backend.kwargs)
    assert result.status=='upscale_ready',result.error
    setup['upscaled_result']=result
    return setup
