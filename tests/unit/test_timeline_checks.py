import json
from pathlib import Path
import wave
import pytest


def rewrite_segments(run,store,data):
    from video_ai.runtime.speech_checks import _artifact
    path=run/'segments.json'; path.write_text(json.dumps(data),encoding='utf-8')
    # Set up a self-consistent but invalid input as an external frozen speech report.
    manifest=store.snapshot(); manifest['stages']['speech']['artifacts']=[_artifact(path)]
    (run/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')


def accept(run,data):
    from video_ai.runtime.manifest import hash_file,thaw,now
    result=dict(schema_version=1,listened=True,accepted=True,user_statement='试听通过',accepted_at=now(),
                segments_identity=thaw(hash_file(run/'segments.json')),
                audio=[{k:s[k] for k in ('unit_id','text','pcm','samples')} for s in data['spans'] if s['kind']=='speech'])
    (run/'voice-listening.json').write_text(json.dumps(result),encoding='utf-8')
    return result


@pytest.mark.parametrize('accepted',[False,True])
def test_transaction_preserves_inputs_and_speech(timeline_run,accepted):
    from video_ai.runtime.timeline_checks import plan_timeline,load_committed_timeline
    run,config,store,data=timeline_run
    if accepted:accept(run,data)
    before=store.snapshot()
    immutable={str(p):p.read_bytes() for p in run.rglob('*') if p.is_file() and p.name!='manifest.json'}
    result=plan_timeline(config,run_dir=run)
    assert result.passed and result.listening_accepted==accepted
    assert (result.total_samples,result.total_frames)==(350400,117)
    t=load_committed_timeline(run)
    assert [c.text for c in t.clips]==['树梢，','水面倒影。','末尾。']
    assert [c.pause_samples for c in t.clips]==[0,96000,0]
    after=store.snapshot()
    assert after['stages']['timeline']['status']=='completed'
    for key in ('config_snapshot','voice_snapshot','inputs','units','services'):
        assert before[key]==after[key]
    assert before['stages']['speech']==after['stages']['speech']
    assert all(Path(p).read_bytes()==b for p,b in immutable.items())
    assert not (run/'.timeline.lock').exists()
    artifact=after['stages']['timeline']['artifacts'][0]
    assert artifact['category']=='run' and artifact['path']==str(run/'timeline.json')


@pytest.mark.parametrize('bad',['boundary','samples','missing','duplicate','extra','path','format','payload','sha','source','text','bom','accepted','snapshot','unit_status'])
def test_invalid_input_never_commits(timeline_run,bad):
    from video_ai.runtime.timeline_checks import plan_timeline
    from video_ai.runtime.manifest import thaw,hash_file
    run,config,store,data=timeline_run
    speech=[x for x in data['spans'] if x['kind']=='speech']
    if bad=='boundary':speech[0]['boundary']='sentence'
    if bad=='samples':speech[0]['samples']+=1
    if bad=='missing':data['spans'].pop(0)
    if bad=='duplicate':data['spans'].insert(0,dict(speech[0]))
    if bad=='extra':data['spans'].append(dict(speech[0],unit_id='reference_replay'))
    if bad=='path':speech[0]['pcm']['path']=str(run/'audio/speech_0002/pcm-48000.wav')
    if bad in ('format','payload'):
        pcm=Path(speech[0]['pcm']['path'])
        if bad=='format':
            with wave.open(str(pcm),'wb') as f:
                f.setparams((2,2,48000,0,'NONE',''));f.writeframes(b'\0'*19200)
        else:pcm.write_bytes(pcm.read_bytes()[:-2])
        ident=hash_file(pcm); speech[0]['pcm'].update(bytes=ident.bytes,sha256=ident.sha256)
    if bad=='sha':Path(speech[0]['pcm']['path']).write_bytes(b'bad')
    if bad=='source':Path(data['source']['path']).write_bytes(b'changed source')
    if bad=='text':data['decoded_text']='another text'
    if bad=='bom':data['has_bom']=False
    rewrite_segments(run,store,data)
    if bad=='accepted':
        record=accept(run,data);record['audio'][0]['samples']+=1
        (run/'voice-listening.json').write_text(json.dumps(record),encoding='utf-8')
    if bad in ('snapshot','unit_status'):
        manifest=store.snapshot()
        if bad=='snapshot':manifest['config_snapshot']['raw']['media']['fps']=24
        else:manifest['units']['speech']['speech_0001']['status']='failed'
        (run/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    result=plan_timeline(config,run_dir=run)
    assert not result.passed and store.snapshot()['stages']['timeline']['status']!='completed'
    assert not (run/'timeline.json').exists()
    assert list((run/'logs/timeline').glob('*.failure.json'))


@pytest.mark.parametrize('bad',['segments_sha','statement','schema','accepted_type','missing_audio'])
def test_malformed_listening_fails(timeline_run,bad):
    from video_ai.runtime.timeline_checks import plan_timeline
    run,config,store,data=timeline_run
    record=accept(run,data)
    if bad=='segments_sha':record['segments_identity']['sha256']='a'*64
    if bad=='statement':record['user_statement']=None
    if bad=='schema':record['schema_version']=True
    if bad=='accepted_type':record['accepted']=1
    if bad=='missing_audio':record['audio'].pop()
    (run/'voice-listening.json').write_text(json.dumps(record),encoding='utf-8')
    assert not plan_timeline(config,run_dir=run).passed


@pytest.mark.parametrize('existing',['lock','timeline','stage'])
def test_existing_state_refused(timeline_run,existing):
    from video_ai.runtime.timeline_checks import plan_timeline,TimelineRefusal
    run,config,store,data=timeline_run
    if existing=='lock':(run/'.timeline.lock').write_text('unknown owner')
    if existing=='timeline':(run/'timeline.json').write_text('orphan')
    if existing=='stage':store.record_stage('timeline','running');store.record_stage('timeline','failed')
    before=(run/'manifest.json').read_bytes()
    with pytest.raises(TimelineRefusal):plan_timeline(config,run_dir=run)
    assert (run/'manifest.json').read_bytes()==before
    if existing=='lock':assert (run/'.timeline.lock').read_text()=='unknown owner'


@pytest.mark.parametrize('when',['construct','drift','replace','before_commit','after_commit'])
def test_failure_and_interrupt_consistent(timeline_run,monkeypatch,when):
    from video_ai.runtime import timeline_checks as tc
    from video_ai.runtime.manifest import ManifestStore
    run,config,store,data=timeline_run
    if when=='construct':monkeypatch.setattr(tc,'build_timeline',lambda *a,**k: (_ for _ in ()).throw(ValueError('construction failure')))
    if when=='drift':
        original=tc.build_timeline
        def drift(*a,**kw):
            t=original(*a,**kw);Path(data['spans'][0]['pcm']['path']).write_bytes(b'changed after read');return t
        monkeypatch.setattr(tc,'build_timeline',drift)
    if when=='replace':
        original=tc.atomic_report
        def fail(path,data):
            if path.name=='timeline.json':raise OSError('replace failed')
            return original(path,data)
        monkeypatch.setattr(tc,'atomic_report',fail)
    if when.endswith('commit'):
        original=ManifestStore.record_stage
        def interrupt(self,stage,status,**kw):
            if stage=='timeline' and status=='completed':
                if when=='after_commit':original(self,stage,status,**kw)
                raise KeyboardInterrupt()
            return original(self,stage,status,**kw)
        monkeypatch.setattr(ManifestStore,'record_stage',interrupt)
        if when=='before_commit':
            with pytest.raises(KeyboardInterrupt):tc.plan_timeline(config,run_dir=run)
        else:assert tc.plan_timeline(config,run_dir=run).passed
    else:assert not tc.plan_timeline(config,run_dir=run).passed
    assert store.snapshot()['stages']['timeline']['status']==('completed' if when=='after_commit' else 'interrupted' if when=='before_commit' else 'failed')
    assert store.snapshot()['stages']['speech']['status']=='completed'
    assert not (run/'.timeline.lock').exists()
    if when=='before_commit':
        with pytest.raises(ValueError):tc.load_committed_timeline(run)


def test_committed_reader_rejects_artifact_drift(timeline_run):
    from video_ai.runtime.timeline_checks import plan_timeline,load_committed_timeline
    run,config,store,data=timeline_run
    assert plan_timeline(config,run_dir=run).passed
    (run/'timeline.json').write_bytes(b'changed')
    with pytest.raises((ValueError,OSError)):load_committed_timeline(run)


def test_interrupt_during_lock_cleanup_reports_durable_completion(timeline_run,monkeypatch):
    from video_ai.runtime.timeline_checks import plan_timeline
    run,config,store,data=timeline_run
    original=Path.unlink
    triggered=False
    def interrupt(path,*args,**kwargs):
        nonlocal triggered
        if path==run/'.timeline.lock' and not triggered:
            triggered=True;raise KeyboardInterrupt()
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',interrupt)
    try:result=plan_timeline(config,run_dir=run)
    except KeyboardInterrupt:pytest.fail('durable completion was incorrectly reported as interrupted')
    assert result.passed and store.snapshot()['stages']['timeline']['status']=='completed'
    assert not (run/'.timeline.lock').exists()


@pytest.mark.parametrize('interrupt',[False,True])
@pytest.mark.parametrize('operation',['exception','failure_report'])
def test_diagnostic_failure_preserves_original_terminal_state(timeline_run,monkeypatch,interrupt,operation):
    from video_ai.runtime import timeline_checks as tc
    from video_ai.runtime.logging import RunLogger
    run,config,store,data=timeline_run
    def broken(*a,**kw):
        if interrupt:raise KeyboardInterrupt()
        raise ValueError('original construction failure')
    monkeypatch.setattr(tc,'build_timeline',broken)
    def io_fail(*a,**kw):raise OSError('diagnostic file locked')
    if operation=='exception':monkeypatch.setattr(RunLogger,'exception',io_fail)
    else:monkeypatch.setattr(RunLogger,'save_json',io_fail)
    if interrupt:
        with pytest.raises(KeyboardInterrupt):tc.plan_timeline(config,run_dir=run)
    else:assert not tc.plan_timeline(config,run_dir=run).passed
    stage=store.snapshot()['stages']['timeline']
    assert stage['status']==('interrupted' if interrupt else 'failed')
    assert stage['error']['kind']==('KeyboardInterrupt' if interrupt else 'ValueError')
    assert not (run/'.timeline.lock').exists()


def test_schema2_refined_spans_rebuild_timeline(timeline_run):
    from video_ai.runtime.timeline_checks import plan_timeline,load_committed_timeline
    from video_ai.runtime.manifest import hash_file,thaw
    from test_speech_semantics import review_for
    run,config,store,data=timeline_run
    path=run/'logs/pipeline/unit-review.json';path.parent.mkdir(parents=True)
    review=review_for(data['decoded_text']);review['script_identity']=data['source']
    path.write_text(json.dumps(review),encoding='utf-8')
    data.update(schema_version=2,segmentation_identity=thaw(hash_file(path)),execution_policy=dict(
        gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300,
        tts_request_timeout_seconds=config.timeouts['tts_request']))
    rewrite_segments(run,store,data)
    result=plan_timeline(config,run_dir=run)
    assert result.passed and len(load_committed_timeline(run).clips)==3


def test_committed_timeline_rechecks_actual_pcm(timeline_run):
    from video_ai.runtime.timeline_checks import plan_timeline,load_committed_timeline
    run,config,store,data=timeline_run
    assert plan_timeline(config,run_dir=run).passed
    path=Path(data['spans'][0]['pcm']['path']);raw=bytearray(path.read_bytes());raw[-1]=1;path.write_bytes(raw)
    with pytest.raises((OSError,ValueError)):load_committed_timeline(run)
