"""Source validation tests use declared synthetic transactions, not model claims."""
from copy import deepcopy
import json
import pytest
from uuid import uuid4

from research_material_helpers import wan_transaction
from scene_continuity_helpers import save
from video_ai.runtime._scene_continuity_io import artifact
from video_ai.runtime.manifest import now


def verify(index, config):
    from video_ai.runtime.research_material_records import verify_wan_material
    return verify_wan_material(index, config=config)


def test_complete_transaction_preserves_research_kind(runtime_run):
    run, config, _ = runtime_run
    item = wan_transaction(run, config)
    result = verify(item['index'], config)
    assert result['source_kind'] == 'research_wan_material_v1'
    assert result['source'] == artifact(item['output'])
    assert result['production_eligible'] is False
    assert result['ready_for_propose'] is False


@pytest.mark.parametrize('mutation', ['double_post', 'client', 'graph', 'output', 'input'])
def test_transaction_substitution_refused(runtime_run, mutation):
    run, config, _ = runtime_run
    item = wan_transaction(run, config)
    if mutation == 'double_post':
        save(item['post'].with_name('other.request.json'), json.loads(item['post'].read_text()))
    elif mutation == 'input':
        item['model_input'].write_bytes(b'changed model input')
    else:
        history = json.loads(item['history'].read_text())
        value = next(iter(history.values()))
        if mutation == 'client': value['prompt'][3]['client_id'] = 'wrong-client'
        if mutation == 'graph': value['prompt'][2]['97']['inputs']['image'] = 'another.png'
        if mutation == 'output':
            value['outputs']['108']['images'][0]['filename'] = 'other.mp4'
            item['output'].with_name('other.mp4').write_bytes(item['output'].read_bytes())
        save(item['history'], history)
        response = item['history'].with_name('history.response.json')
        record = json.loads(response.read_text())
        record['bytes'] = item['history'].stat().st_size
        save(response, record)
    match = {'double_post': 'exactly one', 'client': 'prompt/client/graph',
             'graph': 'prompt/client/graph', 'output': 'prefix', 'input': 'bytes changed'}[mutation]
    with pytest.raises((ValueError, OSError), match=match):
        verify(item['index'], config)


def test_index_cannot_assert_generated_without_transaction(runtime_run):
    run, config, _ = runtime_run
    path = save(run / 'assertion.json', dict(schema_version=1, generated=True))
    with pytest.raises(ValueError): verify(path, config)


def test_metadata_only_transaction_never_becomes_admitted_material(runtime_run):
    from video_ai.runtime.production_research_material import import_research_material
    run, config, paths = runtime_run
    item = wan_transaction(run, config)
    request = save(run / 'import.json', dict(schema_version=1, material_id=str(uuid4()),
        policy='research_material_import_v1', source_index=artifact(item['index']),
        config=artifact(config.config_file, runtime=False), requested_at=now(), reason='fixture-only import rejection'))
    before = {p for p in paths.runs_root.iterdir()}
    with pytest.raises((ValueError, OSError)):
        import_research_material(request, paths=paths)
    assert {p for p in paths.runs_root.iterdir()} == before


def test_material_uuid_cannot_fork_by_changing_timestamp(runtime_run):
    from video_ai.runtime.production_research_material import bind_material_uuid
    from datetime import datetime, timezone, timedelta
    from uuid import UUID
    run, _, paths = runtime_run
    mid = str(uuid4())
    first = dict(schema_version=1, material_id=mid, requested_at=datetime.now(timezone.utc).isoformat())
    path = save(run/'first-request.json', first)
    bound = bind_material_uuid(first, artifact(path), paths=paths)
    changed = dict(first, requested_at=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat())
    other = save(run/'changed-request.json', changed)
    with pytest.raises(ValueError, match='UUID'):
        bind_material_uuid(changed, artifact(other), paths=paths)
    assert not bound.exists()


def test_research_import_never_adopts_an_existing_production_run(runtime_run):
    from video_ai.runtime.production_research_material import prepare_import_run
    run, _, _ = runtime_run
    marker = run/'original.txt'
    marker.write_bytes(b'protected original')
    with pytest.raises(ValueError, match='existing run'):
        prepare_import_run(run, b'new research request')
    assert marker.read_bytes() == b'protected original'
    assert not (run/'research').exists()
