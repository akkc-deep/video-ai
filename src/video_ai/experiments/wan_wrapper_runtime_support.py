"""Strict source trace utilities. No payload read until an admitted reader is called."""
import json
import struct
import hashlib
import os
from pathlib import Path
import importlib.machinery
import sys
from contextlib import contextmanager
import threading

SOFTWARE_SHA256='ae3f18849f140771e8a50bf3509c7423e0aa7f701d8276c4ecfc88b3068ede34'


@contextmanager
def admission_progress_scope():
    """Admission has no video prompt. Preserve progress for other threads."""
    import comfy.utils as utils
    original=utils.PROGRESS_BAR_HOOK
    owner=threading.get_ident()
    def hook(*args,**kwargs):
        if threading.get_ident()!=owner and original is not None:
            return original(*args,**kwargs)
    utils.set_progress_bar_global_hook(hook)
    try:yield
    finally:utils.set_progress_bar_global_hook(original)


class InputLeases:
    """Windows deny-write/delete handles and one full digest per admitted artifact."""
    def __init__(self,artifacts):
        self.files=[];self.closed=False
        if os.name!='nt':raise ValueError('mandatory Windows input leases required')
        from video_ai.runtime.verification import _locked_reader
        try:
            for item in artifacts:
                path=Path(item['path'])
                if path.resolve(strict=True)!=path or path.is_symlink():raise ValueError('lease path alias')
                context=_locked_reader(path);stream=context.__enter__()
                self.files.append((context,stream,path,os.fstat(stream.fileno())))
                h=hashlib.sha256()
                for chunk in iter(lambda:stream.read(8*1024**2),b''):h.update(chunk)
                if stream.tell()!=item['bytes'] or h.hexdigest()!=item['sha256']:raise ValueError('leased artifact content differs')
            self.verify()
        except BaseException:self.close();raise

    def verify(self):
        if self.closed:raise ValueError('input lease expired')
        for _,stream,path,before in self.files:
            if stream.closed:raise ValueError('input lease lost')
            for current in (path.stat(),os.fstat(stream.fileno())):
                if (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns)!=(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns):
                    raise ValueError('leased input changed')

    def close(self):
        self.closed=True
        for context,_,_,_ in reversed(self.files):context.__exit__(None,None,None)
        self.files=[]


class SoftwareVerifier:
    """Verify actually imported source before execution, retaining mandatory leases.

    Native runtime binaries/archives are checked once before Comfy starts. Source
    modules are checked once on import, rather than scanning 49,797 files per run.
    """
    def __init__(self,rows,roots):
        self.rows={str(Path(r['path']).resolve()).lower():r for r in rows};self.roots=[Path(p).resolve() for p in roots]
        self.leases={};self.finder=None
    def verify(self,path):
        path=Path(path).resolve()
        key=str(path).lower()
        if key not in self.rows:raise ValueError('unsealed software module: '+str(path))
        if key not in self.leases:
            row=self.rows[key];self.leases[key]=InputLeases([{k:row[k] for k in ('path','bytes','sha256')}])
        self.leases[key].verify()
    def install(self):
        verifier=self
        class Loader:
            def __init__(self,original,origin):self.original=original;self.origin=origin
            def create_module(self,spec):
                creator=getattr(self.original,'create_module',None)
                return creator(spec) if creator else None
            def exec_module(self,module):
                verifier.verify(self.origin)
                if Path(self.origin).suffix=='.py':
                    # Execute the verified source, never an unrelated cached .pyc.
                    exec(compile(Path(self.origin).read_bytes(),self.origin,'exec'),module.__dict__)
                else:self.original.exec_module(module)
            def __getattr__(self,name):return getattr(self.original,name)
        class Finder:
            def find_spec(self,fullname,path=None,target=None):
                spec=importlib.machinery.PathFinder.find_spec(fullname,path,target)
                if spec is None or not spec.origin or spec.loader is None:return spec
                origin=Path(spec.origin)
                if any(origin.is_relative_to(root) for root in verifier.roots):
                    if '.zip' in spec.origin and not origin.is_file():
                        archive=Path(spec.origin[:spec.origin.index('.zip')+4]);verifier.verify(archive)
                    else:spec.loader=Loader(spec.loader,spec.origin)
                return spec
        self.finder=Finder();sys.meta_path.insert(0,self.finder)
    def close(self):
        if self.finder in sys.meta_path:sys.meta_path.remove(self.finder)
        for lease in self.leases.values():lease.close()
        self.leases.clear()


def read_safetensors_header(path):
    with path.open('rb') as f:
        raw=f.read(8)
        if len(raw)!=8:raise ValueError('header length')
        n=struct.unpack('<Q',raw)[0]
        if not 2<=n<=16*1024**2:raise ValueError('bounded header')
        value=json.loads(f.read(n));value.pop('__metadata__',None);return value


class TraceInputs(dict):
    def __init__(self,mapping,reader,header):
        super().__init__({k:None for k in mapping});self.mapping=mapping;self.reader=reader;self.header=header;self.cache={};self.read=set()
    def __getitem__(self,key):
        import torch
        if key not in self.mapping:raise KeyError(key)
        if key not in self.cache:
            value=self.reader(self.mapping[key]);meta=self.header[self.mapping[key]]
            if list(value.shape)!=meta['shape'] or not value.is_floating_point() or not torch.isfinite(value).all().item():
                raise ValueError('original source tensor shape/finite')
            self.cache[key]=value
        self.read.add(key);return self.cache[key]
    def get(self,key,default=None):return self[key] if key in self else default


def verify_retained(data,parsed,manifest):
    rows={row['normalized_key']:row for row in manifest if row['classification']=='applicable_pending_execution'}
    if data.read!=set(data.mapping) or set(parsed)!={'diffusion_model.'+rows[k]['target'] for k in data.mapping}:
        raise ValueError('source read/parsed target set mismatch')
    for key in data.mapping:
        payload=parsed['diffusion_model.'+rows[key]['target']]
        if key.endswith(('.lora_up.weight','.lora_B.weight')):retained=payload.weights[0]
        elif key.endswith(('.lora_down.weight','.lora_A.weight')):retained=payload.weights[1]
        elif key.endswith(('.diff','.diff_b')) and isinstance(payload,tuple) and payload[0]=='diff':retained=payload[1][0]
        else:raise ValueError('unsupported retained input slot')
        if retained is not data.cache[key]:raise ValueError('source overwritten/not retained')
