from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import pytest

from video_ai.planning.recovery import (
    ValidatedInventory, build_recovery_plan, signature, validate_changes,
)
from video_ai.runtime.manifest import STAGES


def identity(path='D:/VideoSi/input.txt', sha='a'*64):
    return dict(path=path, bytes=10, sha256=sha, mtime_ns=1,
                verified_at='2026-10-05T00:00:00+00:00')


def inventory(**kwargs):
    values = dict(run_dir=Path('D:/VideoSi/projects/video-ai/runs/20261005-000000-aaaaaaaaaaaa'),
        snapshot={'identity': identity(), 'run_id':'20261005-000000-aaaaaaaaaaaa'},
        config_projection={'voice':{'speed_factor':1}, 'media':{'fps':16},
                           'models':{'wan_high':'old','sdxl':'old','upscale':'old'}},
        input_identities={'script':identity()},
        stage_records={s:{'status':'completed' if s!='publish' else 'pending'} for s in STAGES},
        unit_records={s:{'shot_0001':{'status':'completed'}, 'shot_0002':{'status':'completed'}}
                      for s in ('storyboard','start_images','source_clips','upscale')},
        checkpoints={}, signatures={}, submissions={},
        reviews={'voice_acceptance':True,'timing':True,'storyboard':True,'start_images':True,
                 'source_clips':True,'upscale':True})
    values.update(kwargs)
    return ValidatedInventory(**values)


def changes(inv, shot_changes=()):
    return dict(schema_version=1,base_run_id=inv.snapshot['run_id'],
        base_manifest_snapshot_identity=dict(inv.snapshot['identity']),
        created_at='2026-10-05T00:00:00+00:00',reason='explicit test repair',
        script_identity=None,unit_review_identity=None,config_identity=identity(),
        shot_changes=list(shot_changes))


def affected(plan, stage):
    return {r.unit_id for r in plan.invalidated if r.stage==stage}


def test_inventory_deep_immutable_and_result_frozen():
    inv=inventory()
    with pytest.raises(TypeError): inv.stage_records['speech']['status']='pending'
    plan=build_recovery_plan(inv)
    with pytest.raises(FrozenInstanceError): plan.waiting_for=()


def test_candidate_consumes_in_fixed_order_and_waits_final_acceptance():
    plan=build_recovery_plan(inventory())
    assert [o.stage for o in plan.operations if o.action=='consume']==list(STAGES[:-1])
    assert plan.waiting_for==('final_review','full_film_acceptance')
    assert not plan.requires_child_run
    assert all(o.action!='publish' for o in plan.operations)


def test_publish_explicit_and_never_inferred():
    inv=inventory(reviews={'voice_acceptance':True,'final_review':True,'full_film_acceptance':True})
    assert build_recovery_plan(inv).operations[-1].action=='wait'
    assert build_recovery_plan(inv,publish=True).operations[-1].action=='publish'
    assert build_recovery_plan(inv,publish=True,changes=changes(inv)).refusal_reasons


@pytest.mark.parametrize('field,value,first',[
    ('voice.speed_factor',1.2,'speech'),('media.fps',24,'timeline'),
    ('models.wan_high','new','source_clips'),('models.sdxl','new','storyboard'),
    ('models.upscale','new','upscale'),('media.music','new','composition'),
    ('media.font_file','new','composition'),('media.transition','fade','composition'),
])
def test_all_change_classes(field,value,first):
    inv=inventory(); config={k:dict(v) for k,v in inv.config_projection.items()}
    group,key=field.split('.');config[group][key]=value
    plan=build_recovery_plan(inv,config_projection=config,changes=changes(inv))
    assert not plan.refusal_reasons
    assert plan.requires_child_run
    assert min(STAGES.index(r.stage) for r in plan.invalidated)==STAGES.index(first)
    assert any(c.field==field for c in plan.changed_keys)


def test_operational_config_changes_are_listed_but_do_not_invalidate():
    inv=inventory(config_projection={'services':{'comfyui':'old'},'timeouts':{'wan':1}})
    plan=build_recovery_plan(inv,config_projection={'services':{'comfyui':'new'},'timeouts':{'wan':2}})
    assert len(plan.changed_keys)==2
    assert not plan.invalidated and not plan.refusal_reasons
    assert plan.requires_child_run and plan.operations[0].action=='derive'


def test_config_drift_without_explicit_change_refused():
    plan=build_recovery_plan(inventory(),config_projection={'voice':{'speed_factor':2}})
    assert plan.refusal_reasons and not plan.operations


