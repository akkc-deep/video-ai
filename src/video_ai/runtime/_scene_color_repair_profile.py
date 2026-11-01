"""Read-only validation of a sealed conditional repair evidence closure.

No calibration code is imported or executed. Large result bodies are hashed
against their independent identities. Metadata and selected saved control
scalars are decoded, and the frozen closeout reductions are replayed.
"""
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import hashlib
from importlib.metadata import version
import math
from pathlib import Path
import re
import sys

from ..adapters.common import strict_json
from ._scene_continuity_io import instant, local
from .paths import SOURCE_ROOT
from .production_state import ProductionRefused, integer, object_fields


ALGORITHM = 'AI_conditional_constant_color_repair_v1'
PURPOSE = 'offline_AI_repair_calibration'
OPERATIONS = ('exposure', 'wb_r', 'wb_g', 'wb_b', 'chroma')
LEVELS = (1/64, 1/32, 1/16, 1/8, 1/4, 1/2, 1.)
GENRES = {'animals', 'animation', 'indoor', 'outdoor', 'people', 'transport'}
TEMPORAL = 'one constant parameter for the complete source interval'
EVALUATION = 'schema_version algorithm created_at purpose production_eligible inputs thresholds holdout_results checks context_gates requested_sources requested_controls source_groups_not_certified_independent limitations qualified_directions temporal_policy unsupported'
PROFILE = EVALUATION + ' evaluation calibrated_bounds evidence_only'
INPUTS = 'created_at authorization index protocol software versions sources source_count requested_controls_per_source production_eligible limitations'
META = 'source_id scene_group genre split eligible eligibility_reason frames timeline interval counts informative_pairs sampling ROI_origin ROI_uncertainties source_identities pack pixel_allocation_bound'
LIMITATIONS = ['Old AI split, not a fresh blind test', 'Known correspondence AND known operator family/axis',
              'Sampled pixels, not full-resolution output qualification', 'Constant parameter only']
UNSUPPORTED = ['time-varying drift', 'local correction', 'unknown lighting intent', 'unmatched pixels',
               'automatic model/axis selection', 'combined parameter axes', 'arbitrary hue rotation']


def _fields(value, fields, label):
    object_fields(value, fields.split(), label)
    return value


def _text(value):
    if type(value) is not str or not value.strip():
        raise ProductionRefused('nonempty repair evidence text required')
    return value


def _array(value, *, count=None):
    if type(value) is not list or (count is not None and len(value) != count):
        raise ProductionRefused('repair evidence array/count differs')
    return value


def _time(value):
    if type(value) is not str:
        raise ProductionRefused('repair evidence timestamp must be a string')
    at = instant(value)
    if at > datetime.now(timezone.utc):
        raise ProductionRefused('future repair evidence timestamp')
    return at


def _finite(value, *, minimum=0, maximum=math.inf):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ProductionRefused('invalid finite repair evidence number')
    return value


def _common(value):
    if (type(value['schema_version']) is not int or value['schema_version'] != 1 or
            value['algorithm'] != ALGORITHM or value['purpose'] != PURPOSE or value['production_eligible'] is not False):
        raise ProductionRefused('sealed research repair identity required')
    return _time(value['created_at'])


