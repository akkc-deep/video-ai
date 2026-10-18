"""Independent full continuous source/new-video observations and review."""
from datetime import datetime
from pathlib import Path

from ..config import read_json
from ..planning.start_images import keys
from .manifest import hash_file,_timestamp
from .timeline_checks import _again
from ._upscale_inputs import fresh,same
from ._source_clip_review import ReviewIncomplete,text,continuity


def review(run,path,draft,draft_id):
    if not path.exists():raise ReviewIncomplete('independent continuous source/new video review missing')
    identity=hash_file(path);data=read_json(path)
    keys(data,'schema_version run_id draft_identity source_clips_identity review_method reviewer reviewed_at global_verdict reason entries','upscale semantic review')
    method=data['review_method']
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name or method not in ('human_video','agent_video'):raise ValueError('independent human_video or agent_video review required')
    text(data['reviewer']);text(data['reason']);_timestamp(data['reviewed_at']);reviewed=datetime.fromisoformat(data['reviewed_at'])
    if not datetime.fromisoformat(draft['created_at'])<=reviewed<=datetime.now().astimezone():raise ValueError('review outside draft/current time interval')
    ids=dict(review=identity,draft=fresh(data['draft_identity'],run=run,expected=run/'upscaled-clips-draft.json'),source_clips=fresh(data['source_clips_identity'],run=run,expected=run/'source-clips.json'))
    if (ids['draft'].sha256,ids['draft'].mtime_ns)!=(draft_id.sha256,draft_id.mtime_ns) or not same(data['source_clips_identity'],draft['source_clips_identity']):raise ValueError('review draft/source binding differs')
    if data['global_verdict'] not in ('passed','failed','unverified'):raise ValueError('valid independent global verdict required')
    if data['global_verdict']=='failed':raise ValueError('independent upscale video review failed')
    if data['global_verdict']=='unverified':raise ReviewIncomplete('independent upscale video review unverified')
    expected=draft['requirement_clips'];rows=data['entries']
    if not isinstance(rows,list):raise ValueError('ordered review entries required')
    if len(rows)<len(expected):raise ReviewIncomplete('full independent requirement review incomplete')
    if len(rows)!=len(expected):raise ValueError('duplicate/extra independent review entries')
    seen=set();notes={};unverified=False
    for row,wanted in zip(rows,expected):
        keys(row,' '.join(wanted)+' evidence_identity verdict reason','upscale review entry')
        if not same({k:row[k] for k in wanted},wanted):raise ValueError('upscale review requirement/range/source association differs')
        text(row['reason'])
        if row['verdict'] not in ('passed','failed','unverified'):raise ValueError('valid per-requirement verdict required')
        if row['verdict']=='failed':raise ValueError('independent upscale requirement failed')
        unverified|=row['verdict']=='unverified'
        note_id=fresh(row['evidence_identity'],run=run);note_path=Path(note_id.path)
        if note_path.parent!=run/'logs/upscale' or note_path==path or note_path.name.startswith(('media-','video-','extract-','encode-','frame-','clip-')):raise ValueError('direct observation must be isolated in logs/upscale')
        if note_path not in notes:
            note=read_json(note_path)
            keys(note,'schema_version run_id draft_identity review_method reviewer viewed_at entries','source/new continuous observation')
            if type(note['schema_version']) is not int or note['schema_version']!=1 or note['run_id']!=run.name or note['review_method']!=method or note['reviewer']!=data['reviewer']:raise ValueError('continuous observation reviewer/method/schema differs')
            fresh(note['draft_identity'],run=run,expected=run/'upscaled-clips-draft.json')
            if not same(note['draft_identity'],data['draft_identity']):raise ValueError('continuous observation draft differs')
            _timestamp(note['viewed_at'])
            if not datetime.fromisoformat(draft['created_at'])<=datetime.fromisoformat(note['viewed_at'])<=reviewed:raise ValueError('continuous viewing outside draft/review interval')
            observations=note['entries']
            if not isinstance(observations,list) or not observations:raise ValueError('full continuous source/new observations required')
            signatures=set()
            for observation in observations:
                keys(observation,' '.join(wanted)+' source_playback_frames upscaled_playback_frames start_observation process_observation end_observation comparison_observation quality_observation','continuous comparison entry')
                binding={k:observation[k] for k in wanted};candidates=[r for r in expected if same(binding,r)]
                if len(candidates)!=1 or not same(observation['source_playback_frames'],candidates[0]['local_frames']) or not same(observation['upscaled_playback_frames'],candidates[0]['local_frames']):raise ValueError('both complete source/new playback intervals and exact identities required')
                signature=(observation['shot_id'],observation['requirement_index'])
                if signature in signatures:raise ValueError('duplicate continuous observation')
                signatures.add(signature);seen.add(signature)
                for key in ('start_observation','process_observation','end_observation','comparison_observation','quality_observation'):text(observation[key])
                continuity(observation)
            notes[note_path]=(note_id,signatures)
        if (wanted['shot_id'],wanted['requirement_index']) not in notes[note_path][1]:raise ValueError('requirement has no matched full continuous source/new observation')
        for key in ('actual_artifact','source_actual_artifact'):ids[key+'/'+str(len(ids))]=fresh(wanted[key],run=run)
    if len(seen)!=len(expected):raise ReviewIncomplete('full source/new observation coverage incomplete')
    if unverified:raise ReviewIncomplete('upscale action/quality comparison unverified')
    ids.update({str(path):item[0] for path,item in notes.items()});_again(ids);return ids,method
