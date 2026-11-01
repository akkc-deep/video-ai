"""Experimental RGB controls with separate source and display coordinates."""
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path

from ._continuity_schema import ALGORITHM,DETECTORS,stable,rect,identity,validate_regions,validate_context,array
from ._continuity_geometry import numerical,frame_arrays,transform_box
from .colorimetry import ColorAnalysisReader,_object,_int
from ..planning.production_scenes import canonical_digest
from ..runtime.manifest import now


def _control_image_budget(pixels,packed_bytes, *, camera,local):
    raw=3*pixels
    # Reserve a 32MiB opposite raw frame plus the core's 32MiB gray LRU.
    # RGB input/output/bytes and both float32 warp-support arrays can overlap
    # in lifetime. Reject before creating those arrays, including mask storage.
    peak=3*raw+(pixels if local else 0)
    if camera:peak=max(peak,2*raw+8*pixels)
    if 67108864+packed_bytes+peak>201326592:raise ValueError('resource_limit: control peak image allocation')


def _truth(source,truth,reader,entries,regionids):
    _object(truth,'schema_version author reviewed_at samples'.split(),'truth')
    from ._continuity_schema import text
    from ..runtime.manifest import _timestamp
    if type(truth['schema_version']) is not int or truth['schema_version']!=1:raise ValueError('invalid truth version')
    text(truth['author']);_timestamp(truth['reviewed_at']);byframe={}
    for row in array(truth['samples']):
        _object(row,('frame','regions'),'truth sample');reader.check(row['frame']);key=row['frame']['path']
        if key not in entries or key in byframe:raise ValueError('unknown/duplicate truth frame')
        rs={}
        for r in array(row['regions']):
            _object(r,'region_id box visibility mask'.split(),'truth region');rect(r['box'])
            if r['region_id'] not in regionids or r['region_id'] in rs or r['visibility'] not in ('visible','partial','occluded'):raise ValueError('invalid truth region')
            if r['mask'] is not None:reader.check(r['mask'])
            rs[r['region_id']]=deepcopy(r)
        if set(rs)!=set(regionids):raise ValueError('truth must cover every declared region')
        byframe[key]=rs
    if set(byframe)!=set(entries):raise ValueError('truth must cover every original frame')
    return byframe


