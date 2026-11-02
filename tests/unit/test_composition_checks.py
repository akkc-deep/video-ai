from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import pytest
from composition_helpers import inputs
from video_ai.runtime.manifest import thaw,hash_file,create_manifest

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');return path

@pytest.fixture
def fixture(runtime_run,monkeypatch,request):
    from image_helpers import write_png
    from unit.test_composition_audio import wav
    from video_ai.config import load_config
    from video_ai.runtime import _composition_inputs as ci
    run,original,paths=runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    raw=thaw(original.raw);raw['voice_config']=str(original.voice.config_file)
    raw['workflows']={k:str(v) for k,v in original.workflows.items()}
    raw['tools']={k:str(actual.tools[k]) if k in ('ffmpeg','ffprobe') else str(v) for k,v in original.tools.items()}
    raw['media']['font_file']=str(actual.media.font_file)
    options=getattr(request,'param',{})
    if options.get('fade'):
        raw['media']['transition']='fade';raw['media']['transition_seconds']=3/16
    if options.get('music'):
        wav(run/'fixture-music.wav',[1000]*10000)
        raw['media']['music']=str(run/'fixture-music.wav')
    raw['media']['timeline']={k:0 for k in ('sentence_pause_seconds','paragraph_pause_seconds','opening_seconds','closing_seconds')}
    config=load_config(write(run/'fixture-config.json',raw))
    store=create_manifest(run,config,inputs={'config':hash_file(config.config_file),'voice':hash_file(config.voice.config_file)},models={},workflows={})
    t,s,u,timing=inputs(transition='fade' if options.get('fade') else 'cut',seconds=3/16 if options.get('fade') else 0);clips=[]
    for c in t.clips:
        p=run/'audio'/c.unit_id/'pcm-48000.wav';p.parent.mkdir(parents=True);wav(p,[1000]*48000)
        ident=hash_file(p);clips.append(replace(c,pcm=replace(c.pcm,path=p,bytes=ident.bytes,sha256=ident.sha256)))
    t=replace(t,clips=tuple(clips));s.update(run_id=run.name,timing_review_identity=thaw(hash_file(write(run/'logs/storyboard/timing-review.json',{'fixture':'TEST ONLY'}))),timing_basis=dict(method='human_audio',human_boundary_reviewed=True,boundary_basis='TEST ONLY',actual_video_sync='unverified'))
    for clip,mapping in zip(u['clips'],u['frame_mappings']):
        target=write(run/'shots'/clip['shot_id']/'upscaled.mp4',{'fixture':'TEST ONLY replaced upstream consumer'})
        ident=thaw(hash_file(target));clip['upscaled_identity']=mapping['upscaled_identity']=ident
        for frame in clip['frames']:
            path=target.parent/'upscaled-frames'/f'frame_{frame["frame_index"]:06d}.png';path.parent.mkdir(exist_ok=True)
            write_png(path,1920,1080,(frame['frame_index']*10,50,80));frame['upscaled_frame_identity']=thaw(hash_file(path))
        for row in u['requirement_clips']:
            if row['clip_shot_id']==clip['shot_id']:row['actual_artifact']=ident
    u.update(run_id=run.name,source_validation={'video_text_semantics_passed':False},source_review_method='user_acceptance')
    for name,data in [('upscaled-clips.json',u),('storyboard.json',s),('timeline.json',t.as_dict()),('voice-listening.json',{'accepted':True}),('script.txt',{'TEST ONLY':True})]:write(run/name,data)
    ids={k:hash_file(p) for k,p in [('config',config.config_file),('voice',config.voice.config_file),('voice_listening',run/'voice-listening.json'),('script_copy',run/'script.txt')]}
    ids.update({'pcm/'+c.unit_id:hash_file(c.pcm.path) for c in t.clips})
    monkeypatch.setattr(ci,'load_committed_upscaled_clips',lambda r:json.loads((r/'upscaled-clips.json').read_text(encoding='utf-8')))
    monkeypatch.setattr(ci,'load_committed_storyboard',lambda r:json.loads((r/'storyboard.json').read_text(encoding='utf-8')))
    monkeypatch.setattr(ci,'_verified_inputs',lambda c,r,snapshot:(t,ids.copy()))
    monkeypatch.setattr(ci,'load_timing_review',lambda r,p,t:timing)
    for stage in ('speech','timeline','storyboard','start_images','source_clips','upscale'):
        store.record_stage(stage,'running');store.record_stage(stage,'completed')
    return run,config,store

def module():
    from video_ai.runtime import composition_checks
    return composition_checks


