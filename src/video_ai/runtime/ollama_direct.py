"""Local Ollama-compatible API using the installed llama-server directly.

No model download, response byte cap, SSE scanner, or inference deadline.
The compatibility version is explicit; this process never impersonates Ollama.
"""
import argparse
import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from urllib.request import Request,build_opener,ProxyHandler
from urllib.parse import urlsplit


def backend_json(url,payload=None,*,timeout=None):
    raw=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8')
    request=Request(url,data=raw,headers={'Content-Type':'application/json'})
    with build_opener(ProxyHandler({})).open(request,timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def model_blob(root,model):
    if model not in ('qwen3:8b','qwen3:14b'):raise ValueError('unsupported frozen planner model')
    name,tag=model.split(':');root=Path(root).resolve()
    path=root/'manifests/registry.ollama.ai/library'/name/tag
    manifest=json.loads(path.read_text(encoding='utf-8'))
    layers=[v for v in manifest['layers'] if v['mediaType']=='application/vnd.ollama.image.model']
    if len(layers)!=1 or not re.fullmatch(r'sha256:[a-f0-9]{64}',layers[0]['digest']):
        raise ValueError('invalid existing model layer')
    blob=(root/'blobs'/layers[0]['digest'].replace(':','-')).resolve()
    if not blob.is_relative_to(root) or not blob.is_file():raise ValueError('model blob missing or outside model root')
    return blob


def backend_environment(executable,*,cpu=False):
    env=dict(os.environ);directory=Path(executable).parent
    if not cpu:
        library=next((directory/version/'ggml-cuda.dll' for version in ('cuda_v13','cuda_v12')
            if (directory/version/'ggml-cuda.dll').is_file()),None)
        if library is None:raise ValueError('installed CUDA backend library is missing')
        env['GGML_BACKEND_PATH']=str(library)
        env['PATH']=str(library.parent)+os.pathsep+str(directory)+os.pathsep+env.get('PATH','')
    return env


def chat_prompt(body):
    text=body['prompt']
    if not isinstance(text,str):raise ValueError('complete prompt required')
    tail='<think>\n' if body.get('think') else '<think>\n\n</think>\n\n'
    return '<|im_start|>user\n'+text+'<|im_end|>\n<|im_start|>assistant\n'+tail


def completion_request(body,tokens):
    return dict(prompt=tokens,n_keep=len(tokens),n_predict=-1,stream=False,
        temperature=body.get('options',{}).get('temperature',0),json_schema=body['format'],
        cache_prompt=False,stop=['<|im_end|>','<|im_start|>'])


def completion_response(model,value,*,think=False,expected_prompt_tokens=None):
    if not isinstance(value,dict) or value.get('error') or not isinstance(value.get('content'),str):
        raise ValueError('backend did not return a completed text result')
    if value.get('stop') is not True:raise ValueError('backend completion is incomplete')
    evaluated=value.get('tokens_evaluated',value.get('timings',{}).get('prompt_n'))
    if expected_prompt_tokens is not None and (type(evaluated) is not int or evaluated<expected_prompt_tokens):
        raise ValueError('backend did not evaluate the complete prompt')
    content=value['content'];thinking=None
    if think and '</think>' in content:
        try:json.loads(content)
        except ValueError:thinking,content=content.split('</think>',1)
    result=dict(model=model,done=True,done_reason='length' if value.get('stopped_limit') or
        value.get('stop_type')=='limit' else 'stop',response=content)
    if thinking is not None:result['thinking']=thinking
    for original,target in (('tokens_predicted','eval_count'),('tokens_evaluated','prompt_eval_count')):
        if type(value.get(original)) is int:result[target]=value[original]
    return result


class WindowsJob:
    """Closing the bridge also closes its owned backend, including on terminate."""
    def __init__(self,process):
        self.handle=None
        if os.name!='nt':return
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',wintypes.DWORD),
                ('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',wintypes.DWORD),
                ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):_fields_=[(f'count{i}',ctypes.c_ulonglong) for i in range(6)]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO)]+[(name,ctypes.c_size_t) for name in ('process_memory','job_memory','peak_process','peak_job')]
        api=ctypes.WinDLL('kernel32',use_last_error=True);self.api=api
        api.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];api.CreateJobObjectW.restype=wintypes.HANDLE
        api.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        api.SetInformationJobObject.restype=wintypes.BOOL
        api.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];api.AssignProcessToJobObject.restype=wintypes.BOOL
        api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
        handle=api.CreateJobObjectW(None,None)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        info=Extended();info.basic.flags=0x2000
        if not api.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not api.AssignProcessToJobObject(handle,process._handle):
            error=ctypes.get_last_error();api.CloseHandle(handle);raise ctypes.WinError(error)
        self.handle=handle

    def close(self):
        if self.handle is not None:self.api.CloseHandle(self.handle);self.handle=None


