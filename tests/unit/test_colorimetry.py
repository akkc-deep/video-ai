"""Independent color evidence; declarations never imply quality approval."""
from copy import deepcopy
import importlib

import pytest


COLORS = dict(color_space='bt709', color_primaries='bt709',
              color_transfer='bt709', color_range='tv')


def probe_data(**colors):
    stream = dict(index=0, codec_type='video', codec_name='h264', pix_fmt='yuv420p',
                  width=32, height=32, time_base='1/16384', r_frame_rate='16/1',
                  avg_frame_rate='16/1', nb_read_frames='2', nb_frames='2', duration='0.125',
                  **colors)
    frames = [dict(media_type='video', stream_index=0, pts=i*1024, **colors) for i in range(2)]
    return dict(streams=[stream], format=dict(format_name='mov,mp4', duration='0.125')), dict(frames=frames)


def parser():
    # Missing public interface is a behavior failure, not a collection error.
    from video_ai.media import __path__
    assert importlib.util.find_spec('video_ai.media.colorimetry') is not None, 'colorimetry interface missing'
    return importlib.import_module('video_ai.media.colorimetry').parse_color_probe


def test_missing_colors_exact_schema_and_legacy_probe_unchanged():
    from video_ai.media.video import validate_video_probe
    p, f = probe_data()
    before = deepcopy((p, f))
    old = validate_video_probe(p, f, width=32, height=32)
    result = parser()(p, f)
    assert set(result) == {'video', 'png_metadata', 'interpretation', 'risks'}
    assert set(result['video']) == {'codec_name', 'pix_fmt', 'width', 'height', 'encoder',
        *COLORS, 'time_base', 'r_frame_rate', 'avg_frame_rate', 'frames'}
    assert result['video']['frames'] == f['frames']
    assert result['video']['color_space'] == dict(raw=None, value='unknown')
    assert result['interpretation']['status'] == 'unknown'
    assert any(r['code'] == 'missing_color_metadata' for r in result['risks'])
    assert (p, f) == before
    assert validate_video_probe(p, f, width=32, height=32) == old == dict(
        width=32, height=32, codec='h264', pixel_format='yuv420p', fps=16, frames=2, duration=.125)


def test_stream_frame_conflict_keeps_exact_frame_number_and_original():
    p, f = probe_data(**COLORS)
    f['frames'][1]['color_range'] = 'pc'
    result = parser()(p, f)
    assert result['interpretation']['status'] == 'conflicting'
    assert result['interpretation']['conflicts'] == [dict(
        frame_index=1, field='color_range', stream_value='tv', frame_value='pc')]
    assert result['video']['frames'][1]['color_range'] == 'pc'


@pytest.mark.parametrize('changes,status', [({}, 'resolved'),
    ({'color_transfer': 'smpte2084'}, 'unsupported'),
    ({'color_space': 'some-future-matrix'}, 'unsupported'),
    ({'color_range': 'unspecified'}, 'unknown')])
def test_supported_unknown_and_unsupported(changes, status):
    p, f = probe_data(**dict(COLORS, **changes))
    result = parser()(p, f)
    assert result['interpretation']['status'] == status
    assert result['video']['color_space']['raw'] == p['streams'][0]['color_space']


def test_missing_frame_tag_does_not_override_stream_and_audio_is_allowed():
    p, f = probe_data(**COLORS)
    f['frames'][0].pop('color_range')
    p['streams'].append(dict(codec_type='audio', codec_name='aac'))
    assert parser()(p, f)['interpretation']['status'] == 'resolved'


def png_probe():
    p, f = probe_data()
    p['streams'][0].update(codec_name='png', pix_fmt='rgb24', nb_read_frames='1')
    f['frames'] = f['frames'][:1]
    return p, f


@pytest.mark.parametrize('metadata,status', [
    (dict(srgb_intent=None, gamma=None, chromaticities=None, icc_sha256=None), 'unknown'),
    (dict(srgb_intent=0, gamma=45455, chromaticities=None, icc_sha256=None), 'resolved'),
    (dict(srgb_intent=0, gamma=100000, chromaticities=None, icc_sha256=None), 'conflicting'),
    (dict(srgb_intent=None, gamma=None, chromaticities=None, icc_sha256='a'*64), 'unsupported')])