def test_identity_comparison_validates_schema_and_nested_timestamp(fixture):
    from video_ai.runtime._composition_inputs import equal_identity
    from video_ai.runtime._composition_evidence import _same_sources
    run,config,store=fixture;identity=thaw(hash_file(config.config_file))
    bad=dict(identity,extra=True)
    with pytest.raises(ValueError):equal_identity(bad,identity)
    bad=dict(identity,verified_at='invalid')
    with pytest.raises(ValueError):_same_sources({'nested':bad},{'nested':identity})

def test_complete_staging_candidate_is_consumable_and_does_not_publish(fixture):
    run,config,store=fixture;before=store.snapshot()
    result=module().compose_clips(config,run_dir=run)
    assert result.passed and result.staging_only and result.total_frames==48
    report=module().load_committed_composition(run)
    assert report['validation']['actual_final_video_sync']=='unverified'
    assert report['validation']['full_film_acceptance']=='unverified'
    assert report['provenance']['source_review_method']=='user_acceptance'
    after=store.snapshot()
    assert all(before['stages'][k]==after['stages'][k] for k in before['stages'] if k!='composition')
    assert before['units']==after['units']
    assert after['stages']['composition']['status']=='completed'
    with pytest.raises(module().CompositionRefusal):module().compose_clips(config,run_dir=run)


def test_unlimited_composition_receipts_are_readable_outside_production_scope(fixture,monkeypatch):
    from dataclasses import replace
    from datetime import datetime,timedelta
    from video_ai.runtime.execution_limits import production_execution
    from video_ai.media import composition_video
    original=composition_video.run_logged
    def slow_command(*a,**k):
        result=original(*a,**k)
        return replace(result,started_at=(datetime.fromisoformat(result.started_at)-timedelta(seconds=600)).isoformat())
    monkeypatch.setattr(composition_video,'run_logged',slow_command)
    run,config,_=fixture
    result=production_execution(module().compose_clips)(config,run_dir=run)
    assert result.passed
    execution=json.loads((run/'logs/composition/execution.json').read_text(encoding='utf-8'))
    assert all(r['timeout_seconds'] is None and r.get('time_limits')=='unlimited_v1' for r in execution['commands'])
    assert module().load_committed_composition(run)['passed']

@pytest.mark.parametrize('orphan',['.composition.lock','composition.json','staging/composition'])
def test_orphan_and_foreign_lock_refuse_without_commands(fixture,orphan):
    run,config,store=fixture;path=run/orphan;path.parent.mkdir(parents=True,exist_ok=True)
    if orphan=='staging/composition':path.mkdir()
    else:path.write_bytes(b'foreign')
    before=(run/'manifest.json').read_bytes()
    with pytest.raises(module().CompositionRefusal):module().compose_clips(config,run_dir=run)
    assert (run/'manifest.json').read_bytes()==before
    assert path.exists()
    assert not (run/'logs/composition').exists()

def test_error_after_start_preserves_failed_evidence(fixture,monkeypatch):
    run,config,store=fixture
    monkeypatch.setattr(module(),'materialize_frames',lambda *a,**kw:(_ for _ in ()).throw(OSError('TEST ONLY storage failure')))
    result=module().compose_clips(config,run_dir=run)
    assert not result.passed and store.snapshot()['stages']['composition']['status']=='failed'
    assert (run/'staging/composition').is_dir() and not (run/'.composition.lock').exists()
    assert list((run/'logs/composition').glob('diagnostic-*.json'))

@pytest.mark.parametrize('field',['frame_mappings','requirement_bindings','cue_checks','evidence','srt'])
def test_consumer_rejects_tampering_even_with_new_report_receipt(fixture,field):
    run,config,store=fixture;assert module().compose_clips(config,run_dir=run).passed
    report=json.loads((run/'composition.json').read_text(encoding='utf-8'))
    if field=='frame_mappings':report[field][0]['contributors'][0]['native_frame_index']=1
    elif field=='requirement_bindings':report[field].reverse()
    elif field=='cue_checks':report[field][0]['verdict']='failed'
    elif field=='evidence':report['request_evidence'].pop(next(iter(report['request_evidence'])))
    else:(run/'staging/composition/subtitle.srt').write_text('changed',encoding='utf-8')
    write(run/'composition.json',report)
    def refresh(data):
        from video_ai.runtime.timeline_checks import _artifact
        ident=hash_file(run/'composition.json');data['workflows']['composition_report']=thaw(ident);data['stages']['composition']['artifacts']=[_artifact(ident)]
    # Simulate a forged/refreshed receipt by changing the fixture's raw bytes;
    # the public ManifestStore correctly refuses edits to terminal artifacts.
    forged=store.snapshot();refresh(forged);write(run/'manifest.json',forged)
    with pytest.raises((ValueError,OSError)):module().load_committed_composition(run)

