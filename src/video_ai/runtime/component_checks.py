"""Migration-only component verification, preserving failures and ownership."""
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from itertools import islice
import json
import os
from pathlib import Path
import struct
import sys
import time
import wave
from uuid import uuid4

from ..adapters.common import HttpClient, AdapterError, JSON_LIMIT
from ..adapters.comfyui import ComfyClient
from ..config import read_json
from .environment import build_child_env
from .logging import RunLogger
from .manifest import create_manifest, hash_file, thaw, validate_run_dir, now
from .migration import atomic_report, CopyEntry, copy_verified, scan_files, ROOTS
from .paths import PathPolicy, RuntimePaths, SOURCE_ROOT, RUNTIME_ROOT
from .processes import run_logged
from .resources import GpuLease, ResourceSampler
from .service_specs import build_service_specs
from .services import ServiceManager, ServiceConflictError
from .workflows import WorkflowTemplate, safe_comfy_path
from .gpu_desktop import desktop_policy

COMPONENTS=('environment','ollama','tts','sdxl','wan','upscale','media')
INVENTORY=RUNTIME_ROOT/'docs/video-ai/VAI-01-inventory'


def output_path(run_dir, metadata):
    if metadata.get('type')!='output':
        raise ValueError('expected owned Comfy output')
    filename=metadata.get('filename')
    safe_comfy_path(filename)
    if Path(filename).name!=filename:
        raise ValueError('output filename must be basename')
    folder=safe_comfy_path(metadata.get('subfolder'),allow_empty=True)
    root=validate_run_dir(run_dir)/'comfy/output'
    path=PathPolicy().validate_write(root/folder/filename,'run')
    if not path.is_relative_to(root):
        raise ValueError('history path escaped owned output')
    return path


def validate_video_probe(data, *, width, height, frames, fps):
    streams=[s for s in data.get('streams',[]) if s.get('codec_type')=='video']
    if len(streams)!=1:
        raise ValueError('expected one video stream')
    video=streams[0]
    if (video.get('width'),video.get('height'))!=(width,height):
        raise ValueError('video dimensions mismatch')
    if Fraction(video['r_frame_rate'])!=fps or int(video['nb_read_frames'])!=frames:
        raise ValueError('video rate/frame count mismatch')
    if abs(float(video['duration'])-frames/fps)>.1:
        raise ValueError('video duration mismatch')


def snapshot_identities(files):
    """Bounded parallel reads, preserving every input path and raising any error."""
    files=iter(files)
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix='isolation-read') as executor:
        while batch:=tuple(islice(files,256)):
            for path,identity in zip(batch,executor.map(hash_file,batch)):
                yield path,identity


def scan_isolation(config, *, logger=None):
    """Full content hashes; failure to read any file prevents an isolation claim."""
    result={}
    roots=(config.tools['comfy_root'].parent,config.tools['tts_root'],config.tools['ffmpeg'].parent.parent,
           config.tools['ollama_executable'].parent,config.project_root/'config',SOURCE_ROOT,
           RUNTIME_ROOT/'models',Path('C:/Users/qzw19/.cache'),Path('C:/Users/qzw19/.ollama'),
           Path('C:/Users/qzw19/.matplotlib'),Path('C:/Users/qzw19/.triton'),
           Path('C:/Users/qzw19/AppData/Local/NVIDIA/ComputeCache'),
           Path('C:/Users/qzw19/AppData/Roaming/nltk_data'),
           Path('C:/Users/qzw19/AppData/Local/Temp/torch_extensions'))
    total_bytes=0
    started=time.monotonic()
    def progress(event,root):
        if logger is not None:
            logger.event('validation',None,event,dict(root=str(root),files=len(result),
                         bytes=total_bytes,elapsed_seconds=time.monotonic()-started))
    for root in roots:
        if not root.is_dir():
            continue
        progress('isolation_root_started',root)
        def fail(exc):raise exc
        def inputs():
            for directory,dirs,files in os.walk(root,onerror=fail):
                if root==SOURCE_ROOT:
                    dirs[:]=[d for d in dirs if d not in ('.venv','.idea','.git','.agents','.codex','.aws')]
                for name in files:
                    yield Path(directory)/name
        for path,identity in snapshot_identities(inputs()):
            result[str(path)]=thaw(identity)
            total_bytes+=identity.bytes
            if len(result)%5000==0:progress('isolation_progress',root)
        progress('isolation_root_finished',root)
    return result


