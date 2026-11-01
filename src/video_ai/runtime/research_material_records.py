"""Read-only Wan transaction evidence and explicitly non-production research contexts."""
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from ..adapters.common import strict_json
from ._scene_continuity_io import artifact, instant, local, uid, verify
from .manifest import validate_run_dir
from .production_state import ProductionRefused, object_fields
from .workflows import WorkflowTemplate, safe_comfy_path

MIB = 1024 ** 2
SOURCE_KIND = 'research_wan_material_v1'


def ref(value):
    return {k: value[k] for k in ('path', 'bytes', 'sha256')}


class ResearchReader:
    """Call-local identities; no cached JSON objects or cached verification authority."""
    def __init__(self, timeout=300):
        if type(timeout) not in (int, float) or not 0 < timeout <= 300:
            raise ProductionRefused('research timeout must be within 300 seconds')
        self.deadline = monotonic() + timeout
        self.frozen = {}
        self.json_paths = {}

    def check(self):
        if monotonic() >= self.deadline:
            raise TimeoutError('research deadline expired')

    def remaining(self):
        self.check()
        return self.deadline - monotonic()

    def capture(self, source, *, package=False):
        self.check()
        value = ref(source) if isinstance(source, dict) else artifact(source, runtime=not package, empty=True)
        path = verify(value, runtime=not package, empty=True)
        old = self.frozen.setdefault(str(path), value)
        if old != value:
            raise ProductionRefused('research input identity changed')
        return value

    def read(self, source, *, package=False):
        value = self.capture(source, package=package)
        path = Path(value['path'])
        size = value['bytes']
        self.json_paths[str(path)] = size
        if size > 16 * MIB or sum(self.json_paths.values()) > 256 * MIB:
            raise ProductionRefused('resource_limit: research JSON')
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != value['sha256']:
            raise ProductionRefused('research input changed during read')
        result = strict_json(raw)
        self.check()
        return result

    def verify_all(self):
        for value in self.frozen.values():
            self.check()
            verify(value, runtime=Path(value['path']).is_relative_to(Path('D:/VideoSi')), empty=True)


def _require(condition, message):
    if not condition:
        raise ProductionRefused(message)


def _http_exchange(path, reader):
    request = reader.read(path)
    stem = str(path)[:-len('.request.json')]
    response = reader.read(stem + '.response.json')
    body_ref = reader.capture(stem + '.body')
    _require(response.get('status') == 200 and response.get('error') is None
             and response.get('truncated') is False and response.get('bytes') == body_ref['bytes'],
             'incomplete or unsuccessful original HTTP response')
    _require(response.get('method') == request.get('method') and response.get('url') == request.get('url'),
             'HTTP request/response producer differs')
    return request, reader.read(body_ref)


