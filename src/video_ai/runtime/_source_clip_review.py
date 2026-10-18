"""Exact continuous-video observation receipts; no still-image substitute."""
from datetime import datetime
from pathlib import Path
import re

from ..config import read_json
from ..planning.start_images import keys
from .manifest import hash_file,_timestamp
from .timeline_checks import _local,_again
from ._source_clip_inputs import fresh,same


class ReviewIncomplete(ValueError):
    """The draft stays running until every actual video requirement is reviewed."""


def text(value):
    if type(value) is not str or not value.strip():raise ValueError('actual continuous video observation text required')


def continuity(observation):
    """Require the ledgered comparison verdict on its own primary observation."""
    quality=observation['quality_observation']
    pairs={'shot_0004':('shot_0003','shot_0004'),'shot_0006':('shot_0005','shot_0006')}
    pair=pairs.get(observation['clip_shot_id']) if observation['role']=='primary' else None
    markers=re.findall(r'\[continuity:[^\]]*\]',quality)
    if pair is None:
        if '[continuity:' in quality:raise ValueError('continuity label is on the wrong/edge observation')
        return
    if '[continuity:' not in quality:raise ReviewIncomplete('explicit primary cross-shot comparison remains unverified')
    if len(markers)!=1 or quality.count('[continuity:')!=1 or not quality.startswith(markers[0]):
        raise ValueError('missing, misplaced, duplicated or contradictory continuity label')
    label=re.fullmatch(r'\[continuity:'+pair[0]+'->'+pair[1]+r':(passed|failed|unverified)\]',markers[0])
    if label is None:raise ValueError('continuity pair/verdict label differs from primary association')
    text(quality[len(markers[0]):])
    if label[1]=='failed':raise ValueError('required cross-shot continuous-video comparison failed')
    if label[1]=='unverified':raise ReviewIncomplete('required cross-shot continuous-video comparison unverified')


