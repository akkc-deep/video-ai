"""Normal prepared-run revision into native mode; CPU fixture_only resources."""
import json
import pytest
from pathlib import Path
from uuid import uuid4

from integration.test_scene_revision_flow import revision_source,revision_request,tree_identity


def native_revision(setup,tmp_path,monkeypatch):
    from unit.test_temporal_scene_admission import ready_fixture,ready_document
    from unit.test_scene_video_prompts import contract_for,reviewed
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime.reference_image_records import require_reference_image_acceptance
    from video_ai.runtime.manifest import thaw
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.production_scene_revision import create_scene_revision
    admission,qualified,bundle,worker,native,resource=ready_fixture(tmp_path/'native',monkeypatch)
    guard=EvidenceReader()
    for item in qualified['artifacts']:guard.capture(item['path'],item)
    qualified['guard']=guard
    evidence=ready_document(tmp_path/'native',qualified,bundle,worker,native,resource)
    f,b,p,t=setup['frozen'],setup['bible'],setup['plan'],setup['timeline']
    selected=require_reference_image_acceptance(f,setup['units'],t)
    clips=derive_scene_execution_clips(p,t,mode='temporal_extension_v1')
    contract=contract_for(b,p,selected);by_id={c['clip_id']:c for c in contract['clips']}
    contract.update(schema_version=3,clips=[by_id[c['clip_id']] for c in clips])
    contract['binding'].update(rendering_mode='temporal_extension_v1',execution_clips_sha256=canonical_digest(clips))
    reviewed(contract)
    prompt=tmp_path/'native-prompts.json';prompt.write_text(json.dumps(contract),encoding='utf-8')
    raw=thaw(f.options['config_snapshot']['raw']);raw['scene_continuity']=dict(schema_version=1,policy='advisory_v1')
    raw['scene_rendering']=dict(mode='temporal_extension_v1',prompt_policy='visual_v2',prompt_contract=str(prompt),temporal_evidence=str(evidence))
    config=tmp_path/'native-config.json';config.write_text(json.dumps(raw),encoding='utf-8')
    path,request=revision_request(setup)
    request.update(kind='reconfigure',scene_ids=[],choices=[],config_path=str(config))
    path.write_text(json.dumps(request),encoding='utf-8')
    return create_scene_revision(setup['run'],path),path


def test_normal_revision_freezes_native_evidence_and_preserves_pcm_and_images(revision_source,tmp_path,monkeypatch):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix,require_scene_revision
    from video_ai.runtime.scene_execution_records import load_scene_execution
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.planning.scene_revision import identity_from_options
    before=tree_identity(revision_source['run'])
    result,request=native_revision(revision_source,tmp_path,monkeypatch)
    assert result.status=='revision_ready',result.error
    assert tree_identity(revision_source['run'])==before
    frozen=load_frozen_inputs(result.run_dir);proof=require_scene_revision(frozen)
    units,timeline=load_scene_common_prefix(frozen);_,plan=load_committed_plan(frozen,units,timeline)
    assert units==revision_source['units']
    assert timeline.total_frames==revision_source['timeline'].total_frames
    assert [c.samples for c in timeline.clips]==[c.samples for c in revision_source['timeline'].clips]
    assert all(c.pcm.path.is_relative_to(result.run_dir) for c in timeline.clips)
    assert 'image_group:all' in proof['imports'] and not any(k.startswith('clip:') for k in proof['imports'])
    assert identity_from_options(frozen.options)['schema_version']==4
    execution=load_scene_execution(frozen,plan,timeline)
    assert execution['schema_version']==2 and execution['mode']=='temporal_extension_v1'
    assert [c['retained_frames'] for c in execution['clips']]==[13,2,3]
    assert not list((result.run_dir/'production/scene-clips').glob('*/intent.json'))


