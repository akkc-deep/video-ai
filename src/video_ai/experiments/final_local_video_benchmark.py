"""LVA-06 fixed quality benchmark. No production switches or GPU imports.

Batch envelopes, human interval unions and local process-warm observations are
different measurements. Baseline/final share one actual matrix by construction.
"""
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

from .wan_fast_profiles import Artifact, artifact, digest, write_once
from .upscale_experiment import SOURCE, read
from .upscale_experiment import baseline_api

PROFILE = 'quality_strict_serial_x264'
TRIALS = ('cold_1', 'warm_1', 'warm_2', 'warm_3')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True, slots=True, init=False)
class FinalBenchmarkPlan:
    """Own canonical bytes; mutable caller dictionaries never remain attached."""
    _json: str

    def __init__(self, schema_version, task_id, profile, assets, fixtures, trials):
        if (schema_version != 1 or task_id != 'LVA-06' or profile != PROFILE
                or tuple(trials) != TRIALS or set(fixtures) != {'low', 'high', 'chain'}):
            raise ValueError('fixed LVA-06 plan identity required')
        for value in assets.values(): Artifact(**value)
        value = dict(schema_version=schema_version, task_id=task_id, profile=profile,
                     assets=assets, fixtures=fixtures, trials=list(trials))
        object.__setattr__(self, '_json', _json(value))

    def identity_dict(self): return json.loads(self._json)
    def digest(self): return digest(self.identity_dict())


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('missing or nonfinite clock')
    return value


def _union(intervals, lower, upper):
    spans = []
    for a, b in intervals:
        _number(a); _number(b)
        if b < a: raise ValueError('clock reversed')
        a, b = max(lower, a), min(upper, b)
        if b > a: spans.append((a, b))
    total = 0.; end = lower
    for a, b in sorted(spans):
        total += max(0., b-max(end, a)); end = max(end, b)
    return total


def _percentile(values, fraction):
    if not values: return None
    values = sorted(values); i = (len(values)-1)*fraction
    a = math.floor(i); b = math.ceil(i)
    return values[a]+(values[b]-values[a])*(i-a)


def attribution_ledger():
    return dict(
        defaults=[dict(item='quality/strict/serial/libx264 medium CRF18',
                       source='docs/task-designs/LVA-05-completion.json', new_gain=False),
                  dict(item='historical capability cache, batch extraction/copy, single AV decode',
                       source='docs/task-designs/video-generation-performance-results.md', new_gain=False)],
        experimental=[dict(item='validation candidate', adopted=False, source='docs/task-designs/LVA-02-results.json'),
                      dict(item='bounded preparation', adopted=False, source='docs/task-designs/LVA-03-results.json'),
                      dict(item='prefetch/writeback mixed local observations; parent writeback 1.56%', adopted=False,
                           source='docs/task-designs/LVA-05-gpu-results.json')],
        rejected=[dict(item='distill native mixed diff/diff_b/diff_m incompatibility', source='docs/task-designs/LVA-04-completion.json'),
                  dict(item='NVENC RGB differs in 93/93 frames', source='docs/task-designs/LVA-05-completion.json')],
        unverified=['Sage/cache/compile unsupported or unverified', 'combined I/O not run',
                    '107-scene full-film throughput', 'physical weight transfers, kernel/exclusive idle'])


