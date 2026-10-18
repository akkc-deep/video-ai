import json
from pathlib import Path

def content_for(slots):
    shots=[]
    for s in slots:
        requirements=[dict(unit_id=b.unit_id,source_quote=b.text,subject=b.text,action_or_state=None,
            setting=None,quantity=None,negation=None,relation_or_order=None,visual_expression=b.text,
            needs_finer_audio=False,context_sources=[],resolved_references=[]) for b in s.bindings if not b.silence_only]
        shots.append(dict(shot_id=s.shot_id,entity_ids=[],composition='16:9',camera_motion='slow pan',
            action_start='start',action_end='end',image_prompt='16:9 image',video_prompt='visible motion',visual_requirements=requirements))
    return dict(schema_version=1,global_visual=dict(style='realistic',color_palette='blue',lighting='night',entities=[]),shots=shots)


def make_storyboard_run(timeline_run):
    from video_ai.runtime.timeline_checks import plan_timeline,load_committed_timeline
    from video_ai.runtime.manifest import hash_file,thaw,now
    run,config,store,data=timeline_run
    assert plan_timeline(config,run_dir=run).passed
    t=load_committed_timeline(run); folder=run/'logs/storyboard'; folder.mkdir()
    note=folder/'notes.txt'; note.write_text('Test-only human annotation fixture; not real acceptance.',encoding='utf-8')
    units=[dict(unit_id=c.unit_id,pcm_identity=thaw(hash_file(c.pcm.path)),semantic_unit_verdict='passed',semantic_reason='single semantic fixture',
        spoken_start_sample=600,spoken_end_sample=c.samples-600,boundary_uncertainty_samples=100,
        verified_internal_silences=[],verdict='passed',reason='test annotation fixture',evidence_identity=thaw(hash_file(note))) for c in t.clips]
    cues=[dict(cue_id=f'cue_{i:04d}',from_unit_id=a.unit_id,to_unit_id=b.unit_id,absolute_sample=b.start_sample+600,
               verdict='passed',reason='fixture onset') for i,(a,b) in enumerate(zip(t.clips,t.clips[1:]),1)]
    timing=dict(schema_version=1,run_id=run.name,script_identity=thaw(hash_file(run/'script.txt')),
        timeline_identity=thaw(hash_file(run/'timeline.json')),review_method='human_audio',reviewer='fixture human',reviewed_at=now(),
        verdict='passed',reason='fixture annotation only',units=units,cues=cues)
    path=folder/'timing-review.json';path.write_text(json.dumps(timing,ensure_ascii=False),encoding='utf-8')
    return run,config,store,timing,path



def mock_generation(monkeypatch,sequence=None):
    from video_ai.runtime import storyboard_checks as sc
    calls=[]
    def generate(config,run,store,logger,slots,**kwargs):
        calls.append(run)
        return content_for(slots),{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    return calls


def review_for(run):
    from video_ai.runtime.manifest import hash_file,thaw,now
    draft=json.loads((run/'storyboard-draft.json').read_text(encoding='utf-8'))
    entries=[]
    for shot in draft['shots']:
        for i,r in enumerate(shot['visual_requirements']):
            entries.append(dict(shot_id=shot['shot_id'],requirement_id=r['requirement_id'],requirement_index=i,
                unit_id=r['unit_id'],source_quote=r['source_quote'],verdict='passed',reason='Test fixture text review, all dimensions examined.'))
    return dict(schema_version=1,run_id=run.name,draft_identity=thaw(hash_file(run/'storyboard-draft.json')),
        timeline_identity=draft['timeline_identity'],timing_review_identity=draft['timing_review_identity'],review_method='agent_text',
        reviewed_at=now(),reviewer='test fixture',global_verdict='passed',reason='Test fixture global review',entries=entries)


def write_review(run,data):
    path=run/'logs/storyboard/semantic-review.json';path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');return path

