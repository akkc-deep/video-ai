"""Independent native request identities; never constructs a Comfy submission."""
from copy import deepcopy
import hashlib
from pathlib import Path

from ..adapters.common import strict_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from ..planning.scene_temporal import CLOCK_POLICY, PROTOCOL, validate_temporal_clip
from ..planning.source_clips import _integer
from .production_state import ProductionRefused, object_fields
from .scene_clip_observations import _nonempty, _sha
from .temporal_scene_admission import _refused
from .manifest import thaw

INPUT_FIELDS = ('schema_version algorithm clip_id kind source snapshot source_frame_range '
                'parent_result_sha256 condition_pixel_sha256').split()
PARAMETERS = ('positive negative seed width height length fps output_clock_policy steps cfg resolution '
              'num_cond_frames use_kv_cache offload_kv_cache enhance_hf').split()


def _artifact(context, value):
    context['store'].validate_artifact(value)
    return deepcopy(value)


def temporal_workflow(context, row) -> dict:
    """A native call manifest, separate from Wan graph and HTTP transactions."""
    budget = validate_temporal_clip(row['budget'])
    parameters = row['parameters']
    object_fields(parameters, PARAMETERS, 'native sampling parameters')
    for name in ('positive', 'negative'): _nonempty(parameters[name], name)
    _integer(parameters['seed'], 'native seed')
    if parameters['seed'] >= 2**64: raise ProductionRefused('native seed exceeds uint64')
    expected = dict(width=768, height=432, length=93, fps=16, steps=50,
                    num_cond_frames=1 if budget['ordinal'] == 1 else 13)
    for key, value in expected.items():
        if type(parameters[key]) is not int or parameters[key] != value:
            raise ProductionRefused('native sampling '+key+' differs')
    if (type(parameters['cfg']) not in (int, float) or parameters['cfg'] != 4.0
            or parameters['resolution'] != '432p-native16' or parameters['output_clock_policy'] != CLOCK_POLICY
            or parameters['use_kv_cache'] is not True or parameters['offload_kv_cache'] is not True
            or parameters['enhance_hf'] is not False):
        raise ProductionRefused('native fixed numerical protocol differs')
    admitted = context['evidence']['value']
    return dict(schema_version=1, algorithm='longcat_native_workflow_v1', protocol=PROTOCOL,
        runtime_bundle=deepcopy(admitted['runtime_bundle']), model_manifest=deepcopy(admitted['model_manifest']),
        native_python=deepcopy(admitted['native_python']), production_worker=deepcopy(admitted['production_worker']),
        package_versions=deepcopy(admitted['package_versions']), width=768, height=432, raw_frames=93,
        output_fps=16, output_clock_policy=CLOCK_POLICY, history_pixels=expected['num_cond_frames'],
        history_latents=1 if budget['ordinal'] == 1 else 4, allocator_backend='cudaMallocAsync',
        num_inference_steps=50, guidance_scale=4.0, scheduler='official_flow_match_euler_discrete',
        use_kv_cache=True, offload_kv_cache=True, enhance_hf=False)