def summarize_final_results(inputs):
    batches = []; groups = defaultdict(list); seen = set()
    for data in inputs:
        if data['profile'] != PROFILE or data['batch_id'] in seen:
            raise ValueError('duplicate matrix batch or different profile')
        seen.add(data['batch_id']); t0 = _number(data['t0']); tend = _number(data['tend'])
        if tend < t0: raise ValueError('batch clock reversed')
        trials = data['trials']
        if [t['trial'] for t in trials] != list(TRIALS): raise ValueError('complete ordered trials required')
        human = _union([(v['start'], v['end']) for v in data['reviews']], t0, tend)
        active = _union([(v['start'], v['end']) for v in data.get('stages', [])], t0, tend)
        # Phases and human review must not overlap; overlap would misstate idle.
        both = _union([(v['start'], v['end']) for v in data.get('stages', [])+data['reviews']], t0, tend)
        if abs(both-active-human) > 1e-5: raise ValueError('active phase overlaps human review')
        envelopes = [_number(t['completed_at'])-t0 for t in trials]
        if any(v < 0 or v > tend-t0 for v in envelopes): raise ValueError('trial clock outside batch')
        accepted = all(t.get('quality_accepted') is True for t in trials)
        frames = sum(t['contribution_frames'] for t in trials)
        if frames <= 0 or data['fps'] != 16: raise ValueError('positive full frame budget and native16 required')
        usable = frames/16 if accepted else None
        batches.append(dict(batch_id=data['batch_id'], mode=data['mode'],
            batch_wall_seconds=tend-t0, human_wait_seconds=human,
            non_human_envelope_seconds=tend-t0-human, active_span_seconds=active,
            idle_other_waiting_seconds=tend-t0-both,
            trial_scheduling_envelopes_seconds=envelopes,
            envelope_scope='Overlapping trial envelopes include batch queueing; never sum for throughput.',
            accepted_video_seconds=usable,
            cost_per_usable_video_second=(tend-t0-human)/usable if usable else None,
            cost_missing_reason=None if usable else 'all four actual final quality decisions required',
            quality_decisions=data.get('quality_decisions', []),
            stages=data.get('stages', []), resources=data.get('resources', {}),
            counters=data.get('counters', {}), failed=data.get('failed', None), redone=data.get('redone', None)))
        batches[-1]['counters_complete']=data.get('counters_complete',False)
        batches[-1]['counter_scope']=data.get('counters_scope','not supplied')
        for sample in data.get('local_samples', []):
            seconds = sample.get('seconds')
            if seconds is None: continue
            if _number(seconds) < 0: raise ValueError('negative local clock')
            key = (data['batch_id'], sample['stage'], sample['mode'], sample['temperature'])
            groups[key].append(seconds)
    local = [dict(batch_id=k[0], stage=k[1], mode=k[2], temperature=k[3], samples=len(v),
                  p50_seconds=_percentile(v, .5), p95_seconds=_percentile(v, .95),
                  scope='local stage only; three warm observations are descriptive') for k, v in sorted(groups.items())]
    return dict(schema_version=1, task_id='LVA-06', profile=PROFILE,
                matrix_count=1 if batches else 0,
                report_identities=dict(baseline='new_actual_quality_matrix', final='new_actual_quality_matrix'),
                batches=batches, local_groups=local, attribution=attribution_ledger(),
                full_film_throughput=None, causal_speedup=None,
                historical_comparison='LVA-01 separate timing/environment/scheduling; no causal before/after ratio')


