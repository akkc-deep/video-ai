"""Synthetic browser events test software only; they never attest real viewing."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from test_natural_acquisition_observation import observation


def browser(tmp_path, checks):
    template = Path(__file__).parents[2] / 'scripts/experiments/vco06_observe.html'
    script = template.read_text(encoding='utf-8').split('<script>')[1].split('</script>')[0]
    row = observation()
    cases = [dict(case_id=row['case_id'], split='development', video_url='fixture.mp4',
                  reference_url='fixture.png', video=row['video'], reference=row['reference'])]
    cases.append(dict(cases[0], case_id='fixture_second_case', video_url='second.mp4',
                      video=dict(path='second', bytes=1, sha256='9'*64)))
    script = script.replace('/*COLLECTION_DATA*/null', json.dumps(dict(collection=row['collection'], cases=cases)))
    harness = r"""
const assert=require('node:assert/strict');
let clock=0, callback=null, blobText='',timerId=0;
const RealDate=Date, base=Date.UTC(2026,9,28,18), timers=new Map(), elements={};
global.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[base+clock]));}static now(){return Math.trunc(base+clock);}};
global.performance={now:()=>clock};
global.setTimeout=(f,delay=0)=>{let id=++timerId;timers.set(id,{at:clock+delay,f});return id;};
global.clearTimeout=id=>timers.delete(id);
function advance(ms){const until=clock+ms;for(let n=0;n<10000;n++){
 let next=[...timers].filter(([,v])=>v.at<=until).sort((a,b)=>a[1].at-b[1].at)[0];
 if(!next){clock=until;return;}clock=next[1].at;timers.delete(next[0]);next[1].f();}throw Error('timer loop');}
function element(id){return {value:id==='cases'?'0':'',checked:false,textContent:'',append(){},focus(){},select(){},
 handlers:{},addEventListener(e,f){(this.handlers[e]??=[]).push(f);},
 pause(){},async play(){this.ended=false;},readyState:4,currentTime:0,duration:49/16,ended:false,playbackRate:1,
 get currentSrc(){return this.src;},played:{length:1,start:()=>0,end:()=>49/16},
 requestVideoFrameCallback(f){callback=f;}};}
global.document={hidden:false,handlers:{},body:{appendChild(){}},
 getElementById(id){return elements[id]??=element(id);},
 createElement(){return {click(){},remove(){}};},
 addEventListener(e,f){(this.handlers[e]??=[]).push(f);}};
global.Blob=class{constructor(parts){blobText=parts.join('');}};
global.URL={createObjectURL:()=>'blob:fixture',revokeObjectURL(){}};
const memory=new Map();global.localStorage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v)};
function fire(e,target=document.getElementById('video')){for(const f of target.handlers[e]??[])f();}
function frame(i){const f=callback;callback=null;f(clock,{mediaTime:i/16,presentedFrames:i+1});}
function fill(){for(const [id,value] of Object.entries({reviewer:'fixture_only_no_actual_viewing',
 description:'Synthetic software verification only.',label:'neutral',axis:'',structure:'true',motion:'true',lighting:'false'}))
 document.getElementById(id).value=value;document.getElementById('target').checked=true;}
async function watch({missing=[],lateLast=false}={}){
 const video=document.getElementById('video');video.currentTime=0;frame(0);await document.getElementById('start').onclick();
 for(let i=1;i<49;i++){advance(62.5);if(!missing.includes(i)&&!(lateLast&&i===48))frame(i);}
 advance(62.5);video.currentTime=video.duration;video.ended=true;fire('ended');
}
"""
    path = tmp_path / 'remote-browser.cjs'
    path.write_text(harness + script + '\n(async()=>{\n' + checks +
                    '\n})().catch(e=>{console.error(e);process.exitCode=1;});', encoding='utf-8')
    result = subprocess.run(['node', str(path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_real_late_final_callback_is_kept_without_padding_end_time(tmp_path):
    browser(tmp_path, r"""
await watch({lateLast:true});const endedAt=Date.now();advance(150);frame(48);advance(1000);
assert.equal(playback.completed,true,'late actual callback must not be discarded after 100ms');
assert.equal(playback.elapsed_seconds,3.0625,'settlement must not inflate elapsed playback time');
assert.equal(Date.parse(playback.ended_at),endedAt);
""")


def test_previous_end_timer_cannot_close_a_new_playback(tmp_path):
    browser(tmp_path, r"""
await watch({lateLast:true});v.currentTime=0;await $('start').onclick();
const fresh=playback;advance(1500);assert.equal(recording,true,'old settlement must not stop a new viewing');
assert.equal(playback,fresh);assert.equal(playback.ended_at,null);
""")


def test_page_changes_after_native_end_do_not_rewrite_completed_viewing(tmp_path):
    browser(tmp_path, r"""