def test_native_mode_to_real_upscale_mapping_full_pcm_and_subtitles(revision_source,tmp_path,monkeypatch):
    import wave
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix,revision_scope
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.runtime.reference_image_records import build_reference_image_acceptance
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._scene_revision_copy import RevisionStore
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    from video_ai.runtime.production_scene_composition import produce_scene_composition
    from scene_media_helpers import OfflineUpscale
    from temporal_scene_helpers import OfflineNative
    from video_ai.media.subtitles import srt_text
    result,_=native_revision(revision_source,tmp_path,monkeypatch)
    assert result.status=='revision_ready',result.error
    f=load_frozen_inputs(result.run_dir)
    with revision_scope():
        units,timeline=load_scene_common_prefix(f);bible,plan=load_committed_plan(f,units,timeline)
        with RunLock(result.run_dir) as lock:
            selected=build_reference_image_acceptance(f,units,timeline)
            RevisionStore(result.run_dir,lock).save(result.run_dir/'production/reference-images/wan-inputs.json',selected)
    setup=dict(run=result.run_dir,frozen=f,units=units,timeline=timeline,bible=bible,plan=plan,config=f.config,
        paths=RuntimePaths.from_config(f.config),logger=RunLogger(result.run_dir,production=True))
    # Diagnostic/risk behavior is tested separately; this fixture isolates real
    # native media, exact PCM and subtitle contributions without a model/GPU.
    monkeypatch.setattr('video_ai.runtime.scene_continuity_records.require_scene_continuity_acceptance',lambda *a,**k:dict(ready=True,fixture_only=True))
    backend=OfflineNative(setup,monkeypatch)
    assert backend.admit_all().status=='source_clips_ready'
    upscaler=OfflineUpscale(setup)
    kwargs=dict(paths=setup['paths'],logger=setup['logger'])
    upscaled=produce_scene_upscaled_clips(f,units,timeline,**kwargs,**upscaler.kwargs)
    assert upscaled.status=='upscale_ready',upscaled.error
    assert len(upscaler.posts)==timeline.total_frames
    # A later immutable upscale binding must permit the original coordinator
    # to restore the exact native aggregate without sampling or text encoding.
    from types import SimpleNamespace
    from video_ai.runtime.production_scene_pipeline import _restore_missing_aggregates
    complete=result.run_dir/'production/scene-clips/complete.json'
    original_complete=complete.read_bytes();complete.unlink();sample_count=len(backend.calls)
    with RunLock(result.run_dir) as held:
        recovered=_restore_missing_aggregates(f,units,timeline,**kwargs,lock=held,
            deps=SimpleNamespace(wan_client_factory=None,wan_service_factory=None))
    assert recovered is None,getattr(recovered,'error',None)
    assert complete.read_bytes()==original_complete and len(backend.calls)==sample_count
    composed=produce_scene_composition(f,units,timeline,**kwargs)
    assert composed.status=='awaiting_final_review',composed.error
    material=json.loads((result.run_dir/'production/scene-composition/materialized.json').read_bytes())
    assert Path(material['subtitle']['path']).read_bytes()==srt_text(material['subtitle_events']).encode('utf-8')
    with wave.open(material['narration']['audio']['path'],'rb') as audio:
        pcm=audio.readframes(audio.getnframes());assert audio.getnframes()==timeline.total_frames*3000
    for clip in timeline.clips:
        with wave.open(str(clip.pcm.path),'rb') as original:assert pcm[clip.start_sample*2:clip.end_sample*2]==original.readframes(clip.samples)
    count=len(backend.calls)
    assert backend.admit_all().status=='source_clips_ready' and len(backend.calls)==count


def setup_from_native_revision(result):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix,revision_scope
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.runtime.reference_image_records import build_reference_image_acceptance
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._scene_revision_copy import RevisionStore
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    f=load_frozen_inputs(result.run_dir)
    with revision_scope():
        units,timeline=load_scene_common_prefix(f);bible,plan=load_committed_plan(f,units,timeline)
        with RunLock(result.run_dir) as lock:
            selected=build_reference_image_acceptance(f,units,timeline)
            RevisionStore(result.run_dir,lock).save(result.run_dir/'production/reference-images/wan-inputs.json',selected)
    return dict(run=result.run_dir,frozen=f,units=units,timeline=timeline,bible=bible,plan=plan,config=f.config,
        paths=RuntimePaths.from_config(f.config),logger=RunLogger(result.run_dir,production=True))


def native_progress(setup):
    from video_ai.runtime.scene_revision_records import revision_scope
    from video_ai.runtime.verification import whole_input_protection,validation_session
    from video_ai.runtime.scene_clip_records import scene_context
    from video_ai.runtime.temporal_scene_records import collect_temporal_progress
    with revision_scope(),whole_input_protection(),validation_session():
        return collect_temporal_progress(scene_context(setup['frozen'],setup['units'],setup['timeline']))


