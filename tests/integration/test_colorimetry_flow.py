"""Real CPU fixtures with independent code-value expectations and durable evidence."""
from dataclasses import replace
from pathlib import Path
import json
import math
import os
import struct
import zlib

import pytest

from video_ai.config import load_config
from video_ai.runtime.environment import build_child_env
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.manifest import hash_file, thaw
from video_ai.runtime.paths import create_run
from video_ai.runtime.processes import run_logged


@pytest.fixture
def color_context(runtime_run,request):
    run, config, paths = runtime_run
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config = replace(config, tools=dict(config.tools, ffmpeg=actual.tools['ffmpeg'], ffprobe=actual.tools['ffprobe']))
    logger=RunLogger(create_run(paths))
    context=dict(test=request.node.nodeid,source_run=str(run),audit_run=str(logger.run_dir))
    logger.save_json('colorimetry/fixture-context.json',context)
    if os.environ.get('VCO02_EVIDENCE_INDEX'):
        with Path(os.environ['VCO02_EVIDENCE_INDEX']).open('a',encoding='utf-8') as file:
            file.write(json.dumps(context)+'\n')
    return run, dict(config=config, paths=paths, logger=logger), RunLogger(run)


def command(context, args):
    run, kw, logger = context
    result = run_logged([str(a) for a in args], cwd=run, env=build_child_env(kw['paths']),
                        timeout=60, logger=logger, stage='color_fixture')
    assert result.returncode == 0 and not result.timed_out, result.stderr_path.read_text()
    return thaw(result)


def entry(path, name='sample', stage='generated', rows=None, upstream=None, evidence=None, records=None):
    return dict(asset_id=name, stage=stage, path=str(path),
        mapping=dict(rows=rows or [], evidence=evidence or []),
        processing=dict(operation='CPU synthetic control', upstream_ids=upstream or [], command_records=records or []))


def row(index, generated=None, retained=None, output=None):
    return dict(asset_frame_index=index, clip_id='clip_0001', generated_frame_index=generated,
        retained_frame_index=retained, output_frame_index=output, pts=index*1024, time_base='1/16384')


