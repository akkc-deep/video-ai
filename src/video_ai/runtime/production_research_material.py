"""Offline-only import into a separate, locked research run; never invokes Wan."""
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from ..config import load_config
from ..media.colorimetry import load_color_analysis_set
from ..media._continuity_audit import png_bytes
from ._scene_continuity_io import artifact, instant, local, nonempty, uid
from .manifest import now, validate_run_dir
from .production_state import RunLock, object_fields
from .research_material_records import ResearchReader, SOURCE_KIND, _require, ref, verify_wan_material


def _owned(lock):
    _require(ResearchReader().read(lock.path) == lock.owner, 'research import lost held run lock')


def _save_bytes(path, raw, lock):
    _owned(lock)
    path = local(path, exists=False)
    if path.exists():
        _require(path.read_bytes() == raw, 'immutable research output differs')
        return artifact(path, empty=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _owned(lock)
    os.rename(temporary, path)
    return artifact(path, empty=True)


def _save(path, value, lock):
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
    _require(len(raw) <= 16 * 1024 ** 2, 'resource_limit: research import JSON')
    return _save_bytes(path, raw, lock)


def _copy(value, folder, lock, reader):
    reader.capture(value, package=True)
    name = hashlib.sha256(value['path'].encode('utf-8')).hexdigest() + Path(value['path']).suffix
    target = local(folder / name, exists=False)
    _owned(lock)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.' + uuid4().hex + '.tmp')
        with Path(value['path']).open('rb') as source, temporary.open('xb') as output:
            while block := source.read(1024 ** 2):
                reader.check()
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        _owned(lock)
        os.rename(temporary, target)
    copied = artifact(target, empty=True)
    _require((copied['bytes'], copied['sha256']) == (value['bytes'], value['sha256']), 'research copy identity differs')
    reader.capture(value, package=True)
    return copied


def validate_material_analysis(source, *, config, reader):
    """Verify every original pixel, time and command, with no decode side effect."""
    frames = source['frames']
    count = source['parameters']['length']
    _require(len(frames) == count, 'complete original native frame sequence required')
    paths = [reader.capture(row)['path'] for row in frames] + [reader.capture(source['reference'])['path']]
    rows = []
    with load_color_analysis_set(paths, config=config, timeout=reader.remaining()) as color:
        records = color.frames
        sidecars = color.sidecars
        for i, entry in enumerate(records):
            value = entry['record']
            _require(value['status'] == 'ready' and value['analysis_space'] == 'srgb_rgb24_v1'
                     and value['pixels'] is not None, 'research input needs proven sRGB RGB8 pixels')
            raw = color.read_rgb(entry['record_identity']['path'])
            _require(raw is not None, 'missing research RGB pixels')
            expected_source = source['source'] if i < count else source['selected_image']
            _require(ref(value['source']) == expected_source, 'analysis belongs to a different original source')
            sidecar = sidecars[value['sidecar']['path']]
            video = sidecar['probe']['video']
            width, height = video['width'], video['height']
            _require(width == source['parameters']['width'] and height == source['parameters']['height']
                     and len(raw) == width * height * 3, 'research pixel dimensions differ')
            if i < count:
                _require(value['frame_index'] == i and value['mapping'] is not None
                         and value['mapping']['generated_frame_index'] == i
                         and value['mapping']['output_frame_index'] is None
                         and len(video['frames']) == count
                         and Fraction(value['pts']) * Fraction(value['time_base']) == Fraction(i, 16),
                         'research material frame/PTS/native16 mapping differs')
                probe = reader.read(sidecar['probe']['raw_probe'])
                _require(not any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])),
                         'research contribution must have no audio track')
                rows.append(dict(generated_frame_index=i, material_frame_index=i,
                                 pts=value['pts'], time_base=value['time_base']))
                if i == count - 1:
                    import numpy as np
                    tail = png_bytes(np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3))
                    tail_record = frames[i]
                    tail_command = value['command']
            else:
                _require(value['frame_index'] == 0, 'selected reference must be its original image')
        for identity in color.identities:
            reader.capture(identity, package=True)
    summary = dict(schema_version=1, source=source['source'], selected_image=source['selected_image'],
        reference=source['reference'], frames=frames, native_fps='16/1', native_frames=count,
        all_frames_ready=True, all_pixels_verified=True, has_audio=False,
        tail_analysis=tail_record, tail_decode_command=tail_command,
        full_video_observation='unverified', ready_for_propose=False)
    return summary, rows, tail