def test_video_prompt_change_does_not_invalidate_other_shots_or_images():
    inv=inventory(); ch=changes(inv,[dict(shot_id='shot_0001',image_prompt=None,video_prompt='new',reason='repair')])
    plan=build_recovery_plan(inv,changes=ch)
    assert affected(plan,'source_clips')=={'shot_0001'}
    assert affected(plan,'upscale')=={'shot_0001'}
    assert not affected(plan,'start_images')
    assert any(r.stage=='source_clips' and r.unit_id=='shot_0002' for r in plan.reused)


def test_image_shared_dependency_closure_does_not_guess_adjacency():
    inv=inventory();units={s:{k:dict(v) for k,v in rows.items()} for s,rows in inv.unit_records.items()}
    units['start_images']['shot_0002']['references']=['shot_0001']
    inv=replace(inv,unit_records=units)
    ch=changes(inv,[dict(shot_id='shot_0001',image_prompt='new',video_prompt=None,reason='repair')])
    plan=build_recovery_plan(inv,changes=ch)
    assert affected(plan,'start_images')=={'shot_0001','shot_0002'}
    assert affected(plan,'source_clips')=={'shot_0001','shot_0002'}


def test_running_validated_draft_finalizes_only_with_reviews():
    inv=inventory();records={s:dict(r) for s,r in inv.stage_records.items()}
    records['start_images']={'status':'running'}
    inv=replace(inv,stage_records=records,checkpoints={'start_images':{'draft_complete':True}},reviews={})
    plan=build_recovery_plan(inv)
    assert plan.waiting_for==('start_images',)
    assert plan.operations[-1].action=='wait'
    assert build_recovery_plan(inv,reviews={'start_images':True}).operations[-1].action=='finalize'


@pytest.mark.parametrize('state',['intent','ambiguous','accepted','still_running'])
def test_unknown_submissions_never_prepare_even_retry(state):
    inv=inventory(submissions={'source_clips':{'shot_0001':{'state':state}}})
    plan=build_recovery_plan(inv,retry_failed=True)
    assert any(o.action=='reconcile' for o in plan.operations)
    assert all(o.action!='prepare' for o in plan.operations)


def test_failed_needs_explicit_retry_and_child():
    inv=inventory(submissions={'source_clips':{'shot_0001':{'state':'failed'}}})
    assert build_recovery_plan(inv).refusal_reasons
    plan=build_recovery_plan(inv,retry_failed=True)
    assert plan.requires_child_run
    assert any(r.stage=='source_clips' and r.unit_id=='shot_0001' for r in plan.invalidated)


def test_signature_only_normalizes_identity_and_declared_graph_namespace_roles():
    a={'identity':identity(),'graph':{'1':{'inputs':{'filename_prefix':'run/a','seed':1}}}}
    b={'identity':identity('D:/VideoSi/copy.txt'),'graph':{'1':{'inputs':{'filename_prefix':'run/b','seed':1}}}}
    roles={('graph','1','inputs','filename_prefix'):'output'}
    assert signature(a,graph_roles=roles)==signature(b,graph_roles=roles)
    assert signature(a)!=signature(b)
    b['graph']['1']['inputs']['seed']=2
    assert signature(a,graph_roles=roles)!=signature(b,graph_roles=roles)
    with pytest.raises(ValueError):signature({'value':float('nan')})


def test_changes_schema_is_exact_and_shot_ids_known():
    inv=inventory();ch=changes(inv)
    assert validate_changes(ch,run_id=inv.snapshot['run_id'],shot_ids=('shot_0001','shot_0002'))
    ch['unknown']=True
    with pytest.raises(ValueError):validate_changes(ch,run_id=inv.snapshot['run_id'],shot_ids=('shot_0001',))


def test_review_changed_preserves_candidate_but_invalidates_acceptance():
    inv=inventory(reviews={'final_review':identity(),'full_film_acceptance':identity()})
    plan=build_recovery_plan(inv,reviews={'final_review':identity(sha='b'*64)})
    assert not plan.requires_child_run
    assert affected(plan,'publish')=={None}
    assert any(r.stage=='validation' for r in plan.reused)
    assert plan.waiting_for==('full_film_acceptance',)


def test_cue_change_invalidates_timeline_and_reviews():
    inv=inventory(reviews={'timing':identity(),'voice_acceptance':True})
    plan=build_recovery_plan(inv,reviews={'timing':identity(sha='b'*64)})
    assert affected(plan,'timeline')=={None}
    assert not affected(plan,'speech')
    assert plan.requires_child_run


