"""Lossless bounded comparison serialization, without any visual acceptance claim."""
import json
from pathlib import Path
import pytest


def test_large_comparison_roundtrips_without_dropping_points(runtime_run):
    from video_ai.media.research_pair_report import write_comparison, read_comparison
    from video_ai.runtime.research_material_records import ResearchReader
    run, _, _ = runtime_run
    folder = run / 'logs/research-pairs'
    folder.mkdir(parents=True)
    # Greater than the legacy single-JSON output cap; exact payload must survive.
    value = dict(comparison_id='large', kind='reference', left='reference', right='frame_0',
                 regions=[dict(region_id='subject', diagnostic='x' * (17 * 1024 ** 2))])
    row = write_comparison(folder, 0, value, producer=str(run), input_sha256='0'*64)
    assert len(row['parts']) > 1
    assert all(part['bytes'] <= 16 * 1024 ** 2 for part in row['parts'])
    assert read_comparison(row, folder=folder, reader=ResearchReader(), producer=str(run), input_sha256='0'*64) == value


def test_missing_or_foreign_comparison_part_refused(runtime_run):
    from video_ai.media.research_pair_report import write_comparison, read_comparison
    from video_ai.runtime.research_material_records import ResearchReader
    run, _, _ = runtime_run
    folder = run / 'logs/research-pairs'
    folder.mkdir(parents=True)
    value = dict(comparison_id='pair', kind='reference', left='reference', right='frame', regions=[])
    row = write_comparison(folder, 0, value, producer=str(run), input_sha256='0'*64)
    Path(row['parts'][0]['path']).unlink()
    with pytest.raises((OSError, ValueError)):
        read_comparison(row, folder=folder, reader=ResearchReader(), producer=str(run), input_sha256='0'*64)


def test_same_id_shard_from_another_producer_refused(runtime_run):
    from video_ai.media.research_pair_report import write_comparison, read_comparison
    from video_ai.runtime.research_material_records import ResearchReader
    run, _, _ = runtime_run
    folder = run/'logs/research-pairs'
    value = dict(comparison_id='same_id', kind='reference', left='reference', right='frame', regions=[])
    row = write_comparison(folder, 0, value, producer='foreign-audit', input_sha256='a'*64)
    with pytest.raises(ValueError, match='producer'):
        read_comparison(row, folder=folder, reader=ResearchReader(), producer='expected-audit', input_sha256='a'*64)


def test_reduced_comparison_region_schema_refused(runtime_run):
    from video_ai.media.research_pair_report import validate_comparison
    from video_ai.runtime.research_material_records import ResearchReader
    value = dict(comparison_id='pair', kind='reference', left='reference', right='frame',
                 regions=[dict(region_id='subject', comparability='comparable')])
    declared = dict(comparison_id='pair', kind='reference', left='reference', right='frame', region_ids=['subject'])
    with pytest.raises(ValueError):
        validate_comparison(value, declared=declared, records={}, reader=ResearchReader())


def test_comparable_region_cannot_claim_zero_sample_support(runtime_run):
    from video_ai.media.research_pair_report import validate_comparison
    from video_ai.media._continuity_geometry import empty_region
    from video_ai.runtime.research_material_records import ResearchReader
    from scene_continuity_helpers import save, artifact
    run, _, _ = runtime_run
    records = {side: artifact(save(run/(side+'.json'), {'fixture_only':True})) for side in ('reference','frame')}
    region = empty_region('subject', 'insufficient_support', 'not_comparable')
    metrics = {k: 0. for k in ('delta_e_median delta_e_p90 left_luma_median right_luma_median '
        'luma_log_ratio left_chroma_median right_chroma_median chroma_delta sampled_clipped_delta').split()}
    metrics.update(delta_lab_median=[0.,0.,0.], left_clipped_fractions=[0.,0.,0.], right_clipped_fractions=[0.,0.,0.])
    region.update(comparability='comparable', reasons=[], metrics=metrics)
    region['evidence'] = [records['reference'], records['frame']]
    value = dict(comparison_id='pair', kind='reference', left='reference', right='frame', regions=[region])
    declared = dict(comparison_id='pair', kind='reference', left='reference', right='frame', region_ids=['subject'])
    with pytest.raises(ValueError, match='support'):
        validate_comparison(value, declared=declared, records=records, reader=ResearchReader())


@pytest.mark.parametrize('packed',[False,True])
def test_research_window_reads_inherited_json_and_geometry(runtime_run,packed):
    from time import monotonic
    from video_ai.media.research_pair_report import _ResearchWindow
    from video_ai.media._continuity_storage import encode_document
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.manifest import hash_file,thaw
    run,_,paths=runtime_run
    value=dict(schema_version=1,algorithm='continuity_cv_v1',comparison=dict(regions=[dict(
        geometry=dict(vectors=[[1.0,-0.0]],sampled_pairs=[[[1,2],[3,4]]]))]))
    path=run/'input.json'
    path.write_text(json.dumps(encode_document(value,packed=packed)),encoding='utf-8')
    record=thaw(hash_file(path))
    window=_ResearchWindow(paths,RunLogger(create_run(paths)),monotonic()+300,dict(fixture_only=True))
    assert window.read_json(record)==value
    assert str(path) in window.frozen
    window.verify()