class FinalBenchmarkSession:
    """Append-only, chained coordinator events. UTC spans invocations/reviews.

    perf_counter measures only active spans within this process. An interrupted
    span remains unknown; resume never manufactures a duration or recounts it.
    The caller holds the batch lock for mutations.
    """
    def __init__(self, root, plan_sha256, *, utc=time.time, monotonic=time.perf_counter):
        self.root = Path(root); self.plan = plan_sha256
        self.utc, self.monotonic = utc, monotonic
        self.invocation = uuid4().hex; self._active = {}
        self.events = []
        for path in sorted((self.root/'events').glob('*.json')):
            event = read(path)
            if (event.get('plan_sha256') != self.plan or event.get('sequence') != len(self.events)
                    or event.get('previous_sha256') != (digest(self.events[-1]) if self.events else None)):
                raise ValueError('session event identity/sequence differs')
            if self.events and event['utc'] < self.events[-1]['utc']: raise ValueError('session clock reversed')
            self.events.append(event)

    def _event(self, kind, **details):
        now = _number(self.utc())
        if self.events and now < self.events[-1]['utc']: raise ValueError('session clock reversed')
        value = dict(schema_version=1, sequence=len(self.events), plan_sha256=self.plan,
                     previous_sha256=digest(self.events[-1]) if self.events else None,
                     invocation=self.invocation, utc=now, kind=kind, **details)
        write_once(self.root/'events'/f'{len(self.events):06d}.json', value)
        self.events.append(value); return value

    def record_selection_handoff(self):
        if self.events: raise ValueError('selection handoff already recorded')
        return self._event('selection_handoff')

    def enter_phase(self, name, trial=None):
        snapshot = self.snapshot()
        if snapshot['open_phases'] or snapshot['open_reviews']: raise ValueError('active phase or human review')
        key = (name, trial); self._event('phase_start', name=name, trial=trial)
        self._active[key] = self.monotonic()

    def finish_phase(self, name, trial=None, **evidence):
        key = (name, trial)
        recovering = evidence.pop('recovered', False)
        if key not in self._active:
            if not recovering or not any((e['name'], e['trial']) == key for e in self.snapshot()['open_phases']):
                raise ValueError('phase clock unavailable after interruption')
            seconds = None
        else:
            seconds = self.monotonic()-self._active[key]
            if seconds < 0: raise ValueError('phase clock reversed')
        value = self._event('phase_end', name=name, trial=trial, seconds=seconds, evidence=evidence)
        self._active.pop(key, None); return value

    def begin_review(self, kind, media_artifacts):
        if self.snapshot()['open_phases']: raise ValueError('close active service phase before review')
        if self.snapshot()['open_reviews']: raise ValueError('review already open')
        if not media_artifacts: raise ValueError('actual media required')
        for a in media_artifacts: Artifact(**a).verify()
        return self._event('review_start', review_kind=kind, media_artifacts=media_artifacts)

    def finish_review(self, actual_decision_artifact):
        Artifact(**actual_decision_artifact).verify(); decision = read(actual_decision_artifact['path'])
        opened = self.snapshot()['open_reviews']
        if len(opened) != 1: raise ValueError('exactly one pending review required')
        pending = opened[0]
        if (decision.get('task_id') != 'LVA-06' or decision.get('kind') != pending['review_kind']
                or decision.get('media_artifacts') != pending['media_artifacts']
                or decision.get('decision') not in ('accepted', 'rejected') or not decision.get('user_evidence')):
            raise ValueError('actual decision/media binding differs')
        for a in pending['media_artifacts']: Artifact(**a).verify()
        return self._event('review_end', review_kind=decision['kind'], decision=decision['decision'],
                           media_artifacts=pending['media_artifacts'], decision_artifact=actual_decision_artifact)

    def resume_original(self):
        if not self.events: raise ValueError('missing original selection clock')
        return self._event('resume_original')

    def finish_batch(self):
        prior = [e for e in self.events if e['kind'] == 'batch_end']
        if prior: return prior[0]
        snap = self.snapshot()
        if snap['open_phases'] or snap['open_reviews']: raise ValueError('batch has incomplete phase/review')
        return self._event('batch_end')

    def snapshot(self):
        phases = {}; reviews = {}; done = []; decisions = []
        for e in self.events:
            if e['kind'] == 'phase_start': phases[(e['name'], e['trial'])] = e
            elif e['kind'] == 'phase_end':
                start = phases.pop((e['name'], e['trial']))
                done.append(dict(name=e['name'], trial=e['trial'], start=start['utc'], end=e['utc'],
                                 active_seconds=e['seconds'], evidence=e['evidence']))
            elif e['kind'] == 'review_start': reviews[e['review_kind']] = e
            elif e['kind'] == 'review_end':
                start = reviews.pop(e['review_kind'])
                decisions.append(dict(kind=e['review_kind'], start=start['utc'], end=e['utc'],
                                      decision=e['decision'], decision_artifact=e['decision_artifact'],
                                      media_artifacts=e['media_artifacts']))
        return dict(t0=self.events[0]['utc'] if self.events else None, stages=done,
                    reviews=decisions, open_phases=list(phases.values()), open_reviews=list(reviews.values()))


def render_final_markdown(value):
    lines = ['# LVA-06 results', '', 'One actual quality/strict/serial/libx264 matrix shared by baseline and final.', '',
             '| Batch | Wall seconds | Human union | Non-human envelope | Cost / usable second |',
             '|---|---:|---:|---:|---:|']
    for b in value.get('batches', []):
        lines.append(f"| {b['batch_id']} | {b['batch_wall_seconds']:.3f} | {b['human_wait_seconds']:.3f} | {b['non_human_envelope_seconds']:.3f} | {b['cost_per_usable_video_second']} |")
    lines += ['', 'Trial envelopes overlap and include queueing. Local warm P50/P95 are separate.',
              'Historical microbenchmarks are not causal end-to-end gains. Full-film throughput is unverified.', '',
              '```json', json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), '```', '']
    return '\n'.join(lines)


_OriginalClient = baseline_api().ExperimentClient