def test_signature_sampling_roles_may_not_be_normalized():
    with pytest.raises(ValueError):
        signature({'graph':{'1':{'inputs':{'seed':12}}}},
                  graph_roles={('graph','1','inputs','seed'):'same_seed'})


def test_real_context_source_units_map_to_shots_and_transitions_review_only():
    inv=inventory();units={s:{k:dict(v) for k,v in rows.items()} for s,rows in inv.unit_records.items()}
    units['storyboard']['shot_0001'].update(primary_unit_id='speech_0001')
    units['storyboard']['shot_0002'].update(primary_unit_id='speech_0002',
        visual_requirements=[{'context_sources':[{'unit_id':'speech_0001'}], 'resolved_references':[]}])
    inv=replace(inv,unit_records=units)
    ch=changes(inv,[dict(shot_id='shot_0001',image_prompt='new',video_prompt=None,reason='repair')])
    plan=build_recovery_plan(inv,changes=ch)
    assert affected(plan,'start_images')=={'shot_0001','shot_0002'}


def test_shared_reference_index_real_shape_closes_dependents():
    inv=inventory();records={s:dict(v) for s,v in inv.stage_records.items()}
    records['start_images']['receipt']={'reference_index':[
        {'entity_id':'hero','reference_shot_id':'shot_0001'}],
        'images':{'shot_0002':{'reference_entity_ids':['hero']}}}
    inv=replace(inv,stage_records=records)
    ch=changes(inv,[dict(shot_id='shot_0001',image_prompt='new',video_prompt=None,reason='repair')])
    assert affected(build_recovery_plan(inv,changes=ch),'start_images')=={'shot_0001','shot_0002'}


def test_running_incomplete_unsubmitted_prefix_reused_in_child():
    inv=inventory();records={s:dict(v) for s,v in inv.stage_records.items()}
    records['source_clips']['status']='interrupted'
    inv=replace(inv,stage_records=records)
    plan=build_recovery_plan(inv)
    assert plan.requires_child_run
    assert plan.operations[0].action=='derive'
    assert any(r.stage=='source_clips' and r.unit_id=='shot_0001' for r in plan.reused)


def test_unrepresented_local_failed_unit_needs_explicit_retry():
    inv=inventory();units={s:{k:dict(v) for k,v in rows.items()} for s,rows in inv.unit_records.items()}
    units['source_clips']['shot_0001']['status']='failed'
    inv=replace(inv,unit_records=units)
    assert build_recovery_plan(inv).refusal_reasons
    assert build_recovery_plan(inv,retry_failed=True).requires_child_run


def test_transition_peer_revalidation_closure_does_not_regenerate_peer():
    inv=inventory();records={s:dict(v) for s,v in inv.stage_records.items()}
    records['composition']['receipt']={'plan':{'ordered_frame_map':[
        {'contributors':[{'shot_id':'shot_0001','weight_numerator':1},
                         {'shot_id':'shot_0002','weight_numerator':1}]}]}}
    inv=replace(inv,stage_records=records)
    ch=changes(inv,[dict(shot_id='shot_0001',image_prompt=None,video_prompt='repair',reason='repair')])
    plan=build_recovery_plan(inv,changes=ch)
    assert affected(plan,'source_clips')=={'shot_0001'}
    assert any(r.stage=='composition' and r.unit_id=='shot_0002' and 'transition' in r.reason
               for r in plan.invalidated)


def test_formal_storyboard_rows_supply_known_shots_even_without_unit_manifest_rows():
    inv=inventory();records={s:dict(v) for s,v in inv.stage_records.items()}
    records['storyboard']['receipt']={'shots':[{'shot_id':'shot_0001','image_prompt':'old','video_prompt':'old'}]}
    inv=replace(inv,stage_records=records,unit_records={})
    ch=changes(inv,[dict(shot_id='shot_0001',image_prompt=None,video_prompt='repair',reason='repair')])
    plan=build_recovery_plan(inv,changes=ch)
    assert not plan.refusal_reasons
    assert affected(plan,'source_clips')=={'shot_0001'}


def test_terminal_failed_but_proven_unsent_suffix_does_not_require_retry():
    inv=inventory();records={s:dict(r) for s,r in inv.stage_records.items()}
    records['source_clips']['status']='failed'
    inv=replace(inv,stage_records=records,checkpoints={'source_clips':{
        'verified_units':('shot_0001',),'remaining_units':('shot_0002',),'unsent_verified':True}})
    plan=build_recovery_plan(inv)
    assert not plan.refusal_reasons and plan.requires_child_run
    assert plan.operations[0].action=='derive'


