"""TEST ONLY authored observation records; never production acceptance evidence."""
from copy import deepcopy
from composition_helpers import inputs, identity
from video_ai.planning.composition import plan_composition, CompositionSettings
from video_ai.runtime.manifest import thaw

NOW = '2026-10-05T03:00:00+08:00'
CREATED = '2026-10-05T00:00:00+08:00'
VIEWED = '2026-10-05T01:00:00+08:00'
REVIEWED = '2026-10-05T02:00:00+08:00'
VERDICTS = [k+'_verdict' for k in ('text_semantics','video_semantics','motion','sync','quality','continuity')]


def review_fixture(fps=16,transition='cut',seconds=0):
    timeline, storyboard, upscaled, timing = inputs(fps,transition,seconds)
    plan = plan_composition(timeline, storyboard, upscaled, timing, settings=CompositionSettings())
    candidate = dict(run_id='20261005-000000-111111111111', created_at=CREATED,
        candidate_validation_identity=identity('candidate-validation.json'),
        composition_identity=identity('composition.json'), candidate_identity=identity('composition/candidate.mp4'),
        subtitle_identity=identity('composition/subtitle.srt'),
        input_identities=dict(script_copy=identity('script.txt'), timeline=identity('timeline.json')),
        requirement_bindings=thaw(plan.requirement_bindings), cue_checks=thaw(plan.cue_checks),
        effective_media=dict(fps=fps, frames=timeline.total_frames))
    for c in timeline.clips: candidate['input_identities']['pcm/'+c.unit_id] = identity(c.unit_id+'.wav')
    shared = dict(schema_version=1, run_id=candidate['run_id'],
        candidate_validation_identity=candidate['candidate_validation_identity'],
        candidate_identity=candidate['candidate_identity'], review_method='human_video', reviewer='TEST ONLY reviewer')
    review = dict(shared, composition_identity=candidate['composition_identity'],
        subtitle_identity=candidate['subtitle_identity'], script_identity=candidate['input_identities']['script_copy'],
        timeline_identity=candidate['input_identities']['timeline'], reviewed_at=REVIEWED,
        global_verdict='passed', reason='TEST ONLY actual full candidate comparison.', entries=[], cue_entries=[])
    observation = dict(shared, viewed_at=VIEWED, entries=[])
    for row in candidate['requirement_bindings']:
        base = deepcopy(row); base['upscaled_artifact'] = base.pop('actual_artifact')
        base['actual_artifact'] = candidate['candidate_identity']
        base['candidate_sample_ranges'] = [dict(start=r['start']*(48000//fps),end=r['end']*(48000//fps)) for r in row['candidate_frame_ranges']]
        entry = dict(base, evidence_identity=identity('logs/validation/observations.json'), reason='TEST ONLY subject, motion, quantity, negation, context and order checked.')
        entry.update({k:'passed' for k in VERDICTS}); review['entries'].append(entry)
        observation['entries'].append(dict(base, playback_frame_ranges=base['candidate_frame_ranges'],
            playback_sample_ranges=base['candidate_sample_ranges'], start_observation='TEST ONLY actual start.',
            process_observation='TEST ONLY continuous movement.', end_observation='TEST ONLY actual end.',
            audio_text_observation='TEST ONLY complete spoken original.', quality_observation='TEST ONLY encoded quality.',
            continuity_observation='TEST ONLY continuous same subject comparison.',
            sync_observation=dict(requires_action_cue=False, action_cue_ids=[], onset_observation='TEST ONLY actual onset.',
                interval_observation='TEST ONLY full interval.', reason='TEST ONLY continuous state requires no internal event.')))
    cue_shared = dict(schema_version=1, run_id=candidate['run_id'], candidate_validation_identity=candidate['candidate_validation_identity'],
        reviewer='TEST ONLY reviewer',review_method='human_audio_video',viewed_at=VIEWED,entries=[])
    for cue in candidate['cue_checks']:
        base = dict(cue_id=cue['cue_id'],requirement_id=None,kind='boundary',from_unit_id=cue['from_unit_id'],
            to_unit_id=cue['to_unit_id'],pcm_identity=candidate['input_identities']['pcm/'+cue['to_unit_id']],
            timeline_identity=candidate['input_identities']['timeline'],candidate_identity=candidate['candidate_identity'],
            audio_sample=cue['absolute_sample'],audio_uncertainty_samples=0,
            actual_change_frames=dict(start=min(cue['planned_change_frame'],cue['first_positive_contributor_frame']),
                end=max(cue['planned_change_frame'],cue['last_positive_contributor_frame'])+1))
        review['cue_entries'].append(dict(base,evidence_identity=identity('logs/validation/cues.json'),verdict='passed',
            reason='TEST ONLY continuous audio/video establishes exact frame and zero uncertainty.'))
        cue_shared['entries'].append(dict(base,audio_observation='TEST ONLY original PCM onset and order.',
            video_observation='TEST ONLY visible change interval and conservative uncertainty.',full_interval_played=True))
    observations={'logs/validation/observations.json':observation}
    cue_observations={'logs/validation/cues.json':cue_shared}
    review_identity=identity('logs/validation/review.json')
    collection={'logs/validation/review.json':review_identity,'logs/validation/observations.json':identity('logs/validation/observations.json'),
        'logs/validation/cues.json':identity('logs/validation/cues.json')}
    acceptance={k:deepcopy(review[k]) for k in ('schema_version','run_id','candidate_validation_identity','composition_identity',
        'candidate_identity','subtitle_identity','script_identity','timeline_identity')}
    acceptance.update(final_review_identity=review_identity,review_collection_identities=collection,review_method='human_full_film',
        reviewer='TEST ONLY human',reviewed_at=NOW,full_film_watched=True,full_audio_listened=True,subtitle_checked=True,
        verdict='passed',reason='TEST ONLY accept these precise MP4/SRT bytes after full viewing/listening.')
    return tuple(deepcopy(value) for value in (candidate,timeline,review,observations,cue_observations,acceptance,collection))
