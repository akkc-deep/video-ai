"""Bounded runtime records; evidence fixtures are protocol tests, never visual proof."""
from types import SimpleNamespace
from pathlib import Path
import json
import hashlib
import base64

import pytest


def test_explicit_null_rendering_is_not_a_historical_fallback():
    from video_ai.runtime.scene_execution_records import rendering_mode
    frozen=SimpleNamespace(config=SimpleNamespace(raw={'scene_rendering':None}))
    with pytest.raises(ValueError): rendering_mode(frozen)


@pytest.mark.parametrize('mode',[None,'segmented_v1','whole_scene_v1'])
def test_partial_config_dispatch_uses_frozen_snapshot_without_dropping_mode(mode):
    from video_ai.runtime.scene_execution_records import rendering_mode
    raw={}
    if mode is not None:
        settings=dict(mode=mode,prompt_policy='visual_v2',prompt_contract='D:/VideoSi/prompt.json')
        if mode=='whole_scene_v1':
            settings['whole_scene_evidence']='D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/final-assessment.json'
        raw['scene_rendering']=settings
    frozen=SimpleNamespace(config=SimpleNamespace(production_strategy='paragraph_jimeng_v1'),
        options={'config_snapshot':{'raw':raw}})
    assert rendering_mode(frozen)==mode


def test_partial_config_dispatch_does_not_hide_null_in_frozen_snapshot():
    from video_ai.runtime.scene_execution_records import rendering_mode
    frozen=SimpleNamespace(config=SimpleNamespace(production_strategy='paragraph_jimeng_v1'),
        options={'config_snapshot':{'raw':{'scene_rendering':None}}})
    with pytest.raises(ValueError):rendering_mode(frozen)


