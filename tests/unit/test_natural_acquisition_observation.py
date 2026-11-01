from datetime import datetime, timezone, timedelta

import pytest


def observation():
    start = datetime.now(timezone.utc)-timedelta(seconds=10)
    end = start+timedelta(seconds=49/16)
    return dict(schema_version=1,kind='natural_material_observation_v1',case_id='g01_ceramic_spheres_s01',
        collection=dict(path='collection',bytes=1,sha256='0'*64),
        video=dict(path='video',bytes=1,sha256='1'*64),reference=dict(path='reference',bytes=1,sha256='2'*64),
        reviewer='fixture_only_no_actual_playback',review_method='human_video',reviewed_at=end.isoformat(),
        playback=dict(completed=True,frames=49,fps='16/1',covered_frames=list(range(49)),
            frame_times=[i/16 for i in range(49)],started_at=start.isoformat(),ended_at=end.isoformat(),
            elapsed_seconds=49/16,playback_rate=1,visible=True,interruptions=[]),
        natural_label='neutral',operation=None,correction_direction=None,target_reference_confirmed=True,
        subject_structure_intact=True,motion_intact=True,intentional_lighting_change=False,
        description='Fixture only: validates software, does not attest to any real observation.')


def test_actual_label_requires_complete_playback_declaration():
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    assert validate_observation(observation()) == 'label_recorded'


