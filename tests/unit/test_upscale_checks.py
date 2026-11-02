import json
from pathlib import Path
import pytest
from upscale_helpers import setup,review,write


@pytest.mark.parametrize('orphan',['lock','draft','formal','checkpoint','frames','upscaled','mp4','input','output','unit'])
def test_pending_entry_rejects_orphans_without_post(runtime_run,monkeypatch,orphan):
    f=setup(runtime_run,monkeypatch)
    files={'lock':'.upscale.lock','draft':'upscaled-clips-draft.json','formal':'upscaled-clips.json',
        'checkpoint':'logs/upscale/frame-orphan.json','frames':'shots/shot_0001/frames/orphan.png',
        'upscaled':'shots/shot_0001/upscaled-frames/orphan.png','mp4':'shots/shot_0001/upscaled.mp4',
        'input':f'comfy/input/{f.run.name}/upscale/orphan.png','output':f'comfy/output/{f.run.name}/upscale/orphan.png'}
    if orphan=='unit':f.store.record_unit('frame','shot_0001:frame_000001','running')
    else:write(f.run/files[orphan],{'fixture':'TEST ONLY orphan'})
    with pytest.raises(f.uc.UpscaleRefusal):f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert not f.requests and not f.actions and f.store.snapshot()['stages']['upscale']['status']=='pending'


def test_capacity_formula_and_insufficient_space_causes_zero_posts(runtime_run,monkeypatch):
    from types import SimpleNamespace
    f=setup(runtime_run,monkeypatch)
    assert f.ui.required_capacity(f.source)==2*(2*768*432*3+2*1920*1080*3+3*65536)+2*1024**3
    monkeypatch.setattr(f.ui.shutil,'disk_usage',lambda p:SimpleNamespace(free=0))
    with pytest.raises(f.uc.UpscaleRefusal):f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert not f.requests and not f.actions


def test_review_commit_fresh_consumer_and_downstream_progress(runtime_run,monkeypatch):
    f=setup(runtime_run,monkeypatch);before=f.store.snapshot();draft=f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert draft.status=='review_required'
    path,_=review(f.run);result=f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path)
    assert result.passed and result.ready_for_composition and result.status=='completed'
    report=f.uc.load_committed_upscaled_clips(f.run)
    assert all(report['validation'][k] is True for k in ('frame_mapping_passed','upscale_quality_passed','ready_for_composition'))
    assert report['source_validation']==f.source['validation'] and report['source_validation']['motion_semantics_passed'] is False
    assert f.store.snapshot()['units']['shot']==before['units']['shot']
    f.store.record_stage('composition','running');assert f.uc.load_committed_upscaled_clips(f.run)==report


@pytest.mark.parametrize('fault',['missing','unverified','failed','user_acceptance','comparison','process','range','draft'])
def test_review_is_independent_continuous_source_comparison(runtime_run,monkeypatch,fault):
    from video_ai.runtime.manifest import hash_file,thaw
    f=setup(runtime_run,monkeypatch);assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run).status=='review_required'
    path,data=review(f.run)
    if fault=='missing':path.unlink()
    elif fault in ('unverified','failed'):data['global_verdict']=fault;write(path,data)
    elif fault=='user_acceptance':data['review_method']='user_acceptance';write(path,data)
    elif fault=='draft':data['draft_identity']['sha256']='0'*64;write(path,data)
    else:
        note=Path(data['entries'][0]['evidence_identity']['path']);raw=json.loads(note.read_text(encoding='utf-8'))
        if fault=='range':raw['entries'][0]['source_playback_frames']['end']=1
        else:raw['entries'][0][fault+'_observation']=''
        write(note,raw);data['entries'][0]['evidence_identity']=thaw(hash_file(note));write(path,data)
    result=f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path)
    assert not result.passed and not result.clips_path.exists()
    assert result.status==('review_required' if fault in ('missing','unverified') else 'failed')