class _Evidence:
    def __init__(self, reader):
        self.reader = reader
        self.identities = {}
        self.artifacts = {}

    def verify(self, value, *, expected=None, runtime=True):
        self.reader.check()
        if type(value) is not dict or set(value) not in ({'path','bytes','sha256'},
                {'path','bytes','sha256','mtime_ns'}, {'path','bytes','sha256','mtime_ns','verified_at'}):
            raise ProductionRefused('strict repair file identity required')
        integer(value['bytes'], 'repair file bytes', 0)
        if type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
            raise ProductionRefused('repair file SHA256 required')
        if 'mtime_ns' in value:
            integer(value['mtime_ns'], 'repair mtime', 0)
        if 'verified_at' in value:
            _time(value['verified_at'])
        p = local(value['path'], runtime=runtime)
        if expected is not None and p != expected:
            raise ProductionRefused('repair evidence path differs from sealed layout')
        stamp = {k:value[k] for k in ('path','bytes','sha256')}
        st = p.stat()
        if st.st_size != value['bytes'] or ('mtime_ns' in value and st.st_mtime_ns != value['mtime_ns']):
            raise ProductionRefused('repair file identity changed: '+str(p))
        prior = self.artifacts.get(str(p))
        if prior is not None:
            old=self.identities[str(p)]
            if prior != stamp or (old.st_size,old.st_mtime_ns,old.st_ino)!=(st.st_size,st.st_mtime_ns,st.st_ino):
                raise ProductionRefused('conflicting repair evidence identity')
            return p
        digest = hashlib.sha256()
        with p.open('rb') as stream:
            while block := stream.read(1024*1024):
                self.reader.check(); digest.update(block)
        final = p.stat(); self.reader.check()
        if (digest.hexdigest() != value['sha256'] or st.st_size != final.st_size or
                st.st_mtime_ns != final.st_mtime_ns or st.st_ino != final.st_ino):
            raise ProductionRefused('repair file bytes changed: '+str(p))
        self.artifacts[str(p)] = stamp
        self.identities[str(p)] = final
        return p

    def read(self, path, *, identity=None):
        self.reader.check(); p = local(path)
        if identity is not None:
            self.verify(identity, expected=p)
        before = p.stat(); self.reader.charge(p,before.st_size)
        raw = p.read_bytes(); self.reader.check()
        stamp = dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if len(raw) != before.st_size or (str(p) in self.artifacts and self.artifacts[str(p)] != stamp):
            raise ProductionRefused('repair metadata bytes changed during read')
        self.verify(dict(stamp,mtime_ns=before.st_mtime_ns))
        return strict_json(raw)

    def finish(self):
        for path, old in self.identities.items():
            self.reader.check(); p=local(path,runtime=False);new=p.stat()
            if (new.st_size, new.st_mtime_ns, new.st_ino) != (old.st_size, old.st_mtime_ns, old.st_ino):
                raise ProductionRefused('repair closure changed during validation')
            digest=hashlib.sha256()
            with p.open('rb') as stream:
                while block:=stream.read(1024*1024):
                    self.reader.check();digest.update(block)
            final=p.stat();self.reader.check()
            if (digest.hexdigest()!=self.artifacts[path]['sha256'] or
                    (final.st_size,final.st_mtime_ns,final.st_ino)!=(old.st_size,old.st_mtime_ns,old.st_ino)):
                raise ProductionRefused('repair closure bytes changed during validation')
        return [self.artifacts[key] for key in sorted(self.artifacts)]


def _protocol(value):
    expected = dict(algorithm=ALGORITHM, levels=list(LEVELS), operations=list(OPERATIONS), samples_per_role=1024,
        maximum_fit_pairs=16384, minimum_pairs=81, p99_error_codes=2, maximum_error_codes=4,
        minimum_sources=6, required_genres=sorted(GENRES), temporal_policy=TEMPORAL,
        correspondence='oracle_same_pixel', operator_selection='oracle_known_family_and_axis',
        scope='conditional arithmetic only; not real matching, automatic selection or semantic safety',
        production_eligible=False, pixel_working_budget_bytes=134217728,
        operator_details='sRGB transfer; linear x*2**(a*d) or Y+2**a*(x-Y); clip then np.rint to uint8',
        residual_rules='per-frame p99<=2, every channel maximum<=4; new interior clipping cannot increase',
        sampling='visible ROI only; 1024 per role; every native frame; oracle correspondence and family/axis',
        qualification='all baseline-eligible sources; minimum six sources/groups and six genres for each split',
        time_limit_seconds_per_source=265)
    _fields(value, ' '.join(expected)+' created_at', 'repair protocol')
    for key, want in expected.items():
        if type(value[key]) is not type(want) or value[key] != want:
            raise ProductionRefused('repair protocol differs: '+key)
    return _time(value['created_at'])


def _software_paths():
    import numpy as np
    import cv2
    paths = [SOURCE_ROOT/'scripts/experiments/vco06_repair_calibration.py', Path(sys.executable).resolve(),
             Path(np.__file__).resolve(), Path(cv2.__file__).resolve()]
    paths += list(Path(np.__file__).parent.rglob('*.pyd')) + list(Path(cv2.__file__).parent.glob('*.pyd'))
    paths += [SOURCE_ROOT/'src/video_ai'/p for p in ('media/colorimetry.py','media/_continuity_controls.py',
        'media/_continuity_schema.py','media/_continuity_geometry.py','runtime/manifest.py','runtime/paths.py',
        'adapters/common.py','experiments/whole_scene_case.py')]
    return sorted(set(paths))