class DirectBackend:
    def __init__(self,executable,root):
        self.executable=Path(executable);self.root=Path(root);self.lock=threading.Lock()
        self.process=None;self.job=None;self.url=None;self.current=None

    def stop(self):
        process=self.process;self.process=None
        try:
            if process is not None:
                if process.poll() is None:process.terminate()
                process.wait()
        finally:
            if self.job is not None:self.job.close();self.job=None
            self.current=None

    def start(self,model,context,cpu):
        self.stop()
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}'
        args=[str(self.executable),'--model',str(model_blob(self.root,model)),
            '--host','127.0.0.1','--port',str(port),'--no-webui','--offline','--ctx-size',str(context),
            '-np','1','--gpu-layers','0' if cpu else 'auto','--flash-attn','auto',
            '--context-shift','--no-jinja','--chat-template','chatml','--log-verbosity','4']
        if context:args+=['--fit-ctx',str(context),'--override-kv',f'qwen3.context_length=int:{context}']
        print('video-ai direct backend:',json.dumps(args),flush=True)
        self.process=subprocess.Popen(args,cwd=self.executable.parent,stdin=subprocess.DEVNULL,
            env=backend_environment(self.executable,cpu=cpu),
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            self.job=WindowsJob(self.process)
            while self.process.poll() is None:
                try:
                    if backend_json(self.url+'/health',timeout=1).get('status')=='ok':
                        self.current=model;return
                except (OSError,ValueError):pass
                time.sleep(0.1)
            raise RuntimeError(f'owned llama-server exited before readiness: {self.process.returncode}')
        except BaseException:self.stop();raise

    def generate(self,body):
        model=body['model'];cpu=body.get('options',{}).get('num_gpu')==0
        with self.lock:
            try:
                self.start(model,0,cpu)
                tokens=backend_json(self.url+'/tokenize',dict(content=chat_prompt(body),add_special=True,parse_special=True))['tokens']
                if not isinstance(tokens,list) or not tokens or not all(type(t) is int for t in tokens):
                    raise ValueError('backend tokenizer returned invalid complete prompt')
                context=backend_json(self.url+'/slots')[0]['n_ctx']
                # Allocation grows with actual tokens, never a conservative byte
                # estimate or a fixed source cap. Context shift keeps output unlimited.
                if context<4*len(tokens):
                    self.start(model,((4*len(tokens)+255)//256)*256,cpu)
                    context=backend_json(self.url+'/slots')[0]['n_ctx']
                if context<=len(tokens):raise RuntimeError('allocated backend context cannot contain the full prompt')
                print(json.dumps(dict(direct_prompt_tokens=len(tokens),allocated_context=context,output_limit=None)),flush=True)
                value=backend_json(self.url+'/completion',completion_request(body,tokens))
                return completion_response(model,value,think=bool(body.get('think')),expected_prompt_tokens=len(tokens))
            finally:self.stop()


def serve(ollama_executable):
    root=Path(os.environ['OLLAMA_MODELS'])
    backend=DirectBackend(Path(ollama_executable).parent/'lib/ollama/llama-server.exe',root)
    address=urlsplit('http://'+os.environ['OLLAMA_HOST'])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,message,*args):print('direct API:',message%args,flush=True)
        def respond(self,code,value):
            raw=json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path=='/api/version':return self.respond(200,dict(version='video-ai-llama-direct/1'))
            if self.path=='/api/ps':return self.respond(200,dict(models=[] if backend.current is None else [dict(name=backend.current)]))
            if self.path=='/api/tags':
                models=[]
                for name in ('qwen3:8b','qwen3:14b'):
                    try:blob=model_blob(root,name)
                    except (OSError,ValueError):continue
                    models.append(dict(name=name,model=name,size=blob.stat().st_size,digest=blob.name.removeprefix('sha256-')))
                return self.respond(200,dict(models=models))
            self.respond(404,dict(error='unknown local compatibility endpoint'))
        def do_POST(self):
            if self.path!='/api/generate':return self.respond(404,dict(error='unknown local compatibility endpoint'))
            try:
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8'))
                self.respond(200,backend.generate(body))
            except Exception as exc:self.respond(500,dict(error=f'{type(exc).__name__}: {exc}'))
    server=ThreadingHTTPServer((address.hostname,address.port),Handler)
    try:server.serve_forever()
    finally:server.server_close();backend.stop()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ollama-executable',required=True)
    parser.add_argument('command',choices=['serve'])
    args=parser.parse_args();serve(args.ollama_executable)


if __name__=='__main__':main()
