import copy
import json
import pytest
from storyboard_helpers import content_for,review_for,write_review

FIELDS='subject action_or_state setting quantity negation relation_or_order context_sources resolved_references'.split()


def setup_contract(storyboard_run):
    from video_ai.runtime.timeline_checks import load_committed_timeline
    from video_ai.runtime.storyboard_checks import load_timing_review
    from video_ai.runtime.manifest import now,thaw,hash_file
    from video_ai.planning.storyboard import plan_slots,primary_model_slots,source_catalog
    run,config,store,timing,path=storyboard_run
    timeline=load_committed_timeline(run);slots=plan_slots(timeline,timing=load_timing_review(run,path,timeline))
    model=content_for(primary_model_slots(slots));specs={}
    for shot in model['shots']:
        for r in shot['visual_requirements']:specs[r['unit_id']]={k:copy.deepcopy(r[k]) for k in FIELDS}
    units=[dict(unit_id=u,source_quote=c['text'],facts=specs[u],verdict='passed',reason='Fixture source interpretation, not real acceptance') for u,c in source_catalog(slots).items()]
    data=dict(schema_version=1,run_id=run.name,script_identity=thaw(hash_file(run/'script.txt')),timing_review_identity=thaw(hash_file(path)),
        review_method='agent_source',reviewer='test fixture',reviewed_at=now(),verdict='passed',reason='Test source contract only',units=units)
    target=run/'logs/storyboard/visual-contract.json';target.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    return slots,specs,model,data,target


def test_source_facts_frozen_while_model_visual_fields_remain_free(storyboard_run):
    from video_ai.planning.storyboard import make_model_schema,validate_model_content,primary_model_slots
    slots,specs,model,data,path=setup_contract(storyboard_run);projected=primary_model_slots(slots)
    schema=make_model_schema(projected,semantic_specs=specs)
    props=schema['properties']['shots']['prefixItems'][0]['properties']
    fact_props=props['visual_requirements']['prefixItems'][0]['properties']
    assert all('const' in fact_props[k] for k in FIELDS)
    assert 'const' not in props['image_prompt'] and 'const' not in fact_props['visual_expression']
    model['shots'][0]['image_prompt']='A real model presentation choice'
    validate_model_content(model,projected,semantic_specs=specs)
    model['shots'][0]['visual_requirements'][0]['subject']='wrong focal subject'
    with pytest.raises(ValueError,match='const'):validate_model_content(model,projected,semantic_specs=specs)