@pytest.mark.parametrize('operation',['one-window','prepare-cache'])
def test_revision_blocks_native_launch_interrupted_before_worker_intent(revision_source,tmp_path,monkeypatch,operation):
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_clip_records import scene_context
    from video_ai.runtime.temporal_scene_records import expected_temporal_request,temporal_workflow
    from video_ai.runtime.temporal_native_worker import prepare_native_input,MissingNativeTextCache
    from video_ai.runtime import temporal_native_process as process
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from unit.test_temporal_native_process import HEALTHY
    from video_ai.runtime.verification import whole_input_protection,writable_validation_session
    from video_ai.runtime.scene_revision_records import revision_scope
    result,_=native_revision(revision_source,tmp_path,monkeypatch)
    assert result.status=='revision_ready',result.error
    setup=setup_from_native_revision(result);calls=[]
    # GPU acquisition is an explicit fixture seam; the durable launch journal,
    # missing worker owner/intent and public revision validation are real.
    monkeypatch.setattr(process,'_gpu_owned',lambda store:dict(path=str(store.paths.cache_root/'locks/gpu.lock'),token='a'*32))
    def missing(*a,**k):raise MissingNativeTextCache('fixture_only uncached new prompt')
    monkeypatch.setattr('video_ai.runtime.temporal_native_worker.existing_native_text_context',missing)
    def interrupted(command,**kwargs):
        calls.append(command[command.index('--operation')+1])
        raise KeyboardInterrupt('fixture interruption after launch-intent, before worker intent')
    with revision_scope(),RunLock(setup['run']) as held,whole_input_protection(),writable_validation_session(setup['run']):
        context=scene_context(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],lock=held)
        store=context['store'];row=context['rows'][0]
        store.write('inputs.json',context['inputs'])
        selected=next(v for v in context['wan']['scenes'] if v['scene_id']==row['budget']['scene_id'])
        prepared=prepare_native_input(store,row,selected)
        request=expected_temporal_request(context,row,prepared,None);workflow=temporal_workflow(context,row)
        folder=store.clip_dir(request['clip_id'])
        store.write(folder/'request.json',request);store.write(folder/'workflow.json',workflow)
        run_job=process.recover_or_start_native_window if operation=='one-window' else process.recover_or_prepare_native_cache
        with pytest.raises(KeyboardInterrupt):
            run_job(store,request,workflow,worker_factory=interrupted,resource_sampler=lambda:dict(HEALTHY))
    assert calls==[operation] and not (folder/'intent.json').exists()
    path,revision=revision_request(setup)
    revision.update(kind='regenerate_clips',scene_ids=[],choices=[],clip_ids=[request['clip_id']])
    path.write_text(json.dumps(revision),encoding='utf-8')
    before=tree_identity(setup['run'])
    revised=create_scene_revision(setup['run'],path)
    assert revised.status=='blocked' and revised.run_dir is None,revised.error
    assert 'effects' in revised.error['message'].lower()
    assert tree_identity(setup['run'])==before and calls==[operation]


def test_native_revision_inherits_unchanged_scene_with_original_observation(revision_source,tmp_path,monkeypatch):
    from temporal_scene_helpers import OfflineNative
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision,revision_scope
    from video_ai.runtime.scene_clip_records import scene_context
    from video_ai.runtime.temporal_scene_records import collect_temporal_progress
    monkeypatch.setattr('video_ai.runtime.scene_continuity_records.require_scene_continuity_acceptance',lambda *a,**k:dict(ready=True,fixture_only=True))
    result,_=native_revision(revision_source,tmp_path,monkeypatch)
    assert result.status=='revision_ready',result.error
    setup=setup_from_native_revision(result);backend=OfflineNative(setup,monkeypatch)
    assert backend.admit_all().status=='source_clips_ready'
    progress=native_progress(setup)
    old_chains={chain['scene_id']:chain for chain in progress['chains']}
    first=progress['records'][0]['budget']['clip_id']
    path,request=revision_request(setup)
    request.update(kind='regenerate_clips',scene_ids=[],choices=[],clip_ids=[first])
    path.write_text(json.dumps(request),encoding='utf-8')
    before=tree_identity(setup['run'])
    revised=create_scene_revision(setup['run'],path)
    assert revised.status=='revision_ready',revised.error
    assert tree_identity(setup['run'])==before
    f=load_frozen_inputs(revised.run_dir);proof=require_scene_revision(f)
    assert 'clip:'+first not in proof['imports']
    for window in progress['records'][1:]:assert 'clip:'+window['budget']['clip_id'] in proof['imports']
    target=setup_from_native_revision(revised);continued=OfflineNative(target,monkeypatch)
    assert continued.admit_all().status=='source_clips_ready'
    assert len(continued.calls)==1
    current=native_progress(target)
    for chain in current['chains'][1:]:
        original=old_chains[chain['scene_id']]
        assert chain['acceptance']==original['acceptance']
        assert chain['observation']==original['observation']
        assert chain['result']==original['result']
        for window in chain['windows']:
            assert Path(window['raw_frames']['path']).is_relative_to(revised.run_dir)
            assert Path(window['generator']['path']).is_relative_to(revised.run_dir)
    assert tree_identity(setup['run'])==before



