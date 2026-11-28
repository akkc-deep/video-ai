"""Mail submissions preserve original identities and explicit author evidence."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib
import json

import pytest

from video_ai.runtime.scene_clip_observations import CHECK_FIELDS, AUTHORED_FIELDS
from video_ai.runtime.scene_final_observations import CHECK_FIELDS as FINAL_CHECKS
from video_ai.runtime.scene_final_observations import validate_scene_final_observation


AT = '2026-11-29T10:00:00+00:00'


def api():
    return importlib.import_module('video_ai.mail_review_requests')


def artifact(path):
    return dict(path=str(path), bytes=1, sha256='a'*64)


def clip_template(tmp_path):
    return dict(schema_version=2, production_strategy='paragraph_jimeng_v1', run_id='run1',
        scope='scene_clip_process', scene_id='scene_0001', clip_id='scene_0001_clip_0001',
        clip_sha256='b'*64, request_sha256='c'*64, visual_bible_sha256='d'*64,
        selected_image=dict(scene_id='scene_0001', candidate_id='candidate_0001', **artifact(tmp_path/'selected.png')),
        comparison_images=[], generated=artifact(tmp_path/'generated.mp4'), source=artifact(tmp_path/'source.mp4'),
        last_frame=artifact(tmp_path/'last.png'), parent=None,
        playback=dict(clip_source_frames=[0,93],parent_source_frames=None),
        review_method=None, reviewer=None, viewed_at=None,
        checks={k: None if k=='parent_join' else 'unverified' for k in CHECK_FIELDS},
        verdict='unverified', issues=[], **dict.fromkeys(AUTHORED_FIELDS,''))


def clip_request(tmp_path):
    template=clip_template(tmp_path)
    request=api().build_review_request(dict(status='awaiting_continuity_review', run_dir=str(tmp_path),
        observation_templates=[template]))
    return template,request


def clip_authored(template, state='passed'):
    return dict(checks={k: None if s is None else state for k,s in template['checks'].items()},
        verdict=state, issues=[], **dict.fromkeys(AUTHORED_FIELDS,'人工实际观察：主体沿画面左侧缓慢移动。'))


def reply(reviews, **extra):
    return json.dumps(dict(确认='提交',完整查看=True,reviews=reviews,**extra),ensure_ascii=False)


def test_clip_request_binds_original_media_and_roundtrips_human_fields(tmp_path):
    template,request=clip_request(tmp_path)
    assert request['kind']=='scene_clip_process'
    assert request['action']=='clip_observation'
    assert request['templates']==[template]
    assert str(tmp_path/'source.mp4') in request['attachments']
    assert str(tmp_path/'selected.png') in request['attachments']
    authored=clip_authored(template)
    result=api().parse_review_reply(request,reply([authored]),reviewer='person@example.com',viewed_at=AT)
    assert result==[dict(template,**authored,review_method='human_video',reviewer='person@example.com',viewed_at=AT)]
    assert template['reviewer'] is None
    assert api().build_review_request(dict(status='awaiting_continuity_review',observation_templates=[template]))['binding']==request['binding']
    changed=deepcopy(template);changed['source']['sha256']='e'*64
    assert api().build_review_request(dict(observation_templates=[changed]))['binding']!=request['binding']


@pytest.mark.parametrize('transform',[
    lambda v:dict(v,确认=''),lambda v:dict(v,完整查看=False),
    lambda v:dict(v,reviews=[]),lambda v:dict(v,reviews=[dict(v['reviews'][0],reviewer='robot')]),
    lambda v:dict(v,reviews=[dict(v['reviews'][0],source={})]),
    lambda v:dict(v,reviews=[dict(v['reviews'][0],process_observation='')]),
    lambda v:dict(v,reviews=[dict(v['reviews'][0],checks={})]),
    lambda v:dict(v,reviews=[dict(v['reviews'][0],verdict='passed',checks=dict(v['reviews'][0]['checks'],style='unverified'))]),
])
def test_rejects_incomplete_or_identity_overriding_replies(tmp_path,transform):
    template,request=clip_request(tmp_path)
    data=dict(确认='提交',完整查看=True,reviews=[clip_authored(template)])
    with pytest.raises(ValueError):
        api().parse_review_reply(request,json.dumps(transform(data)),reviewer='human',viewed_at=AT)


@pytest.mark.parametrize('state',['failed','unverified'])
def test_negative_clip_judgments_never_become_passed(tmp_path,state):
    template,request=clip_request(tmp_path)
    authored=clip_authored(template,state)
    if state=='failed': authored['issues']=[dict(check='style',frames=[2,7],description='人工观察到风格变化。')]
    result=api().parse_review_reply(request,reply([authored]),reviewer='human',viewed_at=AT)
    assert result[0]['verdict']==state
    assert result[0]['checks']['style']==state


def final_template(tmp_path):
    return dict(schema_version=2,production_strategy='paragraph_jimeng_v1',run_id='run1',scope='scene_final_film',
        composition_sha256='1'*64,candidate=artifact(tmp_path/'final.mp4'),subtitle=artifact(tmp_path/'final.srt'),
        scene_clips_sha256='2'*64,upscale_sha256='3'*64,image_acceptance_sha256='4'*64,visual_bible_sha256='5'*64,
        selected_images=[],comparison_images=[],clip_acceptances=[],
        playback=dict(frame_ranges=[dict(start=0,end=20)],sample_ranges=[dict(start=0,end=60000)]),
        review_method=None,reviewer=None,viewed_at=None,full_film_watched=False,full_audio_listened=False,subtitle_checked=False,
        overall_observation='',scene_observations=[dict(scene_id='scene_0001',start_frame=0,end_frame=20,
            selected_image_sha256='6'*64,baseline_bindings=[],identity_observation='',appearance_observation='',
            environment_observation='',style_observation='',motion_observation='')],
        join_observations=[dict(from_clip_id='c1',to_clip_id='c2',kind='cut',boundary_frame=10,
            played_frames=dict(start=0,end=20),observation='',verdict='unverified')],
        narration_observations=[dict(unit_id='u1',text_start=0,text_end=3,text='原文。',start_sample=0,end_sample=1000,
            pcm_sha256='7'*64,audio_observation='',subtitle_observation='',semantics_observation='',sync_observation='')],
        checks=dict.fromkeys(FINAL_CHECKS,'unverified'),verdict='unverified',issues=[],reason='')


def test_final_authored_fields_restore_exact_scenes_joins_narration_and_validate(tmp_path):
    template=final_template(tmp_path)
    request=api().build_review_request(dict(status='awaiting_final_review',final_observation_template=template))
    body=json.loads(request['body_template'].split('\n',2)[-1])
    authored=body['reviews'][0]
    authored.update(full_film_watched=True,full_audio_listened=True,subtitle_checked=True,
        overall_observation='已完整播放并逐句核对原文。',reason='人工逐项检查。',checks=dict.fromkeys(FINAL_CHECKS,'passed'),verdict='passed')
    for group in ('scene_observations','join_observations','narration_observations'):
        for row in authored[group]:
            for key in row:
                row[key]='passed' if key=='verdict' else '人工看到该场景实际运动，字幕与原文一致。'
    result=api().parse_review_reply(request,reply([authored]),reviewer='human',viewed_at=AT)[0]
    assert result['narration_observations'][0]['text']=='原文。'
    assert result['join_observations'][0]['boundary_frame']==10
    assert result['scene_observations'][0]['selected_image_sha256']=='6'*64
    assert validate_scene_final_observation(result,dict(template=template,created_at='2026-11-29T09:00:00+00:00'),now=AT)==result


def test_publish_requires_explicit_approval_and_binds_candidate(tmp_path):
    request=api().build_review_request(dict(status='final_review_ready',candidate=str(tmp_path/'final.mp4'),
        final_observation_template=final_template(tmp_path)))
    assert request['kind']=='publish' and request['action']=='publish'
    with pytest.raises(ValueError): api().parse_review_reply(request,reply([]),reviewer='human',viewed_at=AT)
    assert api().parse_review_reply(request,reply([],发布=True),reviewer='human',viewed_at=AT)==[{'publish':True}]
    assert api().build_review_request(dict(status='completed')) is None


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


def test_complete_image_group_preserves_accepted_choices_and_all_scene_coverage(tmp_path):
    scenes=[dict(scene_id='s1'),dict(scene_id='s2')]
    write_json(tmp_path/'production/scene-plan.json',dict(payload=dict(scenes=scenes,batches=[['s1'],['s2']])))
    last=None
    for i,scene in enumerate(scenes,1):
        choice=dict(scene_id=scene['scene_id'],candidate_id='candidate_0001',sha256=str(i)*64)
        folder=tmp_path/f'production/image-selection/image_batch_{i:04d}'
        selection=dict(schema_version=2,run_id='run1',batch_id=folder.name,scene_manifest_sha256='a'*64,
            scene_plan_sha256='b'*64,visual_bible_sha256='c'*64,baseline_bindings=[],intent='accept',selections=[choice],observation=None)
        raw=json.dumps(selection).encode();sha=hashlib.sha256(raw).hexdigest()
        write_json(folder/'batch.json',dict(batch_index=i,scenes=[dict(scene_id=scene['scene_id'])]))
        write_json(folder/'accepted.json',dict(selections=[dict(artifact(tmp_path/f'{i}.png'),**choice)],source_submission_sha256=sha))
        (folder/'submissions').mkdir();(folder/f'submissions/{sha}.json').write_bytes(raw)
        last=selection
    request=api().build_review_request(dict(status='image_batch_accepted',run_dir=str(tmp_path),batch_id='image_batch_0002',all_images_accepted=False))
    assert request['kind']=='image_group_review' and request['action']=='image_selection'
    assert request['templates']==[last]
    authored=dict(subject_consistency='unverified',style_consistency='passed',verdict='unverified',issues=[],reason='主体尚不能确认。')
    result=api().parse_review_reply(request,reply([authored]),reviewer='human',viewed_at=AT)[0]
    assert result['selections']==last['selections']
    assert [r['scene_id'] for r in result['observation']['viewed_images']]==['s1','s2']
    assert result['observation']['subject_consistency']=='unverified'
    assert result['observation']['review_method']=='human_image'
    assert result['observation']['reviewer']=='human'
    assert set(request['attachments'])=={str(tmp_path/'1.png'),str(tmp_path/'2.png')}
    (tmp_path/'production/image-selection/image_batch_0001/accepted.json').unlink()
    assert api().build_review_request(dict(status='image_batch_accepted',run_dir=str(tmp_path),all_images_accepted=False)) is None



def continuity_fixture(tmp_path,count=3):
    template=clip_template(tmp_path)
    cid=template['clip_id']
    clips=[]
    for i in range(count):
        folder=tmp_path/f'production/scene-clips/clips/c{i}'
        write_json(folder/'clip.json',dict(created_at='2026-11-29T09:00:00+00:00'))
        clips.append(dict(clip_id=cid if i==count-1 else f'c{i}',clip_record=artifact(folder/'clip.json'),
            source=artifact(tmp_path/f'prefix{i}.mp4'),source_frames=[0,93],output_frames=[i*93,(i+1)*93]))
    write_json(Path(clips[-1]['clip_record']['path']).parent/'observation-template.json',template)
    folder=tmp_path/'production/scene-continuity/jobs/assessment-1'
    assessment=dict(schema_version=1,run_id='run1',assessment_id='assessment-1',clip_id=cid,
        epoch=artifact(tmp_path/'epoch.json'),binding=dict(scene_id=template['scene_id'],clip_id=cid,clips=clips),
        concerns=[dict(concern_id='f'*64,detector_id='drift',region_id='subject',status='unverified',reasons=['需人工确认'],evidence=[])],closure=[])
    write_json(folder/'assessment.json',assessment)
    review=dict(schema_version=1,run_id='run1',assessment_id='assessment-1',assessment=artifact(folder/'assessment.json'),
        video_observation=None,prefix_observation=None,reviewer='',reviewed_at=None,
        responses=[dict(concern_id='f'*64,disposition='unverified',reason='',references=[])])
    write_json(folder/'review-template.json',review)
    return template,assessment,review,folder/'review-template.json'


def test_continuity_rehydrates_video_prefix_and_concerns_with_exact_staged_refs(tmp_path):
    template,assessment,review,path=continuity_fixture(tmp_path)
    before=set(tmp_path.rglob('*'))
    request=api().build_review_request(dict(status='awaiting_review',run_dir=str(tmp_path),review_template=str(path)))
    assert request['action']=='continuity_review'
    assert request['templates'][0]==template and request['templates'][-1]==review
    assert len(request['submission_paths'])==3
    assert all(Path(p).is_relative_to(tmp_path/'production/mail-workflow/submissions'/request['binding']) for p in request['submission_paths'])
    authored=[clip_authored(template),dict(start_observation='完整前缀开头稳定。',process_observation='完整前缀主体缓慢移动。',
        end_observation='前缀结尾主体位于左侧。',quality_observation='已连续播放所有保留片段。',
        checks=dict.fromkeys(('subject_identity','color_lighting','motion_process','camera_path','cumulative_color'),'passed'),
        verdict='passed',issues=[]),dict(responses=[dict(disposition='not_observed_in_full_playback',reason='连续回放未看到检测器提示的漂移。',reference_indices=[])])]
    values=api().parse_review_reply(request,reply(authored),reviewer='human',viewed_at=AT)
    assert len(values)==3
    assert values[-1]['responses']==[dict(concern_id='f'*64,disposition='not_observed_in_full_playback',reason='连续回放未看到检测器提示的漂移。',references=[])]
    for name,index in [('video_observation',0),('prefix_observation',1)]:
        raw=api().encode_submission(values[index])
        assert values[-1][name]==dict(path=request['submission_paths'][index],bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    assert values[1]['playback']==[{k:c[k] for k in ('clip_id','source','source_frames','output_frames')} for c in assessment['binding']['clips']]
    assert values[-1]['reviewer']=='human' and values[-1]['reviewed_at']==AT
    assert set(tmp_path.rglob('*'))==before


def test_continuity_unverified_keeps_original_disposition_and_small_prefix_reuses_video(tmp_path):
    template,assessment,review,path=continuity_fixture(tmp_path,count=2)
    request=api().build_review_request(dict(status='awaiting_review',run_dir=str(tmp_path),review_template=str(path)))
    authored=[clip_authored(template,'unverified'),dict(responses=[dict(disposition='unverified',reason='回放后仍不能判断。',reference_indices=[])])]
    values=api().parse_review_reply(request,reply(authored),reviewer='human',viewed_at=AT)
    assert len(values)==2 and values[0]['verdict']=='unverified'
    assert values[-1]['prefix_observation']==values[-1]['video_observation']
    assert values[-1]['responses'][0]['disposition']=='unverified'
    authored[-1]['responses'][0]['disposition']='not_observed_in_full_playback'
    with pytest.raises(ValueError): api().parse_review_reply(request,reply(authored),reviewer='human',viewed_at=AT)


@pytest.mark.parametrize('scope',['temporal_window_static','scene_temporal_chain_process'])
def test_native_windows_and_full_chains_preserve_source_binding(tmp_path,scope):
    template=dict(schema_version=1,production_strategy='paragraph_jimeng_v1',run_id='run1',scope=scope,
        binding=dict(terminal=False,contact_sheet=artifact(tmp_path/'sheet.png'),viewing=artifact(tmp_path/'chain.mp4')),
        playback=None if scope=='temporal_window_static' else [0,93],review_method=None,reviewer=None,viewed_at=None,
        checks=dict.fromkeys(('subject','color','composition','camera','motion'),'unverified'),verdict='unverified',reason=None,allow_next_window=False)
    request=api().build_review_request(dict(observation_templates=[template]))
    state='acceptable' if scope=='temporal_window_static' else 'passed'
    authored=dict(checks=dict.fromkeys(template['checks'],state),verdict=state,reason='人工实际查看所附完整素材。')
    result=api().parse_review_reply(request,reply([authored]),reviewer='human',viewed_at=AT)[0]
    assert result['binding']==template['binding']
    assert result['review_method']==('human_image' if scope=='temporal_window_static' else 'human_video')
    assert result['allow_next_window']==(scope=='temporal_window_static')



def test_pending_current_continuity_review_takes_precedence_over_clip_only_reply(tmp_path):
    template,assessment,review,path=continuity_fixture(tmp_path,count=2)
    # Current head is bound by the small epoch commit; no media is opened.
    epoch_folder=tmp_path/'production/scene-continuity/epochs/current'
    commit=dict(epoch_id='current',intent=artifact(epoch_folder/'intent.json'))
    write_json(epoch_folder/'intent.json',dict(previous_commit=None))
    write_json(epoch_folder/'commit.json',commit)
    raw=(epoch_folder/'commit.json').read_bytes()
    assessment['epoch']=dict(path=str(epoch_folder/'commit.json'),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    write_json(path.parent/'assessment.json',assessment)
    request=api().build_review_request(dict(status='awaiting_continuity_review',run_dir=str(tmp_path),observation_templates=[template]))
    assert request['kind']=='continuity_review'
    assert request['context']['assessment']['epoch']==assessment['epoch']
    assessment['epoch']['sha256']='0'*64
    write_json(path.parent/'assessment.json',assessment)
    # A stale assessment must never be submitted for the current clip gate.
    request=api().build_review_request(dict(status='awaiting_continuity_review',run_dir=str(tmp_path),observation_templates=[template]))
    assert request['kind']=='scene_clip_process'


def test_publish_without_immutable_candidate_template_is_not_supported(tmp_path):
    assert api().build_review_request(dict(status='final_review_ready',candidate=str(tmp_path/'final.mp4'))) is None


def test_ambiguous_duplicate_json_confirmations_are_rejected(tmp_path):
    template,request=clip_request(tmp_path)
    text=reply([clip_authored(template)]).replace('"确认": "提交"','"确认": "取消", "确认": "提交"')
    with pytest.raises(ValueError): api().parse_review_reply(request,text,reviewer='human',viewed_at=AT)