@_refused
def expected_temporal_request(context, row, input_record, parent) -> dict:
    budget = validate_temporal_clip(row['budget'])
    workflow = temporal_workflow(context, row)
    object_fields(input_record, INPUT_FIELDS, 'native condition input')
    if (type(input_record['schema_version']) is not int or input_record['schema_version'] != 1
            or input_record['algorithm'] != 'temporal_native_input_v1'
            or input_record['clip_id'] != budget['clip_id'] or input_record['kind'] != budget['input_kind']):
        raise ProductionRefused('native input identity differs')
    _artifact(context, input_record['source']); _artifact(context, input_record['snapshot'])
    bound_parent = None
    if budget['ordinal'] == 1:
        if parent is not None: raise ProductionRefused('first native window cannot have a parent')
        images = [value for value in context['wan']['scenes'] if value['scene_id'] == budget['scene_id']]
        if len(images) != 1: raise ProductionRefused('one accepted scene image required')
        selected = {key: images[0][key] for key in ('path', 'bytes', 'sha256')}
        if (input_record['source'] != selected
                or any(input_record['snapshot'][key] != selected[key] for key in ('bytes', 'sha256'))
                or input_record['source_frame_range'] is not None
                or input_record['parent_result_sha256'] is not None
                or input_record['condition_pixel_sha256'] is not None):
            raise ProductionRefused('native first condition must copy accepted original bytes')
    else:
        if not isinstance(parent, dict): raise ProductionRefused('validated native parent required')
        previous = validate_temporal_clip(parent['budget'])
        if (previous['clip_id'] != budget['parent_clip_id'] or previous['scene_id'] != budget['scene_id']
                or previous['end_frame'] != budget['start_frame'] or previous['retained_source_end'] != 93):
            raise ProductionRefused('native parent retained contribution differs')
        for role in ('result', 'raw_frames', 'generator', 'static_acceptance'): _artifact(context, parent[role])
        screening_path = context['store'].validate_artifact(parent['static_acceptance'])
        screening = strict_json(screening_path.read_bytes())
        if (screening.get('verdict') != 'acceptable' or screening.get('allow_next_window') is not True
                or screening.get('result_sha256') != parent['result']['sha256']):
            raise ProductionRefused('native parent requires current actual static acceptance')
        if (input_record['source'] != parent['raw_frames'] or input_record['source_frame_range'] != [80, 93]
                or input_record['parent_result_sha256'] != parent['result']['sha256']):
            raise ProductionRefused('native continuation must bind actual parent raw13')
        _sha(input_record['condition_pixel_sha256'])
        bound_parent = dict(clip_id=previous['clip_id'], result=deepcopy(parent['result']),
            raw_frames=deepcopy(parent['raw_frames']), generator=deepcopy(parent['generator']),
            static_acceptance=deepcopy(parent['static_acceptance']))
    parameters = row['parameters']
    selected=next(image for image in context['wan']['scenes'] if image['scene_id']==budget['scene_id'])
    selected={key:selected[key] for key in ('path','bytes','sha256')}
    text_identity = dict(algorithm='official-umt5-eager-bfloat16-layer-staging-v1',
        model_manifest_sha256=context['evidence']['value']['model_manifest']['sha256'],
        positive_sha256=hashlib.sha256(parameters['positive'].encode('utf-8')).hexdigest(),
        negative_sha256=hashlib.sha256(parameters['negative'].encode('utf-8')).hexdigest())
    return dict(schema_version=1, algorithm='longcat_native16_request_v1', production_strategy=STRATEGY,
        run_id=context['frozen'].options['run_id'], scene_id=budget['scene_id'], clip_id=budget['clip_id'],
        protocol=PROTOCOL, inputs_sha256=canonical_digest(context['inputs']),
        execution_budget=_artifact(context, context['execution_budget']), admission=deepcopy(context['evidence']['root']),
        budget=budget, parameters=deepcopy(parameters), workflow_sha256=canonical_digest(workflow),
        input=deepcopy(input_record), parent=bound_parent,selected_image=selected,
        comparison_images=deepcopy(row['comparison_images']),narration_bindings=deepcopy(row['narration_bindings']),
        visual_bible_sha256=context['inputs']['visual_bible_sha256'],text_identity=text_identity,
        text_cache_key=canonical_digest(text_identity))


@_refused
def temporal_context(frozen, units, timeline, *, paths=None, lock=None) -> dict:
    from ..planning.scene_temporal import MODE, build_scene_temporal_plan
    from .scene_clip_records import SceneClipStore, equal, images
    from .reference_image_records import require_reference_image_acceptance
    from .scene_execution_records import (ensure_scene_execution, execution_artifact, load_scene_execution)
    from .scene_video_prompt_records import load_prompt_contract, prompt_binding_context
    from .temporal_scene_admission import verify_temporal_frozen
    from ._scene_revision_origin_images import source_image_required
    run = images._run(frozen)
    evidence = verify_temporal_frozen(frozen)
    if evidence is None: raise ProductionRefused('native temporal admission required')
    bible, plan = images.load_committed_plan(frozen, units, timeline)
    selected = require_reference_image_acceptance(frozen, units, timeline)
    execution = (ensure_scene_execution(frozen, plan, timeline, lock=lock) if lock is not None
                 else load_scene_execution(frozen, plan, timeline))
    if execution['mode'] != MODE: raise ProductionRefused('native execution budget required')
    budget_artifact = execution_artifact(frozen)
    store = SceneClipStore(frozen, run, paths=paths, lock=lock, clip_ids=[row['clip_id'] for row in execution['clips']])
    store.execution_mode = MODE
    store.continuity_context = (units, timeline)
    contract, prompt_artifact = load_prompt_contract(frozen)
    if contract is None or prompt_artifact is None: raise ProductionRefused('native reviewed visual prompt required')
    binding = prompt_binding_context(frozen, contract, bible, plan, selected)
    rows = build_scene_temporal_plan(frozen, bible, plan, timeline, selected,
        prompt_contract=contract, prompt_binding_context=binding, execution=execution)
    profile = dict(name='fast', width=768, height=432, native_fps=16)
    admitted = evidence['value']
    inputs = dict(schema_version=4, production_strategy=STRATEGY, run_id=run.name,
        algorithm='scene_temporal_execution_v1', protocol=PROTOCOL, output_clock_policy=CLOCK_POLICY,
        frozen_options_sha256=canonical_digest(thaw(frozen.options)), scene_plan_sha256=canonical_digest(thaw(plan)),
        visual_bible_sha256=canonical_digest(thaw(bible)), units_sha256=canonical_digest(thaw(units)),
        timeline_sha256=canonical_digest(timeline.as_dict()), wan_inputs_sha256=canonical_digest(thaw(selected)),
        profile=profile, execution_budget=deepcopy(budget_artifact), admission=deepcopy(evidence['root']),
        runtime_bundle=deepcopy(admitted['runtime_bundle']), model_manifest=deepcopy(admitted['model_manifest']),
        native_python=deepcopy(admitted['native_python']), production_worker=deepcopy(admitted['production_worker']),
        prompt_policy='visual_v2', prompt_contract=deepcopy(prompt_artifact))
    previous = store.read('inputs.json')
    if previous is not None: equal(previous, inputs, 'native inputs')
    for image in selected['scenes']:
        if not source_image_required(frozen, image['scene_id']): continue
        item = {key: image[key] for key in ('path', 'bytes', 'sha256')}
        info = images._inspect_original(frozen, store.validate_artifact(item))
        if info['width']*9 != info['height']*16: raise ProductionRefused('selected native original must be 16:9')
        store.guard_paths[item['path']] = item
    store.guard_paths[budget_artifact['path']] = budget_artifact
    store.guard_paths[prompt_artifact['path']] = prompt_artifact
    for name in ('production/options.json', 'production/scene-plan.json', 'production/visual-bible.json',
                 'production/scene-plan-commit.json', 'production/reference-images/wan-inputs.json'):
        path = run/name
        if path.exists(): store.guard_paths[str(path)] = store.artifact(path)
    for name in ('production/image-selection', 'production/reference-images', 'production/reference-storage', 'production/jimeng'):
        directory = run/name
        inventory = {str(path) for path in directory.rglob('*.json')}
        store.guard_directories[str(directory)] = inventory
        for path in inventory: store.guard_paths[path] = store.artifact(path)
    from ._temporal_media_check_coverage import TemporalExecutionCheck
    store.execution_guard = TemporalExecutionCheck(store,frozen,budget_artifact,evidence)
    return dict(frozen=frozen, units=units, timeline=timeline, store=store, bible=bible, plan=plan,
        execution=execution, execution_budget=budget_artifact, wan=selected, rows=rows, inputs=inputs,
        evidence=evidence, template=None)


