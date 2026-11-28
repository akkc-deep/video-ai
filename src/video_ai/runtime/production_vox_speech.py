"""Approved paragraph narration with durable source audio and measured canonical unit cuts."""
import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import wave

from ..adapters.common import HttpClient
from ..adapters.voxcpm import VoxTtsClient
from ..config import read_json
from ..media.audio import audio_command
from ..media.narration import assemble_narration
from ..media.speech_alignment import measured_cuts, alignment_words
from ..media.timing import measure_envelope
from ..planning.production_timeline import ProductionAudioInfo
from ..planning.segments import speakable
from ..voxcpm.contracts import fingerprint, wav_metadata
from ..voxcpm.process import VoxServiceProcess
from .manifest import thaw
from .production_inputs import _save_bytes, check_stage_space
from .production_state import ArtifactStamp, ProductionRefused, run_path, sync_file, write_exclusive
from .production_support import commit_checkpoint, read_report, recover_checkpoint, stamps, sync_manifest_stage
from .storage_files import write_record, safe_path
from .owned_cleanup import cleanup_preserving_exception


def paragraph_plan(text, spans, *, narration=None):
    recipe = thaw(narration) if narration is not None else {}
    guard = recipe.get('onset_guard')
    capacity = 250-len(guard['text']) if guard else 250
    pause = recipe.get('paragraph_pause_ms',850)
    groups, current = [], []
    for span in spans:
        if span['kind'] == 'speech': current.append(span)
        elif '\n' in span['text'] or '\r' in span['text']:
            if current: groups.append(current); current = []
    if current: groups.append(current)
    result = []
    for group in groups:
        start, end = group[0]['start'], group[-1]['end']
        while start < end:
            stop = min(start+capacity, end)
            if stop < end:
                candidates = [i+1 for i in range(start+80,stop) if text[i] in '。！？；，,!?;']
                if candidates: stop = candidates[-1]
            if speakable(text[start:stop]):
                result.append(dict(unit_id=f'speech_{len(result)+1:04d}',start=start,end=stop,
                    text=text[start:stop],pause_after_ms=pause if stop == end else 0))
            start = stop
    if not result: raise ProductionRefused('no Vox speech paragraphs')
    result[-1]['pause_after_ms'] = 0
    return result


def _atomic_audio(path, raw):
    temp = path.with_name(uuid4().hex+'.wav')
    _save_bytes(temp,raw)
    try:
        wav_metadata(temp)
        temp.replace(path)
    finally: temp.unlink(missing_ok=True)


def _receipt(path, identity):
    if not path.exists(): return None
    record = read_json(path)
    if record['identity'] != identity: raise ProductionRefused('Vox cached inputs differ')
    for stamp in record['outputs'].values():
        safe_path(Path(stamp['path']),path.parent)
        ArtifactStamp.from_dict(stamp).verify()
    return record


def _processed(frozen, plan, *, paths, logger):
    run, recipe = logger.run_dir, thaw(frozen.config.tts.narration)
    directory = run/'production/vox'
    directory.mkdir(parents=True,exist_ok=True)
    client = VoxTtsClient(HttpClient(frozen.config.services['tts'],frozen.config.timeouts['tts_request'],logger),
        frozen.config.tts,reference_sha256=recipe['reference_sha256'],request_scope=str(run)+'/vox-paragraphs')
    controller = None
    outputs = {}
    try:
        for p in plan:
            uid = p['unit_id']; folder = directory/uid; folder.mkdir(exist_ok=True)
            identity = fingerprint(dict(paragraph=p,recipe=recipe))
            intent = dict(identity=identity,request_id=client.request_id(uid),body=client.payload(p['text']))
            intent_path = folder/'intent.json'
            if intent_path.exists():
                if read_json(intent_path) != intent: raise ProductionRefused('Vox original intent differs')
            else: write_exclusive(intent_path,intent)
            raw_path = folder/'raw.wav'
            raw_receipt = _receipt(folder/'raw.json',identity)
            if raw_receipt is None:
                if controller is None:
                    parts = urlsplit(frozen.config.services['tts'])
                    if parts.hostname != '127.0.0.1': raise ProductionRefused('Vox requires loopback service')
                    controller = VoxServiceProcess(paths.runtime_root,directory/'service',port=parts.port,
                        voice_profile=run/'production/inputs/vox/voice.json')
                    controller.start(timeout=frozen.config.timeouts['service_start'])
                # A new client always queries the original ID before any possible submission.
                response = client.synthesize(p['text'],unit_id=uid)
                _atomic_audio(raw_path,response.body)
                write_record(folder/'raw.json',dict(identity=identity,outputs=stamps(dict(raw=raw_path))))
            processed = _receipt(folder/'processed.json',identity)
            if processed is None:
                target = folder/(uuid4().hex+'-tempo.wav')
                audio_command((frozen.config.tools['ffmpeg'],'-v','error','-nostdin','-i',raw_path,
                    '-af','atempo=0.95','-ar','48000','-ac','1','-c:a','pcm_s16le',target),
                    paths=paths,logger=logger,unit_id=uid)
                wav_metadata(target); sync_file(target)
                processed = dict(identity=identity,outputs=stamps(dict(pcm=target)))
                write_record(folder/'processed.json',processed)
            outputs[uid] = Path(processed['outputs']['pcm']['path'])
    finally:
        if controller is not None:
            def shutdown():
                code=controller.stop(finish_pending=True,grace_seconds=frozen.config.timeouts['tts_request'])
                if code != 0: raise RuntimeError('owned Vox service did not stop cleanly')
            cleanup_preserving_exception(shutdown,logger=logger,stage='speech')
    return outputs


