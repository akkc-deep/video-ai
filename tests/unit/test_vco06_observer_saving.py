"""Run real portal JavaScript; simulated events are never actual video observations."""
import json
from pathlib import Path
import subprocess

import pytest


def run_browser(tmp_path, checks):
    template = Path(__file__).parents[2]/'scripts/experiments/vco06_observe.html'
    script = template.read_text(encoding='utf-8').split('<script>')[1].split('</script>')[0]
    cases = [dict(case_id='fixture_dev_'+str(i), split='development', video_url='v'+str(i),
        reference_url='r'+str(i),video=dict(path='v'+str(i),bytes=1,sha256=str(i)*64),
        reference=dict(path='r'+str(i),bytes=1,sha256='a'*64)) for i in range(2)]
    script = script.replace('/*COLLECTION_DATA*/null', json.dumps(dict(collection={'sha256':'b'*64},cases=cases)))
    harness = r"""
const assert=require('node:assert/strict');let blobText='',downloads=0,blockDownload=false;
const elements={},events={},memory=new Map();
global.localStorage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v)};
global.Blob=class{constructor(parts){blobText=parts.join('');}};
global.URL={createObjectURL(){return 'blob:fixture';},revokeObjectURL(){}};
global.setTimeout=f=>{f();return 1;};
global.document={hidden:false,body:{append(){},appendChild(){}},
 getElementById(id){return elements[id]??={value:id==='cases'?'0':'',selectedIndex:0,checked:false,
 textContent:'',hidden:false,append(){},appendChild(){},focus(){},select(){},pause(){},
 currentTime:0,playbackRate:1,ended:false,readyState:4,requestVideoFrameCallback(){},
 addEventListener(e,f){(this.handlers??={})[e]=f;events[e]=f;}};},
 createElement(){return {click(){if(blockDownload)throw Error('download blocked');downloads++;},remove(){}};},
 addEventListener(e,f){events[e]=f;}};
function fill(){
 for(const [id,value] of Object.entries({reviewer:'fixture_only_no_actual_viewing',description:'Synthetic browser test only.',
 label:'neutral',axis:'',structure:'true',motion:'true',lighting:'false'}))document.getElementById(id).value=value;
 document.getElementById('target').checked=true;
}
"""
    setup = r"""
fill();playback=defaults();playback.completed=true;
playback.covered_frames=Array.from({length:49},(_,i)=>i);playback.frame_times=playback.covered_frames.map(i=>i/16);
playback.started_at=new Date(Date.now()-10000).toISOString();playback.ended_at=new Date().toISOString();playback.elapsed_seconds=49/16;
"""
    path=tmp_path/'saving.cjs';path.write_text(harness+script+setup+checks,encoding='utf-8')
    result=subprocess.run(['node',str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_conflicting_confirmed_choices_are_exported_unchanged_as_draft(tmp_path):
    output=run_browser(tmp_path,r"""
$('lighting').value='true';$('save').onclick();
assert.equal(downloads,1,'raw choices must remain saveable even when confirmation is invalid');
const record=JSON.parse(blobText);
assert.equal(record.kind,'natural_material_observation_draft_v1');
assert.equal(record.form.natural_label,'neutral');assert.equal(record.form.intentional_lighting_change,true);
assert.equal(record.playback.completed,true);assert.equal(record.ready_for_propose,false);
assert.ok(record.validation_errors.some(x=>x.includes('光照')));
assert.ok($('message').textContent.includes('草稿'));
console.log(blobText);
""")
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    with pytest.raises(ValueError): validate_observation(json.loads(output))


def test_incomplete_form_can_be_saved_without_inventing_author_or_viewing(tmp_path):
    run_browser(tmp_path,r"""
$('reviewer').value='';$('description').value='';playback=defaults();$('save').onclick();
assert.equal(downloads,1);const record=JSON.parse(blobText);
assert.equal(record.form.reviewer,'');assert.equal(record.form.description,'');
assert.deepEqual(record.playback.covered_frames,[]);assert.equal(record.playback.completed,false);
assert.equal(record.kind,'natural_material_observation_draft_v1');
""")


def test_valid_record_preserves_existing_observation_schema(tmp_path):
    output=run_browser(tmp_path,r"""
$('save').onclick();assert.equal(downloads,1);console.log(blobText);
""")
    from video_ai.experiments.natural_acquisition_observation import validate_observation
    row=json.loads(output)
    assert row['kind']=='natural_material_observation_v1'
    assert validate_observation(row)=='label_recorded'


def test_blocked_browser_download_still_exposes_exact_copyable_record(tmp_path):
    run_browser(tmp_path,r"""
blockDownload=true;$('save').onclick();
assert.ok($('exportText').value.length>0,'download failure must not discard the serialized record');
assert.equal($('exportText').value,blobText);
assert.ok($('message').textContent.includes('复制'));
""")


def test_switching_cases_restores_each_cases_choices(tmp_path):
    run_browser(tmp_path,r"""
$('description').value='first case choice';$('lighting').value='true';
$('cases').value='1';$('cases').onchange();$('description').value='second case choice';
$('cases').value='0';$('cases').onchange();
assert.equal($('description').value,'first case choice');assert.equal($('lighting').value,'true');
""")


def test_non_color_label_does_not_silently_discard_selected_axis(tmp_path):
    run_browser(tmp_path,r"""
$('label').value='unverified';$('axis').value='wb_r:negative';$('save').onclick();
const row=JSON.parse(blobText);assert.equal(row.kind,'natural_material_observation_draft_v1');
assert.equal(row.form.axis,'wb_r:negative');assert.equal(row.form.natural_label,'unverified');
""")


def test_storage_rejection_does_not_block_saving_or_switching(tmp_path):
    run_browser(tmp_path,r"""
Object.defineProperty(globalThis,'localStorage',{get(){throw Error('storage unavailable');}});
$('description').value='keep my choice';$('cases').value='1';$('cases').onchange();
$('cases').value='0';$('cases').onchange();assert.equal($('description').value,'keep my choice');
$('save').onclick();assert.equal(downloads,1);
""")