def _state(row, status):
    return dict(budget=deepcopy(row['budget']), status=status, resample_allowed=False,
                sampling_allowed=status == 'pending')


def _sample(context, folder, request, intent_id):
    store = context['store']
    sample_id = store.artifact(folder/'sample-complete.json')
    sample = store.read(folder/'sample-complete.json')
    fields = ('schema_version algorithm request_sha256 workflow_sha256 intent_sha256 sample generator '
              'native_diffusion_completed text_cache_key text_cache text_binding latent_shape created_at').split()
    object_fields(sample, fields, 'native committed sample')
    if (type(sample['schema_version']) is not int or sample['schema_version'] != 1
            or sample['algorithm'] != 'temporal_native_sample_v1'
            or sample['request_sha256'] != canonical_digest(request)
            or sample['workflow_sha256'] != request['workflow_sha256']
            or sample['intent_sha256'] != intent_id['sha256']
            or sample['native_diffusion_completed'] is not True
            or sample['text_cache_key'] != request['text_cache_key']
            or sample['latent_shape'] != [1, 16, 24, 54, 96]
            or any(type(item) is not int for item in sample['latent_shape'])):
        raise ProductionRefused('native committed sample binding differs')
    for key in ('sample', 'generator'): _artifact(context, sample[key])
    from .temporal_native_worker import QUALIFIED_TEXT_ROOT,TEXT_CACHE_ROOT
    from ._whole_scene_admission import EvidenceReader
    shared = TEXT_CACHE_ROOT/request['text_cache_key']
    for key in ('text_cache','text_binding'):
        path = Path(sample[key]['path'])
        if path.is_relative_to(store.run_dir): _artifact(context,sample[key])
        else:
            allowed = (shared/'context.safetensors',QUALIFIED_TEXT_ROOT/'text-context.safetensors') if key=='text_cache' else (shared/'binding.json',)
            if path not in allowed: raise ProductionRefused('native shared cache path differs from exact identity')
            EvidenceReader().capture(path,sample[key])
    binding = strict_json(Path(sample['text_binding']['path']).read_bytes())
    if binding.get('identity') != request['text_identity'] or binding.get('cache_sha256') != sample['text_cache']['sha256']:
        raise ProductionRefused('native consumed text cache binding differs')
    return sample, sample_id