def test_downstream_stage_progress_does_not_invalidate_candidate(fixture):
    run,config,store=fixture;assert module().compose_clips(config,run_dir=run).passed
    store.record_stage('validation','running')
    assert module().load_committed_composition(run)['passed']

def test_insufficient_capacity_has_no_stage_or_media_side_effect(fixture,monkeypatch):
    run,config,store=fixture
    from types import SimpleNamespace
    monkeypatch.setattr(module().capacity,'disk_usage',lambda p:SimpleNamespace(free=0))
    before=(run/'manifest.json').read_bytes()
    with pytest.raises(module().CompositionRefusal,match='capacity'):module().compose_clips(config,run_dir=run)
    assert (run/'manifest.json').read_bytes()==before and not (run/'staging/composition').exists()

def test_interrupted_stage_and_foreign_lock_are_preserved(fixture,monkeypatch):
    run,config,store=fixture
    def interrupt(*a,**kw):
        write(run/'.composition.lock',{'pid':1,'token':'foreign'})
        raise KeyboardInterrupt()
    monkeypatch.setattr(module(),'materialize_frames',interrupt)
    with pytest.raises(KeyboardInterrupt):module().compose_clips(config,run_dir=run)
    assert store.snapshot()['stages']['composition']['status']=='interrupted'
    assert json.loads((run/'.composition.lock').read_text())['token']=='foreign'

def test_settings_duplicate_json_is_rejected_before_start(fixture):
    run,config,store=fixture;settings=run/'settings.json';settings.write_text('{"font_size":54,"font_size":60}',encoding='utf-8')
    with pytest.raises(module().CompositionRefusal):module().compose_clips(config,run_dir=run,settings_path=settings)
    assert store.snapshot()['stages']['composition']['status']=='pending'

def test_consumer_rejects_replaced_candidate_with_refreshed_all_candidate_receipts(fixture):
    from video_ai.media.composition_video import command,ffmpeg
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.timeline_checks import _artifact
    run,config,store=fixture;assert module().compose_clips(config,run_dir=run).passed
    folder=run/'staging/composition';candidate=folder/'candidate.mp4';forged=run/'fixture-forged.mp4'
    command([*ffmpeg(config),'-i',str(candidate),'-map','0','-c','copy','-metadata','title=forged replacement',str(forged)],config=config,paths=RuntimePaths.from_config(config),logger=RunLogger(run),cwd=folder,operation='TEST ONLY forge')
    candidate.write_bytes(forged.read_bytes());new=thaw(hash_file(candidate))
    report=json.loads((run/'composition.json').read_text(encoding='utf-8'));report['candidate_identity']=new;report['request_evidence']['staging/composition/candidate.mp4']=new;write(run/'composition.json',report)
    data=store.snapshot();identity=hash_file(run/'composition.json');data['workflows']['composition_report']=thaw(identity);data['stages']['composition']['artifacts']=[_artifact(identity)];write(run/'manifest.json',data)
    with pytest.raises((ValueError,OSError)):module().load_committed_composition(run)

@pytest.mark.parametrize('fixture',[{'fade':True},{'music':True}],indirect=True)
def test_derived_command_sources_cannot_be_forged_with_refreshed_receipts(fixture):
    from video_ai.runtime.timeline_checks import _artifact
    run,config,store=fixture;assert module().compose_clips(config,run_dir=run).passed
    report=json.loads((run/'composition.json').read_text(encoding='utf-8'))
    path=run/'logs/composition/execution.json';execution=json.loads(path.read_text(encoding='utf-8'))
    record=next(r for r in execution['commands'] if r['operation'] in ('blend','normalize_music'))
    record['args'][record['args'].index('-i')+1]=str(run/'wrong-source.png')
    write(Path(record['record_path']),{k:v for k,v in record.items() if k!='record_path'})
    report['request_evidence'][Path(record['record_path']).relative_to(run).as_posix()]=thaw(hash_file(Path(record['record_path'])))
    write(path,execution);report['request_evidence']['logs/composition/execution.json']=thaw(hash_file(path));write(run/'composition.json',report)
    data=store.snapshot();ident=hash_file(run/'composition.json');data['workflows']['composition_report']=thaw(ident);data['stages']['composition']['artifacts']=[_artifact(ident)];write(run/'manifest.json',data)
    with pytest.raises((ValueError,OSError)):module().load_committed_composition(run)
