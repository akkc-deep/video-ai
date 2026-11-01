"""Pure v1 contracts. No optional numerical imports or filesystem reads."""
from copy import deepcopy
import math
import re
from fractions import Fraction
from pathlib import Path

from .colorimetry import _object, _int
from ..runtime.manifest import _identity, _timestamp
from ..runtime.paths import RUNTIME_ROOT, _validate_spelling

ALGORITHM='continuity_cv_v1'
DETECTORS=('seam_color','local_color','color_drift','cumulative_color','motion_reset','camera_jump')
GENRES=('people','animals','transport','outdoor','indoor','animation')
KINDS=('same_frame','adjacent','parent_join','reference')
PARAMETERS={
 'geometry': {
  'coordinates': 'normalized_affine_nn_patch_v1', 'thumbnail_long_edge': 256,
  'minimum_image_size': [32,32],
  'features': {'maxCorners':256,'qualityLevel':.01,'minDistance':4,'blockSize':7,'useHarrisDetector':False},
  'flow': {'winSize':[21,21],'maxLevel':3,'criteria':[3,30,.01],'flags':0,'minEigThreshold':1e-4},
  'matching': {'max_fb_error':1.,'patch_size':9,'min_ncc':.85,'min_points':12,
   'grid_size':[4,4],'min_grid_cells':4,'min_overlap':.35,'min_sample_pairs':81},
  'affine': {'model':'full_affine_irls','iterations':5,'huber_delta':1.5,
   'max_residual':2.,'max_condition':1e6,'det_range':[.5,2.]}
 },
 'color': {'input_space':'srgb_rgb24_v1','flow_luma':[.2126,.7152,.0722],
  'srgb_cutoff':.04045,'srgb_divisor':12.92,'srgb_offset':.055,'srgb_scale':1.055,'srgb_gamma':2.4,
  'xyz':[[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]],
  'white':[.95047,1.,1.08883],'lab_delta':6/29,'luma_epsilon':1/65535,'delta_e':'CIE76'},
 'windows': {'baseline_seconds':.5,'minimum_pairs':3,'minimum_reference_pairs_per_clip':3,
  'minimum_cumulative_clips':3,'quantile':.9,'motion_epsilon':1e-6},
 'resources': {'max_raw_bytes':33554432,'max_feature_cache_bytes':134217728,
  'max_image_bytes':201326592,'max_json_bytes':16777216,'max_metadata_bytes':67108864,
  'max_frames':4096,'max_comparisons':65536}
}


def text(value,label='text'):
    if type(value) is not str or not value.strip():raise ValueError(f'{label}: nonempty text required')
    return value


def identifier(value):
    if type(value) is not str or not re.fullmatch('[a-z][a-z0-9_]*',value):raise ValueError('ASCII identifier required')
    return value


def array(value,label='array', *, nonempty=False):
    if type(value) is not list or (nonempty and not value):raise ValueError(f'{label}: list required')
    return value


def identity(value):
    _identity(value)
    if any(value[k] is None for k in ('bytes','mtime_ns','sha256','verified_at')):raise ValueError('complete FileIdentity required')
    p=Path(_validate_spelling(value['path']))
    if not p.is_relative_to(RUNTIME_ROOT) or any(v in ('.','..') for v in re.split(r'[/\\]',value['path'])):
        raise ValueError('explicit local D:/VideoSi identity required')
    return value


def finite(value):
    if type(value) not in (float,int) or not math.isfinite(value):raise ValueError('finite non-boolean number required')
    return value


def rect(value, *, bounded=True):
    if type(value) is not list or len(value)!=4:raise ValueError('rectangle requires four coordinates')
    for v in value:finite(v)
    x0,y0,x1,y1=value
    if x0>=x1 or y0>=y1 or (bounded and not (0<=x0<x1<=1 and 0<=y0<y1<=1)):
        raise ValueError('invalid normalized rectangle')
    return value


def timebase(value):
    if type(value) is not str or not re.fullmatch('[0-9]+/[0-9]+',value):raise ValueError('positive rational time base required')
    try:r=Fraction(value)
    except (ValueError,ZeroDivisionError) as exc:raise ValueError('invalid time base') from exc
    if r<=0:raise ValueError('positive time base required')
    return r


def stable(value):
    if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in ('verified_at','created_at')}
    if isinstance(value,list):return [stable(v) for v in value]
    return value


