from copy import deepcopy

import pytest

from video_ai.runtime.manifest import now
from video_ai.runtime.production_state import ArtifactStamp, validate_report, validate_checkpoint


def stamp(run, name):
    path = run / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'actual fixture')
    return ArtifactStamp.read(path).to_dict()


def command(run):
    return dict(args=['D:/VideoSi/tools/ffmpeg.exe', '-n'], cwd=str(run), returncode=0,
                timed_out=False, stdout_path=str(run/'stdout'), stderr_path=str(run/'stderr'),
                started_at=now(), finished_at=now())


def report(run, payload):
    return dict(schema_version=1, execution_mode='automatic', run_id=run.name, stage='composition',
                created_at=now(), status='completed', input_records={}, payload=payload)


def payload(run):
    return dict(candidate=stamp(run, 'candidate.mp4'), subtitle=stamp(run, 'subtitle.srt'), frames=2,
                samples=6000, subtitle_events=[], encoding=command(run), probe=dict(streams=[
                    dict(codec_type='video', codec_name='h264', width=1920, height=1080,
                         pix_fmt='yuv420p', r_frame_rate='16/1', avg_frame_rate='16/1',
                         nb_read_frames='2', duration='0.125', start_time='0.000000'),
                    dict(codec_type='audio', codec_name='aac', sample_rate='48000', channels=1,
                         duration='0.125', start_time='0.000000')], format=dict(duration='0.125')))


@pytest.mark.parametrize('change', ['candidate_unknown', 'frames_bool', 'samples_short', 'encoding_unknown',
    'returncode_bool', 'timeout', 'cwd_escape', 'probe_short', 'probe_width_bool', 'probe_missing_audio',
    'probe_duration', 'probe_unknown', 'nan'])
def test_composition_report_rejects_nested_drift(runtime_run, change):
    run, _, _ = runtime_run
    p = payload(run)
    validate_report(report(run, p), run, 'composition')
    if change == 'candidate_unknown': p['candidate']['sha256'] = 'fake'
    elif change == 'frames_bool': p['frames'] = True
    elif change == 'samples_short': p['samples'] -= 1
    elif change == 'encoding_unknown': p['encoding']['unknown'] = 1
    elif change == 'returncode_bool': p['encoding']['returncode'] = False
    elif change == 'timeout': p['encoding']['timed_out'] = True
    elif change == 'cwd_escape': p['encoding']['cwd'] = str(run.parent)
    elif change == 'probe_short': p['probe']['streams'][0]['nb_read_frames'] = '1'
    elif change == 'probe_width_bool': p['probe']['streams'][0]['width'] = True
    elif change == 'probe_missing_audio': p['probe']['streams'].pop()
    elif change == 'probe_duration': p['probe']['streams'][1]['duration'] = '0.226'
    elif change == 'probe_unknown': p['probe']['streams'][0]['unknown'] = 1
    else: p['probe']['streams'][0]['duration'] = float('nan')
    with pytest.raises(ValueError): validate_report(report(run, p), run, 'composition')


def test_composition_report_preserves_standard_ffprobe_mime_codec_metadata(runtime_run):
    run,_,_=runtime_run;p=payload(run)
    p['probe']['streams'][0]['mime_codec_string']='avc1.640028'
    p['probe']['streams'][1]['mime_codec_string']='mp4a.40.2'
    original=deepcopy(p)
    validate_report(report(run,p),run,'composition')
    assert p==original
    p['probe']['streams'][0]['unknown_vendor_field']='unexpected'
    with pytest.raises(ValueError):validate_report(report(run,p),run,'composition')


def materialized(run):
    pcm = stamp(run, 'original.wav')
    input_frame = stamp(run, 'upscaled/frame_000001.png')
    output_frame = stamp(run, 'sequence/frame_000001.png')
    return dict(frames=1, samples=3000, sequence=str(run/'sequence'),
        narration=dict(stamp=stamp(run,'narration.wav'), samples=3000, speech_samples=2000,
            silence_samples=990, padding_samples=10,
            clips=[dict(unit_id='speech_0001', start_sample=0, end_sample=2000, samples=2000, pcm=pcm)]),
        subtitle=stamp(run,'subtitle.srt'), ass=stamp(run,'subtitles.ass'), font=stamp(run,'font.ttf'),
        subtitle_events=[], contributions=[dict(output_frame_index=0,shot_id='shot_0001',
            source_frame_index=0,upscaled_frame_index=0,input=input_frame,output=output_frame)])