def test_png_profiles_are_required_and_conflicts_preserved(metadata, status):
    result = parser()(*png_probe(), png_metadata=metadata)
    assert result['interpretation']['status'] == status
    assert result['video']['time_base'] is None
    assert result['video']['avg_frame_rate'] is None
    assert result['png_metadata'] == metadata


def entry(path, **changes):
    return dict(asset_id='sample', stage='generated', path=str(path),
                mapping=dict(rows=[], evidence=[]), processing=dict(operation='test fixture',
                upstream_ids=[], command_records=[]), **changes)


@pytest.fixture
def audit_context(runtime_run):
    from dataclasses import replace
    from pathlib import Path
    from video_ai.config import load_config
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    run, config, paths = runtime_run
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config = replace(config, tools=dict(config.tools, ffmpeg=actual.tools['ffmpeg'], ffprobe=actual.tools['ffprobe']))
    return run, dict(config=config, paths=paths, logger=RunLogger(create_run(paths)))


def test_runtime_interfaces_exist():
    module = importlib.import_module('video_ai.media.colorimetry')
    for name in ('inspect_color_asset', 'decode_analysis_frame', 'inspect_color_chain'):
        assert callable(getattr(module, name, None)), name


def test_readonly_reader_interface_and_empty_input(audit_context):
    module = importlib.import_module('video_ai.media.colorimetry')
    reader = getattr(module, 'load_color_analysis_set', None)
    assert callable(reader), 'read-only batch evidence reader missing'
    with pytest.raises(ValueError):
        reader([], config=audit_context[1]['config'])


def _reader_fixture(audit_context):
    import json
    import struct
    import zlib
    from video_ai.media.colorimetry import inspect_color_asset, decode_analysis_frame
    run, kw = audit_context
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    path = run/'reader.png'
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB',32,32,8,2,0,0,0))+
        chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress((b'\0'+bytes([90,120,150])*32)*32))+chunk(b'IEND',b''))
    side, _ = inspect_color_asset(entry(path), **kw)
    record, _ = decode_analysis_frame(side, frame_index=0, **kw)
    record_path = kw['logger'].root/'colorimetry/sample/analysis/frame_000000.json'
    return record_path, record


def test_reader_is_lazy_readonly_and_checks_exit_drift(audit_context, monkeypatch):
    import os
    from pathlib import Path
    import video_ai.media.colorimetry as c
    factory = getattr(c, 'load_color_analysis_set', None)
    assert callable(factory), 'read-only batch evidence reader missing'
    path, record = _reader_fixture(audit_context)
    run, kw = audit_context
    roots = [run, kw['logger'].run_dir]
    def snapshot():
        return {str(p):(p.stat().st_size,p.stat().st_mtime_ns) for root in roots for p in root.rglob('*')}
    before = snapshot()
    def forbidden(*args, **kwargs):
        raise AssertionError('reader must not instantiate a RunLogger or execute commands')
    monkeypatch.setattr(c, 'RunLogger', forbidden)
    monkeypatch.setattr(c, 'run_logged', forbidden)
    with factory([str(path)], config=kw['config']) as reader:
        assert reader.schema_version == 1 and reader.algorithm == 'colorimetry_evidence_v1'
        assert len(reader.frames) == len(reader.sidecars) == 1
        assert set(reader.frames[0]) == {'record_identity','record','sidecar_identity'}
        assert 'rgb24' not in reader.frames[0]
        assert len(reader.read_rgb(str(path))) == 3072
        assert len({i['path'] for i in reader.identities}) == len(reader.identities)
    assert snapshot() == before
    pixels = Path(record['pixels']['path'])
    with pytest.raises(OSError):
        with factory([str(path)], config=kw['config']):
            stamp = pixels.stat(); raw = pixels.read_bytes()
            pixels.write_bytes(bytes([raw[0]^1])+raw[1:])
            os.utime(pixels, ns=(stamp.st_atime_ns,stamp.st_mtime_ns))