def _verify_native_media(context, row, result):
    from ._scene_revision_origin_clips import source_clip_required
    if not source_clip_required(context['frozen'],row['budget']['clip_id']):return
    from .scene_clip_records import _decode_video, _verify_native_pixels
    store = context['store']; artifacts = result['artifacts']
    for role, count in (('raw_movie', 93), ('viewing_movie', 93), ('source_movie', row['budget']['retained_frames'])):
        _decode_video(store, artifacts[role], frames=count, width=768, height=432)
    _verify_native_pixels(store, artifacts['raw_movie'], artifacts['last_frame'],
                          row['budget']['retained_source_end']-1, 768, 432)
    _verify_native_pixels(store, artifacts['source_movie'], artifacts['last_frame'],
                          row['budget']['retained_frames']-1, 768, 432)


def _verify_consumed_history(context, folder, request):
    store = context['store']
    expected = dict(schema_version=1,request_sha256=canonical_digest(request),input_snapshot=request['input']['snapshot'],
        source_frame_range=request['input']['source_frame_range'],condition_pixel_sha256=request['input']['condition_pixel_sha256'])
    actual = store.read(folder/'consumed-condition.json')
    if canonical_digest(actual)!=canonical_digest(expected): raise ProductionRefused('native actual consumed condition receipt differs')
    if request['parent'] is None:return
    consumed = store.read(folder/'consumed-kv.json')
    object_fields(consumed,('request_sha256','layers','bytes','manifest'),'native consumed KV')
    if (consumed['request_sha256']!=canonical_digest(request) or type(consumed['layers']) is not int or consumed['layers']!=48
            or type(consumed['bytes']) is not int or consumed['bytes']!=4076863488):
        raise ProductionRefused('native consumed KV protocol differs')
    manifest_path = store.validate_artifact(consumed['manifest'])
    if manifest_path!=folder/'kv-manifest.json':raise ProductionRefused('native KV manifest path differs')
    manifest = strict_json(manifest_path.read_bytes())
    object_fields(manifest,('layers','bytes'),'native actual KV bank')
    if type(manifest['bytes']) is not int or manifest['bytes']!=4076863488 or len(manifest['layers'])!=48:
        raise ProductionRefused('native actual KV inventory differs')
    total=0;bank_folder=None
    for index,row in enumerate(manifest['layers']):
        object_fields(row,('layer','manifest','pair'),'native KV layer')
        if type(row['layer']) is not int or row['layer']!=index or len(row['pair'])!=2:raise ProductionRefused('native KV layer ordering differs')
        path=store.validate_artifact(row['manifest'])
        if (path.parent.parent!=folder or not path.parent.name.startswith('kv-workspace-') or path.name!=f'layer-{index:03d}.json'
                or bank_folder is not None and path.parent!=bank_folder):raise ProductionRefused('native KV bank provenance differs')
        bank_folder=path.parent
        if canonical_digest(strict_json(path.read_bytes()))!=canonical_digest(row['pair']):raise ProductionRefused('native KV pair bytes differ')
        for kind,item in zip(('k','v'),row['pair']):
            object_fields(item,('path','bytes','shape','dtype','sha256'),'native KV tensor')
            if (item['path']!=str(path.parent/f'layer-{index:03d}-{kind}.bf16') or item['dtype']!='BF16'
                    or canonical_digest(item['shape'])!=canonical_digest([1,32,5184,128])):
                raise ProductionRefused('native KV shape/type/source differs')
            store.validate_artifact({key:item[key] for key in ('path','bytes','sha256')});total+=item['bytes']
    if total!=4076863488:raise ProductionRefused('native actual KV full bytes differ')


def _static(context, window, folder):
    from .temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation, retained_temporal_observations
    from .scene_clip_observations import _time
    from .manifest import now
    store = context['store']
    accepted, rejected = folder/'static-accepted.json', folder/'static-rejected.json'
    if accepted.exists() and rejected.exists(): raise ProductionRefused('native static rejection history cannot be replaced')
    template = build_temporal_observation_template(context, window, scope='temporal_window_static')
    originals = retained_temporal_observations(context,folder,template,window['created_at'],now())
    has_rejection = any(value['verdict']=='rejected' for value in originals)
    if accepted.exists() and has_rejection: raise ProductionRefused('accepted native window has retained rejected author evidence')
    target = accepted if accepted.exists() else rejected if rejected.exists() else None
    if target is None:
        if has_rejection: window['status']='rejected'
        return window
    receipt = store.read(target)
    object_fields(receipt, ('schema_version', 'algorithm', 'result_sha256', 'request_sha256', 'template_sha256',
                           'observation', 'verdict', 'allow_next_window', 'accepted_at'), 'native static receipt')
    if (type(receipt['schema_version']) is not int or receipt['schema_version'] != 1
            or receipt['algorithm'] != 'temporal_window_static_acceptance_v1'
            or receipt['result_sha256'] != window['result']['sha256']
            or receipt['request_sha256'] != canonical_digest(window['request'])
            or receipt['template_sha256'] != canonical_digest(template)
            or _time(receipt['accepted_at'], 'static accepted_at') > _time(now(), 'now')):
        raise ProductionRefused('native static receipt binding differs')
    authored = strict_json(store.validate_artifact(receipt['observation']).read_bytes())
    observation = validate_temporal_observation(authored, dict(template=template, created_at=window['created_at']), receipt['accepted_at'])
    expected = 'acceptable' if target == accepted else 'rejected'
    if (observation['verdict'] != expected or receipt['verdict'] != expected
            or receipt['allow_next_window'] is not observation['allow_next_window']):
        raise ProductionRefused('native static receipt contradicts actual observation')
    window.update(static_observation=observation, status='static_ready' if target == accepted else 'rejected')
    if target == accepted: window['static_acceptance'] = store.artifact(target)
    return window


