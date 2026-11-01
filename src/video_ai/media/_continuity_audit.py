"""Audit-only identity windows, dependency fingerprints and PNG evidence."""
from copy import deepcopy
import importlib.metadata
import json
from pathlib import Path
import platform
import struct
import sys
import zlib

from ._continuity_geometry import numerical
from ._continuity_schema import stable
from .colorimetry import _identity_shape, _local_file
from ..planning.production_scenes import canonical_digest
from ..runtime.logging import RunLogger
from ..runtime.manifest import thaw,hash_file,validate_run_dir


class AuditWindow:
    def __init__(self,paths,logger,deadline):
        paths.validate()
        if not isinstance(logger,RunLogger) or logger.production:raise ValueError('independent non-production audit logger required')
        run=validate_run_dir(logger.run_dir)
        if run.parent!=paths.runs_root or logger.root!=run/'logs':raise ValueError('audit logger location differs')
        if any(p.name!='logs' for p in run.iterdir()):raise ValueError('new independent audit run required')
        if any(p.name not in ('events.jsonl','errors','processes') for p in logger.root.iterdir()):raise ValueError('empty audit output required')
        self.logger=logger;self.deadline=deadline;self.frozen={};self.outputs=[];self.json_bytes=0
        from ._continuity_storage import GeometryDecoder
        self.geometry_decoder=GeometryDecoder();self.packed_geometry=False

    def check_time(self):
        from .continuity_analysis import _check_deadline
        _check_deadline(self.deadline)

    def freeze(self,path, *, package=False):
        self.check_time();path=Path(path)
        if package:
            if not path.is_absolute() or path!=path.resolve(strict=True) or any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)) or path.stat().st_nlink!=1:
                raise ValueError('redirected dependency/source')
        else:path=_local_file(path)
        key=str(path)
        if key not in self.frozen:self.frozen[key]=thaw(hash_file(path))
        return deepcopy(self.frozen[key])

    def check(self,record):
        path=_identity_shape(record)
        if path.is_relative_to(self.logger.run_dir):raise ValueError('source evidence must be outside new audit')
        value=self.freeze(path)
        if stable(value)!=stable(record):raise OSError(f'input identity differs: {path}')
        return value

    def read_json(self,record):
        value=self.check(record)
        if value['bytes']>16777216 or self.json_bytes+value['bytes']>67108864:raise ValueError('resource_limit: JSON/metadata')
        self.json_bytes+=value['bytes']
        return self.geometry_decoder.decode(json.loads(Path(value['path']).read_text(encoding='utf-8')))

    def release_json(self,record):
        self.json_bytes=max(0,self.json_bytes-record['bytes'])

    def verify(self):
        for value in self.frozen.values():
            actual=thaw(hash_file(Path(value['path'])))
            if stable(actual)!=stable(value):raise OSError(f'input/dependency bytes changed: {value["path"]}')
            self.check_time()

    def save_bytes(self,name,data):
        self.check_time();path=self.logger.path('continuity/'+name)
        if any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)):raise ValueError('redirected output')
        output=self.logger.save_bytes('continuity/'+name,data);self.outputs.append(output)
        return thaw(hash_file(output))

    def save(self,name,value):
        from ._continuity_storage import iter_document_bytes
        packed=(getattr(self,'packed_geometry',False) and value.get('algorithm')=='continuity_cv_v1'
            and type(value.get('schema_version')) is int and value['schema_version']==1
            and ('comparisons' in value or 'comparison' in value))
        data=b''.join(iter_document_bytes(value,packed=packed,maximum=16777216,check=self.check_time))
        if len(data)>16777216:raise ValueError('resource_limit: output JSON')
        return self.save_bytes(name,data)


def dependencies(window):
    np,cv=numerical();package_files={}
    for name in ('numpy','opencv-python-headless'):
        dist=importlib.metadata.distribution(name)
        inventory=dist.files
        if not inventory:raise RuntimeError('installed dependency RECORD inventory is missing')
        for entry in inventory:
            if str(entry).endswith('.pyc'):continue
            located=Path(dist.locate_file(entry))
            if any(p.is_symlink() or p.is_junction() for p in (located,*located.parents)):
                raise ValueError('redirected dependency RECORD entry')
            p=located.resolve(strict=True)
            # RECORD is installed-package evidence; never scan unrelated trees.
            value=window.freeze(p,package=True);package_files[value['path']]=value
    for p in sorted(Path(__file__).parent.glob('*continuity*.py')):
        value=window.freeze(p,package=True);package_files[value['path']]=value
    for name in ('colorimetry.py',):
        value=window.freeze(Path(__file__).with_name(name),package=True);package_files[value['path']]=value
    files=[package_files[k] for k in sorted(package_files)]
    build=cv.getBuildInformation();info=window.save_bytes('build-information.txt',build.encode('utf-8'))
    versions=dict(python=sys.version,numpy=np.__version__,opencv=cv.__version__)
    fingerprint=canonical_digest(dict(**versions,build_information=build,package_files=stable(files)))
    return dict(**versions,build_information=info,package_files=files,fingerprint=fingerprint)


def png_bytes(image):
    h,w=image.shape[:2]
    def chunk(kind,value):return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value))
    rows=b''.join(b'\0'+image[y].tobytes() for y in range(h))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+
            chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))