@pytest.mark.parametrize('fault',['output','checkpoint','source','review','probe','graph','http','mapping','clip_checkpoint'])
def test_consumer_rejects_drift_and_refreshed_receipts_cannot_hide_lies(runtime_run,monkeypatch,fault):
    from video_ai.runtime.manifest import hash_file,thaw
    f=setup(runtime_run,monkeypatch);f.uc.prepare_upscaled_clips(f.config,run_dir=f.run);path,_=review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
    report=json.loads((f.run/'upscaled-clips.json').read_text(encoding='utf-8'));frame=report['clips'][0]['frames'][0]
    if fault=='source':target=Path(frame['source_identity']['path'])
    elif fault=='output':target=Path(frame['upscaled_frame_identity']['path'])
    elif fault=='checkpoint':target=Path(frame['checkpoint_identity']['path'])
    elif fault=='review':target=path
    elif fault=='clip_checkpoint':target=f.run/'logs/upscale/clip-shot_0001.json'
    elif fault=='probe':target=next(f.run/n for n in report['request_evidence'] if n.startswith('logs/upscale/media-'))
    elif fault=='http':target=next(f.run/n for n in report['request_evidence'] if n.endswith('.request.json') and json.loads((f.run/n).read_text())['method']=='POST')
    elif fault=='graph':target=Path(frame['submission']['intent_identity']['path'])
    else:target=f.config.workflows['upscale'].with_suffix('.mapping.json')
    if fault=='mapping':
        # Do not mutate the shared actual template mapping in a unit fixture.
        monkeypatch.setattr(f.ui,'template',lambda c, *, revision=None:(_ for _ in ()).throw(ValueError('TEST ONLY mapping drift')))
    elif fault in ('probe','http','graph'):
        raw=json.loads(target.read_text(encoding='utf-8'))
        if fault=='probe':raw['probe']['streams'][0]['width']=12
        elif fault=='http':raw['json_body']['prompt']['4']['inputs']['image']=['1',0]
        else:raw['4']['inputs']['image']=['1',0]
        write(target,raw)
        # Refresh all identity receipts through both draft and formal plus checkpoints.
        from video_ai.runtime import _upscale_inputs as ui
        def replace(value):
            if isinstance(value,dict):
                if set(value)==set(thaw(hash_file(target))) and value.get('path')==str(target):return thaw(hash_file(target))
                return {k:replace(v) for k,v in value.items()}
            if isinstance(value,list):return [replace(v) for v in value]
            return value
        for p in [f.run/'upscaled-clips-draft.json',f.run/'upscaled-clips.json']:
            write(p,replace(json.loads(p.read_text(encoding='utf-8'))))
        f.store.update(lambda d:d['workflows'].__setitem__('upscale_report',thaw(hash_file(f.run/'upscaled-clips.json'))))
    else:target.write_bytes(target.read_bytes()+b'TEST ONLY drift')
    with pytest.raises((ValueError,OSError,KeyError)):f.uc.load_committed_upscaled_clips(f.run)


def test_current_full_requirement_and_419_frame_coverage_is_preserved():
    from video_ai.runtime._upscale_evidence import requirements
    from video_ai.planning.source_clips import requirement_clips
    from unit.test_upscale import source_input
    from unit.test_source_clips import inputs,identity
    for fps,transition in ((16,'cut'),(24,'fade')):
        source=source_input(fps,transition);board,timeline,_=inputs(fps,transition)
        source['requirement_clips']=requirement_clips(board,source_identities={c['shot_id']:c['source_identity'] for c in source['clips']},
            frame_mappings={m['shot_id']:m for m in source['frame_mappings']},total_samples=timeline['total_samples'])
        assert len(source['requirement_clips'])==13
        if fps==16:assert sum(c['source_frames'] for c in source['clips'])==419
        targets=[dict(shot_id=c['shot_id'],upscaled_identity=identity(c['shot_id']+'/upscaled.mp4')) for c in source['clips']]
        result=requirements(source,targets)
        for row,wanted in zip(result,source['requirement_clips']):
            assert row['source_actual_artifact']==wanted['actual_artifact']
            assert {k:row[k] for k in wanted if k!='actual_artifact'}=={k:v for k,v in wanted.items() if k!='actual_artifact'}


