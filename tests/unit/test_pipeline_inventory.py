from copy import deepcopy
import pytest
from video_ai.runtime.pipeline_inventory import enrich_inventory
from video_ai.runtime.manifest import STAGES


def identity(path='D:/VideoSi/input.txt',sha='a'*64):
    return dict(path=path,bytes=1,sha256=sha,mtime_ns=1,verified_at='2026-10-05T00:00:00+00:00')


def fixture():
    snapshot={'stages':{s:{'status':'completed'} for s in STAGES},
        'units':{'speech':{},'image':{},'shot':{},'frame':{},'shot_attempt':{}},
        'config_snapshot':{'resolved':{'media':{'fps':16,'timeline':{'opening_seconds':2}},'tools':{}}},
        'voice_snapshot':{'resolved':{'speed_factor':1,'reference_text':'test','inference':{'top_k':5}}},
        'inputs':{'script':identity(),'reference':identity()},'models':{'gpt_weights':identity()},'workflows':{}}
    graph={'1':{'class_type':'LoadImage','inputs':{'image':'parent/input.png'}},
           '2':{'class_type':'Sampler','inputs':{'seed':12,'steps':20}},
           '3':{'class_type':'SaveImage','inputs':{'filename_prefix':'parent/output'}}}
    consumed={'speech':{'report':{'source':identity(),'spans':[
        {'kind':'speech','unit_id':'speech_0001','start':0,'end':4,'text':'test','boundary':'sentence',
         'pcm':identity(),'samples':4800,'status':'completed'}], 'models':{'gpt_weights':identity()}}},
      'timeline':{'output_fps':16,'effective_settings':{'opening_seconds':2},'clips':[
        {'unit_id':'speech_0001','text':'test','samples':4800,'pcm':identity()}]},
      'storyboard':{'global_visual':{'style':'natural'},'shots':[
        {'shot_id':'shot_0001','primary_unit_id':'speech_0001','bindings':[{'text':'test'}],
         'image_prompt':'scene','video_prompt':'motion','budget':{'required_native_frames':4},
         'visual_requirements':[{'quantity':'one','context_sources':[]}]}]},
      'start_images':{'images':[{'shot_id':'shot_0001','parameters':{'seed':12,'steps':20},
        'actual_graph':graph,'image_identity':identity(),'reference_entity_ids':['hero']}],
        'references':[{'entity_id':'hero','reference_shot_id':'shot_0001','identity':identity()}]},
      'source_clips':{'clips':[{'shot_id':'shot_0001','parameters':{'seed_high':4},'budget':{'required_native_frames':4},
        'start_image_identity':identity(),'attempts':[{'unit_id':'shot_0001:attempt_0001',
         'requested_frames':4,'actual_graph':graph,'actual_frames':4}]}]},
      'upscale':{'clips':[{'shot_id':'shot_0001','parameters':{'width':1920},'source_identity':identity(),
        'budget':{'required_native_frames':4},'frames':[{'frame_index':1,'source_frame_index':0,'actual_graph':graph,
          'input_identity':identity(),'output_identity':identity(),'parameters':{'width':1920}}]}]},
      'composition':{'settings':{'font_size':54},'plan':{'ordered_frame_map':[{'contributors':[
         {'shot_id':'shot_0001','weight_numerator':1}]}],'subtitle_events':[{'text':'test'}]},
         'provenance':{'font_identity':identity(),'music_identity':None,'ffmpeg_identity':identity()}},
      'validation':{'candidate_identity':identity(),'subtitle_identity':identity()}}
    return snapshot,consumed


def test_enrichment_preserves_stable_units_and_formal_dependencies():
    snapshot,consumed=fixture();units,signatures=enrich_inventory(snapshot,consumed,{})
    assert units['storyboard']['shot_0001']['visual_requirements'][0]['quantity']=='one'
    assert units['start_images']['shot_0001']['reference_index'][0]['entity_id']=='hero'
    assert 'shot_0001:frame_000001' in units['upscale']
    assert signatures['upscale']['shot_0001:frame_000001']
    assert list(signatures)==list(STAGES)


