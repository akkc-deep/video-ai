"""Small offline admission fixture: no services, inference, decoding or rendering."""
from copy import deepcopy
from collections import Counter
from contextlib import nullcontext,ExitStack
from datetime import datetime, timezone
from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import pytest

from video_ai.planning.production_scenes import canonical_digest
from video_ai.runtime import production_scene_clips as clips, scene_clip_records as clip_records
from video_ai.runtime import scene_revision_records as revisions, _scene_revision_readers as readers
from video_ai.runtime import _scene_revision_origins as origins, production_inputs
from video_ai.runtime.production_state import RunLock, ProductionRefused
from unit.test_scene_clip_observations import authored, build_observation_template
from unit.test_scene_comfy_transactions import transaction, Client


@pytest.fixture(autouse=True)
def benchmark_baseline():
    """Load the saved working baseline only in an isolated benchmark process."""
    import os
    baseline=os.environ.get('REVIEW_ADMISSION_BASELINE_DIR')
    if not baseline: return
    import importlib
    for name in ('_continuity_byte_guard','scene_revision_records','image_selection_records',
                 '_scene_revision_readers','_scene_revision_origins','reference_image_records',
                 'scene_clip_records','scene_comfy_transactions','production_scene_clips'):
        module=importlib.import_module('video_ai.runtime.'+name)
        path=Path(baseline)/(name+'.py')
        exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    for name in ('review_admission_batch','_review_snapshot'):
        clips.__dict__.pop(name,None)


@pytest.fixture
def admission_fixture(runtime_run, monkeypatch):
    run, _, paths = runtime_run
    @dataclass
    class Config:
        raw: dict
    frozen = SimpleNamespace(options={'run_id': run.name, 'script_path': str(run/'production/script.txt'),
                                      'model_stamps': {}}, config=Config(raw={}))
    counts = Counter()
    store = clip_records.SceneClipStore(frozen, run, paths=paths,
        clip_ids=[f'scene_{i:04d}_clip_0001' for i in range(1, 7)])
    def artifact(name):
        return store.artifact(store.write_bytes(name, ('synthetic offline '+name).encode()))
    context = dict(frozen=frozen, store=store, inputs={'visual_bible_sha256':'a'*64}, rows=[], plan={'scenes':[]})
    observations = []
    with RunLock(run) as held:
        store.lock = held
        upstream = artifact('fixture-upstream.json')
        store.guard_paths[upstream['path']] = upstream
        store.write('inputs.json', {'visual_bible_sha256':'a'*64})
        for i in range(1, 7):
            sid = f'scene_{i:04d}'; cid = sid+'_clip_0001'
            selected = dict(scene_id=sid, candidate_id='candidate_0001', **artifact(cid+'/selected.png'))
            request = dict(inputs_sha256=canonical_digest(context['inputs']), scene_id=sid, clip_id=cid,
                           selected_image=selected, comparison_images=[], parent=None)
            clip = dict(schema_version=2, production_strategy='paragraph_jimeng_v1', run_id=run.name,
                scene_id=sid, clip_id=cid, request_sha256=canonical_digest(request),
                generated=artifact(cid+'/generated.mp4'), source=artifact(cid+'/source.mp4'),
                created_at='2026-10-19T10:00:00+00:00')
            mapping = dict(retained_frames=1); last = dict(image=artifact(cid+'/frame_000001.png'))
            template = build_observation_template(frozen, clip, request, mapping, last, None)
            record = dict(clip=clip, request=request, mapping=mapping, last_frame=last,
                          template=template, accepted=None, rejected=None)
            store.write(cid+'/fixture-record.json', record)
            store.write(cid+'/observation-template.json', template)
            value = authored(template)
            path = run/(cid+'-authored.json'); path.write_text(json.dumps(value), encoding='utf-8')
            observations.append(path)
            context['rows'].append(dict(budget=dict(scene_id=sid, clip_id=cid)))
            context['plan']['scenes'].append(dict(scene_id=sid))
        def validate(context, row, parent=None):
            counts['validate_clip'] += 1
            folder = store.clip_dir(row['budget']['clip_id'])
            record = store.read(folder/'fixture-record.json')
            stored_template=store.read(folder/'observation-template.json')
            if stored_template is not None:
                clip_records.equal(stored_template,record['template'],'observation template')
            record['accepted'] = store.read(folder/'observation-accepted.json')
            record['rejected'] = store.read(folder/'observation-rejected.json')
            # Mirrors the real reader's complete immutable original bindings.
            for name in ('generated','source'):
                store.validate_artifact(record['clip'][name])
            clip_records.scan_observation_sources(store, folder, record['template'],
                record['clip']['created_at'], now=datetime.now(timezone.utc))
            return record
        monkeypatch.setattr(clip_records, 'validate_clip', validate)
        monkeypatch.setattr(clips, 'validate_clip', validate)
        monkeypatch.setattr('video_ai.runtime.scene_continuity_records.load_continuity_policy', lambda f: None)
        monkeypatch.setattr(clips, 'complete_value', lambda ctx, records: {'clips':sorted(records)})
        original = clips.collect_progress
        def collect(*a, **kw):
            counts['collect_progress'] += 1
            return original(*a, **kw)
        monkeypatch.setattr(clips, 'collect_progress', collect)
        yield SimpleNamespace(context=context, paths=observations, counts=counts, store=store)