@pytest.mark.parametrize('bad',['missing','failed','script','timing','quote','index','bool','unknown','method'])
def test_invalid_contract_stops_before_model(storyboard_run,monkeypatch,bad):
    from video_ai.runtime import storyboard_checks as sc
    run,config,store,timing,path=storyboard_run;slots,specs,model,data,target=setup_contract(storyboard_run);calls=[]
    if bad=='missing':data['units'].pop()
    if bad=='failed':data['units'][0]['verdict']='failed'
    if bad=='script':data['script_identity']['sha256']='a'*64
    if bad=='timing':data['timing_review_identity']['sha256']='a'*64
    if bad=='quote':data['units'][0]['source_quote']='not original text'
    if bad=='index':data['units'][0]['facts']['resolved_references']=[dict(reference_quote=data['units'][0]['source_quote'],resolved_subject='fixture',context_source_indices=[9])]
    if bad=='bool':data['units'][0]['facts']['quantity']=True
    if bad=='unknown':data['units'][0]['facts']['invented']=1
    if bad=='method':data['review_method']='human_audio'
    target.write_text(json.dumps(data),encoding='utf-8')
    def generate(*args,**kwargs):calls.append(1);return model,{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    result=sc.plan_storyboard(config,run_dir=run,timing_review_path=path)
    assert not result.passed and not calls and store.snapshot()['stages']['storyboard']['status']=='pending'


@pytest.mark.parametrize('drift',['replace','delete','add'])
def test_source_contract_presence_or_bytes_change_prevents_draft_commit(storyboard_run,monkeypatch,drift):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.planning.storyboard import expand_boundary_requirements
    run,config,store,timing,path=storyboard_run;slots,specs,model,data,target=setup_contract(storyboard_run)
    if drift=='add':target.unlink()
    def generate(config,run,store,logger,slots,**kwargs):
        if drift=='delete':target.unlink()
        else:target.write_text(json.dumps(dict(data,reason='changed during inference')),encoding='utf-8')
        return expand_boundary_requirements(model,slots)[0],{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    result=sc.plan_storyboard(config,run_dir=run,timing_review_path=path)
    assert not result.passed and result.status=='failed' and not (run/'storyboard-draft.json').exists()


def test_committed_reader_rechecks_source_contract(storyboard_run,monkeypatch):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.planning.storyboard import expand_boundary_requirements
    run,config,store,timing,path=storyboard_run;slots,specs,model,data,target=setup_contract(storyboard_run)
    def generate(config,run,store,logger,slots,**kwargs):return expand_boundary_requirements(model,slots)[0],{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    planned=sc.plan_storyboard(config,run_dir=run,timing_review_path=path)
    assert planned.status=='review_required',store.snapshot()['stages']['storyboard']['error']
    assert sc.finalize_storyboard(config,run_dir=run,review_path=write_review(run,review_for(run))).passed
    assert sc.load_committed_storyboard(run)['validation']['ready_for_images']
    target.write_text(json.dumps(dict(data,reason='changed after accepted draft')),encoding='utf-8')
    with pytest.raises((ValueError,OSError)):sc.load_committed_storyboard(run)


def test_actual_request_enforces_contract_and_keeps_one_correction_budget(storyboard_run):
    from video_ai.runtime.storyboard_checks import _request_content
    from video_ai.runtime.logging import RunLogger
    from video_ai.planning.storyboard import primary_model_slots,make_model_schema
    from video_ai.adapters.ollama import ollama_schema,ollama_content
    slots,specs,model,data,target=setup_contract(storyboard_run);calls=[]
    class Planner:
        def generate(self,prompt,*,schema,request_id):
            assert schema==make_model_schema(primary_model_slots(slots),semantic_specs=specs)
            wire=ollama_schema(schema)
            first=next(iter(wire['properties']['shots']['properties'].values()))
            requirement=next(iter(first['properties']['visual_requirements']['properties'].values()))
            assert requirement['properties']['resolved_references']['const']==[]
            calls.append(request_id);result=copy.deepcopy(model)
            if request_id=='initial':result['shots'][0]['visual_requirements'][0]['subject']='wrong original interpretation'
            return result
    result=_request_content(Planner(),slots,RunLogger(storyboard_run[0]),semantic_specs=specs)
    assert calls==['initial','correction']
    assert result['shots'][0]['visual_requirements'][0]['subject']==specs[slots[0].primary_unit_id]['subject']


def test_committed_reader_rejects_contract_added_at_return_boundary(storyboard_run,monkeypatch):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.planning.storyboard import expand_boundary_requirements,primary_model_slots
    run,config,store,timing,path=storyboard_run
    def generate(config,run,store,logger,slots,**kwargs):
        return expand_boundary_requirements(content_for(primary_model_slots(slots)),slots)[0],{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    assert sc.plan_storyboard(config,run_dir=run,timing_review_path=path).status=='review_required'
    assert sc.finalize_storyboard(config,run_dir=run,review_path=write_review(run,review_for(run))).passed
    original=sc._verify_import
    calls=[]
    def late_add(*args,**kwargs):
        original(*args,**kwargs);calls.append(1)
        if len(calls)==2:
            (run/'logs/storyboard/visual-contract.json').write_text('{}',encoding='utf-8')
    monkeypatch.setattr(sc,'_verify_import',late_add)
    with pytest.raises(OSError,match='presence changed'):sc.load_committed_storyboard(run)
    assert len(calls)==2


def grounded_model(model,slots,specs):
    from video_ai.planning.storyboard import depiction_anchor
    model=copy.deepcopy(model)
    for shot,slot in zip(model['shots'],slots):
        anchor=depiction_anchor(specs[slot.primary_unit_id])
        for key in ('composition','action_start','action_end','image_prompt','video_prompt'):
            shot[key]=anchor+'A visible grounded scene continues.'
        shot['camera_motion']='static camera'
        shot['video_prompt']+=' Camera path: static camera.'
        for r in shot['visual_requirements']:
            r['visual_expression']=depiction_anchor(specs[r['unit_id']])+'A visible grounded scene.'
    return model


@pytest.mark.parametrize('field',['image_prompt','video_prompt','visual_expression','camera_motion','camera_mismatch'])
def test_grounded_policy_rejects_actual_instruction_omissions(storyboard_run,field):
    from video_ai.planning.storyboard import primary_model_slots,make_model_schema,validate_model_content
    slots,specs,model,data,target=setup_contract(storyboard_run);slots=primary_model_slots(slots)
    model=grounded_model(model,slots,specs)
    validate_model_content(model,slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    schema=make_model_schema(slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    assert 'const' not in schema['properties']['shots']['prefixItems'][0]['properties']['image_prompt']
    if field=='visual_expression':model['shots'][0]['visual_requirements'][0][field]='Water ripples only, missing actual original subject'
    elif field=='camera_mismatch':model['shots'][0]['camera_motion']='slow left pan'
    else:model['shots'][0][field]='Smooth, with unspecified subject and path'
    with pytest.raises(ValueError):validate_model_content(model,slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')


def test_grounded_policy_anchor_escapes_literal_regex_and_keeps_free_suffix(storyboard_run):
    from video_ai.planning.storyboard import primary_model_slots,validate_model_content,depiction_anchor
    slots,specs,model,data,target=setup_contract(storyboard_run);slots=primary_model_slots(slots)
    uid=slots[0].primary_unit_id;specs[uid]['subject']='A literal (object) [x]+? with "quotes"'
    model['shots'][0]['visual_requirements'][0]['subject']=specs[uid]['subject']
    model=grounded_model(model,slots,specs)
    model['shots'][0]['image_prompt']=depiction_anchor(specs[uid])+'A different model-selected composition.'
    validate_model_content(model,slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    from video_ai.planning.storyboard import make_model_schema
    with pytest.raises(ValueError):make_model_schema(slots,depiction_policy='grounded_prompts_v1')


def test_v2_contract_policy_reaches_request_finalize_and_consumer(storyboard_run,monkeypatch):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.planning.storyboard import expand_boundary_requirements,primary_model_slots
    run,config,store,timing,path=storyboard_run;slots,specs,model,data,target=setup_contract(storyboard_run)
    data.update(schema_version=2,depiction_policy='grounded_prompts_v1')
    target.write_text(json.dumps(data),encoding='utf-8');calls=[]
    model=grounded_model(model,primary_model_slots(slots),specs)
    def generate(config,run,store,logger,slots,**kwargs):
        calls.append(kwargs['depiction_policy']);return expand_boundary_requirements(model,slots)[0],{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    assert sc.plan_storyboard(config,run_dir=run,timing_review_path=path).status=='review_required'
    assert calls==['grounded_prompts_v1']
    assert sc.finalize_storyboard(config,run_dir=run,review_path=write_review(run,review_for(run))).passed
    assert sc.load_committed_storyboard(run)['validation']['ready_for_images']


def test_grounded_actual_request_keeps_sole_correction_budget(storyboard_run):
    from video_ai.runtime.storyboard_checks import _request_content
    from video_ai.runtime.logging import RunLogger
    from video_ai.planning.storyboard import primary_model_slots
    from video_ai.adapters.ollama import ollama_schema
    slots,specs,model,data,target=setup_contract(storyboard_run);model=grounded_model(model,primary_model_slots(slots),specs);calls=[]
    class Planner:
        def generate(self,prompt,*,schema,request_id):
            calls.append(request_id);result=copy.deepcopy(model)
            wire=ollama_schema(schema);first=next(iter(wire['properties']['shots']['properties'].values()))
            canonical=schema['properties']['shots']['prefixItems'][0]['properties']['image_prompt']
            assert 'pattern' in canonical and 'pattern' in first['properties']['_grounded_visual']['properties']['presentations']['properties']['image_prompt']
            if request_id=='initial':result['shots'][0]['image_prompt']='Missing source subject'
            return result
    result=_request_content(Planner(),slots,RunLogger(storyboard_run[0]),semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    assert calls==['initial','correction']
    assert result['shots'][0]['image_prompt']==model['shots'][0]['image_prompt']


@pytest.mark.parametrize('bad',['missing_policy','unknown_policy','bool_version','v1_extra','no_facts'])
def test_invalid_v2_contract_policy_stops_before_model(storyboard_run,monkeypatch,bad):
    from video_ai.runtime import storyboard_checks as sc
    run,config,store,timing,path=storyboard_run;slots,specs,model,data,target=setup_contract(storyboard_run)
    data.update(schema_version=2,depiction_policy='grounded_prompts_v1');calls=[]
    if bad=='missing_policy':data.pop('depiction_policy')
    if bad=='unknown_policy':data['depiction_policy']='silently_replace_model_text'
    if bad=='bool_version':data['schema_version']=True
    if bad=='v1_extra':data['schema_version']=1
    if bad=='no_facts':
        for k in FIELDS[:6]:data['units'][0]['facts'][k]=None
    target.write_text(json.dumps(data),encoding='utf-8')
    def generate(*args,**kwargs):calls.append(1);return model,{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    assert not sc.plan_storyboard(config,run_dir=run,timing_review_path=path).passed
    assert not calls and store.snapshot()['stages']['storyboard']['status']=='pending'


@pytest.mark.parametrize('field',['image_prompt','video_prompt','visual_expression'])
def test_grounded_policy_requires_nonblank_model_presentation(storyboard_run,field):
    from video_ai.planning.storyboard import primary_model_slots,validate_model_content,depiction_anchor
    slots,specs,model,data,target=setup_contract(storyboard_run);slots=primary_model_slots(slots)
    model=grounded_model(model,slots,specs);shot=model['shots'][0];anchor=depiction_anchor(specs[slots[0].primary_unit_id])
    value=anchor+'\u3000 '
    if field=='video_prompt':value+=' Camera path: static camera.'
    if field=='visual_expression':shot['visual_requirements'][0][field]=value
    else:shot[field]=value
    with pytest.raises(ValueError):validate_model_content(model,slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')


def test_grounded_canonical_escapes_remain_while_wire_uses_json_strings(storyboard_run):
    from video_ai.planning.storyboard import make_model_schema,primary_model_slots,validate_model_content
    from video_ai.adapters.ollama import ollama_schema
    slots,specs,model,data,target=setup_contract(storyboard_run);slots=primary_model_slots(slots)
    uid=slots[0].primary_unit_id;specs[uid]['subject']='A first-person (observer) [x]+? # literal'
    model['shots'][0]['visual_requirements'][0]['subject']=specs[uid]['subject']
    model=grounded_model(model,slots,specs)
    schema=make_model_schema(slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    wire=ollama_schema(schema)
    props=next(iter(wire['properties']['shots']['properties'].values()))['properties']
    for key in ('composition','action_start','action_end','image_prompt','video_prompt'):
        pattern=schema['properties']['shots']['prefixItems'][0]['properties'][key]['pattern']
        assert '\\ ' not in pattern and '\\-' not in pattern and '\\#' not in pattern
        assert '\\(' in pattern and '\\[' in pattern and '\\+' in pattern
        assert 'pattern' in props['_grounded_visual']['properties']['presentations']['properties'][key]
    validate_model_content(model,slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
