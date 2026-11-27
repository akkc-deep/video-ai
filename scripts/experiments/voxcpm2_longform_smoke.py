"""TTS-VOX-06: one fixed-voice, multi-emotion/long-script GPU assembly."""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import traceback
from types import MappingProxyType

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.adapters.common import HttpClient
from video_ai.adapters.longform import LongFormSynthesizer
from video_ai.adapters.voxcpm import VoxTtsClient
from video_ai.config import load_config, read_json
from video_ai.media.narration import assemble_narration
from video_ai.planning.segments import segment_text
from video_ai.planning.speech import freeze_voice, plan_speech, validate_speech_plan
from video_ai.runtime.manifest import thaw
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import write_record
from video_ai.voxcpm.process import VoxServiceProcess
from video_ai.tts_config import TtsSettings
from voxcpm2_adapter_smoke import ExperimentLogger


def repair_synthesis(plan, voice, http, previous, output):
    """Experiment-only repair: query exact old requests; synthesize changed units once."""
    old_plan = read_json(previous/'speech-plan.json')
    if old_plan['voice'] != plan['voice'] or old_plan['source_sha256'] != plan['source_sha256']:
        raise ValueError('experiment repair requires the same frozen voice and source')
    validate_speech_plan(plan, voice)
    fields = ('start','end','synthesis_text','voice_id','seed','emotion','emotion_intensity','instruction')
    key = lambda unit: tuple(unit[name] for name in fields)
    old_units = {key(unit):unit for unit in old_plan['units']}
    clients = {reused:VoxTtsClient(http, TtsSettings('voxcpm2', voice.model_revision, voice.parameters),
        reference_sha256=voice.reference_sha256, request_scope=str(previous if reused else output)) for reused in (True,False)}
    audio = output/'audio'; (audio/'segments').mkdir(parents=True)
    paths, identities, reused_count = {}, {}, 0
    write_record(audio/'speech-plan.json', plan)
    for unit in plan['units']:
        old = old_units.get(key(unit))
        reused = old is not None
        client = clients[reused]
        client.settings = TtsSettings('voxcpm2', voice.model_revision, MappingProxyType(dict(voice.parameters,
            emotion=unit['emotion'], emotion_intensity=unit['emotion_intensity'], instruction=unit['instruction'])))
        request_unit = old['unit_id'] if reused else unit['unit_id']
        response = client.synthesize(unit['synthesis_text'], unit_id=request_unit)
        path = audio/'segments'/(unit['unit_id']+'.wav')
        path.write_bytes(response.body)
        paths[unit['unit_id']] = path
        identities[unit['unit_id']] = client.request_id(request_unit)
        reused_count += reused
        write_record(audio/'requests'/(unit['unit_id']+'.json'), dict(unit=unit,
            request_id=identities[unit['unit_id']], previous_completed_candidate=reused))
    result = assemble_narration(plan, paths, audio/'narration.wav')
    for clip in result['clips']: clip['request_id'] = identities[clip['unit_id']]
    write_record(audio/'tts-result.json', result)
    return result, dict(reused_completed_units=reused_count, newly_generated_units=len(plan['units'])-reused_count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--long-text', type=Path)
    parser.add_argument('--long-chars', type=int, default=1000)
    parser.add_argument('--repair-output', type=Path, help='Experiment-only: same source/voice, reuse original completed requests')
    args = parser.parse_args()
    if args.long_chars < 1:
        parser.error('--long-chars must be positive')
    root = VideoStorage().runtime_root
    output = root/'scratch/benchmarks/TTS-VOX-06'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True)
    report = dict(task_id='TTS-VOX-06', status='running', output=str(output))
    controller = None
    try:
        # Reuse established planning evidence; no redundant Ollama run or new ASR.
        if args.repair_output:
            args.repair_output = args.repair_output.absolute()
            emotion = read_json(args.repair_output/'emotion-plan.json')
            report['source'] = read_json(args.repair_output/'result.json')['source']
            report['repair_from'] = str(args.repair_output)
        else:
            previous = read_json(SOURCE/'docs/research/TTS-VOX-05-result.json')
            emotion = deepcopy(previous['plan'])
            long_source = args.long_text or Path(read_json(SOURCE/'docs/research/TTS-VOX-02-result.json')['output'])/'long-source.txt'
            full = long_source.read_bytes().decode('utf-8-sig')
            end = next((s.end for s in segment_text(full) if s.boundary == 'sentence' and s.end >= args.long_chars), len(full))
            long_text = full[:end]
            emotion['spans'][-1]['end'] += 2
            emotion['spans'][-1]['original_text'] += '\r\n'
            emotion['spans'][-1]['synthesis_text'] += '\r\n'
            start = len(emotion['source_text'])+2
            emotion['spans'].append(dict(span_id=f'emotion_{len(emotion["spans"])+1:04d}',
                start=start, end=start+len(long_text), original_text=long_text, synthesis_text=long_text,
                emotion='narrative', emotion_intensity=.3, tone='沉稳', pause_after_ms=0,
                instruction=emotion['base_style']+'，语气沉稳'))
            emotion['source_text'] += '\r\n'+long_text
            emotion['source_sha256'] = hashlib.sha256(emotion['source_text'].encode()).hexdigest()
            report['source'] = dict(emotion_plan='docs/research/TTS-VOX-05-result.json',
                narrative_text=str(long_source), available_long_chars=len(full), selected_long_chars=len(long_text),
                selection='prefix ending at first sentence boundary at or after requested character count',
                note='05 planned emotions followed by an explicit narrative span; no new Ollama claim')
        source = root/'shared/config/production.json'
        config = load_config(source)
        raw = thaw(config.raw)
        spec = read_json(SOURCE/'config/voxcpm2-deployment.json')
        raw['tts'] = dict(engine='voxcpm2', model_revision=spec['model_revision'])
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        controller = VoxServiceProcess(root, (args.repair_output or output)/'state', port=port)
        raw['services']['tts'] = controller.url
        config = load_config(source, raw=raw, voice=config.voice)
        voice = freeze_voice(config)
        plan = plan_speech(emotion, voice)
        write_record(output/'emotion-plan.json', emotion)
        write_record(output/'speech-plan.json', plan)
        report['planning'] = dict(source_chars=len(plan['source_text']), units=len(plan['units']),
            maximum_unit_chars=max(len(u['synthesis_text']) for u in plan['units']),
            emotions=sorted({u['emotion'] for u in plan['units']}), voice=voice.as_dict())
        print(json.dumps(dict(output=str(output), planning=report['planning']), ensure_ascii=False), flush=True)
        started = time.monotonic()
        report['health'] = controller.start()
        report['cold_service_ready_seconds'] = time.monotonic()-started
        http = HttpClient(controller.url, 300, ExperimentLogger(output))
        print('Generating changed units only' if args.repair_output else 'Generating every unit once, then assembling narration', flush=True)
        started = time.monotonic()
        if args.repair_output:
            result, report['repair'] = repair_synthesis(plan, voice, http, args.repair_output, output)
        else:
            result = LongFormSynthesizer(http, voice, request_scope=str(output)).synthesize(plan, output/'audio')
        report['synthesis_and_assembly_seconds'] = time.monotonic()-started
        assert sum(c['samples']+c['added_pause_samples'] for c in result['clips']) == result['total_samples']
        assert ''.join(r['original_text'] for r in sorted([*result['clips'],*result['skips']], key=lambda r:r['start'])) == plan['source_text']
        report.update(status='passed', result_path=str(output/'audio/tts-result.json'),
            audio_path=result['audio_path'], total_samples=result['total_samples'],
            duration_seconds=result['total_samples']/48000,
            added_pause_samples=result['added_pause_samples'], postprocess=result['postprocess'],
            original_coverage_verified=True, sample_total_verified=True,
            listening='not performed; no new subjective quality verdict')
        report['wall_rtf'] = report['synthesis_and_assembly_seconds']/report['duration_seconds']
        if args.repair_output:
            report['wall_rtf_note'] = 'Repair includes cached completed-task queries/downloads; not a fresh-generation performance result'
    except BaseException:
        report.update(status='failed', error=traceback.format_exc())
        raise
    finally:
        if controller is not None:
            report['owned_vox_exit_code'] = controller.stop()
        write_record(output/'result.json', report)
        print(json.dumps(dict(status=report['status'], output=str(output)), ensure_ascii=False), flush=True)
    if report.get('owned_vox_exit_code') != 0:
        raise RuntimeError('owned VoxCPM2 process did not exit cleanly')


if __name__ == '__main__':
    main()
