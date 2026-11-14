from types import SimpleNamespace

from video_ai.runtime.scene_image_prompts import effective_image_prompt


def test_imported_prompt_reuses_the_admitted_source(monkeypatch,tmp_path):
    from video_ai.runtime import scene_revision_records as records,production_inputs
    from video_ai.planning import scene_revision
    origin=frozen(focused=False)
    current=SimpleNamespace(options=dict(scene_revision={},script_path=str(tmp_path/'production/script.txt')))
    proof=dict(commit=dict(request=dict(path='request.json')),invalidation=dict(dirty=dict(images=[])),
               imports={'plan:all':None},source_run=tmp_path/'source',source_frozen=origin)
    monkeypatch.setattr(records,'require_scene_revision',lambda value:proof)
    monkeypatch.setattr(records,'_json',lambda *args,**kwargs:{})
    monkeypatch.setattr(scene_revision,'validate_revision_request_fields',lambda request:{})
    def unexpected_reload(*args,**kwargs):
        raise AssertionError('already admitted source must not be loaded again')
    monkeypatch.setattr(production_inputs,'load_frozen_inputs',unexpected_reload)
    assert effective_image_prompt(current,dict(scene_id='scene_0001',image_prompt='original'))=='original'


def frozen(text='它就是旅行者2号。',focused=True):
    return SimpleNamespace(options={},script=SimpleNamespace(text=text),config=SimpleNamespace(
        raw={'scene_planner_transport':'focused_v1'} if focused else {}))


def test_visible_voyager_has_positive_spacecraft_geometry():
    prompt=effective_image_prompt(frozen(),dict(image_prompt='探测器独自在宇宙深处飞行。'))
    assert '3.7米' in prompt and '白色抛物面' in prompt and '三节黑色圆柱' in prompt
    assert '宇宙深处' in prompt


def test_planet_launch_and_record_scenes_keep_their_actual_subject():
    for original in ['木星表面，大红斑风暴正在旋转。','运载火箭搭载旅行者2号从发射场升空。',
                     '旅行者2号上的金色唱片，表面有精细刻纹。','探测器携带一张金色的唱片。']:
        prompt=effective_image_prompt(frozen(),dict(image_prompt=original))
        assert original in prompt
        assert '3.7米' not in prompt


def test_legacy_and_other_topics_keep_original_prompts():
    original='探测器飞行。'
    assert effective_image_prompt(frozen(focused=False),dict(image_prompt=original))==original
    assert effective_image_prompt(frozen(text='火星探测任务。'),dict(image_prompt=original))==original


def test_observers_view_space_from_a_ground_control_room():
    original='科学家在观察木卫一的火山，背景是黑暗宇宙。'
    prompt=effective_image_prompt(frozen(),dict(image_prompt=original))
    assert '地球上的任务控制中心' in prompt and '屏幕' in prompt