@_refused
def validate_temporal_window(context, row, parent=None) -> dict:
    from .temporal_scene_origins import inherited_temporal_window
    inherited=inherited_temporal_window(context,row,parent)
    if inherited is not None:return inherited
    from ..planning.scene_temporal import temporal_frame_mapping
    store = context['store']; budget = validate_temporal_clip(row['budget'])
    folder = store.clip_dir(budget['clip_id'])
    begun = any((folder/name).exists() for name in ('intent.json', 'launch-intent.json', 'sample-complete.json', 'native-result.json'))
    input_record, stored_request = store.read(folder/'input.json'), store.read(folder/'request.json')
    if input_record is None or stored_request is None:
        if begun: raise ProductionRefused('started native window lacks frozen input/request')
        return _state(row, 'pending')
    request = expected_temporal_request(context, row, input_record, parent)
    if canonical_digest(stored_request) != canonical_digest(request): raise ProductionRefused('stored native request drift')
    workflow = store.read(folder/'workflow.json')
    if workflow is None or canonical_digest(workflow) != request['workflow_sha256']:
        raise ProductionRefused('stored native workflow drift')
    intent = store.read(folder/'intent.json')
    if intent is None:
        if (folder/'native-result.json').exists() or (folder/'sample-complete.json').exists():
            raise ProductionRefused('native result/sample lacks original intent')
        terminal = store.read(folder/'process-terminal.json')
        status = 'failed' if terminal is not None else 'unknown' if (folder/'launch-intent.json').exists() else 'pending'
        return _state(row, status)
    if (type(intent.get('schema_version')) is not int or intent['schema_version'] != 1
            or intent.get('request_sha256') != canonical_digest(request)
            or intent.get('workflow_sha256') != request['workflow_sha256']
            or type(intent.get('native_diffusion_attempt')) is not int or intent['native_diffusion_attempt'] != 1
            or intent.get('automatic_retry') is not False
            or intent.get('input_snapshot') != input_record['snapshot'] or intent.get('parent') != request['parent']
            or intent.get('text_cache_key') != request['text_cache_key']):
        raise ProductionRefused('native once-only intent differs')
    intent_id = store.artifact(folder/'intent.json')
    sample = sample_id = None
    if (folder/'sample-complete.json').exists(): sample, sample_id = _sample(context, folder, request, intent_id)
    result = store.read(folder/'native-result.json')
    if result is None:
        status = 'sampled_decode_pending' if sample is not None else 'failed' if (folder/'process-terminal.json').exists() else 'unknown'
        return dict(_state(row, status), sample=sample, request=request)
    if sample is None: raise ProductionRefused('native technical result lacks committed sample')
    fields = ('schema_version algorithm status request_sha256 workflow_sha256 intent_sha256 sample_complete '
              'native_diffusion_calls budget frame_mapping artifacts created_at technical').split()
    object_fields(result, fields, 'native technical window')
    if (type(result['schema_version']) is not int or result['schema_version'] != 1
            or result['algorithm'] != 'temporal_native_window_v1' or result['status'] != 'complete'
            or result['request_sha256'] != canonical_digest(request) or result['workflow_sha256'] != request['workflow_sha256']
            or result['intent_sha256'] != intent_id['sha256'] or result['sample_complete'] != sample_id
            or type(result['native_diffusion_calls']) is not int or result['native_diffusion_calls'] != 1
            or canonical_digest(result['budget']) != canonical_digest(budget)
            or canonical_digest(result['frame_mapping']) != canonical_digest(temporal_frame_mapping(budget, actual_generated_frames=93))):
        raise ProductionRefused('native actual result/source/mapping differs')
    artifacts = result['artifacts']
    object_fields(artifacts, ('sample', 'generator', 'frames', 'raw_movie', 'viewing_movie', 'source_movie', 'last_frame', 'contact_sheet'), 'native result artifacts')
    for item in artifacts.values(): _artifact(context, item)
    if artifacts['sample'] != sample['sample'] or artifacts['generator'] != sample['generator']:
        raise ProductionRefused('native result sample/Generator differs')
    technical = result['technical']
    object_fields(technical, ('raw', 'source', 'history'), 'native actual media')
    for role, count in (('raw', 93), ('source', budget['retained_frames'])):
        expected_media = dict(frames=count, fps='16/1', width=768, height=432, pixel_exact=True)
        if canonical_digest(technical[role]) != canonical_digest(expected_media):
            raise ProductionRefused('native actual raw/retained media differs')
    head = budget['discard_head_frames']
    expected_history = dict(pixels=13 if head else 1, latents=4 if head else 1,
            kv_layers=48 if head else 0, kv_bytes=4076863488 if head else 0,
            source_frame_range=input_record['source_frame_range'], condition_pixel_sha256=input_record['condition_pixel_sha256'])
    if canonical_digest(technical['history']) != canonical_digest(expected_history):
        raise ProductionRefused('native actual consumed history differs')
    _verify_consumed_history(context, folder, request)
    _verify_native_media(context, row, result)
    selected = [item for item in context['wan']['scenes'] if item['scene_id'] == budget['scene_id']]
    if len(selected) != 1: raise ProductionRefused('native selected scene image missing')
    selected = {key: selected[0][key] for key in ('path', 'bytes', 'sha256')}
    observed_parent = None if parent is None else dict(result=parent['result'], raw_frames=parent['raw_frames'],
        condition_frames=input_record['snapshot'], source_frame_range=[80, 93])
    window = dict(_state(row, 'awaiting_static'), request=request, request_sha256=canonical_digest(request),
        workflow=workflow, result=store.artifact(folder/'native-result.json'),
        created_at=result['created_at'], generator=artifacts['generator'], raw_frames=artifacts['frames'],
        generated=artifacts['raw_movie'], viewing=artifacts['viewing_movie'], source=artifacts['source_movie'],
        last_frame=artifacts['last_frame'], contact_sheet=artifacts['contact_sheet'], frame_mapping=result['frame_mapping'],
        selected_image=selected, parent=observed_parent, sample_complete=sample_id,
        terminal=not any(item['budget']['parent_clip_id'] == budget['clip_id'] for item in context['rows']))
    return _static(context, window, folder)