def _interval(value):
    _fields(value, 'start_pts end_pts time_base', 'repair interval')
    integer(value['start_pts'], 'repair start PTS', -(2**63)); integer(value['end_pts'], 'repair end PTS', -(2**63))
    try:
        if type(value['time_base']) is not str or Fraction(value['time_base']) <= 0 or value['end_pts'] <= value['start_pts']:
            raise ValueError()
    except (ValueError, ZeroDivisionError) as exc:
        raise ProductionRefused('positive native repair interval required') from exc


def _entries(inputs, evidence):
    entries = _array(inputs['sources'], count=24); ids = set(); groups = set()
    for entry in entries:
        _fields(entry, 'source split ROI_origin ROI_uncertainties', 'repair source entry')
        source = entry['source']
        fields = 'source_id genre source_kind scene_group media frame_records interval rights_note regions truth context'
        if type(source) is dict and 'control_targets' in source:
            fields += ' control_targets'
        _fields(source, fields, 'repair source')
        sid = source['source_id']
        if type(sid) is not str or not re.fullmatch('[A-Za-z0-9_-]+',sid) or sid in ids:
            raise ProductionRefused('unique safe repair source id required')
        ids.add(sid); group = _text(source['scene_group'])
        if group in groups:
            raise ProductionRefused('repair source groups differ from original split')
        groups.add(group)
        if source['genre'] not in GENRES or source['source_kind'] not in ('captured','animation') or entry['split'] not in ('calibration','holdout'):
            raise ProductionRefused('unsupported repair source/split')
        _interval(source['interval']); _text(source['rights_note']); _text(entry['ROI_origin'])
        if entry['ROI_uncertainties'] is not None:
            _text(entry['ROI_uncertainties'])
        refs = [source['media'], source['regions'], source['truth'], *_array(source['frame_records'])]
        if not 1 <= len(source['frame_records']) <= 4096:
            raise ProductionRefused('complete native repair source frames required')
        if source['context'] is not None:
            refs.append(source['context'])
        for ref in refs:
            evidence.verify(ref)
        if 'control_targets' in source:
            controls = source['control_targets']
            if type(controls) is not dict or not controls or set(controls) - {'occlusion','local_color'}:
                raise ProductionRefused('unsupported original control authorization')
            for target in controls.values():
                _fields(target,'region_ids authorization','original control target')
                region_ids = _array(target['region_ids'])
                if not region_ids or any(type(r) is not str or not r.strip() for r in region_ids) or len(set(region_ids)) != len(region_ids):
                    raise ProductionRefused('original control region ids required')
                evidence.verify(target['authorization'])
    for split in ('calibration','holdout'):
        selected = [e for e in entries if e['split'] == split]
        if len(selected) != 12 or any(sum(e['source']['genre'] == g for e in selected) != 2 for g in GENRES):
            raise ProductionRefused('original repair 12/12 six-genre split required')
    return entries


