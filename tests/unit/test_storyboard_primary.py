import copy
from dataclasses import replace
import json
import pytest
from test_storyboard import real_timeline, timing_for
from storyboard_helpers import content_for


def slots_for_test():
    from video_ai.planning.storyboard import plan_slots
    t=real_timeline()
    return plan_slots(t,timing=timing_for(t,start=0,end_margin=0,uncertainty=0))


def test_primary_projection_preserves_original_bindings_and_full_coverage():
    from video_ai.planning.storyboard import primary_model_slots,expand_boundary_requirements,validate_model_content
    slots=slots_for_test();before=copy.deepcopy(slots)
    projected=primary_model_slots(slots)
    assert all(len(s.bindings)==1 and s.bindings[0].unit_id==s.primary_unit_id for s in projected)
    content=content_for(projected);original=copy.deepcopy(content)
    expanded,associations=expand_boundary_requirements(content,slots)
    validate_model_content(expanded,slots)
    assert slots==before and content==original
    assert sum(len(s['visual_requirements']) for s in expanded['shots'])==13
    assert len(associations)==13
    for a in associations:
        target=expanded['shots'][a['target_shot_index']]['visual_requirements'][a['target_requirement_index']]
        source=original['shots'][a['source_shot_index']]['visual_requirements'][0]
        assert target==source
    assert expanded['shots'][0]['visual_requirements'][1] is not content['shots'][1]['visual_requirements'][0]


def test_cross_sentence_reference_is_copied_without_text_repair():
    from video_ai.planning.storyboard import primary_model_slots,expand_boundary_requirements
    slots=slots_for_test();content=content_for(primary_model_slots(slots))
    r=content['shots'][3]['visual_requirements'][0];b=slots[2].bindings[0]
    r.update(subject='灯光在水面的倒影',context_sources=[dict(unit_id=b.unit_id,text_start=b.text_start,text_end=b.text_end,source_quote=b.text)],
        resolved_references=[dict(reference_quote='轻轻摇动',resolved_subject='灯光在水面的倒影',context_source_indices=[0])])
    expanded,_=expand_boundary_requirements(content,slots)
    assert expanded['shots'][2]['visual_requirements'][1]==r
    assert expanded['shots'][3]['visual_requirements'][0]==r


def test_non_edge_foreign_binding_refused():
    from video_ai.planning.storyboard import primary_model_slots,expand_boundary_requirements
    slots=slots_for_test();content=content_for(primary_model_slots(slots))
    first=slots[0];foreign=replace(first.bindings[-1],quantization_edge=False)
    changed=(replace(first,bindings=(first.bindings[0],foreign)),*slots[1:])
    with pytest.raises(ValueError,match='edge'):expand_boundary_requirements(content,changed)


def test_request_contains_only_primary_scene_and_restores_real_bindings(storyboard_run):
    from video_ai.planning.storyboard import primary_model_slots,make_model_schema
    from video_ai.runtime.storyboard_checks import _request_content
    from video_ai.runtime.logging import RunLogger
    slots=slots_for_test();projected=primary_model_slots(slots);seen=[]
    class Planner:
        def generate(self,prompt,*,schema,request_id):
            data=json.loads(prompt);seen.append(data)
            assert schema==make_model_schema(projected)
            assert all(len(s['bindings'])==1 for s in data['frozen_slots'])
            assert data['primary_scenes']['shot_0004']['semantic_reason']=='倒影承接前句'
            return content_for(projected)
    run=storyboard_run[0];logger=RunLogger(run)
    result=_request_content(Planner(),slots,logger,semantic_reasons={'speech_0004':'倒影承接前句'})
    assert len(seen)==1 and len(result['shots'][0]['visual_requirements'])==2
    assert (run/'logs/storyboard/primary-content.json').is_file()
    assert (run/'logs/storyboard/binding-expansion.json').is_file()