def test_failed_local_unit_covered_by_exact_unsent_suffix_needs_no_retry():
    inv=inventory();records={s:dict(r) for s,r in inv.stage_records.items()}
    records['source_clips']['status']='failed'
    units={s:{k:dict(v) for k,v in rows.items()} for s,rows in inv.unit_records.items()}
    units['source_clips']['shot_0002']['status']='failed'
    inv=replace(inv,stage_records=records,unit_records=units,checkpoints={'source_clips':{
        'verified_units':('shot_0001',),'remaining_units':('shot_0002',),'unsent_verified':True}})
    plan=build_recovery_plan(inv)
    assert not plan.refusal_reasons and plan.operations[0].action=='derive'
    inv=replace(inv,checkpoints={'source_clips':{
        'verified_units':('shot_0001',),'remaining_units':(),'unsent_verified':True}})
    assert build_recovery_plan(inv).refusal_reasons


@pytest.mark.parametrize('retry',[False,True])
def test_tts_ambiguous_first_request_without_submission_never_derives_or_prepares(retry):
    inv=inventory();records={s:dict(r) for s,r in inv.stage_records.items()}
    records['speech']['status']='ambiguous'
    inv=replace(inv,stage_records=records,unit_records={'speech':{
        'reference_replay':{'status':'ambiguous','submission':None,'durable_tts_intent':True}}})
    plan=build_recovery_plan(inv,retry_failed=retry)
    assert not plan.requires_child_run and not plan.refusal_reasons
    assert any(op.action=='reconcile' and op.stage=='speech' and op.unit_id=='reference_replay' for op in plan.operations)
    assert not any(op.action in ('derive','prepare') for op in plan.operations)


def test_verified_failed_completed_media_unit_only_explicit_retry_invalidates_native_unit():
    inv=inventory();records={s:dict(r) for s,r in inv.stage_records.items()};records['upscale']['status']='failed'
    units={'upscale':{'shot_0001:frame_000001':{'status':'failed','submission':{'state':'completed'}}}}
    inv=replace(inv,stage_records=records,unit_records=units,
        submissions={'upscale':{'shot_0001:frame_000001':{'state':'completed'}}},
        checkpoints={'upscale':{'known_failed_units':{'shot_0001:frame_000001':{'evidence_identities':(identity(),)}}}})
    assert build_recovery_plan(inv).refusal_reasons
    plan=build_recovery_plan(inv,retry_failed=True)
    assert not plan.refusal_reasons
    assert any(row.unit_id=='shot_0001:frame_000001' and row.reason.startswith('explicit failed') for row in plan.invalidated)


def test_explicit_failed_speech_retry_preserves_exact_target_and_invalidates_all_downstream():
    inv=inventory();records={s:dict(r) for s,r in inv.stage_records.items()};records['speech']['status']='failed'
    units=dict(inv.unit_records,speech={'speech_0001':{'status':'completed'},'speech_0002':{'status':'failed','submission':None}})
    inv=replace(inv,stage_records=records,unit_records=units,
        checkpoints={'speech':{'known_failed_units':{'speech_0002':{'reason':'complete HTTP400'}},
            'verified_units':{'speech_0001':{'record':units['speech']['speech_0001']}},'remaining_units':('speech_0002',),'unsent_verified':False}})
    assert build_recovery_plan(inv).refusal_reasons
    plan=build_recovery_plan(inv,retry_failed=True)
    assert not plan.refusal_reasons and affected(plan,'speech')=={'speech_0002'}
    assert any(row.stage=='speech' and row.unit_id=='speech_0001' for row in plan.reused)
    assert all(affected(plan,stage)=={None} for stage in STAGES[STAGES.index('timeline'):])
    assert not any(row.stage=='speech' and row.unit_id is None for row in plan.reused)


def test_parent_snapshot_independent_verification_timestamp_does_not_drift():
    inv=inventory();ch=changes(inv)
    ch['base_manifest_snapshot_identity']['verified_at']='2026-10-05T01:00:00+00:00'
    assert validate_changes(ch,run_id=inv.snapshot['run_id'],shot_ids=(),snapshot_identity=inv.snapshot['identity'])


def test_explicit_publish_never_starts_unfinished_upstream_work():
    inv=inventory();records={s:dict(r) for s,r in inv.stage_records.items()}
    records['validation']['status']='pending'
    inv=replace(inv,stage_records=records)
    plan=build_recovery_plan(inv,publish=True)
    assert plan.refusal_reasons
    assert not plan.operations
