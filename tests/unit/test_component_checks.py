from pathlib import Path
import pytest


def test_comfy_history_path_cannot_escape_owned_output(runtime_run):
    from video_ai.runtime.component_checks import output_path
    run=runtime_run[0]
    for metadata in (
        {'filename':'../injected.mp4','subfolder':'','type':'output'},
        {'filename':'file.mp4','subfolder':'../../escape','type':'output'},
        {'filename':'file.mp4','subfolder':'','type':'temp'},
    ):
        with pytest.raises(ValueError): output_path(run,metadata)


def test_video_validation_requires_exact_dimensions_and_frames():
    from video_ai.runtime.component_checks import validate_video_probe
    data={'streams':[{'codec_type':'video','width':1280,'height':720,'r_frame_rate':'16/1','nb_read_frames':'81','duration':'5.0625'}]}
    validate_video_probe(data,width=1280,height=720,frames=81,fps=16)
    with pytest.raises(ValueError): validate_video_probe(data,width=1920,height=1080,frames=81,fps=16)
    with pytest.raises(ValueError): validate_video_probe(data,width=1280,height=720,frames=80,fps=16)


def test_upscale_extraction_uses_supported_ffmpeg_frame_passthrough(runtime_run):
    import video_ai.runtime.component_checks as checks
    from types import SimpleNamespace
    class Extracted(Exception):pass
    def extract(*args):
        assert '-vsync' not in args, 'FFmpeg9 removed vsync'
        assert args[args.index('-fps_mode')+1]=='passthrough'
        raise Extracted()
    ctx=SimpleNamespace(run=runtime_run[0],previous_artifact=lambda *a:runtime_run[0]/'input.mp4',ffmpeg=extract)
    with pytest.raises(Extracted):checks.check_upscale(ctx)


def test_failed_component_is_evidenced_and_never_publishes(runtime_run,monkeypatch):
    import video_ai.runtime.component_checks as checks
    run,config,_=runtime_run
    def fail(context): raise OSError('real resource unavailable')
    monkeypatch.setattr(checks,'check_environment',fail)
    monkeypatch.setattr(checks,'scan_isolation',lambda config,**kwargs:{})
    result=checks.verify_components(config,run_dir=run,only='environment')
    assert result['passed'] is False
    assert result['components']['environment']['status']=='failed'
    assert 'real resource unavailable' in result['components']['environment']['error']
    assert (run/'component-report.json').exists()
    assert result['configuration_switched'] is False


def test_failure_is_logged_before_failure_isolation_scan(runtime_run,monkeypatch):
    import video_ai.runtime.component_checks as checks
    run,config,_=runtime_run
    calls=[]
    def scan(config,**kwargs):
        if calls:
            assert list((run/'logs/errors').glob('*.txt')), 'failure traceback delayed until after expensive scan'
        calls.append(True)
        return {}
    def fail(context):raise OSError('component failure')
    monkeypatch.setattr(checks,'scan_isolation',scan)
    monkeypatch.setattr(checks,'check_environment',fail)
    result=checks.verify_components(config,run_dir=run,only='environment')
    assert len(calls)==2
    assert result['components']['environment']['error']=='component failure'


def test_invalid_component_does_not_create_manifest(runtime_run):
    from video_ai.runtime.component_checks import verify_components
    run,config,_=runtime_run
    with pytest.raises(ValueError):verify_components(config,run_dir=run,only='made-up')
    assert not (run/'manifest.json').exists()


def test_snapshot_hashes_every_file_and_fails_on_unreadable_input(tmp_path,monkeypatch):
    import hashlib
    import video_ai.runtime.component_checks as checks
    files=[]
    for i in range(300):
        path=tmp_path/f'file-{i:04d}.bin'
        path.write_bytes(str(i).encode())
        files.append(path)
    identities=list(checks.snapshot_identities(iter(files)))
    assert [p for p,x in identities]==files
    assert [x.path for p,x in identities]==[str(x.resolve()) for x in files]
    assert [x.sha256 for p,x in identities]==[hashlib.sha256(str(i).encode()).hexdigest() for i in range(300)]
    original=checks.hash_file
    def unreadable(path):
        if path==files[257]:raise PermissionError('unreadable snapshot file')
        return original(path)
    monkeypatch.setattr(checks,'hash_file',unreadable)
    with pytest.raises(PermissionError,match='unreadable'):
        list(checks.snapshot_identities(iter(files)))


def test_partial_checks_cannot_switch_configuration(runtime_run,monkeypatch):
    import video_ai.runtime.component_checks as checks
    run,config,_=runtime_run
    monkeypatch.setattr(checks,'check_environment',lambda context:{'passed':True})
    monkeypatch.setattr(checks,'scan_isolation',lambda config,**kwargs:{})
    result=checks.verify_components(config,run_dir=run,only='environment')
    assert result['passed']
    assert result['configuration_switched'] is False


