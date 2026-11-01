"""Real CPU color/ordinary reports; synthetic author declarations only."""
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from scene_continuity_helpers import tiny_scene_context,analysis_request,artifact,snapshot,save
from scene_color_repair_helpers import repair_request


def module():
    assert importlib.util.find_spec('video_ai.runtime.production_scene_color_repair'), 'repair transactions missing'
    return importlib.import_module('video_ai.runtime.production_scene_color_repair')


@pytest.fixture
def setup_repair(runtime_run,monkeypatch):
    from video_ai.runtime.production_scene_continuity import ensure_initial_epoch,analyze_scene_continuity
    from video_ai.runtime.production_state import RunLock
    setup=tiny_scene_context(runtime_run,monkeypatch)
    with RunLock(setup['run']) as lock:
        epoch=ensure_initial_epoch(setup['frozen'],[],setup['timeline'],paths=setup['paths'],logger=setup['logger'],lock=lock)
        req=analysis_request(setup,epoch,count=2)
        result=analyze_scene_continuity(setup['frozen'],[],setup['timeline'],req,paths=setup['paths'],logger=setup['logger'],lock=lock)
    assert result.status=='awaiting_review',result.error
    aid=json.loads(req.read_text(encoding='utf-8'))['assessment_id']
    setup['assessment']=setup['run']/f'production/scene-continuity/jobs/{aid}/assessment.json'
    return setup


def propose(setup,req):
    return module().propose_scene_color_repair(setup['frozen'],[],setup['timeline'],req,paths=setup['paths'],logger=setup['logger'])


def test_explicit_request_rejects_unverified_profile_before_candidate_media(setup_repair):
    setup=setup_repair;req=repair_request(setup,setup['assessment'])
    original=snapshot(setup['run']/'production/scene-clips')
    result=propose(setup,req)
    assert result.status=='blocked' and result.error
    assert snapshot(setup['run']/'production/scene-clips')==original
    assert not list((setup['run']/'production/scene-color-repair').rglob('*.mp4'))


def test_clip_revision_and_media_low_level_boundaries_reject_research_bytes(runtime_run):
    from types import SimpleNamespace
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.scene_revision_records import verify_artifact
    from video_ai.runtime._scene_revision_origin_clips import declared_artifact
    run,config,paths=runtime_run
    path=save(run/'production/scene-color-repair/candidates/x/master.mp4',{'fixture_only':True});ref=artifact(path)
    frozen=SimpleNamespace(config=config,options={'script_path':str(run/'production/script.txt')})
    stores=[SceneClipStore(frozen,run,paths=paths),SceneMediaStore(frozen,run,paths=paths)]
    for store in stores:
        with pytest.raises(ValueError,match='repair|research'):store.validate_artifact(ref)
    with pytest.raises(ValueError,match='repair|research'):verify_artifact(ref,root=run)
    with pytest.raises(ValueError,match='repair|research'):declared_artifact(stores[0],ref)


def complete_setup(runtime_run,monkeypatch,*,colored=False):
    from continuity_helpers import texture
    from video_ai.runtime.production_scene_continuity import ensure_initial_epoch,analyze_scene_continuity
    from video_ai.runtime.production_state import RunLock
    image=texture(64,36)
    if colored:
        # Literal three-code green / one-code opposing-channel shift on a
        # bright textured patch. Quantization at darker red/blue code values
        # would describe a different, unqualified mixed-axis perturbation.
        image[:,:,[0,2]]=225+image[:,:,[0,2]]%25
        image[:,:,1]=252
    def shifted(rgb,index):
        if colored:
            rgb[:,:,1]-=3;rgb[:,:,0]+=1;rgb[:,:,2]+=1
        return rgb
    setup=tiny_scene_context(runtime_run,monkeypatch,count=2,image=image,source_transform=shifted)
    with RunLock(setup['run']) as lock:
        epoch=ensure_initial_epoch(setup['frozen'],[],setup['timeline'],paths=setup['paths'],logger=setup['logger'],lock=lock)
        request=analysis_request(setup,epoch,count=2)
        result=analyze_scene_continuity(setup['frozen'],[],setup['timeline'],request,paths=setup['paths'],logger=setup['logger'],lock=lock)
    assert result.status=='awaiting_review',result.error
    aid=json.loads(request.read_text(encoding='utf-8'))['assessment_id']
    setup['assessment']=setup['run']/f'production/scene-continuity/jobs/{aid}/assessment.json'
    from repair_profile_helpers import make_profile
    profile_folder=setup['run']/'fixture_only-calibration';profile_folder.mkdir()
    req=repair_request(setup,setup['assessment'],profile=make_profile(profile_folder,green_axis=colored))
    # Review/status reconstruct the production context read-only. This fixture
    # substitutes the undersized Wan collector exactly as the continuity fixture.
    import video_ai.runtime._scene_color_repair_validation as validation
    original=validation.resolve_context
    def resolve(frozen,units=None,timeline=None,**kw):
        return original(frozen,[] if units is None else units,setup['timeline'] if timeline is None else timeline,**kw)
    monkeypatch.setattr(validation,'resolve_context',resolve)
    return setup,req


