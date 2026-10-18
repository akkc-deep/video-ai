"""Strict visual report/checkpoint structures; runtime separately replays inputs."""
from dataclasses import fields
import json
import re
from uuid import UUID

from ..planning.source_clips import _budget,WAN_NEGATIVE
from ..planning.start_images import NEGATIVE,validate_dimensions
from ..planning.storyboard import (StoryboardSlot,SOURCE_FACT_FIELDS,validate_model_content,GROUNDED_POLICY)
from ..planning.production_timing import AutomaticSlotPlan
from ..planning.production_visual_plan import ProductionSourceClipPlan,production_frame_mapping
from .manifest import thaw
from .production_state import ArtifactStamp,ProductionRefused,object_fields,integer,string,run_path

VISUAL_FIELDS=('composition','camera_motion','action_start','action_end','image_prompt','video_prompt','entity_ids','visual_requirements')
SLOT_FIELDS=tuple(f.name for f in fields(StoryboardSlot))
IMAGE_FIELDS=('shot_id','primary_unit_id','parameters','image','submission')
CLIP_FIELDS=('shot_id','primary_unit_id','budget','parameters','start_image','generated','source','native_fps','generated_frames','source_frames','submission')


def same(a,b):return json.dumps(thaw(a),sort_keys=True,allow_nan=False)==json.dumps(thaw(b),sort_keys=True,allow_nan=False)


def submission(value,run):
    object_fields(value,('attempt_id','client_id','prompt_id','intent_path','response_paths'),'visual submission')
    for key in ('attempt_id','prompt_id'):
        string(value[key],key)
        try:
            if str(UUID(value[key]))!=value[key]:raise ValueError()
        except ValueError as exc:raise ProductionRefused('actual UUID submission required') from exc
    string(value['client_id'],'client_id');run_path(run,value['intent_path'])
    if not isinstance(value['response_paths'],list) or not value['response_paths']:raise ProductionRefused('actual response evidence required')
    for p in value['response_paths']:run_path(run,p)


def _id(value,ordinal=None):
    if not isinstance(value,str) or re.fullmatch(r'shot_[0-9]{4}',value) is None or ordinal is not None and value!=f'shot_{ordinal:04d}':
        raise ProductionRefused('fixed shot order required')


def image_row(row,run,ordinal=None):
    object_fields(row,IMAGE_FIELDS,'image row');_id(row['shot_id'],ordinal);string(row['primary_unit_id'],'primary unit')
    stamp=ArtifactStamp.from_dict(row['image']);run_path(run,stamp.path);submission(row['submission'],run)
    p=row['parameters'];names=('positive','negative','seed','width','height','steps','cfg','sampler','scheduler','denoise','batch')
    object_fields(p,names,'image parameters');string(p['positive'],'image positive')
    for k in ('seed','width','height','steps','batch'):integer(p[k],k)
    validate_dimensions(p['width'],p['height'])
    if (p['width'],p['height']) not in ((768,432),(1280,720)):raise ProductionRefused('supported image profile required')
    from ..planning.model_visual_prompts import MODEL_NEGATIVE_SUFFIX,VOYAGER_NEGATIVE_SUFFIX
    if p['negative'] not in (NEGATIVE,NEGATIVE+MODEL_NEGATIVE_SUFFIX,NEGATIVE+MODEL_NEGATIVE_SUFFIX+VOYAGER_NEGATIVE_SUFFIX):raise ProductionRefused('fixed image negative prompt differs')
    expected=dict(positive=p['positive'],negative=p['negative'],seed=812045847300606+int(row['shot_id'][5:])-1,
                  width=p['width'],height=p['height'],steps=25,cfg=7,sampler='dpmpp_2m',scheduler='karras',denoise=1,batch=1)
    if not same(p,expected):raise ProductionRefused('fixed image sampling parameters differ')


