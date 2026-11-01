"""Offline, quantized natural measurements. No runtime repair authority."""
from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np

from ..media.color_repair import apply_constant_repair
from ..media.natural_color_repair import natural_patch_features
from ..media.natural_repair_engine import DIRECTIONS,METRICS,fit_natural_parameter
from ..media.natural_repair_statistics import compare_natural_bias,natural_bias_statistics
from .natural_study_records import StudyReader,case_context,read_author_observations,put_json
from .production_state import ProductionRefused


def safe_author(author):
    return (author.get('natural_label')=='mild_color_bias'
        and (author.get('operation'),author.get('correction_direction')) in DIRECTIONS
        and all(author.get(k) is True for k in ('target_reference_confirmed','subject_structure_intact','motion_intact'))
        and author.get('intentional_lighting_change') is False
        and author.get('unresolved') is False and author.get('hard_noncolor_failure') is False)


def measure_pixels(reference,current,coordinates,regions,index):
    f=natural_patch_features(reference,current,coordinates,regions)
    return dict(source_frame_index=index,status=f['status'],features=f)


def fixed_compare(before,after,*,operation):
    return compare_natural_bias(before,after,operation=operation)


def control_recipes(operation,amplitude):
    constant=lambda op,a:dict(kind='constant',operation=op,amplitude=a)
    rows=[dict(name='identity',kind='identity')]
    for op in ('exposure','wb_r','wb_g'):
        for a in (-.02,-.01,.01,.02):
            rows.append(dict(name=f'inject_{op}_{a}',**constant(op,a)))
            rows.append(dict(name=f'inverse_{op}_{a}',kind='sequence',steps=[constant(op,a),constant(op,-a)]))
    injection=constant(operation,-amplitude)
    rows += [dict(name='wrong_direction',kind='sequence',steps=[injection,deepcopy(injection)]),
        dict(name='overcorrection',kind='sequence',steps=[injection,constant(operation,3*amplitude)]),
        dict(name='mixed_axis',kind='sequence',steps=[constant('exposure',.02),constant('wb_r',.02)]),
        dict(name='local',kind='local',operation='wb_r',amplitude=.02),
        dict(name='temporal',kind='temporal',operation='wb_r',amplitude=.02),
        dict(name='clip',**constant('exposure',2.)),dict(name='structural',kind='structural',shift=16)]
    return rows


def transform(image,recipe,index,count):
    kind=recipe['kind']
    if kind=='identity': return image.copy()
    if kind=='constant': return apply_constant_repair(image,operation=recipe['operation'],amplitude=recipe['amplitude'])
    if kind=='sequence':
        value=image.copy()
        for step in recipe['steps']: value=transform(value,step,index,count)
        return value
    if kind=='temporal':
        return apply_constant_repair(image,operation=recipe['operation'],amplitude=recipe['amplitude']*math.sin(2*math.pi*index/count))
    h,w=image.shape[:2];result=image.copy();y0,y1=h//4,3*h//4;x0,x1=w//4,3*w//4
    if kind=='local':
        result[y0:y1,x0:x1]=apply_constant_repair(np.ascontiguousarray(image[y0:y1,x0:x1]),operation=recipe['operation'],amplitude=recipe['amplitude'])
    elif kind=='structural':
        end=min(w,x1+recipe['shift']);start=x0+recipe['shift']
        if start<end: result[y0:y1,start:end]=image[y0:y1,x0:x0+end-start]
    else: raise ValueError('unknown frozen control')
    return result


