from dataclasses import replace
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from test_production_inputs import production_config


def test_batch_intent_is_durable_and_callback_runs_before_actual_post(runtime_run, monkeypatch):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.ollama import OllamaPlanner
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import hash_file, thaw
    import video_ai.runtime.logging as logging
    run, _, _ = runtime_run
    source = run/'source.txt'; source.write_text('原文', encoding='utf-8')
    context = dict(client_id='client-1', script_identity=thaw(hash_file(source)),
                   candidate_ranges=[dict(unit_id='speech_0001',text_start=0,text_end=2)])
    schema = dict(type='object',properties=dict(x=dict(type='integer')),required=['x'],additionalProperties=False)
    requests = []; ready = []; synced = []
    original_fsync = logging.os.fsync
    monkeypatch.setattr(logging.os,'fsync',lambda fd:(synced.append(fd),original_fsync(fd))[-1])
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert ready
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            data=json.dumps(dict(model='qwen3:8b',done=True,response='{"x":3}')).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    def on_intent(path, body):
        intent=json.loads(path.read_bytes())
        assert set(intent)=={'request_id','body','schema','prompt','context'}
        assert intent['context']==context and intent['prompt']=='原文' and intent['schema']==schema
        assert intent['body']==body and synced and requests==[]
        ready.append(path)
        # A callback owns state bookkeeping, and cannot change the exact body
        # already persisted as the one authorized submission.
        body['prompt']='callback-local change'
    try:
        planner=OllamaPlanner(HttpClient(f'http://127.0.0.1:{server.server_port}',2,RunLogger(run,production=True)))
        assert planner.generate('原文',schema=schema,request_id='units_batch_0001_initial',
                                intent_context=context,on_intent=on_intent)=={'x':3}
    finally:
        server.shutdown();server.server_close();thread.join(2)
    assert len(requests)==1 and ready[0].is_relative_to(run/'logs/production')
    assert requests[0]['prompt']=='原文'


def test_batch_intent_callback_failure_prevents_post(runtime_run):
    from test_ollama import client_for
    from video_ai.adapters.common import AdapterError
    p,t=client_for(runtime_run,dict(model='qwen3:8b',done=True,response='{}'))
    context=dict(client_id='c',script_identity={},candidate_ranges=[])
    def reject(*args): raise OSError('checkpoint refused')
    with pytest.raises(AdapterError):
        p.generate('prompt',schema={},request_id='units_batch_0001_initial',intent_context=context,on_intent=reject)
    assert len(t.calls)==0


@pytest.mark.parametrize('request_id',['../initial','units_batch_1_initial','units_batch_00001_initial','units_batch_0001_again','units_batch_0001_initial/x',True])
def test_batch_ids_remain_constrained(runtime_run,request_id):
    from test_ollama import client_for
    p,t=client_for(runtime_run,{})
    with pytest.raises(ValueError): p.generate('prompt',schema={},request_id=request_id)
    assert t.calls==[]


def test_offline_completed_parser_restores_and_checks_model():
    from video_ai.adapters.ollama import parse_completed_response, OllamaFormatError
    from video_ai.adapters.common import AdapterError
    schema={'type':'object','properties':{'x':{'type':'integer'}},'required':['x'],'additionalProperties':False}
    outer=dict(model='qwen3:8b',done=True,response='{"x":1}')
    assert parse_completed_response(outer,schema=schema,request_id='units_batch_0001_initial',evidence_paths=[])=={'x':1}
    for inner in ('{"x":true}','{"extra":1}','[]','{bad','{"x":1,"x":2}'):
        with pytest.raises(OllamaFormatError):
            parse_completed_response(dict(outer,response=inner),schema=schema,request_id='initial',evidence_paths=[])
    for bad in (dict(outer,model='other'),dict(outer,done=1),dict(outer,response='')):
        with pytest.raises(AdapterError) as exc:
            parse_completed_response(bad,schema=schema,request_id='initial',evidence_paths=[])
        assert exc.value.kind.value=='ambiguous'


def test_production_logger_root_and_durable_evidence(runtime_run,monkeypatch):
    import video_ai.runtime.logging as module
    run,_,_=runtime_run; synced=[]
    monkeypatch.setattr(module.os,'fsync',lambda fd:synced.append(fd))
    logger=module.RunLogger(run,production=True)
    p=logger.save_bytes('response.bin',b'complete');logger.event('units',None,'completed',{})
    assert p==run/'logs/production/response.bin' and len(synced)==2
    assert module.RunLogger(run).root==run/'logs'
    with pytest.raises(FileExistsError): logger.save_bytes('response.bin',b'changed')


