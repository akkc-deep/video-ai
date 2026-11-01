"""Repair fixtures. Authored playback is synthetic and never visual acceptance."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from scene_continuity_helpers import artifact,save,snapshot,AUTHOR


def repair_request(setup,assessment,*,profile=None,operation='wb_g'):
    from video_ai.runtime.manifest import now,hash_file,thaw
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    from video_ai.media.colorimetry import inspect_color_asset,decode_analysis_frame
    assessment_path=Path(assessment);current=__import__('json').loads(assessment_path.read_text(encoding='utf-8'))
    cid=current['clip_id'];record=setup['records'][cid];index=next(i for i,r in enumerate(setup['all_frames']) if r['clip_id']==cid)
    logger=RunLogger(create_run(setup['paths']))
    selected=Path(record['request']['selected_image']['path'])
    # A selected still has its own declared reference coordinate at t=0; it
    # does not claim to be a generated or retained video frame. Ordinary
    # reference matching requires this explicit clip/time coordinate proof.
    reference_row=dict(asset_frame_index=0,clip_id='repair_reference_image',generated_frame_index=None,
        retained_frame_index=None,output_frame_index=None,pts=0,time_base='1/16')
    reference_proof=save(setup['run']/('fixture_only-selected-mapping-'+uuid4().hex+'.json'),
        dict(source=thaw(hash_file(selected)),rows=[reference_row]))
    entry=dict(asset_id='clean_selected',stage='native_tail',path=str(selected),
        mapping=dict(rows=[reference_row],evidence=[thaw(hash_file(reference_proof))]),
        processing=dict(operation='independent selected sRGB reference at declared t=0',upstream_ids=[],command_records=[]))
    sc,_=inspect_color_asset(entry,config=setup['config'],paths=setup['paths'],logger=logger)
    decode_analysis_frame(sc,frame_index=0,config=setup['config'],paths=setup['paths'],logger=logger)
    reference=dict(frame_id='repair_clean_reference',record=thaw(hash_file(logger.root/'colorimetry/clean_selected/analysis/frame_000000.json')))
    target=deepcopy(setup['all_frames'][index]);frames=target['frames'];rids=['background','subject']
    regions=save(setup['run']/('fixture_only-repair-regions-'+uuid4().hex+'.json'),
        dict(schema_version=1,author=AUTHOR,reviewed_at=now(),regions=[dict(region_id=rid,role=rid,
            identity_note='fixture_only same texture',anchors=[dict(frame=reference['record'],rect=[0.,0.,1.,1.]),
                dict(frame=frames[0]['record'],rect=[0.,0.,1.,1.])]) for rid in rids]))
    comparisons=[dict(comparison_id=f'repair_adj_{i:06d}',kind='adjacent',left=frames[i-1]['frame_id'],
        right=frames[i]['frame_id'],region_ids=rids) for i in range(1,len(frames))]
    comparisons += [dict(comparison_id=f'repair_ref_{i:06d}',kind='reference',left=reference['frame_id'],right=f['frame_id'],region_ids=rids)
        for i,f in enumerate(frames)]
    manifest=save(setup['run']/('fixture_only-pair-manifest-'+uuid4().hex+'.json'),
        dict(schema_version=1,algorithm='continuity_cv_v1',scope='clip',scene_id=current['binding']['scene_id'],
            domain=dict(genre='animation',source_kind='generated'),timeline=dict(fps_num=16,fps_den=1),
            clips=[target],references=[reference],regions=thaw(hash_file(regions)),comparisons=comparisons,context=None,profile=None))
    basis='fixture_only known wb_g axis; independent selected image color/lighting is intended target'
    folder=Path(current['binding']['clips'][-1]['clip_record']['path']).parent
    precheck=save(setup['run']/('fixture_only-precheck-'+uuid4().hex+'.json'),dict(schema_version=1,run_id=setup['run'].name,
        clip_id=cid,assessment=artifact(assessment_path),source_clip=artifact(folder/'clip.json'),
        video_observation=record['accepted']['observation'],reviewer=AUTHOR,reviewed_at=now(),
        color_issue='fixture_only mild green-axis issue',operation=operation,operator_basis=basis,
        subject_structure_intact=True,motion_intact=True,intentional_lighting_change=False,
        responses=[dict(concern_id=c['concern_id'],disposition='confirmed_issue' if c['detector_id'] in
            ('seam_color','local_color','color_drift','cumulative_color') else 'not_observed_in_full_playback',
            reason='fixture_only schema test; no actual playback claim',references=[]) for c in current['concerns']]))
    if profile is None:profile=save(setup['run']/'fixture_only-profile.json',{'fixture_only':True})
    req=dict(schema_version=1,run_id=setup['run'].name,candidate_id=str(uuid4()),policy='research_candidate_v1',clip_id=cid,
        source_clip=artifact(folder/'clip.json'),assessment=artifact(assessment_path),profile=artifact(profile),manifest=artifact(manifest),
        operation=operation,context=dict(comparable=True,intentional_lighting_change=False,confirmed_motion_defect=False,
            subject_structure_intact=True,operator_basis=basis,review=artifact(precheck)),revision_of=None,requested_at=now(),reason='fixture_only repair')
    return save(setup['run']/('fixture_only-request-'+uuid4().hex+'.json'),req)
