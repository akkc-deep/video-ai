"""Strict production extraction and individual model-frame records."""
import re

from ..config import read_json
from ..planning.upscale import PARAMETERS
from .production_state import ArtifactStamp, ProductionRefused, object_fields, integer, run_path, json_bytes
from .production_visual_records import _id, submission, same
from .production_composition_records import command, local_stamp

MAPPING_FIELDS=('shot_id','coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame',
    'native_fps','output_fps','source_frames','upscaled_frames','source_to_upscaled','output_to_upscaled')
FRAME_FIELDS=('frame_index','source_frame_index','input','input_copy','output','submission','checkpoint_path')
FRAME_CHECKPOINT_FIELDS=('shot_id','frame_index','source_frame_index','source','parameters','input','input_copy',
    'output','model_output','submission','media_evidence_paths')


def _frame(row,run,ordinal):
    integer(row['frame_index'],'frame index',1);integer(row['source_frame_index'],'source frame index')
    if row['frame_index']!=ordinal or row['source_frame_index']!=ordinal-1:
        raise ProductionRefused('one-based frame and zero-based source index differ')
    for key in ('input','input_copy','output'):local_stamp(row[key],run)
    submission(row['submission'],run)


def validate_upscale_checkpoint(uid,payload,run):
    if re.fullmatch(r'shot_[0-9]{4}_extract',uid):
        object_fields(payload,('shot_id','source','source_frames','width','height','frames','command'),'upscale extraction')
        _id(payload['shot_id'])
        if uid!=payload['shot_id']+'_extract':raise ProductionRefused('extraction identity differs')
        local_stamp(payload['source'],run)
        for key in ('source_frames','width','height'):integer(payload[key],key,1)
        if (payload['width'],payload['height']) not in ((768,432),(1280,720)):raise ProductionRefused('original extraction profile required')
        frames=payload['frames']
        if not isinstance(frames,list) or len(frames)!=payload['source_frames']:raise ProductionRefused('complete extraction sequence required')
        parents=set()
        for i,row in enumerate(frames,1):
            object_fields(row,('frame_index','source_frame_index','input'),'extracted frame')
            integer(row['frame_index'],'frame index',1);integer(row['source_frame_index'],'source frame index')
            if row['frame_index']!=i or row['source_frame_index']!=i-1:raise ProductionRefused('extracted frame sequence differs')
            stamp=local_stamp(row['input'],run);path=run_path(run,stamp.path)
            if path.name!=f'frame_{i:06d}.png':raise ProductionRefused('extracted frame filename differs')
            parents.add(path.parent)
        if len(parents)!=1:raise ProductionRefused('one extraction directory required')
        command(payload['command'],run)
    else:
        object_fields(payload,FRAME_CHECKPOINT_FIELDS,'upscale frame checkpoint')
        _id(payload['shot_id']);integer(payload['frame_index'],'frame index',1)
        if uid!=f'{payload["shot_id"]}:frame_{payload["frame_index"]:06d}':raise ProductionRefused('frame checkpoint identity differs')
        _frame(payload,run,payload['frame_index'])
        for key in ('source','model_output'):local_stamp(payload[key],run)
        object_fields(payload['parameters'],PARAMETERS,'upscale parameters')
        if not same(payload['parameters'],PARAMETERS):raise ProductionRefused('fixed real AI upscale parameters required')
        paths=payload['media_evidence_paths']
        if not isinstance(paths,list) or not paths:raise ProductionRefused('actual frame validation evidence required')
        for path in paths:run_path(run,path)
    json_bytes(payload)


def validate_upscale_report(payload,run):
    object_fields(payload,('clips','frame_mappings'),'upscale payload')
    clips,mappings=payload['clips'],payload['frame_mappings']
    if not isinstance(clips,list) or not clips or not isinstance(mappings,list) or len(clips)!=len(mappings):
        raise ProductionRefused('complete upscale clip/mapping coverage required')
    cursor=0
    for ordinal,(clip,mapping) in enumerate(zip(clips,mappings),1):
        object_fields(clip,('shot_id','source','upscaled_frames','frames'),'upscaled clip');_id(clip['shot_id'],ordinal)
        local_stamp(clip['source'],run);integer(clip['upscaled_frames'],'upscaled frames',1)
        n=clip['upscaled_frames'];object_fields(mapping,MAPPING_FIELDS,'upscale mapping')
        for key in MAPPING_FIELDS:
            if key not in ('shot_id','source_to_upscaled','output_to_upscaled'):integer(mapping[key],key)
        expected=dict(shot_id=clip['shot_id'],coverage_start_frame=cursor,coverage_end_frame=cursor+n,
            core_start_frame=cursor,core_end_frame=cursor+n,native_fps=16,output_fps=16,source_frames=n,
            upscaled_frames=n,source_to_upscaled=list(range(n)),output_to_upscaled=list(range(n)))
        if not same(mapping,expected):raise ProductionRefused('canonical native16 upscale mapping differs')
        frames=clip['frames']
        if not isinstance(frames,list) or len(frames)!=n:raise ProductionRefused('complete upscale frame prefix required')
        for i,row in enumerate(frames,1):
            object_fields(row,FRAME_FIELDS,'upscale report frame');_frame(row,run,i)
            uid=f'{clip["shot_id"]}:frame_{i:06d}'
            path=run_path(run,row['checkpoint_path'])
            if path!=run/f'logs/production/checkpoints/upscale/{uid.replace(":","_")}.json':
                raise ProductionRefused('actual Windows-safe frame checkpoint path required')
            from .production_state import validate_checkpoint
            cp=read_json(path);validate_checkpoint(cp,run,'upscale',uid)
            p=cp['payload']
            if p['source']!=clip['source'] or any(p[k]!=row[k] for k in FRAME_FIELDS if k!='checkpoint_path'):
                raise ProductionRefused('upscale report differs from actual frame checkpoint')
        cursor+=n
    json_bytes(payload)
