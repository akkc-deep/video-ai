"""Local pipeline fixtures persist genuine prepared reports before coordinator use."""
from image_selection_helpers import save


def persist_prepared_common(setup):
    from video_ai.runtime.manifest import now
    for stage,payload in (('units',setup['units']),('timeline',setup['timeline'].as_dict())):
        save(setup['run']/f'production/{stage}.json',dict(schema_version=1,execution_mode='automatic',
             run_id=setup['run'].name,stage=stage,created_at=now(),status='completed',input_records={},payload=payload))
    return setup


def prepared_pipeline(runtime_run,tmp_path,monkeypatch):
    """13 native first-scene frames committed as 5/4/4, plus an independent scene."""
    from copy import deepcopy
    import wave
    import json
    import integration.test_jimeng_reference_flow as reference_flow
    from unit.test_jimeng_config import configured
    from unit.test_production_scenes import scene_proposal
    from video_ai.config import load_config,parse_scene_planning
    from video_ai.planning.production_scenes import build_scene_plan,canonical_digest
    from video_ai.planning.production_timeline import ProductionAudioInfo,build_production_timeline
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import ArtifactStamp
    from video_ai.runtime.manifest import thaw
    from scene_clip_helpers import prepared_wan
    def setup_selection(runtime,tmp,*,proposal=None):
        run,config,paths=runtime
        configured_project=configured(config,tmp)
        raw=thaw(configured_project.raw)
        raw['scene_planning']={'max_clip_seconds':0.5,'target_scenes_per_paragraph':3}
        raw['media']['timeline']=dict(sentence_pause_seconds=0,paragraph_pause_seconds=0,opening_seconds=0,closing_seconds=0)
        raw['image_generation']['model_parameters'].update(width=1280,height=720)
        path=save(tmp/'pipeline-config.json',raw);config=load_config(path)
        frozen=freeze_inputs(config,run,text='湖面很静。白鸟停在石上。它望向远处。\r\n\r\n落日映着远山。')
        script=frozen.script
        units=dict(decoded_text=script.text,has_bom=script.has_bom,spans=thaw(script.spans),
            semantic_specs={s.unit_id:dict(facts={}) for s in script.spans if s.kind=='speech'})
        audio={}
        for span,samples in zip((s for s in script.spans if s.kind=='speech'),[19501,19501,6001,6001]):
            pcm=run/'audio'/span.unit_id/'pcm.wav';pcm.parent.mkdir(parents=True,exist_ok=True)
            with wave.open(str(pcm),'wb') as stream:
                stream.setparams((1,2,48000,0,'NONE',''));stream.writeframes(b'\x01\x00'*samples)
            audio[span.unit_id]=ProductionAudioInfo(ArtifactStamp.read(pcm),48000,1,2,samples)
        timeline=build_production_timeline(script,audio,settings=config.media.timeline)
        proposal=deepcopy(proposal or scene_proposal())
        last=next(s for s in script.spans if s.unit_id=='speech_0004')
        sources=[dict(unit_id=last.unit_id,text_start=last.start,text_end=last.end,quote=script.text[last.start:last.end])]
        second_group=dict(proposal['scene_groups'][0],key='mountains',label='远山',environment='落日和远山',change_sources=sources)
        proposal['scene_groups'].append(second_group)
        proposal['scenes'][-1].update(entity_ids=[],scene_group_id='mountains',summary='落日远山',
            image_prompt='落日映着远山',motion_prompt='落日光线缓缓移动',change_sources=sources)
        source=frozen.options['execution_policy']['input_identities']['script']['sha256']
        bible,plan=build_scene_plan(script,dict(units,run_id=run.name,source_sha256=source),timeline,proposal,
            settings=parse_scene_planning(config.raw['scene_planning']))
        save(run/'production/visual-bible.json',bible);save(run/'production/scene-plan.json',plan)
        commit={k:plan[k] for k in ('schema_version','run_id','source_sha256','units_sha256','timeline_sha256','settings','visual_bible_sha256')}
        save(run/'production/scene-plan-commit.json',dict(commit,scene_plan_sha256=canonical_digest(plan)))
        assert plan['scenes'][0]['end_frame']==13
        assert [c['retained_frames'] for c in plan['clips'][:3]]==[5,4,4]
        assert plan['scenes'][-1]['reference_bindings']==[]
        return dict(run=run,frozen=frozen,units=units,timeline=timeline,bible=bible,plan=plan,paths=paths,config=config)
    with monkeypatch.context() as patch:
        patch.setattr(reference_flow,'setup_selection',setup_selection)
        setup=prepared_wan(runtime_run,tmp_path,patch)
    return persist_prepared_common(setup)


def write_clip_observation(setup,template):
    from datetime import datetime,timezone
    from pathlib import Path
    from uuid import uuid4
    import json
    from unit.test_scene_clip_observations import authored
    value=authored(json.loads(Path(template).read_text(encoding='utf-8')))
    value.update(viewed_at=datetime.now(timezone.utc).isoformat(),reviewer='Synthetic protocol fixture; no real viewing claim')
    return save(setup['run']/'authored-observations'/(str(uuid4())+'.json'),value)


def write_final_observation(setup,template):
    from datetime import datetime,timezone
    from pathlib import Path
    from uuid import uuid4
    import json
    from unit.test_scene_final_observations import authored
    value=authored({'template':json.loads(Path(template).read_text(encoding='utf-8'))})
    value.update(viewed_at=datetime.now(timezone.utc).isoformat(),reviewer='Synthetic protocol fixture; no real viewing claim')
    return save(setup['run']/'authored-final'/(str(uuid4())+'.json'),value)