@dataclass
class CheckContext:
    config: object
    run: Path
    paths: RuntimePaths
    store: object
    logger: RunLogger
    manager: ServiceManager
    report: dict
    sampler: object = None

    def command(self,args, *, timeout=300, cwd=None,stage='validation'):
        result=run_logged(tuple(str(x) for x in args),cwd=cwd or self.run,env=build_child_env(self.paths),
                          timeout=timeout,logger=self.logger,stage=stage)
        if result.returncode!=0 or result.timed_out:
            raise OSError(f'command failed: {result.returncode}, timeout={result.timed_out}; {result.stderr_path}')
        return result

    def ffmpeg(self,*args,timeout=300):
        return self.command((self.config.tools['ffmpeg'],'-nostdin','-n','-v','error',*args),timeout=timeout)

    def probe(self,path):
        result=self.command((self.config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',path))
        return json.loads(result.stdout_path.read_text(encoding='utf-8'))

    def decode(self,path):
        self.ffmpeg('-i',path,'-f','null','-')

    def owned_service(self,name):
        specs=build_service_specs(self.config,self.run)
        for key in ('input','output','temp','user'):
            (self.run/'comfy'/key).mkdir(parents=True,exist_ok=True)
        handle=self.manager.ensure(specs[name])
        if not handle.owned:
            raise ServiceConflictError(f'{name}: external instance cannot verify new-location migration')
        if self.sampler is not None:
            self.sampler.sample()
        return handle

    def model(self,name,path):
        inventory=read_json_list(INVENTORY/'files.json')
        expected={str(Path(x['target'])).casefold():x['sha256'] for x in inventory if x.get('target') and x.get('sha256')}
        sources={str(Path(x['source'])).casefold():x['sha256'] for x in inventory if x.get('sha256')}
        for source,target,_ in ROOTS:
            if str(Path(source)).casefold() in sources:
                expected[str(RUNTIME_ROOT/target).casefold()]=sources[str(Path(source)).casefold()]
        identity=hash_file(path)
        if expected.get(str(path).casefold())!=identity.sha256:
            raise OSError(f'model/input identity differs from verified inventory: {path}')
        self.store.update(lambda d:d['models'].update({name:thaw(identity)}))
        return identity

    def previous_artifact(self,component,name):
        local=self.report['components'].get(component,{})
        if local.get('status')=='passed' and name in local.get('artifacts',{}):
            return verified_artifact(local['artifacts'][name])
        signature=hash_file(self.config.config_file).sha256
        for run in sorted(self.paths.runs_root.iterdir(),reverse=True):
            report=run/'component-report.json'
            if run==self.run or not report.is_file():
                continue
            data=json.loads(report.read_text(encoding='utf-8'))
            item=data.get('components',{}).get(component,{})
            if data.get('config_sha256')==signature and item.get('status')=='passed' and name in item.get('artifacts',{}):
                if data.get('voice_sha256')!=hash_file(self.config.voice.config_file).sha256:
                    continue
                return verified_artifact(item['artifacts'][name])
        raise OSError(f'no verified {component}/{name} artifact for this candidate; execute prerequisites first')


def read_json_list(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verified_artifact(identity):
    path=PathPolicy().validate_write(identity['path'],'run')
    fresh=hash_file(path)
    if fresh.sha256!=identity['sha256'] or fresh.bytes!=identity['bytes']:
        raise OSError(f'verified component input changed: {path}')
    return path


def artifact(path):
    return thaw(hash_file(path))


def migration_receipt(paths):
    for run in sorted(paths.runs_root.iterdir(),reverse=True):
        path=run/'migration-result.json'
        if not path.is_file():continue
        data=json.loads(path.read_text(encoding='utf-8'))
        migration=data.get('migration',{})
        counts=migration.get('counts',{})
        if (data.get('passed') is True and data.get('dry_run') is False and migration.get('passed') is True
            and data.get('capacity',{}).get('passed') is True and migration.get('total_files',0)>100000
            and counts.get('verified',0)+counts.get('skipped',0)==migration['total_files']
            and counts.get('failed',0)==0 and counts.get('conflict',0)==0):
            plan=json.loads((run/'logs/copy-plan.json').read_text(encoding='utf-8'))
            targets={str(Path(x['target'])).casefold() for x in plan}
            if len(plan)!=migration['total_files'] or len(targets)!=len(plan):continue
            if not all(any(Path(x['source']).is_relative_to(Path(source)) and Path(x['target']).is_relative_to(RUNTIME_ROOT/target)
                           for x in plan) for source,target,_ in ROOTS):continue
            return artifact(path)
    return None


def validate_publication(config,report):
    if hash_file(config.config_file).sha256!=report['config_sha256']:
        raise OSError('candidate changed after verification')
    if hash_file(config.voice.config_file).sha256!=report['voice_sha256']:
        raise OSError('voice configuration changed after verification')
    receipt=report.get('migration_receipt')
    if receipt is None:raise OSError('complete migration receipt is required for publication')
    path=verified_artifact(receipt)
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('passed') is not True or data.get('dry_run') is not False:
        raise OSError('migration receipt is not successful execution')
    tts_config=config.project_root/'config/tts-api.yaml'
    if hash_file(tts_config).sha256!=report.get('tts_config_sha256'):
        raise OSError('TTS runtime configuration changed after verification')


def check_environment(ctx):
    c=ctx.config
    expected={'scheduler':('3.12.10',64),'comfy':('3.13.14',64),'tts':('3.9.13',64)}
    probe="import sys,json,struct,importlib.metadata as m; print(json.dumps(dict(version='.'.join(map(str,sys.version_info[:3])),bits=struct.calcsize('P')*8,executable=sys.executable,paths=sys.path,packages={n:m.version(n) for n in ('torch','torchaudio','transformers') if list(m.distributions(name=n))})))"
    package_baseline=read_json(INVENTORY/'versions.json')['packages']
    for name,exe in (('scheduler',ctx.paths.env_root/'Scripts/python.exe'),('comfy',c.tools['comfy_python']),('tts',c.tools['tts_python'])):
        ctx.command((exe,'--version'),timeout=30)
        result=ctx.command((exe,'-B','-c',probe),timeout=60)
        info=json.loads(result.stdout_path.read_text(encoding='utf-8').splitlines()[-1])
        if (info['version'],info['bits'])!=expected[name]:
            raise OSError(f'{name}: interpreter differs from fixed baseline')
        if any('D:/AI/' in p.replace('\\','/') or '/Programs/Ollama' in p.replace('\\','/') for p in info['paths']):
            raise OSError(f'{name}: legacy installation on sys.path')
        if name!='scheduler':
            for package in ('torch','torchaudio','transformers'):
                wanted=package_baseline[name][package+'-*.dist-info']
                if wanted!=[package+'-'+info['packages'][package]+'.dist-info']:
                    raise OSError(f'{name}/{package}: package version drift')
    for args in ((c.tools['ffmpeg'],'-version'),(c.tools['ffprobe'],'-version'),(c.tools['ffmpeg'],'-encoders'),(c.tools['ffmpeg'],'-filters')):
        ctx.command(args,timeout=30)
    ctx.command((ctx.paths.env_root/'Scripts/video-ai.exe','--help'),timeout=30)
    doctor=ctx.command((ctx.paths.env_root/'Scripts/video-ai.exe','doctor','--config',c.config_file,'--json'),timeout=120)
    if not json.loads(doctor.stdout_path.read_text(encoding='utf-8'))['passed']:
        raise OSError('new-location doctor failed')
    cli=(c.tools['comfy_root']/'comfy/cli_args.py').read_text(encoding='utf-8')
    for flag in ('models','input','output','temp','user'):
        if '--'+flag+'-directory' not in cli:
            raise OSError('missing Comfy directory redirection')
    if '--database-url' not in cli:
        raise OSError('missing explicit Comfy database redirection')
    help_result=ctx.command((c.tools['tts_python'],'-B',c.tools['tts_root']/'api_v2.py','--help'),cwd=c.tools['tts_root'],timeout=120)
    help_text=help_result.stdout_path.read_text(encoding='utf-8',errors='replace')
    if not all(flag in help_text for flag in ('-a','-p','-c')):
        raise OSError('TTS API arguments unverified')
    return dict(passed=True,doctor_stdout=str(doctor.stdout_path))


def check_ollama(ctx):
    # Ollama generate can use GPU: enforce the same external-resource gate.
    with GpuLease(ctx.paths,ctx.store,ctx.logger,service_manager=ctx.manager,resource_policy=desktop_policy).acquire('storyboard','migration-ollama'):
        handle=ctx.owned_service('ollama')
        try:
            http=HttpClient(ctx.config.services['ollama'],ctx.config.timeouts['ollama_request'],ctx.logger)
            version=http.get_json('/api/version')
            tags=http.get_json('/api/tags')
            http.get_json('/api/ps')
            model=next((x for x in tags.get('models',[]) if x.get('name')=='qwen3:8b'),None)
            manifest=ctx.paths.runtime_root/'models/ollama/manifests/registry.ollama.ai/library/qwen3/8b'
            identity=ctx.model('ollama_manifest',manifest)
            if model is None or model.get('digest')!=identity.sha256:
                raise OSError('Ollama qwen3:8b digest mismatch')
            definition=read_json(manifest)
            for layer in [definition['config'],*definition['layers']]:
                file=ctx.paths.runtime_root/'models/ollama/blobs'/layer['digest'].replace(':','-')
                blob=hash_file(file)
                if blob.sha256!=layer['digest'].split(':')[1] or blob.bytes!=layer['size']:
                    raise OSError('Ollama blob identity mismatch')
            response=http.request('POST','/api/generate',json_body=dict(model='qwen3:8b',prompt='仅回答“迁移验证完成”',stream=False,keep_alive=0))
            data=http.parse_json(response,method='POST')
            if data.get('done') is not True or not isinstance(data.get('response'),str) or not data['response'].strip():
                raise ValueError('invalid Ollama generation result')
            return dict(passed=True,version=version,response_path=str(response.evidence_path))
        finally:
            ctx.manager.stop(handle)


def check_tts(ctx):
    c=ctx.config
    voice=c.voice
    if voice.device!='cpu' or voice.is_half is not False:
        raise ValueError('migration fixed voice must use CPU without half precision')
    yaml_path=c.project_root/'config/tts-api.yaml'
    parsed=ctx.command((c.tools['tts_python'],'-B','-c',
        'import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1],encoding="utf-8"))))',yaml_path),timeout=30)
    validate_tts_configuration(json.loads(parsed.stdout_path.read_text(encoding='utf-8')),voice)
    for name in ('gpt_weights','sovits_weights','reference_audio'):
        ctx.model('voice_'+name,getattr(voice,name))
    for name in ('bert_root','hubert_root'):
        for file in scan_files(getattr(voice,name)):
            ctx.model(name+'_'+file.name,file)
    handle=ctx.owned_service('tts')
    try:
        payload=dict(voice.inference)
        payload.update(text=voice.reference_text,text_lang=voice.text_language,ref_audio_path=str(voice.reference_audio),
                       prompt_text=voice.reference_text,prompt_lang=voice.prompt_language,speed_factor=voice.speed_factor)
        http=HttpClient(c.services['tts'],c.timeouts['tts_request'],ctx.logger)
        response=http.request('POST','/tts',json_body=payload,max_bytes=64*1024*1024,stage='speech',unit_id='migration-voice')
        content_type=response.headers.get('content-type','').split(';')[0]
        if content_type not in ('','audio/wav','audio/x-wav','application/octet-stream') or not response.body:
            raise ValueError('TTS response is not WAV')
        audio=ctx.run/'audio'
        audio.mkdir(exist_ok=True)
        raw=audio/'component-raw.wav'
        with raw.open('xb') as file:file.write(response.body)
        ctx.probe(raw)
        ctx.decode(raw)
        pcm=audio/'component-48000.wav'
        ctx.ffmpeg('-i',raw,'-ar','48000','-ac','1','-c:a','pcm_s16le',pcm)
        ctx.decode(pcm)
        with wave.open(str(pcm),'rb') as file:
            if (file.getframerate(),file.getnchannels(),file.getsampwidth(),file.getcomptype())!=(48000,1,2,'NONE') or file.getnframes()<=0:
                raise ValueError('standardized audio has invalid PCM/sample count')
            samples=file.getnframes()
            if len(file.readframes(samples))!=samples*2:raise ValueError('truncated WAV')
        yaml=(c.project_root/'config/tts-api.yaml').read_text(encoding='utf-8')
        for path in (voice.gpt_weights,voice.sovits_weights,voice.bert_root,voice.hubert_root):
            if str(path).replace('\\','/') not in yaml:
                raise OSError('TTS YAML lacks fixed new model path')
        record=ctx.store.snapshot()['services']['tts']
        logs='\n'.join(Path(record[k]).read_text(encoding='utf-8',errors='replace') for k in ('stdout_path','stderr_path'))
        validate_tts_load_log(logs,voice)
        return dict(passed=True,samples=samples,sample_rate=48000,listened=False,artifacts=dict(wav=artifact(pcm),raw_wav=artifact(raw)))
    finally:
        ctx.manager.stop(handle)


def validate_tts_configuration(data,voice):
    custom=data.get('custom',{})
    expected=dict(version='v2',device='cpu',is_half=False,t2s_weights_path=str(voice.gpt_weights),
                  vits_weights_path=str(voice.sovits_weights),bert_base_path=str(voice.bert_root),cnhuhbert_base_path=str(voice.hubert_root))
    for key,value in expected.items():
        actual=custom.get(key)
        if key.endswith('_path'):
            if not isinstance(actual,str) or not Path(actual).is_absolute() or Path(actual)!=Path(value):
                raise ValueError('active TTS custom path differs: '+key)
        elif type(actual)!=type(value) or actual!=value:
            raise ValueError('active TTS custom setting differs: '+key)


def validate_tts_load_log(logs,voice):
    lower=logs.casefold()
    if any(token in lower for token in ('fallback','fall back','not exist','使用默认配置')):
        raise OSError('TTS model fallback/missing path detected')


def comfy_image(ctx,component,replacements,*,unit_id,stage,timeout):
    end=time.monotonic()+timeout
    def remaining():
        budget=end-time.monotonic()
        if budget<=0:raise TimeoutError('component total deadline exhausted; no resubmission')
        return budget
    template_path=ctx.config.workflows[component]
    mapping=template_path.with_suffix('.mapping.json')
    template=WorkflowTemplate.load(template_path,mapping,ctx.config.models)
    for name in template.mapping['models']:
        ctx.model(name,ctx.config.models[name])
    client=ComfyClient(HttpClient(ctx.config.services['comfyui'],min(remaining(),ctx.config.timeouts['comfy_request']),ctx.logger),ctx.store,ctx.logger)
    client.validate_template(template)
    graph=template.instantiate(replacements,output_prefix=ctx.run.name+'/'+component+'/'+unit_id.replace(':','_'))
    client.http.timeout=min(remaining(),ctx.config.timeouts['comfy_request'])
    submission=client.submit_once(graph,stage=stage,kind='frame' if ':' in unit_id else 'shot',unit_id=unit_id)
    try:
        history=client.wait_for(submission,deadline_seconds=remaining())
    except BaseException:
        client._snapshots(stage,unit_id,submission.prompt_id)
        raise
    if len(history.outputs)!=1:
        raise ValueError('expected one mapped component output')
    return output_path(ctx.run,history.outputs[0])


def validate_png(ctx,path,width,height):
    with path.open('rb') as file:
        header=file.read(24)
    if header[:8]!=b'\x89PNG\r\n\x1a\n' or len(header)!=24 or struct.unpack('>II',header[16:24])!=(width,height):
        raise ValueError('PNG signature/dimensions mismatch')
    ctx.decode(path)


def check_sdxl(ctx):
    with GpuLease(ctx.paths,ctx.store,ctx.logger,service_manager=ctx.manager,resource_policy=desktop_policy).acquire('start_images','shot_0001'):
        handle=ctx.owned_service('comfyui')
        try:
            # The versioned source template retains the successful prompts and sampler.
            image=comfy_image(ctx,'sdxl',dict(seed=812045847300606,width=1024,height=1024),unit_id='shot_0001',stage='start_images',timeout=ctx.config.timeouts['comfy_request'])
            validate_png(ctx,image,1024,1024)
            return dict(passed=True,artifacts=dict(png=artifact(image)))
        finally:ctx.manager.stop(handle)


def check_wan(ctx):
    with GpuLease(ctx.paths,ctx.store,ctx.logger,service_manager=ctx.manager,resource_policy=desktop_policy).acquire('source_clips','shot_0001'):
        handle=ctx.owned_service('comfyui')
        try:
            source=ctx.paths.input_root/'verification/ship_start.png'
            identity=ctx.model('wan_start_image',source)
            target=ctx.run/'comfy/input/ship_start.png'
            copy_verified(CopyEntry(source,target,'run',identity.bytes,identity.sha256),logger=ctx.logger)
            video=comfy_image(ctx,'wan',dict(start_image='ship_start.png',width=1280,height=720,length=81,fps=16,seed_high=264244520398999,seed_low=0),unit_id='shot_0002',stage='source_clips',timeout=ctx.config.timeouts['wan'])
            validate_video_probe(ctx.probe(video),width=1280,height=720,frames=81,fps=16)
            ctx.decode(video)
            if not ctx.manager.release_comfy_models(handle):
                raise OSError('owned Comfy model release could not be verified')
            return dict(passed=True,artifacts=dict(mp4=artifact(video)))
        finally:ctx.manager.stop(handle)


def check_upscale(ctx):
    video=ctx.previous_artifact('wan','mp4')
    frames=ctx.run/'shots/shot_0001/frames'
    frames.mkdir(parents=True)
    ctx.ffmpeg('-i',video,'-fps_mode','passthrough',frames/'frame_%06d.png')
    inputs=sorted(frames.glob('frame_*.png'))
    if [p.name for p in inputs]!=[f'frame_{i:06d}.png' for i in range(1,82)]:
        raise ValueError('expected continuous 81 input frames')
    output=ctx.run/'shots/shot_0001/upscaled-frames'
    output.mkdir()
    end=time.monotonic()+ctx.config.timeouts['upscale_clip']
    with GpuLease(ctx.paths,ctx.store,ctx.logger,service_manager=ctx.manager,resource_policy=desktop_policy).acquire('upscale','shot_0001'):
        handle=ctx.owned_service('comfyui')
        try:
            for i,image in enumerate(inputs,1):
                remaining=end-time.monotonic()
                if remaining<=0:raise TimeoutError('upscale clip deadline exhausted; no resubmission')
                name=f'frame_{i:06d}.png'
                original=hash_file(image)
                copy_verified(CopyEntry(image,ctx.run/'comfy/input'/name,'run',original.bytes,original.sha256),logger=ctx.logger)
                generated=comfy_image(ctx,'upscale',dict(image=name),unit_id=f'shot_0001:frame_{i:06d}',stage='upscale',timeout=min(remaining,ctx.config.timeouts['upscale_frame']))
                validate_png(ctx,generated,1920,1080)
                identity=hash_file(generated)
                copy_verified(CopyEntry(generated,output/name,'run',identity.bytes,identity.sha256),logger=ctx.logger)
            movie=ctx.run/'shots/shot_0001/upscaled.mp4'
            ctx.ffmpeg('-framerate','16','-i',output/'frame_%06d.png','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',movie)
            validate_video_probe(ctx.probe(movie),width=1920,height=1080,frames=81,fps=16)
            ctx.decode(movie)
            return dict(passed=True,frame_count=81,artifacts=dict(mp4=artifact(movie)))
        finally:ctx.manager.stop(handle)


def check_media(ctx):
    movie=ctx.previous_artifact('upscale','mp4')
    audio=ctx.previous_artifact('tts','wav')
    staging=ctx.run/'staging'
    staging.mkdir()
    subtitle=ctx.run/'subtitles/component.srt'
    subtitle.parent.mkdir()
    subtitle.write_text('1\n00:00:00,000 --> 00:00:05,062\n夜色渐渐安静下来，微风轻轻吹过树梢。\n',encoding='utf-8')
    # FFmpeg filter syntax needs a second escape layer for drive colons.
    def escape(path):
        return str(path).replace('\\','/').replace(':','\\:').replace("'", "'\\\\''")
    font=ctx.config.media.font_file
    ctx.model('font',font)
    vf=f"subtitles=filename='{escape(subtitle)}':fontsdir='{escape(font.parent)}':force_style='FontName=Microsoft YaHei,FontSize=28'"
    final=staging/'component-subtitled.mp4'
    encoded=ctx.ffmpeg('-loglevel','verbose','-i',movie,'-i',audio,'-vf',vf,'-c:v','libx264','-c:a','aac','-pix_fmt','yuv420p',final)
    validate_font_log(encoded.stderr_path.read_text(encoding='utf-8',errors='replace'),font)
    data=ctx.probe(final)
    validate_video_probe(data,width=1920,height=1080,frames=81,fps=16)
    if not any(s.get('codec_type')=='audio' and s.get('codec_name')=='aac' for s in data['streams']):
        raise ValueError('AAC output missing')
    if not any(s.get('codec_type')=='video' and (s.get('width'),s.get('height'))==(1920,1080) for s in data['streams']):
        raise ValueError('1080p output missing')
    ctx.decode(final)
    nvenc=staging/'nvenc-test.mp4'
    with GpuLease(ctx.paths,ctx.store,ctx.logger,service_manager=ctx.manager,resource_policy=desktop_policy).acquire('validation','migration-nvenc'):
        ctx.ffmpeg('-f','lavfi','-i','color=c=black:s=1920x1080:r=16','-t','1','-c:v','h264_nvenc',nvenc)
        ctx.decode(nvenc)
    return dict(passed=True,artifacts=dict(mp4=artifact(final),srt=artifact(subtitle),nvenc=artifact(nvenc)))


def validate_font_log(log,font):
    normalized=log.replace('\\','/').casefold()
    font_messages='\n'.join(line for line in normalized.splitlines() if 'font' in line or 'glyph' in line)
    if (str(font).replace('\\','/').casefold() not in normalized or 'fontselect:' not in normalized
        or 'microsoftyahei' not in normalized.replace(' ','') or 'not found' in font_messages):
        raise OSError('migrated font loading/selection or glyph coverage unverified')


def verify_components(config, *, run_dir: Path, only: str | None = None) -> dict:
    if only is not None and only not in COMPONENTS:
        raise ValueError('unknown migration component')
    run=validate_run_dir(run_dir)
    paths=RuntimePaths.from_config(config)
    store=create_manifest(run,config,inputs={},models={},workflows={})
    logger=RunLogger(run)
    manager=ServiceManager(paths,store,logger,resource_policy=desktop_policy)
    report=dict(passed=False,run_dir=str(run),config_sha256=hash_file(config.config_file).sha256,
                voice_sha256=hash_file(config.voice.config_file).sha256,
                components={},configuration_switched=False,listened=False,multishot_verified=False,fast_profile_verified=False)
    ctx=CheckContext(config,run,paths,store,logger,manager,report)
    report['migration_receipt']=migration_receipt(paths)
    tts_config=paths.config_root/'tts-api.yaml'
    report['tts_config_sha256']=hash_file(tts_config).sha256 if tts_config.is_file() else None
    for component in (COMPONENTS if only is None else (only,)):
        stage=dict(environment='preflight',ollama='storyboard',tts='speech',sdxl='start_images',wan='source_clips',upscale='upscale',media='validation')[component]
        store.record_stage(stage,'running')
        item=dict(status='running',started_at=now())
        report['components'][component]=item
        atomic_report(run/'component-report.json',report)
        interrupted=None
        before=None
        try:
            before=scan_isolation(config,logger=logger)
            logger.save_json(f'isolation/{component}-before.json',before)
            with ResourceSampler(run,lambda:manager.owned_pids|{os.getpid()},interval_seconds=10) as sampler:
                ctx.sampler=sampler
                result=globals()['check_'+component](ctx)
            if sampler.summary()['verified_samples']<1:
                raise OSError('no verified resource samples; component evidence retained without acceptance')
            after=scan_isolation(config,logger=logger)
            logger.save_json(f'isolation/{component}-after.json',after)
            changed={p:dict(before=before.get(p),after=after.get(p)) for p in set(before)|set(after)
                     if before.get(p,{}).get('sha256')!=after.get(p,{}).get('sha256')}
            logger.save_json(f'isolation/{component}-changes.json',changed)
            if changed:
                raise OSError('tool/config/source writes detected; see isolation changes')
            item.update(result,status='passed',resources=sampler.summary(),isolation_verified=True)
        except BaseException as exc:
            item.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc),traceback_path=str(logger.exception('validation',component,exc)))
            atomic_report(run/'component-report.json',report)
            if before is not None:
                try:
                    after=scan_isolation(config,logger=logger)
                    logger.save_json(f'isolation/{component}-failure-after-{uuid4().hex}.json',after)
                except Exception as scan_error:logger.exception('validation',None,scan_error)
            interrupted=exc if isinstance(exc,(KeyboardInterrupt,SystemExit)) else None
        item['finished_at']=now()
        error=None
        if item['status']!='passed':
            error=dict(kind='component_failure',message=item['error'],traceback_path=item['traceback_path'],evidence_paths=[])
        store.record_stage(stage,'completed' if item['status']=='passed' else 'interrupted' if interrupted else 'failed',error=error)
        atomic_report(run/'component-report.json',report)
        if interrupted:raise interrupted
        if item['status']!='passed':break
    report['passed']=all(i['status']=='passed' for i in report['components'].values())
    # Only a complete real verification sequence may publish the exact candidate.
    if only is None and report['passed'] and len(report['components'])==len(COMPONENTS):
        validate_publication(config,report)
        for identity in store.snapshot()['models'].values():
            fresh=hash_file(Path(identity['path']))
            if fresh.sha256!=identity['sha256'] or fresh.bytes!=identity['bytes']:
                raise OSError('registered component model/input changed before publication')
        target=paths.config_root/'production.json'
        policy=PathPolicy()
        policy.validate_write(target,'config')
        raw=config.config_file.read_bytes()
        if target.exists():
            if target.read_bytes()!=raw:raise FileExistsError('production configuration conflict')
        else:
            temp=target.with_name('production.'+uuid4().hex+'.tmp')
            with temp.open('xb') as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            os.rename(temp,target)
        report['configuration_switched']=True
        doctor=ctx.command((paths.env_root/'Scripts/video-ai.exe','doctor','--config',target,'--json'),timeout=120)
        report['final_doctor_stdout']=str(doctor.stdout_path)
    atomic_report(run/'component-report.json',report)
    return report
