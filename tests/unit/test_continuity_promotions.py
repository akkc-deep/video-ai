"""Historical identities survive only their fully bound production promotion."""
from copy import deepcopy
import json
import os
import tracemalloc
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest


def module():
    from video_ai.media import _continuity_promotions
    return _continuity_promotions


@pytest.fixture
def promotion_case(runtime_run):
    from video_ai.runtime.manifest import hash_file,thaw,now
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.scene_clip_records import technical_recipes
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.media.continuity_report import _ReadWindow
    run,_,paths=runtime_run;cid='scene_0001_clip_0001'
    folder=run/'production/scene-clips'/cid;folder.mkdir(parents=True)
    logs=run/'logs/production/source-clips';logs.mkdir(parents=True)
    def full(path):return thaw(hash_file(Path(path)))
    def art(path):return {k:v for k,v in full(path).items() if k in ('path','bytes','sha256')}
    def write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        return full(path)
    raw=run/'comfy/output/raw.mp4';raw.parent.mkdir(parents=True);raw.write_bytes(b'generated media')
    generated=folder/'generated.mp4';generated.write_bytes(raw.read_bytes())
    source=folder/'source.mp4';source.write_bytes(b'retained media')
    last=folder/'frame_000003.png';last.write_bytes(b'native image')
    budget=dict(clip_id=cid,scene_id='scene_0001',start_frame=0,end_frame=3,generated_frames=5,
        retained_frames=3,retained_source_start=0,retained_source_end=3)
    parameters=dict(width=16,height=16,length=5,fps=16)
    request=dict(schema_version=2,run_id=run.name,clip_id=cid,budget=budget,parameters=parameters)
    submission=dict(schema_version=2,run_id=run.name,clip_id=cid,output=art(raw))
    mapping=dict(clip_id=cid,scene_id='scene_0001',native_fps=16,output_fps=16,generated_frames=5,
        retained_frames=3,start_frame=0,end_frame=3,retained_to_generated=[0,1,2],generated_to_retained=[0,1,2,None,None])
    recipes=technical_recipes({'budget':budget,'parameters':parameters})
    receipts={};probes={};historical={}
    for index,(op,origin,target) in enumerate((('generated',art(raw),art(generated)),('source',art(generated),art(source)),('last_frame',art(generated),art(last))),1):
        stage=folder/'staging'/f'{index:032x}'/Path(target['path']).name
        stage.parent.mkdir(parents=True)
        old=dict(full(Path(target['path'])),path=str(stage));historical[op]=old
        probe=logs/(op+'.json');probes[op]=probe
        write(probe,{'info':{'identity':old},'source':origin})
        value=dict(schema_version=2,run_id=run.name,clip_id=cid,operation=op,source=origin,
            staging={k:old[k] for k in ('path','bytes','sha256')},target=target,recipe=recipes[op],
            evidence=[art(probe)],created_at=now())
        receipts[op]=value;write(folder/'media-ready'/(op+'.json'),value)
    last_frame=dict(schema_version=2,run_id=run.name,clip_id=cid,generated=art(generated),source_frame_index=2,
        global_output_frame_index=2,image=art(last),extraction_rule='native_index_rgb24_v1',evidence=receipts['last_frame']['evidence'])
    clip=dict(schema_version=2,production_strategy='paragraph_jimeng_v1',run_id=run.name,scene_id='scene_0001',clip_id=cid,
        request_sha256=canonical_digest(request),submission_sha256=canonical_digest(submission),generated=art(generated),source=art(source),
        frame_mapping_sha256=canonical_digest(mapping),last_frame_sha256=canonical_digest(last_frame),
        technical_evidence=sum((receipts[op]['evidence'] for op in ('generated','source','last_frame')),[]),created_at=now())
    for name,value in (('request',request),('submission',submission),('mapping',mapping),('last-frame',last_frame),('clip',clip)):
        write(folder/(name+'.json'),value)
    sidecar=dict(stage='retained',source=full(source),mapping=dict(rows=[dict(asset_frame_index=i,clip_id=cid,
        generated_frame_index=i,retained_frame_index=i,output_frame_index=i) for i in range(3)],
        evidence=[full(folder/'clip.json'),full(folder/'mapping.json'),full(folder/'media-ready/source.json')]),
        probe={'video':{'width':16,'height':16}},processing={'status':'unknown'})
    def window():return _ReadWindow(monotonic()+300,create_run(paths))
    return SimpleNamespace(run=run,folder=folder,sidecar=sidecar,receipts=receipts,probes=probes,
        historical=historical,window=window,full=full,art=art,write=write,source=source)


@pytest.mark.parametrize('operation',['generated','source','last_frame'])
def test_exact_missing_historical_identity_resolves_only_with_bound_promotion(promotion_case,operation):
    case=promotion_case;before=deepcopy(case.sidecar);window=case.window()
    resolver=module().PromotionResolver(window,[case.sidecar])
    assert resolver.resolve(case.historical[operation],case.probes[operation])
    resolver.verify();window.verify()
    assert case.sidecar==before and case.sidecar['processing']['status']=='unknown'
    assert not Path(case.historical[operation]['path']).exists()


@pytest.mark.parametrize('operation',['generated','source','last_frame'])
def test_byte_proof_keeps_actual_resolver_staging_absence(promotion_case,operation):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime.scene_continuity_records import _capture_promotion_absences
    case=promotion_case
    with capture_reads() as capture:
        resolver=module().PromotionResolver(case.window(),[case.sidecar])
        assert resolver.resolve(case.historical[operation],case.probes[operation])
        resolver.verify()
    guard=_capture_promotion_absences(capture.finish());guard.verify()
    path=Path(case.historical[operation]['path']);path.write_bytes(b'wrong reappeared bytes')
    with pytest.raises((ValueError,OSError)):guard.verify()