@pytest.mark.parametrize('change', ['missing_frame','seek','hidden','rate','short','future','unknown_axis','blank_author','nonfinite'])
def test_invalid_playback_or_axis_never_records_valid_natural_label(change):
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    row = observation()
    if change == 'missing_frame':
        row['playback']['covered_frames'].pop()
    elif change == 'seek':
        row['playback']['interruptions'] = ['seeking']
    elif change == 'hidden':
        row['playback']['visible'] = False
    elif change == 'rate':
        row['playback']['playback_rate'] = 2
    elif change == 'short':
        row['playback']['elapsed_seconds'] = .5
    elif change == 'future':
        row['reviewed_at'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    elif change == 'unknown_axis':
        row['natural_label'] = 'mild_color_bias'
    elif change == 'blank_author':
        row['reviewer'] = ' '
    else:
        row['playback']['frame_times'][2] = float('nan')
    with pytest.raises(ValueError):
        validate_observation(row)


def test_unverified_observation_stays_unverified():
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    row = observation()
    row.update(natural_label='unverified',target_reference_confirmed=False,
               subject_structure_intact=None,motion_intact=None,intentional_lighting_change=None)
    row['playback'].update(completed=False,covered_frames=[],frame_times=[],elapsed_seconds=0)
    assert validate_observation(row) == 'unverified'


@pytest.mark.parametrize('axis,direction', [('exposure','negative'),('wb_r','negative'),('wb_g','positive'),('wb_g','negative')])
def test_supported_known_axis_needs_explicit_semantic_conditions(axis,direction):
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    row = observation()
    row.update(natural_label='mild_color_bias',operation=axis,correction_direction=direction)
    assert validate_observation(row) == 'label_recorded'
    row['motion_intact'] = False
    with pytest.raises(ValueError):
        validate_observation(row)


def test_unsafe_observation_can_record_failure_without_clear_motion():
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    row = observation()
    row.update(natural_label='unsafe',motion_intact=False,subject_structure_intact=None)
    assert validate_observation(row) == 'label_recorded'


def test_portal_never_exposes_unsealed_holdout(tmp_path, monkeypatch):
    from video_ai.experiments import natural_acquisition_observation as module
    import json
    root = tmp_path/'portal'; root.mkdir()
    (root/'collection-receipt.json').write_text(json.dumps(dict(collection={})),encoding='utf-8')
    cases = [dict(case_id='dev',split='development',video=dict(path=str(root/'dev.mp4')),
             reference=dict(path=str(root/'dev.png'))),
             dict(case_id='hold_secret',split='holdout',video=dict(path=str(root/'hold.mp4')),
             reference=dict(path=str(root/'hold.png')))]
    monkeypatch.setattr(module,'collection_status',lambda root:dict(cases=cases))
    result = module.export_portal(root)
    text = open(result['portal']['path'],encoding='utf-8').read()
    assert result['cases'] == 1 and 'hold_secret' not in text


@pytest.fixture
def intake(tmp_path, monkeypatch):
    from video_ai.experiments import natural_acquisition_observation as module
    import json
    root = tmp_path/'intake'; root.mkdir()
    row = observation()
    (root/'collection-receipt.json').write_text(json.dumps(dict(collection=row['collection'])),encoding='utf-8')
    case = dict(case_id=row['case_id'],reference=row['reference'],split='development')
    result = dict(video=row['video'],finished_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())
    monkeypatch.setattr(module,'_case',lambda *a:(None,case,root))
    monkeypatch.setattr(module,'_verified_result',lambda *a:result)
    return module, root, row, result


def test_observation_retains_exact_validated_bytes_if_original_changes(intake, monkeypatch):
    import json
    module, root, row, _ = intake
    path = root/'download.json'
    raw = json.dumps(row).encode(); path.write_bytes(raw)
    original_case = module._case
    def change_after_parse(*args):
        path.write_bytes(b'{"unvalidated":true}')
        return original_case(*args)
    monkeypatch.setattr(module,'_case',change_after_parse)
    result = module.record_observation(root,path)
    assert open(result['observation']['path'],'rb').read() == raw


def test_playback_cannot_predate_generated_source(intake):
    import json
    module, root, row, result = intake
    result['finished_at'] = row['playback']['ended_at']
    path = root/'old-playback.json'; path.write_text(json.dumps(row),encoding='utf-8')
    with pytest.raises(ValueError):
        module.record_observation(root,path)


def test_explicit_download_input_can_be_outside_runtime(intake, monkeypatch):
    from pathlib import Path
    import json
    module, root, row, _ = intake
    outside = Path('D:/code/py/video-ai/.observation-intake-test.json')
    assert not outside.exists()
    outside.write_text(json.dumps(row),encoding='utf-8')
    try:
        result = module.record_observation(root,outside)
        assert result['status'] == 'label_recorded'
    finally:
        outside.unlink()


def test_browser_tracks_pause_wait_and_hidden_page(tmp_path):
    import json, subprocess
    from pathlib import Path
    template = Path(__file__).parents[2]/'scripts/experiments/vco06_observe.html'
    script = template.read_text(encoding='utf-8').split('<script>')[1].split('</script>')[0]
    data = dict(collection={},cases=[dict(case_id='dev',split='development',video_url='v',reference_url='r')])
    script = script.replace('/*COLLECTION_DATA*/null',json.dumps(data))
    harness = r"""
const assert=require('node:assert/strict');const elements={};let events={};
global.document={hidden:false,getElementById(id){return elements[id]??={value:'0',selectedIndex:0,checked:false,append(){},
pause(){},currentTime:0,playbackRate:1,ended:false,requestVideoFrameCallback(){},addEventListener(e,f){events[e]=f;}};},
createElement(){return {};},addEventListener(e,f){events[e]=f;}};
"""
    checks = r"""
for(const name of ['pause','waiting','stalled','error']){
 recording=true;playback=defaults();v.ended=false;events[name]();assert.ok(playback.interruptions.length>0,name);
}
recording=true;playback=defaults();document.hidden=true;events.visibilitychange();assert.equal(playback.visible,false);
"""
    path = tmp_path/'browser-check.cjs';path.write_text(harness+script+checks,encoding='utf-8')
    result = subprocess.run(['node',str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr


def test_browser_counts_frame_zero_already_presented_while_paused(tmp_path):
    import json, subprocess
    from pathlib import Path
    template = Path(__file__).parents[2]/'scripts/experiments/vco06_observe.html'
    script = template.read_text(encoding='utf-8').split('<script>')[1].split('</script>')[0]
    data = dict(collection={},cases=[dict(case_id='dev',split='development',video_url='v',reference_url='r')])
    script = script.replace('/*COLLECTION_DATA*/null',json.dumps(data))
    harness = r"""
const assert=require('node:assert/strict');const elements={};let events={},callback;
global.document={hidden:false,getElementById(id){return elements[id]??={value:'0',selectedIndex:0,checked:false,append(){},
pause(){},async play(){},readyState:4,currentTime:0,playbackRate:1,ended:false,
requestVideoFrameCallback(f){callback=f;},addEventListener(e,f){events[e]=f;}};},
createElement(){return {};},addEventListener(e,f){events[e]=f;}};
"""
    checks = r"""
(async()=>{
 callback(0,{mediaTime:0,presentedFrames:1});
 await $('start').onclick();
 assert.deepEqual(playback.covered_frames,[0],'already presented frame0 must be bound to start');
 for(let i=1;i<49;i++)callback(i*62.5,{mediaTime:i/16,presentedFrames:i+1});
 assert.deepEqual(playback.covered_frames,Array.from({length:49},(_,i)=>i));
 assert.deepEqual(playback.interruptions,[]);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    path = tmp_path/'browser-frame-zero.cjs';path.write_text(harness+script+checks,encoding='utf-8')
    result = subprocess.run(['node',str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
