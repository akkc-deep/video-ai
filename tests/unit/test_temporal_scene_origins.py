"""Native origin metadata is usable only through exact captured revision bytes."""
from pathlib import Path
import pytest

from unit.test_temporal_scene_records import request_fixture,put


def test_bound_native_origin_metadata_is_exact_and_unknown_paths_stay_forbidden(runtime_run):
    from video_ai.runtime.temporal_scene_origins import bound_temporal_artifact
    from video_ai.runtime.scene_revision_records import RevisionGuard
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.production_state import ProductionRefused
    context,row,_,_=request_fixture(runtime_run);store=context['store'];store.execution_mode='temporal_extension_v1'
    source=create_run(runtime_run[2]);captured=put(source/'production/scene-clips/native-result.json',dict(fixture_only=True))
    other=put(source/'production/scene-clips/unrelated.json',dict(fixture_only='unrelated'))
    guard=RevisionGuard(context['frozen']);guard.capture(captured['path'],root=source,expected=captured)
    store.revision_context=dict(guard=guard,source_run=source,imports={})
    assert bound_temporal_artifact(store,captured['path'],captured)==captured
    assert bound_temporal_artifact(store,other['path'],other) is None
    Path(captured['path']).write_bytes(b'changed')
    with pytest.raises(ProductionRefused):bound_temporal_artifact(store,captured['path'],captured)


def test_native_upscale_origin_captures_original_chain_metadata(runtime_run,monkeypatch):
    from types import SimpleNamespace
    from unit.test_temporal_chain_records import chain_fixture,write_chain
    from video_ai.runtime import _scene_revision_origins as origins
    from video_ai.runtime.production_state import ProductionRefused
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    folder,_,chain_id=write_chain(context,window)
    frozen=context['frozen'];run=context['store'].run_dir;cid=row['budget']['clip_id']
    script=put(run/'production/script.txt',b'fixture_only original text')
    frozen.options['execution_policy']=dict(input_identities=dict(script=script,
        **{role:context['evidence']['root'] for role in ('temporal_evidence','temporal_evidence_closure','temporal_runtime_bundle','scene_video_prompts')}))
    frozen.config=SimpleNamespace(raw=dict(scene_rendering=dict(mode='temporal_extension_v1')))
    put(run/'production/options.json',frozen.options)
    for stage in ('units','timeline'):put(run/f'production/{stage}.json',dict(payload={}))
    monkeypatch.setattr(origins.ProductionTimeline,'from_dict',lambda value:SimpleNamespace(clips=[]))
    monkeypatch.setattr('video_ai.runtime.image_selection_records.load_committed_plan',lambda *a:({},dict(scenes=[])))
    monkeypatch.setattr('video_ai.runtime.production_scene_revision._source_execution',lambda *a:dict(mode='temporal_extension_v1',clips=[row['budget']]))
    monkeypatch.setattr('video_ai.runtime.temporal_scene_admission.verify_temporal_frozen',lambda *a:None)
    monkeypatch.setattr('video_ai.runtime.scene_continuity_records.load_continuity_policy',lambda *a:None)
    monkeypatch.setattr(origins,'_origin_clip_ids',lambda *a:({cid},{cid}))
    # Admission/semantic origin selection have their own integration coverage;
    # this test exercises the real source inventory and immutable byte guard.
    monkeypatch.setattr(origins,'require_origin_node',lambda *a:dict(fixture_only=True))
    monkeypatch.setattr(origins,'media_for_node',lambda *a:[])
    captured=origins.capture_origin(frozen,'upscale',cid+':frame_000001')
    assert chain_id['path'] in captured['guard'].files
    Path(chain_id['path']).write_bytes(b'changed original chain metadata')
    with pytest.raises(ProductionRefused):captured['guard'].verify_captured_bytes()


