from copy import deepcopy
import pytest
from final_review_helpers import review_fixture, NOW, VERDICTS


def run_review(f):
    from video_ai.planning.final_review import validate_final_review
    c,t,r,o,co,*_=f
    return validate_final_review(r,c,t,observations=o,cue_observations=co,now_value=NOW)


def run_acceptance(f):
    from video_ai.planning.final_review import validate_acceptance
    c,_,r,_,_,a,collection=f
    return validate_acceptance(a,c,r,collection,now_value=NOW)


@pytest.mark.parametrize('fps',[16,24])
def test_complete_continuous_final_review_and_human_acceptance(fps):
    f=review_fixture(fps)
    assert run_review(f)==dict(actual_final_video_semantics='passed',actual_final_video_sync='passed')
    assert run_acceptance(f)==dict(full_film_acceptance='passed')


@pytest.mark.parametrize('field',VERDICTS+['global_verdict'])
@pytest.mark.parametrize('verdict',['failed','unverified'])
def test_global_pass_never_overrides_unpassed_required_check(field,verdict):
    f=review_fixture();r=f[2]
    (r if field=='global_verdict' else r['entries'][0])[field]=verdict
    with pytest.raises(ValueError):run_review(f)


@pytest.mark.parametrize('mutation',[
    lambda r:r['entries'].pop(),lambda r:r['entries'].append(deepcopy(r['entries'][0])),
    lambda r:r['entries'].reverse(),lambda r:r['entries'][0].update(role='quantization_edge_review'),
    lambda r:r.update(review_method='agent_text'),lambda r:r.update(schema_version=True),
    lambda r:r.update(reviewed_at='2026-10-06T00:00:00+08:00'),lambda r:r.update(reviewed_at='2026-10-04T00:00:00+08:00'),
    lambda r:r.update(extra=1),lambda r:r['candidate_identity'].update(mtime_ns=2),
    lambda r:r['candidate_identity'].update(verified_at='2026-10-06T00:00:00+08:00'),
    lambda r:r['entries'][0]['candidate_sample_ranges'][0].update(start=1),
    lambda r:r['entries'][0]['actual_artifact'].update(bytes=True),
    lambda r:r['cue_entries'].pop(),lambda r:r['cue_entries'].reverse(),
    lambda r:r['cue_entries'][0].update(kind='automated_audio'),
    lambda r:r['cue_entries'][0].update(audio_uncertainty_samples=True),
    lambda r:r['cue_entries'][0].update(audio_sample=float('nan')),
    lambda r:r['cue_entries'][0].update(audio_uncertainty_samples=3001),
    lambda r:r['cue_entries'][0]['actual_change_frames'].update(end=19),
    lambda r:r['cue_entries'][0].update(audio_sample=47999),
])
def test_rejects_incomplete_wrong_association_identity_time_and_cue(mutation):
    f=deepcopy(review_fixture());mutation(f[2])
    with pytest.raises(ValueError):run_review(f)


@pytest.mark.parametrize('mutation',[
    lambda o:o['entries'][0].update(playback_frame_ranges=[]),
    lambda o:o['entries'][0].update(playback_sample_ranges=[]),
    lambda o:o['entries'][0].update(process_observation=''),
    lambda o:o['entries'].append(deepcopy(o['entries'][0])),
    lambda o:o.update(viewed_at='2026-10-05T02:30:00+08:00'),
    lambda o:o.update(review_method='agent_text'),
    lambda o:o['entries'][0].update(sync_observation=dict(requires_action_cue=True,action_cue_ids=['missing'],
        onset_observation='onset',interval_observation='interval',reason='required internal event')),
    lambda o:o['entries'][0]['sync_observation'].pop('requires_action_cue'),
])
def test_rejects_missing_continuous_observation_or_action_evidence(mutation):
    f=deepcopy(review_fixture());mutation(f[3]['logs/validation/observations.json'])
    with pytest.raises(ValueError):run_review(f)


def test_one_frame_integer_budget_includes_uncertainty_and_observed_interval():
    f=deepcopy(review_fixture());cue=f[2]['cue_entries'][0]
    cue['audio_uncertainty_samples']=3000
    cue['audio_sample']=51000
    cue['actual_change_frames']=dict(start=17,end=18)
    f[4]['logs/validation/cues.json']['entries'][0]['audio_uncertainty_samples']=3000
    f[4]['logs/validation/cues.json']['entries'][0]['audio_sample']=51000
    f[4]['logs/validation/cues.json']['entries'][0]['actual_change_frames']=dict(start=17,end=18)
    assert run_review(f)['actual_final_video_sync']=='passed'
    cue['actual_change_frames']['end']+=1
    f[4]['logs/validation/cues.json']['entries'][0]['actual_change_frames']['end']+=1
    with pytest.raises(ValueError):run_review(f)