def test_native_revision_keeps_raw_parent_but_requires_new_mixed_chain_review(runtime_run,tmp_path,monkeypatch):
    from scene_pipeline_helpers import prepared_pipeline
    from temporal_scene_helpers import OfflineNative
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_scene_clips import produce_scene_clips,consume_scene_clip_observation
    from video_ai.runtime.scene_revision_records import revision_scope
    from video_ai.runtime.scene_clip_records import scene_context
    from video_ai.runtime.temporal_scene_records import collect_temporal_progress
    from unit.test_temporal_scene_observations import author
    from video_ai.runtime.manifest import now
    import numpy as np
    (tmp_path/'long-source').mkdir()
    source=prepared_pipeline(runtime_run,tmp_path/'long-source',monkeypatch,
        speech_samples=[300001,19501,6001,6001])
    monkeypatch.setattr('video_ai.runtime.scene_continuity_records.require_scene_continuity_acceptance',lambda *a,**k:dict(ready=True,fixture_only=True))
    result,_=native_revision(source,tmp_path/'native-source',monkeypatch)
    assert result.status=='revision_ready',result.error
    setup=setup_from_native_revision(result);backend=OfflineNative(setup,monkeypatch)
    assert backend.admit_all().status=='source_clips_ready'
    progress=native_progress(setup)
    windows=progress['chains'][0]['windows'];assert len(windows)==2
    parent,child=windows;old_chain=progress['chains'][0]
    path,request=revision_request(setup)
    request.update(kind='regenerate_clips',scene_ids=[],choices=[],clip_ids=[child['budget']['clip_id']])
    path.write_text(json.dumps(request),encoding='utf-8')
    before=tree_identity(setup['run'])
    revised=create_scene_revision(setup['run'],path)
    assert revised.status=='revision_ready',revised.error
    target=setup_from_native_revision(revised);continued=OfflineNative(target,monkeypatch)
    kwargs=dict(paths=target['paths'],logger=target['logger'])
    pending=produce_scene_clips(target['frozen'],target['units'],target['timeline'],**kwargs)
    assert pending.status=='awaiting_continuity_review',pending.error
    assert len(continued.calls)==1
    assert continued.calls[0]['condition'][:,0,0,0].tolist()==list(range(80,93))
    for observed in pending.observation_templates:
        template=json.loads(Path(observed).read_bytes());assert template['scope']=='temporal_window_static'
        value=author(template);value['viewed_at']=now();authored=target['run']/'fixture-mixed-static.json'
        authored.write_text(json.dumps(value),encoding='utf-8')
        consumed=consume_scene_clip_observation(target['frozen'],target['units'],target['timeline'],authored,**kwargs)
        assert consumed.status!='source_clips_ready',consumed.error
    pending=produce_scene_clips(target['frozen'],target['units'],target['timeline'],**kwargs)
    assert pending.status=='awaiting_continuity_review',pending.error
    assert not (target['run']/'production/scene-clips/complete.json').exists()
    assert len(pending.observation_templates)==1
    template=json.loads(Path(pending.observation_templates[0]).read_bytes())
    assert template['scope']=='scene_temporal_chain_process'
    assert len(template['binding']['windows'])==2
    assert template['binding']['windows'][0]['result']==parent['result']
    assert continued.admit_all().status=='source_clips_ready'
    current=native_progress(target)
    chain=current['chains'][0];inherited=chain['windows'][0]
    assert chain['acceptance']!=old_chain['acceptance']
    assert inherited['result']==parent['result'] and inherited['static_acceptance']==parent['static_acceptance']
    assert Path(inherited['raw_frames']['path']).is_relative_to(revised.run_dir)
    frames=np.load(inherited['raw_frames']['path'],mmap_mode='r',allow_pickle=False)
    assert frames[80:93,0,0,0].tolist()==list(range(80,93))
    del frames
    assert len(continued.calls)==1 and tree_identity(setup['run'])==before

