"""Lossless typed geometry storage and bounded hostile-input decoding."""
import base64
from copy import deepcopy
import hashlib
import json
import math
import zlib

import pytest


def module():
    from video_ai.media import _continuity_storage
    return _continuity_storage


def document():
    return {'schema_version':1,'algorithm':'continuity_cv_v1','comparisons':[
        {'regions':[{'geometry':{'vectors':[dict(left=[-0.0,.2],right=[.3,.4],residual=None,fb_error=0.,ncc=1.)],
            'sampled_pairs':[[[0,1],[2,4294967295]],[[3,4],[5,6]]]}}]}]}


def test_typed_storage_roundtrip_keeps_numeric_types_null_and_negative_zero():
    m=module();value=document();before=deepcopy(value)
    encoded=m.encode_document(value,packed=True)
    assert value==before and encoded['schema_version']==2
    restored=m.GeometryDecoder().decode(json.loads(json.dumps(encoded)))
    from video_ai.planning.production_scenes import canonical_digest
    assert canonical_digest(restored)==canonical_digest(value)
    geometry=restored['comparisons'][0]['regions'][0]['geometry']
    assert math.copysign(1,geometry['vectors'][0]['left'][0])==-1
    assert geometry['vectors'][0]['residual'] is None
    assert type(geometry['sampled_pairs'][0][0][0]) is int


def test_small_mode_is_unchanged_and_bulk_geometry_selects_bounded_mode(monkeypatch):
    m=module();value=document()
    assert not m.storage_needed(value)
    assert m.encode_document(value,packed=False)==value
    monkeypatch.setattr(m,'PACK_THRESHOLD',1)
    assert m.storage_needed(value)


@pytest.mark.parametrize('mutation',['version','extra','codec','base64','sha','rows','bytes','truncated','trailing','nonfinite'])
def test_decoder_rejects_ambiguous_corrupt_or_unbounded_blocks(mutation):
    m=module();value=m.encode_document(document(),packed=True)
    block=value['comparisons'][0]['regions'][0]['geometry']['vectors']
    if mutation=='version':value['continuity_storage']='unknown'
    elif mutation=='extra':block['extra']=True
    elif mutation=='codec':block['codec']='unknown'
    elif mutation=='base64':block['data']='!'+block['data']
    elif mutation=='sha':block['sha256']='0'*64
    elif mutation=='rows':block['rows']=True
    elif mutation=='bytes':block['bytes']=16777217
    else:
        raw=base64.b64decode(block['data'])
        if mutation=='truncated':raw=raw[:-1]
        elif mutation=='trailing':raw+=b'ignored'
        else:
            body=b'[1e9999]';raw=zlib.compress(body)
            block.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
        block['data']=base64.b64encode(raw).decode('ascii')
    with pytest.raises(ValueError):m.GeometryDecoder().decode(value)


def test_expansion_budget_counts_unique_blocks_without_refunding_or_aliasing():
    m=module();encoded=m.encode_document(document(),packed=True)
    decoder=m.GeometryDecoder()
    first=decoder.decode(encoded);charged=decoder.expanded_bytes
    first['comparisons'][0]['regions'][0]['geometry']['sampled_pairs'][0][0][0]=999
    assert decoder.decode(encoded)==document()
    assert decoder.expanded_bytes==charged
    limited=m.GeometryDecoder(max_expanded=charged)
    assert limited.decode(encoded)==document()
    different=document();different['comparisons'][0]['regions'][0]['geometry']['sampled_pairs'][0][0][0]=8
    with pytest.raises(ValueError,match='resource_limit'):
        limited.decode(m.encode_document(different,packed=True))


def test_integer_shape_and_decompression_size_are_checked_before_acceptance():
    m=module();encoded=m.encode_document(document(),packed=True)
    block=encoded['comparisons'][0]['regions'][0]['geometry']['sampled_pairs']
    block['rows']+=1
    with pytest.raises(ValueError):m.GeometryDecoder().decode(encoded)


def test_repeated_cached_blocks_cannot_expand_one_document_without_limit():
    m=module();encoded=m.encode_document(document(),packed=True)
    initial=m.GeometryDecoder();initial.decode(encoded)
    budget=initial.expanded_bytes
    encoded['comparisons']*=10
    with pytest.raises(ValueError,match='resource_limit'):
        m.GeometryDecoder(max_expanded=budget).decode(encoded)
    encoded=m.encode_document(document(),packed=True)
    block=encoded['comparisons'][0]['regions'][0]['geometry']['vectors']
    body=b' '*10000
    block.update(bytes=1,data=base64.b64encode(zlib.compress(body)).decode('ascii'),sha256=hashlib.sha256(b' ').hexdigest())
    with pytest.raises(ValueError):m.GeometryDecoder().decode(encoded)
