"""Real CPU native16 media; synthetic imagery is never natural acceptance."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import pytest


@pytest.fixture
def natural_media(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.manifest import now,thaw,hash_file
    from video_ai.runtime.natural_study_records import put_json
    from video_ai.runtime.natural_candidate_media import inspect_media
    from video_ai.media._continuity_audit import png_bytes
    from video_ai.media.colorimetry import inspect_color_asset,decode_analysis_frame,load_color_analysis_set
    from video_ai.media.color_repair import apply_constant_repair
    from video_ai.media.research_pair_report import analyze_research_pairs
    from continuity_helpers import texture
    import numpy as np
    run,config,paths=runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config=replace(config,tools=dict(config.tools,ffmpeg=actual.tools['ffmpeg'],ffprobe=actual.tools['ffprobe']))
    logger=RunLogger(create_run(paths));raw=run/'source.rgb';rgb=(170+texture(128,128)//3).astype(np.uint8)
    raw.write_bytes(rgb.tobytes()*4);video=run/'source.mp4'
    cmd=run_logged([str(config.tools['ffmpeg']),'-nostdin','-n','-v','error','-threads','1','-f','rawvideo',
        '-pixel_format','rgb24','-video_size','128x128','-framerate','16','-i',str(raw),'-frames:v','4',
        '-c:v','libx264','-crf','0','-pix_fmt','yuv444p','-an','-colorspace','bt709','-color_trc','iec61966-2-1',
        '-color_primaries','bt709','-color_range','tv','-x264-params','colorprim=bt709:transfer=iec61966-2-1:colormatrix=bt709',str(video)],cwd=run,env=build_child_env(paths),timeout=60,logger=logger,stage='fixture_only')
    assert cmd.returncode==0
    command=put_json(run/'source-command.json',dict(schema_version=1,command=thaw(cmd),source=thaw(hash_file(raw)),target=thaw(hash_file(video))))
    side,frames=inspect_media(video,4,command=command,out=run/'source-proof',config=config,paths=paths,clip_id='fixture')
    with load_color_analysis_set([frames[0]['record']['path']],config=config) as colors:
        source_rgb=np.frombuffer(colors.read_rgb(frames[0]['record']['path']),np.uint8).reshape(128,128,3)
        clean=apply_constant_repair(source_rgb,operation='exposure',amplitude=-.018)
    png=run/'reference.png';png.write_bytes(png_bytes(clean))
    a=RunLogger(create_run(paths));row=dict(asset_frame_index=0,clip_id='fixture_reference',generated_frame_index=None,retained_frame_index=None,output_frame_index=None,pts=0,time_base='1/1')
    proof=put_json(run/'reference-map.json',dict(source=thaw(hash_file(png)),rows=[row]))
    refside,_=inspect_color_asset(dict(asset_id='reference',stage='composition',path=str(png),mapping=dict(rows=[row],evidence=[thaw(hash_file(Path(proof['path'])))]),
        processing=dict(operation='software fixture reference',upstream_ids=[],command_records=[])),config=config,paths=paths,logger=a)
    decode_analysis_frame(refside,frame_index=0,config=config,paths=paths,logger=a)
    reference=thaw(hash_file(a.root/'colorimetry/reference/analysis/frame_000000.json'))
    regions=put_json(run/'regions.json',dict(schema_version=1,author='software fixture',reviewed_at=now(),regions=[dict(region_id='subject',role='subject',identity_note='constructed CPU fixture; reference uses interior ROI',anchors=[dict(frame=frames[0]['record'],rect=[0,0,1,1]),dict(frame=reference,rect=[.05,.05,.95,.95])])]))
    manifest=dict(schema_version=1,algorithm='continuity_cv_v1',scope='clip',scene_id='fixture',domain=dict(genre='animation',source_kind='generated'),
        timeline=dict(fps_num=16,fps_den=1),clips=[dict(clip_id='fixture',frames=frames)],references=[dict(frame_id='reference',record=reference)],
        regions=thaw(hash_file(Path(regions['path']))),context=None,profile=None,comparisons=[dict(comparison_id=f'adj_{i}',kind='adjacent',left=frames[i]['frame_id'],right=frames[i+1]['frame_id'],region_ids=['subject']) for i in range(3)]+
        [dict(comparison_id=f'ref_{i}',kind='reference',left='reference',right=f['frame_id'],region_ids=['subject']) for i,f in enumerate(frames)])
    audit=RunLogger(create_run(paths));report,_=analyze_research_pairs(manifest,config=config,paths=paths,logger=audit)
    return run,config,paths,manifest,report,put_json(run/'report-ref.json',dict(report=str(audit.root/'continuity/report.json'))),video,audit.root/'continuity/report.json'


def test_native16_render_full_decode_mapping_tail_and_fixed_support(natural_media):
    from video_ai.runtime.natural_candidate_media import render_media,validate_media
    from video_ai.runtime.natural_study_records import StudyReader
    from video_ai.runtime._scene_continuity_io import artifact
    run,config,paths,manifest,report,_,video,report_path=natural_media
    fit=dict(status='estimated',operation='exposure',amplitude=-.018)
    media=render_media(manifest,report,fit,out=run/'candidate',source=artifact(video),before_report=artifact(report_path),
        config=config,paths=paths)
    assert media['frames']==4 and len(media['roundtrip_max'])==4 and max(media['roundtrip_max'])<=2
    assert all(r['new_clip']==0 for r in media['full_frame']) and media['last_frame']['bytes']>0
    assert media['scores']['improvement']>0
    validate_media(media,manifest=manifest,report=report,fit=fit,config=config)
    p=Path(media['intended']['path']);raw=p.read_bytes();p.write_bytes(raw[:-1])
    with pytest.raises(ValueError): validate_media(media,manifest=manifest,report=report,fit=fit,config=config)


def test_partial_native_media_never_overwrites_or_reencodes(natural_media):
    from video_ai.runtime.natural_candidate_media import render_media
    from video_ai.runtime._scene_continuity_io import artifact
    run,config,paths,manifest,report,_,video,report_path=natural_media
    out=run/'partial';out.mkdir();p=out/'master.mp4';p.write_bytes(b'partial output')
    with pytest.raises(ValueError,match='partial'):
        render_media(manifest,report,dict(status='estimated',operation='exposure',amplitude=-.01),out=out,source=artifact(video),before_report=artifact(report_path),config=config,paths=paths)
    assert p.read_bytes()==b'partial output'


@pytest.mark.parametrize('problem',['master_swap','playback_omit','playback_reorder'])
def test_scored_and_played_inventory_must_be_complete_and_bound_to_actual_master(natural_media,problem):
    import json
    from video_ai.runtime.natural_candidate_media import render_media,_full_decode
    from video_ai.runtime._scene_continuity_io import artifact
    run,config,paths,manifest,report,_,video,report_path=natural_media
    fit=dict(status='estimated',operation='exposure',amplitude=-.018)
    media=render_media(manifest,report,fit,out=run/'candidate',source=artifact(video),before_report=artifact(report_path),config=config,paths=paths)
    if problem=='master_swap':
        from video_ai.runtime.natural_candidate_media import inspect_media
        _,other=inspect_media(video,4,command=artifact(run/'source-command.json'),out=run/'other-source-proof',config=config,paths=paths,clip_id='fixture')
        media['master_frames']=other
    else:
        p=Path(media['playback_inspection']['path']);inspection=json.loads(p.read_bytes())
        if problem=='playback_omit': inspection['frames']=inspection['frames'][:1]
        else: inspection['frames']=list(reversed(inspection['frames']))
        p.write_text(json.dumps(inspection),encoding='utf-8');media['playback_inspection']=artifact(p)
    with pytest.raises(ValueError): _full_decode(media,manifest,fit,config=config)


def test_refreshed_geometry_shards_are_replayed_from_original_pixels(natural_media):
    import json
    from video_ai.media.research_pair_report import validate_research_pair_report
    from video_ai.runtime._scene_continuity_io import artifact
    from video_ai.runtime.natural_study_measure import replay_ordinary_report
    run,config,paths,manifest,report,_,video,report_path=natural_media
    changed=deepcopy(report);row=next(r for r in changed['comparisons'] if r['kind']=='reference')
    part_path=Path(row['parts'][0]['path']);part=json.loads(part_path.read_bytes());pair=json.loads(part['payload'])
    pair['regions'][0]['geometry']['sampled_pairs'][0][0][0]+=1
    part['payload']=json.dumps(pair,separators=(',',':'))+'\n';part_path.write_text(json.dumps(part),encoding='utf-8')
    row['parts'][0]=artifact(part_path);report_path.write_text(json.dumps(changed),encoding='utf-8')
    # Legacy validation deliberately stays byte-stable and accepts structurally
    # valid refreshed geometry. New authority must actually reconstruct it.
    validate_research_pair_report(report_path,manifest=manifest,config=config)
    with pytest.raises(ValueError,match='replay'): replay_ordinary_report(artifact(report_path),manifest=manifest,config=config)