@pytest.mark.parametrize('required',[False,True])
def test_discarded_native_clip_missing_movie_does_not_block_revision_metadata(runtime_run,monkeypatch,required):
    from unit.test_temporal_chain_records import chain_fixture,write_chain
    from video_ai.runtime.scene_clip_records import validate_clip
    from video_ai.runtime._scene_revision_origin_clips import origin_clip_scope
    from video_ai.runtime.production_state import ProductionRefused
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    context['execution']=dict(mode='temporal_extension_v1')
    write_chain(context,window)
    Path(window['source']['path']).unlink()
    cid=row['budget']['clip_id']
    with origin_clip_scope(context['frozen'],[cid] if required else [],all_ids=[cid]):
        if required:
            with pytest.raises(ProductionRefused):validate_clip(context,row)
        else:
            view=validate_clip(context,row)
            assert view['native_window']['source']==window['source']
            assert view['request']['budget']==row['budget']


@pytest.mark.parametrize('required',[False,True])
def test_discarded_native_chain_missing_viewing_is_scoped_to_revision(runtime_run,monkeypatch,required):
    from unit.test_temporal_chain_records import chain_fixture,write_chain
    from video_ai.runtime.scene_clip_records import validate_clip
    from video_ai.runtime._scene_revision_origin_clips import origin_clip_scope
    from video_ai.runtime.production_state import ProductionRefused
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    context['execution']=dict(mode='temporal_extension_v1')
    _,chain,_=write_chain(context,window)
    Path(chain['artifacts']['viewing_movie']['path']).unlink()
    cid=row['budget']['clip_id']
    with origin_clip_scope(context['frozen'],[cid] if required else [],all_ids=[cid]):
        if required:
            with pytest.raises(ProductionRefused):validate_clip(context,row)
        else:
            view=validate_clip(context,row)
            assert view['native_chain']['viewing']==chain['artifacts']['viewing_movie']



def test_native_import_remaps_media_without_rewriting_original_events(runtime_run,monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    from unit.test_temporal_chain_records import chain_fixture,write_chain
    from unit.test_temporal_scene_observations import author
    from video_ai.runtime.temporal_scene_origins import inherited_temporal_window
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    folder,raw,result_id=write_chain(context,window)
    chain=records.validate_temporal_chain(context,'scene_0001',[window])
    template=build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')
    original_observation=author(template);chain['observation']=deepcopy(original_observation)
    chain['acceptance']=put(folder/'accepted.json',dict(fixture_only=True))
    accepted=chain['acceptance'];cid=row['budget']['clip_id']
    source_record=dict(native_window=window,native_chain=chain,accepted=accepted,rejected=None,
        request=window['request'],template=template,clip=dict(fixture_only=True))
    mappings=[]
    for role,original in (('raw',window['raw_frames']),('image',window['selected_image'])):
        local=put(context['store'].root/f'fixture-import-{role}.bin',Path(original['path']).read_bytes())
        mappings.append(dict(source=original,target=local))
    context['wan']['scenes'][0].update(mappings[1]['target'])
    proof=dict(source_run=context['store'].run_dir,imports={'clip:'+cid:(dict(local_artifacts=mappings),None)},
        guard=SimpleNamespace(verify_captured_bytes=lambda:None))
    context['store'].revision_context=proof
    monkeypatch.setattr(context['store'],'clip_dir',lambda *a:context['store'].root/'fixture-import-window')
    monkeypatch.setattr('video_ai.runtime._scene_revision_readers.proof_for',lambda *a,**k:proof)
    monkeypatch.setattr('video_ai.runtime.production_inputs.load_frozen_inputs',lambda *a:context['frozen'])
    monkeypatch.setattr('video_ai.runtime._scene_revision_origins.source_clip_record',lambda *a:deepcopy(source_record))
    monkeypatch.setattr('video_ai.runtime.scene_revision_records.require_revision_import',lambda *a,**k:dict(fixture_only=True))
    imported=inherited_temporal_window(context,row)
    assert imported['raw_frames']==mappings[0]['target']
    assert imported['selected_image']==mappings[1]['target']
    assert imported['request']==window['request'],'original request bytes are not a new local request'
    assert imported['static_observation']==window['static_observation'],'original static author event must stay verbatim'
    assert imported['origin_chain']['observation']==original_observation,'original playback must not be re-signed for copied paths'
    assert imported['origin_template']==template

