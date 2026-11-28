"""Bind email authored review fields to immutable production templates.

This module reads small JSON records only. It never generates media, verifies
media bytes, writes files, or claims a person viewed an artifact.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from .runtime.scene_clip_observations import AUTHORED_FIELDS as CLIP_TEXT
from .runtime.scene_final_observations import SCENE_TEXT, NARRATION_TEXT


STATES = ('passed', 'failed', 'unverified')
SCOPES = ('scene_clip_process', 'scene_final_film', 'temporal_window_static', 'scene_temporal_chain_process')


def encode_submission(value):
    """Exact UTF-8 canonical bytes used for staged continuity artifact references."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _read(value):
    if isinstance(value, dict) and not set(value) == {'path', 'bytes', 'sha256'}:
        return deepcopy(value)
    path = value['path'] if isinstance(value, dict) else value
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _attachments(value):
    paths = []
    def visit(node):
        if isinstance(node, dict):
            path = node.get('path')
            if isinstance(path, str) and Path(path).suffix.lower() in ('.mp4','.mov','.mkv','.webm','.png','.jpg','.jpeg','.webp','.wav','.srt'):
                if path not in paths: paths.append(path)
            for child in node.values(): visit(child)
        elif isinstance(node, list):
            for child in node: visit(child)
    visit(value)
    return paths


def _authored(template):
    scope = template['scope']
    if scope == 'image_group_review':
        return dict(subject_consistency='unverified', style_consistency='unverified', verdict='unverified', issues=[], reason='')
    if scope in ('temporal_window_static', 'scene_temporal_chain_process'):
        return dict(checks=deepcopy(template['checks']), verdict='unverified', reason='')
    common = dict(checks=deepcopy(template['checks']), verdict='unverified', issues=[], reason='')
    if scope == 'scene_clip_process':
        return dict(common, **dict.fromkeys(CLIP_TEXT, ''))
    if scope == 'scene_final_film':
        common.update(full_film_watched=False, full_audio_listened=False, subtitle_checked=False, overall_observation='')
        for group, fields in (('scene_observations',SCENE_TEXT), ('join_observations',('observation','verdict')),
                               ('narration_observations',NARRATION_TEXT)):
            common[group] = [{key: ('unverified' if key=='verdict' else '') for key in fields} for _ in template[group]]
        return common
    raise ValueError('unsupported review scope')


def _request(kind, templates, action, *, context=None, attachments=None):
    binding = hashlib.sha256(encode_submission(dict(kind=kind, templates=templates, context=context))).hexdigest()
    authored = [] if kind=='publish' else [_authored(t) for t in templates]
    envelope = dict(确认='', 完整查看=False, reviews=authored)
    if kind=='publish': envelope['发布']=False
    order=[]
    for template in templates:
        if template.get('scope')=='scene_final_film':
            order.append(dict(场景顺序=[{k:r[k] for k in ('scene_id','start_frame','end_frame')} for r in template['scene_observations']],
                接点顺序=[{k:r[k] for k in ('from_clip_id','to_clip_id','kind','boundary_frame')} for r in template['join_observations']],
                旁白顺序=[{k:r[k] for k in ('unit_id','text')} for r in template['narration_observations']]))
        else:
            identity=template.get('binding',template)
            order.append({k:identity[k] for k in ('scene_id','clip_id') if k in identity})
    labels=json.dumps(order,ensure_ascii=False)
    states='acceptable/rejected/unverified' if kind=='temporal_window_static' else 'passed/failed/unverified'
    body = ('请完整查看附件；视频须完整连续播放，成片还须听完旁白并核对字幕。仅填写本人实际观察和判断。填写顺序：'+labels+'\n'
            '将“确认”改为“提交”、“完整查看”改为 true；各判断可填 '+states+'，最后仅回复下方 JSON。\n'
            + json.dumps(envelope,ensure_ascii=False,indent=2))
    return dict(kind=kind,binding=binding,subject='视频制作确认：'+kind,body_template=body,
                templates=deepcopy(templates),attachments=_attachments(templates) if attachments is None else attachments,
                action=action,context=deepcopy(context))


