"""Native identities and source budgets remain explicit across mode revisions."""
from copy import deepcopy
import pytest
from unit.test_scene_revision import revision_fixture


def test_native_revision_rehydrates_inactive_workflow_settings_without_freezing_wan(runtime_run):
    from dataclasses import replace
    from types import SimpleNamespace
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.production_scene_revision import _target_configuration
    from video_ai.jimeng_config import active_workflows
    from unit.test_jimeng_config import image_settings
    run,config,_=runtime_run
    raw=thaw(config.raw)
    raw.update(production_strategy='paragraph_jimeng_v1',image_generation=image_settings(),
        scene_continuity=dict(schema_version=1,policy='advisory_v1'))
    raw['scene_rendering']=dict(mode='temporal_extension_v1',prompt_policy='visual_v2',
        prompt_contract='D:/VideoSi/fixture-prompts.json',temporal_evidence='D:/VideoSi/fixture-evidence.json')
    effective=replace(config,production_strategy='paragraph_jimeng_v1',raw=raw,
        workflows=dict(upscale=config.workflows['upscale']))
    source=SimpleNamespace(config=effective,options=dict(config_snapshot=dict(raw=raw),voice_snapshot=dict(raw=thaw(config.voice.raw)),
        execution_policy=dict(input_identities=dict(scene_video_prompts=dict(path=raw['scene_rendering']['prompt_contract']),
            temporal_evidence=dict(path=raw['scene_rendering']['temporal_evidence'])))))
    target,_,_=_target_configuration(source,run,dict(kind='regenerate_clips'))
    assert set(active_workflows(target))=={'upscale'}
    assert target.workflows['wan']==config.workflows['wan']


def options():
    snapshot,request,_=revision_fixture('reconfigure')
    value=snapshot['source_options']
    value['config_snapshot']['raw']['scene_rendering']=dict(mode='temporal_extension_v1',prompt_policy='visual_v2',
        prompt_contract='D:/VideoSi/prompts.json',temporal_evidence='D:/VideoSi/evidence.json')
    value['execution_policy']['input_identities'].update(scene_video_prompts={'sha256':'a'*64},
        temporal_evidence={'sha256':'b'*64},temporal_runtime_bundle={'sha256':'c'*64})
    return value


@pytest.mark.parametrize('native',[True,False])
def test_revision_holds_native_read_window_and_releases_it_on_refusal(runtime_run,tmp_path,monkeypatch,native):
    from dataclasses import replace
    from types import SimpleNamespace
    import json,hashlib
    from video_ai.runtime import production_scene_revision as revision,verification
    from video_ai.runtime.production_state import ProductionRefused
    run,config,_=runtime_run
    raw=dict(scene_rendering=dict(mode='temporal_extension_v1')) if native else {}
    config=replace(config,production_strategy='paragraph_jimeng_v1',raw=raw)
    frozen=SimpleNamespace(config=config,options={})
    options_path=run/'production/options.json';options_path.parent.mkdir(parents=True,exist_ok=True);options_path.write_bytes(b'{}')
    _,request,_=revision_fixture('regenerate_clips')
    request.update(source_run_id=run.name,source_options_sha256=hashlib.sha256(b'{}').hexdigest())
    path=tmp_path/'window-request.json';path.write_text(json.dumps(request),encoding='utf-8')
    monkeypatch.setattr('video_ai.runtime.production_inputs.load_frozen_inputs',lambda *a,**k:frozen)
    visited=[]
    def target(*args):
        visited.append(True)
        assert (verification._whole_inputs.get() is not None)==native
        if native:assert verification.validation_memo('temporal_native_admission') is not None
        raise ProductionRefused('fixture stopped after verifying native input window')
    monkeypatch.setattr(revision,'_target_configuration',target)
    result=revision.create_scene_revision(run,path)
    assert visited and result.status=='blocked',result.error
    assert 'fixture stopped' in result.error['message']
    assert verification._whole_inputs.get() is None


def test_native_rendering_identity_has_independent_schema4_and_runtime_binding():
    from video_ai.planning.scene_revision import identity_from_options,validate_rendering_identity
    value=identity_from_options(options())
    assert value['schema_version']==4
    assert value['rendering']==dict(prompt_policy='visual_v2',prompt_contract_sha256='a'*64,mode='temporal_extension_v1',
        temporal_evidence_sha256='b'*64,temporal_runtime_bundle_sha256='c'*64,execution_algorithm='scene_execution_v2',protocol='longcat_native16_v1')
    validate_rendering_identity(value)
    for key in ('temporal_evidence_sha256','temporal_runtime_bundle_sha256','protocol'):
        changed=deepcopy(value);changed['rendering'].pop(key)
        with pytest.raises(ValueError):validate_rendering_identity(changed)


def test_mode_revision_invalidates_all_video_but_preserves_common_and_selected_images():
    from video_ai.planning.scene_revision import identity_from_options,plan_scene_revision
    snapshot,request,_=revision_fixture('reconfigure')
    request.update(scene_ids=[],clip_ids=[],choices=[],config_path='D:/VideoSi/new-native.json')
    original=identity_from_options(snapshot['source_options'])
    snapshot['source_options']['_scene_revision_planning']=dict(identity=original,completed_image_ids=[s['scene_id'] for s in snapshot['scene_plan']['scenes']],image_group_accepted=True,target_config=None)
    target=deepcopy(original);native=identity_from_options(options())
    target.update(schema_version=native['schema_version'],rendering=native['rendering'])
    target['config_sha256']='f'*64
    result=plan_scene_revision(snapshot,request,target)
    assert result['reusable']['common']==result['reusable']['plan']==['all']
    assert result['dirty']['clips']==[c['clip_id'] for c in snapshot['scene_plan']['clips']]
    assert result['dirty']['clip_reviews']==result['dirty']['clips']
    assert result['dirty']['choices']==[] and result['dirty']['images']==[]


def test_native_source_snapshot_reads_its_schema2_execution():
    from video_ai.planning.scene_revision import identity_from_options,snapshot_execution_clips
    from video_ai.planning.scene_execution import build_scene_execution_budget
    from video_ai.planning.production_scenes import canonical_digest
    from types import SimpleNamespace
    snapshot,request,_=revision_fixture('reconfigure');snapshot['source_options']=options()
    value=identity_from_options(snapshot['source_options'])
    snapshot['scene_execution']=build_scene_execution_budget(snapshot['scene_plan'],dict(total_frames=52),
        run_id=snapshot['source_options']['run_id'],mode='temporal_extension_v1',rendering_identity_sha256=canonical_digest(value),
        admission=dict(path='D:/VideoSi/evidence.json',bytes=123,sha256='b'*64))
    clips=snapshot_execution_clips(snapshot)
    assert len(clips)==4 and all(c['protocol']=='longcat_native16_v1' and c['retained_frames']==13 for c in clips)
