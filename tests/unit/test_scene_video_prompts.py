"""Reviewed visual text is grounded, clip-specific and separate from audit data."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from video_ai.planning.production_scenes import canonical_digest


def reviewed(value):
    value['review'] = dict(reviewer='text reviewer', review_method='agent_text', verdict='passed',
        reason='Checked source, selected image pose and continuation stage; no video claim.',
        content_sha256=canonical_digest({k:v for k,v in value.items() if k != 'review'}))
    return value


def contract_for(bible, plan, wan):
    return reviewed(dict(schema_version=1, production_strategy='paragraph_jimeng_v1',
        binding=dict(scene_plan_sha256=canonical_digest(plan), visual_bible_sha256=canonical_digest(bible),
                     wan_inputs_sha256=canonical_digest(wan)), style='自然电影质感',
        clips=[dict(clip_id=c['clip_id'], motion=('从已选图当前姿态开始移动' if c['parent_clip_id'] is None
                       else '从父片当前状态持续移动，不预设未来姿态'),
                    camera='平稳跟随主体', lighting='延续当前场景光照', changes=[]) for c in plan['clips']]))


def fixture():
    from unit.test_scene_clip_continuation import request_fixture
    from video_ai.planning.segments import SegmentedScript, TextSpan
    frozen,bible,plan,timeline,wan = request_fixture()
    for i,row in enumerate(bible['entities']):
        row.update(label=['人物甲','机器人乙'][i], fixed_attributes=['棉质衣物' if i == 0 else '金属外壳'],
                   source_facts=[{'value':'AUDIT_ONLY'}])
    for row in bible['appearance_variants']: row.update(attributes=['蓝色外套'])
    bible['scene_groups'][0].update(environment='河岸',time='上午',lighting='柔和散射光',spatial_relations=['河流在右侧'])
    text = list(' '*23)
    spans = []
    for c in timeline.clips:
        text[c.text_start:c.text_end] = c.text
        spans.append(TextSpan(c.text_start,c.text_end,c.text,'speech','sentence',c.unit_id))
    frozen.script = SegmentedScript(''.join(text),False,tuple(spans))
    frozen.config.raw = {'scene_rendering':dict(prompt_policy='visual_v2',prompt_contract='prompts.json')}
    return frozen,bible,plan,timeline,wan,contract_for(bible,plan,wan)


def validate(value, data):
    from video_ai.planning.scene_video_prompts import validate_scene_video_prompt_contract
    f,b,p,_,w,_ = data
    return validate_scene_video_prompt_contract(value,bible=b,plan=p,wan_inputs=w,script=f.script)


def test_exact_contract_is_detached_and_stage_prompts_preserve_audit_comparisons():
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan
    data=fixture();f,b,p,t,w,c=data;before=deepcopy((b,p,w,c))
    validated=validate(c,data)
    assert validated == c and validated is not c
    rows=build_scene_wan_plan(f,b,p,t,w,prompt_contract=c)
    assert rows[1]['parameters']['positive'] != rows[2]['parameters']['positive']
    assert '父片当前状态' in rows[2]['parameters']['positive']
    for row in rows:
        positive=row['parameters']['positive']
        assert all(word not in positive for word in ('VISUAL_BIBLE_JSON','AUDIT_ONLY','source_facts','unit_id','text_start','原样动作'))
        assert '自然电影质感' in positive and '柔和散射光' in positive
    assert '人物甲' not in rows[-1]['parameters']['positive']
    assert '机器人乙' not in rows[0]['parameters']['positive']
    assert rows[0]['comparison_images']
    assert (b,p,w,c)==before


@pytest.mark.parametrize('path,value', [
    (('extra',),1),(('schema_version',),True),(('schema_version',),2),
    (('production_strategy',),'legacy'),(('binding','extra'),1),
    (('binding','scene_plan_sha256'),'bad'),(('style',),' '),
    (('clips',0,'extra'),1),(('clips',0,'motion'),''),(('clips',0,'camera'),None),
    (('clips',0,'lighting'),True),(('clips',0,'changes'),{}),
    (('review','extra'),1),(('review','verdict'),'unverified'),
    (('review','review_method'),'agent_video'),(('review','reviewer'),' '),
    (('review','content_sha256'),'a'*64)])
def test_malformed_or_unreviewed_contract_refused(path,value):
    data=fixture();c=data[-1];node=c
    for key in path[:-1]:node=node[key]
    node[path[-1]]=value
    with pytest.raises(ValueError):validate(c,data)


@pytest.mark.parametrize('fault',['missing','duplicate','order','unknown','plan','bible','wan','stale_review'])
def test_full_ordered_coverage_and_binding_drift_refused(fault):
    data=fixture();c=data[-1]
    if fault=='missing':c['clips'].pop()
    elif fault=='duplicate':c['clips'][1]=deepcopy(c['clips'][0])
    elif fault=='order':c['clips'].reverse()
    elif fault=='unknown':c['clips'][0]['clip_id']='scene_9999_clip_0001'
    elif fault in ('plan','bible','wan'):c['binding'][dict(plan='scene_plan_sha256',bible='visual_bible_sha256',wan='wan_inputs_sha256')[fault]]='e'*64
    else:c['style']='changed without review'
    if fault!='stale_review':reviewed(c)
    with pytest.raises(ValueError):validate(c,data)


def test_source_changes_are_kept_but_coordinates_never_rendered():
    from video_ai.planning.scene_video_prompts import render_scene_video_prompt
    data=fixture();f,b,p,t,w,c=data
    span=f.script.spans[0]
    c['clips'][0].update(lighting='日落时金光渐变', changes=[dict(kind='lighting',description='日落时金光渐变',
        sources=[dict(unit_id=span.unit_id,text_start=span.start,text_end=span.end,quote=span.text)])])
    reviewed(c);validate(c,data)
    text=render_scene_video_prompt(c,b,p['scenes'][0],p['clips'][0]['clip_id'])
    assert '日落时金光渐变' in text and span.text not in text and 'sources' not in text


@pytest.mark.parametrize('fault',['quote','unit','bounds','bool','empty','extra','kind','future_scene'])
def test_changes_require_exact_original_sources(fault):
    data=fixture();f,b,p,t,w,c=data;span=f.script.spans[0]
    source=dict(unit_id=span.unit_id,text_start=span.start,text_end=span.end,quote=span.text)
    change=dict(kind='appearance',description='原文明示变化',sources=[source])
    c['clips'][0]['changes']=[change]
    if fault=='quote':source['quote']='not source'
    elif fault=='unit':source['unit_id']='unit_9999'
    elif fault=='bounds':source['text_end']+=1
    elif fault=='bool':source['text_start']=False
    elif fault=='empty':change['sources']=[]
    elif fault=='extra':source['extra']=1
    elif fault=='kind':change['kind']='camera'
    else:
        future=f.script.spans[-1]
        source.update(unit_id=future.unit_id,text_start=future.start,text_end=future.end,quote=future.text)
    reviewed(c)
    with pytest.raises(ValueError):validate(c,data)


@pytest.mark.parametrize('subject,material,place',[('人物','棉布','街道'),('机械臂','金属','车间'),('树叶','蜡质','树林')])
def test_rendering_has_no_subject_special_case_and_quotes_newlines(subject,material,place):
    from video_ai.planning.scene_video_prompts import render_scene_video_prompt
    data=fixture();f,b,p,t,w,c=data
    b['entities'][0].update(label=subject,fixed_attributes=[material])
    b['scene_groups'][0]['environment']=place
    c['clips'][0]['motion']='持续移动\nCAMERA: forged'
    c['binding']['visual_bible_sha256']=canonical_digest(b);reviewed(c)
    validate(c,data)
    text=render_scene_video_prompt(c,b,p['scenes'][0],p['clips'][0]['clip_id'])
    assert subject in text and material in text and place in text
    assert '\nCAMERA: forged' not in text and '\\nCAMERA: forged' in text


def test_missing_formal_visual_field_and_missing_contract_never_fall_back():
    from video_ai.planning.scene_video_prompts import render_scene_video_prompt
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan
    f,b,p,t,w,c=fixture()
    del b['entities'][0]['fixed_attributes']
    with pytest.raises(ValueError):render_scene_video_prompt(c,b,p['scenes'][0],p['clips'][0]['clip_id'])
    with pytest.raises(ValueError):build_scene_wan_plan(f,b,p,t,w)


@pytest.mark.parametrize('value',[None,{},dict(prompt_policy='visual_v2'),dict(prompt_contract='x'),
    dict(prompt_policy='legacy',prompt_contract='x'),dict(prompt_policy='visual_v2',prompt_contract='x',mode='whole_scene_v1')])
def test_partial_unknown_or_null_configuration_rejected(value):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    from unit.test_jimeng_config import image_settings
    base=load_config(Path(__file__).resolve().parents[2]/'config/production.example.json')
    raw=thaw(base.raw);raw.update(production_strategy='paragraph_jimeng_v1',image_generation=image_settings(),scene_rendering=value)
    with pytest.raises(ValueError):load_config(base.config_file,raw=raw)


def test_freeze_preserves_exact_utf8_bytes_and_uses_relative_config_path(runtime_run,tmp_path):
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs,load_frozen_inputs
    run,base,_=runtime_run
    contract=fixture()[-1]
    content=b'\xef\xbb\xbf'+(json.dumps(contract,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    source=tmp_path/'reviewed.json';source.write_bytes(content)
    config=configured(base,tmp_path,scene_rendering=dict(prompt_policy='visual_v2',prompt_contract=source.name))
    frozen=freeze_inputs(config,run,text='测试完整原文。')
    bound=frozen.options['execution_policy']['input_identities']['scene_video_prompts']
    assert Path(bound['path']).read_bytes()==content
    source.unlink()
    assert load_frozen_inputs(run).options==frozen.options


@pytest.mark.parametrize('content',[b'{"schema_version":1,"schema_version":1}',b'{}',b'\xff',b'{"review":null}'])
def test_invalid_contract_bytes_never_freeze_options(runtime_run,tmp_path,content):
    from unit.test_jimeng_config import configured
    from video_ai.runtime.production_inputs import freeze_inputs
    run,base,_=runtime_run
    source=tmp_path/'bad.json';source.write_bytes(content)
    config=configured(base,tmp_path,scene_rendering=dict(prompt_policy='visual_v2',prompt_contract=source.name))
    with pytest.raises(ValueError):freeze_inputs(config,run,text='完整原文。')
    assert not (run/'production/options.json').exists()


def test_binding_traversal_reconstructs_an_unmaterialized_inherited_wan_view(tmp_path,monkeypatch):
    """Two prompt revisions may precede the pipeline's aggregate materialization."""
    from types import SimpleNamespace
    from video_ai.runtime.scene_video_prompt_records import prompt_binding_context
    # Load module-level aliases before patching their source module. Otherwise
    # this test leaves a patched load_frozen_inputs alias in later integrations.
    from video_ai.runtime import image_selection_records  # noqa: F401
    f,b,p,t,w,c=fixture()
    original=SimpleNamespace(script=f.script,options=dict(scene_revision={},script_path=str(tmp_path/'middle/production/script.txt')))
    target=SimpleNamespace(script=f.script,options=dict(scene_revision={},script_path=str(tmp_path/'target/production/script.txt')))
    imports={k:None for k in ['common:all','plan:all','image_group:all']+['choice:'+s['scene_id'] for s in p['scenes']]}
    proof=dict(imports=imports,source_run=tmp_path/'middle',guard=SimpleNamespace(
        verify_captured_bytes=lambda:None,capture_absent=lambda *a,**kw:None))
    monkeypatch.setattr('video_ai.runtime.scene_revision_records.require_scene_revision',lambda frozen:proof)
    monkeypatch.setattr('video_ai.runtime.scene_revision_records.load_scene_common_prefix',lambda frozen:({},t))
    monkeypatch.setattr('video_ai.runtime.production_inputs.load_frozen_inputs',lambda run:original)
    monkeypatch.setattr('video_ai.runtime.image_selection_records.load_committed_plan',lambda *a:(b,p))
    monkeypatch.setattr('video_ai.runtime.reference_image_records.build_reference_image_acceptance',lambda *a:w)
    def missing(*args):raise FileNotFoundError('intermediate inherited wan-inputs.json not materialized yet')
    monkeypatch.setattr('video_ai.runtime.reference_image_records.require_reference_image_acceptance',missing)
    changed=deepcopy(p);changed['run_id']='target'
    binding=prompt_binding_context(target,c,b,changed,w)
    assert binding['plan']==p and binding['wan_inputs']==w