def test_reference_identity_uses_explicit_migration_mapping(runtime_run,run_store,monkeypatch):
    import hashlib
    import video_ai.runtime.component_checks as checks
    from video_ai.runtime.logging import RunLogger
    run,config,paths=runtime_run
    path=run/'reference-test.wav'
    path.write_bytes(b'fresh reference content')
    monkeypatch.setattr(checks,'read_json_list',lambda p:[{'source':'D:/old/voice_ref.wav','target':'historical descriptor','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}])
    monkeypatch.setattr(checks,'ROOTS',(('D:/old/voice_ref.wav',str(path.relative_to(paths.runtime_root)),'run'),))
    ctx=checks.CheckContext(config,run,paths,run_store,RunLogger(run),None,{})
    assert ctx.model('reference',path).bytes==23


def test_sdxl_and_wan_have_distinct_once_only_submission_units(runtime_run,run_store,monkeypatch):
    import video_ai.runtime.component_checks as checks
    from video_ai.runtime.logging import RunLogger
    from contextlib import nullcontext
    from types import SimpleNamespace
    run,config,paths=runtime_run
    logger=RunLogger(run)
    handle=object()
    manager=SimpleNamespace(stop=lambda h:None,release_comfy_models=lambda h:True)
    ctx=checks.CheckContext(config,run,paths,run_store,logger,manager,{})
    monkeypatch.setattr(checks.CheckContext,'owned_service',lambda self,name:handle)
    monkeypatch.setattr(checks.CheckContext,'model',lambda *a:SimpleNamespace(bytes=1,sha256='0'*64))
    monkeypatch.setattr(checks.CheckContext,'probe',lambda *a:{})
    monkeypatch.setattr(checks.CheckContext,'decode',lambda *a:None)
    monkeypatch.setattr(checks,'validate_video_probe',lambda *a,**k:None)
    monkeypatch.setattr(checks,'validate_png',lambda *a:None)
    monkeypatch.setattr(checks,'copy_verified',lambda *a,**k:None)
    monkeypatch.setattr(checks,'artifact',lambda p:{'path':str(p)})
    class Lease:
        def __init__(self,*a,**k):pass
        def acquire(self,*a,**k):return nullcontext()
    monkeypatch.setattr(checks,'GpuLease',Lease)
    units=[]
    def generated(ctx,component,replacements,*,unit_id,stage,timeout):
        assert unit_id not in units, 'components reused once-only unit'
        units.append(unit_id)
        return run/(component+'.test')
    monkeypatch.setattr(checks,'comfy_image',generated)
    checks.check_sdxl(ctx)
    checks.check_wan(ctx)


def test_tts_custom_must_match_voice_and_fallback_is_rejected(runtime_run):
    import video_ai.runtime.component_checks as checks
    from video_ai.runtime.manifest import thaw
    voice=runtime_run[1].voice
    custom=dict(version='v2',device='cpu',is_half=False,t2s_weights_path=str(voice.gpt_weights),
                vits_weights_path=str(voice.sovits_weights),bert_base_path=str(voice.bert_root),cnhuhbert_base_path=str(voice.hubert_root))
    checks.validate_tts_configuration({'custom':custom},voice)
    with pytest.raises(ValueError):checks.validate_tts_configuration({'custom':{**custom,'version':'v3'}},voice)
    with pytest.raises(OSError):checks.validate_tts_load_log('fall back to default t2s_weights_path: old.ckpt',voice)


def test_publication_refuses_missing_migration_receipt_and_changed_candidate(runtime_run):
    import video_ai.runtime.component_checks as checks
    from video_ai.runtime.manifest import hash_file
    run,config,paths=runtime_run
    report={'config_sha256':hash_file(config.config_file).sha256,
            'voice_sha256':hash_file(config.voice.config_file).sha256,'migration_receipt':None,
            'tts_config_sha256':None}
    with pytest.raises(OSError,match='migration'):
        checks.validate_publication(config,report)
    report['config_sha256']='0'*64
    with pytest.raises(OSError,match='candidate'):
        checks.validate_publication(config,report)


def test_subtitle_font_log_requires_loaded_migrated_font(runtime_run):
    import video_ai.runtime.component_checks as checks
    font=runtime_run[1].media.font_file
    log=f"Loading font file '{font}'\nfontselect: (Microsoft YaHei, 400, 0) -> MicrosoftYaHei, 0, MicrosoftYaHei\n"
    checks.validate_font_log(log,font)
    with pytest.raises(OSError):checks.validate_font_log('fontselect: Arial',font)
    with pytest.raises(OSError):checks.validate_font_log(log+'Glyph 0x591C not found',font)


def test_font_validation_ignores_unrelated_pcm_parser_warning(runtime_run):
    import video_ai.runtime.component_checks as checks
    font=runtime_run[1].media.font_file
    log=f"parser not found for codec pcm_s16le\nLoading font file '{font}'\nfontselect: (Microsoft YaHei, 400, 0) -> MicrosoftYaHei, 0, MicrosoftYaHei\n"
    checks.validate_font_log(log,font)


def test_comfy_submission_and_tracking_share_component_deadline(runtime_run,run_store,monkeypatch):
    import video_ai.runtime.component_checks as checks
    from video_ai.runtime.logging import RunLogger
    from types import SimpleNamespace
    run,config,paths=runtime_run
    clock=[0]
    monkeypatch.setattr(checks.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(checks.CheckContext,'model',lambda *a:None)
    class Client:
        def __init__(self,http,store,logger):self.http=http
        def validate_template(self,template):clock[0]=2
        def submit_once(self,graph,**kwargs):
            assert self.http.timeout==8
            clock[0]=3
            return object()
        def wait_for(self,submission,*,deadline_seconds):
            assert deadline_seconds==7
            return SimpleNamespace(outputs=({'filename':'result.png','subfolder':'','type':'output'},))
    monkeypatch.setattr(checks,'ComfyClient',Client)
    ctx=checks.CheckContext(config,run,paths,run_store,RunLogger(run),None,{})
    result=checks.comfy_image(ctx,'sdxl',{},unit_id='shot_0001',stage='start_images',timeout=10)
    assert result==run/'comfy/output/result.png'