@pytest.mark.parametrize('retry',[False,True])
def test_coordinator_first_tts_lost_response_has_durable_unknown_and_zero_repost(runtime_run,monkeypatch,retry):
    """Real TtsClient/HttpClient/manifest evidence; transport fails without a model."""
    import json
    from video_ai import pipeline
    from video_ai.adapters.common import HttpClient,AdapterError
    from video_ai.adapters.tts import TtsClient
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.runtime import pipeline_inventory,pipeline_stages
    run,config,paths=runtime_run
    store=create_manifest(run,config,inputs={'config':hash_file(config.config_file),'voice':hash_file(config.voice.config_file)},models={},workflows={})
    logger=RunLogger(run);store.record_stage('speech','running');store.record_unit('speech','reference_replay','running')
    def lost(request,**kwargs):raise TimeoutError('TEST ONLY first TTS response lost')
    tts=TtsClient(HttpClient(config.services['tts'],2,logger,transport=lost),config.voice)
    intent=logger.save_json('tts/reference_replay.intent.json',dict(unit_id='reference_replay',text=config.voice.reference_text,
        payload=tts.payload(config.voice.reference_text),voice_sha256=hash_file(config.voice.config_file).sha256,created_at=now(),automatic_retry=False))
    store.update(lambda data:data['events'].append(dict(time=now(),stage='speech',unit_id='reference_replay',action='tts_intent',evidence_paths=[str(intent)])))
    with pytest.raises(AdapterError) as error:tts.synthesize(config.voice.reference_text,unit_id='reference_replay')
    trace=logger.exception('speech','reference_replay',error.value)
    failure=dict(kind='ambiguous',message=str(error.value),traceback_path=str(trace),evidence_paths=[str(trace),*[str(p) for p in error.value.evidence_paths]])
    store.record_unit('speech','reference_replay','ambiguous',error=failure);store.record_stage('speech','ambiguous',error=failure)
    before=store.snapshot();original=(run/'manifest.json').read_bytes()
    def projection(config,identities):
        value=thaw(config);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',projection)
    def forbidden(*a,**k):raise AssertionError('durable lost first TTS request cannot generate or derive')
    monkeypatch.setattr(pipeline_stages,'prepare',forbidden)
    from video_ai.runtime import pipeline_import
    monkeypatch.setattr(pipeline_import,'derive_run',forbidden)
    plan=pipeline.plan_resume(config,run_dir=run,retry_failed=retry)
    assert not plan.requires_child_run
    assert any(op.action=='reconcile' and op.unit_id=='reference_replay' for op in plan.operations)
    with pytest.raises(pipeline.PipelineRefusal,match='lost response remains unknown'):
        pipeline.resume_pipeline(config,run_dir=run,retry_failed=retry)
    diagnostic=[json.loads(p.read_text()) for p in (run/'logs/pipeline').glob('diagnostic-*.json')]
    assert any(row.get('reconciliation',{}).get('state')=='unresolved' for row in diagnostic)
    assert store.snapshot()==before and (run/'manifest.json').read_bytes()==original
    assert len(list((run/'logs/http').glob('*.request.json')))==1