def verify_wan_material(index_path, *, config, timeout=300, _reader=None):
    """Verify source transaction only; admission separately validates all VCO-02 pixels."""
    reader = _reader or ResearchReader(timeout)
    index = reader.read(index_path)
    object_fields(index, 'schema_version kind request result reference frames'.split(), 'research source index')
    _require(type(index['schema_version']) is int and index['schema_version'] == 1
             and index['kind'] == 'wan_material_evidence_v1', 'unsupported_source: research evidence index')
    _require(type(index['frames']) is list and 1 <= len(index['frames']) <= 4095,
             'resource_limit: research native frame records')
    request = reader.read(index['request'])
    _require(request.get('record_kind') == 'real_direct_wan_material_request'
             and not any(k in request for k in ('parent', 'parent_clip', 'revision_of')),
             'unsupported_source: direct unparented Wan transaction required')
    run = validate_run_dir(Path(request['run_dir']))
    options_ref = reader.capture(request['frozen_options'])
    _require(Path(options_ref['path']) == run / 'production/options.json', 'source options producer differs')
    options = reader.read(options_ref)
    manifest = reader.read(run / 'manifest.json')
    _require(options.get('run_id') == manifest.get('run_id') == run.name, 'source run identity differs')
    selected = reader.capture(request['selected_image'])
    model_input = reader.capture(request['actual_model_input'])
    _require((selected['bytes'], selected['sha256']) == (model_input['bytes'], model_input['sha256']),
             'selected image and actual model input bytes differ')
    _require(ref(manifest['inputs']['selected_image']) == selected, 'manifest selected image differs')
    conversion = reader.read(request['conversion'])
    _require(conversion.get('target') == selected and instant(conversion['created_at']) <= instant(request['created_at']),
             'reference conversion must precede original generation')
    for key in ('source', 'source_icc', 'target_icc'):
        if key in conversion:
            reader.capture(conversion[key])
    params = request['parameters']
    _require(params.get('fps') == 16 and type(params.get('length')) is int and 1 <= params['length'] <= 4095,
             'unsupported_source: complete native16 material required')
    _require(model_input['path'] == str(run / 'comfy/input' / safe_comfy_path(params['start_image'])),
             'actual LoadImage path differs')
    graph = reader.read(request['graph'])
    for key in ('wan', 'wan_mapping'):
        snap = options['workflow_snapshots'][key]
        reader.capture(snap['path'], package=True)
        _require(artifact(snap['path'], runtime=False)['sha256'] == snap['source_identity']['sha256'],
                 'frozen Wan template identity differs')
    template = WorkflowTemplate.load(Path(options['workflow_snapshots']['wan']['path']),
        Path(options['workflow_snapshots']['wan_mapping']['path']), config.models)
    mapping = template.mapping
    out = mapping['inputs']['output_prefix']
    prefix = safe_comfy_path(graph[out['node_id']]['inputs'][out['input']])
    _require(prefix.startswith(run.name + '/'), 'output prefix must belong to original run')
    _require(template.instantiate(params, output_prefix=prefix) == graph, 'Wan template/parameter/graph mismatch')
    recorded_graphs = [reader.read(v, package=True) for v in manifest['workflows'].values()]
    _require(graph in recorded_graphs, 'manifest has no matching actual graph')
    for key in ('wan_high', 'wan_low', 'text_encoder', 'vae'):
        stamp = options['model_stamps'].get(key)
        _require(stamp is not None, 'missing original model stamp')
        # Existing model stamps intentionally identify shared hard-linked model
        # resources by canonical path/size/mtime, unlike immutable evidence.
        path = local(stamp['path'], exists=False)
        stat = path.stat()
        _require(path.is_file() and path.resolve() == path and stat.st_size == stamp['bytes']
                 and stat.st_mtime_ns == stamp['mtime_ns'], 'source model stamp drift')
    http_dir = run / 'logs/production/http'
    inventory = sorted(http_dir.glob('*.request.json'))
    _require(0 < len(inventory) <= 4096, 'resource_limit: source HTTP inventory')
    requests = [(path, reader.read(path)) for path in inventory]
    posts = [(p, v) for p, v in requests if v.get('method') == 'POST']
    _require(len(posts) == 1, 'source must have exactly one original POST')
    post_path, post = posts[0]
    parsed = urlsplit(post['url'])
    _require(parsed.path == '/prompt' and parsed.hostname in ('127.0.0.1', 'localhost', '::1'),
             'original local prompt endpoint required')
    _require(post['json_body']['prompt'] == graph, 'submitted graph differs')
    client = uid(post['json_body']['client_id'])
    _, accepted = _http_exchange(post_path, reader)
    prompt = uid(accepted['prompt_id'])
    _require(accepted.get('node_errors') == {}, 'Wan submission contains node errors')
    _require(instant(request['created_at']) <= instant(post['started_at']) <= datetime.now(timezone.utc),
             'generation request timestamp order differs')
    histories = []
    for path, item in requests:
        if item.get('method') != 'GET' or item.get('url') != post['url'][:-len('/prompt')] + '/history/' + prompt:
            continue
        _, history = _http_exchange(path, reader)
        if prompt in history and history[prompt].get('status', {}).get('completed') is True:
            histories.append((path, history[prompt]))
    _require(histories, 'missing successful original prompt history')
    expected_output = None
    for path, history in histories:
        hprompt = history['prompt']
        _require(history['status'].get('status_str') == 'success' and hprompt[1] == prompt
                 and hprompt[2] == graph and hprompt[3].get('client_id') == client,
                 'history prompt/client/graph differs')
        node = history['outputs'][mapping['output']['node_id']]
        media = [v for values in node.values() if isinstance(values, list) for v in values
                 if isinstance(v, dict) and v.get('type') == 'output' and v.get('filename', '').endswith('.mp4')]
        _require(len(media) == 1, 'history must contain one complete Wan output')
        item = media[0]
        relative = safe_comfy_path(str(Path(item['subfolder']) / item['filename']))
        output = reader.capture(run / 'comfy/output' / relative)
        _require(str(Path(relative).with_suffix('')).replace('\\', '/').startswith(prefix + '_'),
                 'history output prefix differs')
        _require(expected_output is None or expected_output == output, 'history output changed')
        expected_output = output
    result = reader.read(index['result'])
    _require(result.get('status') == 'generated' and result.get('prompt_id') == prompt
             and result.get('request') == index['request'] and result.get('selected_image') == selected
             and result.get('original_model_output') == expected_output, 'generation result origin differs')
    video = reader.capture(result['video'])
    _require((video['bytes'], video['sha256']) == (expected_output['bytes'], expected_output['sha256']),
             'generated source is not byte-identical to original model output')
    reader.verify_all()
    _require(inventory == sorted(http_dir.glob('*.request.json')), 'source HTTP inventory changed')
    return dict(source_kind=SOURCE_KIND, origin_run=str(run), prompt_id=prompt,
        selected_image=selected, source=video, parameters=params, reference=index['reference'], frames=index['frames'],
        source_index=reader.capture(index_path), closure=[reader.frozen[k] for k in sorted(reader.frozen)],
        production_eligible=False, ready_for_propose=False)