def review(run,path,draft,draft_id):
    if not path.exists():raise ReviewIncomplete('continuous video review is missing')
    identity=hash_file(path);data=read_json(path)
    method=data.get('review_method') if isinstance(data,dict) else None
    fields='schema_version run_id draft_identity images_identity storyboard_identity timeline_identity review_method reviewer reviewed_at entries'
    fields+=' accepted acceptance_text acceptance_scope unverified_checks' if method=='user_acceptance' else ' global_verdict reason'
    keys(data,fields,'source clip review')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name or method not in ('human_video','agent_video','user_acceptance'):
        raise ValueError('valid continuous video review or explicit user acceptance required')
    text(data['reviewer']);_timestamp(data['reviewed_at'])
    reviewed=datetime.fromisoformat(data['reviewed_at'])
    if not datetime.fromisoformat(draft['created_at'])<=reviewed<=datetime.now().astimezone():raise ValueError('review time outside draft/current interval')
    ids={'review':identity,'draft':fresh(data['draft_identity'],run=run,expected=run/'source-clips-draft.json')}
    if ids['draft'].sha256!=draft_id.sha256 or ids['draft'].mtime_ns!=draft_id.mtime_ns:raise ValueError('review draft identity differs')
    for key in ('images','storyboard','timeline'):
        ids[key]=fresh(data[key+'_identity'],run=run,expected=run/(key+'.json'))
        if not same(data[key+'_identity'],draft[key+'_identity']):raise ValueError('review upstream binding differs from draft')
    if method=='user_acceptance':
        text(data['acceptance_text'])
        if data['accepted'] is not True or data['acceptance_scope']!='source_clips_for_upscale':
            raise ValueError('literal accepted=true and source_clips_for_upscale scope required')
        if not same(data['unverified_checks'],['video_text_semantics','motion_semantics','quality','cross_shot_continuity']):
            raise ValueError('explicit ordered unverified semantic/quality/continuity checks required')
        if not same(data['entries'],draft['requirement_clips']):
            raise ValueError('user acceptance requires every exact ordered source/range association')
        for index,row in enumerate(data['entries']):
            ids[f'accepted_source/{index}']=fresh(row['actual_artifact'],run=run,expected=run/'shots'/row['clip_shot_id']/'source.mp4')
        _again(ids)
        return ids,method
    text(data['reason'])
    if data['global_verdict'] not in ('passed','failed','unverified'):raise ValueError('invalid global video verdict')
    if data['global_verdict']=='unverified':raise ReviewIncomplete('global continuous video review unverified')
    if data['global_verdict']=='failed':raise ValueError('global source video semantics failed')
    rows=data['entries'];expected=draft['requirement_clips']
    if not isinstance(rows,list):raise ValueError('video review entries must be list')
    if len(rows)<len(expected):raise ReviewIncomplete('all continuous video requirement entries required')
    if len(rows)!=len(expected):raise ValueError('video review duplicate/extra requirements')
    seen=set();notes={};unverified=False
    for index,(row,wanted) in enumerate(zip(rows,expected)):
        keys(row,' '.join(wanted)+' evidence_identity verdict reason','video review entry')
        if not same({k:row[k] for k in wanted},wanted):raise ValueError('review original requirement/source/full ranges differ')
        text(row['reason'])
        if row['verdict'] not in ('passed','failed','unverified'):raise ValueError('invalid per-requirement video verdict')
        if row['verdict']=='failed':raise ValueError('required continuous source action/quality failed')
        unverified|=row['verdict']=='unverified'
        note_id=fresh(row['evidence_identity'],run=run);note_path=Path(note_id.path)
        if note_path.parent!=run/'logs/source-clips' or note_path==path or note_path.name.startswith(('video-','trim-','clip-','input-')):
            raise ValueError('direct video observation must be isolated in logs/source-clips')
        note=read_json(note_path)
        keys(note,'schema_version run_id draft_identity review_method reviewer viewed_at entries','continuous video observation')
        if type(note['schema_version']) is not int or note['schema_version']!=1 or note['run_id']!=run.name or note['review_method']!=data['review_method'] or note['reviewer']!=data['reviewer']:
            raise ValueError('video observation schema/reviewer/method differs')
        fresh(note['draft_identity'],run=run,expected=run/'source-clips-draft.json')
        if not same(note['draft_identity'],data['draft_identity']):raise ValueError('observation draft differs from semantic review')
        _timestamp(note['viewed_at']);viewed=datetime.fromisoformat(note['viewed_at'])
        if not datetime.fromisoformat(draft['created_at'])<=viewed<=reviewed:raise ValueError('continuous observation outside draft/review interval')
        observations=note['entries']
        if not isinstance(observations,list) or not observations:raise ValueError('continuous video observations required')
        local_seen=set();matched=False
        for observation in observations:
            keys(observation,' '.join(wanted)+' playback_frames start_observation process_observation end_observation quality_observation','continuous observation entry')
            binding={k:observation[k] for k in wanted}
            candidates=[r for r in expected if same(binding,r)]
            if len(candidates)!=1 or not same(observation['playback_frames'],candidates[0]['local_frames']):raise ValueError('full continuous interval playback and exact source required')
            signature=(observation['shot_id'],observation['requirement_index'])
            if signature in local_seen:raise ValueError('duplicate direct video observation')
            local_seen.add(signature);seen.add(signature)
            for key in ('start_observation','process_observation','end_observation','quality_observation'):text(observation[key])
            continuity(observation)
            matched|=same(binding,wanted)
        if not matched:raise ValueError('requirement has no matched continuous direct observation')
        notes[str(note_path)]=note_id
    if len(seen)!=len(expected):raise ReviewIncomplete('direct video observations incomplete')
    if unverified:raise ReviewIncomplete('continuous action/quality remains unverified')
    ids.update(notes);_again(ids)
    return ids,method
