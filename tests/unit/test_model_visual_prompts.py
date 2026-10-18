from copy import deepcopy

import pytest

from video_ai.planning.start_images import image_parameters


def scene(text='Voyager 1 coasts through dark interstellar space.'):
    req=dict(unit_id='speech_0001',source_quote='它继续前进。',subject='旅行者一号',
        action_or_state='继续前进',setting=None,quantity=None,negation=None,
        relation_or_order=None,context_sources=[],resolved_references=[])
    from video_ai.planning.storyboard import depiction_anchor
    anchor=depiction_anchor(req,source_quote=req['source_quote'])
    shot=dict(shot_id='shot_0001',primary_unit_id='speech_0001',entity_ids=['probe'],
        image_prompt=anchor+text,video_prompt=anchor+text+' Camera path: static camera.',
        camera_motion='static camera',visual_requirements=[req])
    global_visual=dict(style='cinematic scientific illustration',color_palette='black and gold',
        lighting='distant sunlight',entities=[dict(entity_id='probe',description='uncrewed probe')])
    return shot,global_visual


def test_model_prompt_separates_chinese_evidence_and_fixed_voyager_appearance():
    shot,g=scene();before=deepcopy(shot)
    p=image_parameters(shot,g,768,432,model_visual=True)
    assert p['positive'].isascii()
    assert 'parabolic dish' in p['positive'] and 'gold foil' in p['positive']
    assert 'dark interstellar space' in p['positive']
    assert 'color_palette:' not in p['positive'] and 'entity probe:' not in p['positive']
    assert (p['width'],p['height'])==(1280,720)
    assert 'diagram' in p['negative']
    assert shot==before


@pytest.mark.parametrize('text',['它飞过木星。','Camera path: static camera.','style: natural, color_palette: blue'])
def test_chinese_or_metadata_only_model_presentations_are_refused(text):
    shot,g=scene(text)
    with pytest.raises(ValueError):image_parameters(shot,g,768,432,model_visual=True)


def test_legacy_prompt_replay_remains_exact():
    shot,g=scene('飞船继续前进')
    p=image_parameters(shot,g,768,432)
    assert p['positive'].startswith(shot['image_prompt']+'\nstyle:')


def test_wan_uses_same_appearance_without_source_anchor():
    from video_ai.planning.model_visual_prompts import render_model_prompt
    shot,g=scene()
    image=render_model_prompt(shot,g,'image')
    video=render_model_prompt(shot,g,'video')
    assert image.isascii() and video.isascii()
    assert 'parabolic dish' in video and 'gold foil' in video
    assert 'static camera' in video
    assert 'Preserve' in video


@pytest.mark.parametrize('quote',['旅行者一号飞掠木星。','科学家看见木卫一火山喷发。','一张镀金铜唱片。'])
def test_appearance_copy_cannot_replace_planet_volcano_or_record(quote):
    from video_ai.planning.model_visual_prompts import validate_english_content
    from video_ai.planning.storyboard import depiction_anchor
    shot,g=scene('Voyager probe with a large white dish and gold foil body.')
    req=shot['visual_requirements'][0];req['source_quote']=quote
    anchor=depiction_anchor(req,source_quote=quote)
    shot['image_prompt']=anchor+'Voyager probe with a large white dish and gold foil body.'
    shot['video_prompt']=shot['image_prompt']+' Camera path: static camera.'
    with pytest.raises(ValueError,match='visual subject'):
        validate_english_content(dict(global_visual=g,shots=[shot]))


def test_volcanic_moon_does_not_inherit_wrong_probe_entity():
    from video_ai.planning.model_visual_prompts import render_model_prompt
    from video_ai.planning.storyboard import depiction_anchor
    shot,g=scene();req=shot['visual_requirements'][0]
    req.update(subject='木卫一',source_quote='木卫一正在喷发火山。')
    shot['image_prompt']=depiction_anchor(req)+'Io moon, sulfur-yellow surface, volcanic plume rising against black space.'
    shot['video_prompt']=depiction_anchor(req)+"Static view of Io's volcanic activity. Camera path: static camera."
    g['entities'][0].update(description='Uncrewed probe, white dish antenna, gold foil body',source_quotes=['旅行者1号：'])
    p=render_model_prompt(shot,g,'image')
    assert 'parabolic dish' not in p and 'Voyager' not in p
    assert 'white dish antenna' not in p and 'gold foil body' not in p
    video=render_model_prompt(shot,g,'video')
    assert 'white dish antenna' not in video and 'gold foil body' not in video


def test_saturn_record_metaphor_is_depicted_as_rings():
    from video_ai.planning.model_visual_prompts import validate_scene_subject
    shot,g=scene();shot['visual_requirements'][0]['source_quote']='从远处看，土星环仿佛一整片平滑的银色唱片。'
    validate_scene_subject(shot,'Saturn rings, smooth flat silver rings viewed from afar.')