@pytest.mark.parametrize('fault',['global_bool','extra','entry_extra','time','duplicate','static','continuity_missing','continuity_wrong','continuity_failed','continuity_unverified','continuity_duplicate','continuity_bare'])
def test_exact_review_schemas_and_primary_continuity_labels(runtime_run,monkeypatch,fault):
    from video_ai.runtime.manifest import hash_file,thaw,now
    from video_ai.runtime._upscale_review import review as consume,ReviewIncomplete
    from video_ai.runtime._source_clip_review import continuity
    from copy import deepcopy
    f=setup(runtime_run,monkeypatch)
    if fault.startswith('continuity_'):
        observation=dict(clip_shot_id='shot_0004',role='primary',quality_observation='[continuity:shot_0003->shot_0004:passed] TEST ONLY comparison details')
        if fault=='continuity_missing':observation['quality_observation']='TEST ONLY no label'
        elif fault=='continuity_wrong':observation['quality_observation']=observation['quality_observation'].replace('shot_0003','shot_0005')
        elif fault=='continuity_failed':observation['quality_observation']=observation['quality_observation'].replace(':passed]',':failed]')
        elif fault=='continuity_unverified':observation['quality_observation']=observation['quality_observation'].replace(':passed]',':unverified]')
        elif fault=='continuity_duplicate':observation['quality_observation']*=2
        else:observation['quality_observation']='[continuity:shot_0003->shot_0004:passed]'
        with pytest.raises((ValueError,ReviewIncomplete)):continuity(observation)
        return
    assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run).status=='review_required'
    path,data=review(f.run);draft=json.loads((f.run/'upscaled-clips-draft.json').read_text(encoding='utf-8'))
    if fault=='global_bool':data['schema_version']=True
    elif fault=='extra':data['unknown']='TEST ONLY'
    elif fault=='entry_extra':data['entries'][0]['unknown']='TEST ONLY'
    elif fault=='time':data['reviewed_at']='2999-01-01T00:00:00+08:00'
    elif fault=='duplicate':data['entries'].append(deepcopy(data['entries'][0]))
    else:
        note=Path(data['entries'][0]['evidence_identity']['path']);raw=json.loads(note.read_text(encoding='utf-8'))
        raw['entries'][0].pop('process_observation');write(note,raw);data['entries'][0]['evidence_identity']=thaw(hash_file(note))
    write(path,data)
    with pytest.raises((ValueError,ReviewIncomplete)):consume(f.run,path,draft,hash_file(f.run/'upscaled-clips-draft.json'))


def test_committed_state_survives_error_after_durable_manifest_write(runtime_run,monkeypatch):
    from video_ai.runtime.manifest import ManifestStore
    f=setup(runtime_run,monkeypatch);f.uc.prepare_upscaled_clips(f.config,run_dir=f.run);path,_=review(f.run)
    base=ManifestStore._write
    def written(self,data):
        base(self,data)
        if data['stages']['upscale']['status']=='completed':raise OSError('TEST ONLY diagnostic failure after durable completed')
    monkeypatch.setattr(ManifestStore,'_write',written)
    result=f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path)
    assert result.passed and f.store.snapshot()['stages']['upscale']['status']=='completed'
    assert f.uc.load_committed_upscaled_clips(f.run)['passed'] is True


@pytest.mark.parametrize('fault',['acceptance','inventory','model','config','template'])
def test_actual_fixed_file_and_task4_provenance_refusals_are_zero_post(runtime_run,monkeypatch,fault):
    f=setup(runtime_run,monkeypatch)
    if fault=='acceptance':
        data=json.loads(f.ui.TASK4_ACCEPTANCE.read_text(encoding='utf-8'));data['components']['upscale']['passed']=False;write(f.ui.TASK4_ACCEPTANCE,data)
    elif fault=='inventory':(f.run/'fixture-inventory.json').write_bytes(b'TEST ONLY changed inventory')
    elif fault=='model':f.config.models['upscale'].write_bytes(b'TEST ONLY changed model')
    elif fault=='config':f.config.config_file.write_bytes(b'TEST ONLY changed config')
    else:
        base=f.ui.WorkflowTemplate.load
        def changed(*args):
            t=base(*args);t.graph['4']['inputs']['image']=['1',0];return t
        monkeypatch.setattr(f.ui.WorkflowTemplate,'load',changed)
    with pytest.raises(f.uc.UpscaleRefusal):f.uc.prepare_upscaled_clips(f.config,run_dir=f.run)
    assert not f.requests and not f.actions


