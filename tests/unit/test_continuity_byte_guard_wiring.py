"""Actual validator observations and write/POST gates reuse one semantic admission."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_manifest_hash_observation_detects_later_content_drift(runtime_run):
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime._continuity_byte_guard import capture_reads
    path=runtime_run[0]/'captured.json';path.write_text('{}')
    with capture_reads() as capture:hash_file(path)
    guard=capture.finish();path.write_text('{"changed":true}')
    with pytest.raises((ValueError,OSError)):guard.verify()


def test_protected_hash_hits_are_also_observed(runtime_run):
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime.verification import validation_session,whole_input_protection
    path=runtime_run[0]/'protected.json';path.write_text('{}')
    with validation_session(),whole_input_protection():
        hash_file(path)
        with capture_reads() as capture:hash_file(path)
        guard=capture.finish();guard.verify()
        assert [row.path for row in guard.files]==[str(path)]


@pytest.mark.parametrize('existing',[False,True])
def test_epoch_inventory_and_absence_are_observed(runtime_run,existing):
    from video_ai.runtime.scene_continuity_records import _epochs
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime._continuity_byte_guard import capture_reads
    run=runtime_run[0];root=run/'production/scene-continuity/epochs'
    if existing:root.mkdir(parents=True)
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt')})
    with capture_reads() as capture:assert _epochs(frozen,[],Reader(),current=False)==([],False)
    guard=capture.finish();(root/'new-empty-epoch').mkdir(parents=True)
    with pytest.raises((ValueError,OSError)):guard.verify()


@pytest.mark.parametrize('kind',['directory','absence'])
def test_revision_guard_enumerations_are_observed(runtime_run,kind):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    from video_ai.runtime._continuity_byte_guard import capture_reads
    run=runtime_run[0];folder=run/'revision-input';folder.mkdir()
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt')})
    original=RevisionGuard(frozen)
    if kind=='directory':original.capture_directory(folder,root=run)
    else:original.capture_absent(folder/'missing.json',root=run)
    with capture_reads() as capture:original.verify_captured_bytes()
    guard=capture.finish();(folder/('new.json' if kind=='directory' else 'missing.json')).write_text('{}')
    with pytest.raises((ValueError,OSError)):guard.verify()


def test_whole_admission_inventory_observes_its_actual_scan(runtime_run):
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime._continuity_byte_guard import capture_reads
    folder=runtime_run[0]/'whole-inventory';folder.mkdir();(folder/'first.json').write_text('{}')
    with capture_reads() as capture:EvidenceReader().inventory(folder)
    guard=capture.finish();(folder/'second.json').write_text('{}')
    with pytest.raises((ValueError,OSError)):guard.verify()


def test_job_intent_inventory_rejects_new_jobs(runtime_run):
    from video_ai.runtime._continuity_byte_guard import capture_reads, observe_inventory
    folder=runtime_run[0]/'jobs';folder.mkdir()
    with capture_reads() as capture:observe_inventory(folder,'job_intents',[])
    guard=capture.finish();guard.verify()
    (folder/'new').mkdir();(folder/'new/intent.json').write_text('{}')
    with pytest.raises((ValueError,OSError)):guard.verify()


def test_retained_prefix_proof_rejects_reappearing_original(runtime_run):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime._scene_continuity_io import Reader,artifact
    from video_ai.runtime.scene_continuity_records import _read_prefix_original
    run=runtime_run[0];original=run/'prefix-original.json';original.write_text('{}')
    ref=artifact(original)
    backup=run/'production/scene-continuity/prefix-observations'/(ref['sha256']+'.json')
    backup.parent.mkdir(parents=True);backup.write_bytes(original.read_bytes());original.unlink()
    with capture_reads() as capture:assert _read_prefix_original(ref,run,Reader())=={}
    guard=capture.finish();guard.verify();original.write_text('{"different":true}')
    with pytest.raises((ValueError,OSError)):guard.verify()


def test_inherited_metadata_fallback_keeps_missing_intermediate_record(runtime_run,monkeypatch):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime.scene_continuity_records import _metadata_folder
    from video_ai.runtime import scene_revision_records,production_inputs,_scene_revision_origins
    run=runtime_run[0];cid='scene_0001_clip_0001'
    current=SimpleNamespace(options={'scene_revision':True})
    intermediate=SimpleNamespace(options={'scene_revision':True})
    ancestor=SimpleNamespace(options={})
    first=run/'missing-intermediate';first.mkdir()
    final=run/'original-metadata';final.mkdir();(final/'clip.json').write_text('{}')
    def proof(frozen):
        return dict(imports={'clip:'+cid:[{}]},source_run='one' if frozen is current else 'two')
    monkeypatch.setattr(scene_revision_records,'require_scene_revision',proof)
    monkeypatch.setattr(production_inputs,'load_frozen_inputs',lambda name:intermediate if name=='one' else ancestor)
    monkeypatch.setattr(_scene_revision_origins,'source_clip_record',lambda frozen,_:
        {'clip':{'source':{'path':str((first if frozen is intermediate else final)/'source.mp4')}}})
    with capture_reads() as capture:assert _metadata_folder(current,cid,{})==final
    guard=capture.finish();(first/'clip.json').write_text('{}')
    assert _metadata_folder(current,cid,{})==first
    with pytest.raises((ValueError,OSError)):guard.verify()


@pytest.fixture
def media_guard_case(runtime_run,monkeypatch):
    from video_ai.planning.segments import SegmentedScript
    from video_ai.runtime.production_inputs import FrozenInputs
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime import scene_media_records as media
    from video_ai.runtime import scene_continuity_records as records
    from video_ai.runtime.manifest import hash_file
    run,config,paths=runtime_run
    frozen=FrozenInputs(config,SegmentedScript('fixture_only',False,()),
        {'run_id':run.name,'script_path':str(run/'production/script.txt'),'model_stamps':{}})
    source=run/'semantic-input.json';source.write_text('{"accepted":true}')
    extra=run/'other-input.json';extra.write_text('{}')
    calls=[];status=['ready'];units=[]
    def semantic(*args,**kwargs):
        calls.append(1);hash_file(source);hash_file(extra)
        if json.loads(source.read_text())!={'accepted':True}:raise ProductionRefused('changed fixture input')
        if status[0]=='pending':raise records.SceneContinuityPending('fixture pending')
        if status[0]=='failed':raise ProductionRefused('fixture failed')
        if status[0]=='legacy':return None
        return {'ready':True,'clips':[]}
    monkeypatch.setattr(records,'load_continuity_policy',lambda *_:None if status[0]=='legacy' else {'policy':'advisory_v1'})
    monkeypatch.setattr(records,'require_scene_continuity_acceptance',semantic)
    with RunLock(run) as lock:
        store=SceneMediaStore(frozen,run,paths=paths,lock=lock,clip_ids=['scene_0001_clip_0001'])
        store.continuity_check=lambda:semantic(frozen,units,None)
        context=dict(store=store,frozen=frozen,units=units,timeline=None)
        monkeypatch.setattr(media,'_scene_media_base_context',lambda *a,**k:context)
        yield SimpleNamespace(run=run,frozen=frozen,paths=paths,store=store,context=context,
            source=source,extra=extra,calls=calls,status=status,units=units,media=media)


def admit(case):
    return case.media.scene_media_context(case.frozen,case.units,None,paths=case.paths,lock=case.store.lock)


def test_repeated_real_writes_and_cloned_root_do_not_rebuild_semantics(media_guard_case):
    case=media_guard_case;admit(case)
    case.store.write('one.json',{'one':1});case.store.verify_global()
    clone=case.store.for_root('production/scene-composition');clone.write('two.json',{'two':2})
    assert (case.run/'production/scene-upscale/one.json').is_file()
    assert (case.run/'production/scene-composition/two.json').is_file()
    assert len(case.calls)==1


@pytest.mark.parametrize('change',['bytes','mtime','arguments'])
def test_proof_still_blocks_writes_and_http_guard_before_dispatch(media_guard_case,change):
    case=media_guard_case;admit(case);store=case.store
    fid='scene_0001_clip_0001:frame_000001';folder=store.frame_dir(fid)
    request={'frame_id':fid};graph={'1':{'class_type':'fixture_only'}}
    store.write('inputs.json',{'fixture_only':True})
    store.write(folder/'request.json',request);store.write(folder/'graph.json',graph)
    callback=store.capture_guard(request,graph)
    if change=='bytes':case.source.write_text('{"accepted":false}')
    elif change=='mtime':
        metadata=case.source.stat();os.utime(case.source,ns=(metadata.st_atime_ns,metadata.st_mtime_ns+1_000_000))
    else:case.frozen.options['new_argument']=True
    sent=[]
    with pytest.raises((ValueError,OSError)):
        callback();sent.append('would submit')
    assert not sent
    with pytest.raises((ValueError,OSError)):store.write('blocked.json',{'bad':True})
    assert not (store.root/'blocked.json').exists()
    assert len(case.calls)==1


@pytest.mark.parametrize('status',['pending','failed','legacy'])
def test_non_admitted_context_never_installs_a_ready_proof(media_guard_case,status):
    case=media_guard_case;case.status[0]=status;original=case.store.continuity_check
    if status=='legacy':
        admit(case)
        assert case.store.continuity_check is original
    else:
        with pytest.raises(ValueError):admit(case)
        assert case.store.continuity_check is original
        assert case.store.continuity_read_guard is None


def test_capture_overflow_retains_full_admission_guard(media_guard_case,monkeypatch):
    from video_ai.runtime import _continuity_byte_guard as proof
    case=media_guard_case;original=case.store.continuity_check;capture=proof.capture_reads
    monkeypatch.setattr(proof,'capture_reads',lambda: capture(maximum_files=1))
    admit(case);assert case.store.continuity_check is original
    case.source.write_text('{"accepted":false}')
    with pytest.raises(ValueError):case.store.write('blocked.json',{})
    assert not (case.store.root/'blocked.json').exists()


@pytest.mark.parametrize('operation',['new_json','existing_json','bytes','global','readonly','clone'])
def test_each_media_mutation_or_audit_pays_one_complete_continuity_proof(media_guard_case,operation):
    case=media_guard_case;admit(case);store=case.store
    store.write('existing.json',{'exists':True})
    original=store.continuity_check;calls=[]
    def complete_proof():
        original();calls.append('verified')
    store.continuity_check=store.continuity_read_guard=complete_proof
    if operation=='new_json':store.write('new.json',{'value':1})
    elif operation=='existing_json':store.write('existing.json',{'exists':True})
    elif operation=='bytes':store.write_bytes('new.body',b'body')
    elif operation=='global':store.verify_global()
    elif operation=='readonly':store.verify_captured_bytes()
    else:store.for_root('production/scene-composition').write('new.json',{'value':1})
    assert calls==['verified']


def test_distinct_media_continuity_callbacks_are_both_verified(media_guard_case):
    case=media_guard_case;admit(case);original=case.store.continuity_check;calls=[]
    def before():original();calls.append('before')
    def after():original();calls.append('after')
    case.store.continuity_check=before;case.store.continuity_read_guard=after
    case.store.verify_global()
    assert calls==['before','after']


def test_final_write_guard_still_detects_mutation_during_json_encoding(media_guard_case,monkeypatch):
    case=media_guard_case;admit(case);original=case.media.json.dumps
    def encode(value,*args,**kwargs):
        raw=original(value,*args,**kwargs)
        if value=={'encoding_marker':True}:case.source.write_text('{"accepted":false}')
        return raw
    monkeypatch.setattr(case.media.json,'dumps',encode)
    with pytest.raises(ValueError):case.store.write('blocked.json',{'encoding_marker':True})
    assert not (case.store.root/'blocked.json').exists()


def test_byte_guard_uses_live_native_protection_and_falls_back_after_close(runtime_run,monkeypatch):
    from video_ai.runtime import _continuity_byte_guard as proof
    from video_ai.runtime._protected_continuity_inputs import prepare_continuity_inputs
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime.verification import validation_session,whole_input_protection
    path=runtime_run[0]/'native-proof.json';path.write_text('{}')
    with validation_session(),whole_input_protection():
        with proof.capture_reads() as capture:hash_file(path)
        guard=capture.finish();prepare_continuity_inputs(guard.files)
        original=proof._safe;calls=[]
        def counted(value):calls.append(str(value));return original(value)
        monkeypatch.setattr(proof,'_safe',counted)
        guard.verify();assert calls==[]
    path.write_text('{"changed":true}')
    with pytest.raises((ValueError,OSError)):guard.verify()
    assert calls


def test_repeated_capture_reuses_only_a_live_protected_read(runtime_run,monkeypatch):
    from video_ai.runtime import _continuity_byte_guard as proof
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime.verification import validation_session,whole_input_protection
    path=runtime_run[0]/'native-observation.json';path.write_text('{}')
    original=proof._safe;calls=[]
    def counted(value):calls.append(str(value));return original(value)
    monkeypatch.setattr(proof,'_safe',counted)
    with validation_session(),whole_input_protection():
        with proof.capture_reads() as capture:
            for _ in range(25):hash_file(path)
        # Initial capture plus strict qualification under the anchored chain
        # is bounded setup; subsequent reads query live native attributes.
        assert set(calls)=={str(path)} and len(calls)<=4
        capture.finish().verify()


def test_ready_admission_pins_actual_closed_owned_source(media_guard_case,monkeypatch):
    from video_ai.runtime import scene_continuity_records as records
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime.verification import writable_validation_session,whole_input_protection
    case=media_guard_case;path=case.run/'production/scene-continuity/closed-source.json'
    path.parent.mkdir(parents=True);path.write_text('{}')
    original=records.require_scene_continuity_acceptance
    def semantic(*args,**kwargs):hash_file(path);return original(*args,**kwargs)
    monkeypatch.setattr(records,'require_scene_continuity_acceptance',semantic)
    with writable_validation_session(case.run),whole_input_protection():
        admit(case)
        with pytest.raises(OSError):path.write_text('{"changed":true}')
        case.store.write('allowed.json',{'allowed':True})
    path.write_text('{"after_close":true}')
    with pytest.raises(ValueError):case.store.verify_global()


@pytest.mark.parametrize('status',['pending','failed','legacy','overflow'])
def test_no_ready_source_pin_is_acquired_on_nonready_or_overflow(media_guard_case,monkeypatch,status):
    from video_ai.runtime import scene_continuity_records as records,_continuity_byte_guard as proof
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime.verification import writable_validation_session,whole_input_protection
    case=media_guard_case;path=case.run/'production/scene-continuity/not-admitted.json'
    path.parent.mkdir(parents=True);path.write_text('{}')
    original=records.require_scene_continuity_acceptance
    def semantic(*args,**kwargs):hash_file(path);return original(*args,**kwargs)
    monkeypatch.setattr(records,'require_scene_continuity_acceptance',semantic)
    if status=='overflow':
        capture=proof.capture_reads;monkeypatch.setattr(proof,'capture_reads',lambda:capture(maximum_files=1))
    else:case.status[0]=status
    with writable_validation_session(case.run),whole_input_protection():
        if status in ('pending','failed'):
            with pytest.raises(ValueError):admit(case)
        else:admit(case)
        path.write_text('{"still_writable":true}')