def build_control_case(source,variant, *, reader,truth):
    if not isinstance(reader,ColorAnalysisReader) or reader._closed:raise ValueError('control requires an open verified ColorAnalysisReader')
    from .continuity_calibration import _source_recipe
    entries={r['record_identity']['path']:r for r in reader.frames}
    entries={r['path']:entries[r['path']] for r in source['frame_records']}
    for i in source['frame_records']:reader.check(i)
    reader.check(source['media']);reader.check(source['truth']);reader.check(source['regions'])
    bypath={p:dict(frame_id=f'source_frame_{i}',record=r['record_identity']) for i,(p,r) in enumerate(entries.items())}
    region_doc=reader._json(Path(source['regions']['path']));regions=validate_regions(region_doc,bypath)
    truth_byframe=_truth(source,truth,reader,entries,{r['region_id'] for r in regions})
    source_records=list(entries.values());n=len(source_records)
    recipe=_source_recipe(source,variant,n,[r['region_id'] for r in regions if r['role']=='subject'])
    for target in source.get('control_targets',{}).values():reader.check(target['authorization'])
    for row in source_records:
        record=row['record']
        if record['status']!='ready' or record['source']['sha256']!=source['media']['sha256']:
            raise ValueError('controls require ready frames from the declared source media')
    tb=source_records[0]['record']['time_base'];start=source_records[0]['record']['pts']
    if tb is None or start is None:raise ValueError('control requires reliable original source time')
    for a,b in zip(source_records,source_records[1:]):
        ar,br=a['record'],b['record']
        if br['frame_index']!=ar['frame_index']+1 or br['time_base']!=tb or br['pts']<=ar['pts']:
            raise ValueError('control source frames must be consecutive with ordered original PTS')
    h=n//2;source_indices=[i if variant!='motion_reset' or i<h else i-h for i in range(n)]
    display=[];frames=[]
    for i,si in enumerate(source_indices):
        row=source_records[si];rec=row['record'];fid=f'display_{i}'
        display_pts=source_records[i]['record']['pts']-start
        display.append(dict(frame_id=fid,source_frame_id=f'source_frame_{si}',display_index=i,display_pts=display_pts,display_time_base=tb,transform_index=i))
        frames.append(dict(frame_id=fid,source_record=row['record_identity'],source_clip_id=(rec['mapping'] or {}).get('clip_id'),
            source_frame_index=rec['frame_index'],source_pts=rec['pts'],source_time_base=rec['time_base'],display_pts=display_pts,
            display_time_base=tb,output_frame_index=None))
    ref=deepcopy(frames[0]);ref.update(frame_id='reference_origin');frames.append(ref)
    cuts=[0,n//3,2*n//3,n] if variant=='cumulative_drift' else [0,h,n]
    clips=[dict(clip_id=f'experiment_{i}',frames=[f'display_{j}' for j in range(a,b)]) for i,(a,b) in enumerate(zip(cuts,cuts[1:]))]
    for clip in clips:
        for fid in clip['frames']:next(f for f in frames if f['frame_id']==fid)['source_clip_id']=clip['clip_id']
    comparisons=[];regionids=[r['region_id'] for r in regions]
    for i in range(n-1):
        comparisons.append(dict(comparison_id=f'pair_{i}',kind='parent_join' if i+1 in cuts[1:-1] else 'adjacent',
            left=f'display_{i}',right=f'display_{i+1}',region_ids=regionids))
    for i in range(n):comparisons.append(dict(comparison_id=f'reference_{i}',kind='reference',left='reference_origin',right=f'display_{i}',region_ids=regionids))
    anchors=[]
    for r in regions:
        aa=[]
        for i in [*cuts[:-1],None]:
            si=source_indices[i] if i is not None else 0;record=source_records[si];fid=f'display_{i}' if i is not None else 'reference_origin'
            box=truth_byframe[record['record_identity']['path']][r['region_id']]['box']
            if i is not None:
                scale=recipe['scale'][i];tx=recipe['translation_x'][i]
                np,_=numerical();a=np.array([[scale,0,(1-scale)/2+tx],[0,scale,(1-scale)/2]])
                box=transform_box(box,a)
                # Input anchors must be normalized and in-frame; the logical
                # tracked boxes later remain unclipped.
                box=[max(0.,box[0]),max(0.,box[1]),min(1.,box[2]),min(1.,box[3])]
            aa.append(dict(frame_id=fid,rect=box))
        anchors.append(dict(r,anchors=aa))
    context=None
    if source['context'] is not None:
        reader.check(source['context']);context=reader._json(Path(source['context']['path']))
        original=validate_context(context,{v['frame_id'] for v in bypath.values()},regionids)
        events=[]
        for event in original['events']:
            e=deepcopy(event);e['frame_ids']=[d['frame_id'] for d in display if d['source_frame_id'] in e['frame_ids']]
            if e['frame_ids']:events.append(e)
        context=dict(original,events=events)
    if variant in ('allowed_lighting','allowed_camera','occlusion'):
        kind={'allowed_lighting':'lighting','allowed_camera':'camera','occlusion':'occlusion'}[variant]
        detectors=list(DETECTORS[:4]) if kind=='lighting' else ['camera_jump'] if kind=='camera' else list(DETECTORS)
        affected=[d['frame_id'] for d in display]
        if kind=='occlusion':affected=affected[recipe['occlusion_interval'][0]:recipe['occlusion_interval'][1]]
        event=dict(event_id='control_change',kind=kind,frame_ids=affected,region_ids=regionids if kind!='occlusion' else recipe['local_region_ids'],
            detector_ids=detectors,description='Recorded experimental construction; human labels remain independent',references=[source['truth']])
        if kind=='occlusion' and variant in source.get('control_targets',{}):
            event['references'].append(source['control_targets'][variant]['authorization'])
            event['description']+='; explicit subject subset authorized before pixel construction'
        context=context or dict(schema_version=1,author='control_constructor',reviewed_at=now(),events=[])
        context['events'].append(event)
    input_digest=canonical_digest(stable(dict(source=source,records=[r['record_identity'] for r in source_records])))
    control=dict(schema_version=1,case_id=f'{source["source_id"]}_{variant}',source_id=source['source_id'],scene_group=source['scene_group'],
        split=None,variant=variant,base_input_sha256=input_digest,recipe=recipe,display_map=display,clips=clips,references=['reference_origin'],
        comparisons=comparisons,anchors=anchors,context=context,padding_masks=[None]*n,truth=source['truth'],created_at=now())
    plan=dict(schema_version=1,algorithm=ALGORITHM,purpose='benchmark_control',domain={k:source[k] for k in ('genre','source_kind')},
        frames=frames,clips=clips,references=['reference_origin'],regions=anchors,comparisons=comparisons,context=context,
        provenance=dict(kind='benchmark_control',input_sha256=input_digest,source_files=reader.identities,control_case=None))
    provider=ControlProvider(reader,source_records,source_indices,recipe,truth_byframe,plan)
    return control,provider


class ControlProvider:
    def __init__(self,reader,records,indices,recipe,truth,plan):
        self.reader=reader;self.records=records;self.indices=indices;self.recipe=recipe;self._truth=truth;self.plan=plan
        self.sidecars=reader.sidecars
        # Finish the truth-dependent reads in the construction phase. Packed
        # masks are bounded independently of the number of source frames.
        self._masks={};self._mask_bytes=0
        for row in records:
            video=self.sidecars[row['record']['sidecar']['path']]['probe']['video']
            for region in truth[row['record_identity']['path']].values():
                if region['mask'] is None:continue
                key=region['mask']['path']
                if key in self._masks:continue
                data=self._load_mask(region['mask'],video['width'],video['height'])
                np,_=numerical();packed=np.packbits(data,bitorder='little').tobytes()
                # Reserve 160MiB for the two raw frames, control construction
                # temporaries, and numerical core's 32MiB gray LRU.
                if self._mask_bytes+len(packed)>33554432:raise ValueError('resource_limit: packed control masks')
                self._masks[key]=(packed,video['width'],video['height']);self._mask_bytes+=len(packed)

    def get(self,frame_id):
        np,cv=numerical();reference=frame_id=='reference_origin';i=0 if reference else int(frame_id.removeprefix('display_'))
        si=0 if reference else self.indices[i];row=self.records[si];rec=row['record']
        video=self.sidecars[rec['sidecar']['path']]['probe']['video'];w,h=video['width'],video['height']
        if w*h*3>33554432:raise ValueError('resource_limit: control RGB')
        if not reference:_control_image_budget(w*h,self._mask_bytes,camera=self.recipe['scale'][i]!=1. or self.recipe['translation_x'][i]!=0.,local=self.recipe['variant']=='local_color')
        raw=self.reader.read_rgb(row['record_identity']['path'])
        if raw is None:return None
        image=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,3)
        if reference:return dict(width=w,height=h,rgb24=raw,valid_mask=None)
        result=image.copy();recipe=self.recipe;truth=self._truth[row['record_identity']['path']]
        local=recipe['variant']=='local_color';color_mask=None
        if local:
            color_mask=np.zeros((h,w),dtype=bool)
            for rid in recipe['local_region_ids']:color_mask|=self._region_mask(truth[rid],w,h)
        factors=[recipe[f'linear_{c}_factors'][i] for c in 'rgb']
        # Row tiles bound float intermediates independently of image dimensions.
        for y in range(0,h,max(1,65536//w)):
            stop=min(h,y+max(1,65536//w))
            for channel,factor in enumerate(factors):
                if factor==1.:continue
                u=image[y:stop,:,channel].astype(np.float64)/255
                linear=np.where(u<=.04045,u/12.92,((u+.055)/1.055)**2.4)
                linear=np.clip(linear*factor,0,1)
                encoded=np.where(linear<=.0031308,linear*12.92,1.055*linear**(1/2.4)-.055)
                values=np.rint(np.clip(encoded,0,1)*255).astype(np.uint8)
                if color_mask is None:result[y:stop,:,channel]=values
                else:np.copyto(result[y:stop,:,channel],values,where=color_mask[y:stop])
        interval=recipe['occlusion_interval']
        if interval and interval[0]<=i<interval[1]:
            for rid in recipe['local_region_ids']:
                x0,y0,x1,y1=truth[rid]['box'];y1=(y0+y1)/2
                result[math.floor(y0*h):math.ceil(y1*h),math.floor(x0*w):math.ceil(x1*w)]=128
        scale=recipe['scale'][i];tx=recipe['translation_x'][i];mask=None
        if scale!=1. or tx!=0.:
            a=np.float64([[scale,0,(1-scale)*(w-1)/2+tx*w],[0,scale,(1-scale)*(h-1)/2]])
            result=cv.warpAffine(result,a,(w,h),flags=cv.INTER_LINEAR,borderMode=cv.BORDER_CONSTANT,borderValue=0)
            support=cv.warpAffine(np.ones((h,w),dtype=np.float32),a,(w,h),flags=cv.INTER_LINEAR,borderMode=cv.BORDER_CONSTANT,borderValue=0)
            mask=support==1.
        return dict(width=w,height=h,rgb24=result.tobytes(),valid_mask=mask)

    def _region_mask(self,region,w,h):
        np,cv=numerical();mask=region['mask']
        if mask is None:
            result=np.zeros((h,w),dtype=bool);x0,y0,x1,y1=region['box']
            result[math.floor(y0*h):math.ceil(y1*h),math.floor(x0*w):math.ceil(x1*w)]=True
            return result
        packed,mw,mh=self._masks[mask['path']]
        if (mw,mh)!=(w,h):raise ValueError('truth mask dimensions differ')
        return np.unpackbits(np.frombuffer(packed,dtype=np.uint8),count=w*h,bitorder='little').reshape(h,w).astype(bool)

    def _load_mask(self,mask,w,h):
        np,cv=numerical();self.reader.check(mask)
        # Exact PNG metadata and bounded dimensions checked before decoder allocation.
        from .colorimetry import _png_metadata
        import struct
        path=Path(mask['path']);_png_metadata(path)
        with path.open('rb') as file:header=file.read(29)
        if header[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',header[16:24])!=(w,h) or header[24:26]!=bytes((8,0)):
            raise ValueError('truth mask must be original-sized single-channel 8-bit PNG')
        data=cv.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),cv.IMREAD_UNCHANGED)
        if data is None or data.shape!=(h,w):raise ValueError('invalid truth mask')
        return data!=0

    def release(self,frame_id):pass