@pytest.mark.parametrize('fault',['png_probe','raw_png','graph','http_graph','http_body','http_time','http_time_small','frame_time','frame_time_small','extract','encode','encode_stderr','pts'])
def test_resealed_receipts_reach_and_reject_technical_lies(runtime_run,monkeypatch,fault):
    from video_ai.runtime._upscale_evidence import validate
    from upscale_helpers import reseal_technical
    # Build a historical finite receipt, whose saved policy retains its bounds.
    f=setup(runtime_run,monkeypatch);result=f.uc.prepare_upscaled_clips.__wrapped__(f.config,run_dir=f.run)
    assert result.status=='review_required'
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'));frame=draft['clips'][0]['frames'][0]
    if fault in ('frame_time','frame_time_small'):
        # A durable completed checkpoint cannot be completed outside its bounded frame interval.
        pass
    elif fault in ('graph','http_graph','http_body','http_time','http_time_small'):
        if fault=='graph':target=Path(frame['submission']['intent_identity']['path'])
        else:
            target=next(f.run/name for name in frame['evidence_identities'] if name.endswith('.request.json') and json.loads((f.run/name).read_text())['method']=='POST')
        if fault in ('http_time','http_time_small'):
            from datetime import datetime,timedelta
            request_record=json.loads(target.read_text());target=target.with_name(target.name.replace('.request.json','.response.json'));data=json.loads(target.read_text())
            data['finished_at']=(datetime.fromisoformat(request_record['started_at'])+timedelta(seconds=request_record['timeout']+.005 if fault=='http_time_small' else 181)).isoformat()
        elif fault=='http_body':target=target.with_name(target.name.replace('.request.json','.body'));data=json.loads(target.read_text());data['prompt_id']='00000000-0000-0000-0000-000000000000'
        else:
            data=json.loads(target.read_text());g=data if fault=='graph' else data['json_body']['prompt'];g['4']['inputs']['image']=['1',0]
        write(target,data)
    elif fault in ('png_probe','raw_png'):
        target=next(f.run/name for name in frame['evidence_identities'] if name.startswith('logs/upscale/media-'))
        data=json.loads(target.read_text(encoding='utf-8'))
        if fault=='png_probe':data['probe']['streams'][0]['width']=128;write(target,data)
        else:
            target=Path(data['commands'][0]['stdout_path']);data=json.loads(target.read_text());data['streams'][0]['width']=128;write(target,data)
    else:
        prefix={'extract':'extract-','encode':'encode-','encode_stderr':'encode-','pts':'video-'}[fault]
        target=next(f.run/name for name in draft['request_evidence'] if name.startswith('logs/upscale/'+prefix))
        data=json.loads(target.read_text(encoding='utf-8'))
        if fault=='extract':data['command']['args'][data['command']['args'].index('format=rgb24')]='scale=768:432'
        elif fault=='encode':data['command']['args'][-1:-1]=['-frames:v','2']
        elif fault=='encode_stderr':Path(data['command']['stderr_path']).write_bytes(b'TEST ONLY FFmpeg error contradicting success')
        else:data['frames']['frames'][1]['pts_time']='0.500000'
        write(target,data)
    draft,snapshot=reseal_technical(f,draft)
    if fault in ('frame_time','frame_time_small'):
        from datetime import datetime,timedelta
        unit=snapshot['units']['frame']['shot_0001:frame_000001']
        unit['finished_at']=(datetime.fromtimestamp(frame['input_copy_identity']['mtime_ns']/1e9).astimezone()+timedelta(seconds=f.config.timeouts['upscale_frame']+.005 if fault=='frame_time_small' else 181)).isoformat()
    # The fully resealed evidence map is fresh; failure must come from its meaning.
    context=f.ui.inputs(f.config,f.run)
    expected={'png_probe':'raw PNG probe','raw_png':'raw PNG stdout','graph':'actual full frame graph',
        'http_graph':'actual frame POST graph','http_body':'actual HTTP prompt acceptance',
        'extract':'source media command arguments','encode':'source media command arguments','encode_stderr':'frame media command.*errors','pts':'PTS|CFR|timestamp',
        'http_time':'absolute.*deadline|HTTP.*budget','frame_time':'absolute.*deadline',
        'http_time_small':'absolute.*deadline|HTTP.*budget','frame_time_small':'absolute.*deadline'}[fault]
    with pytest.raises(ValueError,match=expected):validate(f.config,f.run,draft,context,snapshot)


@pytest.mark.parametrize('fault',[
    'png_probe_stderr','video_probe_stderr','video_pts_stderr',
    'output_probe_deadline','output_decode_deadline','output_probe_after_checkpoint','output_decode_after_unit',
    'extract_deadline','extract_command_cap','encode_deadline','video_probe_deadline','video_pts_deadline','video_decode_deadline',
    'extracted_png_deadline','encoded_png_deadline','png_before_clip'])
