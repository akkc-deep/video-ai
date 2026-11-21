"""Authorized LVA-01 full-frame upscale/composition AFTER native human review.

Uses a separate new owned Comfy service. Every frame has its own durable intent;
already completed upscales are authenticated and reused without a new POST.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import time
import wave

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'scripts'))
from benchmark_local_gpu import (ExperimentClient, OutcomeUnknown, file_sha, read,
    write_once, media_command, validate_completed, digest)
from video_ai.runtime.paths import RUNTIME_ROOT


def slice_narration(timeline,*,start_frame,frames,target):
    start,end=start_frame*3000,(start_frame+frames)*3000
    pcm=bytearray((end-start)*2);bindings=[];speech=0
    from video_ai.runtime.production_state import ArtifactStamp
    for clip in timeline['clips']:
        a,b=max(start,clip['start_sample']),min(end,clip['end_sample'])
        if a>=b:continue
        path=Path(clip['pcm']['stamp']['path'])
        ArtifactStamp.from_dict(clip['pcm']['stamp']).verify()
        with wave.open(str(path),'rb') as audio:
            if (audio.getframerate(),audio.getnchannels(),audio.getsampwidth(),audio.getnframes())!=(48000,1,2,clip['samples']):
                raise ValueError('original narration PCM contract differs')
            audio.setpos(a-clip['start_sample']);data=audio.readframes(b-a)
        if len(data)!=(b-a)*2:raise ValueError('original narration is truncated')
        pcm[(a-start)*2:(b-start)*2]=data;speech+=b-a
        bindings.append(dict(unit_id=clip['unit_id'],source_sha256=file_sha(path),
            source_start_sample=a-clip['start_sample'],samples=b-a,target_start_sample=a-start))
    target=Path(target)
    if target.exists():
        with wave.open(str(target),'rb') as old:
            if old.getparams()[:3]!=(1,2,48000) or old.readframes(end-start)!=bytes(pcm) or old.readframes(1):
                raise ValueError('existing narration slice differs')
    else:
        with wave.open(str(target),'wb') as audio:
            audio.setparams((1,2,48000,0,'NONE',''));audio.writeframes(pcm)
    return dict(samples=end-start,speech_samples=speech,silence_samples=end-start-speech,
                source_start_sample=start,bindings=bindings,sha256=file_sha(target))


def bind_narration(native,timeline_file):
    native,timeline_file=Path(native),Path(timeline_file).resolve(strict=True)
    timeline=read(timeline_file);timeline=timeline.get('payload',timeline)
    by={clip['unit_id']:clip for clip in timeline['clips']}
    request=read(native/'frozen/original-request.json')
    for binding in request['narration_bindings']:
        clip=by[binding['unit_id']]
        if (clip['text']!=binding['text'] or not
                clip['start_sample']<=binding['start_sample']<binding['end_sample']<=clip['end_sample']):
            raise ValueError('narration timeline does not bind this original clip')
    write_once(native/'narration-source.json',dict(path=str(timeline_file),sha256=file_sha(timeline_file),
        original_request_sha256=file_sha(native/'frozen/original-request.json')))


def bind_font(native,identity):
    import hashlib
    native=Path(native).resolve();source=Path(identity['path'])
    payload=source.read_bytes()
    if len(payload)!=identity['bytes'] or hashlib.sha256(payload).hexdigest()!=identity['sha256']:
        raise ValueError('recorded original font identity differs')
    target=native/'frozen/render-font.ttc';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if file_sha(target)!=identity['sha256']:raise ValueError('frozen experiment font changed')
    else:
        with target.open('xb') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
    write_once(native/'render-font.json',dict(path=str(target),sha256=identity['sha256'],source=str(source)))


def require_native_review(root,trial):
    result=read(root/'trials'/trial/'technical-complete.json')
    approval=root/'trials'/trial/'observation-accepted.json'
    if not approval.exists():raise ValueError('native human video observation is required before upscale')
    accepted=read(approval)
    if accepted.get('decision')!='accepted' or any(accepted.get(k+'_sha256')!=result[k+'_sha256'] for k in ('generated','retained','last_frame')):
        raise ValueError('native human observation media binding differs')
    validate_completed(result)
    return result


def upscale_trial(work,native,trial,*,port,result_provider=None,fixture_provider=None,source_frames=None,restarted=False):
    from video_ai.config import load_config
    from video_ai.media.scene_upscale import verify_scene_frame_pixels,png_sequence_hashes,_check_png
    work,native=Path(work).resolve(),Path(native).resolve()
    original=(result_provider or require_native_review)(native,trial)
    fixture=fixture_provider(native,trial) if fixture_provider else read(native/('child-fixture.json' if trial.endswith('_child') else 'fixture.json'))
    fid=fixture['fixture_id'];count=original['retained_frames'];p=fixture['parameters']
    label=fid+'_'+trial
    folder=work/'postprocess'/label;folder.mkdir(parents=True,exist_ok=True)
    complete=folder/'upscale-complete.json'
    if complete.exists():
        result=read(complete)
        for item in result['frames']:
            if file_sha(item['path'])!=item['sha256']:raise ValueError('completed upscale frame changed')
        return result
    config=load_config(SOURCE/'config/production.example.json')
    images=work/'input/upscale'/label;images.mkdir(parents=True,exist_ok=True)
    extraction=folder/'extraction.json'
    started=time.perf_counter()
    if source_frames is not None and not extraction.exists():
        if len(source_frames)!=count:raise ValueError('explicit reviewed source frame budget differs')
        copied=[]
        for index,item in enumerate(source_frames,1):
            source=Path(item['path']);target=images/f'frame_{index:06d}.png'
            if file_sha(source)!=item['sha256']:raise ValueError('explicit reviewed PNG source differs')
            _check_png(source,width=p['width'],height=p['height'])
            if target.exists():
                if file_sha(target)!=item['sha256']:raise ValueError('copied reviewed PNG differs')
            else:shutil.copyfile(source,target)
            copied.append(dict(path=str(target),sha256=item['sha256']))
        write_once(extraction,dict(source_sha256=original['retained_sha256'],frames=copied,
                                  proof_scope='content-bound PNGs from the original necessary RGB decode'))
    if not extraction.exists():
        existing=sorted(images.glob('frame_*.png'))
        if existing!=[images/f'frame_{i:06d}.png' for i in range(1,len(existing)+1)] or len(existing)>count:
            raise ValueError('interrupted extraction has non-prefix frames')
        if len(existing)<count:
            media_command(work,'native-extract',[config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror',
                '-i',original['retained'],'-map','0:v:0','-vf',f'select=gte(n\\,{len(existing)}),format=rgb24',
                '-start_number',str(len(existing)+1),'-frames:v',str(count-len(existing)),'-fps_mode','passthrough',images/'frame_%06d.png'])
        files=[images/f'frame_{i:06d}.png' for i in range(1,count+1)]
        verify_scene_frame_pixels(original['retained'],files,expected_frames=count,width=p['width'],height=p['height'],config=config)
        write_once(extraction,dict(source_sha256=original['retained_sha256'],
            frames=[dict(path=str(f),sha256=file_sha(f)) for f in files]))
    extracted=read(extraction)
    if extracted['source_sha256']!=original['retained_sha256']:raise ValueError('extraction source differs')
    extraction_seconds=time.perf_counter()-started
    frames=folder/'frames';frames.mkdir(exist_ok=True)
    template=read(SOURCE/'workflows/upscale_api.json')
    client=ExperimentClient(work,port=port);rows=[];inference=0.0;io_seconds=0.0;resumed=0;recovered_intents=0
    for index,item in enumerate(extracted['frames'],1):
        if file_sha(item['path'])!=item['sha256']:raise ValueError('native upscale input changed')
        job=f'upscale_{label}_{index:06d}'
        receipt=folder/f'frame_{index:06d}.json';target=frames/f'frame_{index:06d}.png'
        if receipt.exists():
            row=read(receipt)
            if row['source_sha256']!=item['sha256'] or file_sha(target)!=row['sha256']:
                raise ValueError('completed upscale frame/source differs')
            rows.append(row);resumed+=1;continue
        graph=deepcopy(template)
        graph['1']['inputs']['image']=Path(item['path']).relative_to(work/'input').as_posix()
        graph['5']['inputs']['filename_prefix']=f'upscale/{label}/frame_{index:06d}'
        recovering=(work/'trials'/job/'intent.json').exists()
        recovered_intents+=int(recovering)
        inference_started=time.perf_counter()
        archive=work/'trials'/job/'history.completed.json'
        if archive.exists():
            original_intent=read(work/'trials'/job/'intent.json');pid=read(work/'trials'/job/'accepted.json')['prompt_id']
            entry=read(archive).get(pid,{});record=entry.get('prompt',[]);outputs=entry.get('outputs',{}).get('5',{}).get('images',[])
            if (len(record)<4 or record[1]!=pid or record[2]!=graph or record[3].get('client_id')!=original_intent['client_id']
                or original_intent.get('graph')!=graph or not entry.get('status',{}).get('completed') or len(outputs)!=1 or outputs[0].get('type')!='output'):
                raise OutcomeUnknown('original archived upscale identity differs; no POST')
            output=(work/'output'/outputs[0].get('subfolder','')/outputs[0]['filename']).resolve(strict=True)
            if not output.is_relative_to((work/'output').resolve()):raise ValueError('archived upscale output escapes owned root')
        else:
            if restarted and recovering:raise OutcomeUnknown('original upscale request unknown after service exit; no replay')
            output,pid=client.wait(job,graph,timeout=600,output_node='5',poll_seconds=.15)
        tracked=time.perf_counter()-inference_started;inference+=tracked
        io_started=time.perf_counter();_check_png(output,width=1920,height=1080)
        actual=file_sha(output)
        if target.exists():
            if file_sha(target)!=actual:raise ValueError('uncommitted upscale target differs from original task output')
        else:
            with output.open('rb') as src,target.open('xb') as dst:
                shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
        row=dict(path=str(target),sha256=actual,source_sha256=item['sha256'],prompt_id=pid,graph_sha256=digest(graph),
            original_submit_and_tracking_seconds=None if recovering else tracked,
            invocation_tracking_seconds=tracked,mode='recovery' if recovering else 'normal')
        write_once(receipt,row);rows.append(row);io_seconds+=time.perf_counter()-io_started
        if index==1 or index%16==0 or index==count:
            print(json.dumps(dict(stage='upscale',fixture=fid,trial=trial,frame=index,total=count)),flush=True)
    proof_started=time.perf_counter()
    pixels=png_sequence_hashes([r['path'] for r in rows],width=1920,height=1080,config=config)
    result=dict(fixture_id=fid,trial=trial,native_source_sha256=original['retained_sha256'],
        frames=rows,frame_rgb_sha256=pixels,extraction_seconds=extraction_seconds,
        mode='recovery' if resumed or recovered_intents else 'normal',
        submit_and_tracking_seconds=None if resumed or recovered_intents else inference,
        tracking_invocation_seconds=inference,io_seconds=io_seconds,proof_seconds=time.perf_counter()-proof_started,
        resumed_frames=resumed,recovered_intents=recovered_intents,
        width=1920,height=1080,frame_count=count,quality_status='awaiting_final_human_review')
    write_once(complete,result)
    return result


def join_native_preview(child_root,parent_root,parent_trial):
    from video_ai.config import load_config
    from benchmark_local_gpu import inspect_media
    child_root,parent_root=Path(child_root).resolve(),Path(parent_root).resolve()
    parent=require_native_review(parent_root,parent_trial)
    child=read(child_root/'trials'/(parent_trial+'_child')/'technical-complete.json')
    validate_completed(child)
    binding=read(child_root/'trials'/(parent_trial+'_child')/'parent-binding.json')
    if binding['parent_last_frame_sha256']!=parent['last_frame_sha256']:
        raise ValueError('child preview does not bind accepted parent last frame')
    folder=child_root/'review'/parent_trial;folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'preview.json'
    if receipt.exists():
        result=read(receipt)
        if file_sha(result['preview'])!=result['sha256']:raise ValueError('native joint preview changed')
        return result
    listing=folder/'concat.txt'
    # These are verified local experiment paths; FFmpeg concat single-quote escaping.
    listing.write_text(''.join("file '"+str(Path(v).resolve()).replace('\\','/').replace("'","'\\''")+"'\n" for v in (parent['retained'],child['retained'])),encoding='utf-8')
    target=folder/'parent-child-native.mp4'
    if target.exists():raise OutcomeUnknown('uncommitted native joint preview retained')
    config=load_config(SOURCE/'config/production.example.json')
    media_command(child_root,'native-joint-preview',[config.tools['ffmpeg'],'-nostdin','-n','-v','error',
        '-f','concat','-safe','0','-i',listing,'-map','0:v:0','-c:v','copy','-an',target])
    fixture=read(parent_root/'fixture.json');p=fixture['parameters']
    inspect_media(child_root,target,width=p['width'],height=p['height'],
        expected_frames=parent['retained_frames']+child['retained_frames'],ffmpeg=config.tools['ffmpeg'],ffprobe=config.tools['ffprobe'])
    result=dict(preview=str(target),sha256=file_sha(target),parent_sha256=parent['retained_sha256'],
        child_sha256=child['retained_sha256'],frames=parent['retained_frames']+child['retained_frames'],
        quality='awaiting_human_parent_child_continuity_observation',reencoded=False)
    write_once(receipt,result);return result


def compose_chain(work,parent_root,child_root,parent_trial,timeline_file):
    work,parent_root,child_root=Path(work).resolve(),Path(parent_root).resolve(),Path(child_root).resolve()
    require_native_review(parent_root,parent_trial);require_native_review(child_root,parent_trial+'_child')
    fixture=read(parent_root/'fixture.json');child_fixture=read(child_root/'child-fixture.json')
    if fixture['budget']['end_frame']!=child_fixture['budget']['start_frame']:
        raise ValueError('original parent/child intervals are not contiguous')
    source_folders=[work/'postprocess'/('parent_child_'+t) for t in (parent_trial,parent_trial+'_child')]
    records=[read(folder/'upscale-complete.json') for folder in source_folders]
    folder=work/'postprocess'/('parent_child_chain_'+parent_trial);frames=folder/'frames';frames.mkdir(parents=True,exist_ok=True)
    copied=[]
    for row in [r for record in records for r in record['frames']]:
        target=frames/f'frame_{len(copied)+1:06d}.png'
        if target.exists():
            if file_sha(target)!=row['sha256']:raise ValueError('joint 1080p frame changed')
        else:
            payload=Path(row['path']).read_bytes()
            import hashlib
            if hashlib.sha256(payload).hexdigest()!=row['sha256']:raise ValueError('joint source frame changed')
            with target.open('xb') as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
        copied.append(dict(path=str(target),sha256=row['sha256']))
    expected=fixture['budget']['retained_frames']+child_fixture['budget']['retained_frames']
    if len(copied)!=expected:raise ValueError('joint 1080p full frame count differs')
    write_once(folder/'upscale-complete.json',dict(kind='verified_parent_child_sequence',frames=copied,
        frame_count=expected,width=1920,height=1080))
    return compose_trial(work,parent_root,parent_trial,timeline_file,folder_override=folder)


def compose_trial(work,native,trial,timeline_file,*,folder_override=None,fixture_provider=None):
    from video_ai.config import load_config
    from video_ai.media.subtitles import ass_text,layout_text,quantize
    from video_ai.media.font_metrics import PrivateFont
    from video_ai.planning.composition import CompositionSettings
    from video_ai.media.composition_video import validate_probe,validate_audio_packets
    work,native=Path(work).resolve(),Path(native).resolve()
    fixture=fixture_provider(native,trial) if fixture_provider else read(native/('child-fixture.json' if trial.endswith('_child') else 'fixture.json'))
    folder=Path(folder_override) if folder_override is not None else work/'postprocess'/(fixture['fixture_id']+'_'+trial)
    upscaled=read(folder/'upscale-complete.json');count=upscaled['frame_count']
    complete=folder/'composition-complete.json'
    if complete.exists():
        result=read(complete)
        if file_sha(result['candidate'])!=result['candidate_sha256']:raise ValueError('completed 1080p candidate changed')
        return result
    narration_source=read(native/'narration-source.json')
    if Path(narration_source['path']).resolve()!=Path(timeline_file).resolve() or file_sha(timeline_file)!=narration_source['sha256']:
        raise ValueError('frozen original narration/subtitle timeline differs')
    timeline=read(timeline_file);timeline=timeline.get('payload',timeline)
    config=load_config(SOURCE/'config/production.example.json');settings=CompositionSettings()
    audio_started=time.perf_counter()
    narration=slice_narration(timeline,start_frame=fixture['budget']['start_frame'],frames=count,target=folder/'narration.wav')
    start=fixture['budget']['start_frame']*3000;end=start+count*3000;events=[]
    fonts=folder/'fonts';fonts.mkdir(exist_ok=True)
    font_identity=read(native/'render-font.json');font=fonts/'font.ttc'
    if file_sha(font_identity['path'])!=font_identity['sha256']:
        raise ValueError('frozen original font changed before composition')
    if not font.exists():shutil.copyfile(font_identity['path'],font)
    if file_sha(font)!=font_identity['sha256']:raise ValueError('composition font copy differs')
    with PrivateFont(font,settings.font_name,settings.font_size) as metrics:
        for event in timeline['subtitles']:
            a,b=max(start,event['start_sample']),min(end,event['end_sample'])
            if a>=b:continue
            events.append(dict(start_cs=quantize(a-start,100),end_cs=quantize(b-start,100),
                layout=layout_text(event['text'],measure=metrics.measure,width=1920-2*(settings.margin+settings.outline))))
    subtitles=folder/'subtitles.ass';text=ass_text(events,settings)
    if subtitles.exists():
        if subtitles.read_text(encoding='utf-8')!=text:raise ValueError('existing subtitle slice differs')
    else:subtitles.write_text(text,encoding='utf-8')
    audio_seconds=time.perf_counter()-audio_started
    candidate=folder/'candidate-1080p.mp4';encode_started=time.perf_counter()
    if candidate.exists():raise OutcomeUnknown('uncommitted composition retained; do not overwrite')
    # Use relative ASS/font paths from the owned composition working directory.
    args=[config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-framerate','16','-start_number','1',
        '-i',folder/'frames/frame_%06d.png','-i',folder/'narration.wav','-filter_complex',
        '[0:v:0]subtitles=filename=subtitles.ass:fontsdir=fonts[v]','-map','[v]','-map','1:a:0',
        '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',
        '-c:a','aac','-b:a','192k','-ar','48000','-ac','1','-movflags','+faststart',candidate]
    previous=Path.cwd()
    try:
        os.chdir(folder);media_command(work,'compose',args)
    finally:os.chdir(previous)
    encode_seconds=time.perf_counter()-encode_started;check_started=time.perf_counter()
    def probe(name,options):
        return json.loads(media_command(work,name,[config.tools['ffprobe'],'-v','error',*options,'-of','json',candidate]))
    info=validate_probe(probe('delivery-probe',['-count_frames','-show_streams','-show_format']),
        probe('delivery-pts',['-select_streams','v:0','-show_frames']),fps=16,total_frames=count,channels=1)
    skip=validate_audio_packets(probe('delivery-aac',['-select_streams','a:0','-show_packets'])['packets'],count*3000)
    media_command(work,'delivery-full-decode',[config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',candidate,'-f','null','-'])
    result=dict(candidate=str(candidate),candidate_sha256=file_sha(candidate),technical=info,
        narration=narration,subtitles_sha256=file_sha(subtitles),aac_priming_samples=skip,
        narration_subtitle_seconds=audio_seconds,encode_seconds=encode_seconds,
        delivery_check_seconds=time.perf_counter()-check_started,quality_status='awaiting_final_human_review',
        limitations='Fixed original clip interval, not full-film delivery; no publishing or automatic final quality acceptance.')
    write_once(complete,result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-root',required=True,type=Path);parser.add_argument('--native-root',required=True,type=Path)
    trials=('cold_1','warm_1','warm_2','warm_3')
    parser.add_argument('--trial',default='all',choices=('all',*trials,*(t+'_child' for t in trials)))
    parser.add_argument('--port',type=int,default=8189)
    parser.add_argument('--timeline-file',required=True,type=Path)
    parser.add_argument('--upscale-only',action='store_true')
    args=parser.parse_args(argv)
    for root in (args.work_root.resolve(),args.native_root.resolve()):
        if not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or not (root/'experiment.json').is_file():
            parser.error('new experiment roots required')
    for name in ('narration-source.json','render-font.json'):
        if not (args.native_root/name).is_file():parser.error('frozen original narration and font bindings required before upscale')
    for trial in ('cold_1','warm_1','warm_2','warm_3') if args.trial=='all' else (args.trial,):
        upscale_trial(args.work_root,args.native_root,trial,port=args.port)
        if not args.upscale_only:
            print(json.dumps(compose_trial(args.work_root,args.native_root,trial,args.timeline_file),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