def support(manifest,report,reader):
    """Original ordinary sampled coordinates and propagated region boxes."""
    from ..media.research_pair_report import read_comparison
    declared={r['region_id']:r for r in reader.any(manifest['regions'])['regions']}
    reference=manifest['references'][0]
    by_right={r['right']:r for r in report['comparisons'] if r['kind']=='reference'}
    trajectories={t['region_id']:{s['frame_id']:s for s in t['samples']} for t in report['trajectories']}
    for frame in manifest['clips'][0]['frames']:
        row=by_right[frame['frame_id']]
        pair=read_comparison(row,folder=Path(report['producer'])/'logs/continuity',reader=reader,
            producer=report['producer'],input_sha256=report['input_sha256'])
        coords=[];regions={}
        for r in pair['regions']:
            rid=r['region_id'];d=declared[rid]
            if r['comparability']!='comparable': raise ProductionRefused('ordinary_pair_not_comparable:'+rid)
            anchor=next(a for a in d['anchors'] if a['frame']['path']==reference['record']['path'])
            box=trajectories.get(rid,{}).get(frame['frame_id'],{}).get('box')
            if box is None: raise ProductionRefused('missing_propagated_region:'+rid)
            regions[rid]=dict(role=d['role'],reference_rect=anchor['rect'],current_rect=box)
            coords += [dict(region_id=rid,reference=p[0],current=p[1]) for p in r['geometry']['sampled_pairs']]
        yield coords,regions


class PixelSource:
    """One RGB frame at a time; validated underlying VCO-02 analysis records."""
    def __init__(self,manifest,config,reader,*,candidate_frames=None):
        from ..media.colorimetry import load_color_analysis_set
        self.targets=manifest['clips'][0]['frames'];self.reference=manifest['references'][0]
        self.candidates=candidate_frames
        entries=[self.reference]+self.targets+(candidate_frames or [])
        self.colors=load_color_analysis_set([f['record']['path'] for f in entries],config=config,timeout=reader.remaining())
        self.records={r['record_identity']['path']:r['record'] for r in self.colors.frames}
        self.reader=reader
    def rgb(self,entry):
        self.reader.check();record=self.records[entry['record']['path']]
        v=self.colors.sidecars[record['sidecar']['path']]['probe']['video']
        size=v['width']*v['height']*3
        if size>32*1024**2: raise ProductionRefused('resource_limit: natural RGB frame')
        raw=self.colors.read_rgb(entry['record']['path'])
        if raw is None or len(raw)!=size: raise ProductionRefused('complete natural RGB required')
        return np.frombuffer(raw,np.uint8).reshape(v['height'],v['width'],3)
    def __enter__(self): self.colors.__enter__();return self
    def __exit__(self,*args): return self.colors.__exit__(*args)


def _bounded_append(rows,value):
    # Feature windows may be larger than an individual output shard, never64MiB.
    rows.append(value)
    size=sum(len(json.dumps(r,separators=(',',':'),allow_nan=False)) for r in rows)
    if size>16*1024**2: raise ProductionRefused('resource_limit: natural feature window')


def measure_variant(manifest,report,*,config,out,recipe=None,oracle=False,candidate_frames=None,reader=None):
    """Remeasure actual RGB8 on unchanged coordinates; save every frame separately."""
    from ._scene_color_repair_media import frame_changes
    reader=reader or StudyReader();reader.check();before=[];after=[];refs=[];checks=[]
    count=len(manifest['clips'][0]['frames'])
    if not 1<=count<=4096: raise ProductionRefused('bounded complete native frames required')
    if candidate_frames is not None and len(candidate_frames)!=count: raise ProductionRefused('candidate coverage differs')
    with PixelSource(manifest,config,reader,candidate_frames=candidate_frames) as source:
        reference=source.rgb(source.reference)
        for i,(coords,regions) in enumerate(support(manifest,report,reader)):
            original=source.rgb(source.targets[i])
            if oracle:
                left=original
                coords=[dict(c,reference=c['current']) for c in coords]
                regions={k:dict(r,reference_rect=r['current_rect']) for k,r in regions.items()}
            else: left=reference
            changed=(source.rgb(candidate_frames[i]) if candidate_frames is not None else
                transform(original,recipe,i,count) if recipe else original)
            b=measure_pixels(left,original,coords,regions,i);a=measure_pixels(left,changed,coords,regions,i)
            _bounded_append(before,b);_bounded_append(after,a)
            check=dict(source_frame_index=i,**frame_changes(original,changed));checks.append(check)
            row=dict(schema_version=1,source=source.targets[i]['record'],reference=source.reference['record'],
                oracle_current_truth=oracle,recipe=recipe,before=b,after=a,full_frame=check)
            if out is not None: refs.append(put_json(Path(out)/f'frame_{i:06d}.json',row))
    reader.verify_all()
    return dict(before=before,after=after,frames=refs,full_frame=checks)


