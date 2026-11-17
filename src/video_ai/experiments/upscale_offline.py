"""Synthetic CPU fixtures for the separate LVA-05 offline entry points."""
import json
from pathlib import Path
import struct
from uuid import uuid4
import zlib

from .wan_fast_profiles import artifact


def write_png(path, width, height, color=(32,96,192)):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=(b'\0'+bytes(color)*width)*height
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)


def offline_manifest(root, factor, *, count=3):
    root=Path(root);root.mkdir(parents=True)
    fake=root/'synthetic-model-marker.txt';fake.write_text('OFFLINE: no weights or model loading',encoding='utf-8')
    frames=[]
    for i in range(1,count+1):
        source=root/'input'/f'frame_{i:06d}.png';write_png(source,16,16,(i*32,96,192))
        graph={'1':{'inputs':{'image':source.name}},'5':{'inputs':{'filename_prefix':f'frame_{i:06d}'}}}
        frames.append(dict(frame_id=i,source=artifact(source).identity_dict(),graph=graph))
    return dict(schema_version=1,task_id='LVA-05',factor=factor,
        artifacts={'offline_marker':artifact(fake).identity_dict()},
        parameters=dict(width=1920,height=1080,fps=16),frames=frames,
        source_binding=dict(kind='synthetic_CPU_only',human_quality='not_applicable'))


class OfflineTransport:
    """Only the network boundary is fake; all journal/copy/PNG work is real."""
    def __init__(self,root):self.root=Path(root);self.calls=[];self.history={}
    def __call__(self,method,route,payload=None):
        self.calls.append((method,route))
        if method=='POST':
            if set(payload)!={'prompt','client_id'}:raise ValueError('unknown Comfy POST fields')
            graph=payload['prompt'];name=graph['5']['inputs']['filename_prefix']+'.png'
            index=int(Path(graph['1']['inputs']['image']).stem.split('_')[-1])
            output=self.root/'output'/name;write_png(output,1920,1080,(index*32,96,192))
            pid=str(uuid4())
            self.history[pid]=dict(prompt=[0,pid,graph,{'client_id':payload['client_id']}],
                status=dict(completed=True,status_str='success'),
                outputs={'5':{'images':[dict(type='output',filename=name,subfolder='')]}})
            return dict(prompt_id=pid,node_errors={})
        if route=='/history':return self.history
        if route=='/queue':return dict(queue_running=[],queue_pending=[])
        pid=route.split('/')[-1];return {pid:self.history[pid]} if pid in self.history else {}
