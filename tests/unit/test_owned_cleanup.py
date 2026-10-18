"""Native cleanup fault injection with isolated runs and no model or service work."""
from pathlib import Path
from types import SimpleNamespace
import json
import pytest


def native_call(runtime_run,monkeypatch,stage,original,*,stop_failure=True,diagnostic_failure=False):
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime import _upscale_generation as upscale,_source_clip_generation as source,start_image_checks as images,storyboard_checks as board
    module={'upscale':upscale,'source_clips':source,'start_images':images,'storyboard':board}[stage]
    run,config,_=runtime_run;logger=RunLogger(run);stops=[]
    handle=SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:None))
    class Manager:
        def __init__(self,*a,**k):pass
        def ensure(self,*a):return handle
        def stop(self,actual):
            assert actual is handle;stops.append(actual)
            if stop_failure:raise OSError('TEST ONLY owned stop failed')
    monkeypatch.setattr(module,'ServiceManager',Manager)
    monkeypatch.setattr(module,'build_service_specs',lambda *a:{'comfyui':object(),'ollama':object()})
    if diagnostic_failure:
        def log_failed(*a,**k):raise OSError('TEST ONLY cleanup diagnostic failed')
        monkeypatch.setattr(logger,'exception',log_failed)
    def interrupt(*a,**k):
        if original is not None:raise original
    class InterruptedPlans:
        def __iter__(self):
            if original is not None:raise original
            return iter(())
    if stage=='upscale':
        call=lambda:upscale.generate(config,run,None,logger,{'plans':(),'source':{'clips':()},'identities':{}}, {},[],before_generate=interrupt)
    elif stage=='source_clips':
        store=SimpleNamespace(snapshot=lambda:{'workflows':{}})
        call=lambda:source.generate(config,run,store,logger,{'plans':InterruptedPlans(),'identities':{}}, {},[])
    elif stage=='start_images':
        from video_ai.runtime.manifest import create_manifest
        create_manifest(run,config,inputs={},models={},workflows={})
        model=run/'TEST-ONLY-model.bin';model.write_bytes(b'TEST ONLY never loaded')
        monkeypatch.setattr(images,'_revision',lambda *a:None)
        monkeypatch.setattr(images,'_model',lambda *a:(hash_file(model),{}))
        monkeypatch.setattr(images,'_directions',lambda *a:({},{}))
        template=SimpleNamespace(graph={'1':{'class_type':'KSampler','inputs':dict(steps=25,cfg=7,sampler_name='dpmpp_2m',scheduler='karras',denoise=1)},
            '2':{'class_type':'EmptyLatentImage','inputs':dict(batch_size=1)}})
        monkeypatch.setattr(images,'_template',lambda *a:template)
        call=lambda:images._generate_owned(config,run,None,logger,{},InterruptedPlans(),768,432,{})
    else:
        monkeypatch.setattr(board,'_model_files',lambda *a:{})
        monkeypatch.setattr(board,'HttpClient',interrupt)
        call=lambda:board._generate_owned(config,run,None,logger,())
    return call,stops,run


@pytest.mark.parametrize('stage',['upscale','source_clips','start_images','storyboard'])
@pytest.mark.parametrize('exception',[KeyboardInterrupt,SystemExit,ValueError])
@pytest.mark.parametrize('diagnostic_failure',[False,True])
def test_native_owned_cleanup_preserves_original_exception(runtime_run,monkeypatch,stage,exception,diagnostic_failure):
    original=exception('TEST ONLY original generation failure')
    call,stops,run=native_call(runtime_run,monkeypatch,stage,original,diagnostic_failure=diagnostic_failure)
    with pytest.raises(exception) as error:call()
    assert error.value is original and len(stops)==1
    if not diagnostic_failure:
        logs=list((run/'logs/errors').glob('*.txt'))
        assert any('TEST ONLY owned stop failed' in path.read_text() for path in logs)


@pytest.mark.parametrize('stage',['upscale','source_clips','start_images'])
def test_unconfirmed_shutdown_does_not_replace_native_interrupt(runtime_run,monkeypatch,stage):
    original=KeyboardInterrupt('TEST ONLY original interruption')
    call,stops,_=native_call(runtime_run,monkeypatch,stage,original,stop_failure=False)
    with pytest.raises(KeyboardInterrupt) as error:call()
    assert error.value is original and len(stops)==1


def test_native_owned_stop_fault_reaches_cli_as_original_interrupt_130(runtime_run,monkeypatch,capsys):
    from video_ai import pipeline
    from video_ai.cli import main
    original=KeyboardInterrupt('TEST ONLY original generation interruption')
    call,stops,run=native_call(runtime_run,monkeypatch,'upscale',original,diagnostic_failure=True)
    monkeypatch.setattr(pipeline,'resume_pipeline',lambda *a,**k:call())
    assert main(['resume','--config',str(runtime_run[1].config_file),'--run-dir',str(run),'--json'])==130
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='interrupted' and len(stops)==1 and not result['published']


@pytest.mark.parametrize('stage',['upscale','source_clips','start_images'])
@pytest.mark.parametrize('stop_failure',[False,True])
def test_normal_native_stop_failure_cannot_report_success(runtime_run,monkeypatch,stage,stop_failure):
    call,stops,_=native_call(runtime_run,monkeypatch,stage,None,stop_failure=stop_failure,diagnostic_failure=True)
    with pytest.raises(OSError,match='owned stop failed|shutdown unconfirmed'):call()
    assert len(stops)==1


@pytest.mark.parametrize('exception',[KeyboardInterrupt,SystemExit,OSError])
def test_service_start_cleanup_and_error_receipts_cannot_replace_original(runtime_run,run_store,monkeypatch,exception):
    from video_ai.runtime import services as module
    from video_ai.runtime.logging import RunLogger
    from video_ai.adapters.common import AdapterError,FailureKind
    run,config,paths=runtime_run;logger=RunLogger(run);manager=module.ServiceManager(paths,run_store,logger)
    original=exception('TEST ONLY original startup failure');stops=[];launched=[]
    def unavailable(*a):raise AdapterError(FailureKind.unavailable,'TEST ONLY closed port')
    monkeypatch.setattr(manager,'_health',unavailable)
    monkeypatch.setattr(module,'port_listening',lambda *a:False)
    process=SimpleNamespace(pid=4321,returncode=None,poll=lambda:None)
    def launch(*a,**k):launched.append(process);return process
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    def record(*a,**k):raise original
    monkeypatch.setattr(manager,'_record',record)
    def stop(actual):assert actual is process;stops.append(actual);raise OSError('TEST ONLY cleanup stop failure')
    monkeypatch.setattr(module,'stop_process',stop)
    native_exception=logger.exception
    def diagnostic(*a):
        if launched:raise OSError('TEST ONLY diagnostic disk failure')
        return native_exception(*a)
    monkeypatch.setattr(logger,'exception',diagnostic)
    spec=module.ServiceSpec('comfyui',config.services['comfyui'],(str(config.tools['comfy_python']),'-c','pass'),run,10)
    expected=module.ServiceStartError if exception is OSError else exception
    with pytest.raises(expected) as error:manager.ensure(spec)
    assert (error.value.__cause__ if exception is OSError else error.value) is original
    assert stops==[process] and not manager._streams
