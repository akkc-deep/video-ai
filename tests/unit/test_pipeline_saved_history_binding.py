"""TEST ONLY real saved PNGs require independently bound current history."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest


@pytest.mark.parametrize('field', ['prompt', 'client', 'graph', 'number'])
def test_native_saved_media_replay_refuses_history_metadata_before_inspection(runtime_run, monkeypatch, field):
    from unit.test_pipeline_saved_import import fixture
    from video_ai.runtime.pipeline_recovery import _native_saved_validation
    run, config, store, output, response = fixture(runtime_run, monkeypatch)
    saved = dict(store.snapshot()['units']['image']['shot_0001']['submission'],
        prompt_id='test-prompt', number=1, state='completed')
    graph = json.loads(Path(saved['request_path']).read_text(encoding='utf-8'))
    entry = json.loads((run/'logs/pipeline/TEST-ONLY-history.json').read_text(encoding='utf-8'))['test-prompt']
    if field == 'prompt': entry['prompt'][1] = 'unrelated-prompt'
    if field == 'client': entry['prompt'][3]['client_id'] = 'unrelated-client'
    if field == 'graph': entry['prompt'][2]['1']['inputs']['seed'] += 1
    if field == 'number': entry['prompt'][0] = 2
    before = store.snapshot()
    with pytest.raises(ValueError, match='saved history prompt/client/graph/number differs'):
        _native_saved_validation(config, run, 'start_images', 'shot_0001', saved, entry, graph)
    assert store.snapshot() == before


def test_saved_completed_native_sibling_wrong_history_number_cannot_create_child(runtime_run, monkeypatch):
    from unit.test_pipeline_saved_import import fixture
    from video_ai.runtime import start_image_checks as owner
    from video_ai.runtime._pipeline_saved_import import derive_reconciled_run
    from video_ai.runtime.manifest import hash_file, thaw
    from video_ai.runtime.timeline_checks import _artifact
    from video_ai.planning.start_images import image_parameters
    run, config, store, output, response = fixture(runtime_run, monkeypatch)
    board, _ = owner._input_files(config, run)
    second = dict(board['shots'][0], shot_id='shot_0002', primary_unit_id='speech_0002')
    board['shots'].append(second)
    parameters = image_parameters(second, board['global_visual'], 768, 432)
    template = owner._template(config)
    graph = template.instantiate(dict(positive_prompt=parameters['positive'], negative_prompt=parameters['negative'],
        seed=parameters['seed'], width=768, height=432), output_prefix=f'{run.name}/start_images/shot_0002')
    attempt, client, prompt = str(uuid4()), str(uuid4()), str(uuid4())
    graph_path = run/'workflows'/f'{attempt}.json'
    graph_path.write_text(json.dumps(graph), encoding='utf-8')
    request = dict(method='POST', url=config.services['comfyui']+'/prompt', stage='start_images',
        unit_id='shot_0002', timeout=2, json_body={'prompt':graph, 'client_id':client})
    (run/'logs/http/sibling.request.json').write_text(json.dumps(request), encoding='utf-8')
    store.record_unit('image', 'shot_0002', 'running')
    sibling = output.with_name('shot_0002_00001_.png')
    sibling.write_bytes(output.read_bytes())
    entry = dict(prompt=[3, prompt, graph, {'client_id':client}, ['1']],
        status={'completed':True, 'status_str':'success'},
        outputs={'1':{'images':[dict(filename=sibling.name, subfolder=f'{run.name}/start_images', type='output')]}})
    history = run/'logs/pipeline/sibling-history.json'
    history.write_text(json.dumps({prompt:entry}), encoding='utf-8')
    saved = dict(attempt_id=attempt, client_id=client, state='completed', request_path=str(graph_path),
        response_path=str(history), prompt_id=prompt, number=2,
        submitted_at='2026-01-01T00:00:00+00:00', last_seen_at='2026-01-01T00:00:01+00:00')
    store.record_unit('image', 'shot_0002', 'running', submission=dict(saved, state='intent',
        response_path=None, prompt_id=None, number=None, last_seen_at=None))
    store.record_unit('image', 'shot_0002', 'running', submission=dict(saved, state='accepted'))
    store.record_unit('image', 'shot_0002', 'completed', artifacts=[_artifact(hash_file(sibling))], submission=saved)
    store.update(lambda data: data['workflows'].update({attempt:thaw(hash_file(graph_path))}))
    before = store.snapshot()
    directories = set(run.parent.iterdir())
    with pytest.raises(ValueError, match='saved history prompt/client/graph/number differs'):
        derive_reconciled_run(config, parent_run_dir=run, plan=SimpleNamespace(reused=()), reconciliations=(response,))
    assert set(run.parent.iterdir()) == directories
    assert store.snapshot() == before
