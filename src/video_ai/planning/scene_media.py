"""Exact once-only retained native frames and their global contributions."""
from copy import deepcopy
from collections.abc import Mapping
from .scene_clip_continuation import scene_clip_frame_mapping, _artifact
from .source_clips import _integer, _same
from .production_scenes import canonical_digest


def plan_scene_upscale(scene_clips):
    if not isinstance(scene_clips, Mapping): raise ValueError('scene clips object required')
    allowed=set('schema_version production_strategy run_id inputs_sha256 scene_plan_sha256 visual_bible_sha256 wan_inputs_sha256 timeline_sha256 total_frames scenes clips'.split())
    native = type(scene_clips.get('schema_version')) is int and scene_clips['schema_version']==4
    if native:
        allowed.update(('execution_budget','protocol','temporal_chains'))
        if set(scene_clips)!=allowed or scene_clips['protocol']!='longcat_native16_v1':raise ValueError('exact native index schema/protocol required')
        _artifact(scene_clips['execution_budget'])
    elif type(scene_clips.get('schema_version')) is int and scene_clips['schema_version'] == 3:
        allowed.add('execution_budget')
        budget = scene_clips.get('execution_budget')
        if not isinstance(budget, Mapping) or set(budget) != {'path','bytes','sha256'}:
            raise ValueError('schema3 scene clips require exact execution budget Artifact')
        _artifact(budget)
    elif 'schema_version' in scene_clips and (type(scene_clips['schema_version']) is not int or scene_clips['schema_version'] != 2):
        raise ValueError('unknown scene clips index schema')
    if set(scene_clips)-allowed: raise ValueError('unknown scene clips fields')
    total = _integer(scene_clips.get('total_frames'), 'total_frames', 1)
    clips = scene_clips.get('clips')
    if not isinstance(clips, (list, tuple)) or not clips: raise ValueError('ordered clips required')
    chains={}
    if native:
        if not isinstance(scene_clips['temporal_chains'],(list,tuple)):raise ValueError('ordered native chain acceptances required')
        for chain in scene_clips['temporal_chains']:
            if not isinstance(chain,Mapping) or set(chain)!=set(('scene_id','result','acceptance','frame_range')) or chain['scene_id'] in chains:
                raise ValueError('exact unique native chain required')
            _artifact(chain['result']);_artifact(chain['acceptance'])
            bounds=chain['frame_range']
            if not isinstance(bounds,(list,tuple)) or len(bounds)!=2 or any(type(n) is not int for n in bounds) or not 0<=bounds[0]<bounds[1]:
                raise ValueError('native chain frame scope invalid')
            chains[chain['scene_id']]=chain
    rows = []; cursor = 0; identities = set()
    for clip in clips:
        allowed=set('clip_id scene_id budget narration_bindings generated source frame_mapping last_frame clip_sha256 observation_acceptance_sha256'.split())
        if native:allowed.add('temporal_chain')
        if not isinstance(clip,Mapping) or set(clip)-allowed: raise ValueError('unknown scene clip fields')
        budget = clip['budget']
        if (budget.get('protocol')=='longcat_native16_v1') is not native:raise ValueError('native budget requires exact schema4 index')
        mapping = scene_clip_frame_mapping(budget, actual_generated_frames=budget['generated_frames'])
        if native:
            if set(clip)!=allowed:raise ValueError('native source index requires complete clip fields')
            chain=chains.get(clip['scene_id']);receipt=clip['temporal_chain']
            if chain is None or not isinstance(receipt,Mapping) or set(receipt)!=set(('acceptance','source_frame_range')):
                raise ValueError('native clip must bind complete chain acceptance')
            a,z=chain['frame_range']
            if (not _same(receipt['acceptance'],chain['acceptance']) or clip['observation_acceptance_sha256']!=chain['acceptance']['sha256']
                    or not a<=budget['start_frame']<budget['end_frame']<=z
                    or not _same(receipt['source_frame_range'],[budget['start_frame']-a,budget['end_frame']-a])):
                raise ValueError('native clip contribution/complete playback scope differs')
        if (not _same(mapping, clip['frame_mapping']) or budget['start_frame'] != cursor
                or clip['clip_id'] != budget['clip_id'] or clip['scene_id'] != budget['scene_id']
                or clip['clip_id'] in identities): raise ValueError('exact ordered native mapping required')
        identities.add(clip['clip_id'])
        source = _artifact(clip['source'])
        if set(clip['source']) != set(source): raise ValueError('exact source Artifact required')
        for k, generated in enumerate(mapping['retained_to_generated']):
            rows.append(dict(frame_id=f'{clip["clip_id"]}:frame_{k+1:06d}',clip_id=clip['clip_id'],
                scene_id=clip['scene_id'],retained_frame_index=k,generated_frame_index=generated,
                output_frame_index=cursor+k,source=deepcopy(source)))
        cursor = budget['end_frame']
    if cursor != total: raise ValueError('retained frames must cover full timeline exactly')
    if native:
        scene_ids=list(dict.fromkeys(c['scene_id'] for c in clips))
        if list(chains)!=scene_ids:raise ValueError('native chain order/coverage differs')
        for sid in scene_ids:
            scoped=[c['budget'] for c in clips if c['scene_id']==sid]
            if not _same(chains[sid]['frame_range'],[scoped[0]['start_frame'],scoped[-1]['end_frame']]):
                raise ValueError('native chain must cover full scene contribution')
    return rows


def plan_scene_contributions(scene_clips, upscaled, timeline):
    rows = plan_scene_upscale(scene_clips)
    if not isinstance(upscaled,Mapping) or set(upscaled)-set('schema_version production_strategy run_id inputs_sha256 scene_clips_sha256 timeline_sha256 total_frames width height fps frames'.split()):
        raise ValueError('unknown upscale complete fields')
    if type(timeline.total_frames) is not int or timeline.total_frames != len(rows): raise ValueError('timeline differs')
    if type(upscaled.get('total_frames')) is not int or upscaled['total_frames'] != len(rows): raise ValueError('upscale count differs')
    frames = upscaled.get('frames')
    if not isinstance(frames, (list,tuple)) or len(frames) != len(rows): raise ValueError('complete upscale frames required')
    result = []
    for row, frame in zip(rows, frames):
        if not isinstance(frame,Mapping) or set(frame)-set('schema_version production_strategy run_id frame_id request_sha256 submission_sha256 mapping input input_copy model_output output evidence created_at'.split()):
            raise ValueError('unknown technical frame fields')
        mapping = {k:v for k,v in row.items() if k != 'source'}
        if frame.get('frame_id') != row['frame_id'] or not _same(frame.get('mapping'), mapping): raise ValueError('upscale mapping differs')
        image = _artifact(frame['output'])
        if set(frame['output']) != set(image): raise ValueError('exact output Artifact required')
        result.append(dict(**{k:row[k] for k in ('output_frame_index','scene_id','clip_id','retained_frame_index','generated_frame_index')},
            upscale_frame_sha256=canonical_digest(frame),image=deepcopy(image)))
    return result
