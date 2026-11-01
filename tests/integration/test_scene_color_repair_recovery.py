"""Real CPU transaction recovery; all authored playback claims are fixture_only."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from scene_continuity_helpers import artifact, save, snapshot
from test_scene_color_repair_flow import complete_setup, propose, module


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def folder_for(setup, request):
    return setup['run']/'production/scene-color-repair/candidates'/read(request)['candidate_id']


def revise(setup, request, predecessor):
    from video_ai.runtime.manifest import now
    value=read(request)
    value.update(candidate_id=str(uuid4()), revision_of=artifact(predecessor), requested_at=now(),
                 reason='fixture_only explicit revision; always restart the original raw source')
    return save(setup['run']/('fixture_only-revision-'+value['candidate_id']+'.json'),value)


def spy_render(monkeypatch):
    import video_ai.runtime._scene_color_repair_media as media
    original=media.render_media; calls=[]
    def render(store,relative,intent,fit,manifest,pairs,**kwargs):
        calls.append(dict(source=intent['binding']['source'], amplitude=fit['amplitude'],
            current_sha256=hashlib.sha256(b''.join(frame.tobytes() for frame in pairs['current'])).hexdigest()))
        return original(store,relative,intent,fit,manifest,pairs,**kwargs)
    monkeypatch.setattr(media,'render_media',render)
    return calls


@pytest.mark.parametrize('point,colored', [('intent',False),('engine',False),('pair-producer',False),
    ('pair-report',False),('fit',False),('intended-rgb',True),('master-encoded',True),
    ('playback-encoded',True),('media',True),('after-producer',True)])
def test_partial_attempt_retains_bytes_and_same_uuid_never_reencodes(runtime_run,monkeypatch,point,colored):
    setup,request=complete_setup(runtime_run,monkeypatch,colored=colored)
    original=snapshot(setup['run']/'production/scene-clips'); calls=spy_render(monkeypatch)
    runtime=module()
    def interrupt(boundary):
        if boundary==point:
            raise KeyboardInterrupt('fixture_only durable interruption: '+point)
    monkeypatch.setattr(runtime,'boundary',interrupt)
    first=propose(setup,request)
    assert first.status=='interrupted',first.error
    folder=folder_for(setup,request); retained=snapshot(folder)
    assert (folder/'intent.json').is_file()
    if colored and point!='intended-rgb':
        assert (folder/'master.mp4').is_file()
    if point=='intended-rgb':
        assert (folder/'intended.rgb').is_file() and not (folder/'master.mp4').exists()
    monkeypatch.setattr(runtime,'boundary',lambda point:None)
    second=propose(setup,request)
    assert second.status=='interrupted',second.error
    assert snapshot(folder)==retained
    assert len(calls)==int(colored),'same UUID must never restart an interrupted render'
    assert snapshot(setup['run']/'production/scene-clips')==original


def test_request_only_interruption_resumes_without_an_earlier_measurement(runtime_run,monkeypatch):
    setup,request=complete_setup(runtime_run,monkeypatch);runtime=module()
    import video_ai.media.continuity_analysis as analysis
    actual=analysis.analyze_continuity;calls=[]
    def measured(*args,**kwargs):calls.append(1);return actual(*args,**kwargs)
    monkeypatch.setattr(analysis,'analyze_continuity',measured)
    def stop(point):
        if point=='request':raise KeyboardInterrupt('fixture_only request bytes captured before any intent/measurement')
    monkeypatch.setattr(runtime,'boundary',stop)
    first=propose(setup,request);folder=folder_for(setup,request)
    assert first.status=='interrupted' and (folder/'request.json').read_bytes()==request.read_bytes()
    assert not (folder/'intent.json').exists() and calls==[]
    monkeypatch.setattr(runtime,'boundary',lambda point:None)
    second=propose(setup,request)
    assert second.status=='noop',second.error
    assert calls==[1]


def test_new_uuid_can_reference_unfinished_intent_then_terminal_and_fourth_attempt_is_blocked(runtime_run,monkeypatch):
    setup,request=complete_setup(runtime_run,monkeypatch);runtime=module(); calls=spy_render(monkeypatch)
    original=snapshot(setup['run']/'production/scene-clips')
    real_terminal=runtime._terminal
    def interrupted_terminal(*args,**kwargs):
        raise OSError('fixture_only terminal durable write interruption')
    def stop_intent(point):
        if point=='intent':
            raise KeyboardInterrupt('fixture_only interruption before engine archive')
    monkeypatch.setattr(runtime,'boundary',stop_intent)
    monkeypatch.setattr(runtime,'_terminal',interrupted_terminal)
    first=propose(setup,request);one=folder_for(setup,request)
    assert first.status=='interrupted' and (one/'intent.json').is_file()
    assert not (one/'terminal.json').exists()
    old=snapshot(one)
    monkeypatch.setattr(runtime,'boundary',lambda point:None)
    monkeypatch.setattr(runtime,'_terminal',real_terminal)
    second_request=revise(setup,request,one/'intent.json');second=propose(setup,second_request)
    assert second.status=='noop',second.error
    two=folder_for(setup,second_request)
    third_request=revise(setup,second_request,two/'terminal.json');third=propose(setup,third_request)
    assert third.status=='noop',third.error
    three=folder_for(setup,third_request)
    intents=[read(path/'intent.json') for path in (one,two,three)]
    assert len({row['candidate_id'] for row in intents})==3
    assert all(row['binding']['source']==intents[0]['binding']['source'] for row in intents)
    fourth_request=revise(setup,third_request,three/'terminal.json');fourth=propose(setup,fourth_request)
    assert fourth.status=='blocked' and 'three-attempt' in fourth.error['message']
    assert not (folder_for(setup,fourth_request)/'intent.json').exists()
    assert snapshot(one)==old and calls==[]
    assert snapshot(setup['run']/'production/scene-clips')==original


@pytest.mark.parametrize('point', ['after-report','terminal','review-template'])
def test_complete_output_interruption_finishes_without_second_render(runtime_run,monkeypatch,point):
    setup,request=complete_setup(runtime_run,monkeypatch,colored=True);runtime=module()
    calls=spy_render(monkeypatch)
    def interrupt(boundary):
        if boundary==point:
            raise KeyboardInterrupt('fixture_only interruption with complete measured output: '+point)
    monkeypatch.setattr(runtime,'boundary',interrupt)
    first=propose(setup,request)
    assert first.status=='interrupted',first.error
    folder=folder_for(setup,request); retained=snapshot(folder)
    assert (folder/'master.mp4').is_file() and (folder/'media.json').is_file()
    if point=='after-report':
        assert not (folder/'terminal.json').exists()
    if point=='terminal':
        assert (folder/'terminal.json').is_file() and not (folder/'review-template.json').exists()
    monkeypatch.setattr(runtime,'boundary',lambda point:None)
    second=propose(setup,request)
    assert second.status=='awaiting_review',second.error
    assert (folder/'review-template.json').is_file()
    current=snapshot(folder)
    assert all(current[name]==stamp for name,stamp in retained.items())
    assert len(calls)==1,'complete measured media must be verified and retained, never encoded again'


def test_terminal_revision_fits_original_raw_instead_of_previous_candidate(runtime_run,monkeypatch):
    setup,request=complete_setup(runtime_run,monkeypatch,colored=True);calls=spy_render(monkeypatch)
    original=snapshot(setup['run']/'production/scene-clips')
    first=propose(setup,request)
    assert first.status=='awaiting_review',first.error
    one=folder_for(setup,request);retained=snapshot(one)
    revision=revise(setup,request,one/'terminal.json');second=propose(setup,revision)
    assert second.status=='awaiting_review',second.error
    two=folder_for(setup,revision)
    assert len(calls)==2 and calls[0]==calls[1]
    assert calls[1]['source']!=read(one/'media.json')['candidate']
    assert read(one/'fit.json')['amplitude']==read(two/'fit.json')['amplitude']
    assert (one/'intended.rgb').read_bytes()==(two/'intended.rgb').read_bytes()
    assert snapshot(one)==retained
    assert snapshot(setup['run']/'production/scene-clips')==original


def test_status_has_zero_writes_and_same_size_mtime_drift_is_stale(runtime_run,monkeypatch):
    from video_ai.runtime.scene_color_repair_records import load_scene_color_repair_progress
    setup,request=complete_setup(runtime_run,monkeypatch);calls=spy_render(monkeypatch)
    result=propose(setup,request)
    assert result.status=='noop',result.error
    before=snapshot(setup['run'])
    status=load_scene_color_repair_progress(setup['frozen'])
    assert status['candidates'][0]['state']=='noop'
    assert snapshot(setup['run'])==before
    target=folder_for(setup,request)/'fit.json';stamp=target.stat();raw=target.read_bytes()
    assert b'noop' in raw
    target.write_bytes(raw.replace(b'noop',b'nooq',1));os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    changed=snapshot(setup['run'])
    stale=load_scene_color_repair_progress(setup['frozen'])
    assert stale['candidates'][0]['state']=='stale' and stale['candidates'][0]['reasons']
    assert snapshot(setup['run'])==changed and calls==[]


def fixture_review(setup,folder,*,failed=False):
    from video_ai.runtime._scene_color_repair_validation import review_expected
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime.manifest import now
    expected=review_expected(setup['frozen'],folder,reader=Reader())
    value=read(folder/'review-template.json')
    value.update(reviewer='fixture_only synthetic author; no actual playback claim',viewed_at=now(),verdict='passed')
    value['checks']={k:'passed' for k in value['checks']}
    for key in ('start_observation','process_observation','end_observation','quality_observation'):
        value[key]='fixture_only before/after comparison; software recovery test only'
    for row in value['responses']:
        resolved=row['assessment']==expected['before_report'] and row['concern_id'] in expected['confirmed_colors']
        row.update(disposition='resolved_in_candidate' if resolved else 'not_observed_in_full_playback',
                   reason='fixture_only synthetic complete playback response',
                   references=[expected['after_report'],expected['fit']] if resolved else [])
    if failed:
        assert value['responses'],'fixture must exercise a real measured concern'
        value['responses'][0].update(disposition='confirmed_issue',references=[])
        value['verdict']='failed'
        value['issues']=[dict(check='color_improvement',media=expected['playback'],frames=[0,2],
            description='fixture_only confirmed remaining issue; not visual acceptance')]
    return save(setup['run']/('fixture_only-review-'+uuid4().hex+'.json'),value)


def test_valid_failed_review_permanently_blocks_later_passed_and_new_epoch(runtime_run,monkeypatch):
    from video_ai.runtime._scene_color_repair_validation import review_expected,validate_candidate_review
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime.scene_color_repair_records import load_scene_color_repair_progress
    from video_ai.runtime.production_scene_continuity import reassess_scene_continuity
    from video_ai.runtime.manifest import now
    setup,request=complete_setup(runtime_run,monkeypatch,colored=True);runtime=module()
    calls=spy_render(monkeypatch);result=propose(setup,request)
    assert result.status=='awaiting_review',result.error
    folder=folder_for(setup,request);original=snapshot(setup['run']/'production/scene-clips')
    failed=fixture_review(setup,folder,failed=True)
    expected=review_expected(setup['frozen'],folder,reader=Reader())
    assert validate_candidate_review(read(failed),expected,reader=Reader())['verdict']=='failed'
    submit=lambda path:runtime.consume_scene_color_repair_review(setup['frozen'],path,paths=setup['paths'],logger=setup['logger'])
    rejected=submit(failed)
    assert rejected.status=='blocked',rejected.error
    assert load_scene_color_repair_progress(setup['frozen'])['candidates'][0]['state']=='rejected'
    passed=fixture_review(setup,folder);later=submit(passed)
    assert later.status=='blocked',later.error
    assert load_scene_color_repair_progress(setup['frozen'])['candidates'][0]['state']=='rejected'
    archives=list((folder.parents[1]/'reviews').glob('*.json'))
    assert len(archives)==2 and {p.read_bytes() for p in archives}=={failed.read_bytes(),passed.read_bytes()}
    assert read(folder/'review-receipt.json')['state']=='rejected'
    epoch=read(folder/'intent.json')['binding']['epoch']
    request_epoch=save(setup['run']/'fixture_only-reassess-color-repair.json',dict(schema_version=1,
        run_id=setup['run'].name,epoch_id=str(uuid4()),previous_commit=epoch,
        reason='fixture_only new epoch with unchanged original media',requested_at=now()))
    newer=reassess_scene_continuity(setup['frozen'],[],setup['timeline'],request_epoch,
        paths=setup['paths'],logger=setup['logger'])
    assert newer.status=='awaiting_analysis',newer.error
    before=snapshot(setup['run'])
    stale=load_scene_color_repair_progress(setup['frozen'])
    assert stale['candidates'][0]['state']=='stale'
    assert snapshot(setup['run'])==before
    copied=submit(passed)
    assert copied.status=='blocked',copied.error
    assert read(folder/'review-receipt.json')['state']=='rejected' and len(calls)==1
    assert snapshot(setup['run']/'production/scene-clips')==original


def test_bad_recovered_fit_never_commits_a_successful_terminal(runtime_run,monkeypatch):
    setup,request=complete_setup(runtime_run,monkeypatch,colored=True);runtime=module()
    def stop(point):
        if point=='after-report':raise KeyboardInterrupt('fixture_only complete outputs before terminal')
    monkeypatch.setattr(runtime,'boundary',stop)
    first=propose(setup,request);folder=folder_for(setup,request)
    assert first.status=='interrupted' and not (folder/'terminal.json').exists(),first.error
    fit=read(folder/'fit.json');fit.update(status='noop',amplitude=0.,correction_bound=None)
    save(folder/'fit.json',fit)
    monkeypatch.setattr(runtime,'boundary',lambda point:None)
    second=propose(setup,request)
    assert second.status in ('blocked','failed'),second.error
    if (folder/'terminal.json').exists():
        assert read(folder/'terminal.json')['status'] in ('failed','interrupted'),'invalid recovery must never durably claim awaiting_review'


@pytest.mark.parametrize('fault',['encoder','timeout'])
def test_actual_ffmpeg_failure_keeps_original_and_never_retries_same_uuid(runtime_run,monkeypatch,fault):
    import video_ai.runtime.processes as processes
    setup,request=complete_setup(runtime_run,monkeypatch,colored=True)
    original=snapshot(setup['run']/'production/scene-clips');actual=processes.run_logged;commands=[]
    def injected(args,**kwargs):
        if kwargs.get('stage')=='scene_color_repair' and args[-1].endswith('master.mp4'):
            args=list(args)
            if fault=='encoder':args[args.index('-c:v')+1]='fixture_only_missing_encoder'
            else:kwargs['timeout']=1e-9
            result=actual(args,**kwargs);commands.append(result);return result
        return actual(args,**kwargs)
    monkeypatch.setattr(processes,'run_logged',injected)
    first=propose(setup,request);folder=folder_for(setup,request)
    assert first.status=='failed' and read(folder/'terminal.json')['status']=='failed',first.error
    assert not (folder/'media.json').exists()
    assert len(commands)==1 and commands[0].returncode!=0
    if fault=='timeout':assert commands[0].timed_out is True
    assert commands[0].stdout_path.is_file() and commands[0].stderr_path.is_file()
    second=propose(setup,request)
    assert second.status=='failed' and second.terminal==first.terminal and len(commands)==1
    assert snapshot(setup['run']/'production/scene-clips')==original
