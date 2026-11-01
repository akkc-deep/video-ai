"""Conditional operator calibration must not turn oracle controls into safety."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest


def module():
    path=Path(__file__).resolve().parents[2]/'scripts/experiments/vco06_repair_calibration.py'
    assert path.exists(),'offline repair calibrator missing'
    spec=importlib.util.spec_from_file_location('repair_calibration',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def context(**changes):
    return dict(comparable=True,intentional_lighting_change=False,confirmed_motion_defect=False,**changes)


def test_color_reader_identity_metadata_is_normalized_without_hiding_drift(tmp_path):
    m=module();path=tmp_path/'pixels.rgb';path.write_bytes(b'original')
    reader_stamp=dict(m.identity(path),verified_at='2026-10-27T19:00:00+08:00')
    stamp=m.reader_identity(reader_stamp)
    assert set(stamp)=={'path','bytes','sha256','mtime_ns'}
    m.verify_identity(stamp)
    path.write_bytes(b'changed!')
    with pytest.raises(ValueError,match='identity changed'):m.verify_identity(stamp)


@pytest.mark.parametrize('operation',['exposure','wb_r','wb_g','wb_b','chroma'])
def test_known_nonclipped_control_is_reconstructed_without_recipe(operation):
    m=module();reference=np.random.default_rng(6).integers(80,160,(6,256,3),dtype=np.uint8)
    current=m.transform(reference,operation,.125)
    fit=m.estimate(reference,current,operation,context())
    assert fit['status']=='estimated'
    assert fit['amplitude']==pytest.approx(-.125,abs=.004)
    repaired=m.transform(current,operation,fit['amplitude'])
    result=m.score(reference,current,repaired)
    assert result['passed']
    assert result['after_mae'] < result['before_mae']
    assert result['max_error'] <= 4


def test_identity_does_not_propose_a_repair():
    m=module();x=np.full((2,100,3),100,np.uint8)
    assert m.estimate(x,x,'exposure',context())['status']=='noop'


@pytest.mark.parametrize('flag',['intentional_lighting_change','confirmed_motion_defect'])
def test_declared_content_change_blocks_repair(flag):
    m=module();x=np.full((100,3),100,np.uint8);ctx=context();ctx[flag]=True
    assert m.estimate(x,x//2,'exposure',ctx)['status']=='abstained'


def test_noncomparable_and_unknown_context_are_not_fitted():
    m=module();x=np.full((100,3),100,np.uint8);ctx=context();ctx['comparable']=False
    assert m.estimate(x,x//2,'exposure',ctx)['status']=='abstained'
    assert m.estimate(x,x//2,'exposure',None)['status']=='abstained'


def test_sparse_severe_damage_cannot_hide_below_p99():
    m=module();ref=np.full((1000,3),100,np.uint8);out=ref.copy();out[0]=150
    result=m.score(ref,out,out)
    assert result['p99_error']==0
    assert result['max_error']==50
    assert result['passed'] is False


def test_singular_chroma_abstains_and_invalid_pixels_raise():
    m=module();x=np.full((100,3),100,np.uint8)
    assert m.estimate(x,x//2,'chroma',context())['status']=='abstained'
    with pytest.raises(ValueError):m.transform(x.astype(float),'exposure',.1)
    with pytest.raises(ValueError):m.transform(x,'exposure',float('nan'))


def calibration_rows(m):
    genres=['people','animals','transport','outdoor','indoor','animation']
    sources=[dict(source_id=f's{i}',scene_group=f'g{i}',genre=g,eligible=True,split='calibration') for i,g in enumerate(genres)]
    rows=[]
    for source in sources:
        for level in m.LEVELS:
            rows.append(dict(source_id=source['source_id'],split='calibration',operation='exposure',
                injection_direction=1,level=level,passed=True,estimated_amplitude=-level))
    return sources,rows


def test_all_sources_and_contiguous_prefix_define_bound():
    m=module();sources,rows=calibration_rows(m)
    next(r for r in rows if r['source_id']=='s5' and r['level']==.125)['passed']=False
    bound=next(b for b in m.fit_bounds(rows,sources) if b['operation']=='exposure' and b['injection_direction']==1)
    assert bound['max_injection_level']==.0625
    assert bound['correction_direction']==-1
    assert bound['correction_amplitude_ceiling']==.0625


def test_cannot_pick_six_successes_and_drop_a_seventh_failure():
    m=module();sources,rows=calibration_rows(m)
    sources.append(dict(source_id='extra',scene_group='extra',genre='people',eligible=True,split='calibration'))
    for level in m.LEVELS:
        rows.append(dict(source_id='extra',split='calibration',operation='exposure',injection_direction=1,
                         level=level,passed=False,estimated_amplitude=-level))
    b=next(b for b in m.fit_bounds(rows,sources) if b['operation']=='exposure' and b['injection_direction']==1)
    assert b['max_injection_level'] is None


def test_holdout_cannot_be_used_to_fit_and_missing_genre_is_insufficient():
    m=module();sources,rows=calibration_rows(m)
    rows[0]['split']='holdout'
    with pytest.raises(ValueError,match='calibration'):m.fit_bounds(rows,sources)
    rows[0]['split']='calibration';sources[-1]['eligible']=False
    assert all(b['max_injection_level'] is None for b in m.fit_bounds(rows,sources))


def test_check_uses_frozen_bounds_without_widening_them():
    m=module();sources,rows=calibration_rows(m);bounds=m.fit_bounds(rows,sources)
    frozen=next(b for b in bounds if b['operation']=='exposure' and b['injection_direction']==1)
    check_sources=[dict(s,split='holdout') for s in sources]
    check_rows=[dict(r,split='holdout') for r in rows]
    check_rows[0]['passed']=False
    result=m.evaluate(check_rows,check_sources,bounds)
    b=next(b for b in result if b['operation']=='exposure' and b['injection_direction']==1)
    assert b['qualified'] is False
    assert frozen['max_injection_level']==1


def test_phase_and_producer_identity_guard(tmp_path):
    import json
    m=module();entries=[]
    for genre in sorted(m.GENRES):
        for i in range(4):
            entries.append(dict(source=dict(source_id=f'{genre}_{i}',scene_group=f'{genre}_{i}',genre=genre),
                                split='calibration' if i<2 else 'holdout'))
    (tmp_path/'original').mkdir()
    index=tmp_path/'original/index.json';index.write_text(json.dumps(dict(sources=entries)),encoding='utf-8')
    root=tmp_path/'study';m.prepare(root,index_path=index)
    m.phase_guard(root,'calibration')
    with pytest.raises(ValueError,match='seal'):m.phase_guard(root,'holdout')
    with pytest.raises(ValueError):m.seal(root)
    index.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='identity|changed'):m.phase_guard(root,'calibration')


def test_holdout_missing_coverage_is_not_vacuously_qualified():
    m=module();sources,rows=calibration_rows(m);bounds=m.fit_bounds(rows,sources)
    assert all(r['qualified'] is False for r in m.evaluate([],[],bounds))


def test_project_experiment_root_is_accepted_but_source_tree_and_foreign_root_are_rejected(tmp_path):
    m=module()
    project=Path('D:/VideoSi/projects/video-ai/continuity-benchmark/new-calibration-placeholder')
    source=Path('D:/VideoSi/projects/video-ai/continuity-benchmark/old-experiment/inputs.json')
    assert m.validate_root(project,source)==project.resolve()
    with pytest.raises(ValueError):m.validate_root(source.parent/'child',source)
    with pytest.raises(ValueError):m.validate_root(Path('D:/code/py/video-ai/unsafe-output'),source)


def prepared_study(m,tmp_path):
    import json
    original=tmp_path/'original';original.mkdir()
    entries=[dict(source=dict(source_id=f'{g}_{i}',scene_group=f'{g}_{i}',genre=g),
                  split='calibration' if i<2 else 'holdout') for g in sorted(m.GENRES) for i in range(4)]
    index=original/'index.json';index.write_text(json.dumps(dict(sources=entries)),encoding='utf-8')
    root=tmp_path/'study';m.prepare(root,index_path=index)
    return root,entries


def test_complete_looking_rows_with_failed_source_closure_cannot_be_sealed(tmp_path):
    m=module();root,entries=prepared_study(m,tmp_path);e=entries[0]
    path=root/'source-results'/(e['source']['source_id']+'.json')
    m.write_json(path,dict(status='failed',closure_verified=False,source=dict(e['source'],split=e['split'],eligible=True),
                          rows=[dict(passed=True)],error='final source identity changed'))
    with pytest.raises(ValueError,match='closure'):m._collect(root,'calibration')


def test_frozen_input_copy_cannot_drift_before_or_after_seal(tmp_path):
    import json
    m=module();root,_=prepared_study(m,tmp_path);p=root/'inputs.FROZEN.json';old=p.read_bytes()
    v=json.loads(old);v['limitations'].append('changed')
    p.write_text(json.dumps(v),encoding='utf-8')
    with pytest.raises(ValueError,match='identity|changed'):m.phase_guard(root,'calibration')
    p.write_bytes(old)
    # Reset mtime in the independent identity to simulate an intact restored
    # input, then seal its exact identity and verify the post-seal binding too.
    (root/'inputs-identity.json').write_text(json.dumps(m.identity(p)),encoding='utf-8')
    seal=root/'thresholds.SEALED.json';m.write_json(seal,dict(inputs=m.identity(p)))
    m.write_json(root/'threshold-seal-identity.json',m.identity(seal))
    p.write_text(json.dumps(v),encoding='utf-8')
    (root/'inputs-identity.json').write_text(json.dumps(m.identity(p)),encoding='utf-8')
    with pytest.raises(ValueError,match='identity|changed'):m.phase_guard(root,'holdout')


def test_opposite_correction_direction_is_never_within_sealed_domain():
    m=module();sources,rows=calibration_rows(m)
    next(r for r in rows if r['level']==m.LEVELS[0])['estimated_amplitude']=m.LEVELS[0]
    b=next(b for b in m.fit_bounds(rows,sources) if b['operation']=='exposure' and b['injection_direction']==1)
    assert b['max_injection_level'] is None
    sources,rows=calibration_rows(m);bounds=m.fit_bounds(rows,sources)
    check=[dict(r,split='holdout') for r in rows];check[0]['estimated_amplitude']=.001
    result=m.evaluate(check,[dict(s,split='holdout') for s in sources],bounds)
    b=next(b for b in result if b['operation']=='exposure' and b['injection_direction']==1)
    assert b['cases'][0]['within_fitted_parameter_domain'] is False
    assert b['qualified'] is False


def test_native_pixel_and_pack_budget_is_checked_before_allocation():
    m=module()
    assert m.pixel_budget(240,3840,2160)<128*1024*1024
    with pytest.raises(ValueError,match='resource_limit'):m.pixel_budget(4096,3840,2160)
    with pytest.raises(ValueError,match='resource_limit'):m.pixel_budget(120,20000,20000)