def test_genuine_closed_profile_to_all_frame_noop_and_readonly_status(runtime_run,monkeypatch):
    from video_ai.runtime.scene_color_repair_records import load_scene_color_repair_progress
    setup,req=complete_setup(runtime_run,monkeypatch)
    original=snapshot(setup['run']/'production/scene-clips')
    result=propose(setup,req)
    assert result.status=='noop',result.error
    terminal=json.loads(Path(result.terminal['path']).read_text(encoding='utf-8'))
    fit=json.loads(Path(terminal['fit']['path']).read_text(encoding='utf-8'))
    assert [row['source_frame_index'] for row in fit['frame_support']]==[0,1]
    assert all(row['pairs']>=81 for row in fit['frame_support'])
    assert terminal['pair_report']!=terminal['before_report']
    before=snapshot(setup['run'])
    status=load_scene_color_repair_progress(setup['frozen'])
    assert status['production_ready'] is False and status['candidates'][0]['state']=='noop',status
    assert snapshot(setup['run'])==before
    assert propose(setup,req).terminal==result.terminal
    assert snapshot(setup['run']/'production/scene-clips')==original


def test_genuine_cpu_candidate_master_playback_reports_and_fixture_review(runtime_run,monkeypatch):
    setup,req=complete_setup(runtime_run,monkeypatch,colored=True)
    result=propose(setup,req)
    assert result.status=='awaiting_review',result.error
    folder=Path(result.intent['path']).parent
    media=json.loads((folder/'media.json').read_text(encoding='utf-8'))
    assert media['frames']==2 and media['fps']=='16/1'
    assert (folder/'master.mp4').is_file() and (folder/'playback.mp4').is_file()
    terminal=json.loads((folder/'terminal.json').read_text(encoding='utf-8'))
    assert len({terminal[k]['path'] for k in ('pair_report','before_report','after_report')})==3
    from video_ai.runtime._scene_color_repair_media import validate_media
    from video_ai.runtime._scene_continuity_io import Reader
    from copy import deepcopy
    intent=json.loads((folder/'intent.json').read_text(encoding='utf-8'))
    for key,bad in [('width',True),('frames',True),('height',0),('candidate',media['source'])]:
        invalid=deepcopy(media);invalid[key]=bad
        with pytest.raises(ValueError):validate_media(invalid,intent,config=setup['config'],reader=Reader())
    from video_ai.runtime._scene_color_repair_validation import validate_saved_candidate
    terminal_bytes=(folder/'terminal.json').read_bytes()
    try:
        for key in ('pair_report','after_report'):
            invalid=deepcopy(terminal);invalid[key]=terminal['before_report']
            save(folder/'terminal.json',invalid)
            with pytest.raises(ValueError):validate_saved_candidate(setup['frozen'],folder,reader=Reader())
    finally:(folder/'terminal.json').write_bytes(terminal_bytes)
    from video_ai.runtime._scene_color_repair_validation import review_expected
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime.manifest import now
    expected=review_expected(setup['frozen'],folder,reader=Reader())
    value=json.loads((folder/'review-template.json').read_text(encoding='utf-8'))
    value.update(reviewer='fixture_only synthetic playback; no actual playback claim',viewed_at=now(),verdict='passed')
    value['checks']={k:'passed' for k in value['checks']}
    for k in ('start_observation','process_observation','end_observation','quality_observation'):value[k]='fixture_only before/after differences; no actual playback claim'
    for row in value['responses']:
        row['disposition']='resolved_in_candidate' if row['assessment']==expected['before_report'] and row['concern_id'] in expected['confirmed_colors'] else 'not_observed_in_full_playback'
        row['reason']='fixture_only observed candidate difference; software verification only'
        row['references']=[expected['after_report'],expected['fit']] if row['disposition']=='resolved_in_candidate' else []
    review=save(setup['run']/'fixture_only-candidate-review.json',value)
    runtime=module()
    for stop_at in ('review-original','review-receipt'):
        def interrupt(point,target=stop_at):
            if point==target:raise KeyboardInterrupt('fixture_only candidate review boundary '+target)
        monkeypatch.setattr(runtime,'boundary',interrupt)
        interrupted=runtime.consume_scene_color_repair_review(setup['frozen'],review,paths=setup['paths'],logger=setup['logger'])
        assert interrupted.status=='interrupted',interrupted.error
    monkeypatch.setattr(runtime,'boundary',lambda point:None)
    outcome=module().consume_scene_color_repair_review(setup['frozen'],review,paths=setup['paths'],logger=setup['logger'])
    assert outcome.status=='reviewed',outcome.error
    from video_ai.runtime.scene_color_repair_records import load_scene_color_repair_progress
    status=load_scene_color_repair_progress(setup['frozen'])
    assert status['production_ready'] is False and status['candidates'][0]['state']=='research_candidate_reviewed',status
