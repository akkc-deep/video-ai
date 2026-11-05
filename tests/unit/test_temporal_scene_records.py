"""Native generation binds real parent raw13, RNG and static screening only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def request_fixture(runtime_run, *, continuation=False):
    from video_ai.planning.scene_temporal import derive_temporal_clips, CLOCK_POLICY
    from video_ai.runtime.scene_clip_records import SceneClipStore
    run = runtime_run[0]
    frozen = SimpleNamespace(options={'run_id': run.name, 'script_path': str(run/'production/script.txt'), 'model_stamps': {}})
    clips = derive_temporal_clips(dict(total_frames=173, scenes=[dict(scene_id='scene_0001', start_frame=0, end_frame=173)]), dict(total_frames=173))
    store = SceneClipStore(frozen, run, clip_ids=[row['clip_id'] for row in clips])
    root = store.root
    selected = put(root/'selected.png', b'fixture_only selected PNG')
    parts = {name: put(root/(name+'.json'), {'fixture_only': name}) for name in ('evidence', 'bundle', 'model', 'python', 'worker', 'execution')}
    context = dict(frozen=frozen, store=store, inputs={'fixture_only': True,'visual_bible_sha256':'b'*64}, execution_budget=parts['execution'],
        evidence=dict(root=parts['evidence'], value=dict(runtime_bundle=parts['bundle'], model_manifest=parts['model'],
            native_python=parts['python'], production_worker=parts['worker'], package_versions={'torch': 'fixture_only'})),
        wan={'scenes': [dict(scene_id='scene_0001', **selected)]})
    index = int(continuation)
    budget = clips[index]
    row = dict(budget=budget, parameters=dict(positive='fixture_only positive', negative='fixture_only negative',
        seed=42, width=768, height=432, length=93, fps=16, output_clock_policy=CLOCK_POLICY, steps=50, cfg=4.0,
        resolution='432p-native16', num_cond_frames=13 if continuation else 1,
        use_kv_cache=True, offload_kv_cache=True, enhance_hf=False), comparison_images=[], narration_bindings=[])
    parent = None
    if continuation:
        result = put(root/clips[0]['clip_id']/'native-result.json', {'fixture_only': 'parent result'})
        frames = put(root/clips[0]['clip_id']/'frames.npy', b'fixture_only parent raw93')
        generator = put(root/clips[0]['clip_id']/'generator.safetensors', b'fixture_only generator')
        screening = put(root/clips[0]['clip_id']/'static-accepted.json', dict(verdict='acceptable', allow_next_window=True,
            result_sha256=result['sha256']))
        parent = dict(budget=clips[0], result=result, raw_frames=frames, generator=generator, static_acceptance=screening)
        source = frames
        snapshot = put(root/budget['clip_id']/'condition13.npy', b'fixture_only distinct13 snapshot')
    else:
        source = selected
        snapshot = put(root/budget['clip_id']/'input.png', Path(selected['path']).read_bytes())
    input_record = dict(schema_version=1, algorithm='temporal_native_input_v1', clip_id=budget['clip_id'],
        kind=budget['input_kind'], source=source, snapshot=snapshot,
        source_frame_range=[80, 93] if continuation else None,
        parent_result_sha256=parent['result']['sha256'] if continuation else None,
        condition_pixel_sha256='c'*64 if continuation else None)
    return context, row, input_record, parent


def test_first_request_never_depends_on_a_future_chain_review(runtime_run):
    from video_ai.runtime.temporal_scene_records import expected_temporal_request
    context, row, input_record, parent = request_fixture(runtime_run)
    request = expected_temporal_request(context, row, input_record, parent)
    assert request['parent'] is None and request['protocol'] == 'longcat_native16_v1'
    assert request['input']['snapshot']['sha256'] == input_record['source']['sha256']
    context['chain_review'] = {'future_human_acceptance': 'must not enter generation'}
    assert expected_temporal_request(context, row, input_record, parent) == request


def test_native_request_preserves_shared_visual_and_narration_context(runtime_run):
    from video_ai.runtime.temporal_scene_records import expected_temporal_request
    context,row,input_record,parent=request_fixture(runtime_run)
    context['inputs']['visual_bible_sha256']='b'*64
    row['narration_bindings']=[dict(fixture_only='original narration range')]
    request=expected_temporal_request(context,row,input_record,parent)
    assert request['selected_image']=={k:context['wan']['scenes'][0][k] for k in ('path','bytes','sha256')}
    assert request['comparison_images']==row['comparison_images']
    assert request['narration_bindings']==row['narration_bindings']
    assert request['visual_bible_sha256']=='b'*64


def test_continuation_request_binds_parent_raw13_generator_and_static(runtime_run):
    from video_ai.runtime.temporal_scene_records import expected_temporal_request
    context, row, input_record, parent = request_fixture(runtime_run, continuation=True)
    request = expected_temporal_request(context, row, input_record, parent)
    assert request['input']['source_frame_range'] == [80, 93]
    assert request['input']['condition_pixel_sha256'] == 'c'*64
    assert request['parent']['generator'] == parent['generator']
    assert request['parent']['result'] == parent['result']
    assert request['parent']['static_acceptance'] == parent['static_acceptance']
    assert request['parameters']['num_cond_frames'] == 13


@pytest.mark.parametrize('fault', ['parent_result', 'parent_frames', 'history_range', 'pixel_sha',
    'generator_bytes', 'static_rejected', 'static_unverified', 'trimmed_parent', 'single_tail', 'shape', 'clock'])
def test_parent_or_input_drift_refuses_request_before_any_provider(fault, runtime_run):
    from video_ai.runtime.temporal_scene_records import expected_temporal_request
    from video_ai.runtime.production_state import ProductionRefused
    context, row, input_record, parent = request_fixture(runtime_run, continuation=True)
    if fault == 'parent_result': input_record['parent_result_sha256'] = 'f'*64
    elif fault == 'parent_frames': input_record['source'] = input_record['snapshot']
    elif fault == 'history_range': input_record['source_frame_range'] = [92, 93]
    elif fault == 'pixel_sha': input_record['condition_pixel_sha256'] = None
    elif fault == 'generator_bytes': Path(parent['generator']['path']).write_bytes(b'changed')
    elif fault.startswith('static_'):
        value = dict(verdict='rejected' if fault == 'static_rejected' else 'unverified', allow_next_window=False,
                     result_sha256=parent['result']['sha256'])
        parent['static_acceptance'] = put(Path(parent['static_acceptance']['path']), value)
    elif fault == 'trimmed_parent': parent['budget']['retained_source_end'] = 92
    elif fault == 'single_tail': input_record['kind'] = 'parent_retained_last_frame'
    elif fault == 'shape': row['parameters']['width'] = 832
    else: row['parameters']['fps'] = 15
    with pytest.raises(ProductionRefused): expected_temporal_request(context, row, input_record, parent)


@pytest.mark.parametrize('mode,schema,allowed', [
    ('segmented_v1', 1, True), ('segmented_v1', 2, False), ('segmented_v1', 3, False),
    ('whole_scene_v1', 1, False), ('whole_scene_v1', 2, True), ('whole_scene_v1', 3, False),
    ('temporal_extension_v1', 1, False), ('temporal_extension_v1', 2, False), ('temporal_extension_v1', 3, True)])
def test_runtime_prompt_schema_is_exact_for_each_frozen_mode(mode, schema, allowed):
    from video_ai.runtime.scene_video_prompt_records import validate_contract_mode
    from video_ai.runtime.production_state import ProductionRefused
    settings = dict(mode=mode, prompt_policy='visual_v2', prompt_contract='prompt.json')
    if mode == 'whole_scene_v1': settings['whole_scene_evidence'] = 'D:/VideoSi/whole.json'
    if mode == 'temporal_extension_v1': settings['temporal_evidence'] = 'D:/VideoSi/native.json'
    if allowed: assert validate_contract_mode({'schema_version': schema}, settings) == {'schema_version': schema}
    else:
        with pytest.raises(ProductionRefused): validate_contract_mode({'schema_version': schema}, settings)


def test_native_context_branches_before_wan_model_or_workflow_validation(runtime_run, monkeypatch):
    from unit.test_scene_video_prompts import fixture as prompt_fixture, reviewed
    from video_ai.planning.scene_temporal import derive_temporal_clips
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.planning.scene_execution import build_scene_execution_budget
    from video_ai.runtime import scene_clip_records, scene_execution_records, scene_video_prompt_records, temporal_scene_admission
    from video_ai.runtime import reference_image_records, production_visual_templates
    from video_ai.runtime.workflows import WorkflowTemplate
    run = runtime_run[0]
    frozen, bible, plan, timeline, images, contract = prompt_fixture()
    frozen.config.production_strategy = 'paragraph_jimeng_v1'
    timeline.as_dict = lambda: dict(total_frames=205, total_samples=613001)
    frozen.options = dict(run_id=run.name, script_path=str(run/'production/script.txt'), model_stamps={})
    for index, image in enumerate(images['scenes']):
        image.update(put(run/'production/reference-images'/f'selected-{index}.png', b'fixture_only original'))
    clips = derive_temporal_clips(plan, timeline)
    contract['schema_version'] = 3
    contract['binding'].update(wan_inputs_sha256=canonical_digest(images), rendering_mode='temporal_extension_v1',
                                execution_clips_sha256=canonical_digest(clips))
    contract['clips'] = [dict(clip_id=row['clip_id'], motion='Continue motion', camera='Steady tracking',
                              lighting='Maintain current lighting', changes=[]) for row in clips]
    reviewed(contract)
    frozen.config.raw['scene_rendering'].update(mode='temporal_extension_v1', temporal_evidence='D:/VideoSi/native.json')
    prompt = put(run/'production/scene-video-prompts.json', contract)
    parts = {key: put(run/'production/scene-rendering'/(key+'.json'), {'fixture_only': key})
             for key in ('evidence', 'bundle', 'model', 'python', 'worker')}
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    native_guard=EvidenceReader()
    for item in parts.values():native_guard.capture(item['path'],item)
    evidence = dict(root=parts['evidence'], guard=native_guard, value=dict(
        runtime_bundle=parts['bundle'], model_manifest=parts['model'], native_python=parts['python'],
        production_worker=parts['worker'], package_versions={'torch': 'fixture_only'}))
    execution = build_scene_execution_budget(plan, timeline, run_id=run.name, mode='temporal_extension_v1',
        rendering_identity_sha256='a'*64, admission=parts['evidence'])
    execution_id = put(run/'production/scene-rendering/execution-budget.json', execution)
    monkeypatch.setattr(scene_clip_records.images, '_run', lambda *a, **k: run)
    monkeypatch.setattr(scene_clip_records.images, 'load_committed_plan', lambda *a, **k: (bible, plan))
    monkeypatch.setattr(scene_clip_records.images, '_inspect_original', lambda *a, **k: dict(width=16, height=9))
    monkeypatch.setattr(reference_image_records, 'require_reference_image_acceptance', lambda *a, **k: images)
    monkeypatch.setattr(temporal_scene_admission, 'verify_temporal_frozen', lambda *a, **k: evidence)
    monkeypatch.setattr(scene_execution_records, 'load_scene_execution', lambda *a, **k: execution)
    monkeypatch.setattr(scene_execution_records, 'execution_artifact', lambda *a, **k: execution_id)
    monkeypatch.setattr(scene_video_prompt_records, 'load_prompt_contract', lambda *a, **k: (contract, prompt))
    def forbidden(*a, **k): raise AssertionError('native context must branch before Wan admission/graph')
    monkeypatch.setattr(production_visual_templates, 'validate_production_model_paths', forbidden)
    monkeypatch.setattr(WorkflowTemplate, 'load', forbidden)
    context = scene_clip_records.scene_context(frozen, [], timeline)
    assert context['inputs']['schema_version'] == 4
    assert context['inputs']['protocol'] == 'longcat_native16_v1'
    assert [row['budget']['retained_frames'] for row in context['rows']] == [1, 93, 80, 27, 4]
    assert context['evidence'] is evidence


def completed_fixture(runtime_run, monkeypatch):
    import video_ai.runtime.temporal_scene_records as records
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.planning.scene_temporal import temporal_frame_mapping
    context, row, input_record, parent = request_fixture(runtime_run)
    context['rows'] = [row]
    context['plan'] = dict(total_frames=93, scenes=[dict(scene_id='scene_0001', start_frame=0, end_frame=93, unit_ids=[], bindings=[])])
    context['bible'] = {'fixture_only': True}
    context['timeline'] = SimpleNamespace(total_frames=93, as_dict=lambda: {'total_frames': 93})
    context['inputs'].update(scene_plan_sha256=canonical_digest(context['plan']),
        visual_bible_sha256=canonical_digest(context['bible']), wan_inputs_sha256=canonical_digest(context['wan']),
        timeline_sha256=canonical_digest(context['timeline'].as_dict()))
    folder = context['store'].clip_dir(row['budget']['clip_id'])
    put(folder/'input.json', input_record)
    request = records.expected_temporal_request(context, row, input_record, parent)
    workflow = records.temporal_workflow(context, row)
    put(folder/'request.json', request); put(folder/'workflow.json', workflow)
    put(folder/'consumed-condition.json',dict(schema_version=1,request_sha256=canonical_digest(request),
        input_snapshot=request['input']['snapshot'],source_frame_range=request['input']['source_frame_range'],
        condition_pixel_sha256=request['input']['condition_pixel_sha256']))
    intent = put(folder/'intent.json', dict(schema_version=1, request_sha256=canonical_digest(request),
        workflow_sha256=canonical_digest(workflow), native_diffusion_attempt=1, automatic_retry=False,
        input_snapshot=input_record['snapshot'], parent=request['parent'], text_cache_key=request['text_cache_key']))
    artifacts = {role: put(folder/name, ('fixture_only '+role).encode()) for role, name in dict(
        sample='sample.safetensors', generator='generator.safetensors', frames='frames.npy', raw_movie='raw.mp4',
        viewing_movie='viewing.mp4', source_movie='source.mp4', last_frame='last.png', contact_sheet='contact.png').items()}
    cache = put(context['store'].root/'text-context'/request['text_cache_key']/'context.safetensors', b'fixture_only cache')
    cache_binding = put(Path(cache['path']).with_suffix('.json'), dict(identity=request['text_identity'],
        cache_sha256=cache['sha256']))
    sample = put(folder/'sample-complete.json', dict(schema_version=1, algorithm='temporal_native_sample_v1',
        request_sha256=canonical_digest(request), workflow_sha256=canonical_digest(workflow), intent_sha256=intent['sha256'],
        sample=artifacts['sample'], generator=artifacts['generator'], native_diffusion_completed=True,
        text_cache_key=request['text_cache_key'], text_cache=cache, text_binding=cache_binding,
        latent_shape=[1, 16, 24, 54, 96], created_at='2026-11-03T00:00:00+00:00'))
    result = dict(schema_version=1, algorithm='temporal_native_window_v1', status='complete',
        request_sha256=canonical_digest(request), workflow_sha256=canonical_digest(workflow),
        intent_sha256=intent['sha256'], sample_complete=sample, native_diffusion_calls=1,
        budget=deepcopy(row['budget']), frame_mapping=temporal_frame_mapping(row['budget'], actual_generated_frames=93),
        artifacts=artifacts, created_at='2026-11-03T00:00:00+00:00',
        technical=dict(raw=dict(frames=93, fps='16/1', width=768, height=432, pixel_exact=True),
            source=dict(frames=row['budget']['retained_frames'], fps='16/1', width=768, height=432, pixel_exact=True),
            history=dict(pixels=1, latents=1, kv_layers=0, kv_bytes=0, source_frame_range=None, condition_pixel_sha256=None)))
    put(folder/'native-result.json', result)
    # Actual media decoding is the external seam. Metadata/ownership/sample/
    # artifact/parent/observation checks remain real in this protocol fixture.
    monkeypatch.setattr(records, '_verify_native_media', lambda *a, **k: None, raising=False)
    return records, context, row, folder, result


def test_completed_window_still_requires_actual_static_review(runtime_run, monkeypatch):
    records, context, row, folder, result = completed_fixture(runtime_run, monkeypatch)
    window = records.validate_temporal_window(context, row)
    assert window['status'] == 'awaiting_static'
    assert window['generator'] == result['artifacts']['generator']
    assert window['raw_frames'] == result['artifacts']['frames']
    assert window['frame_mapping']['retained_to_generated'] == list(range(93))
    progress = records.collect_temporal_progress(context)
    assert progress['status'] == 'awaiting_static' and progress['source_clips_ready'] is False


def test_native_cache_may_be_shared_but_only_at_exact_cache_identity(runtime_run,monkeypatch):
    from video_ai.runtime.temporal_native_worker import TEXT_CACHE_ROOT
    from video_ai.planning.production_scenes import canonical_digest
    records,context,row,folder,result=completed_fixture(runtime_run,monkeypatch)
    sample_path=folder/'sample-complete.json';sample=context['store'].read(sample_path)
    cache=put(TEXT_CACHE_ROOT/sample['text_cache_key']/'context.safetensors',b'fixture_only shared cache')
    request=context['store'].read(folder/'request.json')
    binding=put(TEXT_CACHE_ROOT/sample['text_cache_key']/'binding.json',dict(identity=request['text_identity'],cache_sha256=cache['sha256']))
    sample.update(text_cache=cache,text_binding=binding)
    result['sample_complete']=put(sample_path,sample);put(folder/'native-result.json',result)
    assert records.validate_temporal_window(context,row)['status']=='awaiting_static'


@pytest.mark.parametrize('fault',['missing','snapshot','pixel'])
def test_missing_or_drifted_consumption_receipt_cannot_claim_technical_success(runtime_run,monkeypatch,fault):
    from video_ai.runtime.production_state import ProductionRefused
    records,context,row,folder,result=completed_fixture(runtime_run,monkeypatch)
    path=folder/'consumed-condition.json'
    if fault=='missing':path.unlink()
    else:
        value=context['store'].read(path)
        if fault=='snapshot':value['input_snapshot']['sha256']='f'*64
        else:value['condition_pixel_sha256']='c'*64
        put(path,value)
    with pytest.raises(ProductionRefused):records.validate_temporal_window(context,row)


@pytest.mark.parametrize('fault', ['request', 'intent', 'sample', 'artifact', 'history', 'mapping', 'clock', 'twice',
                                  'latent_bool', 'pixel_not_bool', 'width_float'])
def test_terminal_worker_claim_cannot_bypass_actual_bindings(fault, runtime_run, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    records, context, row, folder, result = completed_fixture(runtime_run, monkeypatch)
    if fault == 'request': result['request_sha256'] = 'f'*64
    elif fault == 'intent': put(folder/'intent.json', {'changed': True})
    elif fault == 'sample': put(folder/'sample-complete.json', {'changed': True})
    elif fault == 'artifact': Path(result['artifacts']['frames']['path']).write_bytes(b'changed')
    elif fault == 'history': result['technical']['history']['pixels'] = 13
    elif fault == 'mapping': result['frame_mapping']['retained_to_generated'][0] = 1
    elif fault == 'clock': result['technical']['source']['fps'] = '15/1'
    elif fault == 'latent_bool':
        sample_path = folder/'sample-complete.json'
        sample = json.loads(sample_path.read_bytes()); sample['latent_shape'][0] = True
        result['sample_complete'] = put(sample_path, sample)
    elif fault == 'pixel_not_bool': result['technical']['raw']['pixel_exact'] = 1
    elif fault == 'width_float': result['technical']['raw']['width'] = 768.0
    else: result['native_diffusion_calls'] = 2
    put(folder/'native-result.json', result)
    with pytest.raises(ProductionRefused): records.validate_temporal_window(context, row)


def test_intent_without_result_is_unknown_and_committed_latent_is_decode_only(runtime_run, monkeypatch):
    records, context, row, folder, result = completed_fixture(runtime_run, monkeypatch)
    (folder/'native-result.json').unlink()
    state = records.validate_temporal_window(context, row)
    assert state['status'] == 'sampled_decode_pending' and state['resample_allowed'] is False
    (folder/'sample-complete.json').unlink()
    state = records.validate_temporal_window(context, row)
    assert state['status'] == 'unknown' and state['resample_allowed'] is False