def bind_material_uuid(request, request_ref, *, paths):
    """One durable byte-exact request binding per full UUID, independent of timestamp."""
    material_id = uid(request['material_id'])
    when = instant(request['requested_at'])
    run = validate_run_dir(paths.runs_root / (when.strftime('%Y%m%d-%H%M%S') + '-' + UUID(material_id).hex[:12]))
    registry = local(paths.runs_root.parent/'research-material-imports'/f'{material_id}.json', exists=False)
    expected = dict(schema_version=1, material_id=material_id, run_dir=str(run),
                    request_bytes=request_ref['bytes'], request_sha256=request_ref['sha256'])
    if not registry.exists():
        registry.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(expected, sort_keys=True, separators=(',', ':'))+'\n').encode()
        temporary = registry.with_name(registry.name+'.'+uuid4().hex+'.tmp')
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.rename(temporary, registry)
        except FileExistsError:
            # Another owner won publication; preserve the temporary evidence and
            # validate the existing immutable binding instead of overwriting it.
            pass
    _require(ResearchReader().read(registry) == expected, 'material UUID already bound to a different request')
    return run


def prepare_import_run(run, request_bytes):
    try:
        run.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        saved = run/'research/material/request.json'
        _require(saved.is_file(), 'existing run is not the original research import')
        _require(local(saved).read_bytes() == request_bytes, 'existing run belongs to a different research request')


def import_research_material(request_path, *, paths, logger=None, timeout=300):
    reader = ResearchReader(timeout)
    request_ref = reader.capture(request_path)
    request = reader.read(request_ref)
    object_fields(request, 'schema_version material_id policy source_index config requested_at reason'.split(), 'research import request')
    _require(type(request['schema_version']) is int and request['schema_version'] == 1
             and request['policy'] == 'research_material_import_v1', 'unsupported research import policy')
    material_id = uid(request['material_id'])
    when = instant(request['requested_at'])
    _require(when <= datetime.now(timezone.utc), 'future research request forbidden')
    nonempty(request['reason'])
    config_path = reader.capture(request['config'], package=True)['path']
    config = load_config(Path(config_path))
    paths.validate()
    _require(paths.runs_root == config.project_root / 'runs', 'research runtime paths differ from config')
    source = verify_wan_material(request['source_index'], config=config, _reader=reader)
    summary, rows, tail = validate_material_analysis(source, config=config, reader=reader)
    reader.verify_all()
    originals = [reader.frozen[k] for k in sorted(reader.frozen)]
    run = bind_material_uuid(request, request_ref, paths=paths)
    paths.policy.validate_write(run, 'run')
    required = sum(v['bytes'] for v in reader.frozen.values()) + 16 * 1024 ** 3
    _require(shutil.disk_usage(paths.runs_root).free >= required, 'insufficient research output space')
    prepare_import_run(run, Path(request_path).read_bytes())
    with RunLock(run) as lock:
        root = run / 'research/material'
        saved_request = _save_bytes(root / 'request.json', Path(request_path).read_bytes(), lock)
        _require(reader.read(saved_request) == request, 'import request changed during capture')
        intent_path = root / 'intent.json'
        if intent_path.exists():
            intent = reader.read(intent_path)
            _require(intent['material_id'] == material_id and intent['request'] == saved_request, 'research UUID binding differs')
        else:
            intent = dict(schema_version=1, material_id=material_id, run_id=run.name,
                          request=saved_request, created_at=now())
            _save(intent_path, intent, lock)
        if ((root / 'commit.json').exists() and (run / 'research/options.json').exists()
                and (run / 'research/continuity/epoch.json').exists()):
            from .research_material_records import load_research_material_context
            context = load_research_material_context(run, reader=reader)
            return dict(schema_version=1, material_id=material_id, run_dir=str(run),
                        status=context['status'], commit=context['commit'], error=None)
        copies = [dict(original=value, copy=_copy(value, root / 'evidence', lock, reader)) for value in originals]
        copy_of = {entry['original']['path']: entry['copy'] for entry in copies}
        mapping_ref = _save(root / 'frame-map.json', dict(schema_version=1, source=copy_of[source['source']['path']], rows=rows), lock)
        analysis_ref = _save(root / 'color-analysis.json', summary, lock)
        tail_ref = _save_bytes(root / 'last-frame.png', tail, lock)
        tail_receipt = _save(root / 'last-frame-receipt.json', dict(schema_version=1,
            source=source['source'], generated_frame_index=len(rows)-1, analysis=summary['tail_analysis'],
            decode_command=summary['tail_decode_command'], output=tail_ref,
            operation='Lossless PNG serialization of validated original VCO-02 tail RGB'), lock)
        closure = {v['path']: v for v in [*originals, *(r['copy'] for r in copies),
            saved_request, mapping_ref, analysis_ref, tail_ref, tail_receipt, artifact(intent_path)]}
        commit = dict(schema_version=1, kind=SOURCE_KIND, run_id=run.name, material_id=material_id,
            request=saved_request, origin=dict(source_index=source['source_index'],
            run_dir=source['origin_run'], prompt_id=source['prompt_id'], copies=copies),
            selected_image=copy_of[source['selected_image']['path']], source=copy_of[source['source']['path']],
            frame_map=mapping_ref, last_frame=tail_ref, color_analysis=analysis_ref,
            closure=[closure[k] for k in sorted(closure)], created_at=intent['created_at'])
        reader.verify_all()
        commit_ref = _save(root / 'commit.json', commit, lock)
        options = dict(schema_version=1, execution_mode='research', run_id=run.name,
            source_kind=SOURCE_KIND, config=request['config'],
            scene_research_material=dict(schema_version=1, policy='research_material_import_v1', commit=commit_ref),
            scene_continuity=dict(schema_version=1, policy='advisory_v1'), created_at=intent['created_at'])
        options_ref = _save(run / 'research/options.json', options, lock)
        _save(run / 'research/continuity/epoch.json', dict(schema_version=1, run_id=run.name,
            source_kind=SOURCE_KIND, commit=commit_ref, options=options_ref,
            created_at=intent['created_at']), lock)
    from .research_material_records import load_research_material_context
    context = load_research_material_context(run, reader=reader)
    return dict(schema_version=1, material_id=material_id, run_dir=str(run),
                status=context['status'], commit=context['commit'], error=None)


