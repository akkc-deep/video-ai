"""Content invalidation is separate from admission of unchanged scene media."""
from copy import deepcopy
from uuid import UUID

import pytest

from video_ai.planning.production_scenes import canonical_digest
from video_ai.planning.production_visual_plan import plan_scene_clips
from video_ai.planning.visual_consistency import derive_reference_graph


def revision_fixture(kind='reselect_images'):
    bible = dict(entities=[dict(entity_id=f'entity_{i:04d}') for i in range(1, 4)],
                 appearance_variants=[], scene_groups=[dict(group_id=f'group_{i:04d}') for i in range(1, 5)])
    scenes = [dict(scene_id=f'scene_{i:04d}', entity_ids=entities, variant_ids=[],
                   scene_group_id=f'group_{i:04d}', start_frame=(i-1)*13, end_frame=i*13)
              for i, entities in enumerate([
                  ['entity_0001'], ['entity_0001', 'entity_0002'],
                  ['entity_0002'], ['entity_0003']], 1)]
    baselines, bindings, dependencies, batches = derive_reference_graph(scenes, bible)
    bible['baselines'] = baselines
    for scene, refs, deps in zip(scenes, bindings, dependencies):
        scene.update(reference_bindings=refs, dependencies=deps)
    plan = dict(scenes=scenes, batches=batches, total_frames=52)
    plan['clips'] = plan_scene_clips(plan, max_clip_seconds=0.5)
    identity = dict(config_sha256='a'*64, image_generation={'req_key': 'image-v1'},
        reference_settings_sha256=None, model_stamps={}, workflows={},
        voice_sha256='b'*64, font_sha256='c'*64, planning_sha256='d'*64)
    # Runtime has already validated the frozen options, node rows and candidates.
    options = dict(run_id='20261020-000000-abcdef123456',
        image_generation=deepcopy(identity['image_generation']),
        config_snapshot={'raw': {}}, voice_snapshot={'raw': {}},
        model_stamps={}, workflow_snapshots={},
        execution_policy={'input_identities': {}})
    choices = [dict(scene_id=s['scene_id'], candidate_id='request_01_image_01',
                    sha256='1'*64, path=f'D:/VideoSi/source/{s["scene_id"]}.png',
                    bytes=123, req_key='image-v1', request_id='request_01', task_id='task-1')
               for s in scenes]
    clips = [dict(clip_id=c['clip_id'], record={'clip_id': c['clip_id']},
                  acceptance={'verdict': 'passed'}, status='accepted') for c in plan['clips']]
    upscaled = [dict(frame_id=f'{c["clip_id"]}:frame_{n+1:06d}',
                     record={'clip_id': c['clip_id']}, status='ready')
                for c in plan['clips'] for n in range(c['retained_frames'])]
    snapshot = dict(source_options=options, bible=bible, scene_plan=plan,
                    image_choices=choices, clip_nodes=clips,
                    upscale_nodes=upscaled, pending_effects=[])
    request = dict(schema_version=2, production_strategy='paragraph_jimeng_v1',
        revision_id=str(UUID(int=7)), source_run_id=options['run_id'],
        source_options_sha256='e'*64, requested_at='2026-10-19T00:00:00+00:00',
        kind=kind, scene_ids=['scene_0001'], clip_ids=[],
        choices=[dict(scene_id='scene_0001', candidate_id='request_02_image_01', sha256='2'*64)],
        config_path=None, image_model=None, output_path=None, reason='Change baseline choice')
    return snapshot, request, identity


def test_reselected_baseline_invalidates_reference_descendants_but_preserves_unrelated_scene():
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = revision_fixture()
    before = deepcopy((snapshot, request, identity))
    result = plan_scene_revision(snapshot, request, identity)
    assert result['dirty']['images'] == ['scene_0002', 'scene_0003']
    assert result['dirty']['choices'] == ['scene_0001', 'scene_0002', 'scene_0003']
    assert result['reusable']['images'] == ['scene_0001', 'scene_0004']
    assert result['reusable']['choices'] == ['scene_0004']
    for domain in ('clips', 'clip_reviews'):
        assert result['dirty'][domain] == [c['clip_id'] for c in snapshot['scene_plan']['clips']
                                            if c['scene_id'] != 'scene_0004']
        assert result['reusable'][domain] == [c['clip_id'] for c in snapshot['scene_plan']['clips']
                                               if c['scene_id'] == 'scene_0004']
    assert len(result['dirty']['upscale']) == 39
    assert len(result['reusable']['upscale']) == 13
    for domain in ('image_group', 'composition', 'final_review', 'delivery'):
        assert result['dirty'][domain] == ['all']
        assert result['reusable'][domain] == []
    assert result['reusable']['common'] == result['reusable']['plan'] == ['all']
    assert result['blocked_effects'] == []
    assert result['request_sha256'] == canonical_digest(request)
    assert result['target_identity_sha256'] == canonical_digest(identity)
    assert (snapshot, request, identity) == before