def metric_summary(comparison):
    return dict(initial_bias=comparison['before']['bias_max_absolute'],improvement=comparison['improvement'],
        **{k:comparison[k] for k in METRICS})


def replay_ordinary_report(path,*,manifest,config,reader=None):
    """Reconstruct ordinary geometry from RGB, without writing an audit/run."""
    from ..media.research_pair_report import validate_research_pair_report,read_comparison
    from ..media.continuity_analysis import _resolve_manifest,_ReaderProvider,measure_continuity
    from ..media.colorimetry import load_color_analysis_set
    r=reader or StudyReader();r.check()
    report=validate_research_pair_report(path,manifest=manifest,config=config,timeout=r.remaining())['report']
    class Window:
        def read_json(self,value): return r.any(value)
        def check(self,value): return r.capture(value,package=True)
    entries=[f for c in manifest['clips'] for f in c['frames']]+manifest['references']
    with load_color_analysis_set([f['record']['path'] for f in entries],config=config,timeout=r.remaining()) as colors:
        plan,records=_resolve_manifest(manifest,colors,Window())
        actual=measure_continuity(plan,_ReaderProvider(plan,records,colors),deadline=r.deadline)
        for frame in actual['frame_results']:
            frame['source']=records[frame['frame_id']]['source'];frame['risks']=records[frame['frame_id']]['risks']
        source_records={f['frame_id']:f['source_record'] for f in plan['frames']}
        for pair in actual['comparisons']:
            for region in pair['regions']: region['evidence']=[source_records[pair[side]] for side in ('left','right')]
        live=len(json.dumps(actual,separators=(',',':'),allow_nan=False).encode())+len(json.dumps(report,separators=(',',':'),allow_nan=False).encode())
        if live>48*1024**2: raise ProductionRefused('resource_limit: ordinary replay metadata window')
        for key in ('coverage','frame_results','trajectories','detectors'):
            if report[key]!=actual[key]: raise ProductionRefused('ordinary geometry replay differs:'+key)
        if len(actual['comparisons'])!=len(report['comparisons']): raise ProductionRefused('ordinary geometry replay coverage differs')
        for expected,row in zip(actual['comparisons'],report['comparisons']):
            r.check()
            saved=read_comparison(row,folder=Path(report['producer'])/'logs/continuity',reader=r,
                producer=report['producer'],input_sha256=report['input_sha256'])
            if live+len(json.dumps(saved,separators=(',',':'),allow_nan=False).encode())>64*1024**2:
                raise ProductionRefused('resource_limit: ordinary replay comparison window')
            if saved!=expected: raise ProductionRefused('ordinary geometry sampled-pair replay differs')
        for ref in colors.identities: r.capture(ref,package=True)
    r.verify_all();return report