def clip_row(clip,mapping,run,ordinal=None):
    object_fields(clip,CLIP_FIELDS,'source clip');_id(clip['shot_id'],ordinal);string(clip['primary_unit_id'],'primary unit')
    for key in ('start_image','generated','source'):
        stamp=ArtifactStamp.from_dict(clip[key]);run_path(run,stamp.path)
    submission(clip['submission'],run)
    b=_budget(clip['budget'],clip['shot_id'],16)
    if (b['incoming_overlap_frames'] or b['outgoing_overlap_frames'] or b['core_start_frame']!=b['coverage_start_frame']
        or b['core_end_frame']!=b['coverage_end_frame']):raise ProductionRefused('production budget requires zero overlap')
    p=clip['parameters'];names=('positive','negative','seed_high','seed_low','width','height','length','fps','batch','steps','cfg','sampler','scheduler','split_step','shift_high','shift_low','lora_enabled')
    object_fields(p,names,'Wan parameters');string(p['positive'],'Wan positive')
    for k in ('seed_high','seed_low','width','height','length','fps','batch','steps','split_step'):integer(p[k],k)
    validate_dimensions(p['width'],p['height'])
    if (p['width'],p['height']) not in ((768,432),(1280,720)):raise ProductionRefused('supported Wan profile required')
    expected=dict(positive=p['positive'],negative=WAN_NEGATIVE,seed_high=264244520398999+int(clip['shot_id'][5:])-1,seed_low=0,
                  width=p['width'],height=p['height'],length=b['wan_frames'],fps=16,batch=1,steps=40,cfg=3.5,sampler='euler',scheduler='simple',
                  split_step=15,shift_high=5.000000000000001,shift_low=5.000000000000001,lora_enabled=False)
    if not same(p,expected):raise ProductionRefused('fixed Wan sampling parameters differ')
    for k in ('native_fps','generated_frames','source_frames'):integer(clip[k],k,1)
    if clip['native_fps']!=16 or clip['source_frames']!=b['required_native_frames']:raise ProductionRefused('source frame count/rate differs')
    plan=ProductionSourceClipPlan(clip['shot_id'],clip['primary_unit_id'],b,p,ArtifactStamp.from_dict(clip['start_image']))
    if not same(mapping,production_frame_mapping(plan,generated_frames=clip['generated_frames'])):raise ProductionRefused('frame mapping differs from canonical retained prefix')


def storyboard(payload):
    object_fields(payload,('global_visual','effective_media','shots','transitions'),'storyboard')
    media=payload['effective_media'];object_fields(media,('fps','native_fps','profile','image_aspect_ratio','default_image_width','default_image_height','transition','transition_seconds'),'effective media')
    profile=media['profile'];object_fields(profile,('name','width','height','native_fps'),'profile')
    for d in (media,profile):
        for k in ('fps','native_fps','width','height','default_image_width','default_image_height'):
            if k in d:integer(d[k],k,1)
    if ({'fast':(768,432),'quality':(1280,720)}.get(profile['name'])!=(profile['width'],profile['height'])
        or profile['native_fps']!=16 or media['fps']!=16 or media['native_fps']!=16 or media['transition']!='cut'
        or type(media['transition_seconds']) not in (int,float) or media['transition_seconds']!=0 or media['image_aspect_ratio']!='16:9'
        or (media['default_image_width'],media['default_image_height']) not in ((profile['width'],profile['height']),(1280,720)) or payload['transitions']!=[]):raise ProductionRefused('unsupported effective media')
    rows=payload['shots']
    if not isinstance(rows,list) or not rows:raise ProductionRefused('fixed shots required')
    slot_rows=[];visuals=[];facts={};cursor=0
    for i,row in enumerate(rows,1):
        object_fields(row,(*SLOT_FIELDS,*VISUAL_FIELDS,'budget'),'storyboard shot');_id(row['shot_id'],i)
        slot_rows.append({k:row[k] for k in SLOT_FIELDS})
        visual={k:row[k] for k in ('shot_id',*VISUAL_FIELDS)};requirements=[]
        if not isinstance(row['visual_requirements'],list):raise ProductionRefused('visual requirements must be list')
        for j,req in enumerate(row['visual_requirements'],1):
            object_fields(req,('unit_id','source_quote',*SOURCE_FACT_FIELDS,'visual_expression','needs_finer_audio','requirement_id'),'visual requirement')
            if req['requirement_id']!=f'{row["shot_id"]}:req_{j:04d}':raise ProductionRefused('requirement ID differs')
            requirements.append({k:v for k,v in req.items() if k!='requirement_id'})
            f={k:req[k] for k in SOURCE_FACT_FIELDS}
            if req['unit_id'] in facts and not same(facts[req['unit_id']],f):raise ProductionRefused('source facts drift across shots')
            facts[req['unit_id']]=f
        visual['visual_requirements']=requirements;visuals.append(visual)
        b=_budget(row['budget'],row['shot_id'],16)
        expected_ids=list(dict.fromkeys(x['unit_id'] for x in row['bindings']))
        if (row['start_frame']!=cursor or b['core_start_frame']!=cursor or b['core_end_frame']!=row['end_frame']
            or b['coverage_start_frame']!=cursor or b['coverage_end_frame']!=row['end_frame']
            or b['incoming_overlap_frames'] or b['outgoing_overlap_frames'] or b['associated_unit_ids']!=expected_ids):raise ProductionRefused('fixed budget/binding coverage differs')
        cursor=row['end_frame']
    slots=AutomaticSlotPlan.from_dict(dict(slots=slot_rows,cuts=[])).slots
    # A silent-only binding still belongs to the source catalog; the runtime has
    # the complete frozen facts. Structural validation here keeps those entries.
    from ..planning.storyboard import source_catalog
    for uid in source_catalog(slots):
        if uid not in facts:facts[uid]=dict.fromkeys(SOURCE_FACT_FIELDS[:6],None)|dict(context_sources=[],resolved_references=[])
    validate_model_content(dict(schema_version=1,global_visual=payload['global_visual'],shots=visuals),slots,
                           semantic_specs=facts,depiction_policy=GROUNDED_POLICY)