def invoke(kind='regenerate_images', **overrides):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = revision_fixture(kind)
    request['choices'] = []
    if kind == 'regenerate_clips':
        request.update(scene_ids=[], clip_ids=[snapshot['scene_plan']['clips'][1]['clip_id']])
    request.update(overrides)
    return plan_scene_revision(snapshot, request, identity), snapshot


def test_regenerated_baseline_invalidates_own_candidates_and_all_reference_descendants():
    result, _ = invoke()
    assert result['dirty']['images'] == ['scene_0001','scene_0002','scene_0003']
    assert result['reusable']['images'] == ['scene_0004']


def test_clip_regeneration_invalidates_only_parent_continuations_and_not_prior_or_other_scene():
    result, snapshot = invoke('regenerate_clips')
    clips = snapshot['scene_plan']['clips']
    assert result['dirty']['clips'] == [r['clip_id'] for r in clips[1:3]]
    assert result['dirty']['upscale'] == [r['frame_id'] for r in snapshot['upscale_nodes']
                                         if r['record']['clip_id'] in result['dirty']['clips']]
    assert result['dirty']['images'] == result['dirty']['choices'] == result['dirty']['image_group'] == []
    assert result['reusable']['image_group'] == ['all']


@pytest.mark.parametrize('field,value', [
    ('schema_version',True), ('schema_version',1), ('production_strategy','legacy'),
    ('revision_id','00000000000000000000000000000007'), ('revision_id','no'),
    ('source_run_id','other'), ('source_options_sha256','bad'), ('reason','  '),
    ('requested_at','2020-01-01T00:00:00'), ('requested_at','9999-01-01T00:00:00+00:00'),
    ('scene_ids',['scene_0001','scene_0001']), ('scene_ids',['scene_9999']),
    ('scene_ids',[True]), ('clip_ids',['clip_9999']), ('choices',None),
    ('config_path','D:/config.json'), ('image_model','model'), ('output_path','D:/out.mp4'),
    ('extra',1), ('kind','automatic_retry')])
def test_invalid_revision_request_is_rejected(field, value):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = revision_fixture()
    request[field] = value
    with pytest.raises((ValueError, TypeError)): plan_scene_revision(snapshot, request, identity)


def test_same_candidate_reselection_is_not_a_revision():
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = revision_fixture()
    request['choices'] = [{k:snapshot['image_choices'][0][k] for k in ('scene_id','candidate_id','sha256')}]
    with pytest.raises(ValueError, match='no change'): plan_scene_revision(snapshot, request, identity)


@pytest.mark.parametrize('domain,status', [('clips','unknown'),('clips','running'),('upscale','unknown')])
def test_pending_paid_nodes_block_new_logical_generation(domain, status):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = revision_fixture('regenerate_clips')
    request.update(choices=[],scene_ids=[],clip_ids=[snapshot['scene_plan']['clips'][0]['clip_id']])
    key = request['clip_ids'][0] if domain == 'clips' else snapshot['upscale_nodes'][0]['frame_id']
    effect = dict(node=domain+':'+key, intent_sha256='f'*64, status=status)
    snapshot['pending_effects'] = [effect]
    result = plan_scene_revision(snapshot, request, identity)
    assert result['blocked_effects'] == [effect]


@pytest.mark.parametrize('status', ['pending','rejected','unknown','running'])
def test_unaccepted_unrelated_clip_is_not_reusable(status):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = revision_fixture()
    row = snapshot['clip_nodes'][-1]; row['status'] = status; row['acceptance'] = None
    result = plan_scene_revision(snapshot, request, identity)
    assert row['clip_id'] not in result['reusable']['clips']


