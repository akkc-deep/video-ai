"""Independent certificate guards: corruption must fail closed."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import pytest


def module():
    path=Path(__file__).resolve().parents[2]/'scripts/experiments/vco03_replay_evidence.py'
    assert path.exists(),'independent replay evidence verifier missing'
    spec=importlib.util.spec_from_file_location('cert',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def fixture():
    ref=dict(path='D:/data/control.json',bytes=3,mtime_ns=1,sha256='a'*64)
    pack=dict(path='D:/data/pack.json',bytes=3,mtime_ns=1,sha256='b'*64)
    seal=dict(path='D:/data/seal.json',bytes=3,mtime_ns=1,sha256='c'*64)
    entry=dict(source_id='dog',split='new_check',genre='animals',scene_group='dog',source_kind='captured')
    source=dict(entry=entry,controls=[ref],pack=pack)
    control=dict(source_id='dog',split='new_check',variant='replay_exact')
    label=dict(source_id='dog',variant='replay_exact',final_label='anomaly')
    row=dict(case_id='dog__replay_exact',source_id='dog',variant='replay_exact',genre='animals',group='dog',source_kind='captured',
        detector_id='temporal_replay',region_id='fixed_clip_start_ROI',label='anomaly',score=1.,state='comparable')
    case=dict(case_id=row['case_id'],source_id='dog',variant='replay_exact',split='new_check',input_sha256='d'*64,threshold_seal=seal,
        measurement_completed=True,measurement_started_at='2026-10-26T00:02:00+00:00',measurement_finished_at='2026-10-26T00:03:00+00:00',
        control=ref,pack=pack,row=row,result=dict(score=1.,state='comparable',reason='measured'),production_eligible=False)
    receipt=dict(input_sha256='d'*64,threshold_seal=seal,output=dict(path='D:/data/case.json'),provider_closed=True,environment_fingerprint='env',source_closure_digest='closure')
    return dict(case=case,receipt=receipt,source=source,control=control,control_ref=ref,label=label,
        expected_path='D:/data/case.json',input_sha256='d'*64,seal=seal,seal_time='2026-10-26T00:01:00+00:00',
        closure_digest='closure',environment_fingerprint='env')


def test_original_case_certificate_is_accepted():
    assert module().verify_case_binding(**fixture()) is True


@pytest.mark.parametrize('field',['case_path','input','label','score','state','control','pack','split','early','seal','environment','closure','production','infinite'])
def test_cross_run_substitution_and_tampering_are_rejected(field):
    verifier=module().verify_case_binding
    data=deepcopy(fixture());c=data['case'];r=data['receipt']
    if field=='case_path':r['output']['path']='D:/other/case.json'
    if field=='input':r['input_sha256']='f'*64
    if field=='label':c['row']['label']='normal'
    if field=='score':c['row']['score']=.1
    if field=='state':c['row']['state']='unverified'
    if field=='control':c['control']['sha256']='f'*64;data['control_ref']=deepcopy(fixture()['control_ref'])
    if field=='pack':c['pack']=dict(path='D:/other/pack.json')
    if field=='split':c['split']='calibration'
    if field=='early':c['measurement_started_at']='2026-10-26T00:00:00+00:00'
    if field=='seal':r['threshold_seal']=None
    if field=='environment':r['environment_fingerprint']='different'
    if field=='closure':r['source_closure_digest']='different'
    if field=='production':c['production_eligible']=True
    if field=='infinite':c['row']['score']=float('inf');c['result']['score']=float('inf')
    with pytest.raises((ValueError,AssertionError)):
        verifier(**data)


def test_coverage_denominator_separates_excluded_labels_and_abstentions():
    verifier=module()
    rows=[dict(source_id='a',label='anomaly',score=.9,state='comparable'),
          dict(source_id='a',label='normal',score=None,state='unverified'),
          dict(source_id='b',label='normal',score=.1,state='comparable'),
          dict(source_id='b',label='unverified',score=.8,state='comparable')]
    r=verifier.describe_rows(rows,.5)
    assert r['total_cases']==4 and r['labeled_cases']==3 and r['excluded_label_unverified']==1
    assert r['classified_labeled_cases']==2 and r['labeled_abstentions']==1
    assert r['labeled_coverage']==pytest.approx(2/3)
    assert r['all_case_measurement_coverage']==pytest.approx(3/4)
    assert r['positive_original_works']==1 and r['all_positive_variants_detected_works']==1
    assert r['interval_interpretation']=='Nominal row intervals are correlated; do not infer source generalization from variant count.'