def test_batch_uses_one_global_progress_scan(admission_fixture):
    f = admission_fixture
    batch = getattr(clips, 'review_admission_batch', lambda context: nullcontext())
    with batch(f.context):
        for path in f.paths[:3]:
            result = clips._consume(f.context, path)
            assert result.status == 'awaiting_continuity_review'
    assert f.counts['collect_progress'] == 1
    assert f.counts['validate_clip'] <= 15


def test_inherited_clip_uses_admitted_source_frozen(tmp_path, monkeypatch):
    source = object(); frozen = SimpleNamespace(options={'script_path':str(tmp_path/'production/script.txt')})
    proof = {'source_run':tmp_path/'source', 'source_frozen':source,
             'imports':{'clip:c':({'local_artifacts':[]}, {})},
             'guard':SimpleNamespace(verify_frozen=lambda *a:None, verify_captured_bytes=lambda:None, register=lambda *a:None)}
    monkeypatch.setattr(readers, 'proof_for', lambda *a, **kw: proof)
    monkeypatch.setattr(production_inputs, 'load_frozen_inputs',
        lambda *a: pytest.fail('already admitted source must not reload'))
    monkeypatch.setattr(origins, 'source_clip_record', lambda f, key: {'clip':{'clip_id':key}, 'request':{}} if f is source else None)
    monkeypatch.setattr(readers, 'require_revision_import', lambda *a, **kw: {'clip_id':'c'})
    assert readers.inherited_clip_record(frozen, 'c')['clip']['clip_id'] == 'c'


@pytest.mark.parametrize('mutation', ['bytes','replace','add','remove','absent'])
def test_semantic_cache_keeps_complete_dependency_guards(tmp_path, mutation):
    import os
    from video_ai.runtime._continuity_byte_guard import capture_reads, observe_absence
    path = tmp_path/'source.json'; path.write_bytes(b'original')
    absent = tmp_path/'missing.bin'; calls = []
    def read():
        calls.append(1)
        revisions.artifact(path, root=tmp_path)
        revisions.revision_inventory(tmp_path, root=tmp_path)
        observe_absence(absent)
        return {'value':[]}
    with pytest.raises((ValueError, OSError)):
        with revisions.revision_artifact_batch():
            value = revisions.revision_cached_read('fixture', 'key', read)
            value['value'].append('caller mutation')
            with capture_reads() as capture:
                assert revisions.revision_cached_read('fixture', 'key', read) == {'value':[]}
            assert capture.finish().file_count == 1
            assert capture.finish().inventory_count == 1
            assert capture.finish().absence_count == 1
            assert calls == [1]
            old = path.stat()
            if mutation == 'bytes':
                path.write_bytes(b'modified'); os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
            elif mutation == 'replace':
                replacement = tmp_path/'replacement.bin'; replacement.write_bytes(b'original')
                os.replace(replacement, path); os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
            elif mutation == 'add': (tmp_path/'new.json').write_bytes(b'new')
            elif mutation == 'remove': path.unlink()
            else: absent.write_bytes(b'appeared')
            revisions.revision_cached_read('fixture', 'key', read)


