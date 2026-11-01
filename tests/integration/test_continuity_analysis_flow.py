"""Small real CPU evidence; fixture_only and no video quality approval."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import os
import importlib.util

import pytest
from continuity_helpers import texture


def snapshot(root):
    from video_ai.runtime.manifest import hash_file
    return {str(p):(p.stat().st_size,p.stat().st_mtime_ns,hash_file(p).sha256) for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def continuity_fixture(runtime_run):
    return _make_continuity_fixture(runtime_run)


def _make_continuity_fixture(runtime_run,variation=0,variable_time=False):
    from video_ai.config import load_config
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.manifest import hash_file,thaw,now
    from video_ai.media.colorimetry import inspect_color_asset,decode_analysis_frame
    from video_ai.media._continuity_audit import png_bytes
    run,config,paths=runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config=replace(config,tools=dict(config.tools,ffmpeg=actual.tools['ffmpeg'],ffprobe=actual.tools['ffprobe']))
    source_logger=RunLogger(run);audit_logger=RunLogger(create_run(paths))
    rgb=texture(64,36)+variation;source=run/'input.rgb';source.write_bytes(rgb.tobytes()*8);video=run/'input.mp4'
    cmd=run_logged([str(config.tools['ffmpeg']),'-nostdin','-n','-v','error','-threads','1','-f','rawvideo',
        '-pixel_format','rgb24','-video_size','64x36','-framerate','2','-i',str(source),'-frames:v','8','-an',
        *(['-vf','settb=1/8,setpts=N*4+floor(N/2)','-fps_mode','passthrough','-enc_time_base','1/8','-video_track_timescale','8'] if variable_time else []),
        '-c:v','libx264','-crf','0','-pix_fmt','yuv444p','-colorspace','bt709','-color_primaries','bt709',
        '-color_trc','iec61966-2-1','-color_range','tv','-x264-params',
        'colorprim=bt709:transfer=iec61966-2-1:colormatrix=bt709',str(video)],cwd=run,env=build_child_env(paths),
        timeout=60,logger=source_logger,stage='continuity_fixture')
    assert cmd.returncode==0 and not cmd.timed_out
    rows=[dict(asset_frame_index=i,clip_id='clip_a',generated_frame_index=i,retained_frame_index=i,
               output_frame_index=i,pts=(i*4+i//2 if variable_time else i*8192),time_base=('1/8' if variable_time else '1/16384')) for i in range(8)]
    mapping=run/'mapping.json';mapping.write_text(json.dumps(dict(source=thaw(hash_file(video)),rows=rows)),encoding='utf-8')
    kw=dict(config=config,paths=paths,logger=audit_logger)
    entry=dict(asset_id='video',stage='generated',path=str(video),mapping=dict(rows=rows,evidence=[thaw(hash_file(mapping))]),
               processing=dict(operation='real CPU fixture',upstream_ids=[],command_records=[]))
    side,_=inspect_color_asset(entry,**kw);records=[]
    for i in range(8):
        decode_analysis_frame(side,frame_index=i,**kw)
        records.append(thaw(hash_file(audit_logger.root/f'colorimetry/video/analysis/frame_{i:06d}.json')))
    png=run/'reference.png';png.write_bytes(png_bytes(rgb))
    pngrow=dict(rows[0]);pngrow['asset_frame_index']=0
    pm=run/'png-mapping.json';pm.write_text(json.dumps(dict(source=thaw(hash_file(png)),rows=[pngrow])),encoding='utf-8')
    ps,_=inspect_color_asset(dict(entry,asset_id='reference',stage='native_tail',path=str(png),mapping=dict(rows=[pngrow],evidence=[thaw(hash_file(pm))])),**kw)
    decode_analysis_frame(ps,frame_index=0,**kw)
    ref=thaw(hash_file(audit_logger.root/'colorimetry/reference/analysis/frame_000000.json'))
    regions=run/'regions.json';regions.write_text(json.dumps(dict(schema_version=1,author='fixture',reviewed_at=now(),regions=[
        dict(region_id='subject',role='subject',identity_note='synthetic fixture',anchors=[dict(frame=records[0],rect=[0,0,1,1]),dict(frame=ref,rect=[0,0,1,1])]),
        dict(region_id='background',role='background',identity_note='synthetic background',anchors=[dict(frame=records[0],rect=[0,0,1,1]),dict(frame=ref,rect=[0,0,1,1])])])),encoding='utf-8')
    comparisons=[dict(comparison_id=f'pair_{i}',kind='adjacent',left=f'frame_{i}',right=f'frame_{i+1}',region_ids=['subject','background']) for i in range(7)]
    comparisons.append(dict(comparison_id='same',kind='same_frame',left='frame_0',right='frame_0',region_ids=['subject']))
    comparisons.append(dict(comparison_id='reference',kind='reference',left='reference_origin',right='frame_7',region_ids=['subject']))
    manifest=dict(schema_version=1,algorithm='continuity_cv_v1',scope='clip',scene_id='fixture_scene',domain=dict(genre='animation',source_kind='animation'),
        timeline=dict(fps_num=2,fps_den=1),clips=[dict(clip_id='clip_a',frames=[dict(frame_id=f'frame_{i}',record=r) for i,r in enumerate(records)])],
        references=[dict(frame_id='reference_origin',record=ref)],regions=thaw(hash_file(regions)),comparisons=comparisons,context=None,profile=None)
    return run,kw,manifest,records,side


def test_real_readonly_evidence_to_independent_report(continuity_fixture):
    from video_ai.media.continuity_analysis import analyze_continuity
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    run,kw,manifest,records,side=continuity_fixture
    originals={str(run):snapshot(run),str(kw['logger'].run_dir):snapshot(kw['logger'].run_dir)}
    logger=RunLogger(create_run(kw['paths']))
    report,outputs=analyze_continuity(manifest,**dict(kw,logger=logger))
    assert set(report)==set('schema_version algorithm parameters parameters_sha256 input_sha256 inputs dependencies scope scene_id domain coverage frame_results comparisons trajectories detectors profile risks created_at'.split())
    assert (logger.root/'continuity/report.json').is_file()
    assert report['coverage']['requested_frames']==9
    same=next(p for p in report['comparisons'] if p['comparison_id']=='same')['regions'][0]
    assert same['comparability']=='comparable' and same['geometry']['basis']=='same_source_mapping'
    assert same['metrics']['delta_e_p90']==0. and same['confidence']==1.
    assert report['profile'] is None and all(d['status']!='candidate' for d in report['detectors'])
    assert report['frame_results'][1]['pts']==8192
    assert report['frame_results'][1]['timeline_seconds']==.5
    assert all(p.is_relative_to(logger.run_dir) for p in outputs)
    for path,before in originals.items():assert snapshot(Path(path))==before
    with pytest.raises((ValueError,FileExistsError)):analyze_continuity(manifest,**dict(kw,logger=logger))


def test_readonly_batch_hashes_unique_media_once_per_boundary(continuity_fixture,monkeypatch):
    import video_ai.media.colorimetry as c
    run,kw,manifest,records,side=continuity_fixture
    counts={};original=c.hash_file
    def count(path):
        key=str(path);counts[key]=counts.get(key,0)+1;return original(path)
    monkeypatch.setattr(c,'hash_file',count)
    with c.load_color_analysis_set([r['path'] for r in records],config=kw['config']) as reader:
        assert len(reader.frames)==8 and len(reader.sidecars)==1
        for record in records:assert len(reader.read_rgb(record['path']))==64*36*3
    for p in (side['source']['path'],side['tools']['ffmpeg']['identity']['path'],side['tools']['ffprobe']['identity']['path']):assert counts[p]==2


def test_cli_rejects_relative_inputs_without_creating_a_run():
    spec=importlib.util.spec_from_file_location('continuity_audit',Path(__file__).parents[2]/'scripts/continuity_audit.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    assert cli.main(['analyze','--config','relative.json','--manifest','relative.json'])==2


def _control_source(fixture):
    from video_ai.runtime.manifest import hash_file,thaw,now
    run,kw,manifest,records,side=fixture
    regions=run/'control-regions.json';truth_path=run/'truth.json'
    regions.write_text(json.dumps(dict(schema_version=1,author='fixture_only',reviewed_at=now(),regions=[
        dict(region_id='subject',role='subject',identity_note='fixture subject',anchors=[dict(frame=records[0],rect=[0,0,1,1])]),
        dict(region_id='background',role='background',identity_note='fixture background',anchors=[dict(frame=records[0],rect=[0,0,1,1])])])),encoding='utf-8')
    truth=dict(schema_version=1,author='fixture_only',reviewed_at=now(),samples=[dict(frame=r,regions=[
        dict(region_id=rid,box=[0,0,1,1],visibility='visible',mask=None) for rid in ('subject','background')]) for r in records])
    truth_path.write_text(json.dumps(truth),encoding='utf-8')
    source=dict(source_id='source_a',genre='animation',source_kind='animation',scene_group='group_a',media=side['source'],frame_records=records,
        interval=dict(start_pts=side['probe']['video']['frames'][0]['pts'],
                      end_pts=side['probe']['video']['frames'][-1]['pts']+side['probe']['video']['frames'][-1]['duration'],
                      time_base=side['probe']['video']['time_base']),rights_note='generated CPU fixture only',regions=thaw(hash_file(regions)),truth=thaw(hash_file(truth_path)),context=None)
    return source,truth


def test_all_controls_keep_source_pts_and_hide_future_truth_from_measurement(continuity_fixture,monkeypatch):
    from video_ai.media.continuity_calibration import build_control_case,VARIANTS
    from video_ai.media.colorimetry import load_color_analysis_set
    from video_ai.media.continuity_analysis import measure_continuity
    fixture=continuity_fixture;source,truth=_control_source(fixture);kw=fixture[1]
    before=snapshot(fixture[0]);original_read=Path.read_text
    with load_color_analysis_set([r['path'] for r in source['frame_records']],config=kw['config']) as reader:
        for variant in VARIANTS:
            control,provider=build_control_case(source,variant,reader=reader,truth=truth)
            assert len(control['display_map'])==8 and len(provider.plan['frames'])==9
            if variant=='motion_reset':
                f=provider.plan['frames'][4]
                assert f['source_pts']==0 and f['display_pts']==32768
                assert provider.get('display_4')['rgb24']==reader.read_rgb(source['frame_records'][0]['path'])
            def no_truth(path,*args,**kwargs):
                if str(path)==source['truth']['path']:raise AssertionError('future truth file opened by measurement')
                return original_read(path,*args,**kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(Path,'read_text',no_truth)
                result=measure_continuity(provider.plan,provider)
            assert result['coverage']['requested_frames']==9
    assert snapshot(fixture[0])==before


def test_fixture_calibration_seals_thresholds_before_holdout_and_stays_unverified(continuity_fixture,monkeypatch):
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import hash_file,thaw,now
    from video_ai.planning.production_scenes import canonical_digest
    import video_ai.media.continuity_calibration as c
    import video_ai.media.continuity_analysis as a
    from video_ai.media._continuity_schema import stable,DETECTORS
    fixture=continuity_fixture;run,kw,_,_,_=fixture
    second=_make_continuity_fixture((create_run(kw['paths']),kw['config'],kw['paths']),variation=1,variable_time=True)
    first_source,_=_two_subject_source(fixture);second_source,_=_control_source(second)
    second_source.update(source_id='source_b',scene_group='group_b')
    catalog=dict(schema_version=1,corpus_id='fixture_only_corpus',corpus_kind='fixture_only',sources=[first_source,second_source],
        split=dict(calibration_groups=['group_a'],holdout_groups=['group_b']),created_at=now())
    evidence=run/'fixture-labels-evidence.txt';evidence.write_text('Synthetic labels for software checks only. No human playback assertion.',encoding='utf-8')
    labels=c.build_annotation_template(catalog);labels['annotators']=['fixture_a','fixture_b'];labels['adjudicator']='fixture_adjudicator'
    for source in catalog['sources']:
        for variant in c.VARIANTS:
            for rid in ([r['region_id'] for r in json.loads(Path(source['regions']['path']).read_text())['regions']]):
                for d in DETECTORS:
                    labels['entries'].append(dict(case_id=source['source_id']+'_'+variant,region_id=rid,frame_interval=[0,8],detector_id=d,
                        labels=[dict(author=author,label='normal',viewed_interval=[0,8],viewed_at=now()) for author in labels['annotators']],
                        final_label='normal',rationale='fixture_only synthetic label',evidence=[thaw(hash_file(evidence))],adjudication=None))
    seen=[];original_measure=a.measure_continuity;original_fit=c._fit_threshold;fit_calls=[]
    def measure(plan,provider,**kwargs):
        seen.append(plan['frames'][0]['source_record']['path']);return original_measure(plan,provider,**kwargs)
    def fit(rows):
        assert not any(str(second[1]['logger'].run_dir) in p for p in seen),'holdout reached fitting'
        fit_calls.append(deepcopy(rows));return original_fit(rows)
    monkeypatch.setattr(a,'measure_continuity',measure);monkeypatch.setattr(c,'_fit_threshold',fit)
    logger=RunLogger(create_run(kw['paths']))
    profile,outputs=c.calibrate_continuity(catalog,labels,**dict(kw,logger=logger))
    assert len(fit_calls)==6 and len(seen)==20
    assert profile['purpose']=='fixture_only' and profile['status']=='unverified'
    assert all(not d['enabled'] and d['threshold'] is None for d in profile['detectors'])
    assert (logger.root/'continuity/calibration/thresholds.json').is_file()
    assert (logger.root/'continuity/calibration/evaluation.json').is_file()
    assert len(json.loads((logger.root/'continuity/calibration/case-results.json').read_text())['cases'])==20
    controls=logger.root/'continuity/calibration/controls'
    assert json.loads((controls/'source_a_occlusion.json').read_text())['recipe']['local_region_ids']==['hand']
    assert json.loads((controls/'source_a_local_color.json').read_text())['recipe']['local_region_ids']==['pen']
    variable_control=json.loads((controls/'source_b_unchanged.json').read_text())
    assert [d['display_pts'] for d in variable_control['display_map']]==[0,4,9,13,18,22,27,31]
    monkeypatch.setattr(c,'_fit_threshold',original_fit)
    from video_ai.media._continuity_audit import AuditWindow
    from time import monotonic
    consumer=AuditWindow(kw['paths'],RunLogger(create_run(kw['paths'])),monotonic()+300)
    profile_identity=thaw(hash_file(logger.root/'continuity/calibration/profile.json'))
    assert c._verify_profile_evidence(profile,profile_identity,consumer)==profile
    forged=deepcopy(profile);forged['detectors'][0]['threshold']=-1.
    with pytest.raises(ValueError,match='sealed'):c._verify_profile_evidence(forged,profile_identity,consumer)
    # Refreeze every edited artifact: rejection must come from original native
    # evidence, rather than a stale content hash or the control's own claims.
    root=logger.root/'continuity/calibration';rejected=[]
    for kind in ('display_time','region_roles'):
        folder=run/('refrozen-'+kind);folder.mkdir()
        results=json.loads((root/'case-results.json').read_text())
        row=next(r for r in results['cases'] if r['case_id']=='source_b_unchanged')
        control=json.loads(Path(row['control']['path']).read_text())
        if kind=='display_time':control['display_map'][1]['display_pts']=5 # observed rate set is unchanged
        else:
            next(r for r in control['anchors'] if r['region_id']=='background')['role']='subject'
            control['recipe']['local_region_ids'].append('background')
        altered=folder/'control.json';altered.write_text(json.dumps(control),encoding='utf-8');row['control']=thaw(hash_file(altered))
        casespath=folder/'case-results.json';casespath.write_text(json.dumps(results),encoding='utf-8')
        evaluation=json.loads((root/'evaluation.json').read_text());evaluation['case_results']=thaw(hash_file(casespath))
        (folder/'evaluation.json').write_text(json.dumps(evaluation),encoding='utf-8')
        copied=folder/'profile.json';copied.write_bytes((root/'profile.json').read_bytes())
        fresh=AuditWindow(kw['paths'],RunLogger(create_run(kw['paths'])),monotonic()+300)
        try:c._verify_profile_evidence(profile,thaw(hash_file(copied)),fresh)
        except ValueError as exc:
            assert 'native' in str(exc) or 'region' in str(exc)
            rejected.append(kind)
    assert rejected==['display_time','region_roles']


def _two_subject_source(fixture):
    from video_ai.runtime.manifest import hash_file,thaw
    source,truth=_control_source(fixture)
    boxes={'hand':[0.,0.,.5,.5],'pen':[.5,.5,1.,1.],'background':[0.,0.,1.,1.]}
    region_path=Path(source['regions']['path']);doc=json.loads(region_path.read_text())
    doc['regions']=[dict(region_id=rid,role='background' if rid=='background' else 'subject',identity_note='fixture only',
                         anchors=[dict(frame=source['frame_records'][0],rect=box)]) for rid,box in boxes.items()]
    region_path.write_text(json.dumps(doc),encoding='utf-8');source['regions']=thaw(hash_file(region_path))
    for row in truth['samples']:
        row['regions']=[dict(region_id=rid,box=box,visibility='visible',mask=None) for rid,box in boxes.items()]
    truthpath=Path(source['truth']['path']);truthpath.write_text(json.dumps(truth),encoding='utf-8');source['truth']=thaw(hash_file(truthpath))
    auth=fixture[0]/'target-permission.txt';auth.write_text('Fixture only: occlude hand, recolor pen. Not a human annotation.',encoding='utf-8')
    source['control_targets']={v:dict(region_ids=[rid],authorization=thaw(hash_file(auth))) for v,rid in [('occlusion','hand'),('local_color','pen')]}
    return source,truth


@pytest.mark.parametrize('variant',['occlusion','local_color'])
def test_explicit_local_targets_change_only_selected_subject(continuity_fixture,variant):
    import numpy as np
    from video_ai.media.colorimetry import load_color_analysis_set
    from video_ai.media.continuity_calibration import build_control_case
    source,truth=_two_subject_source(continuity_fixture)
    with load_color_analysis_set([r['path'] for r in source['frame_records']],config=continuity_fixture[1]['config']) as reader:
        case,provider=build_control_case(source,variant,reader=reader,truth=truth)
        before=np.frombuffer(reader.read_rgb(source['frame_records'][4]['path']),dtype=np.uint8).reshape(36,64,3)
        after=np.frombuffer(provider.get('display_4')['rgb24'],dtype=np.uint8).reshape(36,64,3)
        if variant=='occlusion':
            assert after[4,4].tolist()==[128,128,128]
            assert np.array_equal(after[18:,32:],before[18:,32:])
            assert case['context']['events'][-1]['region_ids']==['hand']
        else:
            assert np.array_equal(after[:18,:32],before[:18,:32])
            assert not np.array_equal(after[27,48],before[27,48])
        for invalid in (['background'],['missing']):
            bad=deepcopy(source);bad['control_targets'][variant]['region_ids']=invalid
            with pytest.raises(ValueError,match='subject|target'):build_control_case(bad,variant,reader=reader,truth=truth)


def test_control_captures_truth_masks_before_measurement(continuity_fixture,monkeypatch):
    import cv2
    import numpy as np
    from video_ai.runtime.manifest import thaw,hash_file
    from video_ai.media.colorimetry import load_color_analysis_set
    from video_ai.media.continuity_calibration import build_control_case
    from video_ai.media.continuity_analysis import measure_continuity
    source,truth=_control_source(continuity_fixture);path=continuity_fixture[0]/'truth-mask.png'
    ok,png=cv2.imencode('.png',np.ones((36,64),dtype=np.uint8)*255);assert ok;path.write_bytes(png.tobytes())
    for sample in truth['samples']:
        for r in sample['regions']:r['mask']=thaw(hash_file(path))
    truthpath=Path(source['truth']['path']);truthpath.write_text(json.dumps(truth),encoding='utf-8');source['truth']=thaw(hash_file(truthpath))
    original=Path.open
    with load_color_analysis_set([r['path'] for r in source['frame_records']],config=continuity_fixture[1]['config']) as reader:
        _,provider=build_control_case(source,'local_color',reader=reader,truth=truth)
        def no_mask(p,*args,**kwargs):
            if p==path:raise AssertionError('future truth mask opened during measurement')
            return original(p,*args,**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(Path,'open',no_mask)
            result=measure_continuity(provider.plan,provider)
        assert result['coverage']['requested_frames']==9