def test_leading_edge_and_nearest_long_unit_source_are_preserved():
    from video_ai.config import TimelineSettings
    from test_timeline import make
    from video_ai.planning.storyboard import plan_slots,primary_model_slots,expand_boundary_requirements
    t=make('甲，长句，乙。',[48000,481000,48000],settings=TimelineSettings(0,0,0,0))
    slots=plan_slots(t,timing=timing_for(t,start=0,end_margin=0,uncertainty=0))
    projected=primary_model_slots(slots);content=content_for(projected)
    for i,s in enumerate(content['shots']):s['visual_requirements'][0]['visual_expression']=f'actual-model-expression-{i}'
    expanded,links=expand_boundary_requirements(content,slots)
    leading=[a for a in links if a['scope']=='leading_edge']
    assert leading and leading[-1]['source_shot_index']==2
    assert expanded['shots'][-1]['visual_requirements'][0]['visual_expression']=='actual-model-expression-2'


def test_admitted_internal_silence_can_span_primary_slots():
    from video_ai.config import TimelineSettings
    from test_timeline import make
    from video_ai.planning.storyboard import plan_slots,primary_model_slots,expand_boundary_requirements,SpeechTimingEvidence,UnitTiming
    t=make('长句。',[1440000],settings=TimelineSettings(0,0,0,0))
    timing=SpeechTimingEvidence((UnitTiming('speech_0001',0,1440000,0,((24000,1416000),),'passed','passed'),),())
    slots=plan_slots(t,timing=timing);assert sum(s.bindings[0].silence_only for s in slots)==4
    projected=primary_model_slots(slots);content=content_for(projected)
    expanded,links=expand_boundary_requirements(content,slots)
    assert len(expanded['shots'])==6 and len(links)==2
    assert all(not s['visual_requirements'] for s in expanded['shots'][1:5])


def test_primary_evidence_persistence_failure_is_ambiguous_without_correction(storyboard_run,monkeypatch):
    from video_ai.planning.storyboard import primary_model_slots
    from video_ai.runtime.storyboard_checks import _request_content
    from video_ai.runtime.logging import RunLogger
    from video_ai.adapters.common import AdapterError,FailureKind
    slots=slots_for_test();logger=RunLogger(storyboard_run[0]);calls=[];save=logger.save_json
    def fail(path,data):
        if path=='storyboard/primary-content.json':raise OSError('evidence disk failure')
        return save(path,data)
    monkeypatch.setattr(logger,'save_json',fail)
    class Planner:
        def generate(self,prompt,*,schema,request_id):
            calls.append(request_id);return content_for(primary_model_slots(slots))
    with pytest.raises(AdapterError) as caught:_request_content(Planner(),slots,logger)
    assert caught.value.kind==FailureKind.ambiguous and calls==['initial']


@pytest.mark.parametrize('bad',['association','text','uppercase','alias'])
def test_consumer_rederives_expansion_association_and_original_text(storyboard_run,monkeypatch,bad):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.planning.storyboard import primary_model_slots
    run,config,store,timing,path=storyboard_run
    def generate(config,run,store,logger,slots,**kwargs):
        class Planner:
            def generate(self,prompt,*,schema,request_id):return content_for(primary_model_slots(slots))
        return sc._request_content(Planner(),slots,logger),{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    assert sc.plan_storyboard(config,run_dir=run,timing_review_path=path).status=='review_required'
    draft=json.loads((run/'storyboard-draft.json').read_text(encoding='utf-8'))
    if bad=='association':
        p=run/'logs/storyboard/binding-expansion.json';data=json.loads(p.read_text(encoding='utf-8'))
        data['associations'][0]['source_shot_index']=99;p.write_text(json.dumps(data),encoding='utf-8')
        draft['request_evidence']['storyboard/binding-expansion.json']=thaw(hash_file(p))
    elif bad=='alias':
        key='storyboard/primary-content.json'
        draft['request_evidence'][key.upper()]=copy.deepcopy(draft['request_evidence'][key])
    else:
        draft['shots'][0]['image_prompt']='silently rewritten model text'
        if bad=='uppercase':draft['request_evidence']={k.upper():v for k,v in draft['request_evidence'].items()}
    timeline,identities=sc._verified_inputs(config,run,store.snapshot())
    timing,more=sc._timing(run,path,timeline);identities.update(more)
    with pytest.raises(ValueError,match='association differs|model text modified|duplicate normalized'):
        sc._validate_draft(config,run,draft,timeline,timing,identities)
