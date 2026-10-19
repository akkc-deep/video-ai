"""Pure final-film evidence protocol. Templates never assert a viewing occurred."""
from copy import deepcopy
from datetime import datetime
import hashlib

from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest

CHECK_FIELDS = ('subject_identity appearance_structure color_clothing environment_space time_lighting '
                'style motion_process continuation_joins scene_cuts full_narration subtitle_text '
                'audio_video_sync final_quality').split()
IDENTITY_FIELDS = ('schema_version production_strategy run_id scope composition_sha256 candidate subtitle '
                   'scene_clips_sha256 upscale_sha256 image_acceptance_sha256 visual_bible_sha256 '
                   'selected_images comparison_images clip_acceptances').split()
FIELDS = IDENTITY_FIELDS + ('playback review_method reviewer viewed_at full_film_watched full_audio_listened '
                           'subtitle_checked overall_observation scene_observations join_observations '
                           'narration_observations checks verdict issues reason').split()
SCENE_TEXT = ('identity_observation appearance_observation environment_observation style_observation motion_observation').split()
NARRATION_TEXT = ('audio_observation subtitle_observation semantics_observation sync_observation').split()
STATES = ('passed', 'failed', 'unverified')


def _fields(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label+': expected exact fields')


def _equal(value, expected, label):
    if canonical_digest(value) != canonical_digest(expected):
        raise ValueError(label+' differs')


def _text(value, label):
    if not isinstance(value, str) or not value.strip(): raise ValueError(label+': nonempty text required')


