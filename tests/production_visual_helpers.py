"""Actual local Comfy HTTP with synthetic test-only PNG/MP4 outputs."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import struct
import threading
from uuid import uuid4
import zlib

from video_ai.config import load_config,read_json
from video_ai.runtime.environment import build_child_env
from video_ai.runtime.processes import run_logged
from video_ai.runtime.workflows import WorkflowTemplate


def png(width,height):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x30\x60\x90'*width)*height))+chunk(b'IEND',b'')


@contextmanager
def comfy_server(config,run,paths,logger,*,mode='normal',upscale_mode=None):
    templates=[WorkflowTemplate.load(config.workflows[k],config.workflows.get(k+'_mapping',config.workflows[k].with_suffix('.mapping.json')),config.models) for k in ('sdxl','wan','upscale')]
    from unit.test_workflows import remote_info
    info={}
    for t in templates:info.update(remote_info(t))
    posts=[];gets=[];history={}
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    class Handler(BaseHTTPRequestHandler):
        def send(self,data,status=200):
            raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            gets.append(self.path)
            if self.path=='/object_info':return self.send(info)
            if self.path=='/queue':
                rows=[]
                if mode.startswith('lost_queue_'):
                    rows=[json.loads(json.dumps(entry['prompt'])) for entry in history.values()]
                    for row in rows:
                        if mode=='lost_queue_graph':
                            first=next(iter(row[2]));row[2][first]['class_type']='ForeignLoader'
                        if mode=='lost_queue_client':row[3]['client_id']='foreign-client'
                return self.send(dict(queue_running=rows,queue_pending=[]))
            if self.path.startswith('/history'):
                data=history if self.path=='/history' else {k:v for k,v in history.items() if k==self.path.split('/')[-1]}
                if self.path=='/history' and mode=='lost_queue_same':
                    data=json.loads(json.dumps(data))
                    for entry in data.values():entry['status']=dict(status_str='running',completed=False,messages=[])
                return self.send(data)
            self.send({},404)
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));posts.append(body)
            graph=body['prompt'];t=next(t for t in templates if set(t.graph)==set(graph))
            def value(k):r=t.mapping['inputs'][k];return graph[r['node_id']]['inputs'][r['input']]
            prefix=value('output_prefix')
            is_upscale='image' in t.mapping['inputs'] and 'width' not in t.mapping['inputs']
            default_mode=mode.removeprefix('upscale_') if is_upscale else ('normal' if mode.startswith('upscale_') else mode)
            active_mode=(upscale_mode.get('mode','normal') if isinstance(upscale_mode,dict) else upscale_mode) if is_upscale and upscale_mode is not None else default_mode
            w,h=(1920,1080) if is_upscale else (value('width'),value('height'))
            target=run/'comfy/output'/(prefix+'_00001_'+('image.png' if 'length' not in t.mapping['inputs'] else 'video.mp4'))
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.suffix=='.png':target.write_bytes(b'broken' if active_mode=='broken_png' else png(w+8 if active_mode=='wrong_size' else w,h))
            else:
                n=1 if active_mode=='short' else value('length')
                result=run_logged(tuple(str(a) for a in (actual.tools['ffmpeg'],'-nostdin','-n','-v','error','-f','lavfi','-i',f'testsrc2=size={w}x{h}:rate=16','-frames:v',n,'-an','-c:v','libx264','-pix_fmt','yuv420p',target)),
                                  cwd=run,env=build_child_env(paths),timeout=300,logger=logger,stage='fixture',unit_id='test-video')
                assert result.returncode==0,result.stderr_path.read_text()
            pid=str(uuid4());number=len(posts)
            entry=dict(prompt=[number,pid,graph,dict(client_id=body['client_id']),[t.mapping['output']['node_id']]],
                       status=dict(status_str='success',completed=True,messages=[]),outputs={t.mapping['output']['node_id']:{t.mapping['output']['collection']:[dict(filename=target.name,subfolder=target.parent.relative_to(run/'comfy/output').as_posix(),type='output')]}})
            if active_mode=='failed':
                entry['status']=dict(status_str='error',completed=False,messages=[['execution_error',dict(prompt_id=pid,node_id='3',node_type='ImageUpscaleWithModel',exception_message='fixture model failure',exception_type='RuntimeError',traceback=[])]])
                entry['outputs']={}
            if active_mode=='normalized_numeric' and 'length' in t.mapping['inputs']:
                entry=json.loads(json.dumps(entry))
                ref=t.mapping['inputs']['fps']
                entry['prompt'][2][ref['node_id']]['inputs'][ref['input']]=float(value('fps'))
            if active_mode!='missing':history[pid]=entry
            if active_mode=='multiple':
                other=str(uuid4());copy=json.loads(json.dumps(entry));copy['prompt'][1]=other;history[other]=copy
            if active_mode in ('lost','missing','multiple') or active_mode.startswith('lost_queue_'):return self.send({},503)
            if active_mode=='malformed':return self.send([])
            if active_mode in ('malformed_json','invalid_utf8'):
                raw=b'{broken' if active_mode=='malformed_json' else b'\xff'
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            self.send(dict(prompt_id=pid,number=number,node_errors={}))
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',posts,gets,history
    finally:server.shutdown();server.server_close();thread.join(2)


def configure_comfy(config,url,run):
    data=read_json(config.config_file);data['services']['comfyui']=url
    actual=read_json(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    data['models']=actual['models'] # stamps only; test servers never load these files
    file=run/'all-service-config.json';file.write_text(json.dumps(data),encoding='utf-8')
    return load_config(file)


def install_visual_owned(monkeypatch):
    from production_helpers import install_owned_services
    from video_ai.runtime.services import ServiceHandle
    import video_ai.runtime.production_visuals as v
    cls=install_owned_services(monkeypatch)
    monkeypatch.setattr(v,'ServiceManager',cls);monkeypatch.setattr(v,'port_listening',lambda *a:False)
    # Synthetic PNGs/testsrc videos have no semantic content. Media transport
    # tests explicitly bypass review; real gate behavior has separate tests.
    monkeypatch.setattr(v,'require_image_review',lambda *a:None)
    return cls