def test_semantic_cache_never_crosses_scope_or_thread(tmp_path):
    from contextvars import copy_context
    from concurrent.futures import ThreadPoolExecutor
    calls = []
    def read(): calls.append(1); return {'value':len(calls)}
    def cached(): return revisions.revision_cached_read('fixture', 'key', read)
    with revisions.revision_artifact_batch():
        assert cached() == cached()
        copied = copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(copied.run, cached).result() != cached()
    assert copied.run(cached) != {'value':1}
    assert len(calls) == 3


@pytest.mark.parametrize('point', ['before_batch','observation-original','observation-receipt'])
def test_pause_stops_at_atomic_review_boundaries(admission_fixture, monkeypatch, point):
    f=admission_fixture; paused=[point=='before_batch']; notices=[]
    def boundary(name):
        if name==point: paused[0]=True
    monkeypatch.setattr(clips,'boundary',boundary)
    with pytest.raises(KeyboardInterrupt):
        with clips.review_admission_batch(f.context,stop_requested=lambda:paused[0],notify=notices.append):
            for path in f.paths[:2]: clips._consume(f.context,path)
    first=f.store.clip_dir('scene_0001_clip_0001')
    assert (first/'observation-accepted.json').exists() == (point=='observation-receipt')
    assert len(list((first/'observations').glob('*.json'))) == (0 if point=='before_batch' else 1)
    assert not (f.store.clip_dir('scene_0002_clip_0001')/'observation-accepted.json').exists()


def test_unchanged_notifications_are_deduplicated(admission_fixture):
    f=admission_fixture; notices=[]
    with clips.review_admission_batch(f.context,notify=notices.append) as batch:
        batch.snapshot(); batch.snapshot()
        clips._consume(f.context,f.paths[0]); clips._consume(f.context,f.paths[0])
        clips._consume(f.context,f.paths[1])
    assert [n['phase'] for n in notices] == ['review_preparation','review_receiving','review_receiving','review_receiving']
    assert [n['received'] for n in notices if n['clip_id']] == [1,2]


def test_pause_during_shared_ancestor_read_is_cooperative(tmp_path):
    from video_ai.runtime.scene_review_control import review_admission_control
    frozen=SimpleNamespace(options={'script_path':str(tmp_path/'production/script.txt')})
    guard=revisions.RevisionGuard(frozen)
    for i in range(3):
        path=tmp_path/f'{i}.json';path.write_bytes(b'original');guard.capture(path,root=tmp_path)
    with pytest.raises(KeyboardInterrupt):
        with review_admission_control(stop_requested=lambda:True):
            guard.verify_captured_bytes()


