"""Pure exact final-video review and human acceptance gates.

These gates validate authored evidence contracts, never infer observed semantics.
Filesystem freshness and strict JSON reading belong to the publication adapter.
"""
from collections.abc import Mapping
from datetime import datetime
import math
from pathlib import Path, PurePosixPath

from .source_clips import _complete_identity
from ..runtime.manifest import thaw

IDENTITY_FIELDS = set('path bytes mtime_ns sha256 verified_at'.split())
VERDICTS = tuple(k+'_verdict' for k in ('text_semantics','video_semantics','motion','sync','quality','continuity'))
BOUND_IDENTITIES = ('candidate_validation_identity','composition_identity','candidate_identity','subtitle_identity','script_identity','timeline_identity')
REVIEW_FIELDS = 'schema_version run_id candidate_validation_identity composition_identity candidate_identity subtitle_identity script_identity timeline_identity review_method reviewer reviewed_at global_verdict reason entries cue_entries'
OBSERVATION_FIELDS = 'schema_version run_id candidate_validation_identity candidate_identity review_method reviewer viewed_at entries'
CUE_OBSERVATION_FIELDS = 'schema_version run_id candidate_validation_identity reviewer review_method viewed_at entries'
CUE_FIELDS = 'cue_id requirement_id kind from_unit_id to_unit_id pcm_identity timeline_identity candidate_identity audio_sample audio_uncertainty_samples actual_change_frames evidence_identity verdict reason'
ACCEPTANCE_FIELDS = 'schema_version run_id candidate_validation_identity composition_identity candidate_identity subtitle_identity script_identity timeline_identity final_review_identity review_collection_identities review_method reviewer reviewed_at full_film_watched full_audio_listened subtitle_checked verdict reason'
OBSERVATION_TEXT = 'start_observation process_observation end_observation audio_text_observation quality_observation continuity_observation'.split()


def _keys(value, fields, label):
    fields = set(fields.split()) if isinstance(fields,str) else set(fields)
    if type(value) is not dict or set(value) != fields:
        raise ValueError(label+': missing/unknown fields')


def _text(value, label):
    if type(value) is not str or not value.strip(): raise ValueError(label+': nonempty actual observation required')


def _int(value, label, minimum=0):
    if type(value) is not int or value < minimum: raise ValueError(label+': integer required')
    return value


def _time(value):
    if isinstance(value,datetime): parsed=value
    elif type(value) is str:
        try: parsed=datetime.fromisoformat(value)
        except ValueError as exc: raise ValueError('invalid timestamp') from exc
    else: raise ValueError('timezone-aware timestamp required')
    if parsed.tzinfo is None: raise ValueError('timezone-aware timestamp required')
    return parsed


def _tree(value, now):
    if isinstance(value,Mapping):
        if any(type(k) is not str for k in value): raise ValueError('string object keys required')
        if set(value) == IDENTITY_FIELDS:
            _complete_identity(value)
            if _time(value['verified_at']) > now: raise ValueError('future identity timestamp')
        for item in value.values(): _tree(item,now)
    elif isinstance(value,(list,tuple)):
        for item in value: _tree(item,now)
    elif type(value) is float and not math.isfinite(value): raise ValueError('nonfinite evidence value')
    elif value is not None and type(value) not in (str,int,float,bool): raise ValueError('invalid evidence value')


def _same(a,b):
    if isinstance(a,Mapping) and isinstance(b,Mapping):
        if set(a) != set(b): return False
        keys = set(a)-{'verified_at'} if set(a)==IDENTITY_FIELDS else set(a)
        return all(_same(a[k],b[k]) for k in keys)
    if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):
        return len(a)==len(b) and all(_same(x,y) for x,y in zip(a,b))
    return type(a) is type(b) and a==b


def _equal(a,b,label):
    if not _same(a,b): raise ValueError(label+': association/identity differs')


def _bindings(candidate):
    return dict(candidate_validation_identity=candidate['candidate_validation_identity'],
        composition_identity=candidate['composition_identity'],candidate_identity=candidate['candidate_identity'],
        subtitle_identity=candidate['subtitle_identity'],script_identity=candidate['input_identities']['script_copy'],
        timeline_identity=candidate['input_identities']['timeline'])


def _header(data,candidate,now,*,earliest,time_key):
    if type(data['schema_version']) is not int or data['schema_version']!=1: raise ValueError('schema1 required')
    _equal(data['run_id'],candidate['run_id'],'run')
    _text(data['reviewer'],'reviewer')
    when=_time(data[time_key])
    if not earliest <= when <= now: raise ValueError('review/view time outside candidate/current interval')
    for key,want in _bindings(candidate).items():
        if key in data: _equal(data[key],want,key)
    return when


