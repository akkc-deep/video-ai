"""Actual RGB history reaches the provider; durable sampling survives decode failure."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from unit.test_temporal_scene_records import request_fixture, put


@pytest.fixture
def native_job(runtime_run, request):
    from video_ai.runtime import temporal_native_worker as worker
    from video_ai.runtime.temporal_scene_records import expected_temporal_request, temporal_workflow
    context, row, old_input, parent = request_fixture(runtime_run, continuation=True)
    Path(old_input['snapshot']['path']).unlink()  # replace the old byte-only test fixture
    from video_ai.runtime.production_state import RunLock
    lock = RunLock(context['store'].run_dir)
    lock.__enter__()
    request.addfinalizer(lambda: lock.__exit__(None, None, None))
    context['store'].lock = lock
    source = Path(parent['raw_frames']['path'])
    frames = np.lib.format.open_memmap(source, mode='w+', dtype=np.uint8, shape=(93, 432, 768, 3))
    for i in range(93): frames[i] = i
    frames.flush(); del frames
    parent['raw_frames'] = put(source, source.read_bytes())
    source_image = context['wan']['scenes'][0]
    input_record = worker.prepare_native_input(context['store'], row, source_image, parent)
    request = expected_temporal_request(context, row, input_record, parent)
    folder = context['store'].clip_dir(row['budget']['clip_id'])
    put(folder/'request.json', request)
    put(folder/'workflow.json', temporal_workflow(context, row))
    cache = put(folder/'cache.safetensors', b'fixture_only text context')
    binding = put(folder/'cache-binding.json', dict(identity=request['text_identity'], cache_sha256=cache['sha256']))
    provider = FakeProvider(cache, binding)
    return worker, context, row, request, folder, provider


class FakeProvider:
    def __init__(self, cache, binding):
        self.cache, self.binding = cache, binding
        self.calls = []; self.decodes = 0; self.fail_decode = False
    def text_context(self, request): return dict(cache=self.cache, binding=self.binding)
    def sample(self, request, *, condition, generator, output, **kwargs):
        self.calls.append(dict(condition=np.asarray(condition).copy(), generator=generator, **kwargs))
        return dict(sample=put(output/'sample.safetensors', b'fixture_only committed latent'),
            generator=put(output/'generator.safetensors', b'fixture_only advanced RNG'),
            latent_shape=[1, 16, 24, 54, 96],
            kv=dict(layers=48, bytes=4076863488, manifest=put(output/'kv.json', {'fixture_only': 'KV'})))
    def decode(self, sample):
        self.decodes += 1
        if self.fail_decode: raise RuntimeError('fixture_only decoder interruption')
        frames = np.zeros((93, 432, 768, 3), dtype=np.uint8)
        for i in range(93): frames[i] = i
        return frames
    def media(self, output, frames, budget, condition):
        # Codec integration is tested separately with actual media, not these files.
        return {role: put(output/name, b'fixture_only codec '+role.encode()) for role, name in
            [('raw_movie', 'raw.mp4'), ('viewing_movie', 'viewing.mp4'), ('source_movie', 'source.mp4'),
             ('last_frame', 'last-frame.png'), ('contact_sheet', 'contact-sheet.png')]}


def test_thirteen_distinct_raw_frames_reach_provider(native_job):
    worker, context, row, request, folder, provider = native_job
    result = worker.execute_native_operation(request, operation='one-window', output=folder, provider=provider)
    assert result['status'] == 'complete' and len(provider.calls) == 1
    call = provider.calls[0]
    assert call['condition'].shape == (13, 432, 768, 3)
    assert call['condition'][:, 0, 0, 0].tolist() == list(range(80, 93))
    assert call['num_cond_frames'] == 13 and call['use_kv_cache'] is True
    assert call['offload_kv_cache'] is True and call['enhance_hf'] is False
    assert call['generator'] == request['parent']['generator']
    assert result['technical']['history']['kv_bytes'] == 4076863488
    assert json.loads((folder/'consumed-condition.json').read_bytes())['condition_pixel_sha256'] == hashlib.sha256(call['condition'].tobytes()).hexdigest()


def test_successful_latent_only_decodes_after_interruption(native_job):
    worker, context, row, request, folder, provider = native_job
    provider.fail_decode = True
    with pytest.raises(RuntimeError, match='decoder interruption'):
        worker.execute_native_operation(request, operation='one-window', output=folder, provider=provider)
    before = {name: (folder/name).read_bytes() for name in ('intent.json', 'sample-complete.json', 'sample.safetensors', 'generator.safetensors')}
    provider.fail_decode = False
    result = worker.execute_native_operation(request, operation='decode-only', output=folder, provider=provider)
    assert result['status'] == 'complete' and len(provider.calls) == 1 and provider.decodes == 2
    assert all((folder/name).read_bytes() == raw for name, raw in before.items())
    assert worker.execute_native_operation(request, operation='one-window', output=folder, provider=provider) == result
    assert len(provider.calls) == 1 and provider.decodes == 2


def test_partial_media_resume_preserves_sample(native_job):
    worker, context, row, request, folder, provider = native_job
    original_media = provider.media
    def interrupted_media(output, frames, budget, condition):
        put(output/'raw.mp4.pending', b'fixture_only interrupted codec')
        raise RuntimeError('fixture_only partial media')
    provider.media = interrupted_media
    with pytest.raises(RuntimeError, match='partial media'):
        worker.execute_native_operation(request, operation='one-window', output=folder, provider=provider)
    sample_bytes = (folder/'sample-complete.json').read_bytes()
    frames_sha = hashlib.sha256((folder/'frames.npy').read_bytes()).hexdigest()
    provider.media = original_media
    result = worker.execute_native_operation(request, operation='decode-only', output=folder, provider=provider)
    assert result['status'] == 'complete' and len(provider.calls) == 1
    assert (folder/'sample-complete.json').read_bytes() == sample_bytes
    assert hashlib.sha256((folder/'frames.npy').read_bytes()).hexdigest() == frames_sha


@pytest.mark.parametrize('fault', ['unknown', 'snapshot', 'parent', 'rng', 'cache', 'latent'])
def test_drift_or_unknown_never_calls_provider(native_job, fault):
    worker, context, row, request, folder, provider = native_job
    from video_ai.runtime.production_state import ProductionRefused
    if fault == 'unknown': put(folder/'intent.json', {'fixture_only': 'unknown call'})
    elif fault == 'snapshot': Path(request['input']['snapshot']['path']).write_bytes(b'changed')
    elif fault == 'parent': Path(request['parent']['raw_frames']['path']).write_bytes(b'changed')
    elif fault == 'rng': Path(request['parent']['generator']['path']).write_bytes(b'changed')
    elif fault == 'cache': Path(provider.cache['path']).write_bytes(b'changed')
    else: put(folder/'sample-complete.json', {'fixture_only': 'orphan sample'})
    with pytest.raises(ProductionRefused):
        worker.execute_native_operation(request, operation='one-window', output=folder, provider=provider)
    assert provider.calls == []


def test_import_does_not_load_torch_and_allocator_precedes_dynamic_import(runtime_run):
    # A fresh interpreter detects imports already cached by another test.
    code = """import sys,os