class _SelectedRows:
    """A bounded lexical reader retaining scalar control summaries only."""
    _events=re.compile(rb'["\\\[\]{}]')
    _end=re.compile(rb'[\s,\]}]')
    _selected=set('source_id split case_id operation injection_direction level estimated_amplitude conditional_operator_and_correspondence passed status parameter_temporal_variation'.split())

    def __init__(self,stream,reader):
        self.stream=stream;self.reader=reader;self.data=b'';self.pos=0;self.parsed_bytes=0

    def peek(self):
        if self.pos==len(self.data):
            self.reader.check();self.data=self.stream.read(65536);self.pos=0
        return self.data[self.pos:self.pos+1]

    def whitespace(self):
        while self.peek() in (b' ',b'\t',b'\r',b'\n'):
            self.pos+=1

    def punctuation(self,want):
        self.whitespace()
        if self.peek()!=want:
            raise ProductionRefused('malformed saved repair control rows')
        self.pos+=1

    def raw(self,*,capture):
        self.whitespace();first=self.peek();result=bytearray()
        def consume(n):
            if capture:
                result.extend(self.data[self.pos:self.pos+n])
                if len(result)>8192:
                    raise ProductionRefused('resource_limit: repair control scalar')
            self.pos+=n
        if first not in (b'{',b'[',b'"'):
            while self.peek():
                match=self._end.search(self.data,self.pos)
                if match:
                    consume(match.start()-self.pos);break
                consume(len(self.data)-self.pos)
            if not result and capture:
                raise ProductionRefused('empty saved repair scalar')
            return bytes(result)
        quoted=first==b'"';stack=[] if quoted else [b'}' if first==b'{' else b']']
        consume(1)
        while self.peek():
            event=self._events.search(self.data,self.pos)
            if event is None:
                consume(len(self.data)-self.pos);continue
            consume(event.start()-self.pos);c=self.peek();consume(1)
            if quoted:
                if c==b'\\':
                    if not self.peek():raise ProductionRefused('unfinished saved repair string')
                    consume(1)
                elif c==b'"':
                    quoted=False
                    if not stack:return bytes(result)
                continue
            if c==b'"':quoted=True
            elif c in (b'[',b'{'):
                stack.append(b']' if c==b'[' else b'}')
                if len(stack)>64:raise ProductionRefused('resource_limit: repair control nesting')
            elif c in (b']',b'}'):
                if not stack or c!=stack.pop():raise ProductionRefused('malformed saved repair value')
                if not stack:return bytes(result)
            else:raise ProductionRefused('malformed saved repair escape')
        raise ProductionRefused('unfinished saved repair value')

    def row(self):
        self.punctuation(b'{');keys=set();value={}
        while True:
            raw_key=self.raw(capture=True);key=strict_json(b'['+raw_key+b']')[0]
            if type(key) is not str or key in keys:
                raise ProductionRefused('duplicate/invalid saved repair control key')
            keys.add(key);self.punctuation(b':')
            raw=self.raw(capture=key in self._selected)
            if key in self._selected:
                value[key]=strict_json(b'['+raw+b']')[0];self.parsed_bytes+=len(raw_key)+len(raw)+2
            self.whitespace();delimiter=self.peek()
            if delimiter==b'}':self.pos+=1;break
            self.punctuation(b',')
        base=set('source_id split case_id operation injection_direction level estimated_amplitude conditional_operator_and_correspondence passed status'.split())
        state=value.get('status')
        extras=({'fit','frames','parameter_temporal_variation','temporal_mean_error_differences'} if state=='measured' else
            {'fit','frames','negative_construction'} if state=='context_rejected' else {'frames','reason'})
        allowed=[base|extras]
        if state=='abstained':allowed.append(base|extras|{'fit'})
        if keys not in allowed or state not in ('measured','context_rejected','abstained'):
            raise ProductionRefused('saved repair control schema differs')
        if state=='measured' and (type(value['parameter_temporal_variation']) not in (int,float) or value['parameter_temporal_variation']!=0):
            raise ProductionRefused('saved repair parameter was not constant')
        return value

    def rows(self):
        rows=[];self.whitespace()
        while self.peek()!=b']':
            if len(rows)>=74:raise ProductionRefused('saved repair control count exceeds fixed protocol')
            rows.append(self.row());self.whitespace()
            if self.peek()==b']':break
            self.punctuation(b',')
        self.punctuation(b']')
        if len(rows)!=74:raise ProductionRefused('complete 74 saved repair controls required')
        return rows


def _result_metadata(path, evidence):
    """Decode bounded metadata surrounding the independently hashed rows.

    Frozen producer order is status, closure_verified, source, rows, elapsed,
    finished_at. Bulk frame scores are skipped while selected scalar control
    summaries are retained to verify the original frozen closeout reductions.
    """
    marker = re.compile(rb',\s*"rows"\s*:\s*\[')
    prefix = bytearray()
    if path.stat().st_size>16777216:
        raise ProductionRefused('resource_limit: repair result JSON')
    with path.open('rb') as stream:
        while True:
            evidence.reader.check(); block = stream.read(65536)
            if not block or len(prefix) + len(block) > 16777216:
                raise ProductionRefused('resource_limit: repair result metadata prefix')
            prefix.extend(block); match = marker.search(prefix)
            if match is not None:
                header_raw = bytes(prefix[:match.end()]) + b']}'
                header = strict_json(header_raw)
                break
        stream.seek(match.end());selected=_SelectedRows(stream,evidence.reader);rows=selected.rows()
        stream.seek(max(0, path.stat().st_size - 65536)); tail = stream.read(65536)
    matches = list(re.finditer(rb'\]\s*,\s*"elapsed_seconds"\s*:', tail))
    if not matches:
        raise ProductionRefused('repair result metadata suffix missing')
    suffix_raw = b'{"elapsed_seconds":' + tail[matches[-1].end():]
    suffix = strict_json(suffix_raw)
    evidence.reader.charge(path, len(header_raw) + len(suffix_raw)+selected.parsed_bytes)
    _fields(header, 'status closure_verified source rows', 'repair result prefix')
    _fields(suffix, 'elapsed_seconds finished_at', 'repair result suffix')
    if header['status'] != 'completed' or header['closure_verified'] is not True:
        raise ProductionRefused('repair source result closure failed')
    _finite(suffix['elapsed_seconds'], maximum=265)
    return header['source'], _time(suffix['finished_at']), suffix['elapsed_seconds'],rows


