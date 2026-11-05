"""CPU fixture_only temporal chains: real media, no downloaded model or invented review."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from unit.test_temporal_scene_records import request_fixture, put


@pytest.fixture
def native_context(runtime_run):
    from video_ai.runtime.production_state import RunLock
    context, row, input_record, _ = request_fixture(runtime_run)
    store = context['store']; store.paths = runtime_run[2]; store.frozen.config = runtime_run[1]
    context['rows'] = [row]
    context['plan'] = dict(scenes=[dict(scene_id='scene_0001', unit_ids=['fixture_unit'], start_frame=0, end_frame=93, bindings=[])])
    context['timeline'] = SimpleNamespace(total_frames=93)
    context['inputs'].update(scene_plan_sha256='a'*64, visual_bible_sha256='b'*64, wan_inputs_sha256='c'*64, timeline_sha256='d'*64)
    # The generic request fixture leaves a prepared byte-only input; this flow starts fresh.
    Path(input_record['snapshot']['path']).unlink()
    row['narration_bindings'] = []
    with RunLock(store.run_dir) as lock:
        store.lock = lock
        yield context


@pytest.mark.parametrize('count,parts', [(320, [93,80,80,67]), (334, [93,80,80,80,1])])
def test_streamed_chain_preserves_every_raw_retained_frame(native_context, count, parts):
    from video_ai.runtime import production_temporal_scene_clips as production
    from video_ai.planning.scene_temporal import derive_temporal_clips
    from video_ai.runtime.temporal_scene_records import validate_temporal_chain
    from video_ai.runtime.temporal_native_worker import artifact
    context = native_context; store = context['store']
    budgets = derive_temporal_clips(dict(total_frames=count, scenes=[dict(scene_id='scene_0001',start_frame=0,end_frame=count)]),dict(total_frames=count))
    windows = []; expected = []
    for index, (budget, retained) in enumerate(zip(budgets, parts)):
        folder = store.root/budget['clip_id']; folder.mkdir(parents=True, exist_ok=True)
        frames = np.lib.format.open_memmap(folder/'frames.npy', mode='w+', dtype=np.uint8, shape=(93,432,768,3))
        for frame in range(93): frames[frame] = (index*97+frame)%256
        expected += [int(frame[0,0,0]) for frame in frames[budget['retained_source_start']:budget['retained_source_end']]]
        frames.flush()
        last = production.commit_native_png(folder/'last-frame.png', frames[budget['retained_source_end']-1])
        del frames
        windows.append(dict(budget=budget, status='static_ready', result=put(folder/'native-result.json',dict(fixture_only=True)),
            raw_frames=artifact(folder/'frames.npy'), last_frame=last, selected_image=context['wan']['scenes'][0]))
    chain = production.assemble_temporal_chain(context, 'scene_0001', windows)
    assert chain['frames'] == count and chain['boundary_frames'] == ([93,173,253] if count==320 else [93,173,253,333])
    actual = np.load(chain['artifacts']['frames']['path'], mmap_mode='r', allow_pickle=False)
    assert actual[:,0,0,0].tolist() == expected and len(actual) == count
    # Both actual ffprobe/decode and last retained pixels are checked by the public validator.
    for window in windows: window['selected_image'] = {k:window['selected_image'][k] for k in ('path','bytes','sha256')}
    verified = validate_temporal_chain(context, 'scene_0001', windows)
    assert verified['status'] == 'awaiting_chain_review'
    assert production.assemble_temporal_chain(context,'scene_0001',windows) == chain


def test_full_chain_review_is_consumed_once_and_static_cannot_mark_ready(runtime_run, monkeypatch):
    from video_ai.runtime import production_temporal_scene_clips as production
    from unit.test_temporal_chain_records import chain_fixture, write_chain
    from unit.test_temporal_scene_observations import author, NOW
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    records, context, row, window = chain_fixture(runtime_run, monkeypatch)
    folder, raw, result_id = write_chain(context, window)
    context['units'] = []
    chain = records.validate_temporal_chain(context,'scene_0001',[window])
    template = build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')
    observation = put(folder/'authored-full.json',author(template))
    with RunLock(context['store'].run_dir) as lock:
        context['store'].lock=lock
        before = production.finish_temporal_clips(context)
        assert before.status == 'awaiting_continuity_review' and before.source_clips is None
        accepted = production.consume_temporal_observation(context, observation['path'])
        assert accepted.status == 'source_clips_ready'
        complete = context['store'].read('complete.json')
        assert complete['schema_version'] == 4 and len(complete['temporal_chains']) == 1
        assert production.consume_temporal_observation(context, observation['path']).status == 'source_clips_ready'
        assert context['store'].read('complete.json') == complete


def test_existing_entry_dispatches_native_before_comfy(native_context, monkeypatch):
    from video_ai.runtime import production_scene_clips as outer
    from video_ai.runtime import production_temporal_scene_clips as native
    calls = []
    native_context['execution'] = dict(mode='temporal_extension_v1')
    sentinel = object()
    def produce(context, **kwargs): calls.append(context); return sentinel
    monkeypatch.setattr(native,'produce_temporal_clips',produce)
    result = outer._produce(native_context,paths=native_context['store'].paths,logger=None,client_factory=None,service_factory=None)
    assert result is sentinel and calls == [native_context]


def test_existing_observation_entry_consumes_native_scope(runtime_run, monkeypatch):
    from video_ai.runtime import production_scene_clips as outer
    from unit.test_temporal_chain_records import chain_fixture,write_chain
    from unit.test_temporal_scene_observations import author
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    from video_ai.runtime.production_state import RunLock
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    context['execution']=dict(mode='temporal_extension_v1');context['units']=[]
    folder,_,_=write_chain(context,window)
    chain=records.validate_temporal_chain(context,'scene_0001',[window])
    observed=put(folder/'authored.json',author(build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')))
    with RunLock(context['store'].run_dir) as lock:
        context['store'].lock=lock
        assert outer._consume(context,observed['path']).status=='source_clips_ready'
        assert outer._finish(context).status=='source_clips_ready'


def test_retained_raw_rejection_cannot_be_replaced_after_receipt_interruption(runtime_run,monkeypatch):
    from video_ai.runtime import production_temporal_scene_clips as production
    from unit.test_temporal_chain_records import chain_fixture,write_chain
    from unit.test_temporal_scene_observations import author
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    context['units']=[]
    folder,_,_=write_chain(context,window)
    chain=records.validate_temporal_chain(context,'scene_0001',[window])
    template=build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')
    failed=author(template);failed['verdict']='failed';failed['checks']['motion']='failed'
    import json,hashlib
    raw=json.dumps(failed).encode()
    put(folder/'observations'/(hashlib.sha256(raw).hexdigest()+'.json'),raw)
    observed=put(folder/'authored-passed.json',author(template))
    with RunLock(context['store'].run_dir) as lock:
        context['store'].lock=lock
        with pytest.raises(ProductionRefused):production.consume_temporal_observation(context,observed['path'])


@pytest.mark.parametrize('count,windows',[(320,4),(334,5)])
def test_fixture_only_production_transaction_and_replay_have_one_sample_per_window(native_context,count,windows,monkeypatch):
    from video_ai.runtime import production_temporal_scene_clips as production,temporal_native_process as process,temporal_scene_records as records
    from video_ai.runtime import resources
    from video_ai.runtime.temporal_native_worker import execute_native_operation
    from video_ai.planning.scene_temporal import derive_temporal_clips
    from unit.test_temporal_native_worker import FakeProvider
    from unit.test_temporal_native_process import FakeProcess,HEALTHY
    from unit.test_temporal_scene_observations import author
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import now
    context=native_context;store=context['store']
    budgets=derive_temporal_clips(dict(total_frames=count,scenes=[dict(scene_id='scene_0001',start_frame=0,end_frame=count)]),dict(total_frames=count))
    store.clip_ids=frozenset(b['clip_id'] for b in budgets)
    first=context['rows'][0]
    context['rows']=[dict(deepcopy(first),budget=b,parameters=dict(first['parameters'],num_cond_frames=1 if i==0 else 13)) for i,b in enumerate(budgets)]
    context['plan']['scenes'][0]['end_frame']=count;context['timeline'].total_frames=count
    context['execution']=dict(mode='temporal_extension_v1');context['units']=[]
    put(Path(context['frozen'].options['script_path']),b'fixture_only script')
    monkeypatch.setattr(resources,'gpu_guard',lambda *a,**k:dict(status='verified',external_pids=[]))
    monkeypatch.setattr(production,'desktop_policy',lambda run,sample:sample,raising=False)
    from video_ai.runtime import gpu_desktop
    monkeypatch.setattr(gpu_desktop,'desktop_policy',lambda run,sample:sample)
    monkeypatch.setattr(process,'resource_snapshot',lambda root:dict(HEALTHY))
    monkeypatch.setattr(process,'process_started_at',lambda pid:'fixture_start')
    monkeypatch.setattr(process,'recover_or_prepare_native_cache',lambda *a,**k:dict(status='prepared',fixture_only=True))
    real_consumed=records._verify_consumed_history
    def consumed(context,folder,request):
        if request['parent'] is None:return real_consumed(context,folder,request)
        # Numeric KV storage is the explicit external model seam here. Real
        # 48-layer banks remain mandatory in the unpatched production validator.
        value=store.read(folder/'consumed-condition.json')
        assert value['input_snapshot']==request['input']['snapshot']
        assert value['condition_pixel_sha256']==request['input']['condition_pixel_sha256']
    monkeypatch.setattr(records,'_verify_consumed_history',consumed)
    providers=[]
    def factory(command,**kwargs):
        import json
        folder=Path(command[command.index('--output')+1]);request=json.loads((folder/'request.json').read_bytes())
        cache=put(folder/'fixture-cache.safetensors',b'fixture_only text')
        binding=put(folder/'fixture-cache.json',dict(identity=request['text_identity'],cache_sha256=cache['sha256']))
        provider=FakeProvider(cache,binding);providers.append(provider)
        def media(output,frames,budget,condition):
            retained=frames[budget['retained_source_start']:budget['retained_source_end']]
            last=production.commit_native_png(output/'last-frame.png',retained[-1])
            return dict(raw_movie=production._movie(store,output/'raw.mp4',frames,lossless=True),
                viewing_movie=production._movie(store,output/'viewing.mp4',frames,lossless=False),
                source_movie=production._movie(store,output/'source.mp4',retained,lossless=True),last_frame=last,
                contact_sheet=production.commit_native_png(output/'contact-sheet.png',frames[0]))
        provider.media=media
        return FakeProcess(lambda:execute_native_operation(request,operation='one-window',output=folder,provider=provider))
    logger=RunLogger(store.run_dir,production=True)
    for i in range(windows):
        result=production.produce_temporal_clips(context,paths=store.paths,logger=logger,worker_factory=factory)
        assert result.status=='awaiting_continuity_review' and len(providers)==i+1
        template=store.read(result.observation_templates[0]);observed=author(template)
        observed['viewed_at']=now()
        ref=put(store.root/f'fixture-observed-{i}.json',observed)
        production.consume_temporal_observation(context,ref['path'])
    assembled=production.produce_temporal_clips(context,paths=store.paths,logger=logger,worker_factory=factory)
    assert assembled.status=='awaiting_continuity_review' and len(providers)==windows
    template=store.read(assembled.observation_templates[0]);assert template['scope']=='scene_temporal_chain_process'
    observed=author(template);observed['viewed_at']=now()
    ref=put(store.root/'fixture-observed-chain.json',observed)
    assert production.consume_temporal_observation(context,ref['path']).status=='source_clips_ready'
    assert production.produce_temporal_clips(context,paths=store.paths,logger=logger,worker_factory=factory).status=='source_clips_ready'
    assert len(providers)==windows and all(len(p.calls)==1 for p in providers)
    for p in providers[1:]:assert p.calls[0]['condition'][:,0,0,0].tolist()==list(range(80,93))
    assert store.read('complete.json')['total_frames']==count