def video(context, name='input', range_name='tv', transfer='bt709', matrix='bt709', crf='0', audio=False):
    run, kw, _ = context
    # 4 constant gray quadrants. Chroma exactly 128; independent legal-range codes.
    levels = [0, 64, 128, 255] if range_name == 'pc' else [16, 71, 126, 235]
    plane = bytes(levels[(y//16)*2+x//16] for y in range(32) for x in range(32))
    raw = run/(name+'.yuv'); raw.write_bytes((plane+bytes([128])*512)*16)
    target = run/(name+'.mp4')
    args = [kw['config'].tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-f', 'rawvideo',
        '-pixel_format', 'yuv420p', '-video_size', '32x32', '-framerate', '16']
    if matrix: args += ['-colorspace', matrix, '-color_primaries', 'bt709', '-color_trc', transfer, '-color_range', range_name]
    args += ['-i', raw]
    if audio: args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000']
    args += ['-frames:v', '16', '-c:v', 'libx264', '-crf', crf, '-pix_fmt', 'yuv420p']
    if matrix: args += ['-colorspace', matrix, '-color_primaries', 'bt709', '-color_trc', transfer, '-color_range', range_name,
                        '-x264-params', f'colorprim=bt709:transfer={transfer}:colormatrix={matrix}']
    args += ['-c:a', 'aac', '-shortest'] if audio else ['-an']
    cmd = command(context, [*args, target])
    return target, levels, cmd


def snapshot(run):
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns, hash_file(p).sha256)
            for p in run.rglob('*') if p.is_file()}


@pytest.mark.parametrize('range_name,transfer', [('tv','bt709'), ('pc','bt709'), ('tv','iec61966-2-1')])
def test_explicit_decode_range_transfer_and_source_unchanged(color_context, range_name, transfer):
    from video_ai.media.colorimetry import inspect_color_asset, decode_analysis_frame
    from video_ai.media.video import validate_video_probe
    run, kw, _ = color_context
    path, levels, _ = video(color_context, range_name=range_name, transfer=transfer)
    before = snapshot(run)
    side, evidence = inspect_color_asset(entry(path, rows=[row(0,0)]), **kw)
    assert side['analysis_space'] == 'srgb_rgb24_v1'
    assert set(side) == set('schema_version algorithm asset_id stage source input_sha256 mapping processing probe interpretation analysis_space commands tools risks created_at'.split())
    assert side['interpretation']['status'] == 'resolved'
    decoded, outputs = decode_analysis_frame(side, frame_index=0, **kw)
    assert decoded['status'] == 'ready' and decoded['pixels']['bytes'] == 32*32*3
    pixels = Path(decoded['pixels']['path']).read_bytes()
    for x,y,level in [(8,8,levels[0]), (24,8,levels[1]), (8,24,levels[2]), (24,24,levels[3])]:
        encoded = level/255 if range_name == 'pc' else (level-16)/219
        # zscale interprets video BT.709 through display-referred BT.1886 EOTF.
        # This is a fixed analysis convention, not an inferred camera OETF.
        linear = encoded**2.4
        expected = round(encoded*255) if transfer == 'iec61966-2-1' else round(255*(12.92*linear if linear <= .0031308 else 1.055*linear**(1/2.4)-.055))
        assert all(abs(c-expected) <= 2 for c in pixels[(y*32+x)*3:(y*32+x)*3+3])
    args = decoded['command']['args']; filt = args[args.index('-vf')+1]
    assert 'zscale=' in filt and f'transferin={transfer}' in filt and 'rangein='+('full' if range_name=='pc' else 'limited') in filt
    assert 'transfer=iec61966-2-1' in filt and 'matrix=gbr' in filt
    assert snapshot(run) == before
    raw = json.loads(Path(side['probe']['raw_probe']['path']).read_text())
    frames = json.loads(Path(side['probe']['raw_frames']['path']).read_text())
    assert validate_video_probe(raw, frames, width=32, height=32) == dict(width=32,height=32,codec='h264',pixel_format='yuvj420p' if range_name=='pc' else 'yuv420p',fps=16,frames=16,duration=1.)
    assert [f['pts'] for f in side['probe']['video']['frames']] == list(range(0,16384,1024))
    assert all(p.is_relative_to(kw['logger'].run_dir) for p in [*evidence,*outputs])
    with pytest.raises(FileExistsError): decode_analysis_frame(side, frame_index=0, **kw)
    with pytest.raises(ValueError): decode_analysis_frame(side, frame_index=True, **kw)
    with pytest.raises(ValueError): decode_analysis_frame(side, frame_index=16, **kw)


def test_unknown_and_wrong_matrix_do_not_produce_shared_space(color_context):
    from video_ai.media.colorimetry import inspect_color_asset, decode_analysis_frame
    for name,matrix,status in [('untagged',None,'unknown'), ('wrong','bt470bg','unsupported')]:
        path, _, _ = video(color_context, name=name, matrix=matrix)
        side,_=inspect_color_asset(entry(path,name), **color_context[1])
        assert side['interpretation']['status'] == status and side['analysis_space'] is None
        result,_=decode_analysis_frame(side,frame_index=0,**color_context[1])
        assert result['status']=='unverified' and result['pixels'] is None and result['command'] is None


def test_identical_yuv_payload_different_matrix_declarations_are_not_a_repair(color_context):
    from video_ai.media.colorimetry import inspect_color_asset
    run,kw,_=color_context
    payloads=[];sidecars=[]
    for name,matrix in [('correct','bt709'),('wrong','bt470bg'),('unmarked',None)]:
        path,_,_=video(color_context,name=name,matrix=matrix)
        cmd=command(color_context,[kw['config'].tools['ffmpeg'],'-nostdin','-v','error','-i',path,
            '-map','0:v:0','-pix_fmt','yuv420p','-f','rawvideo','-'])
        payloads.append(Path(cmd['stdout_path']).read_bytes())
        side,_=inspect_color_asset(entry(path,name),**kw);sidecars.append(side)
    assert payloads[0]==payloads[1]==payloads[2]
    assert [s['interpretation']['status'] for s in sidecars]==['resolved','unsupported','unknown']
    kw['logger'].save_json('colorimetry/matrix-control.json',dict(
        sources=[s['source'] for s in sidecars],same_decoded_yuv_payload=True,
        limitation='Only declarations changed in this synthetic control; differing labels do not prove real-camera intent.'))


def test_decode_rejects_memory_only_or_modified_sidecar(color_context):
    from video_ai.media.colorimetry import inspect_color_asset, decode_analysis_frame
    path,_,_=video(color_context)
    side,_=inspect_color_asset(entry(path),**color_context[1])
    side['interpretation']['values']['color_range']='pc'
    with pytest.raises(ValueError): decode_analysis_frame(side,frame_index=0,**color_context[1])


def test_sidecar_rejects_source_same_stat_drift_and_duplicate(color_context):
    import os
    from video_ai.media.colorimetry import inspect_color_asset, decode_analysis_frame
    path,_,_=video(color_context)
    side,_=inspect_color_asset(entry(path),**color_context[1])
    with pytest.raises(FileExistsError): inspect_color_asset(entry(path),**color_context[1])
    stamp=path.stat(); original=path.read_bytes()
    path.write_bytes(original[:-1]+bytes([original[-1]^1])); os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises(OSError): decode_analysis_frame(side,frame_index=0,**color_context[1])


def png(path, *, srgb=False, size=32):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    pixels = bytes(c for y in range(size) for x in range(size) for c in (x*255//(size-1),y*255//(size-1),(x+y)*127//(size-1)))
    data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))
    if srgb: data += chunk(b'sRGB',b'\0')
    data += chunk(b'IDAT',zlib.compress(b''.join(b'\0'+pixels[y*size*3:(y+1)*size*3] for y in range(size))))+chunk(b'IEND',b'')
    path.write_bytes(data)
    return pixels


def test_srgb_png_actual_analysis_and_unrelated_mapping_not_proof(color_context):
    from video_ai.media.colorimetry import inspect_color_asset,decode_analysis_frame
    run,kw,_=color_context
    path=run/'profile.png'; expected=png(path,srgb=True)
    unrelated=run/'unrelated.json'; unrelated.write_text('{}')
    data=entry(path, rows=[row(0,15)], evidence=[thaw(hash_file(unrelated))])
    side,_=inspect_color_asset(data,**kw)
    assert any(r['code']=='unverified_mapping' for r in side['risks'])
    result,_=decode_analysis_frame(side,frame_index=0,**kw)
    assert result['status']=='ready' and result['pts'] is None
    assert Path(result['pixels']['path']).read_bytes()==expected


def test_five_stage_chain_records_every_frame_and_preserves_sources(color_context):
    from video_ai.media.colorimetry import inspect_color_chain
    from video_ai.media.video import inspect_video,trim_scene_video
    from video_ai.media.frames import extract_native_frame
    run,kw,logger=color_context
    generated,_,_=video(color_context)
    source_kw=dict(config=kw['config'],paths=kw['paths'],logger=logger,unit_id='clip_0001',width=32,height=32)
    info,_=inspect_video(generated,**source_kw)
    retained=run/'retained.mp4'
    _,trim_evidence=trim_scene_video(generated,retained,source_info=info,start_frame=1,end_frame=15,**source_kw)
    tail=run/'frame_000015.png'
    _,tail_evidence=extract_native_frame(generated,tail,source_frame_index=14,expected_frames=16,**source_kw)
    up=run/'test-resize.png'
    command(color_context,[kw['config'].tools['ffmpeg'],'-nostdin','-n','-v','error','-i',tail,'-vf','scale=64:64','-frames:v','1',up])
    final=run/'final.mp4'
    final_command=command(color_context,[kw['config'].tools['ffmpeg'],'-nostdin','-n','-v','error',
        '-loop','1','-framerate','16','-i',up,'-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
        '-frames:v','16','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-shortest',final])
    final_receipt=run/'final-encode.json'
    final_receipt.write_text(json.dumps(dict(source=thaw(hash_file(up)),target=thaw(hash_file(final)),command=final_command)))
    entries=[entry(generated,'generated',rows=[row(i,i) for i in range(16)]),
        entry(tail,'tail','native_tail',[row(0,14,13,13)],['generated'],records=[thaw(hash_file(tail_evidence[0]))]),
        entry(retained,'retained','retained',[row(i,i+1,i,i) for i in range(14)],['generated'],records=[thaw(hash_file(trim_evidence[0]))]),
        entry(up,'upscaled','upscaled',[row(0,14,13,13)],['tail']),
        entry(final,'composition','composition',[row(i,14,13,i) for i in range(16)],['upscaled'],records=[thaw(hash_file(final_receipt))])]
    # Original fixture mappings explicitly bind each asset SHA and its exact rows.
    # The repeated still in the composition is a controlled fixture, not a motion claim.
    entries[1]['mapping']['rows'][0].update(pts=14*1024,time_base='1/16384')
    entries[3]['mapping']['rows'][0].update(pts=14*1024,time_base='1/16384')
    for data in entries:
        proof=run/(data['asset_id']+'-mapping.json')
        proof.write_text(json.dumps(dict(source=thaw(hash_file(Path(data['path']))),rows=data['mapping']['rows'])))
        data['mapping']['evidence']=[thaw(hash_file(proof))]
    before=snapshot(run)
    chain,evidence=inspect_color_chain(entries,timeout=600,**kw)
    assert chain['coverage']=='complete' and chain['missing_stages']==[]
    assert [a['asset_id'] for a in chain['assets']]==['generated','tail','retained','upscaled','composition']
    assert [len(a['analysis_frames']) for a in chain['assets']]==[16,1,14,1,16]
    assert chain['edges'][-1]==dict(from_asset_id='upscaled',to_asset_id='composition',status='recorded')
    for asset in chain['assets']:
        side=json.loads(Path(asset['sidecar']['path']).read_text())
        assert not any(r['code']=='unverified_mapping' for r in side['risks'])
    tail_record=json.loads(Path(chain['assets'][1]['analysis_frames'][0]['path']).read_text())
    assert tail_record['mapping']['generated_frame_index']==14 and tail_record['pts']==14*1024
    assert snapshot(run)==before
    assert any(r['code']=='missing_color_metadata' for r in chain['risks'])
    assert all(Path(a['sidecar']['path']).is_file() for a in chain['assets'])
    # Synthetic resize deliberately has no model/RealESRGAN claim.
    assert all(p.is_relative_to(kw['logger'].run_dir) for p in evidence)


def test_partial_chain_external_upstream_and_failure_no_chain(color_context):
    from video_ai.media.colorimetry import inspect_color_chain
    run,kw,_=color_context
    image=run/'unknown.png';png(image)
    chain,_=inspect_color_chain([entry(image,'partial','upscaled',upstream=['absent'])],**kw)
    assert chain['coverage']=='partial' and chain['missing_stages']==['generated','native_tail','retained','composition']
    assert chain['edges']==[dict(from_asset_id='absent',to_asset_id='partial',status='unknown')]
    fresh=dict(kw,logger=RunLogger(create_run(kw['paths'])))
    invalid=run/'invalid.mp4';invalid.write_bytes(b'not a video')
    with pytest.raises(RuntimeError): inspect_color_chain([entry(invalid)],**fresh)
    assert not (fresh['logger'].root/'colorimetry/chain.json').exists()
    assert not (fresh['logger'].root/'colorimetry/sample/sidecar.json').exists()


def test_lossless_and_crf18_roundtrip_keep_quantified_evidence(color_context):
    from video_ai.media.colorimetry import inspect_color_chain
    run,kw,_=color_context
    path=run/'original.png'; original=png(path,srgb=True)
    entries=[entry(path,'original','native_tail',rows=[row(0,0)])]
    records=[]
    for name,crf in [('lossless','0'),('crf18','18')]:
        target=run/(name+'.mp4')
        args=[kw['config'].tools['ffmpeg'],'-nostdin','-n','-v','error','-loop','1','-framerate','16','-i',path,
            '-vf','format=gbrp,zscale=matrixin=gbr:transferin=iec61966-2-1:primariesin=bt709:rangein=full:matrix=bt709:transfer=iec61966-2-1:primaries=bt709:range=limited:dither=none,format=yuv420p',
            '-frames:v','16','-c:v','libx264','-crf',crf,'-pix_fmt','yuv420p',
            '-x264-params','colorprim=bt709:transfer=iec61966-2-1:colormatrix=bt709','-color_range','tv',target]
        cmd=command(color_context,args)
        rec=run/(name+'-encode.json');rec.write_text(json.dumps(dict(source=thaw(hash_file(path)),target=thaw(hash_file(target)),command=cmd)))
        records.append(thaw(hash_file(rec)))
        entries.append(entry(target,name,rows=[row(i,0) for i in range(16)],upstream=['original'],records=[records[-1]]))
    for data in entries:
        proof=run/(data['asset_id']+'-mapping.json')
        proof.write_text(json.dumps(dict(source=thaw(hash_file(Path(data['path']))),rows=data['mapping']['rows'])))
        data['mapping']['evidence']=[thaw(hash_file(proof))]
    before=snapshot(run)
    chain,_=inspect_color_chain(entries,timeout=600,**kw)
    assert [edge['status'] for edge in chain['edges']]==['recorded','recorded']
    stats=[]
    for asset in chain['assets'][1:]:
        deltas=[]
        for frame in asset['analysis_frames']:
            record=json.loads(Path(frame['path']).read_text());raw=Path(record['pixels']['path']).read_bytes()
            delta=[abs(a-b) for a,b in zip(raw,original)]
            deltas.append(dict(frame_index=record['frame_index'],mae=sum(delta)/len(delta),max_abs=max(delta),pixels=record['pixels']))
        stats.append(dict(asset_id=asset['asset_id'],frames=deltas))
    report=kw['logger'].save_json('colorimetry/roundtrip-control.json',dict(
        original=thaw(hash_file(path)),commands=records,results=stats,
        limitation='Lossless x264 preserves YUV payload; RGB/YUV420 conversion and chroma subsampling still lose information. No video-quality threshold.'))
    assert report.is_file() and snapshot(run)==before
    assert len(stats)==2 and all(len(s['frames'])==16 for s in stats)
    assert stats[1]['frames'][0]['max_abs']>0


@pytest.mark.parametrize('mutation', ['interpretation','analysis_space','risk_extra','processing_extra','probe_extra','forged_profile'])
def test_persisted_sidecar_cannot_forge_derived_fields(color_context,mutation):
    from video_ai.media.colorimetry import inspect_color_asset,decode_analysis_frame
    run,kw,_=color_context
    path=run/'source.png';png(path)
    side,_=inspect_color_asset(entry(path),**kw)
    if mutation=='interpretation': side['interpretation']['status']='resolved';side['analysis_space']='srgb_rgb24_v1'
    if mutation=='analysis_space':side['analysis_space']='srgb_rgb24_v1'
    if mutation=='risk_extra':side['risks'][0]['passed']=True
    if mutation=='processing_extra':side['processing']['passed']=True
    if mutation=='probe_extra':side['probe']['passed']=True
    if mutation=='forged_profile':
        side['probe']['png_metadata']['srgb_intent']=0
        from video_ai.media.colorimetry import parse_color_probe
        parsed=parse_color_probe(json.loads(Path(side['probe']['raw_probe']['path']).read_text()),
            json.loads(Path(side['probe']['raw_frames']['path']).read_text()),png_metadata=side['probe']['png_metadata'])
        side['interpretation']=parsed['interpretation'];side['analysis_space']='srgb_rgb24_v1'
    stored=kw['logger'].root/'colorimetry/sample/sidecar.json';stored.write_text(json.dumps(side))
    with pytest.raises(ValueError):decode_analysis_frame(side,frame_index=0,**kw)


@pytest.mark.parametrize('failure',['decode','bytes','capability'])
def test_decode_failure_boundaries(color_context,monkeypatch,failure):
    from video_ai.media import colorimetry as c
    from video_ai.runtime.processes import CommandResult
    run,kw,_=color_context
    path=run/'source.png';png(path,srgb=True)
    side,_=c.inspect_color_asset(entry(path),**kw)
    real=c.run_logged
    def broken(args,**kwargs):
        result=real(args,**kwargs)
        if '-filters' in args and failure=='capability':Path(result.stdout_path).write_bytes(b'no zscale')
        if '-f' in args and 'rawvideo' in args:
            if failure=='decode':return replace(result,returncode=1)
            if failure=='bytes':Path(result.stdout_path).write_bytes(b'bad size')
        return result
    monkeypatch.setattr(c,'run_logged',broken)
    if failure=='capability':
        record,_=c.decode_analysis_frame(side,frame_index=0,**kw)
        assert record['status']=='unverified' and record['pixels'] is None
        assert any(r['code']=='missing_zscale' for r in record['risks'])
    else:
        with pytest.raises(RuntimeError if failure=='decode' else ValueError):c.decode_analysis_frame(side,frame_index=0,**kw)
        assert not (kw['logger'].root/'colorimetry/sample/analysis/frame_000000.json').exists()


def test_processing_wrong_input_sha_is_refused_without_success(color_context):
    from video_ai.media.colorimetry import inspect_color_asset
    run,kw,_=color_context
    source=run/'original.png';png(source,srgb=True)
    target=run/'output.mp4'
    cmd=command(color_context,[kw['config'].tools['ffmpeg'],'-nostdin','-n','-v','error','-loop','1','-i',source,
        '-frames:v','16','-r','16','-c:v','libx264',target])
    origin=thaw(hash_file(source));origin['sha256']='0'*64
    rec=run/'wrong-receipt.json';rec.write_text(json.dumps(dict(source=origin,target=thaw(hash_file(target)),command=cmd)))
    with pytest.raises(OSError):inspect_color_asset(entry(target,records=[thaw(hash_file(rec))]),**kw)
    assert not (kw['logger'].root/'colorimetry/sample/sidecar.json').exists()


@pytest.mark.parametrize('range_name',['tv','pc'])
def test_bt709_chroma_matrix_from_independent_color_patch_formula(color_context,range_name):
    from video_ai.media.colorimetry import inspect_color_asset,decode_analysis_frame
    run,kw,_=color_context
    colors=[(.25,.5,.75),(.75,.5,.25),(.3,.6,.4),(0.,0.,0.)]
    codes=[]
    for red,green,blue in colors:
        y=.2126*red+.7152*green+.0722*blue
        cb=(blue-y)/1.8556;cr=(red-y)/1.5748
        codes.append((round(16+219*y),round(128+224*cb),round(128+224*cr)) if range_name=='tv'
                     else (round(255*y),round(128+255*cb),round(128+255*cr)))
    yplane=bytes(codes[(y//16)*2+x//16][0] for y in range(32) for x in range(32))
    uplane=bytes(codes[(y//8)*2+x//8][1] for y in range(16) for x in range(16))
    vplane=bytes(codes[(y//8)*2+x//8][2] for y in range(16) for x in range(16))
    raw=run/'patches.yuv';raw.write_bytes((yplane+uplane+vplane)*16)
    target=run/'patches.mp4'
    tags=['-colorspace','bt709','-color_primaries','bt709','-color_trc','iec61966-2-1','-color_range',range_name]
    command(color_context,[kw['config'].tools['ffmpeg'],'-nostdin','-n','-v','error','-f','rawvideo',
        '-pixel_format','yuv420p','-video_size','32x32','-framerate','16',*tags,'-i',raw,
        '-frames:v','16','-c:v','libx264','-crf','0','-pix_fmt','yuv420p',*tags,
        '-x264-params','colorprim=bt709:transfer=iec61966-2-1:colormatrix=bt709',target])
    side,_=inspect_color_asset(entry(target),**kw)
    record,_=decode_analysis_frame(side,frame_index=0,**kw)
    pixels=Path(record['pixels']['path']).read_bytes()
    for (x,y),expected in zip([(8,8),(24,8),(8,24),(24,24)],colors):
        actual=pixels[(y*32+x)*3:(y*32+x)*3+3]
        assert all(abs(a-round(b*255))<=2 for a,b in zip(actual,expected))