@pytest.mark.parametrize('field,value',[
    ('review_method','agent_video'),('review_method','human_video'),('full_film_watched',False),
    ('full_audio_listened',False),('subtitle_checked',1),('verdict','unverified'),('reason',''),
    ('reviewed_at','2026-10-05T01:00:00+08:00'),('reviewed_at','2026-10-06T00:00:00+08:00')])
def test_acceptance_requires_exact_human_full_film_gate(field,value):
    f=deepcopy(review_fixture());f[5][field]=value
    with pytest.raises(ValueError):run_acceptance(f)


def test_acceptance_rejects_collection_omission_and_stale_review():
    f=deepcopy(review_fixture());f[5]['review_collection_identities'].pop('logs/validation/cues.json')
    with pytest.raises(ValueError):run_acceptance(f)


def add_action(f,*,sample=24000,cue_id='action_test_1'):
    c,t,r,o,co,*_=f
    requirement=c['requirement_bindings'][0]
    unit=requirement['unit_id']
    base=dict(cue_id=cue_id,requirement_id=requirement['requirement_id'],kind='action',from_unit_id=unit,to_unit_id=unit,
        pcm_identity=deepcopy(c['input_identities']['pcm/'+unit]),timeline_identity=deepcopy(c['input_identities']['timeline']),
        candidate_identity=deepcopy(c['candidate_identity']),audio_sample=sample,audio_uncertainty_samples=0,
        actual_change_frames=dict(start=8,end=9))
    r['cue_entries'].append(dict(base,evidence_identity=deepcopy(r['cue_entries'][0]['evidence_identity']),verdict='passed',
        reason='TEST ONLY internal movement at observed sample/frame, conservative exact bound.'))
    co['logs/validation/cues.json']['entries'].append(dict(base,audio_observation='TEST ONLY exact spoken event.',
        video_observation='TEST ONLY continuous action change.',full_interval_played=True))
    sync=o['logs/validation/observations.json']['entries'][0]['sync_observation']
    sync.update(requires_action_cue=True,action_cue_ids=[cue_id],reason='TEST ONLY internal event requires exact audio/video onset.')


def test_explicit_internal_action_cue_and_bidirectional_association():
    f=review_fixture();add_action(f)
    assert run_review(f)['actual_final_video_sync']=='passed'
    sync=f[3]['logs/validation/observations.json']['entries'][0]['sync_observation']
    sync.update(requires_action_cue=False,action_cue_ids=[])
    with pytest.raises(ValueError):run_review(f)


@pytest.mark.parametrize('mutation',[
    lambda f:f[2]['cue_entries'][-1].update(cue_id=f[2]['cue_entries'][0]['cue_id']),
    lambda f:f[2]['cue_entries'][-1].update(from_unit_id='wrong'),
    lambda f:f[2]['cue_entries'][-1].update(requirement_id='wrong'),
    lambda f:f[3]['logs/validation/observations.json']['entries'][0]['sync_observation'].update(action_cue_ids=[]),
    lambda f:f[3]['logs/validation/observations.json']['entries'][0]['sync_observation'].update(requires_action_cue=False),
    lambda f:f[4]['logs/validation/cues.json']['entries'][-1].update(full_interval_played=1),
])
def test_action_cue_must_belong_to_requirement_and_have_actual_complete_evidence(mutation):
    f=review_fixture();add_action(f);mutation(f)
    with pytest.raises(ValueError):run_review(f)


def test_fade_observation_contains_both_actual_positive_weight_extremes():
    f=review_fixture(transition='fade',seconds=.25)
    assert run_review(f)['actual_final_video_sync']=='passed'
    cue=f[2]['cue_entries'][0]
    assert cue['actual_change_frames']==dict(start=15,end=17)
    cue['actual_change_frames']=dict(start=16,end=17)
    f[4]['logs/validation/cues.json']['entries'][0]['actual_change_frames']=dict(start=16,end=17)
    with pytest.raises(ValueError):run_review(f)