def _ranges(rows,total,label):
    if type(rows) is not list or not rows: raise ValueError(label+': complete nonempty ranges required')
    previous=0
    for row in rows:
        _keys(row,'start end',label)
        a,b=(_int(row[k],label+' '+k) for k in ('start','end'))
        if not previous <= a < b <= total: raise ValueError(label+': overlapping/outside range')
        previous=b
    return rows


def _signature(row):
    _int(row['requirement_index'],'requirement_index')
    for key in ('shot_id','clip_shot_id','role'): _text(row[key],key)
    return tuple(row[k] for k in ('shot_id','requirement_index','clip_shot_id','role'))


def _base(row,candidate,fps,frames):
    result=dict(row)
    result['upscaled_artifact']=result.pop('actual_artifact')
    result['actual_artifact']=candidate['candidate_identity']
    ranges=_ranges(row['candidate_frame_ranges'],frames,'candidate frames')
    result['candidate_sample_ranges']=[dict(start=r['start']*(48000//fps),end=r['end']*(48000//fps)) for r in ranges]
    return result


def _evidence_name(identity,candidate):
    _complete_identity(identity)
    run=Path(candidate['candidate_validation_identity']['path']).parent
    path=Path(identity['path'])
    if not path.is_relative_to(run/'logs'/'validation') or path.suffix != '.json':
        raise ValueError('observation must be independent run logs/validation JSON')
    return path.relative_to(run).as_posix()


def _index_names(index):
    if type(index) is not dict: raise ValueError('canonical evidence index required')
    aliases=set()
    for name in index:
        if type(name) is not str or '\\' in name or ':' in name or not name.startswith('logs/validation/') or not name.endswith('.json') or PurePosixPath(name).as_posix()!=name or any(x in ('','.', '..') for x in name.split('/')) or name.casefold() in aliases:
            raise ValueError('noncanonical/aliased evidence name')
        aliases.add(name.casefold())


def _passed(value,label):
    if value != 'passed': raise ValueError(label+': failed/unverified/missing final check')


def _observation_documents(index,candidate,review,now,*,cue=False):
    _index_names(index)
    documents={}
    for name,doc in index.items():
        _keys(doc,CUE_OBSERVATION_FIELDS if cue else OBSERVATION_FIELDS,'cue observation' if cue else 'continuous observation')
        _header(doc,candidate,now,earliest=_time(candidate['created_at']),time_key='viewed_at')
        if _time(doc['viewed_at']) > _time(review['reviewed_at']): raise ValueError('observation after review')
        _equal(doc['reviewer'],review['reviewer'],'observation reviewer')
        method=review['review_method'].replace('_video','_audio_video') if cue else review['review_method']
        _equal(doc['review_method'],method,'continuous observation method')
        if type(doc['entries']) is not list or not doc['entries']: raise ValueError('complete observation entries required')
        signatures={}
        for entry in doc['entries']:
            sign=entry['cue_id'] if cue else _signature(entry)
            if sign in signatures: raise ValueError('duplicate observation signature')
            signatures[sign]=entry
        documents[name]=signatures
    return documents


def _cues(review,candidate,timeline,fps,frames,documents):
    rows=review['cue_entries']; expected=candidate['cue_checks']
    if type(rows) is not list or len(rows)<len(expected): raise ValueError('missing boundary cues')
    clips={clip['unit_id']:clip for clip in timeline['clips']}
    requirements=candidate['requirement_bindings']
    req_order={};req_units={}
    for i,row in enumerate(requirements):
        req_order.setdefault(row['requirement_id'],i)
        req_units[row['requirement_id']]=row['unit_id']
    seen=set();actions={};used=set();last_action=(-1,-1)
    for i,row in enumerate(rows):
        _keys(row,CUE_FIELDS,'cue')
        _text(row['cue_id'],'cue_id');_text(row['reason'],'cue reason');_passed(row['verdict'],'cue '+row['cue_id'])
        if row['cue_id'] in seen: raise ValueError('duplicate cue ID')
        seen.add(row['cue_id'])
        if i<len(expected):
            source=expected[i]
            if row['kind']!='boundary' or row['requirement_id'] is not None: raise ValueError('boundary order/kind differs')
            for key in ('cue_id','from_unit_id','to_unit_id'): _equal(row[key],source[key],'boundary '+key)
        else:
            req=row['requirement_id']
            if row['kind']!='action' or req not in req_order or row['from_unit_id']!=req_units[req] or row['to_unit_id']!=req_units[req]:
                raise ValueError('action requirement/unit association differs')
            order=(req_order[req],_int(row['audio_sample'],'action audio sample'))
            if order<last_action: raise ValueError('action cues not in requirement/sample order')
            last_action=order;actions.setdefault(req,[]).append(row['cue_id'])
        clip=clips[row['to_unit_id']]
        _equal(row['pcm_identity'],candidate['input_identities']['pcm/'+row['to_unit_id']],'cue PCM')
        _equal(row['timeline_identity'],candidate['input_identities']['timeline'],'cue timeline')
        _equal(row['candidate_identity'],candidate['candidate_identity'],'cue candidate')
        sample=_int(row['audio_sample'],'audio_sample');uncertainty=_int(row['audio_uncertainty_samples'],'audio uncertainty')
        if not clip['start_sample'] <= sample-uncertainty <= sample+uncertainty < clip['end_sample']:
            raise ValueError('cue sample/uncertainty outside original PCM interval')
        interval=row['actual_change_frames'];_ranges([interval],frames,'actual change frames')
        start,end=interval['start'],interval['end']
        if max(abs(f*48000-sample*fps) for f in (start,end-1))+uncertainty*fps>48000:
            raise ValueError('cue conservative uncertainty exceeds one frame')
        if i<len(expected):
            first=source['first_positive_contributor_frame'];last=source['last_positive_contributor_frame']
            # Cuts have first == last+1; fades overlap and require both visible extremes.
            if first<=last and not (start<=first<end and start<=last<end):
                raise ValueError('fade observation omits first/last positive-weight visibility')
        name=_evidence_name(row['evidence_identity'],candidate)
        if name not in documents or row['cue_id'] not in documents[name]: raise ValueError('missing actual audio/video cue observation')
        observation=documents[name][row['cue_id']]
        base={k:v for k,v in row.items() if k not in ('evidence_identity','verdict','reason')}
        _keys(observation,set(base)|{'audio_observation','video_observation','full_interval_played'},'cue observation entry')
        _equal({k:observation[k] for k in base},base,'cue observation binding')
        for key in ('audio_observation','video_observation'): _text(observation[key],key)
        if observation['full_interval_played'] is not True: raise ValueError('complete cue interval must be played')
        used.add((name,row['cue_id']))
    if used!={(name,key) for name,entries in documents.items() for key in entries}: raise ValueError('extra/unreferenced cue observation')
    return actions


def validate_final_review(review,candidate,timeline,*,observations,cue_observations,now_value=None):
    """Validate complete passed final observations; return final gate statuses."""
    try:
        now=_time(now_value) if now_value is not None else datetime.now().astimezone()
        timeline=thaw(timeline); _tree([review,candidate,timeline,observations,cue_observations],now)
        _keys(review,REVIEW_FIELDS,'final review')
        _header(review,candidate,now,earliest=_time(candidate['created_at']),time_key='reviewed_at')
        if review['review_method'] not in ('human_video','agent_video'): raise ValueError('actual continuous final-video method required')
        _text(review['reason'],'review reason');_passed(review['global_verdict'],'global verdict')
        fps=timeline['output_fps'];frames=timeline['total_frames']
        if type(fps) is not int or fps not in (16,24): raise ValueError('16/24fps required')
        _int(frames,'total_frames',1)
        _equal(candidate['effective_media']['fps'],fps,'candidate fps');_equal(candidate['effective_media']['frames'],frames,'candidate frames')
        docs=_observation_documents(observations,candidate,review,now)
        cue_docs=_observation_documents(cue_observations,candidate,review,now,cue=True)
        actions=_cues(review,candidate,timeline,fps,frames,cue_docs)
        expected=candidate['requirement_bindings'];entries=review['entries']
        if type(entries) is not list or len(entries)!=len(expected): raise ValueError('incomplete/extra requirement associations')
        used=set();signatures=set()
        for row,entry in zip(expected,entries):
            signature=_signature(row)
            if signature in signatures: raise ValueError('duplicate requirement association')
            signatures.add(signature);base=_base(row,candidate,fps,frames)
            _keys(entry,set(base)|set(VERDICTS)|{'evidence_identity','reason'},'final review entry')
            _equal({k:entry[k] for k in base},base,'ordered final requirement association')
            for key in VERDICTS: _passed(entry[key],str(signature)+' '+key)
            _text(entry['reason'],'entry reason')
            name=_evidence_name(entry['evidence_identity'],candidate)
            if name not in docs or signature not in docs[name]: raise ValueError('missing continuous actual final observation')
            observation=docs[name][signature]
            _keys(observation,set(base)|set(OBSERVATION_TEXT)|{'playback_frame_ranges','playback_sample_ranges','sync_observation'},'continuous observation entry')
            _equal({k:observation[k] for k in base},base,'continuous final association')
            _ranges(observation['playback_frame_ranges'],frames,'playback frames')
            _ranges(observation['playback_sample_ranges'],frames*(48000//fps),'playback samples')
            _equal(observation['playback_frame_ranges'],base['candidate_frame_ranges'],'complete playback frames')
            _equal(observation['playback_sample_ranges'],base['candidate_sample_ranges'],'complete playback samples')
            for key in OBSERVATION_TEXT: _text(observation[key],key)
            sync=observation['sync_observation']
            _keys(sync,'requires_action_cue action_cue_ids onset_observation interval_observation reason','sync observation')
            if type(sync['requires_action_cue']) is not bool or type(sync['action_cue_ids']) is not list:
                raise ValueError('explicit action necessity and IDs required')
            for key in ('onset_observation','interval_observation','reason'): _text(sync[key],key)
            ids=sync['action_cue_ids']
            if any(type(x) is not str or not x.strip() for x in ids) or len(set(ids))!=len(ids): raise ValueError('unique action cue IDs required')
            want=actions.get(row['requirement_id'],[])
            if sync['requires_action_cue']:
                if not want: raise ValueError('required internal action cue unverified')
                _equal(ids,want,'complete action cues')
            elif ids or want: raise ValueError('action necessity conflicts with supplied cues')
            used.add((name,signature))
        if used!={(name,key) for name,rows in docs.items() for key in rows}: raise ValueError('extra/unreferenced continuous observations')
        return dict(actual_final_video_semantics='passed',actual_final_video_sync='passed')
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('invalid final review structure or missing required evidence') from exc


def validate_acceptance(acceptance,candidate,review,collection,*,now_value=None):
    """Validate human full-film acceptance of the complete exact evidence set."""
    try:
        now=_time(now_value) if now_value is not None else datetime.now().astimezone()
        _tree([acceptance,candidate,review,collection],now)
        _keys(acceptance,ACCEPTANCE_FIELDS,'full-film acceptance')
        _header(review,candidate,now,earliest=_time(candidate['created_at']),time_key='reviewed_at')
        when=_header(acceptance,candidate,now,earliest=_time(review['reviewed_at']),time_key='reviewed_at')
        if acceptance['review_method']!='human_full_film': raise ValueError('human_full_film acceptance required')
        for key in ('full_film_watched','full_audio_listened','subtitle_checked'):
            if acceptance[key] is not True: raise ValueError(key+': human full viewing/listening/SRT checking required')
        _text(acceptance['reason'],'acceptance reason');_passed(acceptance['verdict'],'human acceptance')
        _index_names(collection);_index_names(acceptance['review_collection_identities'])
        final_name=_evidence_name(acceptance['final_review_identity'],candidate)
        refs={_evidence_name(row['evidence_identity'],candidate) for row in review['entries']+review['cue_entries']}
        if final_name in refs or set(collection)!=refs|{final_name}: raise ValueError('exact complete independent review collection required')
        _equal(acceptance['final_review_identity'],collection[final_name],'final review identity')
        if 'final_review_identity' in review:
            _equal(review['final_review_identity'],collection[final_name],'actual final review identity')
        _equal(acceptance['review_collection_identities'],collection,'acceptance review collection')
        for name,identity in collection.items():
            if _evidence_name(identity,candidate)!=name: raise ValueError('review collection identity/name differs')
        for row in review['entries']+review['cue_entries']:
            name=_evidence_name(row['evidence_identity'],candidate)
            _equal(row['evidence_identity'],collection[name],'accepted observation identity')
        # The caller validates observation times <= final review time. This gate
        # binds that exact review and requires acceptance at/after its timestamp.
        _passed(review['global_verdict'],'accepted global review')
        for row in review['entries']:
            for key in VERDICTS: _passed(row[key],'accepted '+key)
        for row in review['cue_entries']: _passed(row['verdict'],'accepted cue')
        return dict(full_film_acceptance='passed')
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('invalid full-film acceptance structure or missing collection') from exc