@pytest.mark.parametrize('response_kind',['http400','bad_wav','short_frames','empty_frames','short_fmt','truncated','lost','valid_wav'])
def test_tts_complete_failure_proof_separates_final_response_from_unknown(runtime_run,response_kind):
    import io,json,wave
    from video_ai.runtime.manifest import create_manifest,hash_file,now,thaw
    from video_ai.runtime.logging import RunLogger
    from video_ai.adapters.common import HttpClient,AdapterError
    from video_ai.adapters.tts import TtsClient
    from video_ai.runtime.pipeline_inventory import unknown_tts_intents
    run,config,_=runtime_run;store=create_manifest(run,config,inputs={},models={},workflows={});logger=RunLogger(run)
    store.record_stage('speech','running');store.record_unit('speech','reference_replay','running')
    raw=b'complete non-WAV body'
    if response_kind in ('valid_wav','short_frames','empty_frames'):
        with io.BytesIO() as data:
            with wave.open(data,'wb') as wav:wav.setparams((1,2,24000,0,'NONE',''));wav.writeframes(b'\0\0'*(0 if response_kind=='empty_frames' else 6000))
            raw=data.getvalue()
        if response_kind=='short_frames':raw=raw[:-100]
    if response_kind=='short_fmt':raw=b'RIFF'+(18).to_bytes(4,'little')+b'WAVEfmt '+(16).to_bytes(4,'little')+b'\x01\x00'
    class Response(io.BytesIO):
        status=400 if response_kind=='http400' else 200
        headers={'Content-Type':'application/json' if response_kind=='http400' else 'audio/wav'}
        def geturl(self):return config.services['tts']+'/tts'
    def transport(*a,**k):
        if response_kind=='lost':raise TimeoutError('TEST ONLY lost response')
        response=Response(b'{"detail":"TEST ONLY rejected"}' if response_kind=='http400' else raw)
        if response_kind=='truncated':response.headers=dict(response.headers,**{'Content-Length':str(len(raw)+100)})
        return response
    tts=TtsClient(HttpClient(config.services['tts'],2,logger,transport=transport),config.voice)
    intent=logger.save_json('tts/reference_replay.intent.json',dict(unit_id='reference_replay',text=config.voice.reference_text,
        payload=tts.payload(config.voice.reference_text),voice_sha256=hash_file(config.voice.config_file).sha256,created_at=now(),automatic_retry=False))
    store.update(lambda data:data['events'].append(dict(time=now(),stage='speech',unit_id='reference_replay',action='tts_intent',evidence_paths=[str(intent)])))
    if response_kind in ('valid_wav','short_frames','empty_frames','short_fmt'):
        response=tts.synthesize(config.voice.reference_text,unit_id='reference_replay')
        if response_kind!='valid_wav':
            from video_ai.media.audio import standardize_wav,SpeechLimits
            raw_path=run/'audio/reference_replay/raw.wav';raw_path.parent.mkdir(parents=True);raw_path.write_bytes(response.body)
            with pytest.raises((ValueError,EOFError)):
                standardize_wav(raw_path,raw_path.parent/'pcm-48000.wav',config=config,paths=runtime_run[2],logger=logger,unit_id='reference_replay',limits=SpeechLimits())
    else:
        with pytest.raises(AdapterError):tts.synthesize(config.voice.reference_text,unit_id='reference_replay')
    trace=logger.exception('speech','reference_replay',ValueError('TEST ONLY failed native TTS response'))
    store.record_unit('speech','reference_replay','failed',error=dict(kind='failed',message='TEST ONLY failed native TTS response',traceback_path=str(trace),
        evidence_paths=[] if response_kind in ('short_frames','empty_frames','short_fmt') else [str(trace)]))
    before=store.snapshot();unknown=unknown_tts_intents(before,run_dir=run)
    if response_kind in ('http400','bad_wav','short_frames','empty_frames'):
        assert not unknown
        from video_ai.runtime.pipeline_inventory import classify_tts_intents
        _,failed=classify_tts_intents(before,run_dir=run)
        assert set(failed)=={'reference_replay'} and failed['reference_replay']['evidence_identities']
        request=next((run/'logs/http').glob('*.request.json'));data=json.loads(request.read_text());data['json_body']['text']='altered text';request.write_text(json.dumps(data))
        assert unknown_tts_intents(before,run_dir=run)
    else:assert set(unknown)=={'reference_replay'}
    assert store.snapshot()==before


def test_copied_identity_path_and_run_graph_names_do_not_change_equivalence():
    snapshot,consumed=fixture();_,original=enrich_inventory(snapshot,consumed,{})
    copied=deepcopy(consumed)
    for stage,field in [('start_images','images'),('source_clips','clips'),('upscale','clips')]:
        row=copied[stage][field][0]
        target=row if stage=='start_images' else row['attempts'][0] if stage=='source_clips' else row['frames'][0]
        target['actual_graph']['1']['inputs']['image']='child/input.png'
        target['actual_graph']['3']['inputs']['filename_prefix']='child/output'
    copied['speech']['report']['source']['path']='D:/VideoSi/copy.txt'
    copied['start_images']['images'][0]['image_identity']['path']='D:/VideoSi/copy.png'
    _,derived=enrich_inventory(snapshot,copied,{})
    for stage in ('speech','start_images','source_clips','upscale'):
        assert original[stage]==derived[stage]


def test_all_actual_graph_sampling_parameters_influence_signature():
    snapshot,consumed=fixture();_,original=enrich_inventory(snapshot,consumed,{})
    changed=deepcopy(consumed);changed['source_clips']['clips'][0]['attempts'][0]['actual_graph']['2']['inputs']['steps']=21
    _,modified=enrich_inventory(snapshot,changed,{})
    assert original['source_clips']!=modified['source_clips']


def test_voice_parameters_weight_and_actual_span_changes_influence_speech():
    snapshot,consumed=fixture();_,original=enrich_inventory(snapshot,consumed,{})
    snapshot['voice_snapshot']['resolved']['speed_factor']=1.1
    _,modified=enrich_inventory(snapshot,consumed,{})
    assert original['speech']!=modified['speech']