def _image_group(result):
    if result.get('all_images_accepted') or not result.get('run_dir'): return None
    run=Path(result['run_dir']); plan=_read(run/'production/scene-plan.json')
    plan=plan.get('payload',plan)
    expected=[r['scene_id'] for r in plan['scenes']]
    choices={}; images=[]; sources=[]; last=None; last_batch=None
    for index in range(1,len(plan['batches'])+1):
        folder=run/'production/image-selection'/f'image_batch_{index:04d}'
        if not (folder/'accepted.json').is_file(): return None
        accepted=_read(folder/'accepted.json'); batch=_read(folder/'batch.json')
        sha=accepted['source_submission_sha256']
        if not isinstance(sha,str) or re.fullmatch('[0-9a-f]{64}',sha) is None: raise ValueError('invalid accepted submission identity')
        raw=(folder/'submissions'/(sha+'.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha: raise ValueError('accepted submission bytes changed')
        submission=json.loads(raw.decode('utf-8-sig'))
        if submission['intent']!='accept' or submission['batch_id']!=folder.name: raise ValueError('accepted batch identity differs')
        submitted={r['scene_id']:r for r in submission['selections']}
        if set(submitted)!={r['scene_id'] for r in batch['scenes']}: raise ValueError('incomplete accepted batch')
        for row in accepted['selections']:
            sid=row['scene_id']; choice={k:row[k] for k in ('scene_id','candidate_id','sha256')}
            if sid in choices or choice!=submitted.get(sid): raise ValueError('accepted choices differ')
            choices[sid]=choice; images.append(row['path'])
        sources.append(dict(batch=batch,accepted=accepted,submission_sha256=sha))
        last=submission; last_batch=folder.name
    if set(choices)!=set(expected) or len(expected)!=len(set(expected)): return None
    if result.get('batch_id',last_batch)!=last_batch: return None
    context=dict(viewed_images=[choices[sid] for sid in expected],sources=sources,scene_plan=plan)
    request=_request('image_group_review',[dict(scope='image_group_review')],'image_selection',context=context,attachments=images)
    # Keep the original selected submission unchanged in the journal and digest.
    request['templates']=[last]
    request['binding']=hashlib.sha256(encode_submission(dict(kind=request['kind'],templates=[last],context=context))).hexdigest()
    return request


def build_review_request(result):
    """Return a durable request for a known pending gate, otherwise None."""
    if result.get('status')=='image_batch_accepted': return _image_group(result)
    final=result.get('final_observation_template')
    if result.get('status')=='final_review_ready':
        if not final: return None
        templates=[_read(final)]
        return _request('publish',templates,'publish',context=dict(candidate=result.get('candidate'),run_id=result.get('run_id')))
    if final:
        template=_read(final)
        return _request('scene_final_film',[template],'final_observation')
    review=result.get('review_template')
    if review: return _continuity_request(result,review)
    if result.get('status')=='awaiting_continuity_review' and result.get('run_dir'):
        run=Path(result['run_dir']); current=_current_epoch(run)
        root=run/'production/scene-continuity/jobs'
        for path in sorted(root.glob('*/review-template.json')):
            review_value=_read(path); assessment=_read(review_value['assessment'])
            if current is None or assessment.get('epoch')!=current: continue
            receipt=root.parent/'reviews'/path.parent.name/'receipt.json'
            if receipt.exists() and _read(receipt).get('state')!='awaiting_review': continue
            request=_continuity_request(result,path)
            if request is not None: return request
    templates=[_read(v) for v in result.get('observation_templates',[])]
    if templates:
        if any(t.get('scope') not in SCOPES or t['scope']=='scene_final_film' for t in templates): return None
        if len({t['scope'] for t in templates})!=1: return None
        return _request(templates[0]['scope'],templates,'clip_observation')
    return None


def _current_epoch(run):
    """Find the unique completed epoch head from small local records only."""
    folders=list((run/'production/scene-continuity/epochs').glob('*/intent.json'))
    commits=[]; previous=[]
    for path in folders:
        commit=path.parent/'commit.json'
        if not commit.is_file(): return None
        intent=_read(path)
        if intent['previous_commit'] is not None: previous.append(intent['previous_commit'])
        raw=commit.read_bytes()
        commits.append(dict(path=str(commit),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    heads=[c for c in commits if c not in previous]
    return heads[0] if len(heads)==1 else None


def _exact(value,fields,label):
    if not isinstance(value,dict) or set(value)!=set(fields): raise ValueError(label+': exact fields required')


def _text(value):
    if not isinstance(value,str) or not value.strip(): raise ValueError('human observation text required')


def _checks(authored,original,*,static=False):
    _exact(authored,original,'checks')
    states=('acceptable','rejected','unverified') if static else STATES
    for key,state in authored.items():
        if original[key] is None:
            if state is not None: raise ValueError('inapplicable check must remain null')
        elif state not in states: raise ValueError('invalid check judgment')


def _verdict(value, *, static=False):
    states=[s for s in value['checks'].values() if s is not None]
    verdict=value['verdict']
    if static:
        valid=(verdict=='acceptable' and 'rejected' not in states and all(value['checks'][k]=='acceptable' for k in ('subject','color','composition'))
            or verdict=='rejected' and 'rejected' in states or verdict=='unverified' and 'rejected' not in states and 'unverified' in states)
    else:
        valid=(verdict=='passed' and all(s=='passed' for s in states) or verdict=='failed' and 'failed' in states
            or verdict=='unverified' and 'failed' not in states and 'unverified' in states)
        if 'issues' in value:
            valid=valid and isinstance(value['issues'],list) and (verdict!='passed' or not value['issues']) and (verdict!='failed' or bool(value['issues']))
    if not valid: raise ValueError('verdict contradicts explicit checks')


def _observation(template,authored,reviewer,viewed_at):
    expected=_authored(template);_exact(authored,expected,'authored review')
    _checks(authored['checks'],template['checks'],static=template['scope']=='temporal_window_static')
    for key in expected:
        if key.endswith('_observation') or key=='reason': _text(authored[key])
    value=deepcopy(template);value.update(deepcopy(authored),review_method='human_image' if template['scope']=='temporal_window_static' else 'human_video',reviewer=reviewer,viewed_at=viewed_at)
    if template['scope']=='scene_final_film':
        for key in ('full_film_watched','full_audio_listened','subtitle_checked'):
            if value[key] is not True: raise ValueError('explicit complete film, audio and subtitle review required')
        for group in ('scene_observations','join_observations','narration_observations'):
            rows=authored[group]
            if not isinstance(rows,list) or len(rows)!=len(template[group]): raise ValueError('incomplete authored coverage')
            rehydrated=[]
            for row,fields,original in zip(rows,expected[group],template[group]):
                _exact(row,fields,'authored row')
                for key,text in row.items():
                    if key=='verdict':
                        if text not in STATES: raise ValueError('invalid join judgment')
                    else: _text(text)
                rehydrated.append(dict(deepcopy(original),**deepcopy(row)))
            value[group]=rehydrated
        # The pure validator verifies every nested identity and declared issue.
        from .runtime.scene_final_observations import validate_scene_final_observation
        validate_scene_final_observation(value,dict(template=template,created_at=viewed_at),now=viewed_at)
    elif template['scope']=='scene_clip_process':
        for key in CLIP_TEXT: _text(value[key])
        end=template['playback']['clip_source_frames'][1]
        if not isinstance(value['issues'],list): raise ValueError('issues must be an array')
        for issue in value['issues']:
            _exact(issue,('check','frames','description'),'issue');_text(issue['description'])
            frames=issue['frames']
            if issue['check'] not in value['checks'] or value['checks'][issue['check']] is None: raise ValueError('invalid issue check')
            if not isinstance(frames,list) or len(frames)!=2 or any(type(f) is not int for f in frames) or not 0<=frames[0]<frames[1]<=end: raise ValueError('invalid issue frames')
        _verdict(value)
    else:
        _verdict(value,static=template['scope']=='temporal_window_static')
        value['allow_next_window']=bool(template['scope']=='temporal_window_static' and value['verdict']=='acceptable' and not template['binding']['terminal'])
    return value


def parse_review_reply(request,text,*,reviewer,viewed_at):
    """Rehydrate only explicitly authored fields; quoted templates are ineligible."""
    _text(reviewer);_text(viewed_at)
    try:
        stamp=datetime.fromisoformat(viewed_at)
        if stamp.tzinfo is None or stamp.utcoffset() is None: raise ValueError()
        def unique_pairs(pairs):
            value={}
            for key,item in pairs:
                if key in value: raise ValueError('duplicate JSON field')
                value[key]=item
            return value
        data=json.loads(text,object_pairs_hook=unique_pairs)
    except (ValueError,TypeError) as exc: raise ValueError('reply must be one JSON object with timezone-aware viewing metadata') from exc
    fields=('确认','完整查看','reviews')+ (('发布',) if request['kind']=='publish' else ())
    _exact(data,fields,'reply')
    if data['确认']!='提交' or data['完整查看'] is not True: raise ValueError('explicit submission and full viewing declaration required')
    if not isinstance(data['reviews'],list): raise ValueError('reviews must be an array')
    if request['kind']=='publish':
        if data['发布'] is not True or data['reviews']: raise ValueError('explicit publish approval required')
        return [dict(publish=True)]
    if request['kind']=='continuity_review': return _parse_continuity(request,data['reviews'],reviewer,viewed_at)
    if len(data['reviews'])!=len(request['templates']): raise ValueError('complete review coverage required')
    if request['kind']=='image_group_review':
        authored=data['reviews'][0]; _exact(authored,_authored(dict(scope='image_group_review')),'image group fields')
        _text(authored['reason'])
        for key in ('subject_consistency','style_consistency','verdict'):
            if authored[key] not in STATES: raise ValueError('invalid image judgment')
        if not isinstance(authored['issues'],list): raise ValueError('issues must be list')
        for issue in authored['issues']: _text(issue)
        _verdict(dict(authored,checks={key:authored[key] for key in ('subject_consistency','style_consistency')}))
        value=deepcopy(request['templates'][0]);value.pop('local_review',None)
        value.update(intent='accept',observation=dict(authored,scope='all_selected_images',review_method='human_image',reviewer=reviewer,viewed_images=deepcopy(request['context']['viewed_images'])))
        return [value]
    return [_observation(t,a,reviewer,viewed_at) for t,a in zip(request['templates'],data['reviews'])]


PREFIX_TEXT = ('start_observation','process_observation','end_observation','quality_observation')
PREFIX_CHECKS = ('subject_identity','color_lighting','motion_process','camera_path','cumulative_color')
DISPOSITIONS = ('not_observed_in_full_playback','explained_change','confirmed_issue','unverified')


def _prefix_authored(template):
    return dict(checks=deepcopy(template['checks']),verdict='unverified',issues=[],**dict.fromkeys(PREFIX_TEXT,''))


def _continuity_request(result,review_source):
    review=_read(review_source); assessment=_read(review['assessment'])
    if review['assessment_id']!=assessment['assessment_id']: raise ValueError('continuity assessment differs')
    binding=assessment['binding']; clips=binding['clips']
    if not clips: return None
    run=Path(result['run_dir']) if result.get('run_dir') else Path(review['assessment']['path']).parents[4]
    video_source=result.get('video_observation_template')
    if video_source is None:
        # Native chains use a complete scene playback template, not a window's
        # static screening template. Imported legacy clips keep their origin.
        chain=run/'production/scene-clips/chains'/binding['scene_id']/'observation-template.json'
        leaf=next((c for c in clips if c['clip_id']==assessment['clip_id']),None)
        if leaf is None: return None
        video_source=chain if chain.is_file() else Path(leaf['clip_record']['path']).parent/'observation-template.json'
    if not isinstance(video_source,dict) and not Path(video_source).is_file(): return None
    video=_read(video_source)
    if video.get('scope') not in ('scene_clip_process','scene_temporal_chain_process'): return None
    if video.get('scene_id',video.get('binding',{}).get('scene_id'))!=binding['scene_id']: raise ValueError('continuity video scene differs')
    if video['scope']=='scene_clip_process' and video['clip_id']!=assessment['clip_id']: raise ValueError('continuity video clip differs')
    templates=[video]; authored=[_authored(video)]
    prefix=None
    if len(clips)>=3 and video['scope']!='scene_temporal_chain_process':
        prefix=dict(schema_version=1,run_id=review['run_id'],assessment_id=review['assessment_id'],assessment=deepcopy(review['assessment']),
            review_method=None,reviewer=None,viewed_at=None,
            playback=[{k:deepcopy(c[k]) for k in ('clip_id','source','source_frames','output_frames')} for c in clips],
            checks=dict.fromkeys(PREFIX_CHECKS,'unverified'),verdict='unverified',issues=[],**dict.fromkeys(PREFIX_TEXT,''))
        templates.append(prefix);authored.append(_prefix_authored(prefix))
    templates.append(review)
    authored.append(dict(responses=[dict(disposition='unverified',reason='',reference_indices=[]) for _ in review['responses']]))
    references=[]
    for ref in assessment.get('closure',[]):
        if ref not in references: references.append(deepcopy(ref))
    context=dict(assessment=assessment,reference_choices=references)
    identity=dict(kind='continuity_review',templates=templates,context=context)
    digest=hashlib.sha256(encode_submission(identity)).hexdigest()
    folder=run/'production/mail-workflow/submissions'/digest
    names=['video.json']+(['prefix.json'] if prefix else [])+['review.json']
    concerns=[{k:c[k] for k in ('detector_id','region_id','status','reasons') if k in c} for c in assessment.get('concerns',[])]
    explanation=['请完整连续播放当前片段及全部保留前缀，并逐项描述本人实际观察。',
        '将“确认”改为“提交”、“完整查看”改为 true；仅回复下方 JSON。响应按下列疑点顺序填写。',
        '疑点：'+json.dumps(concerns,ensure_ascii=False),
        'disposition 可填 not_observed_in_full_playback / explained_change / confirmed_issue / unverified。',
        'reference_indices 为引用下列原始证据的序号（从 0 开始）；无引用填 []。',
        '引用：'+json.dumps([dict(index=i,path=r['path']) for i,r in enumerate(references)],ensure_ascii=False)]
    return dict(kind='continuity_review',binding=digest,subject='视频制作确认：连续性回放与疑点',
        body_template='\n'.join(explanation)+'\n'+json.dumps(dict(确认='',完整查看=False,reviews=authored),ensure_ascii=False,indent=2),
        templates=templates,attachments=_attachments([video,assessment]),action='continuity_review',context=context,
        submission_paths=[str(folder/name) for name in names])


def _parse_prefix(template,authored,reviewer,viewed_at):
    _exact(authored,_prefix_authored(template),'prefix authored fields')
    _checks(authored['checks'],template['checks'])
    for key in PREFIX_TEXT: _text(authored[key])
    value=deepcopy(template);value.update(deepcopy(authored),review_method='human_video',reviewer=reviewer,viewed_at=viewed_at)
    _verdict(value)
    clips={c['clip_id']:c for c in template['playback']}
    for issue in value['issues']:
        _exact(issue,('check','clip_id','frames','description'),'prefix issue');_text(issue['description'])
        if issue['check'] not in value['checks'] or issue['clip_id'] not in clips: raise ValueError('prefix issue context differs')
        frames=issue['frames']; end=clips[issue['clip_id']]['source_frames'][1]
        if not isinstance(frames,list) or len(frames)!=2 or any(type(f) is not int for f in frames) or not 0<=frames[0]<frames[1]<=end: raise ValueError('invalid prefix issue frames')
    return value


def _parse_continuity(request,authored,reviewer,viewed_at):
    templates=request['templates']
    if len(authored)!=len(templates): raise ValueError('complete continuity review required')
    video=_observation(templates[0],authored[0],reviewer,viewed_at)
    values=[video]
    if len(templates)==3: values.append(_parse_prefix(templates[1],authored[1],reviewer,viewed_at))
    _exact(authored[-1],('responses',),'continuity authored fields')
    responses=authored[-1]['responses']; original=templates[-1]
    if not isinstance(responses,list) or len(responses)!=len(original['responses']): raise ValueError('every concern requires an explicit response')
    rehydrated=[]; references=request['context']['reference_choices']
    for row,source in zip(responses,original['responses']):
        _exact(row,('disposition','reason','reference_indices'),'concern response');_text(row['reason'])
        if row['disposition'] not in DISPOSITIONS: raise ValueError('invalid concern disposition')
        if row['disposition'] in ('explained_change','not_observed_in_full_playback') and any(v['verdict']!='passed' for v in values):
            raise ValueError('disposition requires explicitly passed full video and prefix playback')
        indices=row['reference_indices']
        if not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(references) for i in indices) or len(indices)!=len(set(indices)):
            raise ValueError('unknown reference index')
        if row['disposition']=='explained_change' and not indices: raise ValueError('explained change requires original context reference')
        rehydrated.append(dict(concern_id=source['concern_id'],disposition=row['disposition'],reason=row['reason'],references=[deepcopy(references[i]) for i in indices]))
    refs=[]
    for value,path in zip(values,request['submission_paths']):
        raw=encode_submission(value)
        refs.append(dict(path=path,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    review=deepcopy(original)
    review.update(video_observation=refs[0],prefix_observation=refs[-1],reviewer=reviewer,reviewed_at=viewed_at,responses=rehydrated)
    values.append(review)
    return values
