"""Native research media, full RGB roundtrip and unchanged-support measurements."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import os
from pathlib import Path

import numpy as np

from ._scene_continuity_io import artifact,local
from ._scene_color_repair_media import MASTER_FILTER,PLAYBACK_FILTER,RECIPE,frame_changes,dimensions
from ._scene_color_repair_validation import validate_native
from .manifest import now,thaw,hash_file
from .natural_study_records import StudyReader,put_json,fields
from .natural_study_measure import PixelSource,measure_variant,fixed_compare,replay_ordinary_report
from .production_state import ProductionRefused


def _args(config,source,target,*,name,width=None,height=None):
    spec=RECIPE[name]
    args=[str(config.tools['ffmpeg']),'-nostdin','-n','-v','error','-threads','1']
    if name=='master': args += ['-f','rawvideo','-pixel_format','rgb24','-video_size',f'{width}x{height}','-framerate','16']
    args += ['-i',str(source),'-filter_threads','1','-vf',spec['filter'],'-c:v','libx264']
    if name=='playback': args += ['-profile:v','high']
    args += ['-crf',str(spec['crf']),'-preset','medium','-threads','1','-pix_fmt',spec['pix_fmt'],'-an',
        '-color_primaries','bt709','-color_trc',spec['color_trc'],'-colorspace','bt709','-color_range',spec['color_range']]
    if name=='master': args += ['-bsf:v',spec['bitstream_filter']]
    return args+[str(target)]


def _run(args,*,config,paths,logger,reader,stage):
    from .processes import run_logged
    from .environment import build_child_env
    result=run_logged(args,cwd=logger.run_dir,env=build_child_env(paths),timeout=reader.remaining(),logger=logger,stage=stage)
    if result.returncode!=0 or result.timed_out: raise ProductionRefused('natural media command failed; evidence retained:'+str(result.stderr_path))
    reader.check();return result


def inspect_media(path,count,*,command,out,config,paths,clip_id='natural_research',reader=None):
    """Generic composition mapping; no fabricated generated/retained/output IDs."""
    from .paths import create_run
    from .logging import RunLogger
    from ..media.colorimetry import inspect_color_asset,decode_analysis_frame
    reader=reader or StudyReader();reader.check();out=Path(out);log=RunLogger(create_run(paths))
    probe=_run([str(config.tools['ffprobe']),'-v','error','-show_streams','-show_frames','-of','json',str(path)],
        config=config,paths=paths,logger=log,reader=reader,stage='natural_native_probe')
    raw=reader.any(probe.stdout_path);streams=raw['streams'];frames=raw['frames']
    if len(streams)!=1 or streams[0]['codec_type']!='video' or len(frames)!=count:
        raise ProductionRefused('natural media needs one video stream and complete native frames')
    tb=streams[0]['time_base']
    rows=[]
    for i,frame in enumerate(frames):
        pts=frame.get('pts')
        if type(pts) is not int or Fraction(tb)*pts!=Fraction(i,16): raise ProductionRefused('natural native PTS differs')
        rows.append(dict(asset_frame_index=i,clip_id=clip_id,generated_frame_index=None,retained_frame_index=None,
            output_frame_index=None,pts=pts,time_base=tb))
    mapping=put_json(out/'mapping-proof.json',dict(source=thaw(hash_file(path)),rows=rows))
    asset='natural_media'
    side,_=inspect_color_asset(dict(asset_id=asset,stage='composition',path=str(path),mapping=dict(rows=rows,evidence=[thaw(hash_file(Path(mapping['path'])))]),
        processing=dict(operation='natural_constant_color_repair_v1 research composition',upstream_ids=[],command_records=[thaw(hash_file(Path(command['path'])))])),
        config=config,paths=paths,logger=log,timeout=reader.remaining())
    if side['interpretation']['status']!='resolved': raise ProductionRefused('natural candidate color interpretation unknown')
    validate_native(side['probe']['video'],count)
    output=[]
    for i in range(count):
        decode_analysis_frame(side,frame_index=i,config=config,paths=paths,logger=log,timeout=reader.remaining())
        output.append(dict(frame_id=f'natural_frame_{i:06d}',record=thaw(hash_file(log.root/f'colorimetry/{asset}/analysis/frame_{i:06d}.json'))))
    put_json(out/'inspection.json',dict(schema_version=1,source=artifact(path),command=command,producer=str(log.run_dir),mapping=mapping,
        sidecar=artifact(log.root/f'colorimetry/{asset}/sidecar.json'),frames=output,
        evidence=[artifact(p,empty=True) for p in sorted(log.root.rglob('*')) if p.is_file()]))
    return side,output


def after_manifest(manifest,frames,*,out):
    reader=StudyReader();value=deepcopy(manifest);original=manifest['clips'][0]['frames'];regions=deepcopy(reader.any(manifest['regions']))
    mapping={old['record']['path']:new['record'] for old,new in zip(original,frames)}
    for r in regions['regions']:
        for a in r['anchors']:
            if a['frame']['path'] in mapping: a['frame']=mapping[a['frame']['path']]
    value['regions']=thaw(hash_file(Path(put_json(Path(out)/'regions.json',regions)['path'])))
    value['clips'][0]['frames']=[dict(old,record=new['record']) for old,new in zip(original,frames)]
    return value


def _full_decode(media,manifest,fit,*,config,reader=None):
    from ..media.color_repair import apply_constant_repair
    from ..media._continuity_audit import png_bytes
    from ..media.colorimetry import load_color_analysis_set
    reader=reader or StudyReader();reader.check();full=[];maxima=[];hashes=[];tail=None
    frames=media['master_frames'];count=media['frames'];inspections={}
    if type(count) is not int or not 1<=count<=4096: raise ProductionRefused('bounded native inspection count required')
    for name in ('master','playback'):
        inspection=reader.any(media[name+'_inspection']);inspections[name]=inspection
        expected=media['candidate'] if name=='master' else media['playback']
        if inspection['source']!=expected or len(inspection['frames'])!=count:
            raise ProductionRefused('natural inspection complete source/count differs')
    if frames!=inspections['master']['frames']: raise ProductionRefused('scored master frames differ from actual master inspection')
    with PixelSource(manifest,config,reader,candidate_frames=frames) as source:
        with Path(media['intended']['path']).open('rb') as stream:
            for i,frame in enumerate(frames):
                original=source.rgb(source.targets[i]);want=apply_constant_repair(original,operation=fit['operation'],amplitude=fit['amplitude'])
                raw=stream.read(want.nbytes)
                if raw!=want.tobytes(): raise ProductionRefused('natural intent is not the exact constant transform')
                decoded=source.rgb(frame)
                if decoded.shape!=original.shape: raise ProductionRefused('natural full frame dimensions differ')
                maximum=frame_changes(want,decoded)['max_change']
                check=dict(source_frame_index=i,**frame_changes(original,decoded))
                if maximum>2 or check['new_clip']!=0: raise ProductionRefused('natural RGB roundtrip/clipping guard failed')
                if frame_changes(original,want)['new_clip']: raise ProductionRefused('natural intent introduces clipping')
                hashes.append(hashlib.sha256(raw).hexdigest());maxima.append(maximum);full.append(check)
                if i==count-1: tail=png_bytes(decoded)
            if stream.read(1): raise ProductionRefused('extra intended native frames')
    # Playback is separately decoded completely, and bound to its own MP4.
    for name in ('master','playback'):
        inspection=inspections[name];expected=media['candidate'] if name=='master' else media['playback']
        if inspection['source']!=expected: raise ProductionRefused('natural inspection source differs')
        for ref in inspection['evidence']: reader.capture(ref,package=True)
        with load_color_analysis_set([f['record']['path'] for f in inspection['frames']],config=config,timeout=reader.remaining()) as colors:
            for i,row in enumerate(colors.frames):
                reader.check()
                rec=row['record'];side=colors.sidecars[rec['sidecar']['path']]
                v=side['probe']['video'];validate_native(v,count)
                if (v['width'],v['height'])!=(media['width'],media['height']) or {k:rec['source'][k] for k in ('path','bytes','sha256')}!=expected:
                    raise ProductionRefused('natural media source/dimensions differ')
                if (rec['frame_index']!=i or Fraction(rec['pts'])*Fraction(rec['time_base'])!=Fraction(i,16)
                        or inspection['frames'][i]['record']['path']!=row['record_identity']['path']):
                    raise ProductionRefused('natural full decode frame order/PTS differs')
                if colors.read_rgb(row['record_identity']['path']) is None: raise ProductionRefused('incomplete natural playback RGB')
    reader.verify_all();return full,maxima,hashes,tail


def render_media(manifest,report,fit,*,out,source,before_report,config,paths,reader=None):
    from .paths import create_run
    from .logging import RunLogger
    from ..media.color_repair import apply_constant_repair
    from ..media.research_pair_report import analyze_research_pairs
    out=local(out,exists=False)
    if out.exists() and any(out.iterdir()): raise ProductionRefused('partial natural media retained; new UUID required')
    if fit.get('status')!='estimated' or fit.get('operation') not in ('exposure','wb_r','wb_g') or type(fit.get('amplitude')) not in (int,float):
        raise ProductionRefused('explicit single estimated natural fit required')
    out.mkdir(parents=True,exist_ok=True);reader=reader or StudyReader();reader.check();count=len(manifest['clips'][0]['frames'])
    put_json(out/'render-intent.json',dict(schema_version=1,source=source,fit=fit,before_report=before_report,recipe=RECIPE,created_at=now()))
    raw_path=out/'intended.rgb';checks=[];hashes=[]
    with PixelSource(manifest,config,reader) as pixels:
        rec=pixels.records[pixels.targets[0]['record']['path']];v=pixels.colors.sidecars[rec['sidecar']['path']]['probe']['video']
        validate_native(v,count);w,h=dimensions(v,count,run=out)
        if 4*w*h*3+count*2048*25+16*1024**2>128*1024**2:
            raise ProductionRefused('resource_limit: natural pixel working budget')
        with raw_path.open('xb') as stream:
            for i,frame in enumerate(pixels.targets):
                original=pixels.rgb(frame);actual=pixels.records[frame['record']['path']]['source']
                if actual['sha256']!=source['sha256']: raise ProductionRefused('natural original source frame differs')
                changed=apply_constant_repair(original,operation=fit['operation'],amplitude=fit['amplitude'])
                check=frame_changes(original,changed)
                if check['new_clip']: raise ProductionRefused('natural full frame introduces clipping')
                checks.append(dict(source_frame_index=i,**check));raw=changed.tobytes()
                hashes.append(hashlib.sha256(raw).hexdigest());stream.write(raw)
            stream.flush();os.fsync(stream.fileno())
    log=RunLogger(create_run(paths));commands=[];inspections=[];native_frames=[];master_side=None
    for name in ('master','playback'):
        target=out/(name+'.mp4');origin=raw_path if name=='master' else out/'master.mp4'
        args=_args(config,origin,target,name=name,width=w,height=h)
        reader.check();result=_run(args,config=config,paths=paths,logger=log,reader=reader,stage='natural_'+name)
        command=put_json(out/(name+'-command.json'),dict(schema_version=1,command=thaw(result),source=artifact(origin),target=artifact(target),tool=artifact(config.tools['ffmpeg'],runtime=False)))
        commands.append(command)
        side,frames=inspect_media(target,count,command=command,out=out/(name+'-proof'),config=config,paths=paths,clip_id=manifest['clips'][0]['clip_id'],reader=reader)
        inspections.append(artifact(out/(name+'-proof/inspection.json')))
        if name=='master': native_frames=frames;master_side=side
    media=dict(schema_version=1,kind='natural_repair_media_v1',source=source,candidate=artifact(out/'master.mp4'),
        playback=artifact(out/'playback.mp4'),intended=artifact(raw_path),frames=count,width=w,height=h,
        recipe=RECIPE,fit=fit,master_frames=native_frames,master_inspection=inspections[0],playback_inspection=inspections[1],
        commands=commands,before_report=before_report,after_report=None,after_manifest=None,last_frame=None,
        frame_map=None,roundtrip_max=[],full_frame=[],scores=None,risks=[],created_at=now())
    full,maxima,actual_hashes,tail=_full_decode(media,manifest,fit,config=config,reader=reader)
    if hashes!=actual_hashes: raise ProductionRefused('natural intended frame identity differs')
    last=out/'last-frame.png'
    with last.open('xb') as stream: stream.write(tail);stream.flush();os.fsync(stream.fileno())
    media.update(full_frame=full,roundtrip_max=maxima,last_frame=artifact(last))
    frame_map=dict(schema_version=1,source=source,candidate=media['candidate'],frames=[dict(source_frame=i,candidate_frame=i,
        source_record=manifest['clips'][0]['frames'][i]['record'],candidate_record=native_frames[i]['record'],
        time=str(Fraction(i,16)),intended_rgb_sha256=hashes[i]) for i in range(count)])
    media['frame_map']=put_json(out/'frame-map.json',frame_map)
    transformed=measure_variant(manifest,report,config=config,out=out/'fixed-support',candidate_frames=native_frames,reader=reader)
    media['scores']=fixed_compare(transformed['before'],transformed['after'],operation=fit['operation'])
    after=after_manifest(manifest,native_frames,out=out/'after')
    media['after_manifest']=put_json(out/'after/manifest.json',after)
    audit=RunLogger(create_run(paths));new_report,_=analyze_research_pairs(after,config=config,paths=paths,logger=audit,timeout=reader.remaining())
    media['after_report']=artifact(audit.root/'continuity/report.json')
    from .scene_continuity_records import derive_concerns
    media['risks']=[dict(phase=phase,**c) for phase,r in [('before',report),('after',new_report)] for c in derive_concerns(r)]
    reader.verify_all();media['created_at']=now();put_json(out/'media.json',media)
    return media


def validate_media(media,*,manifest,report,fit,config,reader=None):
    from ..media.research_pair_report import validate_research_pair_report
    from ..media._continuity_audit import png_bytes
    reader=reader or StudyReader();reader.check()
    fields(media,'schema_version kind source candidate playback intended frames width height recipe fit master_frames master_inspection playback_inspection commands before_report after_report after_manifest last_frame frame_map roundtrip_max full_frame scores risks created_at')
    if media['schema_version']!=1 or media['kind']!='natural_repair_media_v1' or media['recipe']!=RECIPE or media['fit']!=fit:
        raise ProductionRefused('natural media recipe/fit differs')
    folder=Path(media['candidate']['path']).parent
    for key,name in [('candidate','master.mp4'),('playback','playback.mp4'),('intended','intended.rgb'),('last_frame','last-frame.png'),('frame_map','frame-map.json')]:
        if Path(media[key]['path'])!=folder/name: raise ProductionRefused('natural media role path differs')
        reader.cap(media[key])
    intent=reader.any(folder/'render-intent.json')
    if intent['source']!=media['source'] or intent['fit']!=fit or intent['recipe']!=RECIPE or intent['before_report']!=media['before_report']:
        raise ProductionRefused('natural original render intent differs')
    if media['frames']!=len(manifest['clips'][0]['frames']): raise ProductionRefused('natural media complete coverage differs')
    for name,ref in zip(('master','playback'),media['commands']):
        row=reader.any(ref);source=media['intended'] if name=='master' else media['candidate'];target=media['candidate'] if name=='master' else media['playback']
        cmd=row['command']
        if (row['source']!=source or row['target']!=target or row['tool']!=artifact(config.tools['ffmpeg'],runtime=False)
                or cmd['args']!=_args(config,source['path'],target['path'],name=name,width=media['width'],height=media['height'])
                or cmd['returncode']!=0 or cmd['timed_out'] is not False): raise ProductionRefused('natural command recipe/source differs')
        for k in ('stdout_path','stderr_path'): reader.capture(cmd[k],package=True)
    if len(media['commands'])!=2: raise ProductionRefused('natural encode command inventory differs')
    full,maxima,hashes,tail=_full_decode(media,manifest,fit,config=config,reader=reader)
    if media['full_frame']!=full or media['roundtrip_max']!=maxima or Path(media['last_frame']['path']).read_bytes()!=tail:
        raise ProductionRefused('natural decoded arithmetic/tail replay differs')
    mapping=reader.any(media['frame_map'])
    expected=dict(schema_version=1,source=media['source'],candidate=media['candidate'],frames=[dict(source_frame=i,candidate_frame=i,
        source_record=manifest['clips'][0]['frames'][i]['record'],candidate_record=media['master_frames'][i]['record'],
        time=str(Fraction(i,16)),intended_rgb_sha256=hashes[i]) for i in range(media['frames'])])
    if mapping!=expected: raise ProductionRefused('natural frame-map differs')
    actual=measure_variant(manifest,report,config=config,out=None,candidate_frames=media['master_frames'],reader=reader)
    if fixed_compare(actual['before'],actual['after'],operation=fit['operation'])!=media['scores']:
        raise ProductionRefused('natural decoded fixed-support metrics differ')
    before=replay_ordinary_report(media['before_report'],manifest=manifest,config=config,reader=reader)
    if before!=report: raise ProductionRefused('natural original ordinary report differs')
    after=reader.any(media['after_manifest']);regions=deepcopy(reader.any(manifest['regions']))
    mapping={old['record']['path']:new['record'] for old,new in zip(manifest['clips'][0]['frames'],media['master_frames'])}
    for r in regions['regions']:
        for a in r['anchors']:
            if a['frame']['path'] in mapping: a['frame']=mapping[a['frame']['path']]
    expected_after=deepcopy(manifest);expected_after['regions']=after['regions']
    expected_after['clips'][0]['frames']=[dict(old,record=new['record']) for old,new in zip(manifest['clips'][0]['frames'],media['master_frames'])]
    if after!=expected_after or reader.any(after['regions'])!=regions: raise ProductionRefused('natural after manifest/ROI differs')
    new=replay_ordinary_report(media['after_report'],manifest=after,config=config,reader=reader)
    from .scene_continuity_records import derive_concerns
    if media['risks']!=[dict(phase=phase,**c) for phase,r in [('before',report),('after',new)] for c in derive_concerns(r)]:
        raise ProductionRefused('natural before/after risks differ')
    reader.verify_all();return media