def _align(frozen, plan, outputs, *, paths, logger):
    directory = logger.run_dir/'production/vox'
    identity = fingerprint(dict(plan=plan,inputs=stamps(outputs)))
    cached = _receipt(directory/'alignment.json',identity)
    if cached: return read_json(Path(cached['outputs']['data']['path']))['paragraphs']
    request = directory/(uuid4().hex+'-align-request.json')
    write_exclusive(request,dict(paragraphs=[dict(p,audio_path=str(outputs[p['unit_id']])) for p in plan]))
    target = directory/(uuid4().hex+'-alignment.json')
    script = Path(__file__).resolve().parents[3]/'scripts/align_narration.py'
    audio_command((frozen.config.tools['tts_python'],'-B',script,'--request',request,'--output',target,
                   '--model',paths.runtime_root/'shared/models/funasr/timestamp'),paths=paths,logger=logger,
                   unit_id='vox_alignment',timeout=None)
    result = read_json(target)['paragraphs']
    if [p['unit_id'] for p in result] != [p['unit_id'] for p in plan]: raise ProductionRefused('alignment paragraph identity differs')
    sync_file(target)
    write_record(directory/'alignment.json',dict(identity=identity,outputs=stamps(dict(data=target))))
    return result


def _assembled(frozen, plan, outputs, alignment, *, logger):
    directory = logger.run_dir/'production/vox'
    identity = fingerprint(dict(plan=plan,inputs=stamps(outputs),alignment=alignment,recipe=thaw(frozen.config.tts.narration)))
    cached = _receipt(directory/'narration.json',identity)
    if cached: return cached['metadata']
    text = frozen.script.text
    assembled = assemble_narration(dict(units=plan,alignment='funasr-measured-after-tempo',source_text=text,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),voice=thaw(frozen.config.tts.narration),skips=[]),
        outputs,directory/(uuid4().hex+'-narration.wav'),target_rms_db=-23)
    write_record(directory/'narration.json',dict(identity=identity,outputs=stamps(dict(audio=assembled['audio_path'])),metadata=assembled))
    return assembled