def configure_revision(change):
    from video_ai.planning.scene_revision import identity_from_options
    snapshot, request, _ = revision_fixture('reconfigure')
    identity = identity_from_options(snapshot['source_options'])
    request.update(scene_ids=[],choices=[],config_path='D:/VideoSi/config.json')
    change(identity)
    return snapshot, request, identity


@pytest.mark.parametrize('field,domain', [('image_generation','images'),('voice_sha256','common'),
                                         ('font_sha256','common'),('planning_sha256','common')])
def test_effective_config_differences_invalidate_content(field, domain):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = configure_revision(lambda i:i.update({field:{'req_key':'other'} if field=='image_generation' else 'e'*64}))
    result = plan_scene_revision(snapshot, request, identity)
    assert result['dirty'][domain]
    if domain=='images': assert result['reusable']['common'] == ['all']


@pytest.mark.parametrize('role,domain', [('wan_high','clips'),('wan_low','clips'),('text_encoder','clips'),
    ('vae','clips'),('upscale','upscale'),('gpt_weights','common'),('sovits_weights','common')])
def test_model_stamp_changes_invalidate_results_despite_unchanged_names(role, domain):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = configure_revision(lambda i:i['model_stamps'].update({role:{'sha256':'e'*64}}))
    result = plan_scene_revision(snapshot, request, identity)
    assert result['dirty'][domain]
    if domain != 'common': assert result['dirty']['images'] == []
    if domain == 'upscale': assert result['dirty']['clips'] == []


@pytest.mark.parametrize('role,domain', [('wan','clips'),('wan_mapping','clips'),('upscale','upscale'),('upscale_mapping','upscale')])
def test_workflow_bytes_changes_invalidate_results(role, domain):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = configure_revision(lambda i:i['workflows'].update({role:{'sha256':'e'*64}}))
    assert plan_scene_revision(snapshot, request, identity)['dirty'][domain]


def test_reference_settings_change_only_dirties_reference_images_and_descendants():
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, identity = configure_revision(lambda i:i.update(reference_settings_sha256='f'*64))
    result = plan_scene_revision(snapshot, request, identity)
    assert result['dirty']['images'] == ['scene_0002','scene_0003']
    assert result['dirty']['clips'] == [c['clip_id'] for c in snapshot['scene_plan']['clips'] if c['scene_id'] in ('scene_0002','scene_0003')]


def test_same_effective_configuration_rejected():
    from video_ai.planning.scene_revision import plan_scene_revision
    with pytest.raises(ValueError,match='no effective change'):
        plan_scene_revision(*configure_revision(lambda i:None))


def test_reconfigure_cannot_change_frozen_email_addresses():
    from video_ai.planning.scene_revision import plan_scene_revision, identity_from_options
    snapshot, request, identity = configure_revision(lambda i:i.update(config_sha256='e'*64))
    snapshot['source_options']['config_snapshot']['raw']['email_notification'] = {'sender':'old@example.com','recipient':'old@example.com'}
    # Address restrictions are checked by runtime against the target config before
    # hashing: the pure identity does not disclose recipient addresses.
    assert plan_scene_revision(snapshot, request, identity)['dirty']['common'] == ['all']


def test_request_id_order_does_not_change_plan_node_order():
    from video_ai.planning.scene_revision import plan_scene_revision
    result, _ = invoke(scene_ids=['scene_0003','scene_0001'])
    assert result['dirty']['images'] == ['scene_0001','scene_0002','scene_0003']


def test_frame_mapping_and_graph_are_json_serializable():
    import json
    from video_ai.planning.scene_revision import plan_scene_revision
    result, snapshot = invoke('regenerate_clips')
    assert canonical_digest(json.loads(json.dumps(result))) == canonical_digest(result)
    assert all(set(row)=={'source','target'} for row in result['content_edges']+result['admission_edges'])