def test_pcm_sample_count_cue_budget_and_full_subtitle_plan_influence_signatures():
    snapshot,consumed=fixture();_,original=enrich_inventory(snapshot,consumed,{})
    consumed['timeline']['clips'][0]['samples']=4801
    consumed['upscale']['clips'][0]['budget']['required_native_frames']=5
    consumed['composition']['plan']['subtitle_events'][0]['text']='changed'
    _,modified=enrich_inventory(snapshot,consumed,{})
    for stage in ('timeline','upscale','composition'):
        assert original[stage]!=modified[stage]


def test_running_draft_is_enriched_from_validated_checkpoint_only():
    snapshot,consumed=fixture();draft=consumed.pop('start_images')
    units,signatures=enrich_inventory(snapshot,consumed,{'start_images':{'draft_complete':True,'report':draft}})
    assert units['start_images']['shot_0001']['parameters']['seed']==12
    assert signatures['start_images']['shot_0001']


def test_complete_timeline_pcm_paths_in_composition_normalize_by_content():
    snapshot,consumed=fixture()
    consumed['timeline']['clips'][0]['pcm'].update(samples=4800,sample_rate=48000)
    _,original=enrich_inventory(snapshot,consumed,{})
    consumed['timeline']['clips'][0]['pcm']['path']='D:/VideoSi/copied.wav'
    _,copied=enrich_inventory(snapshot,consumed,{})
    assert original['composition']==copied['composition']


def test_bound_actual_graph_replayed_and_late_identity_drift_refuses(tmp_path):
    import json
    import pytest
    from video_ai.runtime.manifest import hash_file,thaw
    snapshot,consumed=fixture()
    row=consumed['start_images']['images'][0]
    graph=row.pop('actual_graph');path=tmp_path/'actual-graph.json'
    path.write_text(json.dumps(graph),encoding='utf-8')
    row['submission']={'attempt_id':'attempt','intent_identity':thaw(hash_file(path))}
    _,signatures=enrich_inventory(snapshot,consumed,{})
    assert signatures['start_images']['shot_0001']
    graph['2']['inputs']['seed']=99;path.write_text(json.dumps(graph),encoding='utf-8')
    with pytest.raises(ValueError,match='identity drift'):
        enrich_inventory(snapshot,consumed,{})


def test_bound_complete_composition_plan_content_replayed(tmp_path):
    import json
    from video_ai.runtime.manifest import hash_file,thaw
    snapshot,consumed=fixture();row=consumed['composition'];plan=row.pop('plan')
    path=tmp_path/'composition-plan.json';path.write_text(json.dumps(plan),encoding='utf-8')
    row['plan_identity']=thaw(hash_file(path))
    _,original=enrich_inventory(snapshot,consumed,{})
    plan['subtitle_events'][0]['text']='new';path.write_text(json.dumps(plan),encoding='utf-8')
    row['plan_identity']=thaw(hash_file(path))
    _,modified=enrich_inventory(snapshot,consumed,{})
    assert original['composition']!=modified['composition']


def test_unknown_graph_string_with_run_prefix_does_not_normalize():
    snapshot,consumed=fixture();_,original=enrich_inventory(snapshot,consumed,{})
    consumed['start_images']['images'][0]['actual_graph']['2']['inputs']['positive']='child/run description'
    _,modified=enrich_inventory(snapshot,consumed,{})
    assert original['start_images']!=modified['start_images']


def test_semantic_config_declared_file_relocation_preserves_content_and_all_other_fields(tmp_path):
    from video_ai.runtime.pipeline_inventory import config_projection
    from video_ai.planning.recovery import signature
    first=tmp_path/'first.bin';second=tmp_path/'second.bin';first.write_bytes(b'model');second.write_bytes(b'model')
    config={'models':{'upscale':str(first)},'tools':{},'workflows':{},'media':{},'voice':{},
        'services':{'comfyui':'http://localhost:8188'},'unknown_future':{'semantic_parameter':12}}
    ids={};old=config_projection(config,ids)
    assert ids and old['unknown_future']==config['unknown_future']
    config['models']['upscale']=str(second)
    new=config_projection(config,{})
    assert signature(old)==signature(new)


def test_voice_directory_content_set_addition_refused_against_captured_inventory(tmp_path):
    import pytest
    from video_ai.runtime.pipeline_inventory import config_projection
    root=tmp_path/'model';root.mkdir();(root/'weights.bin').write_bytes(b'weights')
    config={'models':{},'tools':{},'workflows':{},'media':{},'voice':{'bert_root':str(root)}}
    ids={};config_projection(config,ids)
    (root/'extra.bin').write_bytes(b'unexpected new weight')
    with pytest.raises(ValueError,match='file set changed'):config_projection(config,ids)