def measure_case(case,*,config,conditional_profile,out,paths=None):
    from ..media.research_pair_report import analyze_research_pairs
    from .paths import RuntimePaths,create_run
    from .logging import RunLogger
    reader=StudyReader();context=case_context(case,reader,open_holdout=True);manifest=reader.any(case['manifest'])
    author=read_author_observations(case,context,reader)
    paths=paths or RuntimePaths.from_config(config)
    logger=RunLogger(create_run(paths))
    put_json(Path(out)/'ordinary-intent.json',dict(producer=str(logger.run_dir),manifest=case['manifest']))
    report,_=analyze_research_pairs(manifest,config=config,paths=paths,logger=logger,timeout=reader.remaining())
    report_ref=reader.cap(logger.root/'continuity/report.json')
    variants={};base=None;reason=None;fit=None;preview=None
    try:
        base=measure_variant(manifest,report,config=config,out=Path(out)/'original',reader=reader)
        for op in ('exposure','wb_r','wb_g'): natural_bias_statistics(base['before'],operation=op)
        if safe_author(author):
            fit=fit_natural_parameter(base['before'],operation=author['operation'],conditional_profile=conditional_profile)
            if fit['status']=='estimated' and fit['correction_direction']==author['correction_direction']:
                variants['dry']=measure_variant(manifest,report,config=config,out=Path(out)/'dry',
                    recipe=dict(kind='constant',operation=fit['operation'],amplitude=fit['amplitude']),reader=reader)
                # An offline preview is needed for the independent real viewing
                # gate. It never appears in a runtime candidate ledger.
                from .natural_candidate_media import render_media
                preview=render_media(manifest,report,fit,out=Path(out)/'qualification-preview',source=context['source'],
                    before_report=report_ref,config=config,paths=paths,reader=reader)
    except TimeoutError: raise
    except (ValueError,OSError) as error: reason=str(error)
    controls={}
    # Controls are separate offline oracles, including failures. They do not
    # label the natural case or authorize candidate rendering.
    for op,direction in DIRECTIONS:
        key=op+':'+direction;items=[]
        for n,recipe in enumerate(control_recipes(op,.01 if direction=='positive' else -.01)):
            reader.check()
            try:
                variant=measure_variant(manifest,report,config=config,out=Path(out)/'controls'/key.replace(':','_')/str(n),recipe=recipe,oracle=True,reader=reader)
                metrics=fixed_compare(variant['before'],variant['after'],operation=op)
                items.append(dict(recipe=recipe,status='measured',frames=variant['frames'],metrics=metric_summary(metrics)))
            except TimeoutError: raise
            except (ValueError,OSError) as error:
                items.append(dict(recipe=recipe,status='refused',frames=[],reason=str(error)))
        controls[key]=items
    projections=[]
    for op,direction in DIRECTIONS:
        row=dict(case_id=case['case_id'],scene_group=case['scene_group'],domain=case['domain'],
            natural_label=author['natural_label'],operation=author['operation'],correction_direction=author['correction_direction'],
            projection_operation=op,projection_direction=direction,status='refused',controls={k:[] for k in ('wrong_direction','overcorrection','mixed_axis','local','temporal')})
        if base is not None and reason is None and not author['unresolved'] and not author['hard_noncolor_failure']:
            target=safe_author(author) and (op,direction)==(author['operation'],author['correction_direction'])
            if author['natural_label']=='neutral' or target and 'dry' in variants:
                after=variants['dry']['after'] if target else base['before']
                try:
                    metrics=preview['scores'] if target and preview is not None else fixed_compare(base['before'],after,operation=op)
                    if target and preview is None: raise ValueError('actual qualification preview unavailable')
                    if any(r['new_clip'] for r in variants.get('dry',base)['full_frame']): raise ValueError('full_frame_clipping')
                    row.update(status='measured',**metric_summary(metrics))
                except ValueError as error: row['reason']=str(error)
        for item in controls[op+':'+direction]:
            name=item['recipe']['name']
            if name in row['controls'] and item['status']=='measured': row['controls'][name].append(item['metrics'])
        projections.append(row)
    reader.verify_all()
    return dict(schema_version=1,case=case,material=context['commit'],epoch=context['epoch'],author=author,
        report=report_ref,original=[] if base is None else base['frames'],dry=variants.get('dry',{}).get('frames',[]),
        fit=fit,preview=preview,controls=controls,projections=projections,reason=reason,ready_for_propose=False)