def load_research_material_context(run_dir, *, reader=None):
    """Revalidate retained imports without writing files or claiming repair eligibility."""
    import json
    from ..config import load_config
    from .production_research_material import validate_material_analysis
    budget = reader or ResearchReader()
    run = validate_run_dir(Path(run_dir))
    options_ref = budget.capture(run / 'research/options.json')
    options = budget.read(options_ref)
    object_fields(options, 'schema_version execution_mode run_id source_kind config scene_research_material scene_continuity created_at'.split(), 'research options')
    _require(type(options['schema_version']) is int and options['schema_version'] == 1
             and options['execution_mode'] == 'research' and options['run_id'] == run.name
             and options['source_kind'] == SOURCE_KIND
             and options['scene_continuity'] == dict(schema_version=1, policy='advisory_v1'),
             'research options kind/policy/producer differs')
    policy = options['scene_research_material']
    object_fields(policy, 'schema_version policy commit'.split(), 'research material policy')
    _require(policy['schema_version'] == 1 and policy['policy'] == 'research_material_import_v1', 'research import policy differs')
    commit_ref = budget.capture(policy['commit'])
    _require(Path(commit_ref['path']) == run / 'research/material/commit.json', 'foreign research import commit')
    commit = budget.read(commit_ref)
    object_fields(commit, 'schema_version kind run_id material_id request origin selected_image source frame_map last_frame color_analysis closure created_at'.split(), 'research material commit')
    _require(type(commit['schema_version']) is int and commit['schema_version'] == 1
             and commit['kind'] == SOURCE_KIND and commit['run_id'] == run.name,
             'research commit kind/producer differs')
    uid(commit['material_id'])
    request = budget.read(commit['request'])
    _require(request['material_id'] == commit['material_id'] and request['config'] == options['config']
             and request['source_index'] == commit['origin']['source_index'], 'research import request binding differs')
    closure = commit['closure']
    _require([v['path'] for v in closure] == sorted({v['path'] for v in closure}), 'research closure must be sorted and unique')
    for value in closure:
        budget.capture(value, package=True)
    for pair in commit['origin']['copies']:
        original, copied = pair['original'], pair['copy']
        expected_name = hashlib.sha256(original['path'].encode('utf-8')).hexdigest() + Path(original['path']).suffix
        _require(Path(copied['path']) == run / 'research/material/evidence' / expected_name
                 and (original['bytes'], original['sha256']) == (copied['bytes'], copied['sha256'])
                 and original in closure and copied in closure, 'research retained evidence copy differs')
    config = load_config(Path(budget.capture(options['config'], package=True)['path']))
    source = verify_wan_material(commit['origin']['source_index'], config=config, _reader=budget)
    summary, rows, tail = validate_material_analysis(source, config=config, reader=budget)
    _require(source['prompt_id'] == commit['origin']['prompt_id'] and source['origin_run'] == commit['origin']['run_dir'],
             'research origin changed')
    _require(budget.read(commit['color_analysis']) == summary, 'research color analysis summary differs')
    mapping = budget.read(commit['frame_map'])
    _require(mapping == dict(schema_version=1, source=commit['source'], rows=rows), 'research full frame mapping differs')
    for key in ('source', 'selected_image'):
        kept = budget.capture(commit[key])
        _require((kept['bytes'], kept['sha256']) == (source[key]['bytes'], source[key]['sha256']), 'research retained media differs')
    last = budget.capture(commit['last_frame'])
    _require(last['sha256'] == hashlib.sha256(tail).hexdigest(), 'research tail differs from original full frame')
    epoch_ref = budget.capture(run / 'research/continuity/epoch.json')
    epoch = budget.read(epoch_ref)
    _require(epoch == dict(schema_version=1, run_id=run.name, source_kind=SOURCE_KIND,
             commit=commit_ref, options=options_ref, created_at=commit['created_at']), 'research epoch binding differs')
    assessment_path = run / 'research/continuity/assessment.json'
    assessment_ref = None
    if assessment_path.exists():
        from ..media.research_pair_report import validate_research_pair_report
        assessment_ref = budget.capture(assessment_path)
        assessment = budget.read(assessment_ref)
        _require(assessment['epoch'] == epoch_ref and assessment['commit'] == commit_ref,
                 'research assessment current epoch differs')
        manifest = budget.read(assessment['manifest'])
        _require([ref(f['record']) for f in manifest['clips'][0]['frames']] == source['frames']
                 and ref(manifest['references'][0]['record']) == source['reference'], 'assessment material frames differ')
        validate_research_pair_report(assessment['report'], manifest=manifest, config=config, timeout=budget.remaining())
    budget.verify_all()
    return dict(schema_version=1, run_id=run.name, material_id=commit['material_id'],
        status='research_input_ready', source_kind=SOURCE_KIND, source=commit['source'],
        selected_image=commit['selected_image'], commit=commit_ref, epoch=epoch_ref,
        assessment=assessment_ref, frame_map=commit['frame_map'], reference=source['reference'], frames=source['frames'],
        qualification='awaiting_qualification', full_video_observation='unverified',
        production_eligible=False, production_ready=False, ready_for_propose=False)