@pytest.mark.parametrize('field', ['frame_index','command','pixels','mapping','status'])
def test_reader_rejects_forged_analysis_evidence(audit_context, field):
    import json
    import video_ai.media.colorimetry as c
    factory = getattr(c, 'load_color_analysis_set', None)
    assert callable(factory), 'read-only batch evidence reader missing'
    path, record = _reader_fixture(audit_context)
    if field == 'frame_index': record[field] = True
    elif field == 'command': record[field]['args'][-2] = 'not_rawvideo'
    elif field == 'pixels': record[field]['sha256'] = '0'*64
    elif field == 'mapping': record[field] = dict(asset_frame_index=0)
    else: record[field] = 'unverified'
    path.write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises((ValueError,OSError)):
        with factory([str(path)], config=audit_context[1]['config']): pass


def test_reader_rejects_oversized_original_probe_before_loading(audit_context):
    import json
    from pathlib import Path
    from video_ai.runtime.manifest import hash_file,thaw
    import video_ai.media.colorimetry as c
    path,record=_reader_fixture(audit_context);sidepath=Path(record['sidecar']['path'])
    side=json.loads(sidepath.read_text(encoding='utf-8'));probe=Path(side['probe']['raw_probe']['path'])
    with probe.open('ab') as file:file.write(b' '*16777216)
    side['probe']['raw_probe']=thaw(hash_file(probe));sidepath.write_text(json.dumps(side),encoding='utf-8')
    record['sidecar']=thaw(hash_file(sidepath));path.write_text(json.dumps(record),encoding='utf-8')
    with pytest.raises(ValueError,match='resource_limit'):
        with c.load_color_analysis_set([str(path)],config=audit_context[1]['config']):pass


@pytest.mark.parametrize('change', ['bool', 'extra', 'duplicate', 'nonlocal', 'source_logger'])
def test_invalid_entry_refused_before_commands(audit_context, change):
    from video_ai.media.colorimetry import inspect_color_asset
    from video_ai.runtime.logging import RunLogger
    run, kw = audit_context
    path = run/'sample.mp4'; path.write_bytes(b'not executed')
    data = entry(path)
    row = dict(asset_frame_index=0, clip_id=None, generated_frame_index=0,
               retained_frame_index=None, output_frame_index=None, pts=0, time_base='1/16')
    data['mapping']['rows'] = [row]
    if change == 'bool': row['asset_frame_index'] = True
    if change == 'extra': data['surprise'] = True
    if change == 'duplicate': data['mapping']['rows'].append(deepcopy(row))
    if change == 'nonlocal': data['path'] = '//server/share/sample.mp4'
    if change == 'source_logger': kw['logger'] = RunLogger(run)
    with pytest.raises(ValueError):
        inspect_color_asset(data, **kw)
    assert not list(kw['logger'].root.glob('processes/*'))


def test_chain_cycle_duplicate_and_order_refused(audit_context):
    from video_ai.media.colorimetry import inspect_color_chain
    run, kw = audit_context
    path = run/'sample.mp4'; path.write_bytes(b'not executed')
    a = entry(path); b = deepcopy(a); b['asset_id'] = 'b'
    for entries in ([a, a], [dict(a, processing=dict(a['processing'], upstream_ids=['sample']))],
                    [dict(a, processing=dict(a['processing'], upstream_ids=['b'])), b]):
        with pytest.raises(ValueError): inspect_color_chain(entries, **kw)
    assert not list(kw['logger'].root.glob('processes/*'))


def test_png_crc_and_duplicate_chunks(audit_context):
    import struct
    import zlib
    from video_ai.media.colorimetry import inspect_color_asset
    run, kw = audit_context
    def chunk(kind, payload):
        return struct.pack('>I', len(payload))+kind+payload+struct.pack('>I', zlib.crc32(kind+payload))
    header = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 1,1,8,2,0,0,0))
    pixels = chunk(b'IDAT', zlib.compress(b'\0\xff\0\0'))
    data = header+chunk(b'sRGB', b'\0')+chunk(b'sRGB', b'\0')+pixels+chunk(b'IEND', b'')
    path=run/'duplicate.png'; path.write_bytes(data)
    result, _ = inspect_color_asset(entry(path), **kw)
    assert result['interpretation']['status'] == 'conflicting'
    path=run/'bad.png'; path.write_bytes(data[:-1]+bytes([data[-1]^1]))
    with pytest.raises(ValueError, match='CRC'):
        inspect_color_asset(dict(entry(path), asset_id='bad'), **kw)