@_refused
def collect_temporal_progress(context) -> dict:
    records, parents = [], {}
    blocked = None
    store = context['store']
    for row in context['rows']:
        parent_id = row['budget']['parent_clip_id']
        parent = parents.get(parent_id)
        if parent_id is not None and (parent is None or parent['status'] != 'static_ready'):
            folder = store.clip_dir(row['budget']['clip_id'])
            if any((folder/name).exists() for name in ('intent.json', 'launch-intent.json', 'sample-complete.json', 'native-result.json')):
                raise ProductionRefused('started native child lacks accepted current parent screening')
            window = _state(row, 'waiting_parent')
        else:
            window = validate_temporal_window(context, row, parent)
        records.append(window); parents[row['budget']['clip_id']] = window
        if blocked is None and window['status'] != 'static_ready': blocked = window['status']
    chains = []
    if blocked is None:
        scene_ids = list(dict.fromkeys(row['budget']['scene_id'] for row in context['rows']))
        for scene_id in scene_ids:
            windows = [window for window in records if window['budget']['scene_id'] == scene_id]
            chain = validate_temporal_chain(context, scene_id, windows)
            chains.append(chain)
            if blocked is None and chain['status'] != 'accepted': blocked = chain['status']
    ready = blocked is None
    return dict(status='source_clips_ready' if ready else blocked, source_clips_ready=ready, records=records, chains=chains)


def temporal_chain_sources(windows):
    return [dict(clip_id=window['budget']['clip_id'], result=deepcopy(window['result']), raw_frames=deepcopy(window['raw_frames']),
        source_frame_range=[window['budget']['retained_source_start'], window['budget']['retained_source_end']],
        chain_frame_range=[window['budget']['start_frame'], window['budget']['end_frame']]) for window in windows]