def verify_final_plan(value, expected, *, boundary=False, verify_assets=True):
    if digest(value) != expected or value.get('task_id') != 'LVA-06' or value.get('profile') != PROFILE:
        raise ValueError('final plan identity drift')
    seen=set()
    for role,item in value['assets'].items():
        if not verify_assets:continue
        # The full historical provenance closure is admitted once under native
        # read leases by the coordinator. Per-HTTP guards check generation
        # tools/models/code, plus the exact current copied image/parent below.
        # Never rescan all old accepted videos/PCM solely for a polling request.
        if boundary and 'fixtures' in value and not (role in ('configuration','ffmpeg','ffprobe','comfy_python',
            'wan_workflow','wan_mapping','upscale_workflow','upscale_mapping','nvidia_smi')
            or role.startswith(('model_','source_','comfy_','torch_'))):continue
        key=(item['path'],item['bytes'],item['sha256'])
        if key not in seen:Artifact(**item).verify();seen.add(key)
    return value


def validate_final_launch(root, profile, port, *, verify_assets=True):
    root = Path(root)
    plan = verify_final_plan(read(root/'frozen/final-plan.json'), profile,verify_assets=verify_assets)
    launch, marker = read(root/'frozen/service-launch.json'), read(root/'experiment.json')
    if (marker.get('kind') != 'LVA-06' or marker.get('profile_sha256') != profile
            or launch.get('profile_sha256') != profile or launch.get('port') != port or marker.get('port') != port):
        raise ValueError('owned final launch identity differs')
    return plan