def test_pronoun_subject_still_uses_canonical_voyager_hardware():
    from video_ai.planning.model_visual_prompts import render_model_prompt
    from video_ai.planning.storyboard import depiction_anchor
    shot,g=scene();req=shot['visual_requirements'][0];req['subject']=None
    shot['entity_ids']=[];g['entities'][0]['source_quotes']=['旅行者1号：']
    shot['image_prompt']=depiction_anchor(req)+'Voyager 1 coasts through dark interstellar space.'
    assert 'parabolic dish' in render_model_prompt(shot,g,'image')


@pytest.mark.parametrize(('quote','scene_text'),[
    ('是土星最大的卫星，','Titan moon, dense orange atmospheric haze obscures the surface.'),
    ('利用木星、土星等巨行星的引力，','Voyager probe bends its trajectory beside Jupiter in black space.'),
])
def test_context_ownership_and_lists_do_not_force_every_planet_into_one_frame(quote,scene_text):
    from video_ai.planning.model_visual_prompts import validate_scene_subject
    shot,g=scene();shot['visual_requirements'][0]['source_quote']=quote
    validate_scene_subject(shot,scene_text)


def test_gate_blocks_before_any_wan_request_and_binds_actual_image(tmp_path):
    from video_ai.runtime.production_visual_review import require_image_review,review_binding
    from video_ai.runtime.production_state import ProductionRefused
    image=tmp_path/'start.png';image.write_bytes(b'first image')
    shot,g=scene();board=dict(global_visual=g,shots=[shot])
    images=dict(images=[dict(shot_id='shot_0001',image=dict(path=str(image)))])
    with pytest.raises(ProductionRefused,match='visual review'):
        require_image_review(tmp_path,board,images)
    binding=review_binding(board,images)
    import json
    path=tmp_path/'production/visual-review.json'
    path.write_text(json.dumps(dict(schema_version=1,review_method='human_image',reviewer='tester',
        viewed_images=True,verdict='passed',reason='Inspected actual image against source.',binding=binding)),encoding='utf-8')
    require_image_review(tmp_path,board,images)
    image.write_bytes(b'changed image')
    with pytest.raises(ProductionRefused,match='binding'):
        require_image_review(tmp_path,board,images)


@pytest.mark.parametrize('change',[{'verdict':'unverified'},{'viewed_images':False},{'review_method':'technical_check'}])
def test_technical_checks_cannot_approve_visual_semantics(tmp_path,change):
    import json
    from video_ai.runtime.production_visual_review import require_image_review,review_binding
    from video_ai.runtime.production_state import ProductionRefused
    image=tmp_path/'start.png';image.write_bytes(b'image')
    shot,g=scene();board=dict(global_visual=g,shots=[shot]);images=dict(images=[dict(shot_id='shot_0001',image=dict(path=str(image)))])
    record=dict(schema_version=1,review_method='human_image',reviewer='tester',viewed_images=True,
        verdict='passed',reason='Actual visual inspection.',binding=review_binding(board,images));record.update(change)
    (tmp_path/'production').mkdir();(tmp_path/'production/visual-review.json').write_text(json.dumps(record),encoding='utf-8')
    with pytest.raises(ProductionRefused):require_image_review(tmp_path,board,images)


def test_failed_observation_admits_only_bounded_preview_never_production(tmp_path):
    import json
    from video_ai.runtime.production_visual_review import require_preview_observation,review_binding,require_image_review
    from video_ai.runtime.production_state import ProductionRefused
    shot,g=scene();shots=[];rows=[]
    for i in range(3):
        s=deepcopy(shot);s['shot_id']=f'shot_{i+1:04d}';shots.append(s)
        p=tmp_path/f'image{i}.png';p.write_bytes(b'image');rows.append(dict(shot_id=s['shot_id'],image=dict(path=str(p))))
    board=dict(global_visual=g,shots=shots);images=dict(images=rows)
    sample=tmp_path/'samples';sample.mkdir()
    record=dict(schema_version=1,scope='preview_only',review_method='agent_image',reviewer='tester',
        viewed_images=True,verdict='failed',binding=review_binding(board,images),
        observations=[dict(shot_id=s['shot_id'],observation='Actual image shows geometry defects.') for s in shots])
    (sample/'image-observation.json').write_text(json.dumps(record),encoding='utf-8')
    require_preview_observation(tmp_path,board,images)
    (sample/'images-revision.json').write_text(json.dumps(dict(images=[rows[0]])),encoding='utf-8')
    with pytest.raises(ProductionRefused,match='observation required'):
        require_preview_observation(tmp_path,board,images)
    (sample/'image-revision-observation.json').write_text(json.dumps(record),encoding='utf-8')
    require_preview_observation(tmp_path,board,images)
    with pytest.raises(ProductionRefused):require_image_review(tmp_path,board,images)
    board['shots'].append(shot)
    with pytest.raises(ProductionRefused):require_preview_observation(tmp_path,board,images)