await watch({missing:[7]});
document.hidden=true;fire('visibilitychange',document);v.playbackRate=2;fire('ratechange');
v.ended=false;fire('pause');fire('waiting');advance(1500);
assert.equal(playback.visible,true,'post-ended visibility is outside the viewing interval');
assert.equal(playback.playback_rate,1);assert.deepEqual(playback.interruptions,[]);
fill();$('viewerComplete').checked=true;$('save').onclick();
assert.equal(JSON.parse(blobText).kind,'natural_material_observation_remote_v2');
""")


def test_pending_start_does_not_autoplay_or_erase_another_cases_evidence(tmp_path):
    browser(tmp_path, r"""
v.readyState=0;const pendingStart=$('start').onclick();
$('cases').value='1';$('cases').onchange();const other=playback;
v.readyState=4;fire('canplay');await pendingStart;
assert.equal(playback,other,'stale start continuation must not replace the selected case evidence');
assert.equal(recording,false);
""")


def test_previous_play_rejection_cannot_stop_a_new_viewing(tmp_path):
    browser(tmp_path, r"""
let rejectOld;v.play=()=>new Promise((resolve,reject)=>{rejectOld=reject;});
const oldStart=$('start').onclick();v.play=async()=>{};await $('start').onclick();
const active=playback;rejectOld(Error('old aborted play'));await oldStart;
assert.equal(playback,active);assert.equal(recording,true,'old rejection must not close new recording');
assert.deepEqual(playback.interruptions,[]);
""")


def test_queued_pause_from_previous_play_does_not_invalidate_active_video(tmp_path):
    browser(tmp_path, r"""
await $('start').onclick();v.paused=false;fire('pause');
assert.deepEqual(playback.interruptions,[],'queued pause is stale when video is already playing');
v.paused=true;fire('pause');assert.ok(playback.interruptions.includes('暂停'));
""")


def test_missing_callbacks_stay_missing_and_offer_saveable_diagnostics(tmp_path):
    browser(tmp_path, r"""
await watch({missing:[7,8]});advance(1500);
assert.equal(playback.completed,false);assert.equal(playback.covered_frames.length,47);
assert.ok(!playback.covered_frames.includes(7));
assert.match($('progress').textContent,/47\s*\/\s*49/);
assert.match($('progress').textContent,/7.*8/);
fill();$('save').onclick();const raw=JSON.parse(blobText);
assert.equal(raw.kind,'natural_material_observation_draft_v1');
assert.equal(raw.playback.completed,false);assert.equal(raw.form.natural_label,'neutral');
""")


def test_remote_full_timeline_and_explicit_human_confirmation_export_distinct_record(tmp_path):
    output = browser(tmp_path, r"""
await watch({missing:[7,8]});advance(1500);fill();$('viewerComplete').checked=true;$('save').onclick();
const row=JSON.parse(blobText);assert.equal(row.kind,'natural_material_observation_remote_v2');
assert.equal(row.playback.completed,false);assert.equal(row.playback.covered_frames.length,47);
assert.equal(row.remote_playback.viewer_confirmed_complete,true);console.log(blobText);
""")
    from video_ai.experiments.natural_remote_observation import validate_remote_observation
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    row = json.loads(output)
    assert validate_remote_observation(row) == 'remote_label_recorded'
    with pytest.raises(ValueError):
        validate_observation(row)


def test_native_all_frame_playback_still_exports_frozen_v1_schema(tmp_path):
    output = browser(tmp_path, r"""
await watch();advance(1500);fill();$('save').onclick();
const row=JSON.parse(blobText);assert.equal(row.kind,'natural_material_observation_v1');console.log(blobText);
""")
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    assert validate_observation(json.loads(output)) == 'label_recorded'


def test_remote_evidence_and_choices_survive_reload_but_confirmation_resets_on_replay(tmp_path):
    browser(tmp_path, r"""
await watch({missing:[7]});advance(1500);fill();$('viewerComplete').checked=true;remember();
load();assert.equal($('description').value,'Synthetic software verification only.');
assert.equal($('viewerComplete').checked,true);assert.equal(playback.covered_frames.length,48);
$('save').onclick();assert.equal(JSON.parse(blobText).kind,'natural_material_observation_remote_v2');
v.currentTime=0;await $('start').onclick();
assert.equal($('viewerComplete').checked,false,'human confirmation belongs to the prior viewing only');
assert.equal($('description').value,'Synthetic software verification only.');
$('save').onclick();assert.equal(JSON.parse(blobText).kind,'natural_material_observation_draft_v1');
""")


def test_remote_viewing_does_not_require_any_compositor_callbacks(tmp_path):
    output = browser(tmp_path, r"""
