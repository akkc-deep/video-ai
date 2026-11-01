import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def study(tmp_path, resource_config, monkeypatch):
    from video_ai.experiments import natural_acquisition as records
    monkeypatch.setattr(records, 'COLLECTION_ROOT', tmp_path)
    monkeypatch.setattr(records, 'load_config', lambda path: resource_config)
    root = tmp_path / 'runtime-study'
    plan = records.freeze_collection(root, Path(__file__).parents[2]/'config/jimeng.example.json')
    return root, plan, records


def test_status_keeps_all_unacquired_cases_and_unknown_labels(study):
    from video_ai.experiments.natural_acquisition_runtime import collection_status
    root, _, _ = study
    result = collection_status(root)
    assert len(result['cases']) == 24
    assert result['generated_videos'] == 0
    assert result['observed_natural_positives'] == 0
    assert all(c['status'] == 'not_started' for c in result['cases'])
    assert result['ready_for_propose'] is False


@pytest.mark.parametrize('command', ['acquire_case', 'prepare_case'])
def test_unknown_case_rejected_before_any_run_or_service(study, command):
    from video_ai.experiments import natural_acquisition_runtime as runtime
    root, _, _ = study
    before = sorted(str(p) for p in root.rglob('*'))
    with pytest.raises(ValueError, match='case'):
        getattr(runtime, command)(root, '../invalid')
    assert sorted(str(p) for p in root.rglob('*')) == before


def test_reference_drift_blocks_acquisition_before_case_directory(study):
    from video_ai.experiments.natural_acquisition_runtime import acquire_case
    root, plan, _ = study
    reference = Path(plan['scenes'][0]['reference']['path'])
    reference.write_bytes(reference.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='identity'):
        acquire_case(root, plan['cases'][0]['case_id'])
    assert not (root/'cases').exists()


def test_existing_unfinished_case_never_creates_new_request(study, monkeypatch):
    from video_ai.experiments import natural_acquisition_runtime as runtime
    root, plan, _ = study
    folder = root/'cases'/plan['cases'][0]['case_id']
    folder.mkdir(parents=True)
    called = []
    monkeypatch.setattr(runtime, '_generate_new', lambda *a: called.append(a))
    with pytest.raises(ValueError, match='existing|incomplete|locator'):
        runtime.acquire_case(root, plan['cases'][0]['case_id'])
    assert called == []


def test_existing_locator_is_never_dispatched_as_new(study, monkeypatch):
    from video_ai.experiments import natural_acquisition_runtime as runtime
    root, plan, records = study
    case = plan['cases'][0]
    records.write_json(root/'cases'/case['case_id']/'generation-run.json', dict(run_dir='missing'))
    called = []
    monkeypatch.setattr(runtime, '_generate_new', lambda *a: called.append(a))
    with pytest.raises((ValueError, OSError, KeyError)):
        runtime.acquire_case(root, case['case_id'])
    assert not called


def test_preparation_does_not_generate_when_output_missing(study, monkeypatch):
    from video_ai.experiments import natural_acquisition_runtime as runtime
    root, plan, _ = study
    monkeypatch.setattr(runtime, '_generate_new', lambda *a: pytest.fail('must not generate'))
    with pytest.raises((ValueError, OSError)):
        runtime.prepare_case(root, plan['cases'][0]['case_id'])


def test_cli_unknown_collection_is_structured(tmp_path, capsys):
    import json
    path = Path(__file__).parents[2]/'scripts/experiments/vco06_acquire.py'
    spec = importlib.util.spec_from_file_location('acquisition_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = module.main(['status', '--root', str(tmp_path/'not-created')])
    result = json.loads(capsys.readouterr().out)
    assert code == 2 and result['status'] == 'blocked'
    assert result['ready_for_propose'] is False


def test_png_cannot_be_reported_as_generated_original_video(study, runtime_run):
    from video_ai.experiments.natural_acquisition_runtime import acquire_case
    root, plan, records = study
    run, _, _ = runtime_run
    case = plan['cases'][0]
    folder = root/'cases'/case['case_id']
    records.write_json(folder/'generation-run.json',dict(run_dir=str(run),case_id=case['case_id'],
        collection=records.read_json(root/'collection-receipt.json')['collection']))
    graph = records.write_json(folder/'evidence/wan-graph.json',{})
    options = records.write_json(folder/'evidence/options.json',{})
    request = records.write_json(folder/'evidence/wan-material-request.json',dict(run_dir=str(run),
        selected_image=case['reference'],actual_model_input=case['reference'],conversion=case['conversion'],
        graph=graph,frozen_options=options,parameters=dict(positive_prompt=case['positive_prompt'],
            start_image=run.name+'/vco06_material/selected-reference.png',width=768,height=432,length=49,
            fps=16,seed_high=case['seed_high'],seed_low=0)))
    records.write_json(folder/'evidence/generation-result.json',dict(status='generated',request=request,
        selected_image=case['reference'],video=case['reference'],original_model_output=case['reference']))
    with pytest.raises((ValueError,OSError,KeyError)):
        acquire_case(root,case['case_id'])


def test_original_http_acceptance_restores_missing_manifest_prompt_without_post(runtime_run):
    from video_ai.experiments.natural_acquisition_runtime import _original_acceptance
    from video_ai.experiments.natural_acquisition import write_json
    from video_ai.runtime.logging import RunLogger
    from uuid import uuid4
    run, _, _ = runtime_run
    logger = RunLogger(run,production=True)
    client, prompt = str(uuid4()),str(uuid4())
    graph = {'fixture_only':{'class_type':'fixture_only'}}
    saved = dict(prompt_id=None,number=None,client_id=client,state='intent')
    body = write_json(logger.path('http/post.body'),dict(prompt_id=prompt,number=1,node_errors={}))
    write_json(logger.path('http/post.request.json'),dict(method='POST',url='http://127.0.0.1:8188/prompt',
        unit_id='shot_0001:attempt_0001',json_body=dict(prompt=graph,client_id=client)))
    write_json(logger.path('http/post.response.json'),dict(method='POST',url='http://127.0.0.1:8188/prompt',
        unit_id='shot_0001:attempt_0001',status=200,truncated=False,error=None,bytes=body['bytes']))
    before = sorted(str(p) for p in run.rglob('*'))
    restored = _original_acceptance(logger,saved,graph,'http://127.0.0.1:8188')
    assert restored['prompt_id'] == prompt and restored['number'] == 1
    assert saved['prompt_id'] is None
    assert before == sorted(str(p) for p in run.rglob('*'))


def test_empty_import_file_never_counts_as_a_verified_import(study):
    from video_ai.experiments.natural_acquisition_runtime import collection_status
    root, plan, records = study
    case = plan['cases'][0]
    records.write_json(root/'cases'/case['case_id']/'import-result.json',{})
    status = collection_status(root)
    assert status['import_receipts'] == 0
    assert status['cases'][0]['status'] != 'import_recorded'