@pytest.mark.parametrize('role', ['source','evidence','tool'])
def test_same_stat_drift_after_command_is_rejected(audit_context, monkeypatch, role):
    import os
    from video_ai.media import colorimetry as c
    from video_ai.runtime.processes import CommandResult
    from video_ai.runtime.manifest import now
    run,kw=audit_context
    path=run/(role+'.bin');path.write_bytes(b'original')
    session=c._Session(**kw,deadline=c._deadline(30,c.monotonic()))
    session.freeze(path)
    def mutate(args, **kwargs):
        stamp=path.stat();path.write_bytes(b'modified');os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        stdout=kw['logger'].save_bytes('processes/test.stdout',b'')
        stderr=kw['logger'].save_bytes('processes/test.stderr',b'')
        return CommandResult(tuple(args),kwargs['cwd'],0,False,stdout,stderr,now(),now())
    monkeypatch.setattr(c,'run_logged',mutate)
    with pytest.raises(OSError): session.command([str(path)],'test')
    assert not list(kw['logger'].root.glob('colorimetry/**/sidecar.json'))


def test_command_timeout_preserves_timeout_exception_and_evidence(audit_context, monkeypatch):
    import subprocess
    from video_ai.media import colorimetry as c
    from video_ai.runtime.processes import CommandResult
    from video_ai.runtime.manifest import now
    _,kw=audit_context
    session=c._Session(**kw,deadline=c._deadline(30,c.monotonic()))
    def timeout(args, **kwargs):
        stdout=kw['logger'].save_bytes('processes/timeout.stdout',b'')
        stderr=kw['logger'].save_bytes('processes/timeout.stderr',b'timeout')
        session.deadline=c.monotonic()-1
        return CommandResult(tuple(args),kwargs['cwd'],-1,True,stdout,stderr,now(),now())
    monkeypatch.setattr(c,'run_logged',timeout)
    with pytest.raises(subprocess.TimeoutExpired): session.command(['D:/VideoSi/tools/fake.exe'],'test')
    assert (kw['logger'].root/'processes/timeout.stderr').read_bytes()==b'timeout'


@pytest.mark.parametrize('mutation', ['count_bool','index_bool','missing_pts','mixed_pixfmt','frame_dimensions'])
def test_malformed_decoded_frames_are_rejected(mutation):
    p,f=probe_data(**COLORS)
    if mutation=='count_bool':p['streams'][0]['nb_read_frames']=True
    if mutation=='index_bool':f['frames'][0]['stream_index']=False
    if mutation=='missing_pts':f['frames'][0].pop('pts')
    if mutation=='mixed_pixfmt':f['frames'][1]['pix_fmt']='yuv420p10le'
    if mutation=='frame_dimensions':f['frames'][1]['width']=64
    with pytest.raises(ValueError):parser()(p,f)


def test_one_tagged_frame_cannot_resolve_an_otherwise_unmarked_asset():
    p,f=probe_data()
    f['frames'][0].update(COLORS)
    result=parser()(p,f)
    assert result['interpretation']['status']=='unknown'
    assert all(v=='unknown' for v in result['interpretation']['values'].values())


@pytest.mark.parametrize('pixel_format',['rgb48be','rgba'])
def test_unsupported_png_format_has_explicit_reason(pixel_format):
    p,f=png_probe();p['streams'][0]['pix_fmt']=pixel_format
    result=parser()(p,f,png_metadata=dict(srgb_intent=0,gamma=None,chromaticities=None,icc_sha256=None))
    assert result['interpretation']['status']=='unsupported'
    assert any(r['code']=='unsupported_color_interpretation' for r in result['risks'])


def test_original_native_tail_record_without_timing_proof_cannot_verify_mapping(audit_context):
    import json
    from video_ai.media.colorimetry import _mapping_verified
    from video_ai.runtime.manifest import hash_file,thaw
    run,_=audit_context
    path=run/'native.png';path.write_bytes(b'fixture identity only')
    identity=thaw(hash_file(path))
    record=run/'last-frame.json';record.write_text(json.dumps(dict(image=identity,
        clip_id='clip_1',source_frame_index=14,global_output_frame_index=13)))
    data=entry(path);data['stage']='native_tail'
    data['mapping']=dict(evidence=[thaw(hash_file(record))],rows=[dict(asset_frame_index=0,
        clip_id='clip_1',generated_frame_index=14,retained_frame_index=99,output_frame_index=13,pts=999999,time_base='1/1')])
    assert not _mapping_verified(data,identity)