import video_ai.runtime.temporal_native_worker as worker
assert 'torch' not in sys.modules
os.environ['PYTORCH_ALLOC_CONF']='backend:native'
seen=[]
def importer(name):
    seen.append(os.environ['PYTORCH_ALLOC_CONF'])
    return object()
worker.import_native_torch(importer=importer)
assert seen==['backend:cudaMallocAsync']
"""
    result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_new_prompt_must_pass_untruncated_local_tokenization_before_encoding():
    from video_ai.runtime import temporal_native_worker as worker
    from video_ai.runtime.production_state import ProductionRefused
    calls = []
    def tokenizer(text, **kwargs):
        calls.append(kwargs)
        return {'input_ids': list(range(513 if text == 'too long' else 17))}
    assert worker.validate_native_tokens(tokenizer, ['short', 'short']) == [17, 17]
    with pytest.raises(ProductionRefused): worker.validate_native_tokens(tokenizer, ['short', 'too long'])
    assert all(call.get('truncation') is False for call in calls)


def test_exact_qualified_prompt_reuses_original_cache_without_encoding(tmp_path, monkeypatch):
    from video_ai.runtime import temporal_native_worker as worker
    root = tmp_path/'qualification'; root.mkdir()
    case = put(root/'case.json', dict(positive='same positive', negative='same negative', model_manifest_sha256='a'*64))
    cache = put(root/'text-context.safetensors', b'fixture_only original context')
    put(root/'text-context.json', dict(identity=dict(case_sha256=case['sha256'], model_manifest_sha256='a'*64,
        algorithm='official-umt5-eager-bfloat16-layer-staging-v1'), sha256=cache['sha256']))
    monkeypatch.setattr(worker, 'QUALIFIED_TEXT_ROOT', root)
    identity = dict(algorithm='official-umt5-eager-bfloat16-layer-staging-v1', model_manifest_sha256='a'*64,
        positive_sha256=hashlib.sha256(b'same positive').hexdigest(), negative_sha256=hashlib.sha256(b'same negative').hexdigest())
    from video_ai.planning.production_scenes import canonical_digest
    request = dict(parameters=dict(positive='same positive', negative='same negative'), text_identity=identity,
        text_cache_key=canonical_digest(identity))
    result = worker.existing_native_text_context(request, cache_root=tmp_path/'cache')
    assert result['cache'] == cache
    assert json.loads(Path(result['binding']['path']).read_bytes())['new_text_encoding_calls'] == 0
    assert worker.existing_native_text_context(request, cache_root=tmp_path/'cache') == result
    Path(cache['path']).write_bytes(b'changed')
    from video_ai.runtime.production_state import ProductionRefused
    with pytest.raises(ProductionRefused): worker.existing_native_text_context(request, cache_root=tmp_path/'cache')


@pytest.mark.parametrize('operation',['resource-preflight','prepare-cache'])
def test_real_cli_dispatches_resource_operation_before_exit(runtime_run,operation):
    from uuid import uuid4
    from video_ai.runtime import temporal_native_worker as worker
    root=runtime_run[2].input_root if operation=='resource-preflight' else runtime_run[0]/'production'
    output=root/'native-cli-test'/uuid4().hex/'result'
    request=put(output.parent/'request.json',dict(fixture_only=True))
    marker=output/'called.json'
    # Inject the numeric provider at the actual script's main frame. The CLI,
    # parser, dispatcher and cleanup run normally in a fresh interpreter.
    code="""import sys,runpy,json
