"""Fresh complete upstream composition admission; never mutate inputs."""
from pathlib import Path
import shutil

from ..config import read_json
from ..planning.composition import CompositionSettings,plan_composition
from .manifest import ManifestStore,hash_file,thaw,_identity
from .paths import RuntimePaths,_validate_spelling
from .timeline_checks import _local,_again
from .storyboard_checks import load_committed_storyboard,load_timing_review,_verified_inputs
from .upscale_checks import load_committed_upscaled_clips
from ._source_clip_inputs import same,fresh


def equal_identity(a,b):
    for value in (a,b):
        if value is not None:
            _identity(value)
            if any(v is None for v in value.values()):raise ValueError('complete composition identity required')
    if a is None or b is None:return a is b
    return all(a[k]==b[k] for k in ('path','bytes','mtime_ns','sha256'))


def read_settings(path):
    if path is None:return CompositionSettings(),None
    path=Path(_validate_spelling(path)).absolute()
    if path.resolve(strict=True)!=path:raise ValueError('settings path redirected/noncanonical')
    identity=hash_file(path)
    settings=CompositionSettings.from_dict(read_json(path))
    _again({'settings':identity})
    return settings,identity


def inputs(config,run,settings_path=None):
    snapshot=ManifestStore.open(run).snapshot()
    resolved=thaw(config);resolved.pop('voice');resolved.pop('raw')
    frozen=snapshot['config_snapshot']
    if config.config_file!=Path(frozen['path']) or not same(config.raw,frozen['raw']) or not same(resolved,frozen['resolved']):raise ValueError('composition config differs from frozen snapshot')
    if not config.media.burn_subtitles:raise ValueError('composition requires burned original subtitles')
    upscaled=load_committed_upscaled_clips(run)
    storyboard=load_committed_storyboard(run)
    timeline,ids=_verified_inputs(config,run,snapshot)
    from .pipeline_import import origin_run,fresh_origin_review
    timing_run=origin_run(run,storyboard)
    timing_path=Path(fresh_origin_review(run,storyboard,storyboard['timing_review_identity']).path)
    if timing_run!=run:
        from .timeline_checks import load_committed_timeline
        timing_timeline=load_committed_timeline(timing_run)
    else:timing_timeline=timeline
    timing=load_timing_review(timing_run,timing_path,timing_timeline)
    settings,settings_id=read_settings(settings_path)
    listening=thaw(ids.get('voice_listening')) or read_json(run/'timeline.json')['provenance']['voice_listening']
    if listening is None:raise ValueError('accepted voice listening provenance required')
    listening_path=Path(fresh(listening).path)
    for name,path in [('upscaled_clips',run/'upscaled-clips.json'),('storyboard',run/'storyboard.json'),('timeline',run/'timeline.json'),('timing_review',timing_path),('voice_listening',listening_path),('font',config.media.font_file),('ffmpeg',config.tools['ffmpeg']),('ffprobe',config.tools['ffprobe'])]:
        ids[name]=hash_file(_local(run,path) if path.is_relative_to(run) else path)
    if settings_id:ids['settings']=settings_id
    if config.media.music:ids['music']=hash_file(config.media.music)
    from .pipeline_import import import_source_identities
    ids.update({'import/'+path:identity for path,identity in import_source_identities(run).items()})
    plan=plan_composition(timeline,storyboard,upscaled,timing,settings=settings)
    provenance={k+'_identity':thaw(ids[k]) if k in ids else None for k in ('upscaled_clips','timeline','storyboard','timing_review','voice_listening','font','music','ffmpeg','ffprobe')}
    provenance.update(source_validation=upscaled['source_validation'],source_review_method=upscaled['source_review_method'],timing_basis=storyboard['timing_basis'])
    _again(ids)
    return dict(timeline=timeline,storyboard=storyboard,upscaled=upscaled,timing=timing,settings=settings,settings_identity=settings_id,identities=ids,plan=plan,provenance=provenance,paths=RuntimePaths.from_config(config))


def required_capacity(plan):
    return plan.video_samples*8+plan.total_frames*1920*1080*4*2+2*1024**3


def upstream_unchanged(current,previous):
    for key in ('config_snapshot','voice_snapshot','inputs','models','units','services','resources'):
        if not same(current[key],previous[key]):raise OSError('composition upstream changed: '+key)
    for name in ('preflight','speech','timeline','storyboard','start_images','source_clips','upscale'):
        if not same(current['stages'][name],previous['stages'][name]):raise OSError('composition upstream stage changed: '+name)
    from .pipeline_evidence import media_workflows
    current_workflows,previous_workflows=media_workflows(current,previous)
    old={k:v for k,v in previous_workflows.items() if k!='composition_report'}
    new={k:v for k,v in current_workflows.items() if k not in ('composition_report',) and k in old}
    if not same(old,new):raise OSError('composition upstream workflows changed')
