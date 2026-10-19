"""Pure final-film protocol tests use authored examples, never claim real review."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace

import pytest

from video_ai.runtime.scene_final_observations import (
    build_scene_final_observation_template, validate_scene_final_observation,
)

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


def context(tmp_path,*,kind='continuation'):
    artifact = dict(path='D:/VideoSi/example', bytes=1, sha256='a'*64)
    selected = dict(scene_id='scene_0001', candidate_id='candidate_0001', baseline_bindings=[dict(kind='character',id='hero')], **artifact)
    candidate = dict(candidate=artifact, subtitle=artifact, created_at='2026-10-19T10:00:00+00:00')
    scene = dict(scene_id='scene_0001', start_frame=0, end_frame=20,
                 bindings=[dict(unit_id='u1',text_start=0,text_end=3)], selected_image=selected)
    first='scene_0001_clip_0001';second='scene_0001_clip_0002' if kind=='continuation' else 'scene_0002_clip_0001'
    clips = [dict(clip_id=first, budget=dict(start_frame=0, end_frame=10), clip_sha256='b'*64,
                  observation_acceptance_sha256='c'*64),
             dict(clip_id=second, budget=dict(start_frame=10, end_frame=20), clip_sha256='d'*64,
                  observation_acceptance_sha256='e'*64)]
    scenes=[scene]
    requests = [dict(clip_id=first, comparison_images=[], parent=None),
                dict(clip_id=second, comparison_images=[], parent=dict(clip_id=first) if kind=='continuation' else None)]
    if kind=='cut':
        scene['end_frame']=10
        second_scene=deepcopy(scene);second_scene.update(scene_id='scene_0002',start_frame=10,end_frame=20)
        second_scene['selected_image']=dict(selected,scene_id='scene_0002',candidate_id='candidate_0002',sha256='2'*64)
        scenes.append(second_scene)
    if kind=='single':
        clips=clips[:1];clips[0]['budget']['end_frame']=20;requests=requests[:1]
    scene_clips = dict(visual_bible_sha256='f'*64, scenes=scenes, clips=clips)
    pcm_path=tmp_path/'pcm.wav';pcm_path.write_bytes(b'actual original pcm fixture bytes')
    pcm = SimpleNamespace(path=pcm_path)
    clip = SimpleNamespace(unit_id='u1', text_start=0, text_end=3, text='原文。',
                           start_sample=0, end_sample=1000, pcm=pcm)
    timeline = SimpleNamespace(total_frames=20, clips=[clip])
    frozen = SimpleNamespace(options=dict(run_id='20261019_example'))
    template = build_scene_final_observation_template(frozen, [], timeline, candidate,
                                                      scene_clips, {}, {}, requests)
    return dict(template=template, created_at=candidate['created_at'])


def authored(expected):
    value = deepcopy(expected['template'])
    value.update(review_method='human_video', reviewer='Authored protocol fixture',
                 viewed_at='2026-10-19T11:00:00+00:00', full_film_watched=True,
                 full_audio_listened=True, subtitle_checked=True,
                 overall_observation='Continuous complete playback compared with originals; no cuts apply.',
                 reason='Authored protocol fixture only.', verdict='passed')
    value['checks'] = dict.fromkeys(value['checks'], 'passed')
    for group in ('scene_observations', 'join_observations', 'narration_observations'):
        for row in value[group]:
            for key in row:
                if key.endswith('_observation') or key == 'observation': row[key] = 'Authored specific observation.'
            if 'verdict' in row: row['verdict'] = 'passed'
    return value


def test_template_is_unverified_pure_and_exactly_binds_scenes_joins_units(tmp_path):
    expected = context(tmp_path); template = expected['template']
    assert template['scene_observations'][0]['baseline_bindings']==[dict(kind='character',id='hero')]
    assert template['verdict'] == 'unverified'
    assert not template['full_film_watched']
    assert template['playback'] == dict(frame_ranges=[dict(start=0,end=20)],
                                        sample_ranges=[dict(start=0,end=60000)])
    assert template['join_observations'][0]['kind'] == 'continuation'
    assert template['join_observations'][0]['played_frames'] == dict(start=0,end=20)
    assert template['narration_observations'][0]['text'] == '原文。'
    assert template['narration_observations'][0]['pcm_sha256']==hashlib.sha256((tmp_path/'pcm.wav').read_bytes()).hexdigest()
    value = authored(expected)
    assert validate_scene_final_observation(value, expected, now=NOW) == value
    assert validate_scene_final_observation(value, expected, now=NOW) is not value
    with pytest.raises(ValueError): validate_scene_final_observation(template, expected, now=NOW)


@pytest.mark.parametrize('path,replacement', [
    (('schema_version',), True), (('candidate','sha256'), 'b'*64),
    (('candidate','bytes'), True), (('scene_observations',0,'start_frame'), False),
    (('narration_observations',0,'text_start'), False),
    (('playback','frame_ranges'), [dict(start=0,end=19)]),
    (('playback','sample_ranges'), [dict(start=False,end=60000)]),
    (('review_method',), 'screenshots'), (('reviewer',), ' '),
    (('viewed_at',), '2026-10-19T09:59:59+00:00'),
    (('viewed_at',), '2026-10-19T12:00:01+00:00'),
    (('viewed_at',), '2026-10-19T11:00:00'),
    (('full_film_watched',), 1), (('full_audio_listened',), False),
    (('scene_observations',0,'identity_observation'), ''),
    (('scene_observations',0,'baseline_bindings'), []),
    (('join_observations',0,'kind'), 'cut'),
    (('join_observations',0,'verdict'), 'failed'),
    (('narration_observations',0,'text'), '摘要'),
    (('narration_observations',0,'pcm_sha256'), '2'*64),
    (('checks','style'), 'unverified'), (('reason',), ' '),
])
def test_rejects_incomplete_or_wrong_identity_and_authorship(tmp_path,path,replacement):
    expected = context(tmp_path); value = authored(expected); target=value
    for key in path[:-1]: target=target[key]
    target[path[-1]]=replacement
    with pytest.raises(ValueError): validate_scene_final_observation(value, expected, now=NOW)


@pytest.mark.parametrize('group', ['scene_observations','join_observations','narration_observations'])
def test_rejects_missing_extra_and_reordered_rows(tmp_path,group):
    expected=context(tmp_path); value=authored(expected)
    value[group][0]['extra']=True
    with pytest.raises(ValueError): validate_scene_final_observation(value,expected,now=NOW)
    value[group]=[]
    with pytest.raises(ValueError): validate_scene_final_observation(value,expected,now=NOW)


def test_explicit_failed_and_unverified_verdicts_are_preserved(tmp_path):
    expected=context(tmp_path); value=authored(expected)
    value['checks']['continuation_joins']='failed'; value['join_observations'][0]['verdict']='failed'
    value.update(verdict='failed',issues=[dict(check='continuation_joins',frames=dict(start=9,end=11),description='Visible jump.')])
    assert validate_scene_final_observation(value,expected,now=NOW)==value


@pytest.mark.parametrize('kind',['cut','single'])
def test_multiple_scene_cuts_and_no_join_keep_every_global_check(tmp_path,kind):
    expected=context(tmp_path,kind=kind);template=expected['template']
    assert set(template['checks'])==set(('subject_identity appearance_structure color_clothing environment_space '
        'time_lighting style motion_process continuation_joins scene_cuts full_narration subtitle_text '
        'audio_video_sync final_quality').split())
    assert all(state=='unverified' for state in template['checks'].values())
    if kind=='cut':
        assert len(template['scene_observations'])==2
        assert template['join_observations'][0]['kind']=='cut'
    else:assert template['join_observations']==[]
    value=authored(expected)
    value['overall_observation']='Complete playback; no continuation boundaries apply.' if kind=='cut' else 'Complete single-clip playback; no continuation or cut boundary applies.'
    assert validate_scene_final_observation(value,expected,now=NOW)==value
    value['checks']['continuation_joins']='unverified'
    with pytest.raises(ValueError):validate_scene_final_observation(value,expected,now=NOW)
    value=authored(expected);value['overall_observation']=''
    with pytest.raises(ValueError):validate_scene_final_observation(value,expected,now=NOW)
    value=authored(expected); value['full_audio_listened']=False; value['verdict']='unverified'
    assert validate_scene_final_observation(value,expected,now=NOW)==value


@pytest.mark.parametrize('group',['selected_images','comparison_images','clip_acceptances','scene_observations'])
def test_ordered_scene_and_clip_identity_cannot_be_reversed(tmp_path,group):
    expected=context(tmp_path,kind='cut');value=authored(expected)
    value[group].reverse()
    with pytest.raises(ValueError):validate_scene_final_observation(value,expected,now=NOW)
