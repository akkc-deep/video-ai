"""A fresh, fixed-voice speech stage with durable per-unit evidence."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import wave

from ..adapters.common import AdapterError, FailureKind, HttpClient
from ..adapters.tts import TtsClient
from ..config import read_json
from ..media.audio import SpeechLimits, standardize_wav, audio_command
from ..planning.segments import SegmentedScript, validate_segments
from .component_checks import scan_isolation, validate_tts_configuration, validate_tts_load_log, INVENTORY
from .logging import RunLogger
from .manifest import ManifestStore, create_manifest, hash_file, now, thaw, validate_run_dir
from .migration import CopyEntry, ROOTS, atomic_report, copy_verified, scan_files
from .paths import RuntimePaths, RUNTIME_ROOT
from .service_specs import build_service_specs
from .services import ServiceManager, ServiceConflictError


@dataclass(frozen=True)
class SpeechResult:
    passed: bool
    run_dir: Path
    segments_path: Path
    total_speech_samples: int
    listened: bool


def freeze_inputs(config, script, *, revision_context=None):
    voice = config.voice
    if voice.device != 'cpu' or voice.is_half is not False:
        raise ValueError('fixed task-five voice requires CPU without half precision')
    if read_json(config.config_file) != thaw(config.raw) or read_json(voice.config_file) != thaw(voice.raw):
        raise OSError('loaded configuration differs from current source')
    inputs = {name:hash_file(path) for name,path in dict(script=script, config=config.config_file,
              voice=voice.config_file, tts_yaml=config.project_root/'config/tts-api.yaml',
              reference=voice.reference_audio).items()}
    if inputs['reference'].sha256 != voice.reference_sha256:
        raise OSError('fixed reference audio SHA256 changed')
    verification = RUNTIME_ROOT/'docs/video-ai/VAI-04-evidence/verification.json'
    evidence = read_json(verification)
    accepted = evidence.get('acceptance',{})
    acceptance_file = Path(accepted.get('path',''))
    acceptance_identity = hash_file(acceptance_file)
    if evidence.get('task') != 'VAI-04' or evidence.get('passed') is not True or acceptance_identity.sha256 != accepted.get('sha256'):
        raise OSError('task-four acceptance evidence changed or unverified')
    baseline = read_json(acceptance_file)
    if baseline.get('passed') is not True or baseline.get('components',{}).get('tts',{}).get('status') != 'passed':
        raise OSError('task-four fixed voice has no verified acceptance')
    if revision_context is None:
        validate_voice_baseline(inputs,baseline)
    else:
        from ._pipeline_voice_admission import verify_revision
        revision_context=verify_revision(config,script,revision_context)
        if revision_context.baseline_identity.sha256!=baseline.get('voice_sha256') or inputs['tts_yaml'].sha256!=baseline.get('tts_config_sha256'):
            raise OSError('revised voice installed baseline changed or unverified')
        inputs.update(voice_revision=revision_context.changes_identity,voice_revision_baseline=revision_context.baseline_identity)
    inputs.update(voice_acceptance=acceptance_identity,voice_verification=hash_file(verification))
    inventory = json.loads((INVENTORY/'files.json').read_text(encoding='utf-8'))
    expected = {str(Path(x['target'])).casefold():x['sha256'] for x in inventory if x.get('target') and x.get('sha256')}
    sources = {str(Path(x['source'])).casefold():x['sha256'] for x in inventory if x.get('sha256')}
    for source,target,_ in ROOTS:
        if str(Path(source)).casefold() in sources:
            expected[str(RUNTIME_ROOT/target).casefold()] = sources[str(Path(source)).casefold()]
    files = dict(gpt_weights=voice.gpt_weights, sovits_weights=voice.sovits_weights, reference=voice.reference_audio)
    for name in ('bert_root','hubert_root'):
        root = getattr(voice,name)
        if not root.is_dir(): raise OSError(f'missing voice model directory: {root}')
        listed = tuple(scan_files(root))
        if not listed: raise OSError(f'empty voice model directory: {root}')
        files.update({f'{name}/{file.relative_to(root).as_posix()}':file for file in listed})
    models = {}
    if revision_context is not None:
        from ._pipeline_voice_admission import revised_voice_files
        admitted=revised_voice_files(revision_context,files)
    for name,file in files.items():
        identity = hash_file(file)
        if revision_context is not None:
            if (identity.bytes,identity.sha256)!=(admitted[name].bytes,admitted[name].sha256):
                raise OSError('revised voice model/input changed')
        elif expected.get(str(file).casefold()) != identity.sha256:
            raise OSError(f'voice model/input differs from verified inventory: {file}')
        if name=='reference' and revision_context is not None:
            from ..media.audio import _wave_duration
            try:duration=_wave_duration(file)
            except EOFError as exc:raise ValueError('revised reference audio is not complete WAV') from exc
            if duration is None or duration<=0:raise ValueError('revised reference audio has no complete samples')
        models[name] = identity
    return inputs, models


def validate_voice_baseline(inputs, baseline):
    for name,key in (('voice','voice_sha256'),('tts_yaml','tts_config_sha256')):
        if inputs[name].sha256 != baseline.get(key):
            raise OSError(f'fixed {name} differs from accepted task-four voice')


def revalidate_identities(identities):
    for name,identity in identities.items():
        fresh = hash_file(Path(identity.path))
        if fresh.sha256 != identity.sha256 or fresh.bytes != identity.bytes or name=='tts_runtime' and fresh.mtime_ns!=identity.mtime_ns:
            raise OSError(f'frozen input/model changed: {identity.path}')


def _runtime_voice_configuration(installed,voice):
    from copy import deepcopy
    data=deepcopy(installed)
    custom=data.get('custom')
    if not isinstance(custom,dict):raise ValueError('installed TTS custom configuration missing')
    # The installed CPU/v2 route is immutable even when model paths are revised.
    for key,value in dict(version='v2',device='cpu',is_half=False).items():
        if type(custom.get(key))!=type(value) or custom[key]!=value:raise ValueError('installed TTS fixed route differs')
    custom.update(t2s_weights_path=str(voice.gpt_weights),vits_weights_path=str(voice.sovits_weights),
        bert_base_path=str(voice.bert_root),cnhuhbert_base_path=str(voice.hubert_root))
    validate_tts_configuration(data,voice)
    return data


def validate_voice_startup(config, *, paths, logger, revision_context=None, run_local=False):
    result = audio_command((config.tools['tts_python'],'-B','-c',
        'import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1],encoding="utf-8"))))',
        config.project_root/'config/tts-api.yaml'), paths=paths, logger=logger, unit_id='voice_configuration', timeout=30)
    installed=json.loads(result.stdout_path.read_text(encoding='utf-8'))
    if revision_context is None:
        validate_tts_configuration(installed,config.voice)
        if not run_local:return None
    logger.save_json('voice-installed-configuration.json',installed)
    data=_runtime_voice_configuration(installed,config.voice)
    semantic=logger.save_json('voice-runtime-configuration.json',data)
    # GPT-SoVITS saves yaml.dump at model startup. Use its bundled serializer
    # and Windows text newlines so these already frozen bytes remain stable.
    serialized=audio_command((config.tools['tts_python'],'-B','-c',
        'import yaml,json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); print(json.dumps(dict(configuration=d,yaml=yaml.dump(d))))',semantic),
        paths=paths,logger=logger,unit_id='voice_serialization',timeout=30)
    proof=json.loads(serialized.stdout_path.read_text(encoding='utf-8'))
    if set(proof)!= {'configuration','yaml'} or proof['configuration']!=data or not isinstance(proof['yaml'],str):
        raise ValueError('TTS bundled YAML serializer differs from current configuration')
    logger.save_json('voice-runtime-serialization.json',proof)
    return logger.save_bytes('voice-runtime-configuration.yaml',proof['yaml'].replace('\n',os.linesep).encode('utf-8'))


def service_log(store):
    record = store.snapshot()['services']['tts']
    return '\n'.join(Path(record[k]).read_text(encoding='utf-8',errors='replace') for k in ('stdout_path','stderr_path'))


def validate_fixed_voice_log(logs, voice):
    validate_tts_load_log(logs,voice)
    fields = {}
    for line in logs.splitlines():
        key, separator, value = line.partition(':')
        if separator: fields[key.strip()] = value.strip()
    for key,value in dict(device='cpu',is_half='False',version='v2').items():
        if fields.get(key) != value: raise ValueError(f'TTS loaded setting differs or missing: {key}')
    for field,key,name in [('t2s_weights_path','gpt_weights','Text2Semantic'),
                           ('vits_weights_path','sovits_weights','VITS'),
                           ('bert_base_path','bert_root','BERT'),('cnhuhbert_base_path','hubert_root','CNHuBERT')]:
        path = getattr(voice,key)
        actual = fields.get(field)
        if actual is None or Path(actual) != path or f'Loading {name} weights from {path.as_posix()}' not in logs.replace('\\','/'):
            raise ValueError(f'TTS loaded model differs or missing: {field}')


def _artifact(path):
    identity = thaw(hash_file(path))
    identity.pop('mtime_ns')
    identity['category'] = 'run'
    return identity


def _verify_artifact(identity):
    fresh = hash_file(Path(identity['path']))
    if fresh.sha256 != identity['sha256'] or fresh.bytes != identity['bytes']:
        raise OSError(f'completed audio/artifact changed: {identity["path"]}')


def _write_bytes(path, data, paths):
    path = paths.policy.validate_write(path,'run')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())


def _preview(run, spans, paths):
    target = paths.policy.validate_write(run/'audio/listening-preview.wav','run')
    total = 0
    with target.open('xb') as stream:
        with wave.open(stream,'wb') as out:
            out.setparams((1,2,48000,0,'NONE',''))
            for span in spans:
                if span['kind'] != 'speech': continue
                identity = span['pcm']
                path = paths.policy.validate_write(identity['path'],'run')
                fresh = hash_file(path)
                if fresh.sha256 != identity['sha256'] or fresh.bytes != identity['bytes']:
                    raise OSError('PCM changed before listening preview')
                with wave.open(str(path),'rb') as audio:
                    remaining = span['samples']
                    if audio.getnframes() != remaining: raise ValueError('preview sample mismatch')
                    while remaining:
                        count = min(remaining,65536)
                        data = audio.readframes(count)
                        if len(data) != count*2: raise ValueError('preview input truncated')
                        out.writeframesraw(data)
                        remaining -= count
                total += span['samples']
        stream.flush()
        os.fsync(stream.fileno())
    with wave.open(str(target),'rb') as check:
        if check.getnframes() != total: raise ValueError('preview total mismatch')
    return dict(identity=_artifact(target),samples=total,sample_rate=48000,preview_only=True)


def synthesize_script(config, script: Path, *, run_dir: Path, limits: SpeechLimits = SpeechLimits(),
                      store: ManifestStore | None = None, segmentation_path: Path | None = None) -> SpeechResult:
    return _synthesize_script(config,script,run_dir=run_dir,limits=limits,store=store,segmentation_path=segmentation_path)


def _synthesize_script(config, script, *, run_dir, limits=SpeechLimits(),store=None,segmentation_path=None,reuse_context=None):
    run = validate_run_dir(run_dir)
    if not run.is_dir(): raise ValueError('create_run must create the speech directory first')
    reviewed = None
    if segmentation_path is not None:
        from .pipeline_reviews import load_unit_review
        reviewed = load_unit_review(segmentation_path,script_path=script,run_dir=run)
    if store is not None:
        if reviewed is None and reuse_context is None: raise ValueError('shared pipeline speech requires unit review')
        if store.run_dir != run: raise ValueError('shared speech store belongs to another run')
        initial=store.snapshot()
        if reuse_context is None and (initial['stages']['preflight']['status']!='completed' or initial['stages']['speech']['status']!='pending'
                or initial['units']['speech'] or any((run/p).exists() for p in ('segments.json','script.txt','audio','voice-listening.json'))):
            raise ValueError('shared speech requires completed preflight, pending speech and no orphan audio')
        if initial['inputs'].get('script'):
            from .pipeline_reviews import fresh_identity
            fresh_identity(initial['inputs']['script'],expected=script)
    paths = RuntimePaths.from_config(config)
    store = store if store is not None else create_manifest(run,config,inputs={},models={},workflows={})
    logger = RunLogger(run)
    manager = ServiceManager(paths,store,logger)
    report_path = run/'segments.json'
    report = dict(schema_version=1, passed=False, run_dir=str(run), source=None, decoded_text=None,
                  has_bom=False, coverage_verified=False, spans=[], limits=thaw(limits),
                  total_speech_samples=0, listened=False, accepted=False, status='running', started_at=now())
    if reviewed is not None:
        report.update(schema_version=2,segmentation_identity=thaw(reviewed.identity),execution_policy=dict(
            gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300,
            tts_request_timeout_seconds=config.timeouts['tts_request']))
    if reuse_context is not None:
        report=read_json(report_path)
        report.update(passed=False,status='running',started_at=now(),listened=False,accepted=False)
        for key in ('error','finished_at','listening_preview'):report.pop(key,None)
        report['execution_policy']=dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300,
            tts_request_timeout_seconds=config.timeouts['tts_request'])
    store.record_stage('speech','running')
    atomic_report(report_path, report)
    handle, before, active, interruption = None, None, None, None

    def persist(action):
        """Keep the first interruption even when its diagnostics cannot be saved."""
        nonlocal interruption
        try:
            return action()
        except BaseException as exc:
            if interruption is not None:
                return None
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):
                interruption=exc
                report.update(passed=False,status='interrupted',error=dict(
                    kind=type(exc).__name__,message=str(exc),traceback_path=None,evidence_paths=[]))
                return None
            raise

    def submit(text, unit_id, item):
        nonlocal active
        active = item
        item['unit_id'] = unit_id
        item['status'] = 'running'
        store.record_unit('speech',unit_id,'running')
        atomic_report(report_path, report)
        if handle.process.poll() is not None: raise OSError('owned TTS process exited')
        payload = tts.payload(text)
        intent = logger.save_json(f'tts/{unit_id}.intent.json', dict(unit_id=unit_id, text=text,
                      payload=payload, voice_sha256=inputs['voice'].sha256 if 'voice' in inputs else None,
                      created_at=now(), automatic_retry=False))
        store.update(lambda data:data['events'].append(dict(time=now(),stage='speech',unit_id=unit_id,
                     action='tts_intent',evidence_paths=[str(intent)])))
        response = tts.synthesize(text,unit_id=unit_id)
        raw, pcm = run/'audio'/unit_id/'raw.wav', run/'audio'/unit_id/'pcm-48000.wav'
        _write_bytes(raw,response.body,paths)
        item['raw'] = _artifact(raw)
        item['http_evidence_path'] = str(response.evidence_path)
        atomic_report(report_path,report)
        info = standardize_wav(raw,pcm,config=config,paths=paths,logger=logger,unit_id=unit_id,limits=limits)
        verified_pcm = _artifact(pcm)
        if verified_pcm['sha256'] != info.sha256 or verified_pcm['bytes'] != info.bytes:
            raise OSError('PCM changed after conversion validation')
        _verify_artifact(item['raw'])
        item.update(pcm=verified_pcm, samples=info.samples, sample_rate=info.sample_rate,
                    channels=info.channels, sample_width=info.sample_width, duration=info.duration,
                    audio_evidence_path=str(logger.root/f'audio/{unit_id}.validation.json'))
        store.record_unit('speech',unit_id,'completed',artifacts=[item['raw'],item['pcm']])
        item['status'] = 'completed'
        atomic_report(report_path,report)
        active = None

    try:
        identity = hash_file(script)
        copy = hash_file(run/'script.txt') if reuse_context is not None else copy_verified(CopyEntry(script,run/'script.txt','run',identity.bytes,identity.sha256),logger=logger)
        if (copy.bytes,copy.sha256)!=(identity.bytes,identity.sha256):raise OSError('reused script copy differs')
        parsed = SegmentedScript.read(run/'script.txt')
        if reviewed is not None:
            if (parsed.text,parsed.has_bom)!=(reviewed.script.text,reviewed.script.has_bom):raise OSError('reviewed script copy changed')
            parsed=reviewed.script
        if reuse_context is None:
            report.update(source=thaw(identity), script_copy=thaw(copy), decoded_text=parsed.text, has_bom=parsed.has_bom,
                          coverage_verified=True, spans=[dict(thaw(span),status='pending' if span.kind=='speech' else 'skip') for span in parsed.spans])
        else:
            from dataclasses import fields
            from ..planning.segments import TextSpan
            spans=tuple(TextSpan(**{f.name:item[f.name] for f in fields(TextSpan)}) for item in report['spans'])
            validate_segments(parsed.text,spans);parsed=SegmentedScript(parsed.text,parsed.has_bom,spans)
        atomic_report(report_path,report)
        if not any(span.kind=='speech' for span in parsed.spans): raise ValueError('input has no speech text')
        from ._pipeline_voice_admission import voice_revision
        revision=voice_revision(config,run,script) if store is not None else None
        inputs, models = freeze_inputs(config,script,revision_context=revision) if revision is not None else freeze_inputs(config,script)
        if inputs['script'].sha256 != identity.sha256: raise OSError('script changed before voice freeze')
        existing=store.snapshot()['inputs']
        for name,record in existing.items():
            if name in inputs:
                from .pipeline_reviews import fresh_identity
                fresh_identity(record,expected=Path(inputs[name].path))
                if (record['bytes'],record['sha256'])!=(inputs[name].bytes,inputs[name].sha256):raise OSError('preflight input changed')
        store.update(lambda data:(data['inputs'].update(thaw(inputs)),data['models'].update(thaw(models))))
        report.update(inputs=thaw(inputs),models=thaw(models),voice_snapshot=thaw(config.voice))
        before = scan_isolation(config,logger=logger)
        logger.save_json('isolation/speech-before.json',before)
        startup_options={}
        if revision is not None:startup_options['revision_context']=revision
        # Formal schema2 startup must never rewrite the installed baseline.
        # Isolation follows freeze_inputs; it grants no voice revision rights.
        if report['schema_version']==2:startup_options['run_local']=True
        runtime_yaml=validate_voice_startup(config,paths=paths,logger=logger,**startup_options)
        if runtime_yaml is not None:
            inputs.update(tts_runtime=hash_file(runtime_yaml),tts_installed_data=hash_file(logger.root/'voice-installed-configuration.json'),
                tts_runtime_data=hash_file(logger.root/'voice-runtime-configuration.json'),
                tts_serialization=hash_file(logger.root/'voice-runtime-serialization.json'))
            store.update(lambda data:data['inputs'].update(thaw(inputs)))
            report['inputs']=thaw(inputs)
        revalidate_identities(inputs)
        spec=build_service_specs(config,run)['tts']
        if runtime_yaml is not None:
            from dataclasses import replace
            args=list(spec.args);args[args.index('-c')+1]=str(runtime_yaml);spec=replace(spec,args=tuple(args))
        candidate = manager.ensure(spec)
        if not candidate.owned: raise ServiceConflictError('external TTS instance cannot prove this run fixed voice; preserved')
        handle = candidate
        if runtime_yaml is not None:
            validate_fixed_voice_log(service_log(store),config.voice)
            before_runtime=inputs['tts_runtime'];after_runtime=hash_file(runtime_yaml)
            if (before_runtime.bytes,before_runtime.sha256)!=(after_runtime.bytes,after_runtime.sha256):
                raise OSError('owned TTS startup changed runtime YAML content')
            receipt=logger.save_json('voice-runtime-startup.json',dict(schema_version=1,owned=True,
                runtime_config_path=str(runtime_yaml),before=dict(bytes=before_runtime.bytes,sha256=before_runtime.sha256,
                mtime_ns=before_runtime.mtime_ns),after_identity=thaw(after_runtime),recorded_at=now()))
            inputs.update(tts_runtime=after_runtime,tts_runtime_startup=hash_file(receipt))
            store.update(lambda data:data['inputs'].update(thaw(inputs)))
            report['inputs']=thaw(inputs)
        tts = TtsClient(HttpClient(config.services['tts'],config.timeouts['tts_request'],logger),config.voice)
        if reuse_context is None:report['reference_replay'] = dict(status='pending', text=config.voice.reference_text)
        if report['reference_replay']['status']!='completed':submit(config.voice.reference_text,'reference_replay',report['reference_replay'])
        for span in report['spans']:
            if span['kind']=='speech' and span['status']!='completed': submit(span['text'],span['unit_id'],span)
        validate_segments(parsed.text,parsed.spans)
        validate_fixed_voice_log(service_log(store),config.voice)
        manager.stop(handle)
        handle = None
        revalidate_identities(inputs)
        revalidate_identities(models)
        if hash_file(run/'script.txt').sha256 != identity.sha256: raise OSError('copied script changed')
        report['listening_preview'] = _preview(run,report['spans'],paths)
        report['total_speech_samples'] = sum(span.get('samples',0) for span in report['spans'] if span['kind']=='speech')
        after = scan_isolation(config,logger=logger)
        logger.save_json('isolation/speech-after.json',after)
        changes = {path:dict(before=before.get(path),after=after.get(path)) for path in set(before)|set(after)
                   if before.get(path,{}).get('sha256') != after.get(path,{}).get('sha256')}
        logger.save_json('isolation/speech-changes.json',changes)
        if changes: raise OSError('tool/config/source/model/cache writes detected; see isolation changes')
        # The scan can take minutes. Freeze inputs and every delivered run artifact again afterward.
        revalidate_identities(inputs)
        revalidate_identities(models)
        if hash_file(run/'script.txt').sha256 != identity.sha256: raise OSError('copied script changed')
        for completed in [report['reference_replay'],*report['spans']]:
            if completed['status']=='completed':
                _verify_artifact(completed['raw'])
                _verify_artifact(completed['pcm'])
        _verify_artifact(report['listening_preview']['identity'])
        if reuse_context is not None:
            from .pipeline_import import load_pipeline_import
            load_pipeline_import(run,identity=reuse_context.import_identity)
        report.update(passed=True,status='completed',isolation_verified=True)
    except BaseException as exc:
        if isinstance(exc,(KeyboardInterrupt,SystemExit)): interruption=exc
        diagnostic=persist(lambda:logger.exception('speech',active.get('unit_id') if active else None,exc))
        exc=interruption if interruption is not None else exc
        kind = exc.kind.value if isinstance(exc,AdapterError) else type(exc).__name__
        status = 'interrupted' if interruption is not None else 'ambiguous' if isinstance(exc,AdapterError) and exc.kind==FailureKind.ambiguous else 'failed'
        error = dict(kind=kind,message=str(exc),traceback_path=str(diagnostic) if diagnostic is not None else None,
                     evidence_paths=[str(p) for p in getattr(exc,'evidence_paths',())])
        report.update(passed=False,status=status,error=error)
        def record_active():
            if active is not None and active['status']=='running':
                persisted = store.snapshot()['units']['speech'][active['unit_id']]['status']
                if persisted == 'completed':
                    active['status'] = 'completed'
                else:
                    active.update(status=status,error=error)
                    store.record_unit('speech',active['unit_id'],status,error=error)
        persist(record_active)
    finally:
        if handle is not None:
            try: manager.stop(handle)
            except BaseException as exc:
                if interruption is None:
                    if isinstance(exc,(KeyboardInterrupt,SystemExit)):interruption=exc
                    diagnostic=persist(lambda:logger.exception('speech',None,exc))
                    report.update(passed=False,status='interrupted' if interruption is not None else 'failed',
                        error=dict(kind=type(exc).__name__,message=str(exc),
                            traceback_path=str(diagnostic) if diagnostic is not None else None,evidence_paths=[]))
        report['total_speech_samples'] = sum(p.get('samples',0) for p in report['spans'] if p['kind']=='speech' and p['status']=='completed')
        report['finished_at'] = now()
        persist(lambda:atomic_report(report_path,report))
        if before is not None and not report.get('isolation_verified'):
            def failure_scan():
                try:
                    failed_after = scan_isolation(config,logger=logger)
                    logger.save_json('isolation/speech-failure-after.json',failed_after)
                except Exception as exc: logger.exception('speech',None,exc)
            persist(failure_scan)
        listening = dict(schema_version=1,listened=False,accepted=False,recorded_at=now(),user_statement=None,
                         voice=report.get('inputs',{}),models=report.get('models',{}),
                         reference_replay=report.get('reference_replay'), preview=report.get('listening_preview'),
                         audio=[{k:p[k] for k in ('unit_id','text','raw','pcm','samples') if k in p}
                                for p in report['spans'] if p['kind']=='speech' and p['status']=='completed'])
        persist(lambda:atomic_report(run/'voice-listening.json',listening))
        persist(lambda:store.record_stage('speech',report['status'],artifacts=[_artifact(report_path)] if report['passed'] else [],error=report.get('error')))
    if interruption is not None: raise interruption
    return SpeechResult(report['passed'],run,report_path,report['total_speech_samples'],False)


from .verification import verified_read


@verified_read
def load_committed_speech(run_dir):
    """Consume the current speech report, every PCM and its bound provenance."""
    from ..config import load_config
    from .timeline_checks import _run_path,_inputs,_fresh,_again,_pcm
    run=_run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot()
    config=load_config(Path(snapshot['config_snapshot']['path']))
    script,audio,identities,accepted,listening=_inputs(config,run,snapshot)
    report=read_json(run/'segments.json')
    if report.get('inputs',{}).get('tts_runtime') is not None:
        native=report.get('import_identity') is None
        runtime=_fresh(report['inputs']['tts_runtime'],**(dict(run=run,expected=run/'logs/voice-runtime-configuration.yaml') if native else {}))
        installed=_fresh(report['inputs']['tts_installed_data'],**(dict(run=run,expected=run/'logs/voice-installed-configuration.json') if native else {}))
        semantic=_fresh(report['inputs']['tts_runtime_data'],**(dict(run=run,expected=run/'logs/voice-runtime-configuration.json') if native else {}))
        serialized=_fresh(report['inputs']['tts_serialization'],**(dict(run=run,expected=run/'logs/voice-runtime-serialization.json') if native else {}))
        expected=_runtime_voice_configuration(read_json(Path(installed.path)),config.voice)
        proof=read_json(Path(serialized.path))
        if read_json(Path(semantic.path))!=expected or set(proof)!= {'configuration','yaml'} or proof['configuration']!=expected or not isinstance(proof['yaml'],str):
            raise ValueError('revised TTS service configuration differs from current voice')
        if Path(runtime.path).read_bytes()!=proof['yaml'].replace('\n',os.linesep).encode('utf-8'):
            raise ValueError('revised TTS service YAML bytes differ from bundled serialization')
        startup=_fresh(report['inputs']['tts_runtime_startup'],**(dict(run=run,expected=run/'logs/voice-runtime-startup.json') if native else {}))
        note=read_json(Path(startup.path));after=_fresh(note['after_identity'],expected=Path(runtime.path))
        if (set(note)!= {'schema_version','owned','runtime_config_path','before','after_identity','recorded_at'}
                or type(note['schema_version']) is not int or note['schema_version']!=1 or note['owned'] is not True
                or note['runtime_config_path']!=runtime.path or set(note['before'])!={'bytes','sha256','mtime_ns'}
                or (note['before']['bytes'],note['before']['sha256'])!=(runtime.bytes,runtime.sha256)
                or (after.bytes,after.sha256,after.mtime_ns)!=(runtime.bytes,runtime.sha256,runtime.mtime_ns)):
            raise ValueError('owned TTS runtime startup transition differs')
    historical_tts=None
    if report['schema_version']==1:
        # Inherited schema1 speech binds the canonical installed YAML by
        # payload. Use the already reviewed role-bound candidate walker to
        # freeze its current full identity and every other bound report leaf.
        # This does not change either original receipt or permit later drift.
        from ._candidate_evidence import capture_bound_identities,HISTORICAL_TTS_CONFIG
        bound_identities=capture_bound_identities(
            dict(segments_identity=thaw(identities['segments'])),run=run)
        identities.update({'speech_bound/'+key:value for key,value in bound_identities.items()})
        record=report.get('inputs',{}).get('tts_yaml')
        if record is not None and record.get('path')==str(HISTORICAL_TTS_CONFIG):
            historical_tts=next(value for value in bound_identities.values()
                if value.path==str(HISTORICAL_TTS_CONFIG))
    for group in ('inputs','models'):
        for name,record in report.get(group,{}).items():
            frozen=snapshot[group].get(name)
            if frozen is None:raise ValueError('speech provenance missing from manifest')
            if group=='inputs' and name=='tts_yaml' and historical_tts is not None:
                from .manifest import _identity
                from datetime import datetime
                _identity(record);_identity(frozen)
                if datetime.fromisoformat(frozen['verified_at'])>datetime.now().astimezone():
                    raise ValueError('future historical TTS manifest identity timestamp')
                if any(record[key]!=frozen[key] for key in ('path','bytes','mtime_ns','sha256')):
                    raise ValueError('historical TTS manifest/receipt identity differs')
                current=bound=historical_tts
            else:
                current=_fresh(record);bound=_fresh(frozen)
            identities[f'speech/{group}/{name}']=current
            if (bound.bytes,bound.sha256)!=(identities[f'speech/{group}/{name}'].bytes,identities[f'speech/{group}/{name}'].sha256):
                raise ValueError('speech frozen provenance mismatch')
    for item in [*report['spans'],*([report['reference_replay']] if report.get('reference_replay') else [])]:
        if item['kind']=='skip' if 'kind' in item else False:continue
        uid=item['unit_id']
        if 'raw' in item:
            raw=_fresh(item['raw'],run=run,expected=run/'audio'/uid/'raw.wav')
            registered=[a for a in snapshot['units']['speech'][uid]['artifacts'] if a['path']==raw.path]
            if len(registered)!=1 or (registered[0]['bytes'],registered[0]['sha256'])!=(raw.bytes,raw.sha256):
                raise ValueError('speech raw not bound to unit')
            identities['raw/'+uid]=raw
        identities.update(_speech_unit_evidence(config,run,item))
        if uid=='reference_replay':
            info,identity=_pcm(run,item,snapshot['units']['speech'][uid]);identities['reference_replay']=identity
    if 'listening_preview' in report:
        item=report['listening_preview'];identity=_fresh(item['identity'],run=run,expected=run/'audio/listening-preview.wav')
        total=sum(a.samples for a in audio.values())
        if type(item['samples']) is not int or item['samples']!=total or item['sample_rate']!=48000 or item['preview_only'] is not True:
            raise ValueError('listening preview metadata mismatch')
        with wave.open(identity.path,'rb') as preview:
            if (preview.getframerate(),preview.getnchannels(),preview.getsampwidth(),preview.getcomptype(),preview.getnframes())!=(48000,1,2,'NONE',total):
                raise ValueError('listening preview format mismatch')
            for span in report['spans']:
                if span['kind']=='skip':continue
                with wave.open(span['pcm']['path'],'rb') as pcm:
                    remaining=span['samples']
                    while remaining:
                        count=min(65536,remaining);expected=pcm.readframes(count)
                        if len(expected)!=count*2 or preview.readframes(count)!=expected:raise ValueError('listening preview differs from current PCM')
                        remaining-=count
            if preview.readframes(1):raise ValueError('extra preview audio')
        identities['preview']=identity
    if report['schema_version']==1 and 'import_provenance_identity' in report:
        from .storyboard_checks import _verify_import
        _verify_import(run,report)
        imported=_fresh(report['import_provenance_identity'],run=run,expected=run/'logs/storyboard/upstream-import.json')
        receipt=read_json(Path(imported.path));identities['legacy_import']=imported
        origin=load_committed_speech(Path(receipt['parent_run']))
        identities.update({'legacy_origin/'+k:v for k,v in origin['input_identities'].items()})
    _again(identities)
    if store.snapshot()['stages']['speech']!=snapshot['stages']['speech']:raise OSError('speech changed during consumption')
    return dict(script=script,spans=script.spans,audio=audio,input_identities=identities,accepted=accepted,
        listening_identity=listening,report=report)


def _speech_unit_evidence(config,run,item):
    """Retain original HTTP and conversion leaves without replaying a command."""
    from .timeline_checks import _local,_fresh,_again
    identities={};uid=item['unit_id']
    body_path=item.get('http_evidence_path')
    if body_path is not None:
        path=Path(body_path)
        if path.is_relative_to(run):
            body=hash_file(_local(run,path));identities['http/'+uid]=body
            if (body.bytes,body.sha256)!=(item['raw']['bytes'],item['raw']['sha256']):raise ValueError('saved TTS HTTP body differs from raw audio')
            intent_path=_local(run,run/'logs/tts'/f'{uid}.intent.json')
            intent=read_json(intent_path);identities['tts_intent/'+uid]=hash_file(intent_path)
            if intent.get('unit_id')!=uid or intent.get('text')!=item['text'] or intent.get('automatic_retry') is not False:
                raise ValueError('saved TTS original request text differs')
            if intent.get('payload')!=TtsClient(None,config.voice).payload(item['text']):raise ValueError('saved TTS request parameters differ')
            response=path.with_suffix('.response.json');request=path.with_suffix('.request.json')
            if response.exists() or request.exists():
                data=read_json(response);payload=read_json(request)
                if (type(data.get('status')) is not int or not 200<=data['status']<300 or data.get('truncated') is not False
                        or data.get('error') is not None or data.get('bytes')!=body.bytes or data.get('unit_id')!=uid):
                    raise ValueError('saved TTS HTTP response is not complete successful audio')
                if payload.get('method')!='POST' or payload.get('json_body')!=intent['payload']:
                    raise ValueError('saved actual TTS HTTP request differs from intent')
                identities['http_response/'+uid]=hash_file(response);identities['http_request/'+uid]=hash_file(request)
    validation=item.get('audio_evidence_path')
    if validation is not None:
        path=Path(validation)
        if path.is_relative_to(run) and path.exists():
            data=read_json(_local(run,path));identities['audio_validation/'+uid]=hash_file(path)
            raw=_fresh(data['raw'],run=run,expected=Path(item['raw']['path']))
            if raw.sha256!=item['raw']['sha256']:raise ValueError('conversion raw audio differs')
            expected=dict(path=item['pcm']['path'],sha256=item['pcm']['sha256'],bytes=item['pcm']['bytes'],
                sample_rate=item['sample_rate'],channels=item['channels'],sample_width=item['sample_width'],samples=item['samples'])
            if data['pcm']!=expected:raise ValueError('conversion actual PCM/sample receipt differs')
            for i,command in enumerate(data['commands']):
                if command['returncode']!=0 or command['timed_out'] is not False:raise ValueError('speech conversion command failed')
                for key in ('stdout_path','stderr_path'):
                    identities[f'audio_command/{uid}/{i}/{key}']=hash_file(_local(run,Path(command[key])))
    _again(identities);return identities


def speech_import_inventory(parent_run_dir, run_dir, *, partial=False):
    """Explicit copy requests and origin rows for a completely consumed voice."""
    from .pipeline_import import content_signature
    from .timeline_checks import _run_path
    parent,run=_run_path(parent_run_dir),_run_path(run_dir)
    loaded=_load_partial_speech(parent) if partial else load_committed_speech(parent)
    report=loaded['report'];snapshot=ManifestStore.open(parent).snapshot()
    source_id=hash_file(parent/'segments.json')
    sources={identity.path:thaw(identity) for identity in loaded['input_identities'].values()}
    copies=[dict(original_identity=thaw(hash_file(parent/'script.txt')),copy_path=run/'script.txt',role='script_copy',stage='speech',unit_id=None)]
    units=[]
    for item in [report.get('reference_replay'),*report['spans']]:
        if item is None or item.get('kind')=='skip' or item['status']!='completed':continue
        uid=item['unit_id'];old=report.get('reused_units',{}).get(uid)
        units.append(dict(id=uid,source_record=snapshot['units']['speech'][uid],imported_record=dict(stage='speech',
            origin_run_id=old['origin_run_id'] if old else parent.name,
            source_report_identity=old['source_report_identity'] if old else thaw(source_id),
            source_unit_id=old['source_unit_id'] if old else uid),
            signature=old['signature'] if old else content_signature(item),origin='reused_verified'))
        for key,name in (('raw','raw.wav'),('pcm','pcm-48000.wav')):
            if key not in item:continue
            original=hash_file(Path(item[key]['path']))
            copies.append(dict(original_identity=thaw(original),copy_path=run/'audio'/uid/name,role=key,stage='speech',unit_id=uid))
    if report.get('listening_preview'):
        original=hash_file(Path(report['listening_preview']['identity']['path']))
        copies.append(dict(original_identity=thaw(original),copy_path=run/'audio/listening-preview.wav',role='preview',stage='speech',unit_id=None))
    stage=dict(id='speech',source_record=snapshot['stages']['speech'],imported_record=dict(source_report_identity=thaw(source_id)),
        signature=content_signature(report),origin='reused_verified')
    return dict(source_identities=sources,copies=copies,stage=stage,units=units)


def serialize_imported_speech(config, run_dir, *, source_report, import_identity, reused_units, copies):
    """Rebind only documented media fields; production HTTP/argv keep origin."""
    from .timeline_checks import _run_path
    from .pipeline_import import fresh
    run=_run_path(run_dir);result=thaw(source_report)
    if not reused_units:
        from .pipeline_import import load_pipeline_import
        receipt=load_pipeline_import(run,identity=import_identity)
        rows=[r for r in receipt['stages'] if r['id']=='speech']
        if source_report.get('status')=='completed' or len(rows)!=1 or rows[0]['source_record']['status']=='completed':
            raise ValueError('speech import requires verified originals or proven incomplete attempt')
    mapping={r['original_identity']['path']:r['copy_identity'] for r in copies if r['stage']=='speech'}
    def copied(record):
        if record['path'] not in mapping:raise ValueError('speech media missing independent copy')
        fresh(mapping[record['path']]);actual=thaw(mapping[record['path']])
        if 'category' in record:actual.pop('mtime_ns');actual['category']='run'
        return actual
    result.update(schema_version=2,run_dir=str(run),import_identity=thaw(import_identity),reused_units=thaw(reused_units))
    result['script_copy']=copied(result['script_copy'])
    for item in [result.get('reference_replay'),*result['spans']]:
        if item is None or item.get('kind')=='skip':continue
        if item['unit_id'] in reused_units:
            for key in ('raw','pcm'):
                if key in item:item[key]=copied(item[key])
    if result.get('listening_preview'):result['listening_preview']['identity']=copied(result['listening_preview']['identity'])
    if source_report['schema_version']==1:
        source_identity=(next(iter(reused_units.values()))['source_report_identity'] if reused_units else rows[0]['imported_record']['source_report_identity'])
        source_run=Path(fresh(source_identity).path).parent
        original_snapshot=ManifestStore.open(source_run).snapshot()['config_snapshot']
        result['segmentation_identity']=thaw(source_identity)
        result['execution_policy']=dict(gpu_management='sampled' if 'resources' in source_report else 'disabled',
            total_timeout_seconds=None,media_command_timeout_seconds=300,
            tts_request_timeout_seconds=original_snapshot['resolved']['timeouts']['tts_request'])
    snapshot=ManifestStore.open(run).snapshot()
    for key,path in (('config',config.config_file),('voice',config.voice.config_file)):
        record=snapshot['inputs'].get(key,source_report['inputs'].get(key))
        if record is None or Path(record['path'])!=path:raise ValueError('speech import current input missing')
        fresh(record);result['inputs'][key]=thaw(record)
    return result


def verify_speech_import(run, report, script, spans):
    """Fresh origin replay plus exact explicit serialization for schema2 imports."""
    from .pipeline_import import load_pipeline_import,import_source_identities,same_identity,fresh
    from ..config import load_config
    if not isinstance(report.get('reused_units'),dict):raise ValueError('speech import needs explicit original unit map')
    snapshot=ManifestStore.open(run).snapshot();registered=snapshot['workflows'].get('pipeline_import')
    if registered is None or not same_identity(registered,report['import_identity']):raise ValueError('speech import is not registered')
    receipt=load_pipeline_import(run,identity=report['import_identity'])
    rows=[r for r in receipt['stages'] if r['id']=='speech']
    if len(rows)!=1:raise ValueError('speech import source stage missing')
    parent=run.parent/receipt['parent_run_id'];source_id=rows[0]['imported_record']['source_report_identity'];fresh(source_id)
    complete=rows[0]['source_record']['status']=='completed'
    origin=load_committed_speech(parent) if complete else _load_partial_speech(parent)
    if origin['script'].spans!=tuple(spans) or (origin['script'].text,origin['script'].has_bom)!=(script.text,script.has_bom):
        raise ValueError('speech imported segmentation differs from verified origin')
    if not report['reused_units'] and (complete or not origin.get('known_failed_units')):
        raise ValueError('empty speech reuse requires proven original failed response')
    if not same_identity(hash_file(parent/'segments.json'),source_id):raise ValueError('speech source report differs')
    config=load_config(Path(snapshot['config_snapshot']['path']))
    from ._pipeline_voice_admission import verify_reused_voice
    current_voice_ids={}
    verify_reused_voice(config,parent,current_voice_ids)
    expected=serialize_imported_speech(config,run,source_report=origin['report'],import_identity=report['import_identity'],
        reused_units=report['reused_units'],copies=receipt['copies'])
    if complete:
        if report!=expected:raise ValueError('speech import differs from fresh origin serialization')
    else:
        from .pipeline_import import content_signature
        for key in ('source','script_copy','decoded_text','has_bom','coverage_verified','segmentation_identity','limits'):
            if content_signature(report.get(key))!=content_signature(expected.get(key)):raise ValueError('partial speech origin field differs')
        origin_items={i['unit_id']:i for i in [expected['reference_replay'],*expected['spans']] if i.get('kind')!='skip'}
        current_items={i['unit_id']:i for i in [report['reference_replay'],*report['spans']] if i.get('kind')!='skip'}
        for uid in report['reused_units']:
            if content_signature(current_items[uid])!=content_signature(origin_items[uid]):raise ValueError('partial reused audio differs from original')
    unit_rows={r['id']:r for r in receipt['units'] if r['imported_record'].get('stage')=='speech'}
    expected_ids={item['unit_id'] for item in [origin['report'].get('reference_replay'),*origin['report']['spans']]
        if item is not None and item.get('kind')!='skip' and item['status']=='completed'}
    if set(report['reused_units'])!=expected_ids or set(unit_rows)!=expected_ids:raise ValueError('speech imported unit coverage mismatch')
    for uid,reused in report['reused_units'].items():
        if set(reused)!=set('origin_run_id source_report_identity source_unit_id signature import_identity'.split()):raise ValueError('speech reuse fields mismatch')
        row=unit_rows[uid];source=row['imported_record']
        for key in ('origin_run_id','source_report_identity','source_unit_id'):
            if thaw(reused[key])!=thaw(source[key]):raise ValueError('speech unit origin mismatch')
        if reused['signature']!=row['signature'] or not same_identity(reused['import_identity'],report['import_identity']):raise ValueError('speech reuse signature mismatch')
        current=snapshot['units']['speech'].get(uid)
        if current is None or current['status']!='completed' or current['submission'] is not None:raise ValueError('speech reuse must have no child submission')
    return dict(current_voice_ids,**{'import/'+key:identity for key,identity in import_source_identities(run).items()})


def _load_partial_speech(run_dir):
    """Only complete, verified prefixes followed by provably unsent units."""
    from dataclasses import fields
    from ..planning.segments import TextSpan,segment_text
    from .timeline_checks import _run_path,_fresh,_pcm,_again,_local
    from .pipeline_reviews import load_unit_review
    run=_run_path(run_dir);snapshot=ManifestStore.open(run).snapshot();report=read_json(run/'segments.json')
    if snapshot['stages']['speech']['status'] not in {'interrupted','failed','running'}:
        raise ValueError('partial speech requires incomplete original stage')
    if report.get('run_dir')!=str(run) or report.get('coverage_verified') is not True:raise ValueError('partial speech source unverified')
    identities={'segments':hash_file(run/'segments.json'),'source':_fresh(report['source']),
        'script_copy':_fresh(report['script_copy'],run=run,expected=run/'script.txt')}
    parsed=SegmentedScript.read(run/'script.txt')
    if (parsed.text,parsed.has_bom)!=(report['decoded_text'],report['has_bom']):raise ValueError('partial speech original text differs')
    spans=tuple(TextSpan(**{f.name:item[f.name] for f in fields(TextSpan)}) for item in report['spans'])
    validate_segments(parsed.text,spans)
    if report['schema_version']==1:
        if spans!=segment_text(parsed.text):raise ValueError('partial canonical speech differs')
    elif report['schema_version']==2 and report.get('import_identity') is None:
        reviewed=load_unit_review(Path(report['segmentation_identity']['path']),script_path=Path(report['source']['path']),run_dir=run)
        if reviewed.script.spans!=spans:raise ValueError('partial reviewed spans differ')
        identities['segmentation']=reviewed.identity
    elif report['schema_version']==2 and report.get('import_identity') is not None:
        identities.update(verify_speech_import(run,report,parsed,spans))
    else:raise ValueError('partial speech schema unsupported')
    for group in ('inputs','models'):
        for key,record in report.get(group,{}).items():
            identity=_fresh(record);identities[group+'/'+key]=identity
            frozen=snapshot[group].get(key)
            if frozen is None or (frozen['bytes'],frozen['sha256'])!=(identity.bytes,identity.sha256):raise ValueError('partial frozen source differs')
    from .pipeline_inventory import classify_tts_intents
    unknown,failed=classify_tts_intents(snapshot,run_dir=run)
    if unknown:raise ValueError('unknown TTS intent cannot be submitted again')
    if len(failed)>1:raise ValueError('sequential speech cannot contain multiple failed sends')
    for uid,proof in failed.items():
        for path,record in proof['evidence_identities'].items():identities['failure/'+path]=_fresh(record)
    items=[report.get('reference_replay'),*[item for item in report['spans'] if item['kind']=='speech']]
    if items[0] is None:raise ValueError('partial reference replay missing')
    completed=[];tail=False
    for item in items:
        uid=item.get('unit_id')
        if item['status']=='completed':
            if tail:raise ValueError('partial speech is not a completed prefix')
            unit=snapshot['units']['speech'].get(uid)
            if unit is None:raise ValueError('partial completed unit missing')
            info,identity=_pcm(run,item,unit);identities['pcm/'+uid]=identity
            raw=_fresh(item['raw'],run=run,expected=run/'audio'/uid/'raw.wav');identities['raw/'+uid]=raw
            if not any(a['path']==raw.path and a['sha256']==raw.sha256 and a['bytes']==raw.bytes for a in unit['artifacts']):raise ValueError('partial raw unregistered')
            completed.append(uid)
            from ..config import load_config
            config=load_config(Path(snapshot['config_snapshot']['path']))
            if report.get('import_identity') is not None and uid not in report['reused_units']:
                # A newly completed suffix needs this run's actual send/conversion
                # proof. Inherited rows are proved by recursive origin replay.
                body=item.get('http_evidence_path');validation=item.get('audio_evidence_path')
                if body is None or validation is None:
                    raise ValueError('mixed speech native unit requires HTTP and conversion evidence')
                body=_local(run,Path(body))
                if not body.is_relative_to(run/'logs/http'):
                    raise ValueError('mixed speech native HTTP evidence is outside current transport logs')
                for suffix in ('.request.json','.response.json'):
                    path=body.with_suffix(suffix)
                    identities['native_http/'+uid+suffix]=hash_file(_local(run,path))
                path=run/'logs/audio'/f'{uid}.validation.json'
                if _local(run,Path(validation))!=path:
                    raise ValueError('mixed speech native conversion evidence differs from current unit')
                identities['native_validation/'+uid]=hash_file(path)
            identities.update(_speech_unit_evidence(config,run,item))
        else:
            tail=True
            if item['status']=='failed' and uid in failed:
                if (run/'audio'/uid/'pcm-48000.wav').exists():raise ValueError('failed TTS unit has orphan PCM')
                if item.get('raw') is not None:
                    raw=_fresh(item['raw'],run=run,expected=run/'audio'/uid/'raw.wav')
                    body=_fresh(failed[uid]['body_identity'])
                    if (raw.bytes,raw.sha256)!=(body.bytes,body.sha256):raise ValueError('failed raw WAV differs from complete original HTTP body')
                    identities['failed_raw/'+uid]=raw
                continue
            if item['status']!='pending' or uid in snapshot['units']['speech']:
                raise ValueError('unknown/failed TTS intent cannot be submitted again')
            if (run/'audio'/uid).exists() or (run/'logs/tts'/f'{uid}.intent.json').exists() or any(
                    event.get('unit_id')==uid and event.get('action')=='tts_intent' for event in snapshot['events']):
                raise ValueError('orphan/unknown TTS submission evidence')
    if not tail or not completed and not failed:raise ValueError('partial speech needs verified prefix or proven failed send')
    if set(snapshot['units']['speech'])!=set(completed)|set(failed):raise ValueError('partial speech has unaccounted units')
    _again(identities)
    return dict(report=report,input_identities=identities,script=SegmentedScript(parsed.text,parsed.has_bom,spans),accepted=False,known_failed_units=failed)


def resume_speech(config, *, run_dir, reuse_context, store):
    """Continue only a consumer-sealed imported prefix in an independent run."""
    from .pipeline_import import verify_reuse_context,load_pipeline_import,fresh
    from .timeline_checks import _run_path,_pcm
    run=_run_path(run_dir)
    if not isinstance(store,ManifestStore) or store.run_dir!=run:raise ValueError('speech recovery store mismatch')
    snapshot=store.snapshot();report=read_json(run/'segments.json')
    if snapshot['stages']['preflight']['status']!='completed' or snapshot['stages']['speech']['status']!='pending':
        raise ValueError('speech recovery needs independent pending stage')
    unit_ids=('reference_replay',)+tuple(item['unit_id'] for item in report['spans'] if item['kind']=='speech')
    identities={k:fresh(v) for k,v in snapshot['inputs'].items()}
    verified=verify_reuse_context(run,reuse_context,stage='speech',unit_ids=unit_ids,current_input_identities=identities)
    receipt=load_pipeline_import(run,identity=verified.import_identity)
    parent=run.parent/receipt['parent_run_id'];origin=_load_partial_speech(parent)
    rows=[r for r in receipt['stages'] if r['id']=='speech']
    retry=rows[0]['imported_record'].get('retry_failed_units',[]) if len(rows)==1 else []
    failed=origin.get('known_failed_units',{})
    if len(retry)!=len(set(retry)) or set(retry)!=set(failed):raise ValueError('failed TTS retry requires exact explicit author targets')
    expected=serialize_imported_speech(config,run,source_report=origin['report'],import_identity=verified.import_identity,
        reused_units=verified.verified_units,copies=receipt['copies'])
    if report!=expected:raise ValueError('partial imported speech differs from original proven prefix')
    for item in [report['reference_replay'],*[s for s in report['spans'] if s['kind']=='speech']]:
        uid=item['unit_id']
        if uid in verified.verified_units:
            _pcm(run,item,snapshot['units']['speech'][uid]);_verify_artifact(item['raw'])
        elif (item['status']!='pending' and not (item['status']=='failed' and uid in retry)) or uid in snapshot['units']['speech'] or (run/'audio'/uid).exists():
            raise ValueError('speech suffix must remain unsubmitted')
    review_path=run/'logs/pipeline/unit-review.json'
    if review_path.exists():
        from .pipeline_reviews import load_unit_review
        reviewed=load_unit_review(review_path,script_path=Path(report['source']['path']),run_dir=run)
        if reviewed.script.spans!=origin['script'].spans:raise ValueError('speech recovery may not change segmentation')
    for item in [report['reference_replay'],*report['spans']]:
        if item.get('unit_id') in retry:
            for key in ('raw','pcm','http_evidence_path','audio_evidence_path','samples','sample_rate','channels','sample_width','duration','error'):
                item.pop(key,None)
            item['status']='pending'
    if retry:atomic_report(run/'segments.json',report)
    return _synthesize_script(config,Path(report['source']['path']),run_dir=run,store=store,reuse_context=verified)
