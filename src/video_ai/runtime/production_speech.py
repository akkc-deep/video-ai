"""Original text submitted once, durable WAV recovery and stamp-based narration."""
from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

from ..adapters.common import AdapterError, HttpClient
from ..adapters.tts import TtsClient
from ..config import read_json
from ..media.audio import SpeechLimits, audio_command, standardize_production_wav
from ..media.timing import measure_envelope
from ..planning.production_timeline import ProductionAudioInfo
from ..planning.segments import TextSpan, validate_segments
from .manifest import thaw
from .owned_cleanup import stop_owned_preserving_exception
from .execution_limits import production_execution
from .production_inputs import _save_bytes, check_stage_space
from .production_state import (ArtifactStamp, ProductionRefused, integer, object_fields, run_path,
                               sync_file, write_exclusive)
from .production_support import (commit_checkpoint, mark_request_error, read_report, recover_checkpoint,
                                 recover_http, stamps, sync_manifest_stage)
from .service_specs import build_service_specs
from .services import ServiceConflictError, ServiceManager, port_listening
from .speech_checks import _runtime_voice_configuration, service_log, validate_fixed_voice_log

SPAN_FIELDS = ('start','end','text','kind','boundary','unit_id')
AUDIO_FIELDS = ('raw','pcm','samples','sample_rate','channels','sample_width')


def validate_speech_payload(payload, *, run, units=None):
    object_fields(payload,('script_path','spans','total_speech_samples'),'speech payload')
    if run_path(run,payload['script_path']) != run/'production/script.txt': raise ProductionRefused('speech script path differs')
    if not isinstance(payload['spans'],list): raise ProductionRefused('speech spans must be array')
    spans=[]; audio={}; total=0
    for item in payload['spans']:
        object_fields(item,SPAN_FIELDS if item.get('kind')=='skip' else (*SPAN_FIELDS,*AUDIO_FIELDS),'speech span')
        span=TextSpan(**{k:item[k] for k in SPAN_FIELDS}); spans.append(span)
        if span.kind == 'speech':
            for name in ('raw','pcm'):
                stamp=ArtifactStamp.from_dict(item[name]); run_path(run,stamp.path); stamp.verify()
            info=ProductionAudioInfo.from_dict(dict(stamp=item['pcm'],sample_rate=item['sample_rate'],
                channels=item['channels'],sample_width=item['sample_width'],samples=item['samples']))
            if span.unit_id in audio: raise ProductionRefused('duplicate speech audio')
            audio[span.unit_id]=info; total+=info.samples
    text=Path(payload['script_path']).read_bytes().decode('utf-8-sig')
    validate_segments(text,tuple(spans)); integer(payload['total_speech_samples'],'total_speech_samples',1)
    if payload['total_speech_samples'] != total: raise ProductionRefused('speech total samples differ')
    if units is not None and thaw(spans) != units['spans']: raise ProductionRefused('speech/units text relation differs')
    return audio


def runtime_voice_yaml(frozen, *, state, logger):
    blueprint=read_json(Path(frozen.options['tts_yaml_path']))
    data=_runtime_voice_configuration(blueprint,frozen.config.voice)
    relative=f'services/{uuid4().hex}/tts-runtime.yaml'
    path=logger.save_json(relative,data)
    sync_file(path)
    return path


def validate_production_voice_startup(frozen, yaml_path, *, paths, logger, manifest):
    # Parse with the service's bundled YAML implementation and check the actual loaded logs.
    result=audio_command((frozen.config.tools['tts_python'],'-B','-c',
        'import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1],encoding="utf-8"))))',yaml_path),
        paths=paths,logger=logger,unit_id='voice_configuration',timeout=30)
    installed=json.loads(result.stdout_path.read_text(encoding='utf-8'))
    expected=_runtime_voice_configuration(read_json(Path(frozen.options['tts_yaml_path'])),frozen.config.voice)
    actual=_runtime_voice_configuration(installed,frozen.config.voice)
    if actual['custom'] != expected['custom'] or installed['custom'] != expected['custom']:
        raise RuntimeError('TTS runtime YAML loaded settings differ')
    validate_fixed_voice_log(service_log(manifest),frozen.config.voice)