def test_paused_continuation_never_enters_preparation(admission_fixture, monkeypatch):
    import importlib.util
    f=admission_fixture
    monkeypatch.setenv('VOYAGER2_RUN_DIR',str(f.store.run_dir))
    path=Path(__file__).resolve().parents[2]/'.tools/resume_voyager2_after_reboot.py'
    spec=importlib.util.spec_from_file_location('paused_continuation_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.STOP=f.store.run_dir/'stop.json'
    module.STOP.write_text(json.dumps(dict(run_id=f.store.run_dir.name,token=f.store.lock.owner['token'])),encoding='utf-8')
    monkeypatch.setattr(module,'_main',lambda:pytest.fail('paused continuation started preparation'))
    with pytest.raises(SystemExit) as exc: module.main()
    assert exc.value.code==130


@pytest.mark.parametrize('mutation',['bytes','replace','new_observation','new_descendant','context'])
def test_warm_reviews_reject_changed_scene_dependencies(admission_fixture,monkeypatch,mutation):
    from video_ai.runtime import verification
    import os
    # Exercise the strict unretained fallback as well as native protection tests.
    def unretained(window,path,compute):
        with path.open('rb') as stream: return compute(stream,path)
    monkeypatch.setattr(verification._WholeInputWindow,'hash',unretained)
    f=admission_fixture
    with pytest.raises((ValueError,OSError)):
        with clips.review_admission_batch(f.context) as batch:
            clips._consume(f.context,f.paths[0])
            path=f.store.clip_dir('scene_0003_clip_0001')/'fixture-record.json'
            old=path.stat()
            if mutation=='bytes':
                raw=path.read_bytes();changed=raw.replace(b'2026-10-19',b'2026-10-18')
                assert changed!=raw
                path.write_bytes(changed)
                os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
            elif mutation=='replace':
                replacement=path.with_suffix('.replacement');replacement.write_bytes(path.read_bytes())
                os.replace(replacement,path);os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
            elif mutation=='new_observation':
                target=path.parent/'observations/unexpected.json';target.parent.mkdir(exist_ok=True)
                target.write_text('{}',encoding='utf-8')
            elif mutation=='new_descendant':
                # Previously absent receipt is part of the captured dependency set.
                (path.parent/'observation-accepted.json').write_text('{}',encoding='utf-8')
            else: f.context['rows'][0]['parameters']={'seed':123}
            clips._consume(f.context,f.paths[1])
    assert not (f.store.clip_dir('scene_0002_clip_0001')/'observation-accepted.json').exists()


def test_cached_inherited_records_recheck_row_and_parent(admission_fixture,monkeypatch):
    from review_admission_helpers import add_shared_sources
    f=add_shared_sources(admission_fixture,monkeypatch)
    frozen=f.context['frozen'];row=f.context['rows'][-1];key=row['budget']['clip_id']
    with revisions.revision_artifact_batch():
        original=readers.inherited_clip_record(frozen,key,row=row)
        original['request']['parameters']['seed']='caller mutation'
        assert readers.inherited_clip_record(frozen,key,row=row)['request']['parameters']=={}
        with pytest.raises(ProductionRefused,match='parameters'):
            readers.inherited_clip_record(frozen,key,row=dict(row,parameters={'seed':1}))
        source=deepcopy(original);source['request']['parameters']={};source['request']['parent']={'clip_id':'expected_parent'}
        monkeypatch.setattr(origins,'source_clip_record',lambda *a:deepcopy(source))
        with pytest.raises(ProductionRefused,match='parent'):
            readers.inherited_clip_record(frozen,key,row=row,parent={'clip':{'clip_id':'different_parent'}})


def test_warm_batch_rejects_new_owned_evidence_competing_with_import(admission_fixture,monkeypatch):
    from review_admission_helpers import add_shared_sources
    f=add_shared_sources(admission_fixture,monkeypatch)
    with pytest.raises((ValueError,OSError)):
        with clips.review_admission_batch(f.context):
            clips._consume(f.context,f.paths[0])
            folder=f.store.clip_dir('inherited_0002_clip_0001')
            folder.mkdir();(folder/'clip.json').write_text('{}',encoding='utf-8')
            clips._consume(f.context,f.paths[1])
    assert not (f.store.clip_dir('scene_0002_clip_0001')/'observation-accepted.json').exists()


@pytest.mark.parametrize('when',['service','capability'])
def test_pause_after_service_or_capability_never_submits(transaction,monkeypatch,when):
    from video_ai.runtime.scene_review_control import review_admission_control
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    store,request,graph,template=transaction;client=Client(store,request,graph);paused=[False]
    def ensure():
        if when=='service': paused[0]=True
    original=client.object_info
    def info(**kw):
        value=original(**kw)
        if when=='capability': paused[0]=True
        return value
    monkeypatch.setattr(client,'object_info',info)
    with pytest.raises(KeyboardInterrupt):
        with review_admission_control(stop_requested=lambda:paused[0]):
            recover_or_submit_scene_clip(store,request,graph,client=client,template=template,
                ensure_service=ensure,logger=None,timeout=1)
    assert client.posts==0


def test_new_wrong_template_for_accepted_scene_is_rejected(admission_fixture):
    f=admission_fixture;path=f.store.clip_dir('scene_0001_clip_0001')/'observation-template.json'
    path.unlink()
    with pytest.raises((ValueError,OSError)):
        with clips.review_admission_batch(f.context):
            clips._consume(f.context,f.paths[0])
            assert not path.exists()
            path.write_text('{}',encoding='utf-8')
            clips._consume(f.context,f.paths[1])
    assert not (f.store.clip_dir('scene_0002_clip_0001')/'observation-accepted.json').exists()


def test_receiver_can_materialize_exact_pending_template(admission_fixture):
    f=admission_fixture;path=f.store.clip_dir('scene_0006_clip_0001')/'observation-template.json'
    path.unlink()
    with clips.review_admission_batch(f.context):
        clips._consume(f.context,f.paths[0])
        assert path.exists()
        clips._consume(f.context,f.paths[1])


@pytest.mark.parametrize('existing_empty',[False,True])
def test_reference_cache_observes_nonjson_request_evidence(tmp_path,monkeypatch,existing_empty):
    from video_ai.runtime import reference_image_records as refs
    root=tmp_path/'production/jimeng/s';root.mkdir(parents=True)
    folder=root/'request_99'
    if existing_empty: folder.mkdir()
    monkeypatch.setattr('video_ai.runtime.scene_image_prompts.effective_image_prompt',lambda *a:'prompt')
    monkeypatch.setattr('video_ai.runtime.reference_visual_prompt.compact_reference_prompt',lambda *a:'prompt')
    monkeypatch.setattr(refs,'build_reference_prompt',lambda *a:'prompt')
    monkeypatch.setattr(refs.images,'_run',lambda *a:tmp_path)
    monkeypatch.setattr(refs,'load_reference_settings',lambda *a:{'model_settings':{}})
    monkeypatch.setattr(refs,'parse_image_generation',lambda *a:SimpleNamespace(candidates_per_scene=1))
    def read(): return refs.resolve_reference_prompt(None,{'scene_id':'s'}, {},{'max_prompt_bytes':100})
    with pytest.raises((ValueError,OSError)):
        with revisions.revision_artifact_batch():
            assert revisions.revision_cached_read('reference_test','key',read)=='prompt'
            folder.mkdir(exist_ok=True);(folder/'unexpected.bin').write_bytes(b'unexpected')
            revisions.revision_cached_read('reference_test','key',read)


def test_byte_proof_cache_verification_stops_before_full_scan(tmp_path,monkeypatch):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime.scene_review_control import review_admission_control
    from video_ai.runtime import manifest
    path=tmp_path/'original.json';path.write_text('{}')
    with capture_reads() as capture: manifest.hash_file(path)
    monkeypatch.setattr(manifest,'hash_file',lambda *a:pytest.fail('continued expensive verification after pause'))
    with pytest.raises(KeyboardInterrupt):
        with review_admission_control(stop_requested=lambda:True): capture.finish().verify()


def test_cached_source_images_reject_new_owned_evidence(tmp_path,monkeypatch):
    from video_ai.runtime import image_selection_records as images
    frozen=SimpleNamespace(options={'script_path':str(tmp_path/'production/script.txt')})
    canonical=tmp_path/'production/jimeng/s/candidates.json'
    proof={'imports':{'image:s':({'view_artifact':{'path':str(tmp_path/'view.json')}},{})}}
    monkeypatch.setattr(origins,'inherited',lambda *a:{'candidates':[]})
    monkeypatch.setattr(revisions,'require_scene_revision',lambda *a:proof)
    def read(): return images._candidates(frozen,{'scene_id':'s'},canonical)
    with pytest.raises((ValueError,OSError)):
        with revisions.revision_artifact_batch():
            revisions.revision_cached_read('image_test','key',read)
            canonical.parent.mkdir(parents=True);canonical.write_text('{}')
            revisions.revision_cached_read('image_test','key',read)


def test_cached_native_import_rejects_new_owned_chain(tmp_path,monkeypatch):
    frozen=SimpleNamespace(options={'script_path':str(tmp_path/'production/script.txt'),'scene_revision':{}},
        config=SimpleNamespace(raw={'scene_rendering':{'mode':'temporal_extension_v1'}}))
    monkeypatch.setattr(readers,'inherited_clip_record',lambda *a:{'clip':'fixture'})
    def read(): return origins._source_clip_record(frozen,'scene_0001_clip_0001')
    with pytest.raises((ValueError,OSError)):
        with revisions.revision_artifact_batch():
            revisions.revision_cached_read('native_test','key',read)
            path=tmp_path/'production/scene-clips/chains/scene_0001/result.json'
            path.parent.mkdir(parents=True);path.write_text('{}')
            revisions.revision_cached_read('native_test','key',read)


def test_review_snapshot_rejects_foreign_thread_and_closed_scope(admission_fixture):
    from contextvars import copy_context
    from concurrent.futures import ThreadPoolExecutor
    f=admission_fixture
    with clips.review_admission_batch(f.context) as batch:
        batch.snapshot();copied=copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(ProductionRefused,match='owning protected scope'):
                pool.submit(copied.run,batch.snapshot).result()
    with pytest.raises(ProductionRefused,match='owning protected scope'): copied.run(batch.snapshot)


def test_temporal_batch_retains_original_consumer(admission_fixture,monkeypatch):
    f=admission_fixture;f.context['execution']={'mode':'temporal_extension_v1'};calls=[]
    monkeypatch.setattr(clips,'_entry',lambda *a,operation,**kw:operation(f.context))
    monkeypatch.setattr(clips,'_consume',lambda context,path:calls.append(path) or SimpleNamespace(status='awaiting_continuity_review'))
    monkeypatch.setattr(clips,'review_admission_batch',lambda *a,**kw:pytest.fail('temporal path changed admission protocol'))
    result=clips.consume_scene_clip_observations(f.context['frozen'],None,None,f.paths[:2],paths=None,logger=None)
    assert calls==f.paths[:2] and result.status=='awaiting_continuity_review'


def test_fixture_measurement(admission_fixture, monkeypatch):
    """Opt-in report; same fixture and measurement stages before/after changes."""
    import os
    output = os.environ.get('REVIEW_ADMISSION_BENCHMARK')
    if not output:
        pytest.skip('representative measurement is opt-in')
    from review_admission_helpers import add_shared_sources
    f = add_shared_sources(admission_fixture,monkeypatch); stages = {}
    def measure(name, operation):
        previous = f.counts.copy(); started = perf_counter()
        value = operation()
        stages[name] = dict(seconds=perf_counter()-started, calls=dict(f.counts-previous))
        return value
    # Baseline has no batch scope; optimized implementation prepares lazily.
    from video_ai.runtime.verification import whole_input_protection
    batch = getattr(clips, 'review_admission_batch', lambda context: nullcontext())
    with ExitStack() as stack:
        def prepare():
            # Match the existing public review API: both versions retain the
            # same mandatory input protection, including baseline _consume.
            stack.enter_context(whole_input_protection())
            stack.enter_context(batch(f.context))
            return clips._review_snapshot(f.context) if hasattr(clips,'_review_snapshot') else clips.collect_progress(f.context)
        measure('cold_preparation',prepare)
        measure('first_receive', lambda: clips._consume(f.context, f.paths[0]))
        measure('warm_batch_3', lambda: [clips._consume(f.context, p) for p in f.paths[1:4]])
        measure('final_boundary',stack.close)
    Path(output).write_text(json.dumps({'fixture':'six pending synthetic clips plus two accepted clips across three inherited layers and a shared ancestor DAG; real observation validator, store, progress, provenance schema and receipt writes; leaf media/plan semantics stubbed; no production writes',
                                      'stages':stages}, indent=2)+'\n', encoding='utf-8')