def _source_result(entry, ref, root, evidence, started, sealed_at, evaluated):
    source = entry['source']; sid = source['source_id']; split = entry['split']
    result_path = root/'source-results'/(sid+'.json')
    evidence.verify(ref, expected=result_path)
    independent = evidence.read(result_path.with_suffix('.identity.json'))
    if independent != ref:
        raise ProductionRefused('independent repair result identity differs')
    evidence.verify(independent, expected=result_path)
    meta, finished, elapsed,rows = _result_metadata(result_path, evidence)
    _fields(meta, META, 'repair source pack metadata')
    if evidence.read(root/'source-packs'/(sid+'.json')) != meta:
        raise ProductionRefused('repair source pack and result metadata differ')
    for key, want in (('source_id',sid),('scene_group',source['scene_group']),('genre',source['genre']),
            ('split',split),('interval',source['interval']),('ROI_origin',entry['ROI_origin']),('ROI_uncertainties',entry['ROI_uncertainties'])):
        if meta[key] != want:
            raise ProductionRefused('repair result source binding differs: '+key)
    integer(meta['frames'],'repair frames',1); integer(meta['informative_pairs'],'informative pairs',0)
    if meta['frames'] > 4096 or meta['frames'] != len(source['frame_records']):
        raise ProductionRefused('repair source frame count differs')
    integer(meta['pixel_allocation_bound'],'repair pixel work',1)
    if meta['pixel_allocation_bound'] > 134217728:
        raise ProductionRefused('resource_limit: sealed repair pixel work')
    _text(meta['eligibility_reason'])
    if meta['sampling'] != 'oracle paired coordinates; visible ROI; at most 1024 pixels per role':
        raise ProductionRefused('repair correspondence limitation differs')
    counts = _array(meta['counts'],count=meta['frames']); timeline = _array(meta['timeline'],count=meta['frames'])
    previous_index = previous_pts = None
    for row in timeline:
        _fields(row,'frame_index pts time_base','repair native frame');integer(row['frame_index'],'frame index',0);integer(row['pts'],'native PTS',-(2**63))
        if (row['time_base'] != source['interval']['time_base'] or
                (previous_index is not None and (row['frame_index'] != previous_index+1 or row['pts'] <= previous_pts))):
            raise ProductionRefused('repair complete native timeline differs')
        previous_index, previous_pts = row['frame_index'], row['pts']
    if timeline[0]['pts'] != source['interval']['start_pts'] or timeline[-1]['pts'] >= source['interval']['end_pts']:
        raise ProductionRefused('repair native interval differs')
    for row in counts:
        _fields(row,'points regions','repair sampling count');integer(row['points'],'repair points',0)
        if row['points'] > 2048:
            raise ProductionRefused('repair per-role sample support exceeds frozen cap')
        for region in _array(row['regions']):
            _fields(region,'region_id role points_before_role_cap','repair sampling region')
            _text(region['region_id']);integer(region['points_before_role_cap'],'uncapped points',0)
            if region['role'] not in ('subject','background'):
                raise ProductionRefused('repair sampling role differs')
    eligible = min(c['points'] for c in counts) >= 81 and meta['informative_pairs'] >= 81
    if type(meta['eligible']) is not bool or meta['eligible'] != eligible:
        raise ProductionRefused('repair baseline eligibility differs')
    identities = _array(meta['source_identities'])
    for item in identities:
        evidence.verify(item)
    actual = {(i['path'],i['bytes'],i['sha256']) for i in identities}
    required = [source['media'],source['regions'],source['truth'],*source['frame_records']]
    if source['context'] is not None:
        required.append(source['context'])
    if any((r['path'],r['bytes'],r['sha256']) not in actual for r in required):
        raise ProductionRefused('repair source metadata omits original evidence')
    evidence.verify(meta['pack'], expected=root/'source-packs'/(sid+'.npz'))
    began = finished - timedelta(seconds=elapsed)
    if finished > evaluated or (split == 'calibration' and not started <= began <= finished <= sealed_at) or (split == 'holdout' and not sealed_at <= began <= finished):
        raise ProductionRefused('repair calibration/seal/holdout stage order differs')
    return {k:meta[k] for k in ('source_id','scene_group','genre','split','eligible')},rows