def test_all_thirteen_mixed_primary_and_quantization_edge_associations_are_ordered():
    f=review_fixture();c,_,r,o,*_=f
    original=c['requirement_bindings'];original_review=r['entries'];original_observation=o['logs/validation/observations.json']['entries']
    c['requirement_bindings']=[];r['entries']=[];o['logs/validation/observations.json']['entries']=[]
    for i in range(13):
        template=i%len(original)
        role='primary' if i%2==0 else 'quantization_edge_review'
        for destination,source in [(c['requirement_bindings'],original),(r['entries'],original_review),
            (o['logs/validation/observations.json']['entries'],original_observation)]:
            row=deepcopy(source[template]);row.update(shot_id=f'shot_{i+1:04d}',requirement_index=i,
                requirement_id=f'shot_{i+1:04d}:req_test',role=role)
            destination.append(row)
    assert run_review(f)['actual_final_video_semantics']=='passed'
    r['entries'][1],r['entries'][2]=r['entries'][2],r['entries'][1]
    with pytest.raises(ValueError):run_review(f)


@pytest.mark.parametrize('key,value', [('bytes',None),('mtime_ns',None),('sha256',None),
    ('verified_at',None),('verified_at','2026-10-05T00:00:00'),('extra',1)])
def test_full_identity_shape_and_timestamps_required(key,value):
    f=review_fixture();f[2]['candidate_identity'][key]=value
    with pytest.raises(ValueError):run_review(f)


@pytest.mark.parametrize('mutation',[
    lambda f:f[3]['logs/validation/observations.json'].update(viewed_at='2026-10-04T23:00:00+08:00'),
    lambda f:f[4]['logs/validation/cues.json'].update(viewed_at='2026-10-05T02:30:00+08:00'),
    lambda f:f[3].update({'logs/validation/extra.json':deepcopy(f[3]['logs/validation/observations.json'])}),
    lambda f:f[3].update({'logs/validation/./alias.json':deepcopy(f[3]['logs/validation/observations.json'])}),
    lambda f:f[4]['logs/validation/cues.json']['entries'][0].update(audio_observation=''),
    lambda f:f[4]['logs/validation/cues.json'].update(review_method='automated_audio'),
])
def test_observations_reject_stale_future_alias_extra_and_automated_sources(mutation):
    f=review_fixture();mutation(f)
    with pytest.raises(ValueError):run_review(f)


def test_identity_verification_time_may_change_without_changing_stable_bytes():
    f=review_fixture();f[2]['candidate_identity']['verified_at']='2026-10-05T02:30:00+08:00'
    assert run_review(f)['actual_final_video_semantics']=='passed'
    f[5]['review_collection_identities']['logs/validation/cues.json']['verified_at']='2026-10-05T02:30:00+08:00'
    assert run_acceptance(f)['full_film_acceptance']=='passed'


def test_acceptance_binds_review_to_same_candidate():
    f=review_fixture();f[2]['candidate_identity']['mtime_ns']=9
    with pytest.raises(ValueError):run_acceptance(f)


@pytest.mark.parametrize('mutation',[
    lambda f:f[6].update({'logs/validation/extra.json':deepcopy(f[6]['logs/validation/cues.json'])}),
    lambda f:f[6].update({'logs/validation/./review.json':deepcopy(f[6]['logs/validation/review.json'])}),
    lambda f:f[5]['review_collection_identities']['logs/validation/cues.json'].update(sha256='b'*64),
    lambda f:f[5].update(final_review_identity=None),
    lambda f:f[5].update(extra=1),
])
def test_acceptance_rejects_extra_alias_replaced_or_malformed_collection(mutation):
    f=review_fixture();mutation(f)
    with pytest.raises(ValueError):run_acceptance(f)


def test_actions_follow_requirement_then_sample_order():
    f=review_fixture();add_action(f,cue_id='action_first')
    add_action(f,sample=27000,cue_id='action_second')
    f[2]['cue_entries'][-1]['actual_change_frames']=dict(start=9,end=10)
    f[4]['logs/validation/cues.json']['entries'][-1]['actual_change_frames']=dict(start=9,end=10)
    f[3]['logs/validation/observations.json']['entries'][0]['sync_observation']['action_cue_ids']=['action_first','action_second']
    assert run_review(f)['actual_final_video_sync']=='passed'
    f[2]['cue_entries'][-1],f[2]['cue_entries'][-2]=f[2]['cue_entries'][-2],f[2]['cue_entries'][-1]
    with pytest.raises(ValueError):run_review(f)
    f=deepcopy(review_fixture());f[5]['final_review_identity']['mtime_ns']=4
    with pytest.raises(ValueError):run_acceptance(f)