def temporal_progress_view(context):
    """Explicit native views for shared continuity/revision consumers; no HTTP records."""
    from .production_temporal_scene_clips import _scenes
    from .temporal_scene_observations import build_temporal_observation_template
    progress=collect_temporal_progress(context)
    chains={chain['scene_id']:chain for chain in progress['chains'] if 'result' in chain}
    records={}
    for window in progress['records']:
        if 'result' not in window:continue
        budget=window['budget'];cid=budget['clip_id'];chain=chains.get(budget['scene_id'])
        clip=dict(schema_version=4,protocol=PROTOCOL,run_id=context['store'].run_dir.name,scene_id=budget['scene_id'],clip_id=cid,
            generated=window['generated'],source=window['source'],native_result=window['result'],raw_frames=window['raw_frames'],
            generator=window['generator'],created_at=window['created_at'],request_sha256=window['request_sha256'])
        if 'origin_clip_view' in window:clip=deepcopy(window['origin_clip_view'])
        records[cid]=dict(native_window=window,native_chain=chain,clip=clip,request=window['request'],mapping=window['frame_mapping'],
            last_frame=dict(image=window['last_frame'],source_frame_index=budget['retained_source_end']-1,
                global_output_frame_index=budget['end_frame']-1),
            accepted=chain.get('acceptance') if chain and chain['status']=='accepted' else None,
            rejected=chain.get('acceptance',dict(raw_only=True)) if chain and chain['status']=='rejected' else None,
            template=deepcopy(chain['origin_template']) if chain and 'origin_template' in chain else build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process') if chain else None)
    return dict(scenes=_scenes(context,progress),status=progress['status'],source_clips_ready=progress['source_clips_ready']),records


def _verify_native_chain_media(context, chain):
    from ._scene_revision_origin_clips import source_clip_required
    if not any(source_clip_required(context['frozen'],window['budget']['clip_id']) for window in chain['windows']):return
    from .scene_clip_records import _decode_video, _verify_native_pixels
    count = chain['frame_range'][1]-chain['frame_range'][0]
    for role in ('raw_movie', 'viewing_movie'):
        _decode_video(context['store'], chain['artifacts'][role], frames=count, width=768, height=432)
    for window in chain['windows']:
        index = window['budget']['end_frame']-chain['frame_range'][0]-1
        _verify_native_pixels(context['store'], chain['artifacts']['raw_movie'], window['last_frame'], index, 768, 432)


@_refused
def validate_temporal_chain(context, scene_id, windows) -> dict:
    from .temporal_scene_observations import build_temporal_observation_template, validate_temporal_observation, retained_temporal_observations
    from .scene_clip_observations import _time
    from .manifest import now
    store = context['store']; folder = store.path(Path('chains')/scene_id)
    if not windows or any(window['status'] != 'static_ready' for window in windows):
        raise ProductionRefused('native chain requires all actual static screenings')
    from .temporal_scene_origins import inherited_temporal_chain
    inherited=inherited_temporal_chain(context,scene_id,windows)
    if inherited is not None:return inherited
    raw = store.read(folder/'result.json')
    if raw is None: return dict(scene_id=scene_id, status='awaiting_chain_assembly', windows=windows)
    fields = ('schema_version algorithm scene_id inputs_sha256 frames fps frame_range boundary_frames windows artifacts '
              'technical history_output_once blend_interpolate_repeat_or_retime new_model_calls created_at').split()
    object_fields(raw, fields, 'native assembled chain')
    sources = temporal_chain_sources(windows)
    start, end = sources[0]['chain_frame_range'][0], sources[-1]['chain_frame_range'][1]
    cursor = start
    for source in sources:
        if source['chain_frame_range'][0] != cursor: raise ProductionRefused('native chain contribution gap/overlap')
        cursor = source['chain_frame_range'][1]
    identity = dict(schema_version=1, algorithm='longcat_native_scene_chain_v1', scene_id=scene_id,
        inputs_sha256=canonical_digest(context['inputs']), frames=end-start, fps='16/1', frame_range=[start, end],
        boundary_frames=[row['chain_frame_range'][0] for row in sources[1:]], windows=sources,
        history_output_once=True, blend_interpolate_repeat_or_retime=False, new_model_calls=0)
    if canonical_digest({key: raw[key] for key in identity}) != canonical_digest(identity):
        raise ProductionRefused('native assembled chain identity/mapping differs')
    artifacts = raw['artifacts']
    object_fields(artifacts, ('frames', 'raw_movie', 'viewing_movie', 'mapping', 'diagnostics'), 'native chain artifacts')
    for item in artifacts.values(): _artifact(context, item)
    mapping = strict_json(store.validate_artifact(artifacts['mapping']).read_bytes())
    expected_mapping = dict(schema_version=1, protocol=PROTOCOL, fps='16/1', frame_range=[start, end], windows=sources,
                            history_output_once=True, blend_interpolate_repeat_or_retime=False)
    if canonical_digest(mapping) != canonical_digest(expected_mapping): raise ProductionRefused('native chain mapping bytes differ')
    technical = dict(raw=dict(frames=end-start, fps='16/1', width=768, height=432, pixel_exact=True),
                     viewing=dict(frames=end-start, fps='16/1', width=768, height=432, pixel_exact=False))
    if canonical_digest(raw['technical']) != canonical_digest(technical): raise ProductionRefused('native chain actual technical media differs')
    chain = dict(scene_id=scene_id, status='awaiting_chain_review', result=store.artifact(folder/'result.json'),
        selected_image=deepcopy(windows[0]['selected_image']), viewing=artifacts['viewing_movie'], artifacts=artifacts,
        windows=windows, created_at=raw['created_at'], frame_range=[start, end], boundary_frames=identity['boundary_frames'])
    _verify_native_chain_media(context, chain)
    accepted, rejected = folder/'accepted.json', folder/'rejected.json'
    if accepted.exists() and rejected.exists(): raise ProductionRefused('native chain rejection history cannot be replaced')
    template = build_temporal_observation_template(context, chain, scope='scene_temporal_chain_process')
    originals = retained_temporal_observations(context,folder,template,raw['created_at'],now())
    has_rejection = any(value['verdict']=='failed' for value in originals)
    if accepted.exists() and has_rejection: raise ProductionRefused('accepted native chain has retained failed author evidence')
    target = accepted if accepted.exists() else rejected if rejected.exists() else None
    if target is None:
        if has_rejection: chain['status']='rejected'
        return chain
    receipt = store.read(target)
    object_fields(receipt, ('schema_version', 'algorithm', 'result_sha256', 'template_sha256', 'observation', 'verdict', 'accepted_at'), 'native chain acceptance')
    if (type(receipt['schema_version']) is not int or receipt['schema_version'] != 1
            or receipt['algorithm'] != 'temporal_chain_acceptance_v1'
            or receipt['result_sha256'] != chain['result']['sha256']
            or receipt['template_sha256'] != canonical_digest(template)
            or _time(receipt['accepted_at'], 'chain accepted_at') > _time(now(), 'now')):
        raise ProductionRefused('native complete-chain acceptance binding differs')
    authored = strict_json(store.validate_artifact(receipt['observation']).read_bytes())
    observation = validate_temporal_observation(authored, dict(template=template, created_at=raw['created_at']), receipt['accepted_at'])
    expected_verdict = 'passed' if target == accepted else 'failed'
    if observation['verdict'] != expected_verdict or receipt['verdict'] != expected_verdict:
        raise ProductionRefused('native chain receipt contradicts actual complete observation')
    chain.update(status='accepted' if target == accepted else 'rejected', observation=observation,
                 acceptance=store.artifact(target))
    return chain


@_refused
def complete_temporal_value(context, records) -> dict:
    """Re-read actual windows/reviews; caller-supplied ready flags have no authority."""
    progress = collect_temporal_progress(context)
    if not progress['source_clips_ready']: raise ProductionRefused('all native windows and full-chain observations required')
    if canonical_digest(records) != canonical_digest(progress['records']):
        raise ProductionRefused('native complete index caller records differ from actual source')
    by_clip = {window['budget']['clip_id']: window for window in progress['records']}
    by_scene = {chain['scene_id']: chain for chain in progress['chains']}
    clips, scenes, cursor = [], [], 0
    for row in context['rows']:
        budget = row['budget']; window = by_clip[budget['clip_id']]; chain = by_scene[budget['scene_id']]
        if budget['start_frame'] != cursor: raise ProductionRefused('native index contribution gap/overlap')
        cursor = budget['end_frame']
        clips.append(dict(clip_id=budget['clip_id'], scene_id=budget['scene_id'], budget=deepcopy(budget),
            narration_bindings=deepcopy(row['narration_bindings']), generated=window['generated'], source=window['source'],
            frame_mapping=window['frame_mapping'], last_frame=window['last_frame'], clip_sha256=window['result']['sha256'],
            observation_acceptance_sha256=chain['acceptance']['sha256'], temporal_chain=dict(acceptance=chain['acceptance'],
                source_frame_range=[budget['start_frame']-chain['frame_range'][0], budget['end_frame']-chain['frame_range'][0]])))
    if cursor != context['timeline'].total_frames: raise ProductionRefused('native index must cover complete timeline')
    for scene in context['plan']['scenes']:
        chain = by_scene[scene['scene_id']]
        if chain['frame_range'] != [scene['start_frame'], scene['end_frame']]: raise ProductionRefused('native scene contribution differs')
        scenes.append(dict({key: deepcopy(scene[key]) for key in ('scene_id', 'unit_ids', 'start_frame', 'end_frame', 'bindings')},
            selected_image=deepcopy(next(row for row in context['wan']['scenes'] if row['scene_id'] == scene['scene_id'])),
            clip_ids=[row['budget']['clip_id'] for row in context['rows'] if row['budget']['scene_id'] == scene['scene_id']]))
    inputs = context['inputs']
    return dict(schema_version=4, production_strategy=STRATEGY, run_id=context['store'].run_dir.name,
        protocol=PROTOCOL, inputs_sha256=canonical_digest(inputs),
        **{key: inputs[key] for key in ('scene_plan_sha256', 'visual_bible_sha256', 'wan_inputs_sha256', 'timeline_sha256')},
        execution_budget=deepcopy(context['execution_budget']), total_frames=cursor, scenes=scenes, clips=clips,
        temporal_chains=[dict(scene_id=chain['scene_id'], result=chain['result'], acceptance=chain['acceptance'],
                              frame_range=chain['frame_range']) for chain in progress['chains']])
