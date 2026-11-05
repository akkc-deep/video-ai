"""Explicit fixture_only numerical provider; actual native RGB and codec transactions."""
from pathlib import Path

from unit.test_temporal_scene_records import put
from unit.test_temporal_native_worker import FakeProvider


class OfflineNative:
    def __init__(self,setup,monkeypatch):
        self.setup=setup;self.calls=[]
        from video_ai.runtime import resources,gpu_desktop,temporal_native_process
        monkeypatch.setattr(resources,'gpu_guard',lambda *a,**k:dict(status='verified',external_pids=[]))
        monkeypatch.setattr(gpu_desktop,'desktop_policy',lambda run,sample:sample)
        monkeypatch.setattr(temporal_native_process,'recover_or_start_native_window',self.recover)
        monkeypatch.setattr(temporal_native_process,'recover_or_prepare_native_cache',lambda *a,**k:dict(status='prepared',fixture_only=True))
        from video_ai.runtime import temporal_scene_records as records
        real_consumed=records._verify_consumed_history
        def consumed(context,folder,request):
            if request['parent'] is None:return real_consumed(context,folder,request)
            # FakeProvider is the numerical seam; no 4 GiB KV allocation is
            # claimed. The actual copied raw13 pixels still reach the provider.
            value=context['store'].read(folder/'consumed-condition.json')
            assert value['input_snapshot']==request['input']['snapshot']
            assert value['condition_pixel_sha256']==request['input']['condition_pixel_sha256']
        monkeypatch.setattr(records,'_verify_consumed_history',consumed)

    def recover(self,store,request,workflow,**kwargs):
        from video_ai.runtime.temporal_native_worker import execute_native_operation
        from video_ai.runtime import production_temporal_scene_clips as production
        folder=store.clip_dir(request['clip_id'])
        cache=put(folder/'fixture-cache.safetensors',b'fixture_only cached text')
        binding=put(folder/'fixture-binding.json',dict(identity=request['text_identity'],cache_sha256=cache['sha256']))
        provider=FakeProvider(cache,binding)
        def media(output,frames,budget,condition):
            retained=frames[budget['retained_source_start']:budget['retained_source_end']]
            return dict(raw_movie=production._movie(store,output/'raw.mp4',frames,lossless=True),
                viewing_movie=production._movie(store,output/'viewing.mp4',frames,lossless=False),
                source_movie=production._movie(store,output/'source.mp4',retained,lossless=True),
                last_frame=production.commit_native_png(output/'last-frame.png',retained[-1]),
                contact_sheet=production.commit_native_png(output/'contact-sheet.png',frames[0]))
        provider.media=media
        execute_native_operation(request,operation='one-window',output=folder,provider=provider)
        self.calls.extend(provider.calls)
        return dict(status='completed',new_worker_started=True)

    def admit_all(self):
        from video_ai.runtime.production_scene_clips import produce_scene_clips,consume_scene_clip_observation
        from video_ai.runtime.manifest import now
        from unit.test_temporal_scene_observations import author
        import json
        s=self.setup;kwargs=dict(paths=s['paths'],logger=s['logger'])
        for stage in range(20):
            result=produce_scene_clips(s['frozen'],s['units'],s['timeline'],**kwargs)
            if result.status=='source_clips_ready':return result
            assert result.status in ('awaiting_continuity_review','blocked'),result.error
            assert result.error is None,result.error
            for path in result.observation_templates:
                value=author(json.loads(Path(path).read_bytes()));value['viewed_at']=now()
                authored=s['run']/f'fixture-native-observation-{stage}-{Path(path).parent.name}.json'
                put(authored,value)
                consumed=consume_scene_clip_observation(s['frozen'],s['units'],s['timeline'],authored,**kwargs)
                assert consumed.status in ('awaiting_continuity_review','blocked','source_clips_ready'),consumed.error
        raise AssertionError('fixture did not finish native windows/chains')
