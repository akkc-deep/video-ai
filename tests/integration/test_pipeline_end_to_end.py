"""TEST ONLY real HTTP/WAV/FFmpeg and real publication transaction boundaries."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from pipeline_helpers import unit_review,review_index,tts_server,write,patch_committed_upstream


def test_new_pipeline_actual_http_pcm_stops_for_voice_with_one_manifest(runtime_run,monkeypatch):
    from video_ai.config import load_config
    from video_ai import pipeline
    from video_ai.runtime import speech_checks as speech
    from video_ai.runtime import preflight as pf
    from video_ai.runtime import pipeline_inventory
    def isolated_projection(config,identities):
        value=thaw(config);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',isolated_projection)
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime.paths import RuntimePaths
    parent,original,paths=runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    script=parent/'TEST-ONLY-input.txt';script.write_text('一只红鸟，飞过蓝湖。',encoding='utf-8')
    review=unit_review(script,parent/'TEST-ONLY-units.json')
    with tts_server() as (url,requests):
        raw=thaw(original.raw);raw['voice_config']=str(original.voice.config_file)
        raw['services']['tts']=url
        raw['workflows']={k:str(v) for k,v in original.workflows.items()}
        raw['tools']={k:str(actual.tools[k]) if k in ('ffmpeg','ffprobe') else str(v) for k,v in original.tools.items()}
        config=load_config(write(parent/'TEST-ONLY-config.json',raw))
        monkeypatch.setattr(pf,'preflight',lambda *a,**k:pf.PreflightReport((pf.PreflightCheck('TEST ONLY',True,'service fixture'),)))
        monkeypatch.setattr(speech,'freeze_inputs',lambda cfg,src:({k:hash_file(p) for k,p in
            dict(script=src,config=cfg.config_file,voice=cfg.voice.config_file).items()},{}))
        monkeypatch.setattr(speech,'scan_isolation',lambda *a,**k:{})
        monkeypatch.setattr(speech,'validate_voice_startup',lambda *a,**k:None)
        monkeypatch.setattr(speech,'validate_fixed_voice_log',lambda *a,**k:None)
        monkeypatch.setattr(speech,'service_log',lambda *a,**k:'TEST ONLY')
        monkeypatch.setattr(speech,'build_service_specs',lambda *a,**k:{'tts':object()})
        class Manager:
            def __init__(self,*a):self.owned_pids=set()
            def ensure(self,*a):return SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:None))
            def stop(self,*a):pass
        monkeypatch.setattr(speech,'ServiceManager',Manager)
        monkeypatch.setattr(speech,'ResourceSampler',lambda *a,**k:pytest.fail('new pipeline sampled GPU'),raising=False)
        calls=[]; create=pipeline.create_manifest
        def create_once(*a,**k):calls.append(a[0]);return create(*a,**k)
        monkeypatch.setattr(pipeline,'create_manifest',create_once)
        result=pipeline.run_pipeline(config,script=script,unit_review_path=review)
    assert result.status=='awaiting_review' and result.waiting_for==('voice_acceptance',)
    assert len(calls)==1
    segments=json.loads((result.run_dir/'segments.json').read_text(encoding='utf-8'))
    assert segments['schema_version']==2 and segments['execution_policy']['gpu_management']=='disabled'
    assert [r['text'] for r in requests][1:]==['一只红鸟，','飞过蓝湖。']
    assert segments['total_speech_samples']==48000
    assert (result.run_dir/'audio/listening-preview.wav').is_file()
    assert not json.loads((result.run_dir/'voice-listening.json').read_text())['accepted']
    import os,subprocess,sys
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(Path(__file__).resolve().parents[2]/'src'))
    probe=subprocess.run([sys.executable,'-B','-c',
        'import sys; from pathlib import Path; from video_ai.runtime.pipeline_evidence import load_pipeline_result; '
        'from video_ai.runtime.speech_checks import load_committed_speech; '
        'audit=load_pipeline_result(Path(sys.argv[1])); speech=load_committed_speech(Path(audit["result"]["run_dir"])); '
        'print(audit["result"]["status"],speech["accepted"])',str(result.report_path)],
        cwd=result.run_dir/'logs',env=env,capture_output=True,text=True,timeout=300)
    assert probe.returncode==0,probe.stderr
    assert probe.stdout.strip()=='awaiting_review False'


@pytest.mark.parametrize('fps',[16,24])
def test_candidate_transaction_is_real_and_default_resume_keeps_staging(runtime_run,monkeypatch,fps):
    from candidate_helpers import make_candidate_fixture
    from video_ai.pipeline import resume_pipeline
    from video_ai.runtime.pipeline_evidence import load_pipeline_result
    run,config,store,composition=make_candidate_fixture(runtime_run,monkeypatch,fps=fps)
    patch_committed_upstream(monkeypatch,composition)
    result=resume_pipeline(config,run_dir=run)
    assert result.status=='candidate_ready'
    assert store.snapshot()['stages']['validation']['status']=='completed'
    assert store.snapshot()['stages']['publish']['status']=='pending'
    assert not (config.output_root/(run.name+'.mp4')).exists()
    audit=load_pipeline_result(result.report_path)
    assert audit['validation']['full_film_acceptance']=='unverified'
    assert resume_pipeline(config,run_dir=run).status=='awaiting_acceptance'


def test_explicit_pipeline_publication_preserves_accepted_bytes_and_new_consumer(runtime_run,monkeypatch):
    from publication_helpers import make_publication_fixture,cleanup_output
    from video_ai.pipeline import resume_pipeline
    from video_ai.runtime.pipeline_evidence import load_pipeline_result
    run,config,store,review,acceptance=make_publication_fixture(runtime_run,monkeypatch)
    composition=json.loads((run/'composition.json').read_text(encoding='utf-8'))
    patch_committed_upstream(monkeypatch,composition)
    index=review_index(run,{'final_review':review,'full_film_acceptance':acceptance})
    try:
        assert resume_pipeline(config,run_dir=run,reviews_path=index).status=='awaiting_acceptance'
        result=resume_pipeline(config,run_dir=run,reviews_path=index,publish=True)
        assert result.published and result.status=='published'
        assert result.candidate_path.read_bytes()==(run/'staging/composition/candidate.mp4').read_bytes()
        assert result.subtitle_path.read_bytes()==(run/'staging/composition/subtitle.srt').read_bytes()
        assert load_pipeline_result(result.report_path)['validation']['full_film_acceptance']=='passed'
    finally:cleanup_output(config,run)


def test_explicit_publish_missing_acceptance_calls_original_refusal(runtime_run,monkeypatch):
    from candidate_helpers import make_candidate_fixture
    from video_ai.pipeline import resume_pipeline
    run,config,store,composition=make_candidate_fixture(runtime_run,monkeypatch)
    patch_committed_upstream(monkeypatch,composition)
    resume_pipeline(config,run_dir=run)
    before=(run/'manifest.json').read_bytes()
    with pytest.raises(ValueError):resume_pipeline(config,run_dir=run,publish=True)
    assert (run/'manifest.json').read_bytes()==before
    assert list((run/'logs/publication').glob('diagnostic-*.json'))


def test_default_resume_rejects_supplied_stale_final_author_record_without_publication(runtime_run,monkeypatch):
    from publication_helpers import make_publication_fixture,cleanup_output
    from video_ai.pipeline import resume_pipeline
    run,config,store,review,acceptance=make_publication_fixture(runtime_run,monkeypatch)
    composition=json.loads((run/'composition.json').read_text(encoding='utf-8'))
    patch_committed_upstream(monkeypatch,composition)
    data=json.loads(acceptance.read_text(encoding='utf-8'))
    data['candidate_identity']['sha256']='a'*64
    write(acceptance,data)
    index=review_index(run,{'final_review':review,'full_film_acceptance':acceptance})
    before=(run/'manifest.json').read_bytes()
    try:
        with pytest.raises(ValueError):resume_pipeline(config,run_dir=run,reviews_path=index)
        assert (run/'manifest.json').read_bytes()==before
        assert not (config.output_root/(run.name+'.mp4')).exists()
    finally:cleanup_output(config,run)


def test_voice_author_index_continues_real_timeline_without_rewriting_listening(timeline_run,monkeypatch):
    from unit.test_pipeline_reviews import complete_voice_fixture
    from video_ai.pipeline import resume_pipeline
    run,config,store,data,path,record=complete_voice_fixture(timeline_run)
    # This fixture's manifest deliberately contains no model provenance. Test
    # real author/PCM/timeline behavior without hashing unrelated installed models.
    from video_ai.runtime import pipeline_inventory
    from video_ai.runtime.manifest import thaw
    def fixture_projection(config,identities):
        value=thaw(config);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',fixture_projection)
    false=run/'voice-listening.json'
    false.write_text(json.dumps(dict(schema_version=1,listened=False,accepted=False,
        audio=[{k:s[k] for k in ('unit_id','text','pcm','samples')} for s in data['spans'] if s['kind']=='speech'])),encoding='utf-8')
    before=false.read_bytes()
    result=resume_pipeline(config,run_dir=run,reviews_path=review_index(run,{'voice_acceptance':path}))
    assert result.status=='awaiting_review' and result.waiting_for==('timing',)
    assert store.snapshot()['stages']['timeline']['status']=='completed'
    assert false.read_bytes()==before