def _time(value):
    if not isinstance(value, (str, datetime)): raise ValueError('timezone-aware time required')
    parsed = datetime.fromisoformat(value) if isinstance(value,str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError('timezone-aware time required')
    return parsed


def _interval(value, maximum):
    _fields(value, ('start','end'), 'interval')
    if any(type(value[k]) is not int for k in ('start','end')) or not 0 <= value['start'] < value['end'] <= maximum:
        raise ValueError('invalid half-open interval')


def build_scene_final_observation_template(frozen, units, timeline, candidate, scene_clips,
                                          upscaled, image_acceptance, clip_requests):
    """Build exact identities read-only, hashing original PCM without writes/services."""
    requests = list(clip_requests)
    clips = scene_clips['clips']
    if [r['clip_id'] for r in requests] != [c['clip_id'] for c in clips]:
        raise ValueError('ordered complete clip requests required')
    if type(timeline.total_frames) is not int or timeline.total_frames < 1:
        raise ValueError('positive total frames required')
    scenes=[]
    for scene in scene_clips['scenes']:
        scenes.append(dict(scene_id=scene['scene_id'],start_frame=scene['start_frame'],end_frame=scene['end_frame'],
            selected_image_sha256=scene['selected_image']['sha256'],baseline_bindings=deepcopy(scene['selected_image']['baseline_bindings']),
            **dict.fromkeys(SCENE_TEXT,'')))
    joins=[]
    for index in range(1,len(clips)):
        before,after=clips[index-1],clips[index]; parent=requests[index]['parent']
        boundary=after['budget']['start_frame']
        joins.append(dict(from_clip_id=before['clip_id'],to_clip_id=after['clip_id'],
            kind='continuation' if parent is not None and parent['clip_id']==before['clip_id'] else 'cut',
            boundary_frame=boundary,played_frames=dict(start=max(before['budget']['start_frame'],boundary-16),
                end=min(after['budget']['end_frame'],boundary+16)),observation='',verdict='unverified'))
    def pcm_digest(clip):
        with clip.pcm.path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
    narration=[dict(unit_id=clip.unit_id,text_start=clip.text_start,text_end=clip.text_end,text=clip.text,
        start_sample=clip.start_sample,end_sample=clip.end_sample,pcm_sha256=pcm_digest(clip),
        **dict.fromkeys(NARRATION_TEXT,'')) for clip in timeline.clips]
    _time(candidate['created_at'])
    return dict(schema_version=2,production_strategy=STRATEGY,run_id=frozen.options['run_id'],scope='scene_final_film',
        composition_sha256=canonical_digest(candidate),candidate=deepcopy(candidate['candidate']),subtitle=deepcopy(candidate['subtitle']),
        scene_clips_sha256=canonical_digest(scene_clips),upscale_sha256=canonical_digest(upscaled),
        image_acceptance_sha256=canonical_digest(image_acceptance),visual_bible_sha256=scene_clips['visual_bible_sha256'],
        selected_images=[dict(scene_id=s['scene_id'],selected_image=deepcopy(s['selected_image'])) for s in scene_clips['scenes']],
        comparison_images=[dict(clip_id=r['clip_id'],comparison_images=deepcopy(r['comparison_images'])) for r in requests],
        clip_acceptances=[{k:c[k] for k in ('clip_id','clip_sha256','observation_acceptance_sha256')} for c in clips],
        playback=dict(frame_ranges=[dict(start=0,end=timeline.total_frames)],sample_ranges=[dict(start=0,end=timeline.total_frames*3000)]),
        review_method=None,reviewer=None,viewed_at=None,full_film_watched=False,full_audio_listened=False,subtitle_checked=False,
        overall_observation='',scene_observations=scenes,join_observations=joins,narration_observations=narration,
        checks=dict.fromkeys(CHECK_FIELDS,'unverified'),verdict='unverified',issues=[],reason='')


def validate_scene_final_observation(value, expected, *, now):
    """Validate authored evidence and return a deep copy; never infer a pass.

    ``expected`` has exact fields ``template/created_at``, with the latter from
    the freshly admitted candidate commit. All media admission belongs to the
    caller; this function is pure and checks the complete protocol identities.
    """
    try:
        _fields(expected,('template','created_at'),'expected context'); template=expected['template']
        _fields(template,FIELDS,'template'); _fields(value,FIELDS,'observation')
        for key in IDENTITY_FIELDS: _equal(value[key],template[key],key)
        _fields(value['playback'],('frame_ranges','sample_ranges'),'playback')
        _equal(value['playback'],template['playback'],'complete continuous playback')
        end=template['playback']['frame_ranges'][0]['end']
        _interval(value['playback']['frame_ranges'][0],end)
        _interval(value['playback']['sample_ranges'][0],end*3000)
        if value['review_method'] not in ('human_video','agent_video'): raise ValueError('actual video review required')
        _text(value['reviewer'],'reviewer')
        if not isinstance(value['viewed_at'],str) or not _time(expected['created_at']) <= _time(value['viewed_at']) <= _time(now):
            raise ValueError('viewing time outside candidate review period')
        for key in ('overall_observation','reason'): _text(value[key],key)
        flags=[value[key] for key in ('full_film_watched','full_audio_listened','subtitle_checked')]
        if any(type(flag) is not bool for flag in flags): raise ValueError('full playback flags must be bool')
        for group,texts,mutable in (('scene_observations',SCENE_TEXT,()),
                                   ('join_observations',['observation'],('verdict',)),
                                   ('narration_observations',NARRATION_TEXT,())):
            rows=value[group]; originals=template[group]
            if not isinstance(rows,list) or len(rows)!=len(originals): raise ValueError('complete '+group+' required')
            for row,original in zip(rows,originals):
                _fields(row,original,group)
                for key in original:
                    if key in texts: _text(row[key],key)
                    elif key not in mutable: _equal(row[key],original[key],group+' '+key)
                if group=='join_observations' and row['verdict'] not in STATES: raise ValueError('invalid join verdict')
        _fields(value['checks'],CHECK_FIELDS,'checks')
        if any(state not in STATES for state in value['checks'].values()): raise ValueError('invalid check state')
        if not isinstance(value['issues'],list): raise ValueError('issues must be array')
        for issue in value['issues']:
            _fields(issue,('check','frames','description'),'issue')
            if issue['check'] not in CHECK_FIELDS: raise ValueError('invalid issue check')
            _interval(issue['frames'],end); _text(issue['description'],'issue description')
        for join in value['join_observations']:
            key='continuation_joins' if join['kind']=='continuation' else 'scene_cuts'
            if join['verdict']=='failed' and value['checks'][key]!='failed': raise ValueError('failed join concealed by global check')
        checks=list(value['checks'].values()); joins=[j['verdict'] for j in value['join_observations']]
        verdict=value['verdict']
        valid=((verdict=='passed' and all(flags) and all(s=='passed' for s in checks+joins) and not value['issues'])
            or (verdict=='failed' and 'failed' in checks and bool(value['issues']))
            or (verdict=='unverified' and 'failed' not in checks+joins and ('unverified' in checks+joins or not all(flags))))
        if not valid: raise ValueError('verdict contradicts checks, joins, issues or full playback')
        return deepcopy(value)
    except (KeyError,TypeError,IndexError,OverflowError) as exc:
        raise ValueError('malformed final-film observation') from exc