def _directions(bounds, checks, sources):
    _array(bounds,count=10);_array(checks,count=10)
    expected = [(op, sign) for op in OPERATIONS for sign in (-1,1)]
    for rows in (bounds,checks):
        if (any(type(r) is not dict or type(r.get('injection_direction')) is not int for r in rows) or
                [(r.get('operation'),r.get('injection_direction')) for r in rows] != expected):
            raise ProductionRefused('complete sealed repair direction grid required')
    eligible = {split:[s['source_id'] for s in sources if s['split'] == split and s['eligible']] for split in ('calibration','holdout')}
    coverage = {}
    for split in eligible:
        rows = [s for s in sources if s['source_id'] in eligible[split]]
        coverage[split] = len(rows) >= 6 and len({r['scene_group'] for r in rows}) >= 6 and {r['genre'] for r in rows} == GENRES
    qualified = []
    for bound, check in zip(bounds,checks):
        _fields(bound,'operation injection_direction max_injection_level correction_direction correction_amplitude_ceiling eligible_sources coverage_sufficient reason','sealed correction bound')
        _fields(check,'operation injection_direction qualified coverage_sufficient eligible_sources cases reason','holdout direction check')
        if type(bound['injection_direction']) is not int or type(bound['correction_direction']) is not int or bound['correction_direction'] != -bound['injection_direction']:
            raise ProductionRefused('sealed correction direction differs')
        for row,split in ((bound,'calibration'),(check,'holdout')):
            if row['eligible_sources'] != eligible[split] or type(row['coverage_sufficient']) is not bool or row['coverage_sufficient'] != coverage[split]:
                raise ProductionRefused('repair qualification source coverage differs')
        limit, ceiling = bound['max_injection_level'], bound['correction_amplitude_ceiling']
        if limit is None:
            if ceiling is not None:
                raise ProductionRefused('unsealed correction amplitude')
        else:
            if not coverage['calibration']:
                raise ProductionRefused('non-null repair bound lacks calibration coverage')
            if type(limit) not in (int,float) or limit not in LEVELS:
                raise ProductionRefused('sealed injection grid level required')
            _finite(ceiling,minimum=1e-300,maximum=8)
        expected_cases = [] if limit is None else [(sid,level) for sid in eligible['holdout'] for level in LEVELS if level <= limit]
        cases = _array(check['cases'],count=len(expected_cases))
        for case, pair in zip(cases,expected_cases):
            _fields(case,'source_id level measured passed within_fitted_parameter_domain','holdout measured case')
            if (type(case['level']) not in (int,float) or (case['source_id'],case['level']) != pair or
                    any(type(case[k]) is not bool for k in ('measured','passed','within_fitted_parameter_domain'))):
                raise ProductionRefused('holdout case provenance differs')
            if case['passed'] and not (case['measured'] and case['within_fitted_parameter_domain']):
                raise ProductionRefused('holdout case claims unsupported pass')
        want = bool(coverage['calibration'] and coverage['holdout'] and cases and all(c['passed'] for c in cases))
        if type(check['qualified']) is not bool or check['qualified'] != want:
            raise ProductionRefused('holdout qualified direction differs from checks')
        if want:
            qualified.append({k:check[k] for k in ('operation','injection_direction')})
    return qualified