class FinalExperimentClient(_OriginalClient):
    """Original durable intent/accepted protocol, with separate LVA-06 identity."""
    def __init__(self, root, *, plan_sha256, port=8189, http=None, counters=None):
        self.profile = plan_sha256; self.transport = http
        self.counters = counters if counters is not None else dict(post=0, get=0)
        super().__init__(root, port=port, http=self._checked_http)

    def verify(self):
        value = verify_final_plan(read(self.root/'frozen/final-plan.json'), self.profile,boundary=True)
        if hasattr(self,'_current'): self._verify_current(value)
        if self.transport is None:
            validate_final_launch(self.root, self.profile, self.port,verify_assets=False)
            owner = read(self.root/'service-owner.json'); binding = self.root/'frozen/service-binding.json'
            if (owner.get('profile_sha256') != self.profile
                    or owner.get('launch_sha256') != digest(read(self.root/'frozen/service-launch.json'))):
                raise ValueError('original service identity differs')
            if binding.exists():
                if read(binding) != owner: raise ValueError('original owner replaced')
            elif list((self.root/'trials').glob('*/intent.json')):
                raise ValueError('original service binding missing')
            else: write_once(binding, owner)
        return value

    def _verify_current(self, plan):
        trial,graph=self._current
        # Small offline protocol unit fixtures deliberately have no native plan.
        # Real plans always carry the four exact source-clip definitions.
        if 'fixtures' in plan and self.root.name.startswith('native_'):
            name=self.root.name.removeprefix('native_')
            sources=[f['native'][name] for f in plan['fixtures'].values() if name in f['native']]
            if len(sources)!=1:raise ValueError('native source plan differs')
            source=sources[0];fixture=read(self.root/'fixture.json')
            expected=dict(source['fixture'])
            if name=='child':expected.update(input_sha256=None,input_relative=None,
                input_policy='Per-trial exact accepted new-parent retained last PNG')
            if fixture!=expected:raise ValueError('native fixture input/parameters drift')
            for local,original in [('original-request.json','request'),
                ('child-original-graph.json' if name=='child' else 'original-graph.json','graph')]:
                if read(self.root/'frozen'/local)!=read(source[original]['path']):raise ValueError('frozen native source drift')
        if '97' in graph:
            image=graph['97']['inputs']['image'];fixture=read(self.root/'fixture.json')
            binding=self.root/'trials'/trial/'parent-binding.json'
            expected_sha=fixture['input_sha256']
            if binding.exists():
                b=read(binding);parent=Path(b['parent_root'])/'trials'/b['parent_trial']
                result=read(parent/'technical-complete.json');approval=read(parent/'observation-accepted.json')
                if (b['input_relative']!=image or b['parent_generated_sha256']!=result['generated_sha256']
                        or b['parent_last_frame_sha256']!=result['last_frame_sha256']
                        or artifact(parent/'observation-accepted.json').sha256!=b['human_acceptance_sha256']
                        or approval.get('decision')!='accepted'
                        or any(approval.get(k+'_sha256')!=result[k+'_sha256'] for k in ('generated','retained','last_frame'))):
                    raise ValueError('child parent/acceptance input drift')
                baseline_api().validate_completed(result);expected_sha=b['parent_last_frame_sha256']
            elif fixture.get('input_relative')!=image:raise ValueError('native input path differs')
            target=(self.root/'input'/image).resolve()
            if not target.is_relative_to((self.root/'input').resolve()) or artifact(target).sha256!=expected_sha:
                raise ValueError('native input content drift')
            if 'fixtures' in plan:
                expected_graph=baseline_api().rebind_graph(read(source['graph']['path']),image,fixture['fixture_id']+'/'+trial)
                if graph!=expected_graph:raise ValueError('planned native graph drift')
        elif '1' in graph and 'image' in graph['1'].get('inputs',{}):
            image=graph['1']['inputs']['image'];target=(self.root/'input'/image).resolve()
            if not target.is_relative_to((self.root/'input').resolve()):raise ValueError('upscale input escapes root')
            if 'fixtures' in plan:
                label,index=trial.removeprefix('upscale_').rsplit('_',1);index=int(index)
                extraction=read(self.root/'postprocess'/label/'extraction.json')
                item=extraction['frames'][index-1]
                if Path(item['path']).resolve()!=target or artifact(target).sha256!=item['sha256']:
                    raise ValueError('upscale input source drift')
                expected_graph=read(plan['assets']['upscale_workflow']['path'])
                expected_graph['1']['inputs']['image']=f'upscale/{label}/frame_{index:06d}.png'
                expected_graph['5']['inputs']['filename_prefix']=f'upscale/{label}/frame_{index:06d}'
                if graph!=expected_graph:raise ValueError('planned upscale graph drift')

    def _checked_http(self, method, route, payload=None):
        self.verify()
        if self.transport is None: self.assert_owned_service()
        self.counters[method.lower()] += 1
        return (self.transport or super().http)(method, route, payload)

    def submit(self, trial_id, graph):
        self._current=(trial_id,graph)
        self.verify()
        folder = self.root/'trials'/trial_id; binding = folder/'final-binding.json'
        value = dict(plan_sha256=self.profile, graph_sha256=digest(graph))
        if (folder/'intent.json').exists() and not binding.exists():
            raise ValueError('original intent lacks final identity')
        write_once(binding, value)
        return super().submit(trial_id, graph)

    def completed(self, trial_id, graph, *, node='108'):
        """Authenticates local history without contacting a stopped service."""
        self._current=(trial_id,graph)
        self.verify(); folder = self.root/'trials'/trial_id
        binding = read(folder/'final-binding.json'); intent = read(folder/'intent.json')
        accepted = read(folder/'accepted.json'); pid = accepted['prompt_id']
        history = read(folder/'history.completed.json'); entry = history.get(pid, {})
        prompt = entry.get('prompt', [])
        if (binding != dict(plan_sha256=self.profile, graph_sha256=digest(graph))
                or intent.get('graph') != graph or intent.get('graph_sha256') != digest(graph)
                or len(prompt) < 4 or prompt[1] != pid or prompt[2] != graph
                or prompt[3].get('client_id') != intent['client_id']
                or entry.get('status', {}).get('completed') is not True
                or entry['status'].get('status_str') == 'error'):
            raise ValueError('original completion identity differs')
        outputs = entry.get('outputs', {}).get(node, {}).get('images', [])
        if len(outputs) != 1 or outputs[0].get('type') != 'output': raise ValueError('one original output required')
        item = outputs[0]; target = (self.root/'output'/item.get('subfolder', '')/item['filename']).resolve(strict=True)
        if not target.is_relative_to((self.root/'output').resolve()): raise ValueError('original output escapes root')
        return target, pid

    def wait(self, trial_id, graph, *, output_node='108', **kwargs):
        if (self.root/'trials'/trial_id/'history.completed.json').exists():
            return self.completed(trial_id, graph, node=output_node)
        return super().wait(trial_id, graph, output_node=output_node, **kwargs)