def validate_continuity_manifest(manifest):
    _object(manifest,'schema_version algorithm scope scene_id domain timeline clips references regions comparisons context profile'.split(),'manifest')
    if type(manifest['schema_version']) is not int or manifest['schema_version']!=1 or manifest['algorithm']!=ALGORITHM:
        raise ValueError('unsupported continuity schema/algorithm')
    if manifest['scope'] not in ('clip','scene'):raise ValueError('invalid scope')
    identifier(manifest['scene_id']);domain(manifest['domain'])
    _object(manifest['timeline'],('fps_num','fps_den'),'timeline')
    for value in manifest['timeline'].values():_int(value,'fps',1)
    clips=array(manifest['clips'],nonempty=True);refs=array(manifest['references'])
    ids=set();physical=set();clipids=set()
    def frame(row):
        _object(row,('frame_id','record'),'frame');identifier(row['frame_id']);identity(row['record'])
        if row['frame_id'] in ids or row['record']['path'] in physical:raise ValueError('duplicate frame identity')
        ids.add(row['frame_id']);physical.add(row['record']['path'])
        if len(ids)>4096:raise ValueError('resource_limit: frames')
    for clip in clips:
        _object(clip,('clip_id','frames'),'clip');identifier(clip['clip_id'])
        if clip['clip_id'] in clipids:raise ValueError('duplicate clip ID')
        clipids.add(clip['clip_id'])
        for row in array(clip['frames'],nonempty=True):frame(row)
    for row in refs:frame(row)
    identity(manifest['regions'])
    for key in ('context','profile'):
        if manifest[key] is not None:identity(manifest[key])
    pairs=array(manifest['comparisons'])
    if len(pairs)>65536:raise ValueError('resource_limit: comparisons')
    seen=set()
    for row in pairs:
        _object(row,'comparison_id kind left right region_ids'.split(),'comparison');identifier(row['comparison_id'])
        if row['comparison_id'] in seen:raise ValueError('duplicate comparison ID')
        seen.add(row['comparison_id'])
        if row['kind'] not in KINDS or row['left'] not in ids or row['right'] not in ids:raise ValueError('unknown comparison/frame')
        if row['left']==row['right'] and row['kind']!='same_frame':raise ValueError('duplicate timepoint')
        regions=array(row['region_ids'],nonempty=True)
        if len(set(regions))!=len(regions):raise ValueError('duplicate comparison region')
        for r in regions:identifier(r)
    return deepcopy(manifest)


def domain(value, *, unspecified=True):
    _object(value,('genre','source_kind'),'domain')
    if value['genre'] not in (*GENRES, *(('unspecified',) if unspecified else ())):raise ValueError('unknown genre')
    if value['source_kind'] not in ('captured','generated','animation', *(('unspecified',) if unspecified else ())):raise ValueError('unknown source kind')


def validate_regions(value, records):
    _object(value,'schema_version author reviewed_at regions'.split(),'regions')
    if type(value['schema_version']) is not int or value['schema_version']!=1:raise ValueError('invalid regions version')
    text(value['author']);_timestamp(value['reviewed_at']);seen=set();result=[]
    for r in array(value['regions'],nonempty=True):
        _object(r,'region_id role identity_note anchors'.split(),'region');identifier(r['region_id']);text(r['identity_note'])
        if r['region_id'] in seen or r['role'] not in ('subject','background'):raise ValueError('invalid/duplicate region')
        seen.add(r['region_id']);anchors=[];anchored=set()
        for a in array(r['anchors'],nonempty=True):
            _object(a,('frame','rect'),'anchor');identity(a['frame']);rect(a['rect'])
            key=a['frame']['path']
            if key not in records or key in anchored:raise ValueError('unknown/duplicate anchor frame')
            if stable(a['frame'])!=stable(records[key]['record']):raise ValueError('anchor identity differs')
            anchored.add(key);anchors.append(dict(frame_id=records[key]['frame_id'],rect=a['rect']))
        result.append(dict(r,anchors=anchors))
    return result


def validate_context(value, frames, regions):
    if value is None:return None
    _object(value,'schema_version author reviewed_at events'.split(),'context')
    if type(value['schema_version']) is not int or value['schema_version']!=1:raise ValueError('invalid context version')
    text(value['author']);_timestamp(value['reviewed_at']);seen=set()
    for e in array(value['events']):
        _object(e,'event_id kind frame_ids region_ids detector_ids description references'.split(),'event')
        identifier(e['event_id']);text(e['description'])
        if e['event_id'] in seen:raise ValueError('duplicate context event')
        seen.add(e['event_id'])
        if e['kind'] not in ('lighting','camera','occlusion','content_change','appearance_change'):raise ValueError('invalid context kind')
        for key,allowed in (('frame_ids',frames),('region_ids',regions),('detector_ids',DETECTORS)):
            items=array(e[key],nonempty=True)
            if len(set(items))!=len(items) or any(x not in allowed for x in items):raise ValueError('unknown/duplicate scoped context ID')
        if e['kind']=='lighting' and any(d not in DETECTORS[:4] for d in e['detector_ids']):raise ValueError('lighting may only scope color detectors')
        if e['kind']=='camera' and e['detector_ids']!=['camera_jump']:raise ValueError('camera may only scope camera_jump')
        for ref in array(e['references'],nonempty=True):identity(ref)
    return deepcopy(value)