def test_completed_candidate_set_remains_reusable_before_its_choice_is_confirmed():
    from video_ai.planning.scene_revision import plan_scene_revision,identity_from_options
    snapshot,request,identity=revision_fixture()
    snapshot['image_choices']=[c for c in snapshot['image_choices'] if c['scene_id']!='scene_0004']
    snapshot['source_options']['_scene_revision_planning']=dict(
        identity=identity_from_options(snapshot['source_options']),
        completed_image_ids=['scene_0001','scene_0002','scene_0003','scene_0004'],image_group_accepted=False,target_config=None)
    result=plan_scene_revision(snapshot,request,identity)
    assert 'scene_0004' in result['reusable']['images']
    assert 'scene_0004' not in result['reusable']['choices']


def test_verified_late_bound_reference_identity_is_not_dirtied_by_only_upscale_change():
    from video_ai.planning.scene_revision import plan_scene_revision,identity_from_options
    snapshot,request,identity=configure_revision(lambda i:i['model_stamps'].update(upscale={'path':'same-model','bytes':1,'mtime_ns':2}))
    original=identity_from_options(snapshot['source_options'],reference_settings_sha256='e'*64)
    identity['reference_settings_sha256']='e'*64
    snapshot['source_options']['_scene_revision_planning']=dict(identity=original,
        completed_image_ids=[s['scene_id'] for s in snapshot['scene_plan']['scenes']],image_group_accepted=True,target_config={})
    result=plan_scene_revision(snapshot,request,identity)
    assert result['dirty']['images']==result['dirty']['clips']==[]
    assert result['dirty']['upscale']


def test_verified_profile_only_config_change_invalidates_wan_but_preserves_common_and_images():
    from video_ai.planning.scene_revision import plan_scene_revision,identity_from_options
    snapshot,request,_=configure_revision(lambda i:None)
    raw={'media':{'profile':'fast'}}
    snapshot['source_options']['config_snapshot']['raw']=raw
    original=identity_from_options(snapshot['source_options'])
    target_raw={'media':{'profile':'quality'}}
    target_options=deepcopy(snapshot['source_options']);target_options['config_snapshot']['raw']=target_raw
    target=identity_from_options(target_options)
    snapshot['source_options']['_scene_revision_planning']=dict(identity=original,
        completed_image_ids=[s['scene_id'] for s in snapshot['scene_plan']['scenes']],image_group_accepted=True,target_config=target_raw)
    result=plan_scene_revision(snapshot,request,target)
    assert result['dirty']['common']==result['dirty']['images']==[]
    assert result['dirty']['clips']==[c['clip_id'] for c in snapshot['scene_plan']['clips']]


def test_admission_graph_is_linear_in_total_frames_and_clips():
    result,snapshot=invoke('regenerate_clips')
    frames=len(snapshot['upscale_nodes']);clips=len(snapshot['clip_nodes'])
    assert len(result['admission_edges'])<=4*frames+8*clips+20
    children={}
    for edge in result['admission_edges']:children.setdefault(edge['source'],[]).append(edge['target'])
    def reachable(start):
        seen=set();todo=[start]
        while todo:
            node=todo.pop()
            if node in seen:continue
            seen.add(node);todo.extend(children.get(node,[]))
        return seen
    for clip in snapshot['clip_nodes']:
        reached=reachable('clip_reviews:'+clip['clip_id'])
        assert all('upscale:'+frame['frame_id'] in reached for frame in snapshot['upscale_nodes'])


def test_voice_identity_binds_reference_content_and_not_the_frozen_copy_filename():
    from video_ai.planning.scene_revision import identity_from_options
    snapshot,_,_=revision_fixture()
    source=snapshot['source_options']
    source['voice_snapshot']['raw'].update(reference_audio='D:/VideoSi/source/reference.wav',prompt_text='原声参考')
    source['execution_policy']['input_identities']['reference']=dict(path='D:/VideoSi/source/reference.wav',bytes=100,sha256='a'*64)
    target=deepcopy(source)
    target['voice_snapshot']['raw']['reference_audio']='D:/VideoSi/new-run/production/inputs/reference.wav'
    target['execution_policy']['input_identities']['reference']['path']=target['voice_snapshot']['raw']['reference_audio']
    assert identity_from_options(source)['voice_sha256']==identity_from_options(target)['voice_sha256']
    target['voice_snapshot']['raw']['prompt_text']='另一声线参考'
    assert identity_from_options(source)['voice_sha256']!=identity_from_options(target)['voice_sha256']