from pathlib import Path
from types import SimpleNamespace
target,request,output,marker,operation=sys.argv[1:]
class Provider:
    def __init__(self,*a,**k):self.guard=SimpleNamespace(close=lambda:None)
    def resource_preflight(self,value):
        Path(marker).write_text(json.dumps(value))
        return {'status':'complete','fixture_only':True}
    def prepare_cache(self,value):return self.resource_preflight(value)
def trace(frame,event,arg):
    if event=='call' and frame.f_code.co_name=='main' and frame.f_code.co_filename==target:
        frame.f_globals['NativeProvider']=Provider
        sys.settrace(None)
    return trace
sys.argv=[target,'--operation',operation,'--request',request,'--output',output]
sys.settrace(trace)
runpy.run_path(target,run_name='__main__')
"""
    result=subprocess.run([sys.executable,'-B','-c',code,str(Path(worker.__file__)),request['path'],str(output),str(marker),operation],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(marker.read_bytes())==dict(fixture_only=True)


def test_new_prompt_cache_validation_errors_cannot_fall_through_to_encoding():
    from video_ai.runtime import temporal_native_worker as worker
    from video_ai.runtime.production_state import ProductionRefused
    provider=worker.NativeProvider.__new__(worker.NativeProvider)
    invalid=dict(parameters=dict(positive='new positive',negative='new negative'),text_identity={},text_cache_key='f'*64)
    with pytest.raises(ProductionRefused):provider.prepare_cache(invalid)


@pytest.mark.parametrize('fault',['protocol','run','clip','input-clip'])
def test_worker_rejects_foreign_request_header_before_sampling(native_job,fault):
    worker,context,row,request,folder,provider=native_job
    from video_ai.runtime.production_state import ProductionRefused
    if fault=='protocol':request['protocol']='foreign'
    elif fault=='run':request['run_id']='20261103-000000-abcdef123456'
    elif fault=='clip':request['clip_id']='scene_9999_clip_0001'
    else:request['input']['clip_id']='scene_9999_clip_0001'
    put(folder/'request.json',request)
    with pytest.raises(ProductionRefused):worker.execute_native_operation(request,operation='one-window',output=folder,provider=provider)
    assert provider.calls==[]


def test_first_worker_condition_must_be_the_actual_selected_original(runtime_run):
    from video_ai.runtime import temporal_native_worker as worker
    from video_ai.runtime.temporal_scene_records import expected_temporal_request,temporal_workflow
    from video_ai.runtime.production_state import ProductionRefused
    context,row,input_record,parent=request_fixture(runtime_run)
    request=expected_temporal_request(context,row,input_record,parent);folder=context['store'].clip_dir(request['clip_id'])
    request['selected_image']=put(folder/'other-scene.png',b'fixture_only other selected original')
    put(folder/'request.json',request);put(folder/'workflow.json',temporal_workflow(context,row))
    cache=put(folder/'cache.safetensors',b'fixture_only cache')
    binding=put(folder/'binding.json',dict(identity=request['text_identity'],cache_sha256=cache['sha256']))
    provider=FakeProvider(cache,binding)
    with pytest.raises(ProductionRefused):worker.execute_native_operation(request,operation='one-window',output=folder,provider=provider)
    assert provider.calls==[]