def produce_vox_speech(frozen, units, *, state, manifest, paths, logger):
    from .production_speech import validate_speech_payload, SPAN_FIELDS
    alignment_words(frozen.script.text)  # Unsupported scripts fail before spending GPU work.
    complete = state.snapshot()['stages']['speech']['status'] == 'completed'
    report = read_report(state,'speech')
    if complete:
        if report is None: raise ProductionRefused('completed speech lacks report')
        audio = validate_speech_payload(report['payload'],run=state.run_dir,units=units)
        for item in units['spans']:
            if item['kind']=='speech' and not recover_checkpoint(state,'speech',item['unit_id']):
                raise ProductionRefused('completed Vox unit lacks checkpoint')
        sync_manifest_stage(manifest,'speech',state.run_dir/'production/speech.json')
        return audio
    state.start_stage('speech'); check_stage_space(frozen.config)
    if manifest.snapshot()['stages']['speech']['status'] == 'pending': manifest.record_stage('speech','running')
    recipe = thaw(frozen.config.tts.narration)
    plan = paragraph_plan(frozen.script.text,units['spans'],narration=recipe)
    guard = recipe.get('onset_guard')
    synthesis = [dict(p,text=guard['text']+p['text']) for p in plan] if guard else plan
    outputs = _processed(frozen,synthesis,paths=paths,logger=logger)
    if guard:
        from .production_vox_guard import prepare_guarded_bodies
        outputs = prepare_guarded_bodies(frozen,plan,outputs,logger=logger)
    alignment = _align(frozen,plan,outputs,paths=paths,logger=logger)
    assembled = _assembled(frozen,plan,outputs,alignment,logger=logger)
    tokens, times = [], []
    for p, clip, measured in zip(plan,assembled['clips'],alignment):
        # Validate each paragraph before translating its measured times to the assembled PCM.
        measured_cuts(p['text'],[dict(end=len(p['text']))],measured,clip['samples'])
        tokens.extend(measured['tokens'])
        times.extend([[v+clip['start_sample']/48 for v in pair] for pair in measured['timestamp']])
    speech = [p for p in units['spans'] if p['kind']=='speech']
    cuts = measured_cuts(frozen.script.text,speech,dict(tokens=tokens,timestamp=times),assembled['total_samples'])
    audio, spans, position = {}, [], 0
    with wave.open(assembled['audio_path'],'rb') as source:
        for item in units['spans']:
            if item['kind']=='skip': spans.append(item); continue
            uid=item['unit_id']; cp=recover_checkpoint(state,'speech',uid)
            if cp:
                saved=cp['payload']['span']
                if {k:saved[k] for k in SPAN_FIELDS} != item: raise ProductionRefused('Vox cached unit text differs')
                if saved['samples'] != cuts[position+1]-cuts[position]: raise ProductionRefused('Vox cached unit samples differ')
            else:
                path=state.run_dir/'production/audio'/uid/(uuid4().hex+'.wav')
                path.parent.mkdir(parents=True,exist_ok=True)
                source.setpos(cuts[position]); data=source.readframes(cuts[position+1]-cuts[position])
                with wave.open(str(path),'wb') as target:
                    target.setparams((1,2,48000,0,'NONE','')); target.writeframes(data)
                sync_file(path); stamp=ArtifactStamp.read(path)
                saved=dict(item,raw=ArtifactStamp.read(assembled['audio_path']).to_dict(),pcm=stamp.to_dict(),
                    samples=len(data)//2,sample_rate=48000,channels=1,sample_width=2)
                intent_path=logger.path(f'speech/{uid}.intent.json')
                intent=dict(engine='voxcpm2',span=item,narration=saved['raw'],
                    parents=stamps({p['unit_id']:state.run_dir/'production/vox'/p['unit_id']/'intent.json' for p in plan}))
                if intent_path.exists():
                    if read_json(intent_path) != intent: raise ProductionRefused('Vox slice intent differs')
                else: write_exclusive(intent_path,intent)
                request=dict(state='intent',intent_path=str(intent_path),client_id=fingerprint(intent),prompt_id=None,response_paths=[])
                state.record_unit('speech',uid,status='running',request=request)
                commit_checkpoint(state,'speech',uid,request=request,outputs=dict(raw=saved['raw'],pcm=saved['pcm'],
                    intent=ArtifactStamp.read(intent_path).to_dict(),
                    **stamps(dict(narration=state.run_dir/'production/vox/narration.json',alignment=state.run_dir/'production/vox/alignment.json'))),
                    payload=dict(text=item['text'],span=saved,estimate=thaw(measure_envelope(path))))
            if uid not in manifest.snapshot()['units']['speech']: manifest.record_unit('speech',uid,'running')
            if manifest.snapshot()['units']['speech'][uid]['status']=='running': manifest.record_unit('speech',uid,'completed')
            audio[uid]=ProductionAudioInfo(ArtifactStamp.from_dict(saved['pcm']),48000,1,2,saved['samples'])
            spans.append(saved); position+=1
    payload=dict(script_path=frozen.options['script_path'],spans=spans,total_speech_samples=assembled['total_samples'])
    validate_speech_payload(payload,run=state.run_dir,units=units)
    if report and report['payload'] != payload: raise ProductionRefused('Vox speech report differs')
    if report is None: state.write_report('speech',payload,input_records=stamps(dict(units=state.run_dir/'production/units.json')))
    state.complete_stage('speech'); sync_manifest_stage(manifest,'speech',state.run_dir/'production/speech.json')
    return audio