def test_resealed_raw_media_errors_and_total_deadlines(runtime_run,monkeypatch,fault):
    """TEST ONLY resealing must reach semantic errors, not freshness failures."""
    from datetime import datetime,timedelta
    from video_ai.runtime._upscale_evidence import validate
    from upscale_helpers import reseal_technical
    f=setup(runtime_run,monkeypatch);result=f.uc.prepare_upscaled_clips.__wrapped__(f.config,run_dir=f.run)
    assert result.status=='review_required'
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'));clip=draft['clips'][0];frame=clip['frames'][0]
    prefix='video-' if fault.startswith('video_') else 'extract-' if fault.startswith('extract_') else 'encode-' if fault.startswith('encode_') else 'media-'
    candidates=[f.run/name for name in draft['request_evidence'] if name.startswith('logs/upscale/'+prefix) and name.endswith('.json')]
    if prefix=='media-':
        identity=frame['input_identity'] if fault=='extracted_png_deadline' else frame['upscaled_frame_identity'] if fault=='encoded_png_deadline' else frame['output_identity']
        candidates=[path for path in candidates if json.loads(path.read_text(encoding='utf-8'))['info']['identity']['path']==identity['path']]
    assert len(candidates)==1
    path=candidates[0];record=json.loads(path.read_text(encoding='utf-8'))
    command_index=1 if fault in ('video_pts_stderr','video_pts_deadline','output_decode_deadline','output_decode_after_unit') else 2 if fault=='video_decode_deadline' else 0
    selected=record['command'] if prefix in ('extract-','encode-') else record['commands'][command_index]
    if fault.endswith('_stderr'):
        Path(selected['stderr_path']).write_bytes(b'TEST ONLY ffprobe error contradicting success')
    else:
        extract=next(f.run/name for name in draft['request_evidence'] if name.startswith('logs/upscale/extract-') and name.endswith('.json'))
        start=datetime.fromisoformat(json.loads(extract.read_text())['command']['started_at'])
        frame_start=datetime.fromtimestamp(frame['input_copy_identity']['mtime_ns']/1e9).astimezone()
        if fault.startswith('output_'):
            if fault=='output_probe_after_checkpoint':end=datetime.fromtimestamp(frame['checkpoint_identity']['mtime_ns']/1e9).astimezone()+timedelta(seconds=.01)
            elif fault=='output_decode_after_unit':end=datetime.fromisoformat(f.store.snapshot()['units']['frame']['shot_0001:frame_000001']['finished_at'])+timedelta(seconds=.01)
            else:end=frame_start+timedelta(seconds=f.config.timeouts['upscale_frame']+1)
            selected['finished_at']=end.isoformat()
        elif fault=='png_before_clip':
            selected['started_at']=(start-timedelta(seconds=1)).isoformat()
        elif fault=='extract_command_cap':selected['finished_at']=(start+timedelta(seconds=301)).isoformat()
        else:selected['finished_at']=(start+timedelta(seconds=f.config.timeouts['upscale_clip']+1)).isoformat()
        write(path,record)
    draft,snapshot=reseal_technical(f,draft)
    if fault=='output_probe_after_checkpoint':
        # Resealing rewrites the durable checkpoint; place the command after that
        # refreshed checkpoint while keeping unit completion within its budget.
        from video_ai.runtime.manifest import hash_file,thaw
        checkpoint_time=datetime.fromtimestamp(draft['clips'][0]['frames'][0]['checkpoint_identity']['mtime_ns']/1e9).astimezone()
        record=json.loads(path.read_text(encoding='utf-8'))
        record['commands'][0]['finished_at']=(checkpoint_time+timedelta(seconds=.01)).isoformat()
        write(path,record);draft['request_evidence'][path.relative_to(f.run).as_posix()]=thaw(hash_file(path))
        snapshot['units']['frame']['shot_0001:frame_000001']['finished_at']=(checkpoint_time+timedelta(seconds=.02)).isoformat()
    context=f.ui.inputs(f.config,f.run)
    with pytest.raises(ValueError,match='stderr|absolute.*deadline|durable.*completion'):
        validate(f.config,f.run,draft,context,snapshot)


def test_later_encoding_png_reinspection_uses_clip_deadline(runtime_run,monkeypatch):
    """TEST ONLY encoded copies may be reinspected after the original frame budget."""
    from datetime import datetime,timedelta
    from video_ai.runtime._upscale_evidence import validate
    from upscale_helpers import reseal_technical
    f=setup(runtime_run,monkeypatch);result=f.uc.prepare_upscaled_clips.__wrapped__(f.config,run_dir=f.run)
    assert result.status=='review_required'
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'));frame=draft['clips'][0]['frames'][0]
    target=next(f.run/name for name in draft['request_evidence'] if name.startswith('logs/upscale/media-') and json.loads((f.run/name).read_text())['info']['identity']['path']==frame['upscaled_frame_identity']['path'])
    record=json.loads(target.read_text(encoding='utf-8'))
    start=datetime.fromtimestamp(frame['input_copy_identity']['mtime_ns']/1e9).astimezone()+timedelta(seconds=f.config.timeouts['upscale_frame']+1)
    for index,command in enumerate(record['commands']):
        command['started_at']=(start+timedelta(seconds=index)).isoformat()
        command['finished_at']=(start+timedelta(seconds=index+.1)).isoformat()
    write(target,record);draft,snapshot=reseal_technical(f,draft)
    assert validate(f.config,f.run,draft,f.ui.inputs(f.config,f.run),snapshot)
