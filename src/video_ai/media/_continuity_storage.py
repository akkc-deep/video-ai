"""Versioned lossless geometry storage; logical metrics remain schema one."""
import base64
from copy import deepcopy
import hashlib
import json
import math
import re
import struct
import zlib

from ..adapters.common import strict_json

MODE='typed_geometry_zlib_v1'
PACK_THRESHOLD=1024*1024
MAX_BLOCK=16*1024*1024
MAX_EXPANDED=64*1024*1024


def _pairs(value):
    if 'comparisons' in value and 'comparison' not in value:return value['comparisons']
    if 'comparison' in value and 'comparisons' not in value:return [value['comparison']]
    raise ValueError('geometry storage requires one comparison container')


def storage_needed(value):
    size=0
    for pair in _pairs(value):
        for region in pair['regions']:
            for name in ('vectors','sampled_pairs'):
                size+=len(json.dumps(region['geometry'][name],allow_nan=False,separators=(',',':')).encode('utf-8'))
                if size>PACK_THRESHOLD:return True
    return False


def _map(value,operation):
    def pair_copy(pair):
        regions=[]
        for region in pair['regions']:
            geometry=dict(region['geometry'])
            for name in ('vectors','sampled_pairs'):geometry[name]=operation(name,geometry[name])
            regions.append(dict(region,geometry=geometry))
        return dict(pair,regions=regions)
    result=dict(value)
    if 'comparisons' in value and 'comparison' not in value:result['comparisons']=[pair_copy(p) for p in value['comparisons']]
    elif 'comparison' in value and 'comparisons' not in value:result['comparison']=pair_copy(value['comparison'])
    else:raise ValueError('geometry storage comparison container differs')
    return result


def _encode(name,value):
    if type(value) is not list:raise ValueError('geometry array required')
    if not value:return []
    if name=='sampled_pairs':
        if len(value)>MAX_BLOCK//16:raise ValueError('resource_limit: sampled coordinates')
        raw=bytearray()
        for row in value:
            if (type(row) is not list or len(row)!=2 or any(type(p) is not list or len(p)!=2 for p in row)
                    or any(type(n) is not int or not 0<=n<=4294967295 for p in row for n in p)):
                raise ValueError('uint32 coordinate shape/types differ')
            raw.extend(struct.pack('<IIII',*row[0],*row[1]))
        codec='u32le_zlib_v1'
    else:
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        codec='json_zlib_v1'
    if len(raw)>MAX_BLOCK:raise ValueError('resource_limit: geometry block')
    return dict(codec=codec,rows=len(value),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
        data=base64.b64encode(zlib.compress(raw,6)).decode('ascii'))


def encode_document(value,*,packed=False):
    if not packed:return value
    if type(value.get('schema_version')) is not int or value['schema_version']!=1 or value.get('algorithm')!='continuity_cv_v1':
        raise ValueError('unsupported logical geometry document')
    if 'continuity_storage' in value:raise ValueError('logical document already has storage marker')
    result=_map(value,_encode)
    result.update(schema_version=2,continuity_storage=MODE)
    return result


class EncodedJSONLimit(ValueError):
    """The bounded producer representation cannot fit one JSON file."""


