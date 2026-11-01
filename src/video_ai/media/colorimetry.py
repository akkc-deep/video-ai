"""Read-only color declarations and explicit CPU SDR analysis in a separate run.

Resolved metadata describes an interpretation, never media quality or camera intent.
No production pipeline imports this optional diagnostic module.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from time import monotonic
import zlib

from .images import _deadline, _remaining
from ..planning.production_scenes import canonical_digest
from ..runtime.environment import build_child_env
from ..runtime.logging import RunLogger
from ..runtime.manifest import hash_file, thaw, now, validate_run_dir, _timestamp
from ..runtime.paths import RUNTIME_ROOT, _validate_spelling
from ..runtime.processes import run_logged


ALGORITHM = 'colorimetry_v1'
SPACE = 'srgb_rgb24_v1'
COLORS = ('color_space', 'color_primaries', 'color_transfer', 'color_range')
PNG_FIELDS = ('srgb_intent', 'gamma', 'chromaticities', 'icc_sha256')
YUV8 = {'yuv420p', 'yuv422p', 'yuv444p', 'yuvj420p', 'yuvj422p', 'yuvj444p'}
SRGB_CHROMA = [31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000]


def _object(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError(f'{label}: exact fields required')


def _int(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{label}: integer >= {minimum} required')
    return value


def _probe_int(value, label, minimum=0):
    if isinstance(value, str) and value.lstrip('-').isascii() and value.lstrip('-').isdigit():
        value = int(value)
    return _int(value, label, minimum)


def _value(value):
    return 'unknown' if value is None or value in ('', 'unknown', 'unspecified', 'N/A') else value


def _risk(code, detail, frame_index=None):
    return dict(code=code, detail=detail, frame_index=frame_index)


def _png_values(metadata):
    _object(metadata, PNG_FIELDS, 'PNG metadata')
    for field in ('srgb_intent', 'gamma'):
        if metadata[field] is not None:
            _int(metadata[field], field, 0 if field == 'srgb_intent' else 1)
    if metadata['srgb_intent'] is not None and metadata['srgb_intent'] > 3:
        raise ValueError('invalid sRGB rendering intent')
    chroma = metadata['chromaticities']
    if chroma is not None:
        if type(chroma) is not list or len(chroma) != 8:
            raise ValueError('cHRM requires eight raw integers')
        for n in chroma:
            _int(n, 'chromaticity')
    icc = metadata['icc_sha256']
    if icc is not None and (not isinstance(icc, str) or len(icc) != 64 or
                            any(c not in '0123456789abcdef' for c in icc)):
        raise ValueError('invalid iCCP digest')


def parse_color_probe(probe, frame_data, *, png_metadata=None):
    """Preserve raw ffprobe fields; interpret only complete supported declarations."""
    if type(probe) is not dict or type(frame_data) is not dict:
        raise ValueError('probe and frame data must be objects')
    streams = probe.get('streams')
    if type(streams) is not list or any(type(s) is not dict for s in streams):
        raise ValueError('streams required')
    videos = [s for s in streams if s.get('codec_type') == 'video']
    if len(videos) != 1:
        raise ValueError('exactly one video stream required (audio allowed)')
    stream = videos[0]
    frames = frame_data.get('frames')
    if type(frames) is not list or not frames:
        raise ValueError('complete decoded frames required')
    if _probe_int(stream.get('nb_read_frames'), 'decoded count', 1) != len(frames):
        raise ValueError('decoded count differs from all-frame probe')
    stream_index = _probe_int(stream.get('index'), 'stream index')
    previous = None
    for frame in frames:
        if type(frame) is not dict or frame.get('media_type') != 'video' or _probe_int(frame.get('stream_index'), 'frame stream index') != stream_index:
            raise ValueError('frames must belong to the selected video stream')
        if stream.get('codec_name') != 'png':
            timestamps = [_probe_int(frame[key], key, -(2**63)) for key in ('pts','best_effort_timestamp') if key in frame]
            if not timestamps or len(set(timestamps)) != 1 or (previous is not None and timestamps[0] <= previous):
                raise ValueError('reliable ordered decoded PTS required')
            previous = timestamps[0]
        for key in ('pix_fmt','width','height'):
            if key in frame and (type(frame[key]) is not type(stream.get(key)) or frame[key] != stream.get(key)):
                raise ValueError('decoded frame format/dimensions differ from stream')
    video = {k: deepcopy(stream.get(k, 'unknown')) for k in
             ('codec_name', 'pix_fmt', 'width', 'height', 'time_base', 'r_frame_rate', 'avg_frame_rate')}
    for key in ('width', 'height'):
        _int(video[key], key, 1)
    video['encoder'] = dict(stream=deepcopy(stream.get('tags', {}).get('encoder', 'unknown')),
                            format=deepcopy(probe.get('format', {}).get('tags', {}).get('encoder', 'unknown')))
    video['frames'] = deepcopy(frames)
    values, evidence, conflicts, risks = {}, [], [], []
    for key in COLORS:
        raw = stream.get(key)
        if raw is not None and type(raw) is not str:
            raise ValueError('color declarations must be strings')
        video[key] = dict(raw=raw, value=_value(raw))
        baseline = _value(raw)
        if baseline != 'unknown':
            evidence.append(f'stream.{key}={raw}')
        for index, frame in enumerate(frames):
            declared = _value(frame.get(key))
            if type(declared) is not str:
                raise ValueError('frame color declaration must be a string')
            if declared == 'unknown':
                continue
            if baseline == 'unknown':
                baseline = declared
            elif declared != baseline:
                conflicts.append(dict(frame_index=index, field=key,
                                      stream_value=baseline, frame_value=declared))
            evidence.append(f'frame[{index}].{key}={declared}')
        values[key] = ('unknown' if _value(raw)=='unknown' and
                       any(_value(f.get(key))=='unknown' for f in frames) else baseline)
    png = video['codec_name'] == 'png'
    if png:
        if len(frames) != 1:
            raise ValueError('a PNG asset must have exactly one frame')
        video.update(time_base=None, r_frame_rate=None, avg_frame_rate=None)
        if png_metadata is None:
            png_metadata = dict.fromkeys(PNG_FIELDS)
        _png_values(png_metadata)
        if png_metadata['srgb_intent'] is not None:
            target = dict(color_space='gbr', color_primaries='bt709',
                          color_transfer='iec61966-2-1', color_range='pc')
            for key, wanted in target.items():
                if values[key] not in ('unknown', wanted):
                    conflicts.append(dict(frame_index=0, field=key, stream_value=values[key], frame_value=wanted))
            values = target
            evidence.append('PNG.sRGB')
            for key, wanted in (('gamma', 45455), ('chromaticities', SRGB_CHROMA), ('icc_sha256', None)):
                if png_metadata[key] is not None and png_metadata[key] != wanted:
                    conflicts.append(dict(frame_index=0, field='PNG.'+key,
                                          stream_value=wanted, frame_value=deepcopy(png_metadata[key])))
        else:
            # PNG integer samples are full range; no transfer/primaries inference.
            values['color_range'] = 'pc'
    elif png_metadata is not None:
        raise ValueError('PNG metadata supplied for a non-PNG stream')
    missing = [key for key in COLORS if values[key] == 'unknown']
    supported = (video['pix_fmt'] in YUV8 and values == dict(color_space='bt709', color_primaries='bt709',
        color_transfer=values['color_transfer'], color_range=values['color_range']) and
        values['color_transfer'] in ('bt709', 'iec61966-2-1') and values['color_range'] in ('tv', 'pc'))
    if png:
        supported = video['pix_fmt'] == 'rgb24' and png_metadata['srgb_intent'] is not None
    unsupported = ((png and (png_metadata['icc_sha256'] is not None or video['pix_fmt'] != 'rgb24')) or
        (not png and video['pix_fmt'] not in YUV8) or
        any(values[k] != 'unknown' and values[k] not in allowed for k, allowed in (
            ('color_space', ('gbr',) if png else ('bt709',)), ('color_primaries', ('bt709',)),
            ('color_transfer', ('bt709', 'iec61966-2-1')), ('color_range', ('tv', 'pc')))))
    status = 'conflicting' if conflicts else 'unsupported' if unsupported else 'unknown' if missing or not supported else 'resolved'
    if missing or (png and png_metadata['srgb_intent'] is None):
        risks.append(_risk('missing_color_metadata', 'Missing supported declarations: '+', '.join(missing or ['PNG.sRGB'])))
    for conflict in conflicts:
        risks.append(_risk('conflicting_color_metadata', str(conflict), conflict['frame_index']))
    if status == 'unsupported':
        risks.append(_risk('unsupported_color_interpretation', f'Unsupported SDR interpretation: {values}, {video["pix_fmt"]}'))
    return dict(video=video, png_metadata=deepcopy(png_metadata),
                interpretation=dict(status=status, values=values, evidence=evidence, conflicts=conflicts), risks=risks)


STAGES = ('generated', 'native_tail', 'retained', 'upscaled', 'composition')
ROW_FIELDS = 'asset_frame_index clip_id generated_frame_index retained_frame_index output_frame_index pts time_base'.split()
IDENTITY_FIELDS = 'path bytes mtime_ns sha256 verified_at'.split()
SIDECAR_FIELDS = 'schema_version algorithm asset_id stage source input_sha256 mapping processing probe interpretation analysis_space commands tools risks created_at'.split()


def _local_file(value):
    text = _validate_spelling(value)
    if '..' in re.split(r'[/\\]', text) or '.' in re.split(r'[/\\]', text):
        raise ValueError('path traversal/alias forbidden')
    path = Path(text)
    if not path.is_absolute() or not path.is_relative_to(RUNTIME_ROOT):
        raise ValueError('explicit local D:/VideoSi file required')
    if path != path.resolve(strict=True) or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError('redirected file path forbidden')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('regular non-aliased file required')
    return path


def _identity_shape(value):
    _object(value, IDENTITY_FIELDS, 'FileIdentity')
    path = _local_file(value['path'])
    _int(value['bytes'], 'bytes')
    _int(value['mtime_ns'], 'mtime_ns')
    _timestamp(value['verified_at'])
    if type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ValueError('full SHA256 identity required')
    return path


def _identity(value):
    path = _identity_shape(value)
    actual = thaw(hash_file(path))
    if any(actual[k] != value[k] for k in ('path', 'bytes', 'mtime_ns', 'sha256')):
        raise OSError(f'frozen file bytes changed: {path}')
    return deepcopy(value)


def _audit(paths, logger):
    paths.validate()
    if not isinstance(logger, RunLogger) or logger.production:
        raise ValueError('independent non-production audit logger required')
    run = validate_run_dir(logger.run_dir)
    if run.parent != paths.runs_root or logger.root != run/'logs':
        raise ValueError('audit logger location differs')
    if any(p.name != 'logs' for p in run.iterdir()):
        raise ValueError('audit run must be created independently of production inputs')
    if any(p.name not in {'colorimetry', 'events.jsonl', 'processes', 'errors'} for p in logger.root.iterdir()):
        raise ValueError('logger contains unrelated production evidence')
    for path in (run, logger.root):
        if path != path.resolve() or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
            raise ValueError('redirected audit run')


def _entry(entry, logger=None, *, audit_root=None, identity_check=None):
    _object(entry, 'asset_id stage path mapping processing'.split(), 'entry')
    data = deepcopy(entry)
    if type(data['asset_id']) is not str or not re.fullmatch('[A-Za-z0-9_-]+', data['asset_id']):
        raise ValueError('ASCII asset_id required')
    if data['stage'] not in STAGES:
        raise ValueError('unknown stage')
    path = _local_file(data['path'])
    audit_root = logger.run_dir if logger is not None else audit_root
    identity_check = identity_check or _identity
    if path.suffix.lower() not in ('.mp4', '.png') or path.is_relative_to(audit_root):
        raise ValueError('source MP4/PNG must be outside the audit run')
    data['path'] = str(path)
    mapping = data['mapping']; _object(mapping, ('rows', 'evidence'), 'mapping')
    if type(mapping['rows']) is not list or type(mapping['evidence']) is not list:
        raise ValueError('mapping rows/evidence must be lists')
    seen = set()
    for row in mapping['rows']:
        _object(row, ROW_FIELDS, 'mapping row')
        index = _int(row['asset_frame_index'], 'asset_frame_index')
        if index in seen: raise ValueError('duplicate local frame mapping')
        seen.add(index)
        if row['clip_id'] is not None and (type(row['clip_id']) is not str or not row['clip_id'].strip()):
            raise ValueError('clip_id must be text or null')
        for key in ('generated_frame_index', 'retained_frame_index', 'output_frame_index'):
            if row[key] is not None: _int(row[key], key)
        if (row['pts'] is None) != (row['time_base'] is None):
            raise ValueError('PTS and time_base must be supplied together')
        if row['pts'] is not None:
            _int(row['pts'], 'pts', -(2**63))
            if type(row['time_base']) is not str or not re.fullmatch('[0-9]+/[0-9]+', row['time_base']):
                raise ValueError('positive rational time_base required')
            try: valid = Fraction(row['time_base']) > 0
            except ZeroDivisionError: valid = False
            if not valid: raise ValueError('positive time_base required')
    processing = data['processing']
    _object(processing, ('operation', 'upstream_ids', 'command_records'), 'processing')
    if type(processing['operation']) is not str or not processing['operation'].strip():
        raise ValueError('operation description required')
    ids = processing['upstream_ids']
    if type(ids) is not list or any(type(i) is not str or not re.fullmatch('[A-Za-z0-9_-]+', i) for i in ids) or len(set(ids)) != len(ids) or data['asset_id'] in ids:
        raise ValueError('invalid/duplicate/self upstream IDs')
    if type(processing['command_records']) is not list:
        raise ValueError('command_records must be a list')
    for identity in [*mapping['evidence'], *processing['command_records']]:
        identity_check(identity)
        if Path(identity['path']).is_relative_to(audit_root):
            raise ValueError('input evidence must be outside audit run')
    return data


def _png_metadata(path):
    """Validate every chunk CRC; keep raw integer declarations, never inflate ICC."""
    metadata, conflicts, seen = dict.fromkeys(PNG_FIELDS), [], set()
    with path.open('rb') as file:
        if file.read(8) != b'\x89PNG\r\n\x1a\n': raise ValueError('invalid PNG signature')
        first = True
        while True:
            header = file.read(8)
            if len(header) != 8: raise ValueError('truncated PNG')
            size, kind = struct.unpack('>I4s', header)
            if size > path.stat().st_size: raise ValueError('invalid PNG chunk length')
            data = file.read(size); crc = file.read(4)
            if len(data) != size or len(crc) != 4 or zlib.crc32(kind+data) != struct.unpack('>I', crc)[0]:
                raise ValueError('invalid PNG CRC')
            if first and (kind != b'IHDR' or size != 13): raise ValueError('PNG IHDR required')
            first = False
            if kind in (b'sRGB', b'gAMA', b'cHRM', b'iCCP'):
                if kind in seen:
                    conflicts.append(dict(frame_index=0, field='PNG.'+kind.decode(), stream_value='single chunk', frame_value='duplicate chunk'))
                seen.add(kind)
                if kind == b'sRGB':
                    if size != 1: raise ValueError('invalid sRGB chunk')
                    metadata['srgb_intent'] = data[0]
                elif kind == b'gAMA':
                    if size != 4: raise ValueError('invalid gAMA chunk')
                    metadata['gamma'] = struct.unpack('>I', data)[0]
                elif kind == b'cHRM':
                    if size != 32: raise ValueError('invalid cHRM chunk')
                    metadata['chromaticities'] = list(struct.unpack('>8I', data))
                else:
                    if b'\0' not in data or len(data.split(b'\0',1)[0]) not in range(1,80):
                        raise ValueError('invalid iCCP chunk')
                    metadata['icc_sha256'] = hashlib.sha256(header+data+crc).hexdigest()
            if kind == b'IEND':
                if size != 0 or file.read(1): raise ValueError('invalid PNG end/trailing bytes')
                break
    _png_values(metadata)
    return metadata, conflicts


class _Session:
    def __init__(self, *, config, paths, logger, deadline):
        _audit(paths, logger)
        self.config, self.paths, self.logger, self.deadline = config, paths, logger, deadline
        self.frozen, self.outputs = {}, []

    def freeze(self, path):
        path = _local_file(path)
        identity = thaw(hash_file(path))
        old = self.frozen.get(str(path))
        if old is not None and any(old[k] != identity[k] for k in ('bytes', 'mtime_ns', 'sha256')):
            raise OSError(f'file changed: {path}')
        self.frozen[str(path)] = old or identity
        return deepcopy(self.frozen[str(path)])

    def verify(self, *, budget=True):
        for identity in self.frozen.values(): _identity(identity)
        if budget: _remaining(self.deadline, monotonic())

    def command(self, args, asset_id):
        self.verify()
        timeout = min(300, _remaining(self.deadline, monotonic()))
        result = run_logged(tuple(str(a) for a in args), cwd=self.logger.run_dir,
            env=build_child_env(self.paths), timeout=timeout,
            logger=self.logger, stage='colorimetry', unit_id=asset_id)
        self.outputs.extend([result.stdout_path, result.stderr_path])
        self.verify(budget=not result.timed_out)
        if result.timed_out:
            raise subprocess.TimeoutExpired(result.args, timeout)
        if result.returncode != 0:
            raise RuntimeError(f'colorimetry command failed: {result.stderr_path}')
        return thaw(result)

    def save(self, name, data):
        self.verify()
        _absent(self.logger, name)
        path = self.logger.save_json(name, data)
        self.outputs.append(path)
        return path


def _absent(logger, name):
    path = logger.path(name)
    if path != logger.root/name or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError('redirected audit output')
    if path.exists() or path.is_symlink(): raise FileExistsError(path)
    return path


def _artifact_matches(value, identity):
    return (isinstance(value, dict) and isinstance(identity, dict) and
            all(k in identity and value.get(k)==identity[k] for k in ('path','bytes','sha256')))


COMMAND_FIELDS = 'args cwd returncode timed_out stdout_path stderr_path started_at finished_at'.split()


def _command_record(command):
    _object(command, COMMAND_FIELDS, 'CommandResult')
    if (type(command['returncode']) is not int or command['returncode'] != 0 or command['timed_out'] is not False or
        type(command['args']) is not list or not command['args'] or any(type(a) is not str for a in command['args'])):
        raise ValueError('original successful command required')
    for key in ('cwd','stdout_path','stderr_path'): _validate_spelling(command[key])
    for key in ('started_at','finished_at'):
        _timestamp(command[key])


def _read_evidence_json(path,session=None):
    if isinstance(session,ColorAnalysisReader):return session._json(Path(path))
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _processing(data, source, session=None):
    result = deepcopy(data['processing']); rules = []
    for identity in result['command_records']:
        record = _read_evidence_json(identity['path'],session)
        if type(record) is not dict: continue
        cmd = record.get('command')
        target = record.get('target', record.get('output', {}))
        if isinstance(target, dict): target = target.get('identity', target)
        origin = record.get('source', {})
        if isinstance(origin, dict): origin = origin.get('identity', origin)
        if not _artifact_matches(target, source) or not isinstance(origin, dict):
            continue
        try: _command_record(cmd)
        except ValueError: continue
        if not all(k in origin for k in ('path','bytes','sha256')): continue
        actual = session.freeze(origin['path']) if session else thaw(hash_file(_local_file(origin['path'])))
        if not _artifact_matches(origin, actual): raise OSError('processing source bytes differ from original receipt')
        if session:
            session.freeze(origin['path'])
            for key in ('stdout_path','stderr_path'): session.freeze(cmd[key])
        args = cmd.get('args')
        if type(args) is not list or not args or any(type(a) is not str for a in args): continue
        # Only an original successful command with bound input/output bytes is used.
        if origin.get('path') not in args or not any(target['path'] == a for a in args): continue
        def option(key): return args[args.index(key)+1] if key in args and args.index(key)+1 < len(args) else None
        explicit = {key: option(key) for key in ('-colorspace', '-color_primaries', '-color_trc', '-color_range') if key in args}
        filt = option('-vf') or option('-filter_complex')
        converted = bool(filt and ('zscale=' in filt or 'colorspace=' in filt) and
                         all(token in filt for token in ('matrixin=', 'transferin=', 'primariesin=', 'rangein=')))
        rules.append(dict(args=deepcopy(args), filter=filt, encoder=option('-c:v'), pix_fmt=option('-pix_fmt'),
                          explicit_color_options=explicit,
                          conversion_status='explicit_conversion' if converted else 'implicit_ffmpeg_conversion'))
    result.update(status='recorded' if rules else 'unknown', rules=rules)
    return result


def _input_digest(data, source, tools):
    # verified_at is an observation timestamp, not stable content identity.
    def stable(identity): return {k: identity[k] for k in ('path', 'bytes', 'mtime_ns', 'sha256')}
    entry = deepcopy(data)
    for group, field in (('mapping', 'evidence'), ('processing', 'command_records')):
        entry[group][field] = [stable(i) for i in entry[group][field]]
    return canonical_digest(dict(entry=entry, source=stable(source),
        tools={k: stable(v['identity']) for k,v in tools.items()}, algorithm=ALGORITHM))


def _mapping_verified(data, source, session=None):
    """A file's presence is not proof: require byte binding and exact mapping rows.

    A normalized source/rows export is accepted as explicit recorded evidence.
    Historical clip mappings require their original clip digest binding as well.
    Unrecognized historical formats remain readable but unverified.
    """
    records = [_read_evidence_json(i['path'],session) for i in data['mapping']['evidence']]
    for record in records:
        if not isinstance(record, dict): continue
        bound = record.get('source')
        if isinstance(bound, dict): bound = bound.get('identity', bound)
        if (set(record) == {'source', 'rows'} and isinstance(bound, dict) and
            all(bound.get(k) == source[k] for k in ('path', 'bytes', 'sha256')) and record['rows'] == data['mapping']['rows']):
            return bool(record['rows'])
    # Exact native-tail records bind image, generated input and source frame index.
    if data['stage'] == 'native_tail' and len(data['mapping']['rows']) == 1:
        row = data['mapping']['rows'][0]
        for record in records:
            if not isinstance(record, dict): continue
            image = record.get('image', {})
            if (isinstance(image, dict) and all(image.get(k)==source[k] for k in ('path','bytes','sha256')) and
                record.get('source_frame_index') == row['generated_frame_index'] and
                record.get('clip_id') == row['clip_id'] and row['asset_frame_index'] == 0 and
                record.get('global_output_frame_index') == row['output_frame_index']):
                generated = record.get('generated', {})
                for probe in records:
                    if not isinstance(probe, dict) or not _artifact_matches(probe.get('info',{}).get('identity',{}), generated): continue
                    try:
                        source_frame = probe['frames']['frames'][row['generated_frame_index']]
                        stream = next(s for s in probe['probe']['streams'] if s.get('codec_type')=='video')
                        # Retained index additionally needs the original clip mapping.
                        clip_mapping = next((m for m in records if isinstance(m,dict) and
                            m.get('clip_id')==row['clip_id'] and isinstance(m.get('generated_to_retained'),list)), None)
                        if (clip_mapping is not None and clip_mapping['generated_to_retained'][row['generated_frame_index']]==row['retained_frame_index'] and
                            source_frame.get('pts')==row['pts'] and stream['time_base']==row['time_base']): return True
                    except (KeyError,IndexError,TypeError,StopIteration): pass
    for clip in records:
        if not isinstance(clip, dict): continue
        key = 'generated' if data['stage']=='generated' else 'source' if data['stage']=='retained' else None
        if key is None: continue
        bound = clip.get(key, {})
        if not isinstance(bound, dict) or not all(bound.get(k)==source[k] for k in ('path','bytes','sha256')): continue
        mapping = next((m for m in records if isinstance(m,dict) and canonical_digest(m)==clip.get('frame_mapping_sha256')), None)
        if mapping is None: continue
        valid = bool(data['mapping']['rows'])
        for row in data['mapping']['rows']:
            try:
                g = row['asset_frame_index'] if key=='generated' else mapping['retained_to_generated'][row['asset_frame_index']]
                r = mapping['generated_to_retained'][g]
                o = None if r is None else mapping['start_frame']+r
                valid &= (row['clip_id']==mapping['clip_id'] and row['generated_frame_index']==g and
                          row['retained_frame_index']==r and row['output_frame_index']==o)
            except (KeyError, IndexError, TypeError): valid=False
        if valid: return True
    return False


def _diagnostic_risks(parsed, data, source, processing,session=None):
    risks = deepcopy(parsed['risks'])
    if processing['status']=='unknown': risks.append(_risk('missing_processing_evidence', 'No original successful command binds the input and output bytes'))
    if any(r['conversion_status']=='implicit_ffmpeg_conversion' for r in processing['rules']):
        risks.append(_risk('implicit_ffmpeg_conversion', 'Original command lacks explicit conversion parameters'))
    if not _mapping_verified(data, source,session):
        risks.append(_risk('unverified_mapping', 'No evidence-backed frame correspondence; caller rows alone are unverified'))
    return risks


def _parsed_source(data, probe, frames):
    png_meta, conflicts = _png_metadata(Path(data['path'])) if Path(data['path']).suffix.lower()=='.png' else (None, [])
    parsed = parse_color_probe(probe, frames, png_metadata=png_meta)
    if conflicts:
        parsed['interpretation']['status']='conflicting'
        parsed['interpretation']['conflicts'].extend(conflicts)
        parsed['risks'].extend(_risk('conflicting_color_metadata',str(c),0) for c in conflicts)
    if (png_meta is not None) != (parsed['video']['codec_name']=='png'):
        raise ValueError('source extension and decoded format differ')
    if png_meta is None and 'mp4' not in str(probe.get('format',{}).get('format_name','')).split(','):
        raise ValueError('MP4 source container required')
    for row in data['mapping']['rows']:
        if row['asset_frame_index']>=len(parsed['video']['frames']): raise ValueError('mapping index outside decoded frames')
        if png_meta is None and row['pts'] is not None:
            actual = parsed['video']['frames'][row['asset_frame_index']].get('pts')
            if actual != row['pts'] or row['time_base'] != parsed['video']['time_base']:
                raise ValueError('mapping PTS must be the actual asset PTS')
    return parsed


def _inspect(data, session):
    name = f'colorimetry/{data["asset_id"]}/sidecar.json'
    _absent(session.logger, name)
    source = session.freeze(data['path'])
    if Path(data['path']).suffix.lower()=='.png': _png_metadata(Path(data['path']))
    for i in [*data['mapping']['evidence'], *data['processing']['command_records']]: session.freeze(i['path'])
    tools = {key: dict(identity=session.freeze(session.config.tools[key])) for key in ('ffmpeg', 'ffprobe')}
    processing = _processing(data, source, session)
    for key in tools:
        command = session.command([tools[key]['identity']['path'], '-version'], data['asset_id'])
        tools[key].update(version_command=command, version_output=session.freeze(command['stdout_path']))
    base = [tools['ffprobe']['identity']['path'], '-v', 'error']
    probe = session.command([*base, '-count_frames', '-show_streams', '-show_format', '-of', 'json', data['path']], data['asset_id'])
    frames = session.command([*base, '-select_streams', 'v:0', '-show_frames', '-of', 'json', data['path']], data['asset_id'])
    parsed = _parsed_source(data, json.loads(Path(probe['stdout_path']).read_text(encoding='utf-8')),
        json.loads(Path(frames['stdout_path']).read_text(encoding='utf-8')))
    risks = _diagnostic_risks(parsed, data, source, processing)
    record = dict(schema_version=1, algorithm=ALGORITHM, asset_id=data['asset_id'], stage=data['stage'],
        source=source, input_sha256=_input_digest(data, source, tools), mapping=data['mapping'], processing=processing,
        probe=dict(raw_probe=session.freeze(probe['stdout_path']), raw_frames=session.freeze(frames['stdout_path']),
                   png_metadata=parsed['png_metadata'], video=parsed['video']), interpretation=parsed['interpretation'],
        analysis_space=SPACE if parsed['interpretation']['status'] == 'resolved' else None,
        commands=[probe,frames], tools=tools, risks=risks, created_at=now())
    session.save(name, record)
    return record


def inspect_color_asset(entry, *, config, paths, logger, timeout=300):
    session = _Session(config=config, paths=paths, logger=logger, deadline=_deadline(timeout, monotonic()))
    data = _entry(entry, logger)
    record = _inspect(data, session)
    return record, list(session.outputs)


def _load_sidecar(sidecar, session):
    path = session.logger.path(f'colorimetry/{sidecar["asset_id"]}/sidecar.json')
    return _validate_sidecar(sidecar, session, path, session.logger.run_dir, _identity)


def _validate_sidecar(sidecar, session, path, audit_root, identity_check):
    _object(sidecar, SIDECAR_FIELDS, 'sidecar')
    if type(sidecar['schema_version']) is not int or sidecar['schema_version'] != 1 or sidecar['algorithm'] != ALGORITHM:
        raise ValueError('unsupported sidecar schema/algorithm')
    asset_id = sidecar['asset_id']
    if type(asset_id) is not str or not re.fullmatch('[A-Za-z0-9_-]+', asset_id): raise ValueError('invalid asset_id')
    path = _local_file(path)
    if path != audit_root/'logs'/'colorimetry'/asset_id/'sidecar.json':
        raise ValueError('sidecar must use its original audit/asset path')
    session.freeze(path)
    if json.loads(path.read_text(encoding='utf-8')) != sidecar:
        raise ValueError('sidecar must equal the persisted audit record')
    processing = deepcopy(sidecar['processing'])
    processing.pop('status', None); processing.pop('rules', None)
    data = _entry(dict(asset_id=asset_id, stage=sidecar['stage'], path=sidecar['source']['path'],
                       mapping=sidecar['mapping'], processing=processing), audit_root=audit_root, identity_check=identity_check)
    for identity in [sidecar['source'], *data['mapping']['evidence'], *processing['command_records']]:
        identity_check(identity); session.freeze(identity['path'])
    _object(sidecar['tools'], ('ffmpeg', 'ffprobe'), 'tools')
    for key, tool in sidecar['tools'].items():
        _object(tool, ('identity', 'version_command', 'version_output'), 'tool')
        if str(session.config.tools[key]) != tool['identity']['path']: raise ValueError('configured tool differs')
        for identity in (tool['identity'], tool['version_output']):
            identity_check(identity); session.freeze(identity['path'])
    _object(sidecar['probe'], ('raw_probe', 'raw_frames', 'png_metadata', 'video'), 'probe')
    for key in ('raw_probe', 'raw_frames'):
        identity = sidecar['probe'][key]; identity_check(identity); session.freeze(identity['path'])
    if _input_digest(data, sidecar['source'], sidecar['tools']) != sidecar['input_sha256']:
        raise ValueError('sidecar input digest differs')
    # Re-derive interpretation from frozen raw evidence, not mutable in-memory claims.
    parsed = _parsed_source(data, _read_evidence_json(sidecar['probe']['raw_probe']['path'],session),
        _read_evidence_json(sidecar['probe']['raw_frames']['path'],session))
    expected_processing = _processing(data, sidecar['source'], session)
    for actual, expected, label in (
        (sidecar['probe']['video'],parsed['video'],'video'),
        (sidecar['probe']['png_metadata'],parsed['png_metadata'],'PNG metadata'),
        (sidecar['interpretation'],parsed['interpretation'],'interpretation'),
        (sidecar['processing'],expected_processing,'processing'),
        (sidecar['risks'],_diagnostic_risks(parsed,data,sidecar['source'],expected_processing,session),'risks'),
        (sidecar['analysis_space'],SPACE if parsed['interpretation']['status']=='resolved' else None,'analysis space')):
        if actual != expected: raise ValueError('sidecar '+label+' differs from frozen original evidence')
    if type(sidecar['commands']) is not list or len(sidecar['commands'])!=2: raise ValueError('two original probe commands required')
    for command, key in zip(sidecar['commands'], ('raw_probe','raw_frames')):
        _command_record(command)
        if command['stdout_path']!=sidecar['probe'][key]['path'] or command['cwd']!=str(audit_root):
            raise ValueError('probe command output/cwd differs')
        expected_args = [str(session.config.tools['ffprobe']),'-v','error']
        expected_args += (['-count_frames','-show_streams','-show_format'] if key=='raw_probe' else ['-select_streams','v:0','-show_frames'])
        expected_args += ['-of','json',data['path']]
        if command['args']!=expected_args: raise ValueError('probe invocation differs')
        session.freeze(command['stderr_path'])
    for key,tool in sidecar['tools'].items():
        command=tool['version_command']; _command_record(command)
        if (command['args']!=[tool['identity']['path'],'-version'] or command['stdout_path']!=tool['version_output']['path'] or
            command['cwd']!=str(audit_root)): raise ValueError('tool version invocation differs')
        session.freeze(command['stderr_path'])
    _timestamp(sidecar['created_at'])
    return session.freeze(path)


def _analysis_filter(sidecar, index):
    values = sidecar['interpretation']['values']
    matrix = 'gbr' if sidecar['probe']['video']['codec_name'] == 'png' else 'bt709'
    range_name = {'tv':'limited', 'pc':'full'}[values['color_range']]
    return (f'select=eq(n\\,{index}),format={"gbrp" if matrix == "gbr" else sidecar["probe"]["video"]["pix_fmt"]},'
        f'zscale=matrixin={matrix}:transferin={values["color_transfer"]}:primariesin=bt709:rangein={range_name}:'
        'matrix=gbr:transfer=iec61966-2-1:primaries=bt709:range=full:dither=none,format=gbrp,format=rgb24')


def _decode(sidecar, index, session):
    identity = _load_sidecar(sidecar, session)
    video = sidecar['probe']['video']
    _int(index, 'frame_index')
    if index >= len(video['frames']): raise ValueError('frame_index outside decoded asset')
    stem = f'colorimetry/{sidecar["asset_id"]}/analysis/frame_{index:06d}'
    _absent(session.logger, stem+'.json'); _absent(session.logger, stem+'.rgb')
    mapping = next((deepcopy(r) for r in sidecar['mapping']['rows'] if r['asset_frame_index']==index), None)
    frame = video['frames'][index]
    pts = frame.get('pts', frame.get('best_effort_timestamp')) if video['codec_name'] != 'png' else None
    time_base = video['time_base'] if pts is not None else None
    if video['codec_name'] == 'png' and mapping and not any(r['code']=='unverified_mapping' for r in sidecar['risks']):
        pts, time_base = mapping['pts'], mapping['time_base']
    risks = deepcopy(sidecar['risks']); pixels = command = None
    space = sidecar['analysis_space']
    if space == SPACE and sidecar['interpretation']['status'] == 'resolved':
        capability = session.command([session.config.tools['ffmpeg'], '-hide_banner', '-filters'], sidecar['asset_id'])
        if not re.search(r'\bzscale\s+V->V', Path(capability['stdout_path']).read_text(encoding='utf-8')):
            space = None
            risks.append(_risk('missing_zscale', 'Configured FFmpeg lacks zscale; see capability command '+capability['stdout_path']))
        else:
            command = session.command([session.config.tools['ffmpeg'], '-nostdin', '-v', 'error', '-xerror',
                '-threads', '1', '-i', sidecar['source']['path'], '-map', '0:v:0', '-an', '-filter_threads', '1',
                '-vf', _analysis_filter(sidecar, index), '-frames:v', '1', '-fps_mode', 'passthrough',
                '-threads', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], sidecar['asset_id'])
            output = _local_file(command['stdout_path'])
            if output.stat().st_size != video['width']*video['height']*3:
                raise ValueError('analysis raw RGB byte count differs from dimensions')
            session.verify()
            _absent(session.logger, stem+'.rgb')
            path = session.logger.save_bytes(stem+'.rgb', output.read_bytes()); session.outputs.append(path)
            pixels = session.freeze(path)
    record = dict(schema_version=1, algorithm=ALGORITHM, source=sidecar['source'], sidecar=identity,
        frame_index=index, pts=pts, time_base=time_base, mapping=mapping, status='ready' if pixels else 'unverified',
        analysis_space=space if pixels else None, pixels=pixels, command=command, risks=risks)
    session.save(stem+'.json', record)
    return record


def decode_analysis_frame(sidecar, *, frame_index, config, paths, logger, timeout=300):
    session = _Session(config=config, paths=paths, logger=logger, deadline=_deadline(timeout, monotonic()))
    record = _decode(deepcopy(sidecar), frame_index, session)
    return record, list(session.outputs)


class ColorAnalysisReader:
    """A call-local, lazy, read-only window over persisted color evidence.

    No logger or process is created. Metadata is interned by sidecar; full-size
    pixels are returned only by read_rgb and are never retained by this object.
    """
    schema_version = 1
    algorithm = 'colorimetry_evidence_v1'

    def __init__(self, record_paths, *, config, timeout=300):
        if type(record_paths) not in (list, tuple) or not 0 < len(record_paths) <= 4096:
            raise ValueError('resource_limit: 1..4096 explicit frame records required')
        self.config = config
        self.deadline = _deadline(timeout, monotonic())
        self.frozen, self._frames, self._sidecars, self._records = {}, [], {}, {}
        self._json_bytes, self._closed = 0, False
        self._json_paths=set()
        try:
            for value in record_paths:
                path = _local_file(value)
                if str(path) in self._records: raise ValueError('duplicate analysis record')
                record_identity = self.freeze(path)
                record = self._json(path)
                _object(record, 'schema_version algorithm source sidecar frame_index pts time_base mapping status analysis_space pixels command risks'.split(), 'analysis record')
                if type(record['schema_version']) is not int or record['schema_version'] != 1 or record['algorithm'] != ALGORITHM:
                    raise ValueError('unsupported analysis record')
                self.check(record['sidecar'])
                sidepath = Path(record['sidecar']['path'])
                key = str(sidepath)
                if key not in self._sidecars:
                    sidecar = self._json(sidepath)
                    if len(sidepath.parents) < 4: raise ValueError('invalid sidecar path')
                    audit_root = validate_run_dir(sidepath.parents[3])
                    _validate_sidecar(sidecar, self, sidepath, audit_root, self.check)
                    self._sidecars[key] = sidecar
                sidecar = self._sidecars[key]
                self._validate_record(path, record, sidecar)
                self._records[str(path)] = record
                self._frames.append(dict(record_identity=record_identity, record=record,
                                         sidecar_identity=record['sidecar']))
            self._budget()
        except BaseException:
            self.verify(budget=False)
            raise

    @property
    def frames(self):
        return deepcopy(self._frames)

    @property
    def sidecars(self):
        return deepcopy(self._sidecars)

    @property
    def identities(self):
        return [deepcopy(self.frozen[p]) for p in sorted(self.frozen)]

    def _budget(self):
        _remaining(self.deadline, monotonic())

    def freeze(self, path):
        self._budget()
        path = _local_file(path); key = str(path)
        if key not in self.frozen:
            size = path.stat().st_size
            if path.suffix.lower() == '.json':
                if size > 16777216 or self._json_bytes + size > 67108864:
                    raise ValueError('resource_limit: JSON/metadata budget')
                self._json_bytes += size
                self._json_paths.add(key)
            self.frozen[key] = thaw(hash_file(path))
        return deepcopy(self.frozen[key])

    def check(self, identity):
        path = _identity_shape(identity)
        actual = self.freeze(path)
        if any(actual[k] != identity[k] for k in ('path','bytes','mtime_ns','sha256')):
            raise OSError(f'frozen file bytes changed: {path}')
        return identity

    def _json(self, path):
        path=Path(path);identity=self.freeze(path);key=str(path)
        if key not in self._json_paths:
            size=identity['bytes']
            if size>16777216 or self._json_bytes+size>67108864:raise ValueError('resource_limit: JSON/metadata budget')
            self._json_bytes+=size;self._json_paths.add(key)
        return json.loads(Path(path).read_text(encoding='utf-8'))

    def _validate_record(self, path, record, sidecar):
        index = _int(record['frame_index'], 'frame_index')
        video = sidecar['probe']['video']
        if index >= len(video['frames']): raise ValueError('frame_index outside decoded asset')
        if path != Path(record['sidecar']['path']).parent/'analysis'/f'frame_{index:06d}.json':
            raise ValueError('analysis record path/index differs')
        self.check(record['source'])
        if record['source'] != sidecar['source']: raise ValueError('analysis source differs')
        mapping = next((r for r in sidecar['mapping']['rows'] if r['asset_frame_index']==index), None)
        frame = video['frames'][index]
        pts = frame.get('pts', frame.get('best_effort_timestamp')) if video['codec_name']!='png' else None
        tb = video['time_base'] if pts is not None else None
        if video['codec_name']=='png' and mapping and not any(r['code']=='unverified_mapping' for r in sidecar['risks']):
            pts,tb = mapping['pts'],mapping['time_base']
        if record['mapping'] != mapping or type(record['pts']) is not type(pts) or record['pts'] != pts or record['time_base'] != tb:
            raise ValueError('analysis mapping/native time differs')
        if record['status'] == 'ready':
            if sidecar['analysis_space'] != SPACE or record['analysis_space'] != SPACE or sidecar['interpretation']['status']!='resolved':
                raise ValueError('ready requires resolved explicit analysis space')
            identity = record['pixels']; self.check(identity)
            if Path(identity['path']) != path.with_suffix('.rgb'):
                raise ValueError('raw pixel path differs')
            if identity['bytes'] > 33554432: raise ValueError('resource_limit: raw RGB')
            if identity['bytes'] != video['width']*video['height']*3:
                raise ValueError('raw RGB dimensions differ')
            command = record['command']; _command_record(command)
            expected = [str(self.config.tools['ffmpeg']), '-nostdin','-v','error','-xerror','-threads','1',
                '-i',record['source']['path'],'-map','0:v:0','-an','-filter_threads','1','-vf',
                _analysis_filter(sidecar,index),'-frames:v','1','-fps_mode','passthrough','-threads','1',
                '-pix_fmt','rgb24','-f','rawvideo','-']
            if command['args'] != expected or command['cwd'] != str(path.parents[4]):
                raise ValueError('actual RGB conversion command differs')
            stdout = self.freeze(command['stdout_path']); self.freeze(command['stderr_path'])
            if any(stdout[k] != identity[k] for k in ('bytes','sha256')):
                raise ValueError('RGB differs from command stdout')
            if record['risks'] != sidecar['risks']: raise ValueError('analysis risks differ')
        elif record['status'] == 'unverified':
            if any(record[k] is not None for k in ('pixels','analysis_space','command')):
                raise ValueError('unverified must not carry pixels/space/command')
            risks = record['risks']
            if risks != sidecar['risks']:
                if (type(risks) is not list or risks[:-1]!=sidecar['risks'] or
                    set(risks[-1])!=set(('code','detail','frame_index')) or risks[-1]['code']!='missing_zscale'):
                    raise ValueError('unverified reasons differ')
                prefix = 'Configured FFmpeg lacks zscale; see capability command '
                if not risks[-1]['detail'].startswith(prefix): raise ValueError('missing capability evidence')
                capability = Path(risks[-1]['detail'][len(prefix):]); self.freeze(capability)
                if re.search(r'\bzscale\s+V->V', capability.read_text(encoding='utf-8')):
                    raise ValueError('capability evidence contradicts missing_zscale')
            elif sidecar['analysis_space'] is not None:
                raise ValueError('unverified resolved source requires capability failure evidence')
        else:
            raise ValueError('unknown analysis status')

    def read_rgb(self, record_path):
        if self._closed: raise ValueError('reader is closed')
        self._budget()
        key = str(_local_file(record_path))
        if key not in self._records: raise ValueError('frame was not requested')
        record = self._records[key]
        if record['status'] != 'ready': return None
        identity = record['pixels']
        data = Path(identity['path']).read_bytes()
        if len(data)!=identity['bytes'] or hashlib.sha256(data).hexdigest()!=identity['sha256']:
            raise OSError('raw RGB changed while reading')
        return data

    def verify(self, *, budget=True):
        for identity in self.frozen.values():
            _identity(identity)
            if budget: self._budget()

    def __enter__(self):
        if self._closed: raise ValueError('reader is closed')
        return self

    def __exit__(self, exc_type, exc, tb):
        try: self.verify(budget=exc_type is None)
        finally: self._closed = True
        return False


def load_color_analysis_set(record_paths, *, config, timeout=300):
    return ColorAnalysisReader(record_paths, config=config, timeout=timeout)


def _edge_recorded(upstream, target):
    if upstream is None or target['processing']['status']!='recorded': return False
    if any(r['code']=='unverified_mapping' for asset in (upstream,target) for r in asset['risks']): return False
    def coordinates(asset):
        return {(r['clip_id'],r['generated_frame_index']) for r in asset['mapping']['rows']
                if r['clip_id'] is not None and r['generated_frame_index'] is not None}
    if not coordinates(upstream) or not coordinates(target) or not coordinates(target).issubset(coordinates(upstream)): return False
    for identity in target['processing']['command_records']:
        record=json.loads(Path(identity['path']).read_text(encoding='utf-8'))
        if not isinstance(record,dict): continue
        source=record.get('source',{}); output=record.get('target',record.get('output',{}))
        if isinstance(source,dict): source=source.get('identity',source)
        if isinstance(output,dict): output=output.get('identity',output)
        cmd=record.get('command')
        if (not _artifact_matches(source,upstream['source']) or not _artifact_matches(output,target['source']) or
            not isinstance(cmd,dict)): continue
        if any(rule['args']==cmd.get('args') for rule in target['processing']['rules']): return True
    return False


def inspect_color_chain(entries, *, config, paths, logger, timeout=1200):
    session = _Session(config=config, paths=paths, logger=logger, deadline=_deadline(timeout, monotonic()))
    _absent(logger, 'colorimetry/chain.json')
    if type(entries) is not list or not entries: raise ValueError('nonempty ordered entries required')
    data = [_entry(e, logger) for e in entries]
    ids = [e['asset_id'] for e in data]
    if len(set(ids)) != len(ids): raise ValueError('duplicate asset_id')
    missing = [s for s in STAGES if s not in {e['stage'] for e in data}]
    seen = set()
    for e in data:
        for upstream in e['processing']['upstream_ids']:
            if upstream in ids and upstream not in seen: raise ValueError('cycle or non-topological input order')
            if upstream not in ids and not missing: raise ValueError('complete chain has dangling upstream')
        seen.add(e['asset_id'])
        _absent(logger, f'colorimetry/{e["asset_id"]}/sidecar.json')
        for path in [e['path'], *[i['path'] for i in e['mapping']['evidence']], *[i['path'] for i in e['processing']['command_records']]]:
            session.freeze(path)
    assets, edges, risks, inspected = [], [], [], {}
    for e in data:
        record = _inspect(e, session); inspected[e['asset_id']] = record
        name = f'colorimetry/{e["asset_id"]}'
        analysis = []
        indexes = [r['asset_frame_index'] for r in e['mapping']['rows']]
        if record['probe']['video']['codec_name'] == 'png': indexes = [0]
        for index in indexes:
            _decode(record, index, session)
            analysis.append(session.freeze(logger.path(f'{name}/analysis/frame_{index:06d}.json')))
        assets.append(dict(asset_id=e['asset_id'], sidecar=session.freeze(logger.path(name+'/sidecar.json')), analysis_frames=analysis))
        risks.extend(record['risks'])
        for upstream in e['processing']['upstream_ids']:
            edges.append(dict(from_asset_id=upstream, to_asset_id=e['asset_id'],
                status='recorded' if _edge_recorded(inspected.get(upstream),record) else 'unknown'))
    if missing: risks.append(_risk('missing_stage', ', '.join(missing)))
    chain = dict(schema_version=1, algorithm=ALGORITHM, assets=assets, edges=edges,
                 coverage='partial' if missing else 'complete', missing_stages=missing, risks=risks, created_at=now())
    session.save('colorimetry/chain.json', chain)
    return chain, list(dict.fromkeys(session.outputs))
