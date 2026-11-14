import json

from video_ai.runtime.production_visual_storyboard import _with_subject_context


def test_planet_subject_overrides_previous_probe_and_entity_catalog():
    data = dict(global_visual=dict(entities=[dict(entity_id='Voyager 2')]),
                previous_scene=dict(image_prompt='A probe drifting in space'),
                shots=[dict(shot_id='shot_0061', source_quote='这是太阳系中最大的行星，',
                            source_facts=dict(subject='木星', action_or_state='是太阳系中最大的行星')),
                       dict(shot_id='shot_0062', source_quote='质量超过地球的300倍，',
                            source_facts=dict(subject='木星', action_or_state='质量超过地球的300倍'))])
    original = 'instructions\nVISUAL_INPUT_JSON\n' + json.dumps(data, ensure_ascii=False)
    result = _with_subject_context(original)
    updated = json.loads(result.split('\nVISUAL_INPUT_JSON\n')[1])
    assert updated['shots'][0]['scene_subject'] == '木星'
    assert updated['shots'][0]['subject_transition'] == 'explicit_subject'
    assert updated['shots'][1]['scene_subject'] == '木星'
    assert updated['entity_catalog'] == [dict(entity_id='Voyager 2')]
    assert 'previous_scene' not in updated
    assert data['global_visual'] == dict(entities=[dict(entity_id='Voyager 2')])
    assert updated['shots'][0]['source_facts'] == data['shots'][0]['source_facts']
    assert 'not a list of permitted scene subjects' in result
    assert _with_subject_context(result) == result


def test_abstract_quote_keeps_continuity_without_inventing_subject():
    data = dict(shots=[dict(shot_id='s', source_quote='但这并不是终点。',
                           source_facts=dict(subject=None))])
    result = _with_subject_context('instructions\nVISUAL_INPUT_JSON\n' + json.dumps(data))
    shot = json.loads(result.split('\nVISUAL_INPUT_JSON\n')[1])['shots'][0]
    assert shot['scene_subject'] is None
    assert shot['subject_transition'] == 'resolve_from_original_context'


def test_scene_repair_checkpoint_accepts_durable_batch_id(tmp_path):
    from video_ai.runtime.production_visual_records import validate_visual_checkpoint
    validate_visual_checkpoint('storyboard', 'storyboard_batch_0008_scenerepair',
        dict(batch_id='storyboard_batch_0008', shot_ids=['shot_0061'],
             format_valid=True, content={}, error=None), tmp_path)