def checkpoint(run, uid, p, outputs=None, request=None):
    return dict(schema_version=1,execution_mode='automatic',run_id=run.name,stage='composition',unit_id=uid,
                created_at=now(),status='completed',request=request,outputs=outputs or {},payload=p)


@pytest.mark.parametrize('change',['unknown','index_bool','reorder','narration_unknown','speech_sum','padding','pcm_unknown','sequence_escape'])
def test_materialized_rejects_nested_drift(runtime_run,change):
    from video_ai.runtime.production_composition_records import validate_composition_checkpoint
    run,_,_=runtime_run;p=materialized(run)
    validate_composition_checkpoint('materialized',p,run)
    if change=='unknown':p['contributions'][0]['unknown']=1
    elif change=='index_bool':p['contributions'][0]['source_frame_index']=False
    elif change=='reorder':p['contributions'][0]['output_frame_index']=2
    elif change=='narration_unknown':p['narration']['unknown']=1
    elif change=='speech_sum':p['narration']['speech_samples']+=1
    elif change=='padding':p['narration']['padding_samples']=3000
    elif change=='pcm_unknown':p['narration']['clips'][0]['pcm']['unknown']=1
    else:p['sequence']=str(run.parent)
    with pytest.raises(ValueError):validate_composition_checkpoint('materialized',p,run)


def test_encoded_requires_registered_candidate_and_no_request(runtime_run):
    run,_,_=runtime_run
    candidate=stamp(run,'candidate.mp4')
    cp=stamp(run,'logs/production/checkpoints/composition/materialized.json')
    p=dict(candidate=candidate,encoding=command(run),materialized_checkpoint=cp)
    with pytest.raises(ValueError):validate_checkpoint(checkpoint(run,'encoded',p),run,'composition','encoded')


def test_final_checkpoint_requires_actual_probe_and_prior_checkpoints(runtime_run):
    run,_,_=runtime_run;p=payload(run)
    cp=checkpoint(run,'final',p,outputs=dict(candidate=p['candidate'],subtitle=p['subtitle']))
    with pytest.raises(ValueError,match='checkpoint|probe'):validate_checkpoint(cp,run,'composition','final')


def test_encoded_checkpoint_rejects_replacement_materialized_record(runtime_run):
    run,_,_=runtime_run
    candidate=stamp(run,'candidate.mp4'); materialized=stamp(run,'logs/production/checkpoints/composition/materialized.json')
    cmd=command(run)
    stdout=stamp(run,'stdout');stderr=stamp(run,'stderr')
    cp=checkpoint(run,'encoded',dict(candidate=candidate,encoding=cmd,materialized_checkpoint=materialized),
        outputs=dict(candidate=candidate,materialized_checkpoint=materialized,stdout=stdout,stderr=stderr))
    with pytest.raises(ValueError):validate_checkpoint(cp,run,'composition','encoded')


def test_technical_checks_requires_completed_report_and_all_five_passed(runtime_run):
    from video_ai.runtime.production_composition_records import validate_technical_checks
    run,_,_=runtime_run
    p=payload(run); path=run/'production/composition.json';path.parent.mkdir(parents=True,exist_ok=True)
    from video_ai.runtime.production_state import write_exclusive
    write_exclusive(path,report(run,p))
    checks=dict.fromkeys(('source_text_coverage','audio_samples','frame_mapping','subtitles','final_media'),'passed')
    record=dict(schema_version=1,execution_mode='automatic',run_id=run.name,created_at=now(),
        composition_report=ArtifactStamp.read(path).to_dict(),technical_checks=checks,human_review='unverified')
    validate_technical_checks(record,run)
    for key,value in [('human_review','passed'),('schema_version',True),('unknown',1)]:
        bad=deepcopy(record);bad[key]=value
        with pytest.raises(ValueError):validate_technical_checks(bad,run)
    record['technical_checks']['final_media']='unverified'
    with pytest.raises(ValueError):validate_technical_checks(record,run)
