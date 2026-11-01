"""A repair profile is authority only with its original sealed byte closure."""
import importlib
import importlib.util
import os
from pathlib import Path

import pytest

from video_ai.runtime._scene_continuity_io import Reader


REAL = Path('D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2')


def module():
    name = 'video_ai.runtime._scene_color_repair_profile'
    assert importlib.util.find_spec(name), 'sealed repair profile loader missing'
    return importlib.import_module(name)


from repair_profile_helpers import identity, save, load, make_profile as study

def rewrite_profile(path, edit):
    value = load(path); edit(value); save(path, value)


@pytest.mark.parametrize('green_axis',[False,True])
def test_complete_sealed_profile_returns_plain_value_and_sorted_unique_closure(tmp_path,green_axis):
    path = study(tmp_path,green_axis=green_axis); before = {str(p):identity(p) for p in tmp_path.rglob('*') if p.is_file()}
    reader = Reader(); result, closure = module().verified_profile(path, reader=reader)
    assert result == load(path)
    assert closure == sorted(closure, key=lambda a:a['path'])
    assert len({a['path'] for a in closure}) == len(closure)
    assert all(set(a) == {'path','bytes','sha256'} for a in closure)
    assert str(path.parent/'source-packs/calibration_people_0.npz') in {a['path'] for a in closure}
    assert reader.bytes < 64*1024*1024
    assert before == {str(p):identity(p) for p in tmp_path.rglob('*') if p.is_file()}


def test_original_optional_control_authorization_stays_in_closure(tmp_path):
    path=study(tmp_path,control_targets=True)
    profile,refs=module().verified_profile(path,reader=Reader())
    assert profile['evidence_only'] is True
    assert str(tmp_path/'original/calibration_people_0.truth') in {r['path'] for r in refs}


def test_bulk_result_rows_are_hashed_without_consuming_metadata_budget(tmp_path):
    path=study(tmp_path,row_payload_bytes=3*1024*1024);reader=Reader()
    profile,refs=module().verified_profile(path,reader=reader)
    assert sum(r['bytes'] for r in refs if '/source-results/' in r['path'].replace('\\','/')) > 64*1024*1024
    assert reader.bytes < 2*1024*1024
    assert profile['production_eligible'] is False


def test_holdout_cannot_start_before_calibration_seal(tmp_path):
    path=study(tmp_path,holdout_finished_at='2026-10-26T00:01:30+00:00')
    with pytest.raises(ValueError,match='stage order'):
        module().verified_profile(path,reader=Reader())


@pytest.mark.parametrize('key,bad', [('schema_version',True),('production_eligible',True),('evidence_only',False),
    ('purpose','continuity_cv_v1'),('created_at','2999-01-01T00:00:00+00:00'),('created_at','2026-10-26T00:04:00'),('extra',1)])
def test_profile_strict_schema_and_time_refuse(tmp_path,key,bad):
    path = study(tmp_path); rewrite_profile(path,lambda p:p.__setitem__(key,bad))
    with pytest.raises(ValueError): module().load_profile(path,reader=Reader())


def test_fake_qualified_direction_cannot_bypass_holdout_checks(tmp_path):
    path=study(tmp_path)
    rewrite_profile(path,lambda p:p['qualified_directions'].append(dict(operation='wb_b',injection_direction=1)))
    with pytest.raises(ValueError): module().load_profile(path,reader=Reader())


@pytest.mark.parametrize('relative', ['inputs.FROZEN.json','thresholds.SEALED.json',
    'source-results/calibration_people_0.json','source-packs/holdout_people_0.npz','software/calibrator.py'])
def test_same_size_same_mtime_byte_drift_is_refused(tmp_path,relative):
    path=study(tmp_path); changed=path.parent/relative; st=changed.stat(); raw=changed.read_bytes()
    changed.write_bytes(bytes([raw[0]^1])+raw[1:]); os.utime(changed,ns=(st.st_atime_ns,st.st_mtime_ns))
    with pytest.raises(ValueError): module().load_profile(path,reader=Reader())


def test_original_source_bytes_are_in_profile_closure(tmp_path):
    path=study(tmp_path); changed=tmp_path/'original/holdout_people_0.media';changed.write_bytes(b'changed original')
    with pytest.raises(ValueError): module().load_profile(path,reader=Reader())