def test_production_specs_use_frozen_custom_urls_and_runtime_yaml(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import create_manifest, ManifestStore, thaw
    from video_ai.runtime.production_inputs import FrozenInputs
    from video_ai.planning.segments import SegmentedScript, segment_text
    from video_ai.runtime.service_specs import build_service_specs
    from video_ai.runtime.services import service_environment
    run,config,paths=runtime_run
    config=replace(config,services=dict(ollama='http://127.0.0.1:12435',tts='http://127.0.0.1:12880',comfyui='http://127.0.0.1:12888'))
    store=create_manifest(run,config,inputs={},models={},workflows={})
    store=ManifestStore.open(run,verify_integrity=False)
    frozen=FrozenInputs(config,SegmentedScript('text',False,segment_text('text')),dict(config_snapshot=store.snapshot()['config_snapshot']))
    runtime=run/'logs/production/services/invocation/tts-runtime.yaml';runtime.parent.mkdir(parents=True);runtime.write_text('custom: {}')
    monkeypatch.setattr(ManifestStore,'open',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('must use passed store')))
    specs=build_service_specs(config,run,production=True,frozen=frozen,store=store,tts_yaml_path=runtime)
    assert set(specs)=={'ollama','tts','comfyui'}
    assert specs['comfyui'].args[specs['comfyui'].args.index('--port')+1]=='12888'
    assert specs['comfyui'].args[specs['comfyui'].args.index('--database-url')+1]=='sqlite:///'+(run/'comfy/user/comfyui.db').as_posix()
    assert all(str(run/'comfy'/name) in specs['comfyui'].args for name in ('input','output','temp','user'))
    assert specs['tts'].args[specs['tts'].args.index('-c')+1]==str(runtime)
    assert service_environment(paths,specs['ollama'])['OLLAMA_HOST']=='127.0.0.1:12435'
    assert specs['tts'].url==config.services['tts']
    with pytest.raises(ValueError): service_environment(paths,replace(specs['ollama'],url='http://127.0.0.1:12436'))
    with pytest.raises(ValueError): service_environment(paths,replace(specs['ollama'],env_overrides={'OLLAMA_HOST':'127.0.0.1:11435'}))
    with pytest.raises(ValueError):
        build_service_specs(config,run,production=True,frozen=frozen,store=store,tts_yaml_path=config.project_root/'config/tts-api.yaml')


def test_production_specs_accept_effective_run_local_inputs(production_config,runtime_run):
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.manifest import create_manifest
    from video_ai.runtime.service_specs import build_service_specs
    run,_,_=runtime_run
    frozen=freeze_inputs(production_config,run,text='湖水。')
    assert frozen.config.media.font_file!=production_config.media.font_file
    store=create_manifest(run,frozen.config,inputs={},models={},workflows={},verify_integrity=False)
    specs=build_service_specs(frozen.config,run,production=True,frozen=frozen,store=store)
    assert specs['ollama'].url==frozen.options['config_snapshot']['resolved']['services']['ollama']
    with pytest.raises(ValueError):
        build_service_specs(production_config,run,production=True,frozen=frozen,store=store)


def test_production_pcm_retains_silence_and_uses_stamp_without_hash(runtime_run,monkeypatch):
    import wave
    from test_audio import media_config
    import video_ai.media.audio as audio
    from video_ai.runtime.logging import RunLogger
    run,config,paths=media_config(runtime_run)
    raw=run/'raw.wav';target=run/'pcm.wav'
    frames=b'\x12\x03'*2400+b'\0\0'*4800+b'\x12\x03'*2400
    with wave.open(str(raw),'wb') as f:
        f.setparams((1,2,48000,0,'NONE',''));f.writeframes(frames)
    before=raw.read_bytes()
    monkeypatch.setattr(audio,'hash_file',lambda *a:(_ for _ in ()).throw(AssertionError('no production SHA')))
    info=audio.standardize_production_wav(raw,target,config=config,paths=paths,logger=RunLogger(run,production=True),unit_id='speech_0001',limits=audio.SpeechLimits())
    assert (info.sample_rate,info.channels,info.sample_width,info.samples)==(48000,1,2,9600)
    assert set(info.as_dict())=={'stamp','sample_rate','channels','sample_width','samples'}
    info.stamp.verify();assert raw.read_bytes()==before
    with wave.open(str(target),'rb') as f: assert f.readframes(9600)==frames


@pytest.mark.parametrize('bad',['silent','truncated','short','long'])
def test_production_pcm_refuses_bad_audio(runtime_run,bad):
    import wave
    from test_audio import media_config
    from video_ai.media.audio import standardize_production_wav,SpeechLimits
    from video_ai.runtime.logging import RunLogger
    run,config,paths=media_config(runtime_run)
    raw=run/'raw.wav';target=run/'pcm.wav'
    frames=480 if bad=='short' else 4800
    with wave.open(str(raw),'wb') as f:
        f.setparams((1,2,48000,0,'NONE',''));f.writeframes((b'\0\0' if bad=='silent' else b'\x12\x03')*frames)
    if bad=='truncated': raw.write_bytes(raw.read_bytes()[:-20])
    with pytest.raises((ValueError,RuntimeError,OSError)):
        standardize_production_wav(raw,target,config=config,paths=paths,logger=RunLogger(run,production=True),unit_id='speech_0001',limits=SpeechLimits(max_seconds=.08 if bad=='long' else 120))