class FinalMediaCommands:
    """Success receipt is durable before postprocessing; unknown never reruns."""
    def __init__(self, root, plan_sha256, *, execute=None, counters=None):
        import subprocess
        self.root, self.plan = Path(root), plan_sha256
        self.execute = execute or subprocess.run
        self.counters = counters if counters is not None else dict(producer=0, decode=0, probe=0)

    def produce(self, name, argv, sources, output, *, cwd=None):
        output = Path(output).resolve(); args = list(map(str, argv))
        request = dict(plan_sha256=self.plan, args=args, cwd=str(Path(cwd).resolve()) if cwd else None,
                       sources=[artifact(p).identity_dict() for p in sources])
        if Path(args[0]).is_file(): request['tool'] = artifact(args[0]).identity_dict()
        intent = self.root/'commands'/(name+'.intent.json'); complete = intent.with_name(name+'.complete.json')
        if complete.exists():
            receipt = read(complete)
            if receipt['request'] != request: raise ValueError('original command/tool/source differs')
            Artifact(**receipt['output']).verify(); return receipt
        if intent.exists() or output.exists():
            raise baseline_api().OutcomeUnknown('original command outcome unknown; no automatic re-encoding')
        write_once(intent, request)
        before = time.perf_counter()
        if not getattr(self.counters,'observed',False):self.counters['producer'] += 1
        result = self.execute(args, cwd=cwd, capture_output=True, timeout=600, shell=False)
        if isinstance(result, bytes): code, stdout, stderr = 0, result, b''
        else: code, stdout, stderr = result.returncode, result.stdout, result.stderr
        for suffix, payload in (('.stdout', stdout), ('.stderr', stderr)):
            (self.root/'commands'/(name+suffix)).write_bytes(payload)
        if code: raise RuntimeError('original media command failed: '+name)
        receipt = dict(request=request, returncode=0, seconds=time.perf_counter()-before,
                       output=artifact(output).identity_dict())
        write_once(complete, receipt); return receipt


def stage_schedule(fixture):
    names = {'low': [('native_low', None), ('upscale_low', 'native')],
             'high': [('native_high', None), ('upscale_high', 'native')],
             'chain': [('native_parent', None), ('native_child', 'parent'), ('upscale_chain', 'child_continuity')]}
    if fixture not in names: raise ValueError('unknown fixed fixture')
    return [dict(name=name, requires_review=review,
                 temperatures=['process_cold', 'warm_process', 'warm_process', 'warm_process'])
            for name, review in names[fixture]]