def fixture_evidence(root,monkeypatch):
    """Tiny protocol-only media/models, but full 321/1874 inventories and links.

    Integration tests may separately replace verify_current_environment when
    their production config uses different fixture model/tool paths.
    """
    import video_ai.runtime._whole_scene_admission as admission
    root=Path(root);root.mkdir(parents=True)
    def put(relative,value):
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(value if isinstance(value,bytes) else (json.dumps(value,ensure_ascii=False)+'\n').encode())
        return ident(path)
    def ident(path):
        raw=Path(path).read_bytes()
        return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),mtime_ns=Path(path).stat().st_mtime_ns)
    def media(frames,pixel='yuv420p'):
        return dict(width=768,height=432,fps=16,frames=frames,duration=frames/16,pixel_format=pixel)
    graph=json.loads((Path(__file__).parents[2]/'workflows/wan22_i2v_14b_api.json').read_text(encoding='utf-8'))
    graph['129:98']['inputs'].update(width=768,height=432,length=321,batch_size=1)
    graph['97']['inputs']['image']='start.png';graph['108']['inputs']['filename_prefix']='candidate'
    graph['129:93']['inputs']['text']='fixture_only'
    graph_id=put('graph.json',graph)
    source=put('source/input.json',{'fixture_only':True})
    source_inventory=put('source-inventory.json',[source])
    dependencies={}
    for role in ('start','selected','prompt_contract','model/wan_high','model/wan_low','model/text_encoder','model/vae','tool/comfy_python','tool/ffmpeg','tool/ffprobe'):
        dependencies[role]=put('dependencies/'+role,b'fixture_only')
    original=put('comfy/tiny.py',b'# Comfy fixture only\n')
    product=put('historical/tiny.py',b'# historical product fixture only\n')
    dependencies['code/comfy/tiny.py']=original;dependencies['code/video_ai/tiny.py']=product
    archived=[put('software/comfy/tiny.py',b'# Comfy fixture only\n'),put('software/video_ai/tiny.py',b'# historical product fixture only\n')]
    case=dict(schema_version=1,algorithm='wan22_whole_scene_experiment_v1',source_run=str(root/'source'),
        budget=dict(requested_frames=321,retained_frames=320,source_start=0,source_end=320,fps=16,duration_seconds=20),
        graph=graph_id,source_inventory=source_inventory,dependencies=dependencies,
        runtime=dict(tools=dict(comfy_root=str(root/'comfy')),model_root=str(root/'models')))
    case_id=put('case.json',case)
    put('prepared.json',dict(case_sha256=case_id['sha256'],start=put('input/start.png',b'fixture_only'),
        prompt=put('prompt-contract.json',b'fixture_only'),software=archived))
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    frames=[put(f'native-frames/frame_{i:06d}.png',png) for i in range(321)]
    native=put('native-frame-identities.json',frames)
    mapping=put('mapping.json',dict(requested_frames=321,retained_frames=320,source_start=0,source_end=320,
        discarded_source_frames=[320],frames=[dict(review_frame=i,source_frame=i,pts=f'{i}/16') for i in range(320)]))
    generated=put('output/candidate_00001_.mp4',b'fixture_only_generated')
    lossless=put('review.mp4',b'fixture_only_lossless')
    compatible=put('review-playback.mp4',b'fixture_only_compatible')
    playback=put('playback-review.json',dict(video=media(320),source_frame_range=[0,320],lossless=False,
        generated_identity=generated,lossless_review_identity=lossless,mapping_identity=mapping,playback_identity=compatible,
        ffmpeg_identity=dependencies['tool/ffmpeg'],probe_identity=put('probe.json',{}),
        producer_identity=put('producer.py',b'# playback producer fixture only\n')))
    sample=dict(pid=7,verified=True,gpu=[dict(returncode=0,stdout='NVIDIA GeForce RTX 5090 D v2, 24455, 21657, 2379, 100\n'),
        dict(returncode=0,stdout='7, [N/A]\n')],memory=dict(system_used_bytes=33298898944,process_rss_bytes={'7':16056832000}))
    for i in range(1874):put(f'resources/{i:04d}.json',sample)
    summary=put('evidence-summary.json',dict(resource_samples=1874,verified_samples=1874,peak_total_gpu_used_mib=21657,
        minimum_gpu_free_mib=2379,peak_owned_service_rss_bytes=16056832000,peak_system_used_bytes=33298898944,
        raw_frames=321,review_frames=320,review_duration=20,native_png_count=321,mapping_count=320,rgb_preserved=True,
        review_sha256=lossless['sha256'],execution_error_lines=[],source_inventory_count=1,dependency_count=len(dependencies),
        post_count=1,post_routes=['http://127.0.0.1:8198/prompt']))
    client='fixture_client';prompt_id='fixture_prompt'
    history=dict(prompt=[0,prompt_id,graph,dict(client_id=client)],status=dict(completed=True,status_str='success',
        messages=[['execution_start',dict(timestamp=1000)],['execution_success',dict(timestamp=3799752)]]))
    submission=dict(status='completed',prompt_id=prompt_id,history=history)
    put('intent.json',dict(case_sha256=case_id['sha256'],graph_sha256=graph_id['sha256'],client_id=client))
    put('submission-result.json',submission)
    put('http/post.request.json',dict(method='POST',url='http://127.0.0.1:8198/prompt',json_body=dict(prompt=graph,client_id=client)))
    put('http/post.response.json',dict(status=200,error=None,truncated=False))
    put('http/post.body',dict(prompt_id=prompt_id,node_errors={}))
    result=put('result.json',dict(technical='passed',status='awaiting_video_observation',full_video_observation='unverified',source_unchanged=True,
        submission=submission,media=dict(generated=media(321),review=media(320,'gbrp'),generated_identity=generated,
            review_identity=lossless,mapping_identity=mapping,native_manifest_identity=native,rgb_preserved=True)))
    observation=put('user-observation.json',dict(reviewer='user',review_method='human_video',verdict='passed',
        feedback_quote='fixture only; no real observation',feedback_source='fixture_only',coverage=dict(frames=[0,320],duration_seconds=20),
        checks={k:dict(verdict='passed') for k in ('subject_color','lighting','composition','motion')},
        generated_identity=generated,lossless_review_identity=lossless,mapping_identity=mapping,playback_identity=compatible,
        playback_receipt_identity=playback))
    final=put('final-assessment.json',dict(task_id='VCO-05',outcome='authorized_first_case_accepted',technical='passed',resource_evidence='passed',
        full_video_observation='passed',vco07_first_case_evidence_ready=True,production_mode_enabled=False,production_eligible=False,
        scope=dict(width=768,height=432,fps=16,retained_frames=320,duration_seconds=20,cross_subject='not_verified_not_authorized',
            longer_duration='not_verified',multi_window='not_verified'),observation=observation,technical_result=result,evidence_summary=summary))
    put('completion-check.json',dict(assessment=final,user_observation=observation,verified=True,production_mode_enabled=False))
    monkeypatch.setattr(admission,'PINNED_ROOT',root)
    monkeypatch.setattr(admission,'PINNED_SHA256',final['sha256'])
    monkeypatch.setattr(admission,'PINNED_CASE_SHA256',case_id['sha256'])
    monkeypatch.setattr(admission,'PINNED_PREPARED_SHA256',ident(root/'prepared.json')['sha256'])
    from video_ai.planning.production_scenes import canonical_digest
    for folder,constant in [('resources','PINNED_RESOURCE_INVENTORY_SHA256'),('http','PINNED_HTTP_INVENTORY_SHA256')]:
        rows=[]
        for p in sorted((root/folder).rglob('*')):
            if p.is_file():rows.append(dict(path=p.relative_to(root/folder).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        monkeypatch.setattr(admission,constant,canonical_digest(rows))
    return Path(final['path'])


def execution_fixture(run, mode='segmented_v1'):
    return SimpleNamespace(config=SimpleNamespace(raw={'scene_rendering': dict(mode=mode,
        prompt_policy='visual_v2', prompt_contract='prompt.json')}), options=dict(run_id=run.name,
        script_path=str(run/'production/script.txt'), config_snapshot=dict(raw={}),
        voice_snapshot=dict(raw={}), image_generation={}, model_stamps={}, workflow_snapshots={},
        execution_policy=dict(input_identities={'scene_video_prompts': dict(path=str(run/'prompt.json'),bytes=1,sha256='a'*64)})))


def plan_fixture():
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    p=dict(total_frames=320,scenes=[dict(scene_id='scene_0001',start_frame=0,end_frame=320)])
    p['clips']=derive_scene_execution_clips(p,dict(total_frames=320),mode='whole_scene_v1')
    return p,dict(total_frames=320)


def test_readonly_missing_explicit_budget_never_writes(runtime_run):
    from video_ai.runtime.scene_execution_records import load_scene_execution
    run,_,_=runtime_run
    frozen=execution_fixture(run)
    plan,timeline=plan_fixture()
    before=set(run.rglob('*'))
    with pytest.raises(ValueError,match='budget.*missing'):
        load_scene_execution(frozen,plan,timeline)
    assert set(run.rglob('*'))==before


def test_explicit_budget_requires_owned_run_lock_and_revalidates(runtime_run,monkeypatch):
    from video_ai.runtime.scene_execution_records import ensure_scene_execution,load_scene_execution,execution_artifact
    from video_ai.runtime.production_state import RunLock
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    run,_,_=runtime_run
    frozen=execution_fixture(run)
    plan,timeline=plan_fixture()
    plan['clips']=[dict(plan['clips'][0],retained_frames=320)]
    # A genuine segmented semantic plan is supplied by the pure module fixtures.
    monkeypatch.setattr('video_ai.runtime.scene_execution_records._identity',lambda f: dict(
        run_id=run.name,mode='whole_scene_v1',rendering_identity_sha256='b'*64,
        admission=dict(path=str(run/'evidence.json'),bytes=1,sha256='c'*64)))
    frozen.config.raw['scene_rendering']['mode']='whole_scene_v1'
    frozen.config.raw['scene_rendering']['whole_scene_evidence']=str(run/'evidence.json')
    with pytest.raises(ValueError,match='lock'):
        ensure_scene_execution(frozen,plan,timeline,lock=RunLock(run))
    with RunLock(run) as lock:
        value=ensure_scene_execution(frozen,plan,timeline,lock=lock)
        assert value['clips']==derive_scene_execution_clips(plan,timeline,mode='whole_scene_v1')
        assert load_scene_execution(frozen,plan,timeline)==value
        assert execution_artifact(frozen)['path']==str(run/'production/scene-rendering/execution-budget.json')
    path=Path(execution_artifact(frozen)['path'])
    bad=dict(value,mode='segmented_v1');path.write_text(json.dumps(bad),encoding='utf-8')
    with pytest.raises(ValueError):load_scene_execution(frozen,plan,timeline)


def test_evidence_rejects_unpinned_root(tmp_path):
    from video_ai.runtime.scene_execution_records import load_whole_scene_evidence
    path=tmp_path/'final-assessment.json';path.write_text('{"verified":true}',encoding='utf-8')
    with pytest.raises(ValueError,match='accepted evidence'):
        load_whole_scene_evidence(path)


def test_evidence_full_closure_and_archived_product_code(tmp_path,monkeypatch):
    from video_ai.runtime.scene_execution_records import load_whole_scene_evidence
    path=fixture_evidence(tmp_path/'evidence',monkeypatch)
    # Current product Python may change; its historical archive remains exact.
    (path.parent/'historical/tiny.py').write_bytes(b'new product implementation')
    evidence=load_whole_scene_evidence(path)
    paths={v['path'] for v in evidence['artifacts']}
    assert len([p for p in paths if '/resources/' in p.replace('\\','/')])==1874
    assert len([p for p in paths if '/native-frames/' in p.replace('\\','/')])==321
    assert str(path.parent/'historical/tiny.py') not in paths
    assert evidence['assessment']['full_video_observation']=='passed'
    assert len(evidence['inventories'])==6


@pytest.mark.parametrize('relative',[
    'user-observation.json','result.json','mapping.json','native-frames/frame_000007.png',
    'resources/0003.json','software/video_ai/tiny.py','comfy/tiny.py','dependencies/model/wan_high',
    'http/post.body','source/input.json','graph.json'])
def test_evidence_rejects_any_external_byte_drift(tmp_path,monkeypatch,relative):
    from video_ai.runtime.scene_execution_records import load_whole_scene_evidence
    path=fixture_evidence(tmp_path/'evidence',monkeypatch)
    target=path.parent/relative
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError):load_whole_scene_evidence(path)


def test_frozen_closure_roundtrip_and_no_resigning(tmp_path,runtime_run,monkeypatch):
    from video_ai.runtime.scene_execution_records import freeze_whole_scene_evidence,verify_whole_scene_frozen,load_whole_scene_evidence
    import video_ai.runtime.scene_execution_records as records
    path=fixture_evidence(tmp_path/'evidence',monkeypatch)
    run,_,_=runtime_run
    frozen=execution_fixture(run,'whole_scene_v1')
    frozen.config.raw['scene_rendering']['whole_scene_evidence']=str(path)
    monkeypatch.setattr(records,'verify_current_environment',lambda frozen,evidence:None)
    def save(path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    identities=frozen.options['execution_policy']['input_identities']
    freeze_whole_scene_evidence(frozen.config,run,identities,save=save)
    assert Path(identities['whole_scene_evidence']['path']).read_bytes()==path.read_bytes()
    result=verify_whole_scene_frozen(frozen)
    assert result['root']['sha256']==identities['whole_scene_evidence']['sha256']
    assert load_whole_scene_evidence(Path(identities['whole_scene_evidence']['path']))['root']==result['root']
    from video_ai.runtime.paths import create_run
    next_run=create_run(runtime_run[2])
    inherited=execution_fixture(next_run,'whole_scene_v1')
    inherited.config.raw['scene_rendering']['whole_scene_evidence']=identities['whole_scene_evidence']['path']
    inherited_ids=inherited.options['execution_policy']['input_identities']
    freeze_whole_scene_evidence(inherited.config,next_run,inherited_ids,save=save)
    assert verify_whole_scene_frozen(inherited)['root']['sha256']==result['root']['sha256']
    before=Path(identities['whole_scene_evidence_closure']['path']).read_bytes()
    (path.parent/'resources/added.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError):verify_whole_scene_frozen(frozen)
    assert Path(identities['whole_scene_evidence_closure']['path']).read_bytes()==before


def test_json_limits_apply_before_parsing(tmp_path,monkeypatch):
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    import video_ai.runtime._whole_scene_admission as admission
    path=tmp_path/'oversize.json';path.write_bytes(b' '*32)
    monkeypatch.setattr(admission,'JSON_LIMIT',16)
    with pytest.raises(ValueError,match='16 MiB'):EvidenceReader().json(path)
    monkeypatch.setattr(admission,'JSON_LIMIT',64)
    monkeypatch.setattr(admission,'METADATA_LIMIT',16)
    with pytest.raises(ValueError,match='64 MiB'):EvidenceReader().json(path)


def test_legacy_execution_is_in_memory_with_zero_writes(runtime_run):
    from unit.test_scene_execution import fixture
    from video_ai.runtime.scene_execution_records import load_scene_execution,ensure_scene_execution,rendering_mode
    run,_,_=runtime_run
    frozen=execution_fixture(run);frozen.config.raw={}
    plan,timeline=fixture(320)
    before=set(run.rglob('*'))
    assert rendering_mode(frozen) is None
    assert load_scene_execution(frozen,plan,timeline)['clips']==plan['clips']
    assert ensure_scene_execution(frozen,plan,timeline,lock=None)['clips']==plan['clips']
    assert set(run.rglob('*'))==before


def test_owned_exact_temporary_recovers_after_rename_interruption(runtime_run,monkeypatch):
    from unit.test_scene_execution import fixture
    from video_ai.runtime.scene_execution_records import ensure_scene_execution,load_scene_execution
    from video_ai.runtime.production_state import RunLock
    import video_ai.runtime.scene_execution_records as records
    run,_,_=runtime_run;frozen=execution_fixture(run);plan,timeline=fixture(320)
    with RunLock(run) as lock:
        with monkeypatch.context() as patch:
            def interrupted(*args):raise OSError('interrupted rename')
            patch.setattr(records.os,'rename',interrupted)
            with pytest.raises(OSError,match='interrupted'):
                ensure_scene_execution(frozen,plan,timeline,lock=lock)
        temporary=run/'production/scene-rendering'/('execution-budget.'+lock.owner['token']+'.tmp')
        original=temporary.read_bytes()
        with pytest.raises(ValueError,match='budget missing'):load_scene_execution(frozen,plan,timeline)
        assert temporary.read_bytes()==original
        result=ensure_scene_execution(frozen,plan,timeline,lock=lock)
        assert result['mode']=='segmented_v1' and result['clips']==plan['clips']
        assert not temporary.exists()


def test_new_lock_recovers_budget_after_prior_owner_pre_rename_interruption(runtime_run,monkeypatch):
    from unit.test_scene_execution import fixture
    from video_ai.runtime.scene_execution_records import ensure_scene_execution,load_scene_execution
    from video_ai.runtime.production_state import RunLock
    import video_ai.runtime.scene_execution_records as records
    run,_,_=runtime_run;frozen=execution_fixture(run);plan,timeline=fixture(320)
    with RunLock(run) as first:
        with monkeypatch.context() as patch:
            patch.setattr(records.os,'rename',lambda *a:(_ for _ in ()).throw(OSError('fixture pre-rename interruption')))
            with pytest.raises(OSError):ensure_scene_execution(frozen,plan,timeline,lock=first)
        old=run/'production/scene-rendering'/('execution-budget.'+first.owner['token']+'.tmp')
        original=old.read_bytes()
    with RunLock(run) as second:
        assert second.owner['token']!=first.owner['token']
        result=ensure_scene_execution(frozen,plan,timeline,lock=second)
        assert load_scene_execution(frozen,plan,timeline)==result
        assert old.read_bytes()==original
        assert result['clips']==plan['clips']


@pytest.mark.parametrize('kind',['downstream','foreign','partial'])
def test_missing_budget_refuses_downstream_or_unowned_partial_records(runtime_run,kind):
    from unit.test_scene_execution import fixture
    from video_ai.runtime.scene_execution_records import ensure_scene_execution
    from video_ai.runtime.production_state import RunLock
    run,_,_=runtime_run;frozen=execution_fixture(run);plan,timeline=fixture(320)
    with RunLock(run) as lock:
        if kind=='downstream':path=run/'production/scene-clips/inputs.json'
        else:path=run/'production/scene-rendering'/('execution-budget.'+('f'*32 if kind=='foreign' else lock.owner['token'])+'.tmp')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'{')
        before=set(run.rglob('*'))
        with pytest.raises(ValueError):ensure_scene_execution(frozen,plan,timeline,lock=lock)
        assert set(run.rglob('*'))==before and path.read_bytes()==b'{'


def test_explicit_writer_holds_protected_model_bytes_through_nested_calls(tmp_path):
    from video_ai.runtime.scene_execution_records import verified_scene_execution_write
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime.verification import _current
    path=tmp_path/'tiny.safetensors';path.write_bytes(b'fixture_model')
    frozen=SimpleNamespace(config=SimpleNamespace(raw={'scene_rendering':dict(mode='segmented_v1',prompt_policy='visual_v2',prompt_contract='prompts.json')}))
    @verified_scene_execution_write
    def inner(frozen):
        assert _current.get() is not None
        return hash_file(path).sha256
    @verified_scene_execution_write
    def outer(frozen):
        value=hash_file(path).sha256
        assert inner(frozen)==value
        with pytest.raises(PermissionError):path.write_bytes(b'changed_during_writer')
        return value
    assert outer(frozen)==hashlib.sha256(b'fixture_model').hexdigest()
    assert _current.get() is None
    path.write_bytes(b'changed_after_writer')
    @verified_scene_execution_write
    def legacy(frozen):
        hash_file(path)
        assert _current.get() is None
        path.write_bytes(b'legacy_has_no_extended_read_window')
    legacy(SimpleNamespace(config=SimpleNamespace(raw={})))


@pytest.mark.parametrize('target_kind',['external','frozen_root','frozen_closure','inventory'])
def test_writer_reuses_authenticated_semantics_but_rechecks_every_captured_byte(tmp_path,runtime_run,monkeypatch,target_kind):
    import video_ai.runtime.scene_execution_records as records
    from video_ai.runtime.production_state import ProductionRefused
    path=fixture_evidence(tmp_path/'evidence',monkeypatch)
    run,_,_=runtime_run
    frozen=execution_fixture(run,'whole_scene_v1')
    frozen.config.raw['scene_rendering']['whole_scene_evidence']=str(path)
    monkeypatch.setattr(records,'verify_current_environment',lambda frozen,evidence:None)
    def save(path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    records.freeze_whole_scene_evidence(frozen.config,run,frozen.options['execution_policy']['input_identities'],save=save)
    semantic_calls=[]
    original_load=records.load_evidence
    def counting_load(*args,**kwargs):
        semantic_calls.append(args[0])
        return original_load(*args,**kwargs)
    monkeypatch.setattr(records,'load_evidence',counting_load)
    @records.verified_scene_execution_write
    def nested(frozen):return records.verify_whole_scene_frozen(frozen)
    @records.verified_scene_execution_write
    def writer(frozen,*,mutate):
        evidence=records.verify_whole_scene_frozen(frozen)
        assert nested(frozen) is evidence
        assert len(semantic_calls)==(1 if mutate else 2)
        if not mutate:return evidence
        if target_kind=='inventory':
            target=path.parent/'http/added.body'
            target.write_bytes(b'new unregistered file')
            try:
                with pytest.raises(ProductionRefused,match='inventory changed'):
                    records.verify_whole_scene_frozen(frozen)
            finally:target.unlink()
        else:
            target=(path.parent/'resources/0003.json' if target_kind=='external' else
                run/'production/scene-rendering'/('whole-scene-evidence.json' if target_kind=='frozen_root' else 'evidence-closure.json'))
            original=target.read_bytes();stamp=target.stat()
            try:
                # Meaning/size/mtime-preserving changes must either be denied
                # by the whole window or rejected by complete byte rechecks.
                target.write_bytes(original[:-1]+b' ')
            except PermissionError:
                assert target_kind=='external' and os.name=='nt'
                assert target.read_bytes()==original
                assert records.verify_whole_scene_frozen(frozen) is evidence
            else:
                os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
                assert target.stat().st_size==stamp.st_size and target.stat().st_mtime_ns==stamp.st_mtime_ns
                try:
                    with pytest.raises(ProductionRefused,match='captured bytes'):
                        records.verify_whole_scene_frozen(frozen)
                finally:
                    target.write_bytes(original);os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        assert len(semantic_calls)==1
        return evidence
    import os
    first=writer(frozen,mutate=True)
    second=writer(frozen,mutate=False)
    assert second is not first and len(semantic_calls)==2


def test_writer_semantic_cache_keys_full_options_raw_and_resets_after_exception(tmp_path,runtime_run,monkeypatch):
    """Use a tiny authenticated-reader stand-in to isolate cache boundaries."""
    import video_ai.runtime.scene_execution_records as records
    from video_ai.runtime._whole_scene_admission import EvidenceReader,ALGORITHM
    from video_ai.runtime.production_state import json_bytes
    run,_,_=runtime_run;frozen=execution_fixture(run,'whole_scene_v1')
    root=run/'production/scene-rendering/whole-scene-evidence.json'
    closure=root.with_name('evidence-closure.json')
    root.parent.mkdir(parents=True);root.write_bytes(b'{"fixture_only":true}\n')
    external=tmp_path/'external.json';external.write_bytes(b'{"fixture_only":true}\n')
    root_identity=records.artifact(root,root=run)
    external_identity=records.artifact(external,root=tmp_path)
    closure.write_bytes(json_bytes(dict(schema_version=1,algorithm=ALGORITHM,root=root_identity,artifacts=[external_identity])))
    frozen.options['execution_policy']['input_identities'].update(
        whole_scene_evidence=root_identity,whole_scene_evidence_closure=records.artifact(closure,root=run))
    frozen.config.raw['scene_rendering']['whole_scene_evidence']=str(root)
    calls=[]
    def authenticated_load(path,**kwargs):
        calls.append(path)
        guard=EvidenceReader();guard.capture(root);guard.capture(external)
        return dict(root=guard.artifacts[str(root)],artifacts=sorted(guard.artifacts.values(),key=lambda v:v['path']),guard=guard)
    monkeypatch.setattr(records,'load_evidence',authenticated_load)
    monkeypatch.setattr(records,'verify_current_environment',lambda frozen,evidence:None)
    @records.verified_scene_execution_write
    def interrupted(frozen):
        first=records.verify_whole_scene_frozen(frozen)
        assert records.verify_whole_scene_frozen(frozen) is first and len(calls)==1
        frozen.options['audit_marker']='options changed'
        second=records.verify_whole_scene_frozen(frozen)
        assert second is not first and len(calls)==2
        frozen.config.raw['audit_marker']='raw changed'
        assert records.verify_whole_scene_frozen(frozen) is not second and len(calls)==3
        raise RuntimeError('writer interrupted')
    with pytest.raises(RuntimeError,match='writer interrupted'):interrupted(frozen)
    # Read-only calls and later writer invocations each authenticate afresh.
    records.verify_whole_scene_frozen(frozen);records.verify_whole_scene_frozen(frozen)
    assert len(calls)==5
    @records.verified_scene_execution_write
    def later(frozen):return records.verify_whole_scene_frozen(frozen)
    assert later(frozen) is not later(frozen) and len(calls)==7


def test_reader_validation_session_reuses_semantics_rechecks_bytes_and_rebuilds_next_session(tmp_path,runtime_run,monkeypatch):
    import os
    import video_ai.runtime.scene_execution_records as records
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.verification import validation_session
    path=fixture_evidence(tmp_path/'evidence',monkeypatch)
    run,_,_=runtime_run;frozen=execution_fixture(run,'whole_scene_v1')
    frozen.config.raw['scene_rendering']['whole_scene_evidence']=str(path)
    monkeypatch.setattr(records,'verify_current_environment',lambda frozen,evidence:None)
    def save(path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    records.freeze_whole_scene_evidence(frozen.config,run,frozen.options['execution_policy']['input_identities'],save=save)
    calls=[];original_load=records.load_evidence
    def counting_load(*args,**kwargs):
        calls.append(args[0]);return original_load(*args,**kwargs)
    monkeypatch.setattr(records,'load_evidence',counting_load)
    with validation_session():
        first=records.verify_whole_scene_frozen(frozen)
        with validation_session():assert records.verify_whole_scene_frozen(frozen) is first
        assert len(calls)==1
        for target in (path.parent/'resources/0003.json',run/'production/scene-rendering/evidence-closure.json'):
            raw=target.read_bytes();stamp=target.stat()
            target.write_bytes(raw[:-1]+b' ');os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            assert target.stat().st_size==stamp.st_size and target.stat().st_mtime_ns==stamp.st_mtime_ns
            try:
                with pytest.raises(ProductionRefused,match='captured bytes'):
                    records.verify_whole_scene_frozen(frozen)
            finally:
                target.write_bytes(raw);os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            assert len(calls)==1
    with validation_session():
        second=records.verify_whole_scene_frozen(frozen)
        assert second is not first and len(calls)==2


def test_explicit_writer_can_promote_large_owned_staging_while_external_model_stays_protected(tmp_path,runtime_run):
    import os
    from video_ai.runtime.scene_execution_records import verified_scene_execution_write
    from video_ai.runtime.manifest import hash_file
    run,_,_=runtime_run;frozen=execution_fixture(run)
    external=tmp_path/'immutable.safetensors';external.write_bytes(b'external_model')
    ancestor_media=tmp_path/'ancestor.mp4';ancestor_media.write_bytes(b'a'*(1024**2+1))
    staging=run/'staging.bin';staging.write_bytes(b'x'*(1024**2+1))
    target=run/'promoted.bin'
    @verified_scene_execution_write
    def writer(frozen):
        hash_file(external)
        hash_file(ancestor_media)
        original=hash_file(staging)
        os.rename(staging,target)
        assert hash_file(target).sha256==original.sha256
        with pytest.raises(PermissionError):external.write_bytes(b'modified_model')
        with pytest.raises(PermissionError):os.rename(ancestor_media,ancestor_media.with_name('moved.mp4'))
    writer(frozen)
    assert not staging.exists() and target.stat().st_size==1024**2+1
    external.write_bytes(b'editable_after_writer_exit')
    os.rename(ancestor_media,ancestor_media.with_name('moved.mp4'))
