"""Versioned technical adapter for frozen real-model collections; no generation."""
from fractions import Fraction
from pathlib import Path
import re
from time import monotonic

from .natural_acquisition import identity, read_json, write_json, verify
from .natural_acquisition_runtime import _case, _verified_result, prepare_case
from ..config import load_config
from ..runtime._scene_continuity_io import local
from ..runtime.manifest import hash_file, thaw, now
from ..runtime.paths import RuntimePaths, create_run
from ..runtime.logging import RunLogger


def save_mapping_evidence(folder, source, rows, *, audit_id):
    """Keep input evidence outside the independent color audit's output tree."""
    if not isinstance(audit_id,str) or not re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{12}',audit_id):
        raise ValueError('canonical independent audit ID required')
    folder = local(folder,exists=False)
    proof = folder/'evidence'/('generated-mapping-'+audit_id+'.json')
    value = dict(source=thaw(hash_file(local(source))),rows=rows)
    if proof.exists():
        saved = read_json(proof)
        if (saved.get('rows') != rows or any(saved.get('source',{}).get(key) != value['source'][key]
                for key in ('path','bytes','sha256','mtime_ns'))):
            raise ValueError('immutable mapping evidence differs')
    else:
        write_json(proof,value)
    return proof


def _import_bound_case(root,plan,case,folder,result):
    index_path = folder/'source-index.json'
    index_ref = identity(index_path)
    index = read_json(index_path)
    gate = read_json(folder/'evidence/reference-gate.json')
    if (index.get('request') != result['request']
            or index.get('result') != identity(folder/'evidence/generation-result.json')
            or index.get('reference') != gate['analysis']):
        raise ValueError('source index/case binding differs')
    request_path = folder/'import-request.json'
    if request_path.exists():
        request = read_json(request_path)
        if request.get('source_index') != index_ref or request.get('config') != plan['config']:
            raise ValueError('import request/case binding differs')
    for path in folder.glob('preparation-v2-complete-*.json'):
        complete = read_json(path)
        if complete.get('source_index') != index_ref:
            raise ValueError('completed preparation/index binding differs')
        intent = read_json(verify(complete['intent']))
        if intent['case_id'] != case['case_id'] or intent['source'] != result['video']:
            raise ValueError('preparation intent/case binding differs')
        verify(intent['implementation'])
    imported = prepare_case(root,case['case_id'])
    if read_json(folder/'import-result.json') != imported:
        raise ValueError('retained import result/case binding differs')
    from ..runtime.research_material_records import load_research_material_context
    context = load_research_material_context(Path(imported['run_dir']))
    if (any(context['source'][key] != result['video'][key] for key in ('bytes','sha256'))
            or any(context['selected_image'][key] != case['reference'][key] for key in ('bytes','sha256'))):
        raise ValueError('imported source/reference case binding differs')
    return imported


def prepare_native_source_v2(root, case_id):
    plan, case, folder = _case(root,case_id)
    result = _verified_result(root,case,folder)
    index = folder/'source-index.json'
    if index.exists():
        return _import_bound_case(root,plan,case,folder,result)
    from ..media.colorimetry import inspect_color_asset, decode_analysis_frame, load_color_analysis_set
    from ..runtime.processes import run_logged
    from ..runtime.environment import build_child_env
    config = load_config(Path(plan['config']['path']))
    paths = RuntimePaths.from_config(config)
    logger = RunLogger(create_run(paths))
    intent = write_json(folder/('preparation-v2-'+logger.run_dir.name+'.json'),dict(
        schema_version=1,kind='native_material_preparation_v2',created_at=now(),case_id=case_id,
        collection=read_json(Path(root)/'collection-receipt.json')['collection'],
        implementation=identity(Path(__file__)),source=result['video'],audit_run=str(logger.run_dir),
        purpose='Technical all-frame source preparation only; no natural metrics or labels.'))
    command = run_logged([str(config.tools['ffprobe']),'-v','error','-count_frames','-show_streams','-show_frames',
        '-of','json',result['video']['path']],cwd=logger.run_dir,env=build_child_env(paths),timeout=300,
        logger=logger,stage='native_material_probe',unit_id='wan_material_0001')
    if command.returncode != 0 or command.timed_out:
        raise ValueError('complete native probe failed')
    probe = read_json(command.stdout_path)
    streams, frames = probe['streams'],probe['frames']
    if (len(streams) != 1 or streams[0]['codec_type'] != 'video' or len(frames) != 49
            or Fraction(streams[0]['r_frame_rate']) != 16 or Fraction(streams[0]['avg_frame_rate']) != 16
            or any(Fraction(f['pts'])*Fraction(streams[0]['time_base']) != Fraction(i,16) for i,f in enumerate(frames))):
        raise ValueError('complete native16/PTS/video-only contract differs')
    rows = [dict(asset_frame_index=i,clip_id='wan_material_0001',generated_frame_index=i,
        retained_frame_index=None,output_frame_index=None,pts=f['pts'],time_base=streams[0]['time_base'])
        for i,f in enumerate(frames)]
    proof = save_mapping_evidence(folder,Path(result['video']['path']),rows,audit_id=logger.run_dir.name)
    sidecar, _ = inspect_color_asset(dict(asset_id='generated_material',stage='generated',path=result['video']['path'],
        mapping=dict(rows=rows,evidence=[thaw(hash_file(proof))]),processing=dict(
            operation='Unmodified original real Wan output; technical preparation v2 with external input mapping.',
            upstream_ids=[],command_records=[])),config=config,paths=paths,logger=logger,timeout=300)
    records = []
    started = monotonic()
    for i in range(49):
        remaining = 300-(monotonic()-started)
        if remaining <= 0:
            raise TimeoutError('all49-frame color decode exceeded300 seconds')
        record, _ = decode_analysis_frame(sidecar,frame_index=i,config=config,paths=paths,logger=logger,timeout=remaining)
        if record['status'] != 'ready' or record['pixels'] is None:
            raise ValueError('every source frame requires actual proven sRGB pixels')
        records.append(identity(logger.root/'colorimetry/generated_material/analysis'/f'frame_{i:06d}.json'))
    with load_color_analysis_set([r['path'] for r in records],config=config,timeout=300) as reader:
        for row in records:
            if reader.read_rgb(row['path']) is None:
                raise ValueError('missing original RGB frame')
        reader.verify()
    gate = read_json(folder/'evidence/reference-gate.json')
    write_json(index,dict(schema_version=1,kind='wan_material_evidence_v1',request=result['request'],
        result=identity(folder/'evidence/generation-result.json'),reference=gate['analysis'],frames=records))
    write_json(folder/('preparation-v2-complete-'+logger.run_dir.name+'.json'),dict(intent=intent,
        source_index=identity(index),native_frames=49,all_pixels_verified=True,full_video_observation='unverified'))
    return _import_bound_case(root,plan,case,folder,result)