@pytest.mark.parametrize('mutation', ['version','software','index','protocol'])
def test_rebound_inputs_still_require_versions_inventory_original_index_and_protocol(tmp_path,mutation):
    path=study(tmp_path); inputs_path=path.parent/'inputs.FROZEN.json'; data=load(inputs_path)
    if mutation=='version': data['versions']['numpy']='0.0.0'
    if mutation=='software': data['software']=data['software'][:-1]
    if mutation=='index': data['sources'][0]['source']['rights_note']='changed source declaration'
    if mutation=='protocol':
        proto=load(path.parent/'protocol.FROZEN.json');proto['minimum_pairs']=1
        data['protocol']=save(path.parent/'protocol.FROZEN.json',proto)
    new=save(inputs_path,data);save(path.parent/'inputs-identity.json',new)
    # Rebinding every downstream pointer must not turn invalid inputs into authority.
    sealed=load(path.parent/'thresholds.SEALED.json');sealed['inputs']=new
    sealref=save(path.parent/'thresholds.SEALED.json',sealed);save(path.parent/'threshold-seal-identity.json',sealref)
    evaluation=load(path.parent/'evaluation.json');evaluation['inputs']=new;evaluation['thresholds']=sealref
    evaluation_ref=save(path.parent/'evaluation.json',evaluation)
    p=load(path);p.update(evaluation,evaluation=evaluation_ref);save(path,p)
    with pytest.raises(ValueError): module().load_profile(path,reader=Reader())


def test_source_pack_metadata_must_equal_independently_bound_result(tmp_path):
    path=study(tmp_path); meta=path.parent/'source-packs/calibration_people_0.json';value=load(meta);value['eligible']=False;save(meta,value)
    with pytest.raises(ValueError): module().load_profile(path,reader=Reader())


def test_independent_result_identity_cannot_be_replaced_by_seal_reference(tmp_path):
    path=study(tmp_path); side=path.parent/'source-results/holdout_people_0.identity.json'; value=load(side);value['sha256']='0'*64;save(side,value)
    with pytest.raises(ValueError): module().load_profile(path,reader=Reader())


def test_deadline_is_checked_before_reading(tmp_path):
    path=study(tmp_path); reader=Reader();reader.deadline=0
    with pytest.raises(TimeoutError): module().load_profile(path,reader=reader)


def test_closeout_rehashes_dependencies_after_same_size_restored_mtime_change(tmp_path):
    target=tmp_path/'fixture_only-post-hash-drift.bin';target.write_bytes(b'original')
    evidence=module()._Evidence(Reader());evidence.verify(identity(target));stamp=target.stat()
    target.write_bytes(b'changed!');os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises(ValueError,match='changed'):
        evidence.finish()


def test_duplicate_identity_cannot_rebind_mtime_during_validation(tmp_path):
    target=tmp_path/'fixture_only-mtime.bin';target.write_bytes(b'original')
    evidence=module()._Evidence(Reader());evidence.verify(identity(target));stamp=target.stat()
    os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1000000))
    with pytest.raises(ValueError,match='changed|conflicting'):
        evidence.verify(identity(target))


def test_widened_declaration_is_rejected_with_all_measurement_bytes_unchanged(tmp_path):
    path=study(tmp_path);root=path.parent
    before={str(p):identity(p) for p in (root/'source-results').glob('*')}
    sealed=load(root/'thresholds.SEALED.json')
    next(b for b in sealed['bounds'] if b['operation']=='exposure' and b['injection_direction']==1)['correction_amplitude_ceiling']=8.
    seal_ref=save(root/'thresholds.SEALED.json',sealed);save(root/'threshold-seal-identity.json',seal_ref)
    evaluation=load(root/'evaluation.json');evaluation['thresholds']=seal_ref
    evaluation_ref=save(root/'evaluation.json',evaluation)
    p=load(path);p.update(evaluation,evaluation=evaluation_ref,calibrated_bounds=sealed['bounds']);save(path,p)
    assert before=={str(p):identity(p) for p in (root/'source-results').glob('*')}
    with pytest.raises(ValueError):
        module().verified_profile(path,reader=Reader())


def test_no_eligible_calibration_cannot_authorize_holdout_direction(tmp_path):
    path=study(tmp_path);root=path.parent;p=load(path);sealed=load(root/'thresholds.SEALED.json')
    sources=sealed['sources']+[dict(source_id=e['source']['source_id'],scene_group=e['source']['scene_group'],
        genre=e['source']['genre'],split='holdout',eligible=True) for e in load(root/'inputs.FROZEN.json')['sources'] if e['split']=='holdout']
    for source in sources:
        if source['split']=='calibration':source['eligible']=False
    for bound in sealed['bounds']:
        bound.update(eligible_sources=[],coverage_sufficient=False)
    with pytest.raises(ValueError):
        module()._directions(sealed['bounds'],p['checks'],sources)


def test_rebound_holdout_pass_flags_cannot_override_unchanged_saved_results(tmp_path):
    path=study(tmp_path);root=path.parent;evaluation=load(root/'evaluation.json')
    check=next(c for c in evaluation['checks'] if c['operation']=='wb_b' and c['injection_direction']==1)
    check['qualified']=True
    for case in check['cases']:case['passed']=True
    evaluation['qualified_directions'].append(dict(operation='wb_b',injection_direction=1))
    evaluation_ref=save(root/'evaluation.json',evaluation)
    p=load(path);p.update(evaluation,evaluation=evaluation_ref);save(path,p)
    with pytest.raises(ValueError,match='saved holdout'):
        module().verified_profile(path,reader=Reader())