def _validate_intent(path, frozen, span, client):
    intent=read_json(Path(path))
    object_fields(intent,('unit_id','text','payload','voice_identity','client_id'),'TTS intent')
    if (intent['unit_id']!=span.unit_id or intent['text']!=span.text or intent['payload']!=client.payload(span.text) or
        intent['voice_identity']!=frozen.options['execution_policy']['input_identities']['voice']):
        raise ProductionRefused('original TTS intent differs from frozen text/voice')
    return intent


@production_execution
def produce_speech(frozen, units, *, state, manifest, paths, logger, limits=SpeechLimits()):
    report=read_report(state,'speech')
    complete=state.snapshot()['stages']['speech']['status']=='completed'
    if complete:
        if report is None: raise ProductionRefused('completed speech cursor lacks report')
        validate_speech_payload(report['payload'],run=state.run_dir,units=units)
    if not complete: state.start_stage('speech');check_stage_space(frozen.config)
    status=manifest.snapshot()['stages']['speech']['status']
    if status=='pending': manifest.record_stage('speech','running')
    elif status=='completed' and report is None: raise ProductionRefused('manifest speech ahead of evidence')
    elif status not in ('running','completed'): raise ProductionRefused('manifest speech has incompatible status')
    manager=ServiceManager(paths,manifest,logger);handle=None
    client=TtsClient(HttpClient(frozen.config.services['tts'],frozen.config.timeouts['tts_request'],logger),frozen.config.voice)
    spans=[];audio={}
    try:
        for item in units['spans']:
            span=TextSpan(**item)
            if span.kind=='skip': spans.append(item);continue
            uid=span.unit_id;cp=recover_checkpoint(state,'speech',uid)
            if cp:
                intent=_validate_intent(cp['request']['intent_path'],frozen,span,client)
                if cp['request']['client_id']!=intent['client_id'] or cp['payload']['text']!=span.text:
                    raise ProductionRefused('TTS completed request association differs')
                saved=cp['payload']['span']
                object_fields(saved,(*SPAN_FIELDS,*AUDIO_FIELDS),'completed speech span')
                if {k:saved[k] for k in SPAN_FIELDS}!=item: raise ProductionRefused('completed speech text differs')
                if cp['outputs'].get('raw')!=saved['raw'] or cp['outputs'].get('pcm')!=saved['pcm']:
                    raise ProductionRefused('completed PCM output association differs')
                info=ProductionAudioInfo.from_dict(dict(stamp=saved['pcm'],sample_rate=saved['sample_rate'],
                    channels=saved['channels'],sample_width=saved['sample_width'],samples=saved['samples']))
                backing=manifest.snapshot()['units'].get('speech',{}).get(uid)
                if backing is None: manifest.record_unit('speech',uid,'running')
                if manifest.snapshot()['units']['speech'][uid]['status']=='running': manifest.record_unit('speech',uid,'completed')
                spans.append(saved);audio[uid]=info;continue
            if complete: raise ProductionRefused('completed speech lacks original request checkpoints')
            intent_path=logger.path(f'speech/{uid}.intent.json')
            record=state.snapshot()['units'].get('speech',{}).get(uid)
            if intent_path.exists() or record and record['request']:
                intent=_validate_intent(intent_path,frozen,span,client)
                req=dict(state='intent',intent_path=str(intent_path),client_id=intent['client_id'],prompt_id=None,response_paths=[])
                if record is None: state.record_unit('speech',uid,status='running',request=req)
                else:
                    req=record['request']
                    if req is None or req['client_id']!=intent['client_id'] or req['intent_path']!=str(intent_path):
                        raise ProductionRefused('TTS request/state identity differs')
                try: raw_bytes,_,evidence=recover_http(logger,uid=uid,url=frozen.config.services['tts']+'/tts',payload=intent['payload'])
                except AdapterError as exc: mark_request_error(state,'speech',uid,exc)
            else:
                if handle is None:
                    try: occupied=port_listening(frozen.config.services['tts'],3)
                    except ServiceConflictError as exc: raise ProductionRefused(str(exc)) from exc
                    if occupied: raise ProductionRefused(f'external service listening at {frozen.config.services["tts"]}')
                    yaml_path=runtime_voice_yaml(frozen,state=state,logger=logger)
                    specs=build_service_specs(frozen.config,state.run_dir,production=True,frozen=frozen,store=manifest,tts_yaml_path=yaml_path)
                    try: handle=manager.ensure(specs['tts'])
                    except ServiceConflictError as exc: raise ProductionRefused(str(exc)) from exc
                    if not handle.owned: raise ProductionRefused(f'external TTS service: {handle.url}')
                    validate_production_voice_startup(frozen,yaml_path,paths=paths,logger=logger,manifest=manifest)
                intent=dict(unit_id=uid,text=span.text,payload=client.payload(span.text),
                            voice_identity=frozen.options['execution_policy']['input_identities']['voice'],client_id=uuid4().hex)
                write_exclusive(intent_path,intent)
                req=dict(state='intent',intent_path=str(intent_path),client_id=intent['client_id'],prompt_id=None,response_paths=[])
                state.record_unit('speech',uid,status='running',request=req)
                if uid not in manifest.snapshot()['units']['speech']: manifest.record_unit('speech',uid,'running')
                try:
                    import sys
                    print(f'[make-video] speech {uid}: GPT-SoVITS',file=sys.stderr,flush=True)
                    client.synthesize(span.text,unit_id=uid)
                except AdapterError as exc: mark_request_error(state,'speech',uid,exc)
                raw_bytes,_,evidence=recover_http(logger,uid=uid,url=frozen.config.services['tts']+'/tts',payload=intent['payload'])
            req=dict(req,response_paths=[str(intent_path),*evidence])
            try:
                if len(raw_bytes)<12 or raw_bytes[:4]!=b'RIFF' or raw_bytes[8:12]!=b'WAVE': raise RuntimeError('original TTS response is not a complete WAV')
                attempt=run_path(state.run_dir,state.run_dir/f'production/audio/{uid}/{uuid4().hex}')
                raw=attempt/'raw.wav';pcm=attempt/'pcm-48000.wav'
                _save_bytes(raw,raw_bytes);original=ArtifactStamp.read(raw)
                info=standardize_production_wav(raw,pcm,config=frozen.config,paths=paths,logger=logger,unit_id=uid,limits=limits)
                estimate=measure_envelope(pcm)
                if estimate.samples!=info.samples: raise RuntimeError('PCM sample/envelope mismatch')
                original.verify();info.stamp.verify();sync_file(raw);sync_file(pcm)
            except (ValueError,EOFError) as exc:
                # A confirmed invalid media result is execution failure, not an input refusal.
                failure=RuntimeError(f'{uid}: invalid original WAV/PCM: {exc}')
                state.record_unit('speech',uid,status='failed',request=dict(req,state='failed'),
                    error=dict(kind='InvalidAudio',message=str(failure),evidence_paths=req['response_paths']))
                raise failure from exc
            saved=dict(item,raw=original.to_dict(),pcm=info.stamp.to_dict(),samples=info.samples,
                       sample_rate=info.sample_rate,channels=info.channels,sample_width=info.sample_width)
            commit_checkpoint(state,'speech',uid,request=req,outputs=stamps(dict(raw=raw,pcm=pcm,
                              **{f'evidence_{i}':p for i,p in enumerate(req['response_paths'])})),
                              payload=dict(text=span.text,span=saved,estimate=thaw(estimate)))
            backing=manifest.snapshot()['units']['speech'].get(uid)
            if backing is None: manifest.record_unit('speech',uid,'running')
            if manifest.snapshot()['units']['speech'][uid]['status']=='running': manifest.record_unit('speech',uid,'completed')
            spans.append(saved);audio[uid]=info
            logger.event('speech',uid,'completed',dict(samples=info.samples))
        payload=dict(script_path=frozen.options['script_path'],spans=spans,total_speech_samples=sum(i.samples for i in audio.values()))
        validate_speech_payload(payload,run=state.run_dir,units=units)
        if report and report['payload']!=payload: raise ProductionRefused('speech report differs from original completed checkpoints')
        if not report: state.write_report('speech',payload,input_records=stamps({'units':state.run_dir/'production/units.json'}))
        if not complete: state.complete_stage('speech')
        sync_manifest_stage(manifest,'speech',state.run_dir/'production/speech.json')
        return audio
    finally: stop_owned_preserving_exception(manager,handle,logger,'speech')