def test_promotion_absence_capture_cannot_bless_new_staging(promotion_case):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime.scene_continuity_records import _capture_promotion_absences
    case=promotion_case
    with capture_reads() as capture:module().PromotionResolver(case.window(),[case.sidecar]).verify()
    guard=capture.finish()
    Path(case.historical['source']['path']).write_bytes(case.source.read_bytes())
    with pytest.raises((ValueError,OSError)):_capture_promotion_absences(guard)


def test_combined_promotion_absences_stay_bounded(promotion_case):
    from dataclasses import replace
    from video_ai.runtime._continuity_byte_guard import capture_reads,CaptureLimit
    from video_ai.runtime.scene_continuity_records import _capture_promotion_absences
    case=promotion_case
    with capture_reads() as capture:module().PromotionResolver(case.window(),[case.sidecar]).verify()
    guard=replace(capture.finish(),absences=tuple(str(case.run/f'absent-{i}') for i in range(32768)))
    with pytest.raises(CaptureLimit):_capture_promotion_absences(guard)


def test_same_hash_in_unrelated_document_is_not_authorized(promotion_case):
    case=promotion_case;resolver=module().PromotionResolver(case.window(),[case.sidecar])
    assert not resolver.resolve(case.historical['source'],case.run/'unrelated.json')


@pytest.mark.parametrize('mutation',['recipe','operation','run','target','source','evidence_order','request_digest','mapping_digest','last_digest','missing_receipt'])
def test_resigned_but_invalid_production_proof_is_rejected(promotion_case,mutation):
    case=promotion_case;path=case.folder/'media-ready/source.json'
    value=deepcopy(case.receipts['source'])
    if mutation=='recipe':value['recipe']['parameters']['end_frame']=2
    elif mutation=='operation':value['operation']='generated'
    elif mutation=='run':value['run_id']='different'
    elif mutation=='target':value['target']['path']=str(case.run/'same-bytes.mp4');Path(value['target']['path']).write_bytes(case.source.read_bytes())
    elif mutation=='source':value['source']=value['target']
    elif mutation=='missing_receipt':(case.folder/'media-ready/generated.json').unlink()
    elif mutation=='evidence_order':value['evidence'].append(value['evidence'][0])
    else:
        name={'request_digest':'request','mapping_digest':'mapping','last_digest':'last-frame'}[mutation]
        original=case.folder/(name+'.json');body=json.loads(original.read_text());body['changed']=True;case.write(original,body)
    if mutation in ('recipe','operation','run','target','source','evidence_order'):
        case.write(path,value)
        case.sidecar['mapping']['evidence'][-1]=case.full(path)
    if mutation=='mapping_digest':case.sidecar['mapping']['evidence'][1]=case.full(case.folder/'mapping.json')
    with pytest.raises((ValueError,OSError)):module().PromotionResolver(case.window(),[case.sidecar])


@pytest.mark.parametrize('bad',[False,True])
def test_existing_stage_is_checked_instead_of_hidden_by_valid_target(promotion_case,bad):
    case=promotion_case;record=case.historical['source'];stage=Path(record['path'])
    stage.write_bytes(b'bad bytes' if bad else case.source.read_bytes())
    os.utime(stage,ns=(record['mtime_ns'],record['mtime_ns']))
    if bad:
        with pytest.raises((ValueError,OSError)):module().PromotionResolver(case.window(),[case.sidecar])
    else:
        window=case.window();resolver=module().PromotionResolver(window,[case.sidecar])
        assert resolver.resolve(record,case.probes['source'])
        resolver.verify();window.verify()


def test_stage_appearing_with_bad_bytes_during_verification_is_rejected(promotion_case):
    case=promotion_case;resolver=module().PromotionResolver(case.window(),[case.sidecar])
    Path(case.historical['source']['path']).write_bytes(b'bad later data')
    with pytest.raises((ValueError,OSError)):resolver.verify()


def test_small_invalid_mapping_with_large_declared_budget_does_not_allocate_budget_arrays(promotion_case):
    """A signed declaration cannot allocate memory proportional to its frame count."""
    from video_ai.planning.production_scenes import canonical_digest
    case=promotion_case
    request_path=case.folder/'request.json'
    request=json.loads(request_path.read_text())
    request['budget']['generated_frames']=500_000
    request['parameters']['length']=500_000
    case.write(request_path,request)
    mapping_path=case.folder/'mapping.json'
    mapping=json.loads(mapping_path.read_text());mapping['generated_frames']=500_000
    case.write(mapping_path,mapping)
    clip_path=case.folder/'clip.json';clip=json.loads(clip_path.read_text())
    clip['request_sha256']=canonical_digest(request)
    clip['frame_mapping_sha256']=canonical_digest(mapping)
    case.write(clip_path,clip)
    case.sidecar['mapping']['evidence'][:2]=[case.full(clip_path),case.full(mapping_path)]
    resolver=module().PromotionResolver
    tracemalloc.start()
    try:
        initial=tracemalloc.get_traced_memory()[0]
        with pytest.raises((ValueError,OSError)):
            resolver(case.window(),[case.sidecar])
        peak=tracemalloc.get_traced_memory()[1]-initial
    finally:
        tracemalloc.stop()
    assert peak<2*1024*1024, f'invalid small metadata allocated {peak} bytes'
