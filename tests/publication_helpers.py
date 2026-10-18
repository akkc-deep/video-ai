"""TEST ONLY full author inputs over independent real FFmpeg MP4/SRT bytes."""
from copy import deepcopy
import json
from pathlib import Path
import wave

from candidate_helpers import make_candidate_fixture,write
from video_ai.config import read_json
from video_ai.runtime.manifest import hash_file,thaw,now


def fixture_upstream(run_dir):
    """TEST ONLY replacement for the expensive complete composition consumer."""
    from video_ai.runtime._composition_inputs import fresh
    data=read_json(run_dir/'composition.json')
    for record in data['input_identities'].values():fresh(record)
    fresh(data['candidate_identity']);fresh(data['subtitles']['srt_identity'])
    return data


def make_publication_fixture(runtime_run,monkeypatch):
    from video_ai.runtime.candidate_checks import validate_candidate
    run,config,store,composition=make_candidate_fixture(runtime_run,monkeypatch)
    timeline=read_json(run/'timeline.json')
    for clip in timeline['clips']:
        pcm=run/'audio'/clip['unit_id']/'pcm-48000.wav';pcm.parent.mkdir(parents=True,exist_ok=True)
        if not pcm.exists():
            with wave.open(str(pcm),'wb') as stream:
                stream.setparams((1,2,48000,0,'NONE',''));stream.writeframes(b'\0\0'*clip['samples'])
        composition['input_identities']['pcm/'+clip['unit_id']]=thaw(hash_file(pcm))
    if read_json(run/'composition.json')!=composition:write(run/'composition.json',composition)
    # The fixture upstream mock deliberately treats this complete TEST ONLY
    # composition as expensive upstream evidence; candidate transaction is real.
    result=validate_candidate(config,run_dir=run)
    assert result.passed,'TEST ONLY candidate validation must complete'
    candidate=read_json(run/'candidate-validation.json');candidate_id=thaw(hash_file(run/'candidate-validation.json'))
    author=run/'logs/validation';author.mkdir(exist_ok=True,parents=True)
    shared=dict(schema_version=1,run_id=run.name,candidate_validation_identity=candidate_id,
                candidate_identity=candidate['candidate_identity'],review_method='human_video',reviewer='TEST ONLY author')
    review=dict(shared,composition_identity=candidate['composition_identity'],subtitle_identity=candidate['subtitle_identity'],script_identity=candidate['input_identities']['script_copy'],timeline_identity=candidate['input_identities']['timeline'],reviewed_at=now(),global_verdict='passed',reason='TEST ONLY precise output review.',entries=[],cue_entries=[])
    observation=dict(shared,viewed_at=now(),entries=[])
    fps=candidate['effective_media']['fps']
    for row in candidate['requirement_bindings']:
        base=deepcopy(row);base['upscaled_artifact']=base.pop('actual_artifact');base['actual_artifact']=candidate['candidate_identity']
        base['candidate_sample_ranges']=[dict(start=r['start']*48000//fps,end=r['end']*48000//fps) for r in row['candidate_frame_ranges']]
        review['entries'].append(dict(base,**{k+'_verdict':'passed' for k in ('text_semantics','video_semantics','motion','sync','quality','continuity')},reason='TEST ONLY complete subject/action/setting/quantity/negation/context/order observation.',evidence_identity=None))
        observation['entries'].append(dict(base,playback_frame_ranges=base['candidate_frame_ranges'],playback_sample_ranges=base['candidate_sample_ranges'],start_observation='TEST ONLY actual start.',process_observation='TEST ONLY continuous process.',end_observation='TEST ONLY actual end.',audio_text_observation='TEST ONLY complete original speech.',quality_observation='TEST ONLY actual encoded frames.',continuity_observation='TEST ONLY same object through continuous viewing.',sync_observation=dict(requires_action_cue=False,action_cue_ids=[],onset_observation='TEST ONLY actual spoken onset.',interval_observation='TEST ONLY full spoken and visual interval.',reason='TEST ONLY continuous state; no separate internal event needed.')))
    cue_observation=dict(schema_version=1,run_id=run.name,candidate_validation_identity=candidate_id,reviewer='TEST ONLY author',review_method='human_audio_video',viewed_at=now(),entries=[])
    for cue in candidate['cue_checks']:
        base=dict(cue_id=cue['cue_id'],requirement_id=None,kind='boundary',from_unit_id=cue['from_unit_id'],to_unit_id=cue['to_unit_id'],pcm_identity=candidate['input_identities']['pcm/'+cue['to_unit_id']],timeline_identity=candidate['input_identities']['timeline'],candidate_identity=candidate['candidate_identity'],audio_sample=cue['absolute_sample'],audio_uncertainty_samples=0,actual_change_frames=dict(start=cue['planned_change_frame'],end=cue['planned_change_frame']+1))
        review['cue_entries'].append(dict(base,evidence_identity=None,verdict='passed',reason='TEST ONLY exact onset at visible frame; full interval determines zero uncertainty.'))
        cue_observation['entries'].append(dict(base,audio_observation='TEST ONLY original PCM onset and order.',video_observation='TEST ONLY visible frame interval and uncertainty.',full_interval_played=True))
    observation_path=write(author/'TEST-ONLY-observations.json',observation);cue_path=write(author/'TEST-ONLY-cues.json',cue_observation)
    for row in review['entries']:row['evidence_identity']=thaw(hash_file(observation_path))
    for row in review['cue_entries']:row['evidence_identity']=thaw(hash_file(cue_path))
    review['reviewed_at']=now();review_path=write(author/'TEST-ONLY-review.json',review)
    collection={p.relative_to(run).as_posix():thaw(hash_file(p)) for p in (review_path,observation_path,cue_path)}
    acceptance={k:deepcopy(review[k]) for k in ('schema_version','run_id','candidate_validation_identity','composition_identity','candidate_identity','subtitle_identity','script_identity','timeline_identity')}
    acceptance.update(final_review_identity=thaw(hash_file(review_path)),review_collection_identities=collection,review_method='human_full_film',reviewer='TEST ONLY human',reviewed_at=now(),full_film_watched=True,full_audio_listened=True,subtitle_checked=True,verdict='passed',reason='TEST ONLY accepts these precise fixture bytes; no production review asserted.')
    acceptance_path=write(author/'TEST-ONLY-acceptance.json',acceptance)
    return run,config,store,review_path,acceptance_path


def cleanup_output(config,run):
    """Only exact explicitly test-owned run stem artifacts are removed."""
    root=config.output_root.resolve()
    for name in (run.name+'.mp4',run.name+'.srt',run.name+'.publication.json','.'+run.name+'.publish.lock'):
        path=root/name
        if path.resolve(strict=False).parent!=root:raise ValueError('test output cleanup redirected')
        if path.exists():path.unlink()
    for path in root.glob(run.name+'.publication.json.*.tmp'):
        if path.resolve(strict=False).parent!=root:raise ValueError('test temporary cleanup redirected')
        path.unlink()
