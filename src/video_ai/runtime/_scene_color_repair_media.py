"""Bounded native-frame repair and fixed CPU encodes with ordinary audit evidence."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import math
import os
from pathlib import Path
import shutil
from uuid import uuid4

from .manifest import thaw,hash_file
from .production_state import ProductionRefused,object_fields,integer
from ._scene_continuity_io import artifact,verify,local
from ._scene_color_repair_validation import remaining,validate_native

MASTER_FILTER='zscale=matrixin=gbr:transferin=iec61966-2-1:primariesin=bt709:rangein=full:matrix=bt709:transfer=iec61966-2-1:primaries=bt709:range=full:dither=none,format=yuv444p'
PLAYBACK_FILTER='zscale=matrixin=bt709:transferin=iec61966-2-1:primariesin=bt709:rangein=full:matrix=bt709:transfer=bt709:primaries=bt709:range=limited:dither=none,format=yuv420p'
RECIPE=dict(master=dict(filter=MASTER_FILTER,codec='libx264',crf=0,preset='medium',pix_fmt='yuv444p',
    color_primaries='bt709',color_trc='iec61966-2-1',colorspace='bt709',color_range='pc',
    bitstream_filter='h264_metadata=colour_primaries=1:transfer_characteristics=13:matrix_coefficients=1:video_full_range_flag=1'),
    playback=dict(filter=PLAYBACK_FILTER,codec='libx264',profile='high',crf=16,preset='medium',pix_fmt='yuv420p',
        color_primaries='bt709',color_trc='bt709',colorspace='bt709',color_range='tv'))


def frame_changes(before,after):
    """Measure all RGB channels with at most 65,536 pixels of temporaries."""
    import numpy as np
    for value in (before,after):
        if (not isinstance(value,np.ndarray) or value.dtype!=np.uint8 or value.ndim<2 or
                value.shape[-1]!=3 or not value.size or not value.flags.c_contiguous):
            raise ValueError('contiguous nonempty uint8 RGB required')
    if before.shape!=after.shape:raise ValueError('full-frame RGB shapes differ')
    source,target=before.reshape(-1,3),after.reshape(-1,3)
    clips=changed=maximum=0
    for start in range(0,len(source),65536):
        a,b=source[start:start+65536],target[start:start+65536]
        clips+=int(np.count_nonzero((a>=3)&(a<=252)&((b==0)|(b==255))))
        difference=np.subtract(b,a,dtype=np.int16)
        np.abs(difference,out=difference)
        changed+=int(np.count_nonzero(difference));maximum=max(maximum,int(difference.max()))
    return dict(new_clip=clips,changed_channels=changed,max_change=maximum)


def _finite(value,label,*,maximum=None):
    if (type(value) not in (int,float) or not math.isfinite(value) or value<0 or
            (maximum is not None and value>maximum)):
        raise ProductionRefused('repair '+label+' requires a finite nonnegative number')


def _measured_rows(rows,support,*,label):
    if type(rows) is not list or len(rows)!=len(support):raise ProductionRefused('repair '+label+' native coverage differs')
    total=0
    for i,(row,frame) in enumerate(zip(rows,support)):
        object_fields(row,'source_frame_index mae p99_error max_error new_clip'.split(),'repair '+label+' frame')
        if type(row['source_frame_index']) is not int or row['source_frame_index']!=i:
            raise ProductionRefused('repair '+label+' frame order differs')
        for key in ('mae','p99_error'):_finite(row[key],label+' '+key,maximum=255)
        for key in ('max_error','new_clip'):integer(row[key],'repair '+label+' '+key,0)
        if (row['max_error']>255 or row['new_clip']>frame['pairs']*3 or
                row['mae']>row['max_error'] or row['p99_error']>row['max_error']):
            raise ProductionRefused('repair '+label+' frame metrics contradict their ranges')
        total+=round(row['mae']*frame['pairs']*3)
    return total


def _improved_rows(before,after,support,*,label):
    before_total=_measured_rows(before,support,label=label+' before')
    after_total=_measured_rows(after,support,label=label+' after')
    for b,a in zip(before,after):
        if a['p99_error']>2 or a['max_error']>4 or a['new_clip']>b['new_clip'] or a['mae']>b['mae']:
            raise ProductionRefused('repair '+label+' frame residual or regression gate failed')
    if after_total>=before_total:raise ProductionRefused('repair '+label+' lacks strict aggregate improvement')
    return before_total,after_total


def _full_rows(rows,*,frames,channels,label):
    if type(rows) is not list or len(rows)!=frames:raise ProductionRefused('repair '+label+' native coverage differs')
    for i,row in enumerate(rows):
        object_fields(row,'source_frame_index new_clip changed_channels max_change parameter_delta'.split(),'repair '+label+' frame')
        if type(row['source_frame_index']) is not int or row['source_frame_index']!=i:
            raise ProductionRefused('repair '+label+' frame order differs')
        for key in ('new_clip','changed_channels','max_change'):integer(row[key],'repair '+label+' '+key,0)
        _finite(row['parameter_delta'],label+' parameter delta')
        if (row['new_clip']!=0 or row['parameter_delta']!=0 or row['changed_channels']>channels or
                row['max_change']>255 or (row['changed_channels']==0)!=(row['max_change']==0)):
            raise ProductionRefused('repair '+label+' clipping, change count or constant-parameter gate failed')


def validate_measured_checks(fit,full,decoded,*,candidate_id,frames,channels):
    """Validate saved measured arithmetic; never refit or trust a passed flag."""
    from .scene_color_repair_records import schema
    integer(frames,'repair measured frames',1);integer(channels,'repair measured channels',1)
    if frames>4096:raise ProductionRefused('resource_limit: repair measured frames')
    support=fit.get('frame_support')
    if type(support) is not list or len(support)!=frames:raise ProductionRefused('repair measured support incomplete')
    for i,row in enumerate(support):
        object_fields(row,'source_frame_index pairs informative_pairs'.split(),'repair measured support')
        if type(row['source_frame_index']) is not int or row['source_frame_index']!=i:
            raise ProductionRefused('repair measured support frame order differs')
        integer(row['pairs'],'repair measured pairs',81);integer(row['informative_pairs'],'repair measured informative pairs',0)
        if row['pairs']>2048 or row['informative_pairs']>row['pairs']:raise ProductionRefused('repair measured support exceeds sampling domain')
    schema(full,'schema_version candidate_id frames')
    schema(decoded,'schema_version candidate_id scores roundtrip_max full_frames temporal_error_differences')
    if full['candidate_id']!=candidate_id or decoded['candidate_id']!=candidate_id:
        raise ProductionRefused('repair measured candidate identity differs')
    _full_rows(full['frames'],frames=frames,channels=channels,label='intended full-frame')
    _full_rows(decoded['full_frames'],frames=frames,channels=channels,label='decoded full-frame')
    if (type(decoded['roundtrip_max']) is not list or len(decoded['roundtrip_max'])!=frames or
            any(type(value) is not int or not 0<=value<=2 for value in decoded['roundtrip_max'])):
        raise ProductionRefused('repair all-frame roundtrip budget invalid')
    temporal=decoded['temporal_error_differences']
    if type(temporal) is not list or len(temporal)!=frames-1:raise ProductionRefused('repair measured temporal coverage differs')
    for value in temporal:_finite(value,'temporal error difference')
    scores=decoded['scores'];object_fields(scores,'before after before_mae after_mae passed reasons'.split(),'repair decoded scores')
    if scores['passed'] is not True or type(scores['reasons']) is not list or scores['reasons']:
        raise ProductionRefused('repair decoded scores did not pass without reasons')
    totals=_improved_rows(scores['before'],scores['after'],support,label='decoded')
    denominator=sum(row['pairs']*3 for row in support)
    for key,total in zip(('before_mae','after_mae'),totals):
        _finite(scores[key],'decoded '+key,maximum=255)
        if not math.isclose(scores[key],total/denominator,rel_tol=1e-12,abs_tol=1e-12):
            raise ProductionRefused('repair decoded weighted aggregate contradicts frame metrics')
    if 'before' in fit or 'after' in fit:
        if 'before' not in fit or 'after' not in fit:raise ProductionRefused('repair fit scoring incomplete')
        _improved_rows(fit['before'],fit['after'],support,label='fit')
        if fit['before']!=scores['before']:raise ProductionRefused('repair fit and decoded original metrics differ')
    if 'reasons' in fit and (type(fit['reasons']) is not list or fit['reasons']):
        raise ProductionRefused('repair measured fit retains failure reasons')


def _write_last_frame(store,folder,image,*,reader):
    """Write sRGB PNG with bounded zlib/IDAT buffers instead of full scanlines."""
    import struct
    import zlib
    target=store.root/folder/'last-frame.png';local(target,exists=False)
    if target.exists():raise ProductionRefused('partial repair PNG retained; explicit new UUID required')
    temporary=target.with_name('last-frame.'+uuid4().hex+'.tmp');store.owned()
    with temporary.open('xb') as stream:
        def chunk(kind,data):
            stream.write(struct.pack('>I',len(data)));stream.write(kind);stream.write(data)
            stream.write(struct.pack('>I',zlib.crc32(data,zlib.crc32(kind))))
        h,w=image.shape[:2];stream.write(b'\x89PNG\r\n\x1a\n')
        chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0));chunk(b'sRGB',b'\0')
        compressor=zlib.compressobj()
        for row in image:
            reader.check();store.owned()
            data=compressor.compress(b'\0')
            if data:chunk(b'IDAT',data)
            with memoryview(row).cast('B') as pixels:
                for start in range(0,len(pixels),65536):
                    data=compressor.compress(pixels[start:start+65536])
                    if data:chunk(b'IDAT',data)
        data=compressor.flush()
        if data:chunk(b'IDAT',data)
        chunk(b'IEND',b'');stream.flush();os.fsync(stream.fileno())
    reader.check();store.owned();os.rename(temporary,target)
    return artifact(target)


def dimensions(video,count,*,run,reference_bytes=None):
    width,height=video['width'],video['height'];raw=width*height*3
    for v in (width,height,count):integer(v,'repair dimensions',1)
    if reference_bytes is None:reference_bytes=raw
    integer(reference_bytes,'repair reference RGB bytes',1)
    if count>4096 or max(raw,reference_bytes)>33554432 or 3*max(raw,reference_bytes)+count*2048*25+16777216>134217728:
        raise ProductionRefused('resource_limit: repair pixel working budget')
    disk=3*count*raw+536870912
    if disk>17179869184 or shutil.disk_usage(run).free<disk:raise ProductionRefused('resource_limit: repair disk budget')
    return width,height


def pair_pixels(manifest,report,*,config,reader):
    import numpy as np
    from ..media.colorimetry import load_color_analysis_set
    from ..media._continuity_geometry import numerical
    numerical()
    target=manifest['clips'][0]['frames'];reference=manifest['references'][0]
    comparisons={row['comparison_id']:row for row in report['comparisons']}
    region_source=reader.read({k:manifest['regions'][k] for k in ('path','bytes','sha256')})
    roles={region['region_id']:region['role'] for region in region_source['regions']}
    refs=[];currents=[];coordinates=[];support=[]
    with load_color_analysis_set([reference['record']['path']]+[f['record']['path'] for f in target],config=config,timeout=remaining(reader)) as colors:
        records=colors.frames;sidecars=colors.sidecars
        def rgb(frame):
            row=next(r for r in records if r['record_identity']['path']==frame['record']['path'])
            sc=sidecars[row['record']['sidecar']['path']];v=sc['probe']['video']
            raw=colors.read_rgb(frame['record']['path'])
            if raw is None:raise ProductionRefused('repair requires complete explicit sRGB frame support')
            return np.frombuffer(raw,np.uint8).reshape(v['height'],v['width'],3)
        clean=rgb(reference)
        for i,frame in enumerate(target):
            reader.check();key=f'repair_ref_{i:06d}';pair=comparisons.get(key)
            if pair is None or pair['kind']!='reference' or pair['left']!=reference['frame_id'] or pair['right']!=frame['frame_id']:
                raise ProductionRefused('repair pair report reference producer or complete coverage differs')
            points=set();role_points={}
            for region in pair['regions']:
                if region['comparability']!='comparable':return None,['incomparable_reference_frame:'+str(i)]
                rows=sorted({tuple(xy for point in p for xy in point) for p in region['geometry']['sampled_pairs']})
                role_points.setdefault(roles[region['region_id']],set()).update(rows)
            for rows in role_points.values():
                rows=sorted(rows)
                if len(rows)>1024:rows=[rows[j] for j in np.linspace(0,len(rows)-1,1024,dtype=int)]
                points.update(rows)
            points=sorted(points)
            if len(points)<81:return None,['insufficient_reference_pairs:'+str(i)]
            cur=rgb(frame);coords=np.asarray(points,dtype=np.int32)
            if ((coords<0).any() or (coords[:,0]>=clean.shape[1]).any() or (coords[:,1]>=clean.shape[0]).any() or
                    (coords[:,2]>=cur.shape[1]).any() or (coords[:,3]>=cur.shape[0]).any()):raise ProductionRefused('repair pair coordinates out of range')
            left=clean[coords[:,1],coords[:,0]].copy();right=cur[coords[:,3],coords[:,2]].copy()
            refs.append(left);currents.append(right);coordinates.append(coords)
            informative=int(np.count_nonzero(((left>=2)&(left<=253)&(right>=2)&(right<=253)).all(axis=1)))
            support.append(dict(source_frame_index=i,pairs=len(points),informative_pairs=informative))
    return dict(reference=refs,current=currents,coordinates=coordinates,frame_support=support),[]


def _command(store,folder,name,args,source,target,*,config,paths,logger,reader):
    from .processes import run_logged
    from .environment import build_child_env
    store.owned();local(target,exists=False)
    if target.exists():raise ProductionRefused('partial repair output retained; explicit new UUID required')
    result=run_logged(args,cwd=store.run_dir,env=build_child_env(paths),timeout=remaining(reader),logger=logger,stage='scene_color_repair',unit_id=folder.name)
    reader.check();store.owned()
    if result.returncode!=0 or result.timed_out:raise RuntimeError('repair command failed; retained stdout/stderr: '+str(result.stderr_path))
    receipt=dict(schema_version=1,command=thaw(result),source=source,target=artifact(target),tool=artifact(config.tools['ffmpeg'],runtime=False))
    return artifact(store.write(folder/(name+'-command.json'),receipt))


def inspect_candidate(store,folder,source,mapping,*,name,config,paths,reader):
    from .paths import create_run
    from .logging import RunLogger
    from ..media.colorimetry import inspect_color_asset,decode_analysis_frame
    audit=create_run(paths);log=RunLogger(audit)
    proof=store.write(folder/(name+'-mapping-proof.json'),dict(source=thaw(hash_file(source)),rows=mapping))
    entry=dict(asset_id=name,stage='retained',path=str(source),mapping=dict(rows=mapping,evidence=[thaw(hash_file(proof))]),
        processing=dict(operation='constant_color_repair_v1 '+name,upstream_ids=[],command_records=[]))
    sidecar,_=inspect_color_asset(entry,config=config,paths=paths,logger=log,timeout=remaining(reader))
    if sidecar['interpretation']['status']!='resolved':raise ProductionRefused('candidate color interpretation unknown')
    for i in range(len(mapping)):
        store.owned();reader.check()
        decode_analysis_frame(sidecar,frame_index=i,config=config,paths=paths,logger=log,timeout=remaining(reader))
    frames=[dict(frame_id=f'candidate_frame_{i:06d}',record=thaw(hash_file(log.root/f'colorimetry/{name}/analysis/frame_{i:06d}.json')))
        for i in range(len(mapping))]
    return sidecar,frames,audit


def render_media(store,folder,intent,fit,manifest,pairs,*,config,paths,logger,reader,boundary):
    import numpy as np
    from ..media.colorimetry import load_color_analysis_set
    from ..media.color_repair import apply_constant_repair,score_repair_pairs
    targets=manifest['clips'][0]['frames'];binding=intent['binding'];mapping=reader.read(binding['mapping'])
    with load_color_analysis_set([f['record']['path'] for f in targets],config=config,timeout=remaining(reader)) as colors:
        video=next(iter(colors.sidecars.values()))['probe']['video'];count=len(targets);pts=validate_native(video,count)
        w,h=dimensions(video,count,run=store.run_dir)
        source_raw=store.root/folder/'intended.rgb';temporary=source_raw.with_name('intended.'+uuid4().hex+'.tmp')
        hashes=[];full=[]
        with temporary.open('xb') as stream:
            for i,f in enumerate(targets):
                reader.check();store.owned();raw=colors.read_rgb(f['record']['path'])
                if raw is None:raise ProductionRefused('repair source frame is unverified')
                image=np.frombuffer(raw,np.uint8).reshape(h,w,3)
                changed=apply_constant_repair(image,operation=fit['operation'],amplitude=fit['amplitude'])
                measured=frame_changes(image,changed)
                full.append(dict(source_frame_index=i,**measured,parameter_delta=0.))
                if measured['new_clip']:raise RuntimeError('repair introduces whole-frame clipping')
                with memoryview(changed).cast('B') as data:
                    hashes.append(hashlib.sha256(data).hexdigest());stream.write(data)
                del data,image,changed,raw
            stream.flush();os.fsync(stream.fileno())
        store.owned();os.rename(temporary,source_raw)
        full_record=dict(schema_version=1,candidate_id=intent['candidate_id'],frames=full)
        full_ref=artifact(store.write(folder/'full-frame-checks.json',full_record))
        boundary('intended-rgb')
    master=store.root/folder/'master.mp4'
    args=[str(config.tools['ffmpeg']),'-nostdin','-n','-v','error','-threads','1','-f','rawvideo','-pixel_format','rgb24',
        '-video_size',f'{w}x{h}','-framerate','16','-i',str(source_raw),'-filter_threads','1','-vf',MASTER_FILTER,
        '-c:v','libx264','-crf','0','-preset','medium','-threads','1','-pix_fmt','yuv444p','-an',
        '-color_primaries','bt709','-color_trc','iec61966-2-1','-colorspace','bt709','-color_range','pc',
        '-bsf:v',RECIPE['master']['bitstream_filter'],str(master)]
    command=_command(store,folder,'master',args,artifact(source_raw),master,config=config,paths=paths,logger=logger,reader=reader)
    boundary('master-encoded')
    # Native mapping is measured first; no presumed muxer time base enters proof.
    from .processes import run_logged
    from .environment import build_child_env
    probe=run_logged([str(config.tools['ffprobe']),'-v','error','-select_streams','v:0','-show_streams','-show_frames','-of','json',str(master)],
        cwd=store.run_dir,env=build_child_env(paths),timeout=remaining(reader),logger=logger,stage='repair_native_probe')
    if probe.returncode!=0 or probe.timed_out:raise RuntimeError('candidate native probe failed')
    probe_json=reader.read(Path(probe.stdout_path));stream=probe_json['streams'][0];tb=stream['time_base'];native=probe_json['frames']
    if len(native)!=count or any(type(f.get('pts')) is not int or f['pts']*Fraction(tb)!=Fraction(i,16) for i,f in enumerate(native)):
        raise RuntimeError('candidate native PTS or count differs')
    rows=[dict(asset_frame_index=i,clip_id=manifest['clips'][0]['clip_id'],generated_frame_index=mapping['retained_to_generated'][i],
        retained_frame_index=i,output_frame_index=mapping['start_frame']+i,pts=native[i]['pts'],time_base=tb) for i in range(count)]
    sidecar,frames,color_audit=inspect_candidate(store,folder,master,rows,name='master',config=config,paths=paths,reader=reader)
    validate_native(sidecar['probe']['video'],count)
    final_pairs=[];decoded_last=None;maxima=[];decoded_full=[];temporal=[];previous_mean=None
    with load_color_analysis_set([f['record']['path'] for f in frames+targets],config=config,timeout=remaining(reader)) as colors:
        with source_raw.open('rb') as intended:
            for i,f in enumerate(frames):
                reader.check();decoded=colors.read_rgb(f['record']['path'])
                if decoded is None:raise RuntimeError('candidate complete decode unavailable')
                rgb=np.frombuffer(decoded,np.uint8).reshape(h,w,3);want=intended.read(w*h*3)
                if len(want)!=w*h*3:raise RuntimeError('candidate intent RGB incomplete')
                intended_rgb=np.frombuffer(want,np.uint8).reshape(h,w,3)
                difference=frame_changes(intended_rgb,rgb)['max_change']
                if difference>2:raise RuntimeError('RGB encoding roundtrip exceeds two code values')
                del intended_rgb,want
                raw=colors.read_rgb(targets[i]['record']['path'])
                if raw is None:raise RuntimeError('original complete decode unavailable')
                original=np.frombuffer(raw,np.uint8).reshape(h,w,3)
                measured=frame_changes(original,rgb)
                if measured['new_clip']:raise RuntimeError('decoded candidate introduces full-frame clipping')
                decoded_full.append(dict(source_frame_index=i,**measured,parameter_delta=0.));del original,raw
                coords=pairs['coordinates'][i];sample=rgb[coords[:,3],coords[:,2]].copy();final_pairs.append(sample)
                mean=(sample.astype(np.int16)-pairs['reference'][i]).mean(axis=0)
                if previous_mean is not None:temporal.append(float(np.linalg.norm(mean-previous_mean)))
                previous_mean=mean;maxima.append(difference)
                if i==count-1:decoded_last=rgb.copy()
                del sample,rgb,decoded
            if intended.read(1):raise RuntimeError('candidate intended RGB has extra frames')
    scores=score_repair_pairs(pairs['reference'],pairs['current'],final_pairs)
    if not scores['passed']:raise RuntimeError('decoded candidate residual/temporal regression: '+','.join(scores['reasons']))
    del final_pairs
    decoded_record=dict(schema_version=1,candidate_id=intent['candidate_id'],scores=scores,roundtrip_max=maxima,
        full_frames=decoded_full,temporal_error_differences=temporal)
    validate_measured_checks(fit,full_record,decoded_record,candidate_id=intent['candidate_id'],frames=count,channels=w*h*3)
    score_ref=artifact(store.write(folder/'decoded-scores.json',decoded_record))
    last_ref=_write_last_frame(store,folder,decoded_last,reader=reader);del decoded_last
    playback=store.root/folder/'playback.mp4'
    args=[str(config.tools['ffmpeg']),'-nostdin','-n','-v','error','-threads','1','-i',str(master),'-filter_threads','1','-vf',PLAYBACK_FILTER,
        '-c:v','libx264','-profile:v','high','-crf','16','-preset','medium','-threads','1','-pix_fmt','yuv420p','-an',
        '-colorspace','bt709','-color_trc','bt709','-color_primaries','bt709','-color_range','tv',str(playback)]
    playback_command=_command(store,folder,'playback',args,artifact(master),playback,config=config,paths=paths,logger=logger,reader=reader)
    boundary('playback-encoded')
    play_side,_,play_audit=inspect_candidate(store,folder,playback,rows,name='playback',config=config,paths=paths,reader=reader)
    validate_native(play_side['probe']['video'],count)
    if any(play_side['probe']['video'][key]!=sidecar['probe']['video'][key] for key in ('width','height','time_base')):
        raise RuntimeError('playback dimensions or native timebase differs')
    master_ref=artifact(master)
    mapping_rows=[dict(candidate_frame=i,source_frame=i,generated_frame=mapping['retained_to_generated'][i],output_frame=mapping['start_frame']+i,
        source_pts=pts[i],source_time_base=video['time_base'],candidate_pts=native[i]['pts'],candidate_time_base=tb,rgb_sha256=hashes[i]) for i in range(count)]
    frame_map=artifact(store.write(folder/'frame-map.json',dict(schema_version=1,candidate_id=intent['candidate_id'],source=binding['source'],candidate=master_ref,frames=mapping_rows)))
    evidence=[full_ref,score_ref,artifact(playback),artifact(probe.stdout_path),artifact(probe.stderr_path,empty=True),last_ref,frame_map,artifact(source_raw)]
    for ref in (command,playback_command):
        receipt=reader.read(ref)
        evidence += [artifact(receipt['command'][k],empty=True) for k in ('stdout_path','stderr_path')]
        evidence.append(receipt['tool'])
    for audit in (color_audit,play_audit):
        evidence += [artifact(p,empty=p.stat().st_size==0) for p in sorted((audit/'logs').rglob('*')) if p.is_file()]
    media=dict(schema_version=1,candidate_id=intent['candidate_id'],source=binding['source'],candidate=master_ref,frames=count,width=w,height=h,
        fps='16/1',time_base=tb,pts=[f['pts'] for f in native],frame_map=frame_map,
        encoding=dict(algorithm='fixed_srgb_yuv444_crf0_v1',parameters=RECIPE,command_receipts=[command,playback_command]),last_frame=last_ref,evidence=evidence)
    return media,frames


def validate_media(media,intent,*,config,reader):
    from .scene_color_repair_records import schema
    schema(media,'schema_version candidate_id source candidate frames width height fps time_base pts frame_map encoding last_frame evidence')
    if media['candidate_id']!=intent['candidate_id'] or media['source']!=intent['binding']['source'] or media['fps']!='16/1':
        raise ProductionRefused('repair media binding or native rate differs')
    folder=Path(intent['request']['path']).parent
    for name in ('frames','width','height'):integer(media[name],'repair '+name,1)
    original=reader.read(intent['binding']['mapping'])
    if media['frames']!=original['retained_frames']:raise ProductionRefused('repair media omits original retained frames')
    for ref,path in [(media['candidate'],folder/'master.mp4'),(media['last_frame'],folder/'last-frame.png'),(media['frame_map'],folder/'frame-map.json')]:
        if ref['path']!=str(path):raise ProductionRefused('repair media role or candidate path differs')
    object_fields(media['encoding'],'algorithm parameters command_receipts'.split(),'repair encoding')
    if media['encoding']['algorithm']!='fixed_srgb_yuv444_crf0_v1' or media['encoding']['parameters']!=RECIPE:
        raise ProductionRefused('repair encoding recipe differs')
    for ref in [media['source'],media['candidate'],media['last_frame'],media['frame_map']]+media['evidence']+media['encoding']['command_receipts']:
        verify(ref,empty=ref['bytes']==0)
    count=media['frames']
    measured={}
    for name in ('full-frame-checks.json','decoded-scores.json'):
        refs=[ref for ref in media['evidence'] if ref['path']==str(folder/name)]
        if len(refs)!=1:raise ProductionRefused('repair measured evidence missing or ambiguous: '+name)
        measured[name]=reader.read(refs[0])
    validate_measured_checks(reader.read(folder/'fit.json'),measured['full-frame-checks.json'],measured['decoded-scores.json'],
        candidate_id=intent['candidate_id'],frames=count,channels=media['width']*media['height']*3)
    try:tb=Fraction(media['time_base'])
    except (TypeError,ValueError,ZeroDivisionError) as exc:raise ProductionRefused('repair candidate timebase invalid') from exc
    if count>4096 or len(media['pts'])!=count or any(type(p) is not int or p*tb!=Fraction(i,16) for i,p in enumerate(media['pts'])):
        raise ProductionRefused('repair media exact rational PTS differs')
    mapping=reader.read(media['frame_map']);schema(mapping,'schema_version candidate_id source candidate frames')
    if mapping['candidate_id']!=intent['candidate_id'] or mapping['source']!=media['source'] or mapping['candidate']!=media['candidate'] or len(mapping['frames'])!=count:
        raise ProductionRefused('repair frame-map media binding differs')
    original_manifest=reader.read(intent['binding']['manifest'])
    targets=original_manifest['clips'][0]['frames']
    if len(targets)!=count:raise ProductionRefused('repair manifest native coverage differs')
    rgb_source=folder/'intended.rgb'
    if not rgb_source.is_file() or rgb_source.stat().st_size!=count*media['width']*media['height']*3:
        raise ProductionRefused('repair intended RGB complete byte count differs')
    if artifact(rgb_source) not in media['evidence']:raise ProductionRefused('repair RGB intent lacks evidence binding')
    original_native=[]
    for row in targets:
        ref={k:row['record'][k] for k in ('path','bytes','sha256')}
        original_native.append(reader.read(ref))
    import re
    for i,row in enumerate(mapping['frames']):
        object_fields(row,'candidate_frame source_frame generated_frame output_frame source_pts source_time_base candidate_pts candidate_time_base rgb_sha256'.split(),'repair frame map')
        if (any(type(row[k]) is not int for k in ('candidate_frame','source_frame','generated_frame','output_frame','source_pts','candidate_pts')) or
                [row['candidate_frame'],row['source_frame'],row['generated_frame'],row['output_frame']]!=[i,i,original['retained_to_generated'][i],original['start_frame']+i] or
                row['source_pts']!=original_native[i]['pts'] or row['source_time_base']!=original_native[i]['time_base'] or
                row['candidate_pts']!=media['pts'][i] or row['candidate_time_base']!=media['time_base'] or
                type(row['rgb_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',row['rgb_sha256']) is None):
            raise ProductionRefused('repair frame-map coordinates differ')
    with rgb_source.open('rb') as stream:
        for row in mapping['frames']:
            reader.check();raw=stream.read(media['width']*media['height']*3)
            if hashlib.sha256(raw).hexdigest()!=row['rgb_sha256']:raise ProductionRefused('repair intended frame RGB hash differs')
            del raw
    expected_receipts=[folder/'master-command.json',folder/'playback-command.json']
    receipts=media['encoding']['command_receipts']
    if type(receipts) is not list or [ref['path'] for ref in receipts]!=[str(p) for p in expected_receipts]:
        raise ProductionRefused('repair encoding command receipts incomplete')
    from ..media.colorimetry import _command_record,load_color_analysis_set
    for index,ref in enumerate(receipts):
        receipt=reader.read(ref);schema(receipt,'schema_version command source target tool')
        source=artifact(rgb_source) if index==0 else media['candidate']
        target=media['candidate'] if index==0 else artifact(folder/'playback.mp4')
        if receipt['source']!=source or receipt['target']!=target or receipt['tool']!=artifact(config.tools['ffmpeg'],runtime=False):
            raise ProductionRefused('repair command source/target/tool differs')
        command=receipt['command'];_command_record(command)
        if command['returncode']!=0 or command['timed_out'] is not False:
            raise ProductionRefused('repair command did not complete successfully')
        args=command['args'];spec=RECIPE['master' if index==0 else 'playback']
        if args[0]!=str(config.tools['ffmpeg']) or args[-1]!=target['path'] or command['cwd']!=str(folder.parents[3]):
            raise ProductionRefused('repair command producer path differs')
        expected_flags={'-i':source['path'],'-vf':spec['filter'],'-c:v':spec['codec'],'-crf':str(spec['crf']),
            '-preset':spec['preset'],'-pix_fmt':spec['pix_fmt'],'-color_primaries':spec['color_primaries'],
            '-color_trc':spec['color_trc'],'-colorspace':spec['colorspace'],'-color_range':spec['color_range']}
        expected_flags.update({'-bsf:v':spec['bitstream_filter'],'-video_size':f"{media['width']}x{media['height']}",'-framerate':'16','-pixel_format':'rgb24','-f':'rawvideo'}
            if index==0 else {'-profile:v':'high'})
        for key,want in expected_flags.items():
            if args.count(key)!=1 or args[args.index(key)+1]!=want:raise ProductionRefused('repair command recipe differs: '+key)
        if '-an' not in args or '-n' not in args:raise ProductionRefused('repair command audio/overwrite policy differs')
        for key in ('stdout_path','stderr_path'):verify(artifact(command[key],empty=True),empty=True)
    candidate_frames=master_frames(media,reader=reader)
    for name in ('master','playback'):
        sidecars=[ref for ref in media['evidence'] if Path(ref['path']).name=='sidecar.json' and Path(ref['path']).parent.name==name]
        if len(sidecars)!=1:raise ProductionRefused('repair complete color sidecar missing or ambiguous')
        side_path=verify(sidecars[0]);frame_paths=[side_path.parent/'analysis'/f'frame_{i:06d}.json' for i in range(count)]
        for path in frame_paths:
            if artifact(path) not in media['evidence']:raise ProductionRefused('repair complete decode evidence missing')
        with load_color_analysis_set(frame_paths,config=config,timeout=remaining(reader)) as colors:
            side=next(iter(colors.sidecars.values()));video=side['probe']['video']
            expected_source=media['candidate'] if name=='master' else artifact(folder/'playback.mp4')
            if {k:side['source'][k] for k in ('path','bytes','sha256')}!=expected_source:
                raise ProductionRefused('repair color evidence measures foreign media')
            pts=validate_native(video,count)
            if video['width']!=media['width'] or video['height']!=media['height'] or any(p*Fraction(video['time_base'])!=q*tb for p,q in zip(pts,media['pts'])):
                raise ProductionRefused('repair measured dimensions/native mapping differs')
            if name=='master' and (video['time_base']!=media['time_base'] or pts!=media['pts']):
                raise ProductionRefused('repair master probe differs from media record')
    return media


def master_frames(media,*,reader):
    """Return only the complete, separately owned master analysis frames."""
    sidecars=[ref for ref in media['evidence'] if Path(ref['path']).name=='sidecar.json' and Path(ref['path']).parent.name=='master']
    if len(sidecars)!=1:raise ProductionRefused('repair master sidecar missing or ambiguous')
    side=verify(sidecars[0]);frames=[]
    for i in range(media['frames']):
        path=side.parent/'analysis'/f'frame_{i:06d}.json'
        ref=artifact(path)
        if ref not in media['evidence']:raise ProductionRefused('repair master all-frame decode evidence missing')
        frames.append(dict(frame_id=f'candidate_frame_{i:06d}',record=thaw(hash_file(path))))
    return frames