def _bounded_strings(value,maximum,check):
    # JSONEncoder streams containers, but encodes an entire string token at
    # once. Bound those tokens before asking it to allocate escaped strings.
    from itertools import chain
    pending=[iter((value,))]
    while pending:
        try:item=next(pending[-1])
        except StopIteration:pending.pop();continue
        if isinstance(item,dict):pending.append(chain.from_iterable(item.items()))
        elif isinstance(item,(list,tuple)):pending.append(iter(item))
        elif isinstance(item,str):
            if check is not None:check()
            if len(item)+2>maximum:raise EncodedJSONLimit('resource_limit: output JSON')
            if len(item)*6+2<=maximum:continue
            if item.isascii() and item.isprintable():
                if len(item)+item.count('"')+item.count('\\')+2>maximum:
                    raise EncodedJSONLimit('resource_limit: output JSON')
                continue
            size=2
            for start in range(0,len(item),max(1,min(65536,maximum//6))):
                if check is not None:check()
                part=item[start:start+max(1,min(65536,maximum//6))]
                size+=len(json.dumps(part,ensure_ascii=False).encode('utf-8'))-2
                if size>maximum:raise EncodedJSONLimit('resource_limit: output JSON')


def iter_document_bytes(value,*,packed=False,maximum=None,check=None):
    """The producer's exact UTF-8 JSON, with bounded optional verification IO."""
    stored=encode_document(value,packed=packed)
    if maximum is not None:_bounded_strings(stored,maximum,check)
    options=dict(separators=(',',':')) if packed else dict(indent=2)
    encoder=json.JSONEncoder(ensure_ascii=False,allow_nan=False,**options)
    size=0
    for text in encoder.iterencode(stored):
        if check is not None:check()
        part=text.encode('utf-8');size+=len(part)
        if maximum is not None and size>maximum:
            raise EncodedJSONLimit('resource_limit: output JSON')
        yield part


class GeometryDecoder:
    """Physical JSON budgets remain with callers; expansion has another bound."""
    def __init__(self,*,max_expanded=MAX_EXPANDED):
        if type(max_expanded) is not int or not 0<max_expanded<=MAX_EXPANDED:raise ValueError('invalid geometry expansion limit')
        self.maximum=max_expanded;self.expanded_bytes=0;self.document_bytes=0;self.cache={}

    def _block(self,name,value):
        if type(value) is list and not value:return []
        if type(value) is not dict or set(value)!={'codec','rows','bytes','sha256','data'}:raise ValueError('geometry descriptor fields differ')
        codec='u32le_zlib_v1' if name=='sampled_pairs' else 'json_zlib_v1'
        rows,size=value['rows'],value['bytes']
        if (value['codec']!=codec or type(rows) is not int or not 0<rows<=MAX_BLOCK
                or type(size) is not int or not 0<size<=MAX_BLOCK):raise ValueError('invalid geometry codec/shape/size')
        if name=='sampled_pairs' and size!=rows*16:raise ValueError('coordinate byte length differs')
        digest,data=value['sha256'],value['data']
        if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest) or type(data) is not str:
            raise ValueError('invalid geometry digest/data')
        if len(data)>4*((MAX_BLOCK+2)//3):raise ValueError('resource_limit: encoded geometry block')
        # Repeated descriptors share cached backing data, but every occurrence
        # allocates an independent returned list. Bound each document as well.
        if self.document_bytes+size>self.maximum:raise ValueError('resource_limit: document geometry expansion')
        self.document_bytes+=size
        key=(codec,rows,size,digest,data)
        if key in self.cache:return deepcopy(self.cache[key])
        if self.expanded_bytes+size>self.maximum:raise ValueError('resource_limit: geometry expansion')
        try:
            compressed=base64.b64decode(data,validate=True)
            stream=zlib.decompressobj();raw=stream.decompress(compressed,size+1)
        except (ValueError,zlib.error) as exc:raise ValueError('invalid compressed geometry') from exc
        if (len(raw)!=size or not stream.eof or stream.unused_data or stream.unconsumed_tail
                or hashlib.sha256(raw).hexdigest()!=digest):raise ValueError('geometry stream/length/digest differs')
        if name=='sampled_pairs':
            result=[[[a,b],[c,d]] for a,b,c,d in struct.iter_unpack('<IIII',raw)]
        else:
            result=strict_json(raw)
            if type(result) is not list or len(result)!=rows:raise ValueError('geometry row count differs')
            pending=[result]
            while pending:
                item=pending.pop()
                if type(item) is float and not math.isfinite(item):raise ValueError('non-finite geometry value')
                if isinstance(item,dict):pending.extend(item.values())
                elif isinstance(item,list):pending.extend(item)
        self.expanded_bytes+=size;self.cache[key]=result
        return deepcopy(result)

    def decode(self,value):
        self.document_bytes=0
        if type(value) is not dict or 'continuity_storage' not in value:return value
        if (type(value.get('schema_version')) is not int or value['schema_version']!=2
                or value.get('algorithm')!='continuity_cv_v1' or value['continuity_storage']!=MODE):
            raise ValueError('unsupported continuity storage version')
        try:result=_map(value,self._block)
        except (KeyError,TypeError) as exc:raise ValueError('invalid stored geometry structure') from exc
        result.pop('continuity_storage');result['schema_version']=1
        return result
