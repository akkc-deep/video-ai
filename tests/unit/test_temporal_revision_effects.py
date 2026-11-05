"""Revision must account for native launches before a worker intent exists."""
from pathlib import Path
import pytest

from unit.test_temporal_native_process import job,FakeProcess,HEALTHY
from unit.test_temporal_scene_records import put


def effect_context(store,request):
    return dict(store=store,rows=[dict(budget=request['budget'])])


def interrupt_job(native,store,request,workflow,operation,monkeypatch):
    from video_ai.runtime import temporal_native_worker as worker
    calls=[]
    def missing(*a,**k):raise worker.MissingNativeTextCache('fixture_only new prompt')
    monkeypatch.setattr(worker,'existing_native_text_context',missing)
    def stopped(command,**kwargs):calls.append(command);raise KeyboardInterrupt('after durable launch')
    run_job=native.recover_or_start_native_window if operation=='one-window' else native.recover_or_prepare_native_cache
    with pytest.raises(KeyboardInterrupt):run_job(store,request,workflow,worker_factory=stopped,resource_sampler=lambda:dict(HEALTHY))
    assert len(calls)==1
    return calls


@pytest.mark.parametrize('operation',['one-window','prepare-cache'])
def test_native_revision_accounts_for_launch_before_worker_intent(job,monkeypatch,operation):
    native,store,request,workflow,folder=job
    calls=interrupt_job(native,store,request,workflow,operation,monkeypatch)
    assert not (folder/'intent.json').exists()
    effects=native.native_revision_effects(effect_context(store,request),{})
    assert len(effects)==1 and effects[0]['node']=='clips:'+request['clip_id']
    assert effects[0]['status']=='unknown'
    assert len(effects[0]['intent_sha256'])==64 and len(calls)==1


def test_matching_native_failure_terminal_is_known_but_mismatch_refuses(job):
    from video_ai.runtime.production_state import ProductionRefused
    native,store,request,workflow,folder=job
    failed=FakeProcess();failed.returncode=7
    result=native.recover_or_start_native_window(store,request,workflow,worker_factory=lambda *a,**k:failed,
        resource_sampler=lambda:dict(HEALTHY))
    assert result['status']=='failed'
    assert native.native_revision_effects(effect_context(store,request),{})==[]
    terminal=store.read(folder/'process-terminal.json');terminal['token']='f'*32
    put(folder/'process-terminal.json',terminal)
    with pytest.raises(ProductionRefused):native.native_revision_effects(effect_context(store,request),{})


def test_committed_sample_pending_decode_still_blocks_revision_and_only_decodes(job):
    from video_ai.planning.production_scenes import canonical_digest
    native,store,request,workflow,folder=job
    failed=FakeProcess();failed.returncode=7
    native.recover_or_start_native_window(store,request,workflow,worker_factory=lambda *a,**k:failed,
        resource_sampler=lambda:dict(HEALTHY))
    digest=canonical_digest(request)
    put(folder/'intent.json',dict(request_sha256=digest))
    put(folder/'sample-complete.json',dict(request_sha256=digest,native_diffusion_completed=True))
    assert native.native_revision_effects(effect_context(store,request),{})[0]['status']=='unknown'
    commands=[]
    def decode(command,**kwargs):
        commands.append(command)
        return FakeProcess(lambda:put(folder/'native-result.json',dict(request_sha256=digest)))
    result=native.recover_or_start_native_window(store,request,workflow,worker_factory=decode,
        resource_sampler=lambda:dict(HEALTHY),sleeper=lambda *a:None)
    assert result['status']=='completed' and len(commands)==1
    assert commands[0][commands[0].index('--operation')+1]=='decode-only'


def test_completed_cache_is_readonly_reusable_and_unknown_launch_never_reencodes(job,tmp_path,monkeypatch):
    from video_ai.runtime import temporal_native_worker as worker
    native,store,request,workflow,folder=job
    with monkeypatch.context() as interruption:
        interrupt_job(native,store,request,workflow,'prepare-cache',interruption)
    cache_root=tmp_path/'cache-identity';monkeypatch.setattr(worker,'TEXT_CACHE_ROOT',cache_root)
    cached=put(cache_root/request['text_cache_key']/'context.safetensors',b'fixture_only committed context')
    put(cache_root/request['text_cache_key']/'binding.json',dict(schema_version=1,identity=request['text_identity'],
        cache=cached,cache_sha256=cached['sha256'],new_text_encoding_calls=1))
    before={str(p):p.read_bytes() for p in cache_root.rglob('*') if p.is_file()}
    assert native.native_revision_effects(effect_context(store,request),{})==[]
    assert {str(p):p.read_bytes() for p in cache_root.rglob('*') if p.is_file()}==before
    resolver=worker.existing_native_text_context
    monkeypatch.setattr(worker,'existing_native_text_context',lambda value,**kw:resolver(value,cache_root=cache_root))
    def forbidden(*a,**k):raise AssertionError('completed cache cannot encode again')
    assert native.recover_or_prepare_native_cache(store,request,workflow,worker_factory=forbidden)['status']=='prepared'


def test_completed_video_has_no_unknown_revision_effect(job):
    from unit.test_temporal_native_process import completed_outputs
    native,store,request,workflow,folder=job
    process=FakeProcess(lambda:completed_outputs(folder,request))
    result=native.recover_or_start_native_window(store,request,workflow,
        worker_factory=lambda *a,**k:process,resource_sampler=lambda:dict(HEALTHY),sleeper=lambda *a:None)
    assert result['status']=='completed'
    assert native.native_revision_effects(effect_context(store,request),{})==[]


def test_shared_cache_launch_binds_its_actual_continuation_workflow(job,monkeypatch):
    from copy import deepcopy
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.planning.scene_temporal import derive_temporal_clips
    native,store,first,workflow,folder=job
    second=deepcopy(first)
    budget=derive_temporal_clips(dict(total_frames=173,scenes=[dict(scene_id='scene_0001',start_frame=0,end_frame=173)]),
        dict(total_frames=173))[1]
    # This case exercises the separate cache journal, without sampling either
    # video or fabricating any completed parent media.
    continuation=dict(workflow,history_pixels=13,history_latents=4)
    second.update(clip_id=budget['clip_id'],budget=budget,workflow_sha256=canonical_digest(continuation))
    second['parameters']['num_cond_frames']=13
    target=store.clip_dir(second['clip_id'])
    put(target/'request.json',second);put(target/'workflow.json',continuation)
    interrupt_job(native,store,second,continuation,'prepare-cache',monkeypatch)
    context=effect_context(store,first)
    context['rows'].append(dict(budget=budget))
    effects=native.native_revision_effects(context,{})
    assert {value['node'] for value in effects}=={'clips:'+first['clip_id'],'clips:'+second['clip_id']}
    assert all(value['status']=='unknown' for value in effects)
