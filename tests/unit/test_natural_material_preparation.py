from pathlib import Path

import pytest


def test_mapping_evidence_is_external_to_clean_color_audit(runtime_run, tmp_path):
    from video_ai.experiments.natural_material_preparation import save_mapping_evidence
    from video_ai.media.colorimetry import _audit
    from video_ai.runtime.logging import RunLogger
    from video_ai.experiments.natural_acquisition import read_json
    run, _, paths = runtime_run
    logger = RunLogger(run)
    source = tmp_path/'fixture.mp4';source.write_bytes(b'fixture only, never model evidence')
    rows = [dict(asset_frame_index=0,generated_frame_index=0,retained_frame_index=None,
                 output_frame_index=None,clip_id='wan_material_0001',pts=0,time_base='1/16')]
    proof = save_mapping_evidence(tmp_path/'case',source,rows,audit_id=run.name)
    assert not proof.is_relative_to(run)
    assert read_json(proof)['rows'] == rows
    _audit(paths,logger)  # Real original guard, unchanged and still strict.
    assert list(logger.root.iterdir()) == []


def test_mapping_evidence_is_immutable_and_source_bound(runtime_run, tmp_path):
    from video_ai.experiments.natural_material_preparation import save_mapping_evidence
    from video_ai.experiments.natural_acquisition import read_json, identity
    run, _, _ = runtime_run
    source = tmp_path/'fixture.mp4';source.write_bytes(b'fixture only')
    proof = save_mapping_evidence(tmp_path/'case',source,[],audit_id=run.name)
    raw = proof.read_bytes()
    assert read_json(proof)['source']['sha256'] == identity(source)['sha256']
    assert save_mapping_evidence(tmp_path/'case',source,[],audit_id=run.name) == proof
    assert proof.read_bytes() == raw
    with pytest.raises(ValueError,match='differs'):
        save_mapping_evidence(tmp_path/'case',source,[dict(changed=True)],audit_id=run.name)


def test_preparation_rejects_unknown_collection_without_model_request(tmp_path):
    from video_ai.experiments.natural_material_preparation import prepare_native_source_v2
    with pytest.raises((ValueError,OSError)):
        prepare_native_source_v2(tmp_path/'missing-collection','not-a-case')


@pytest.mark.parametrize('foreign', ['source_index','import_index','import_config','completion'])
def test_resuming_cannot_import_another_valid_cases_transaction(tmp_path, resource_config, monkeypatch, foreign):
    from video_ai.experiments import natural_material_preparation as module
    from video_ai.experiments.natural_acquisition import read_json, write_json, identity
    from video_ai.runtime.paths import RuntimePaths, create_run
    from video_ai.runtime.research_material_records import verify_wan_material
    from research_material_helpers import wan_transaction
    paths = RuntimePaths.from_config(resource_config)
    own = wan_transaction(create_run(paths),resource_config)
    other = wan_transaction(create_run(paths),resource_config)
    assert verify_wan_material(other['index'],config=resource_config)['source_kind'] == 'research_wan_material_v1'
    folder = tmp_path/'case'; folder.mkdir()
    own_result = read_json(own['result'])
    write_json(folder/'evidence/generation-result.json',own_result)
    own_index = read_json(own['index'])
    own_index['result'] = identity(folder/'evidence/generation-result.json')
    write_json(folder/'evidence/reference-gate.json',dict(analysis=own_index['reference']))
    config_ref = identity(resource_config.config_file)
    if foreign == 'source_index':
        write_json(folder/'source-index.json',read_json(other['index']))
    else:
        write_json(folder/'source-index.json',own_index)
    if foreign in ('import_index','import_config'):
        write_json(folder/'import-request.json',dict(source_index=identity(other['index']) if foreign=='import_index'
            else identity(folder/'source-index.json'),config=identity(other['result']) if foreign=='import_config' else config_ref))
    if foreign == 'completion':
        write_json(folder/'preparation-v2-complete-fixture.json',dict(source_index=identity(other['index'])))
    monkeypatch.setattr(module,'_case',lambda *a:(dict(config=config_ref),dict(case_id='own'),folder))
    monkeypatch.setattr(module,'_verified_result',lambda *a:own_result)
    calls=[]
    monkeypatch.setattr(module,'prepare_case',lambda *a:calls.append(a) or dict(status='research_input_ready'))
    with pytest.raises(ValueError,match='binding|differs'):
        module.prepare_native_source_v2(tmp_path,'own')
    assert calls == []