def validate_visual_report(stage,payload,run):
    if stage=='storyboard':storyboard(payload)
    elif stage=='start_images':
        if not isinstance(payload['images'],list) or not payload['images']:raise ProductionRefused('images required')
        for i,row in enumerate(payload['images'],1):image_row(row,run,i)
    elif stage=='source_clips':
        clips,mappings=payload['clips'],payload['frame_mappings']
        if not isinstance(clips,list) or not clips or not isinstance(mappings,list) or len(clips)!=len(mappings):raise ProductionRefused('clip/mapping coverage differs')
        cursor=0
        for i,(clip,mapping) in enumerate(zip(clips,mappings),1):
            clip_row(clip,mapping,run,i)
            if clip['budget']['coverage_start_frame']!=cursor:raise ProductionRefused('clip gap/overlap')
            cursor=clip['budget']['coverage_end_frame']


def validate_visual_checkpoint(stage,uid,payload,run):
    if stage=='storyboard':
        if re.fullmatch(r'storyboard_batch_[0-9]{4}_(initial|correction|entityrepair)',uid) is None:raise ProductionRefused('invalid visual batch ID')
        object_fields(payload,('batch_id','shot_ids','format_valid','content','error'),'visual batch payload')
        if payload['batch_id']!=uid.rsplit('_',1)[0] or type(payload['format_valid']) is not bool:raise ProductionRefused('invalid visual batch identity/status')
        if not isinstance(payload['shot_ids'],list) or not 1<=len(payload['shot_ids'])<=8 or len(set(payload['shot_ids']))!=len(payload['shot_ids']):raise ProductionRefused('batch fixed shots required')
        for sid in payload['shot_ids']:_id(sid)
        if payload['format_valid']:
            if not isinstance(payload['content'],dict) or payload['error'] is not None:raise ProductionRefused('valid visual content required')
        elif payload['content'] is not None or not isinstance(payload['error'],str) or not payload['error']:raise ProductionRefused('invalid batch requires format diagnostic')
    elif stage=='start_images':image_row(payload,run)
    elif stage=='source_clips':
        object_fields(payload,('clip','frame_mapping','input_copy','media_evidence_paths'),'source checkpoint')
        clip_row(payload['clip'],payload['frame_mapping'],run)
        stamp=ArtifactStamp.from_dict(payload['input_copy']);run_path(run,stamp.path)
        if not isinstance(payload['media_evidence_paths'],list) or not payload['media_evidence_paths']:raise ProductionRefused('actual media evidence required')
        for p in payload['media_evidence_paths']:run_path(run,p)