await $('start').onclick();advance(3062.5);v.currentTime=v.duration;v.ended=true;fire('ended');advance(1500);
fill();$('viewerComplete').checked=true;$('save').onclick();
const row=JSON.parse(blobText);assert.equal(row.kind,'natural_material_observation_remote_v2');
assert.deepEqual(row.playback.covered_frames,[]);assert.deepEqual(row.playback.frame_times,[]);console.log(blobText);
""")
    from video_ai.experiments.natural_remote_observation import validate_remote_observation
    assert validate_remote_observation(json.loads(output)) == 'remote_label_recorded'


def test_network_stall_with_continuous_buffered_playback_is_preserved_as_diagnostic(tmp_path):
    output = browser(tmp_path, r"""
await watch({missing:[7]});playback.interruptions.push('stalled');advance(1500);
fill();$('viewerComplete').checked=true;$('save').onclick();
const row=JSON.parse(blobText);assert.equal(row.kind,'natural_material_observation_remote_v2');
assert.deepEqual(row.playback.interruptions,['stalled']);assert.equal(row.playback.completed,false);console.log(blobText);
""")
    from video_ai.experiments.natural_remote_observation import validate_remote_observation
    assert validate_remote_observation(json.loads(output)) == 'remote_label_recorded'


@pytest.mark.parametrize('problem', ['unconfirmed', 'hidden', 'seek', 'pause', 'waiting', 'rate', 'short', 'range_gap'])
def test_remote_browser_rejects_incomplete_or_interrupted_viewing(tmp_path, problem):
    checks = {
        'unconfirmed': "$('viewerComplete').checked=false;",
        'hidden': "playback.visible=false;",
        'seek': "playback.interruptions.push('跳转');",
        'pause': "playback.interruptions.push('暂停');",
        'waiting': "playback.interruptions.push('waiting');",
        'rate': "playback.playback_rate=2;",
        'short': "playback.elapsed_seconds=.5;",
        'range_gap': "remotePlayback.played_ranges=[[0,1],[1.5,49/16]];",
    }[problem]
    browser(tmp_path, r"""