def _replay_saved(sources, saved, sealed, profile):
    """Replay frozen summary reductions, never pixel fitting or measurement."""
    lookup={};gates={name:dict(requested=24,refused=0,not_exercised=0)
        for name in ('allowed_lighting','not_comparable','motion_defect')}
    declared={}
    for op in OPERATIONS:
        for sign in (-1,1):
            for level in LEVELS:
                declared[f'{op}_{"neg" if sign<0 else "pos"}_{level:g}']=(op,sign,level)
    declared.update(identity=('identity',0,0.),**{k:('context_gate',0,0.) for k in gates})
    for source,rows in zip(sources,saved):
        seen=set()
        for row in rows:
            case_id=row['case_id']
            if type(case_id) is not str or case_id not in declared or case_id in seen:
                raise ProductionRefused('saved control ids differ from frozen protocol')
            seen.add(case_id);op,sign,level=declared[case_id]
            if (row['source_id']!=source['source_id'] or row['split']!=source['split'] or row['operation']!=op or
                    type(row['injection_direction']) is not int or row['injection_direction']!=sign or
                    type(row['level']) not in (int,float) or row['level']!=level or
                    type(row['passed']) is not bool or row['conditional_operator_and_correspondence'] is not True):
                raise ProductionRefused('saved control provenance differs from frozen protocol')
            amplitude=row['estimated_amplitude']
            if amplitude is not None:
                _finite(amplitude,minimum=-8,maximum=8)
            if op in OPERATIONS:
                lookup[source['source_id'],op,sign,level]=row
            if case_id in gates:
                exercised=row['status']=='context_rejected'
                gates[case_id]['refused']+=int(exercised and row['passed'])
                gates[case_id]['not_exercised']+=int(not exercised)
        if seen!=set(declared):
            raise ProductionRefused('saved control coverage is incomplete')
    eligible={split:[s for s in sources if s['split']==split and s['eligible']] for split in ('calibration','holdout')}
    coverage={split:(len(rows)>=6 and len({s['scene_group'] for s in rows})>=6 and {s['genre'] for s in rows}==GENRES)
        for split,rows in eligible.items()}
    def correct(row,sign):
        a=row['estimated_amplitude']
        return type(a) in (int,float) and math.isfinite(a) and a*sign<=1e-12
    bounds=[]
    for op in OPERATIONS:
        for sign in (-1,1):
            limit=None;amplitudes=[]
            if coverage['calibration']:
                for level in LEVELS:
                    at=[lookup[s['source_id'],op,sign,level] for s in eligible['calibration']]
                    if any(row['passed'] is not True or not correct(row,sign) for row in at):break
                    limit=level;amplitudes.extend(abs(row['estimated_amplitude']) for row in at if row['estimated_amplitude'] is not None)
            bounds.append(dict(operation=op,injection_direction=sign,max_injection_level=limit,correction_direction=-sign,
                correction_amplitude_ceiling=max(amplitudes) if limit is not None and amplitudes else None,
                eligible_sources=[s['source_id'] for s in eligible['calibration']],coverage_sufficient=coverage['calibration'],
                reason=None if limit is not None else 'no_contiguous_pass' if coverage['calibration'] else 'insufficient_source_genre_coverage'))
    if bounds!=sealed['bounds']:
        raise ProductionRefused('sealed correction bounds contradict saved calibration summaries')
    checks=[]
    for bound in bounds:
        cases=[];limit=bound['max_injection_level'];op=bound['operation'];sign=bound['injection_direction']
        if limit is not None:
            for source in eligible['holdout']:
                for level in LEVELS:
                    if level>limit:break
                    row=lookup[source['source_id'],op,sign,level]
                    inside=correct(row,sign) and abs(row['estimated_amplitude'])<=bound['correction_amplitude_ceiling']+1e-12
                    cases.append(dict(source_id=source['source_id'],level=level,measured=True,
                        passed=bool(row['passed'] and inside),within_fitted_parameter_domain=inside))
        checks.append(dict(operation=op,injection_direction=sign,
            qualified=bool(coverage['holdout'] and cases and all(c['passed'] for c in cases)),coverage_sufficient=coverage['holdout'],
            eligible_sources=[s['source_id'] for s in eligible['holdout']],cases=cases,
            reason='no_calibrated_bound' if limit is None else None if coverage['holdout'] else 'insufficient_source_genre_coverage'))
    if checks!=profile['checks'] or gates!=profile['context_gates']:
        raise ProductionRefused('repair evaluation contradicts saved holdout/context summaries')


