"""Duplicate audit representations can be byte-proved without parsing them twice."""
import json
import os
from pathlib import Path
from time import monotonic
import tracemalloc

import pytest


@pytest.fixture
def expected_case(runtime_run):
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    from video_ai.media._continuity_audit import AuditWindow
    _,_,paths=runtime_run;audit=create_run(paths)
    return audit,AuditWindow(paths,RunLogger(audit),monotonic()+300)


def read_window(audit,budget=None):
    from video_ai.media.continuity_report import _ReadWindow
    return _ReadWindow(monotonic()+300,audit,budget)


@pytest.mark.parametrize('packed',[False,True])
def test_producer_exact_duplicate_needs_no_parse_but_remains_in_byte_closure(expected_case,packed):
    audit,writer=expected_case
    value=dict(schema_version=1,algorithm='continuity_cv_v1',comparison={'regions':[{'geometry':{
        'vectors':[[1.0,-0.0]],'sampled_pairs':[[[1,2],[3,4]]]}}]})
    writer.packed_geometry=packed;ref=writer.save('pairs/000000.json',value)
    window=read_window(audit)
    assert window.matches_json(ref['path'],value,packed=packed)
    assert window.json_bytes==0 and ref['path'] in window.frozen
    assert window.geometry_decoder.expanded_bytes==0
    window.verify()


def test_alternative_formatting_uses_original_parse_and_charges_bytes(expected_case):
    audit,writer=expected_case;value={'value':1,'other':'文字'}
    ref=writer.save('metrics.json',value);path=Path(ref['path'])
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf-8')
    window=read_window(audit)
    assert window.matches_json(path,value,packed=False)
    assert window.json_bytes==path.stat().st_size


@pytest.mark.parametrize('raw',['{"value":true}','{"value":2}','{"value":1.0}','{"value":1,"value":1}','{"value":NaN}'])
def test_changed_types_values_or_invalid_json_cannot_use_expected_hash(expected_case,raw):
    audit,writer=expected_case;ref=writer.save('metrics.json',{'value':1})
    path=Path(ref['path']);path.write_text(raw,encoding='utf-8');window=read_window(audit)
    try:result=window.matches_json(path,{'value':1},packed=False)
    except ValueError:return
    assert result is False


def test_fallback_preserves_negative_zero_distinction(expected_case):
    audit,writer=expected_case;path=Path(writer.save('metrics.json',{'value':0.0})['path'])
    assert read_window(audit).matches_json(path,{'value':-0.0},packed=False) is False


def test_shared_reader_budget_is_not_refunded_or_reset_by_the_exact_path(expected_case):
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime.production_state import ProductionRefused
    audit,writer=expected_case;ref=writer.save('metrics.json',{'value':1})
    budget=Reader()
    for index in range(4):budget.charge(f'already-parsed-{index}',16*1024*1024)
    assert read_window(audit,budget).matches_json(ref['path'],{'value':1},packed=False)
    assert budget.bytes==64*1024*1024
    path=Path(writer.save('alternate.json',{'value':1})['path']);path.write_text('{"value": 1}',encoding='utf-8')
    with pytest.raises(ProductionRefused,match='metadata'):
        read_window(audit,budget).matches_json(path,{'value':1},packed=False)


def test_large_expected_string_abandons_encoding_before_large_allocation(expected_case,monkeypatch):
    from video_ai.media import continuity_report
    audit,writer=expected_case;ref=writer.save('metrics.json',{'value':1})
    value={'value':'\x00'*(2*1024*1024)};monkeypatch.setattr(continuity_report,'MAX_JSON',128)
    window=read_window(audit);tracemalloc.start()
    try:
        initial=tracemalloc.get_traced_memory()[0]
        assert window.matches_json(ref['path'],value,packed=False) is False
        peak=tracemalloc.get_traced_memory()[1]-initial
    finally:tracemalloc.stop()
    assert peak<1024*1024
    assert window.json_bytes==Path(ref['path']).stat().st_size


def test_exact_match_still_detects_later_byte_changes(expected_case):
    audit,writer=expected_case;ref=writer.save('metrics.json',{'value':1})
    window=read_window(audit);assert window.matches_json(ref['path'],{'value':1},packed=False)
    Path(ref['path']).write_text('{"value":2}',encoding='utf-8')
    with pytest.raises((OSError,ValueError)):window.verify()


def test_producer_deadline_stops_encoding_before_writing(expected_case):
    audit,writer=expected_case;writer.deadline=0
    with pytest.raises(TimeoutError):writer.save('expired.json',{'value':1})
    assert not (audit/'logs/continuity/expired.json').exists()


@pytest.mark.parametrize('kind',['empty','large','hardlink'])
def test_exact_expected_never_bypasses_file_admission(expected_case,monkeypatch,kind):
    from video_ai.media import continuity_report
    audit,writer=expected_case;path=Path(writer.save('metrics.json',{'value':1})['path'])
    if kind=='empty':path.write_bytes(b'')
    elif kind=='large':monkeypatch.setattr(continuity_report,'MAX_JSON',4)
    else:os.link(path,path.with_name('alias.json'))
    with pytest.raises((ValueError,OSError)):
        read_window(audit).matches_json(path,{'value':1},packed=False)