await watch({missing:[7]});advance(1500);fill();$('viewerComplete').checked=true;
""" + checks + r"""
$('save').onclick();const row=JSON.parse(blobText);
assert.equal(row.kind,'natural_material_observation_draft_v1');assert.equal(row.ready_for_propose,false);
""")


def remote_observation():
    row = observation()
    row.update(schema_version=2, kind='natural_material_observation_remote_v2', review_method='human_remote_video')
    row['playback']['completed'] = False
    row['playback']['covered_frames'].pop(7)
    row['playback']['frame_times'].pop(7)
    row['remote_playback'] = dict(ended_event=True, media_duration=49/16, end_media_time=49/16,
        played_ranges=[[0, 49/16]], video_sha256=row['video']['sha256'], viewer_confirmed_complete=True)
    return row


def test_independent_remote_schema_retains_actual_incomplete_frame_evidence():
    from video_ai.experiments.natural_remote_observation import validate_remote_observation
    row = remote_observation()
    before = json.dumps(row)
    assert validate_remote_observation(row) == 'remote_label_recorded'
    assert json.dumps(row) == before


@pytest.mark.parametrize('problem', [
    'schema', 'author', 'target', 'structure', 'motion', 'lighting', 'axis', 'confirmation', 'ended',
    'duration', 'current_time', 'gap', 'range_start', 'range_end', 'rate', 'hidden', 'seek',
    'short', 'short_dates', 'inconsistent_dates', 'end_after_review', 'frame_times', 'frame_duplicate',
    'frame_bounds', 'false_strict_complete', 'media', 'nan', 'boolean_number', 'extra', 'draft'])
def test_remote_validator_rejects_false_or_mismatched_proof(problem):
    from video_ai.experiments.natural_remote_observation import validate_remote_observation
    row = remote_observation()
    p, r = row['playback'], row['remote_playback']
    if problem == 'schema': row['schema_version'] = True
    elif problem == 'author': row['reviewer'] = ' '
    elif problem == 'target': row['target_reference_confirmed'] = False
    elif problem == 'structure': row['subject_structure_intact'] = False
    elif problem == 'motion': row['motion_intact'] = None
    elif problem == 'lighting': row['intentional_lighting_change'] = True
    elif problem == 'axis': row.update(natural_label='mild_color_bias', operation='wb_b', correction_direction='positive')
    elif problem == 'confirmation': r['viewer_confirmed_complete'] = False
    elif problem == 'ended': r['ended_event'] = False
    elif problem == 'duration': r['media_duration'] = 2.5
    elif problem == 'current_time': r['end_media_time'] = 2.5
    elif problem == 'gap': r['played_ranges'] = [[0, 1], [1.5, 49/16]]
    elif problem == 'range_start': r['played_ranges'] = [[.5, 49/16]]
    elif problem == 'range_end': r['played_ranges'] = [[0, 2.5]]
    elif problem == 'rate': p['playback_rate'] = 2
    elif problem == 'hidden': p['visible'] = False
    elif problem == 'seek': p['interruptions'] = ['seeking']
    elif problem == 'short': p['elapsed_seconds'] = .5
    elif problem == 'short_dates': p['started_at'] = p['ended_at']
    elif problem == 'inconsistent_dates': p['elapsed_seconds'] = 30
    elif problem == 'end_after_review': row['reviewed_at'] = p['started_at']
    elif problem == 'frame_times': p['frame_times'][2] = 1
    elif problem == 'frame_duplicate': p['covered_frames'][2] = 1
    elif problem == 'frame_bounds': p['covered_frames'][-1] = 49
    elif problem == 'false_strict_complete': p['completed'] = True
    elif problem == 'media': r['video_sha256'] = '9'*64
    elif problem == 'nan': r['played_ranges'][0][1] = float('nan')
    elif problem == 'boolean_number': r['played_ranges'][0][0] = False
    elif problem == 'extra': row['ready_for_propose'] = True
    elif problem == 'draft': row['kind'] = 'natural_material_observation_draft_v1'
    with pytest.raises(ValueError):
        validate_remote_observation(row)


@pytest.fixture
def remote_intake(tmp_path, monkeypatch):
    from video_ai.experiments import natural_remote_observation as module
    root = tmp_path / 'intake'; root.mkdir()
    row = remote_observation()
    (root/'collection-receipt.json').write_text(json.dumps(dict(collection=row['collection'])), encoding='utf-8')
    case = dict(case_id=row['case_id'], reference=row['reference'], split='development')
    result = dict(video=row['video'], finished_at=row['playback']['started_at'])
    monkeypatch.setattr(module, '_case', lambda *a: (None, case, root))
    monkeypatch.setattr(module, '_verified_result', lambda *a: result)
    path = root/'download.json'; path.write_text(json.dumps(row, indent=3)+'\n', encoding='utf-8')
    return module, root, row, case, result, path


def test_remote_intake_archives_exact_bytes_without_claiming_qualification(remote_intake):
    module, root, row, _, _, path = remote_intake
    raw = path.read_bytes()
    result = module.record_remote_observation(root, path)
    assert Path(result['observation']['path']).read_bytes() == raw
    assert result['status'] == 'remote_label_recorded'
    assert result['ready_for_propose'] is False and result['production_eligible'] is False
    assert not (root/'observations').exists(), 'v2 must never masquerade as frozen v1 observations'
    assert module.record_remote_observation(root, path)['observation'] == result['observation']


@pytest.mark.parametrize('problem', ['video', 'reference', 'collection', 'holdout', 'time'])
def test_remote_intake_rejects_wrong_source_or_holdout_before_archive(remote_intake, problem):
    module, root, _, case, result, path = remote_intake
    if problem == 'video': result['video'] = dict(path='different', bytes=1, sha256='9'*64)
    elif problem == 'reference': case['reference'] = dict(path='different', bytes=1, sha256='9'*64)
    elif problem == 'collection': (root/'collection-receipt.json').write_text('{"collection":{}}', encoding='utf-8')
    elif problem == 'holdout': case['split'] = 'holdout'
    elif problem == 'time': result['finished_at'] = remote_observation()['playback']['ended_at']
    with pytest.raises(ValueError): module.record_remote_observation(root, path)
    assert not (root/'remote-observations').exists()


def test_remote_intake_preserves_bytes_validated_before_external_file_changes(remote_intake, monkeypatch):
    module, root, _, _, _, path = remote_intake
    raw = path.read_bytes()
    original = module._case
    def changed(*args):
        path.write_text('{"not_validated":true}', encoding='utf-8')
        return original(*args)
    monkeypatch.setattr(module, '_case', changed)
    result = module.record_remote_observation(root, path)
    assert Path(result['observation']['path']).read_bytes() == raw


def test_remote_cli_rejects_unknown_collection_with_structured_result(tmp_path, capsys):
    path = Path(__file__).parents[2] / 'scripts/experiments/vco06_remote_observe.py'
    spec = importlib.util.spec_from_file_location('remote_cli', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    source = tmp_path/'row.json'; source.write_text(json.dumps(remote_observation()), encoding='utf-8')
    assert module.main(['--root', str(tmp_path/'unknown'), '--observation', str(source)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'blocked' and result['ready_for_propose'] is False