def verified_profile(path, *, reader):
    """Return (plain profile, sorted unique Artifact closure), without writes."""
    evidence = _Evidence(reader); reader.check()
    p = local(path); root = p.parent
    if p.name != 'experimental-repair-profile.json':
        raise ProductionRefused('explicit sealed experimental repair profile required')
    profile = _fields(evidence.read(p),PROFILE,'repair profile'); evaluated = _common(profile)
    if profile['evidence_only'] is not True:
        raise ProductionRefused('repair profile evidence_only must remain true')
    inputs_ref = evidence.read(root/'inputs-identity.json')
    if inputs_ref != profile['inputs']:
        raise ProductionRefused('independent repair input identity differs')
    inputs = _fields(evidence.read(root/'inputs.FROZEN.json',identity=inputs_ref),INPUTS,'repair frozen inputs')
    started = _time(inputs['created_at']); _text(inputs['authorization'])
    if (type(inputs['source_count']) is not int or inputs['source_count'] != 24 or
            type(inputs['requested_controls_per_source']) is not int or inputs['requested_controls_per_source'] != 74 or
            inputs['production_eligible'] is not False or inputs['limitations'] != LIMITATIONS):
        raise ProductionRefused('repair input scope/limitations differ')
    original_path = evidence.verify(inputs['index'])
    if original_path.is_relative_to(root) or root.is_relative_to(original_path.parent):
        raise ProductionRefused('repair study must remain independent of original index')
    original = evidence.read(original_path)
    if type(original) is not dict or original.get('sources') != inputs['sources']:
        raise ProductionRefused('repair copied source index differs from original')
    proto = evidence.read(root/'protocol.FROZEN.json',identity=inputs['protocol'])
    if _protocol(proto) > started:
        raise ProductionRefused('repair protocol created after inputs')
    _fields(inputs['versions'],'python numpy opencv','repair software versions')
    if inputs['versions'] != dict(python=sys.version,numpy=version('numpy'),opencv=version('opencv-python-headless')):
        raise ProductionRefused('repair dependency version drift')
    software = _array(inputs['software'])
    if [Path(s['path']) for s in software] != _software_paths():
        raise ProductionRefused('repair complete software inventory differs')
    for ref in software:
        evidence.verify(ref,runtime=False)
    archive = root/'software/calibrator.py'
    producer = next(s for s in software if Path(s['path']) == SOURCE_ROOT/'scripts/experiments/vco06_repair_calibration.py')
    evidence.verify(dict(path=str(archive),bytes=producer['bytes'],sha256=producer['sha256']))
    entries = _entries(inputs,evidence)
    seal_ref = evidence.read(root/'threshold-seal-identity.json')
    if profile['thresholds'] != seal_ref:
        raise ProductionRefused('independent threshold seal identity differs')
    sealed = _fields(evidence.read(root/'thresholds.SEALED.json',identity=seal_ref),
        'schema_version algorithm created_at purpose production_eligible inputs calibration_results bounds sources','repair sealed thresholds')
    sealed_at = _common(sealed)
    if sealed['inputs'] != inputs_ref or not started <= sealed_at <= evaluated:
        raise ProductionRefused('sealed repair input/time differs')
    evaluation = _fields(evidence.read(root/'evaluation.json',identity=profile['evaluation']),EVALUATION,'repair evaluation')
    _common(evaluation)
    if evaluation != {k:profile[k] for k in EVALUATION.split()} or profile['calibrated_bounds'] != sealed['bounds']:
        raise ProductionRefused('repair profile differs from sealed evaluation/bounds')
    if (type(profile['requested_sources']) is not int or profile['requested_sources'] != 24 or
            type(profile['requested_controls']) is not int or profile['requested_controls'] != 1776 or
            profile['source_groups_not_certified_independent'] is not True or profile['limitations'] != LIMITATIONS or
            profile['temporal_policy'] != TEMPORAL or profile['unsupported'] != UNSUPPORTED):
        raise ProductionRefused('repair conditional evidence scope differs')
    _fields(profile['context_gates'],'allowed_lighting not_comparable motion_defect','repair context gate counts')
    for counts in profile['context_gates'].values():
        _fields(counts,'requested refused not_exercised','repair context gate')
        for n in counts.values():
            integer(n,'context gate count',0)
        if counts['requested'] != 24 or counts['refused'] + counts['not_exercised'] != 24:
            raise ProductionRefused('repair context control coverage differs')
    refs = _array(sealed['calibration_results'],count=12) + _array(profile['holdout_results'],count=12)
    ordered = [e for split in ('calibration','holdout') for e in entries if e['split'] == split]
    measured=[_source_result(e,ref,root,evidence,started,sealed_at,evaluated) for e,ref in zip(ordered,refs)]
    sources=[item[0] for item in measured];saved=[item[1] for item in measured]
    if sealed['sources'] != [s for s in sources if s['split'] == 'calibration']:
        raise ProductionRefused('sealed baseline source eligibility differs')
    _replay_saved(sources,saved,sealed,profile)
    for row in _array(profile['qualified_directions']):
        _fields(row,'operation injection_direction','qualified repair direction')
        if type(row['injection_direction']) is not int:
            raise ProductionRefused('qualified repair direction must be an integer')
    if profile['qualified_directions'] != _directions(sealed['bounds'],profile['checks'],sources):
        raise ProductionRefused('repair qualified directions differ from holdout evidence')
    return profile,evidence.finish()


def load_profile(path, *, reader):
    return verified_profile(path,reader=reader)[0]