@contextmanager
def batch_lock(root):
    """OS-held lock; stale text never authorizes a second coordinator."""
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    stream = (root/'coordinator.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if stream.seek(0, 2) == 0: stream.write(b'\0'); stream.flush()
            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally: stream.close()


def prepare_final_plan(output):
    """Read-only content admission; no torch, Comfy, service or media creation."""
    import subprocess
    from .upscale_manifest import select_native_case, _module
    from ..config import load_config
    from ..runtime.paths import RUNTIME_ROOT
    from ..runtime.verification import whole_input_protection
    from .wan_fast_profiles import QUALITY_SHA
    config = load_config(SOURCE/'config/production.example.json')
    baseline = read(SOURCE/'docs/task-designs/LVA-01-gpu-results.json')
    experiment = read(SOURCE/'docs/task-designs/LVA-01-gpu-experiments.json')
    assets = {}; native = {}
    def add(role, path, expected=None):
        a = artifact(path).identity_dict()
        if expected and a['sha256'] != expected: raise ValueError('source identity drift: '+role)
        assets[role] = a; return a
    with whole_input_protection(immutable_roots=()):
        # Actual decisions, not the wording of the old proposal, determine final.
        r4 = read(SOURCE/'docs/task-designs/LVA-04-results.json')
        r5 = read(SOURCE/'docs/task-designs/LVA-05-results.json')
        if (r4['default_mode'] != 'quality' or r4['default_adoption'] is not False
                or r5['adoption']['factor'] != 'serial' or r5['adoption']['encoder'] != 'libx264'
                or r5['adoption']['changed'] is not False):
            raise ValueError('baseline/final behavior differs; refuse duplicate or unreviewed matrix')
        for role in ('wan_high', 'wan_low', 'text_encoder', 'vae', 'upscale'):
            add('model_'+role, config.models[role])
        for role in ('ffmpeg', 'ffprobe', 'comfy_python'):
            add(role, config.tools[role])
        add('configuration', config.config_file)
        add('wan_workflow', SOURCE/'workflows/wan22_i2v_14b_api.json', QUALITY_SHA)
        add('wan_mapping', SOURCE/'workflows/wan22_i2v_14b_api.mapping.json')
        add('upscale_workflow', SOURCE/'workflows/upscale_api.json', 'a647f05940ce6b59de9bde8d5d53b9300bfe6b5174d900b3324eb6cd01680533')
        add('upscale_mapping', SOURCE/'workflows/upscale_api.mapping.json')
        for name in ('main.py', 'nodes.py', 'execution.py', 'comfyui_version.py', 'comfy/model_management.py',
                     'comfy/utils.py', 'comfy/ops.py', 'comfy_extras/nodes_upscale_model.py', 'comfy_extras/nodes_wan.py'):
            add('comfy_'+name, Path(config.tools['comfy_root'])/name)
        for folder, names in [('scripts', ('benchmark_final_local_video', 'observe_final_comfy', 'benchmark_local_gpu',
                                         'postprocess_local_gpu', 'observe_local_comfy', 'observe_upscale_comfy')),
                              ('src/video_ai/experiments', ('final_local_video_benchmark', 'final_local_video_execution',
                                                           'wan_fast_profiles', 'upscale_experiment', 'upscale_manifest')),
                              ('src/video_ai/runtime', ('local_video_metrics', 'local_comfy_metrics'))]:
            for name in names: add('source_'+name, SOURCE/f'{folder}/{name}.py')
        for task in range(1, 6):
            prefix = f'LVA-{task:02}'
            for suffix in ('design.md', 'results.json'):
                add(prefix+'-'+suffix, SOURCE/f'docs/task-designs/{prefix}-{suffix}')
        for name in ('LVA-01-completion.json', 'LVA-01-gpu-experiments.json', 'LVA-01-gpu-results.json',
                     'LVA-01-timing-evidence.json', 'LVA-04-completion.json', 'LVA-05-completion.json',
                     'LVA-05-gpu-results.json', 'LVA-05-gpu-recovery.json', 'video-generation-performance-results.md',
                     'jimeng-local-video-acceleration-v1.md'):
            add(name, SOURCE/'docs/task-designs'/name)
        helper = _module('_lva06_sources', SOURCE/'scripts/postprocess_local_gpu.py')
        for key in ('low', 'high', 'parent', 'child'):
            case, fixture = select_native_case(baseline['cases'], key)
            root = Path(case['root']); is_child = key == 'child'
            request_file = root/'frozen'/('child-original-request.json' if is_child else 'original-request.json')
            graph_file = root/'frozen'/('child-original-graph.json' if is_child else 'original-graph.json')
            req = read(request_file); graph = read(graph_file)
            from ..planning.production_scenes import canonical_digest
            if (canonical_digest(graph) != req['graph_sha256'] or req['clip_id'] != fixture['source_clip_id']
                    or req['budget'] != fixture['budget'] or req['parameters']['steps'] != 40
                    or req['parameters']['cfg'] != 3.5 or req['parameters']['lora_enabled']
                    or {k:v for k,v in req['parameters'].items() if k not in ('positive','negative')} != fixture['parameters']):
                raise ValueError('original quality source differs')
            if req['budget']['retained_frames'] != (77 if is_child else 93): raise ValueError('full frame budget differs')
            value = dict(source_root=str(root), fixture=fixture,
                         request=add(key+'_request', request_file), graph=add(key+'_graph', graph_file),
                         source_clip_id=req['clip_id'], requires_new_parent=is_child,
                         parameters={k:v for k,v in req['parameters'].items() if k not in ('positive', 'negative')},
                         budget=req['budget'])
            if not is_child:
                value['input'] = add(key+'_input', root/'input'/fixture['input_relative'], fixture['input_sha256'])
                original = next(f for f in experiment['fixtures'] if f['id'] == fixture['fixture_id'])
                add(key+'_original_request', original['source_request'], fixture['source_request_sha256'])
                selected = req['selected_image']
                # Frozen request contains original selected image identity separately.
                value['selected_image'] = selected
                add(key+'_selected_image',selected['path'],selected['sha256'])
            for name in ('narration-source.json', 'render-font.json'):
                add(key+'_'+name, root/name)
            narration = read(root/'narration-source.json'); font = read(root/'render-font.json')
            value['timeline'] = add(key+'_timeline', narration['path'], narration['sha256'])
            value['font'] = add(key+'_font', font['path'], font['sha256'])
            timeline = read(narration['path']); timeline = timeline.get('payload', timeline)
            for i, clip in enumerate(timeline['clips']):
                # Legacy stamp is size/mtime only: admit full content now,
                # without claiming that a historical full SHA existed.
                add(f'{key}_pcm_{i}', clip['pcm']['stamp']['path'])
            value['acceptance_sources'] = []
            for trial in TRIALS:
                actual = trial+'_child' if is_child else trial
                result = helper.require_native_review(root, actual)
                value['acceptance_sources'].append(add(key+'_'+trial+'_approval', root/'trials'/actual/'observation-accepted.json'))
                for name in ('technical-complete.json', 'intent.json', 'accepted.json', 'history.completed.json'):
                    add(key+'_'+trial+'_'+name, root/'trials'/actual/name)
                for name in ('generated', 'retained', 'last_frame'):
                    add(key+'_'+trial+'_'+name, result[name], result[name+'_sha256'])
            native[key] = value
        if native['child']['budget']['parent_clip_id'] != native['parent']['source_clip_id']:
            raise ValueError('source child parent differs')
        # Pin installed Python/Torch/CUDA without importing torch or initializing a device.
        code = 'import json,sys,importlib.metadata as m;print(json.dumps(dict(python=sys.version,packages={k:m.version(k) for k in ("torch","numpy","comfy-aimdo","comfy-kitchen")})))'
        environment = json.loads(subprocess.check_output([str(config.tools['comfy_python']), '-B', '-s', '-c', code], timeout=30))
        version = Path(config.tools['comfy_python']).parent/'Lib/site-packages/torch/version.py'
        add('torch_version', version); environment['torch_version_source'] = version.read_text('utf-8')
        # Bind native Python/library binaries used by this installed backend.
        site = Path(config.tools['comfy_python']).parent/'Lib/site-packages'
        for i, path in enumerate(sorted((site/'torch/lib').glob('*.dll'))): add('torch_binary_'+str(i), path)
        add('torch_C', next((site/'torch').glob('_C*.pyd')))
        from ..runtime.resources import find_nvidia_smi
        smi = find_nvidia_smi()
        if smi:
            add('nvidia_smi', smi)
            environment['device_driver'] = subprocess.check_output([str(smi), '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'], timeout=30).decode().strip()
        tag = time.strftime('%Y%m%d-%H%M%S', time.gmtime())+'-'+uuid4().hex[:6]
        fixtures = {}
        for key, parts in [('low', ['low']), ('high', ['high']), ('chain', ['parent', 'child'])]:
            root = RUNTIME_ROOT/'scratch/benchmarks'/('LVA-06-'+tag+'-'+key)
            fixtures[key] = dict(root=str(root.resolve()), native={k:native[k] for k in parts},
                                 schedule=stage_schedule(key), environment=environment,
                                 baseline_profile=PROFILE, final_profile=PROFILE)
        plan = FinalBenchmarkPlan(1, 'LVA-06', PROFILE, assets, fixtures, TRIALS)
        report = dict(schema_version=1, task_id='LVA-06', plan=plan.identity_dict(), plan_sha256=plan.digest(),
                      status='prepared_awaiting_specific_gpu_authorization', matrix_count=1,
                      limits=dict(wan=16, upscale=1424, compositions=12, owned_processes=7,
                                  concurrent_gpu_requests=1, downloads=0, nvenc=0, paid_calls=0),
                      production_resumed=False, attribution=attribution_ledger())
        write_once(output, report)
        return report


def run_final_batch(plan_path, fixture):
    from .final_local_video_execution import run_batch
    return run_batch(plan_path, fixture)


def load_final_measurement(path):
    """Read-only saved-data summary, including genuine later quality decisions."""
    path=Path(path);value=read(path);root=path.parent
    plan=read(root/'frozen/final-plan.json');sha=digest(plan)
    session=FinalBenchmarkSession(root,sha);snap=session.snapshot()
    bindings=[e for e in session.events if e['kind']=='measurement_complete']
    if len(bindings)!=1 or bindings[0]['measurement']!=artifact(path).identity_dict():
        raise ValueError('saved measurement identity drift')
    end=[e for e in session.events if e['kind']=='batch_end']
    if (len(end)!=1 or value['t0']!=snap['t0'] or value['tend']!=end[0]['utc']
            or value['stages']!=snap['stages']):raise ValueError('saved measurement clock/stage drift')
    final=[r for r in snap['reviews'] if r['kind']=='final']
    accepted=False
    if final:
        actual=final[0];Artifact(**actual['decision_artifact']).verify()
        decision=read(actual['decision_artifact']['path'])
        subjects=[artifact(t['candidate']).identity_dict() for t in value['trials']]
        if (actual['media_artifacts']!=subjects or decision.get('media_artifacts')!=subjects
                or decision.get('decision')!=actual['decision']):raise ValueError('final quality binding drift')
        accepted=actual['decision']=='accepted'
    for trial in value['trials']:trial['quality_accepted']=accepted
    value['quality_decisions']=snap['reviews']
    return value