def replay_case(result,*,config,conditional_profile):
    """Recompute pixels and reductions; rehashed metric JSON alone is no authority."""
    reader=StudyReader();case=result['case'];context=case_context(case,reader,open_holdout=True)
    author=read_author_observations(case,context,reader)
    if author!=result['author'] or context['commit']!=result['material'] or context['epoch']!=result['epoch']:
        raise ProductionRefused('natural producer/source/author replay differs')
    if [(p['projection_operation'],p['projection_direction']) for p in result['projections']]!=list(DIRECTIONS):
        raise ProductionRefused('natural projection inventory differs')
    for p in result['projections']:
        if (any(p[k]!=author[k] for k in ('natural_label','operation','correction_direction'))
                or any(p[k]!=case[k] for k in ('case_id','scene_group','domain'))
                or p['status']=='measured' and (author['unresolved'] or author['hard_noncolor_failure'])):
            raise ProductionRefused('natural projection original author/history differs')
    manifest=reader.any(case['manifest'])
    report=replay_ordinary_report(result['report'],manifest=manifest,config=config,reader=reader)
    # Feature artifacts bind original and changed pixel measurements, not merely
    # their hashes. Every variant shares this case's original deadline.
    def check(refs,recipe=None,oracle=False):
        if not refs: return None
        v=measure_variant(manifest,report,config=config,out=None,recipe=recipe,oracle=oracle,reader=reader)
        if len(refs)!=len(v['before']): raise ProductionRefused('natural variant coverage differs')
        for i,r in enumerate(refs):
            row=reader.any(r)
            if row['before']!=v['before'][i] or row['after']!=v['after'][i] or row['full_frame']!=v['full_frame'][i]:
                raise ProductionRefused('natural pixel feature replay differs')
        return v
    base=check(result['original']);dry=None
    if result['dry']:
        if base is None or not safe_author(author): raise ProductionRefused('unauthorized natural dry transform')
        fit=fit_natural_parameter(base['before'],operation=author['operation'],conditional_profile=conditional_profile)
        if fit!=result['fit'] or fit['status']!='estimated' or fit['correction_direction']!=author['correction_direction']:
            raise ProductionRefused('natural dry fit differs')
        dry=check(result['dry'],dict(kind='constant',operation=fit['operation'],amplitude=fit['amplitude']))
    preview=result.get('preview')
    if preview is not None:
        from .natural_candidate_media import validate_media
        if dry is None: raise ProductionRefused('preview lacks authorized natural dry fit')
        if reader.any(Path(preview['candidate']['path']).parent/'media.json')!=preview:
            raise ProductionRefused('independent natural preview identity differs')
        validate_media(preview,manifest=manifest,report=report,fit=result['fit'],config=config,reader=reader)
    for op,direction in DIRECTIONS:
        key=op+':'+direction;items=result['controls'][key]
        recipes=control_recipes(op,.01 if direction=='positive' else -.01)
        if [r['recipe'] for r in items]!=recipes: raise ProductionRefused('frozen control inventory differs')
        for item in items:
            if item['status']=='measured':
                v=check(item['frames'],item['recipe'],True)
                if v is None or metric_summary(fixed_compare(v['before'],v['after'],operation=op))!=item['metrics']:
                    raise ProductionRefused('natural control reduction differs')
        row=next(r for r in result['projections'] if (r['projection_operation'],r['projection_direction'])==(op,direction))
        if row['status']=='measured':
            target=safe_author(author) and (op,direction)==(author['operation'],author['correction_direction'])
            if base is None or (not target and author['natural_label']!='neutral') or target and dry is None:
                raise ProductionRefused('measured natural projection lacks authority')
            if target and preview is None: raise ProductionRefused('positive lacks actual qualification preview')
            metrics=metric_summary(preview['scores'] if target else fixed_compare(base['before'],base['before'],operation=op))
            if any(row[k]!=v for k,v in metrics.items()): raise ProductionRefused('natural metric reduction differs')
            expected={k:[i['metrics'] for i in items if i['recipe']['name']==k and i['status']=='measured'] for k in row['controls']}
            if row['controls']!=expected: raise ProductionRefused('natural harmful control reduction differs')
    reader.verify_all()
    return result