def analyze_research_material(run_dir, manifest_path, *, timeout=300):
    from .research_material_records import load_research_material_context
    from .paths import RuntimePaths, create_run
    from .logging import RunLogger
    from ..media.research_pair_report import analyze_research_pairs, validate_research_pair_report, _full_manifest
    reader = ResearchReader(timeout)
    run = validate_run_dir(Path(run_dir))
    with RunLock(run) as lock:
        context = load_research_material_context(run, reader=reader)
        manifest_ref = reader.capture(manifest_path)
        manifest = _full_manifest(reader.read(manifest_ref))
        _require([ref(f['record']) for f in manifest['clips'][0]['frames']] == context['frames']
                 and ref(manifest['references'][0]['record']) == context['reference'], 'diagnostic material frame binding differs')
        options = reader.read(run / 'research/options.json')
        config = load_config(Path(options['config']['path']))
        root = run / 'research/continuity'
        intent_path = root / 'analysis-intent.json'
        if intent_path.exists():
            intent = reader.read(intent_path)
            _require(intent['manifest'] == manifest_ref and intent['epoch'] == context['epoch']
                     and intent['commit'] == context['commit'], 'research diagnostic intent binding differs')
            audit = validate_run_dir(Path(intent['audit_run_dir']))
        else:
            audit = create_run(RuntimePaths.from_config(config))
            intent = dict(schema_version=1, run_id=run.name, manifest=manifest_ref,
                epoch=context['epoch'], commit=context['commit'], audit_run_dir=str(audit), created_at=now())
            _save(intent_path, intent, lock)
        report_path = audit / 'logs/continuity/report.json'
        if not report_path.exists():
            analyze_research_pairs(manifest, config=config, paths=RuntimePaths.from_config(config),
                logger=RunLogger(audit), timeout=reader.remaining())
        verified = validate_research_pair_report(report_path, manifest=manifest, config=config, timeout=reader.remaining())
        report_ref = artifact(report_path)
        assessment_path = root / 'assessment.json'
        assessment = dict(schema_version=1, run_id=run.name, epoch=context['epoch'], commit=context['commit'],
            manifest=manifest_ref, report=report_ref, status='measured', repair_eligibility='awaiting_qualification',
            created_at=intent['created_at'])
        _save(assessment_path, assessment, lock)
        reader.verify_all()
        return dict(schema_version=1, run_dir=str(run), status='research_input_ready',
            assessment=artifact(assessment_path), report=report_ref, coverage=verified['report']['coverage'],
            qualification='awaiting_qualification', full_video_observation='unverified',
            production_eligible=False, ready_for_propose=False)
