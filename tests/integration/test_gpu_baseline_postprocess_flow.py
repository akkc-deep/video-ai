"""Tiny synthetic end-to-end media test; no Comfy service, torch, GPU or cloud."""
import importlib.util
from pathlib import Path
import subprocess
from uuid import uuid4
import wave

from image_helpers import write_png
from unit.test_frames import media_context,make_video


def test_all_frames_original_audio_subtitles_and_1080p_delivery_without_gpu(media_context,monkeypatch):
    spec=importlib.util.spec_from_file_location('offline_postprocess_flow',Path(__file__).parents[2]/'scripts/postprocess_local_gpu.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    native=run/'native-fixture';work=run/'upscale-fixture';native.mkdir();work.mkdir()
    trial=native/'trials/cold_1';trial.mkdir(parents=True)
    last=trial/'last.png';write_png(last,128,72)
    result=dict(generated=str(source),generated_sha256=module.file_sha(source),
        retained=str(source),retained_sha256=module.file_sha(source),
        last_frame=str(last),last_frame_sha256=module.file_sha(last),retained_frames=3)
    module.write_once(trial/'technical-complete.json',result)
    module.write_once(trial/'observation-accepted.json',dict(decision='accepted',
        **{k:result[k] for k in ('generated_sha256','retained_sha256','last_frame_sha256')},
        evidence='SYNTHETIC TEST ONLY; not real human quality acceptance'))
    module.write_once(native/'fixture.json',dict(fixture_id='low_motion',parameters=dict(width=128,height=72),budget=dict(start_frame=0)))
    audio=run/'original.wav'
    with wave.open(str(audio),'wb') as stream:
        stream.setparams((1,2,48000,0,'NONE',''));stream.writeframes(bytes(9000*2))
    stamp=dict(path=str(audio),bytes=audio.stat().st_size,mtime_ns=audio.stat().st_mtime_ns)
    event=dict(unit_id='speech_1',text='测试。',text_start=0,text_end=3,start_sample=0,end_sample=9000)
    timeline=run/'timeline.json'
    module.write_once(timeline,dict(clips=[dict(event,samples=9000,pcm=dict(stamp=stamp))],subtitles=[event]))
    module.write_once(native/'frozen/original-request.json',dict(narration_bindings=[event]))
    module.bind_narration(native,timeline)
    from video_ai.config import load_config
    font=load_config(Path('E:/VideoAI/shared/config/production.json')).media.font_file
    module.bind_font(native,dict(path=str(font),bytes=font.stat().st_size,sha256=module.file_sha(font)))
    calls=[]
    class OfflineUpscale:
        def __init__(self,root,**kwargs):self.root=Path(root)
        def wait(self,job,graph,**kwargs):
            calls.append(job)
            image=self.root/'input'/graph['1']['inputs']['image']
            output=self.root/'output'/(job+'.png');output.parent.mkdir(exist_ok=True)
            result=subprocess.run([str(kw['config'].tools['ffmpeg']),'-nostdin','-n','-v','error','-i',str(image),
                '-vf','scale=1920:1080,format=rgb24','-threads','1',str(output)],capture_output=True,timeout=30)
            assert result.returncode==0,result.stderr
            return output,str(uuid4())
    kw=kwargs
    monkeypatch.setattr(module,'ExperimentClient',OfflineUpscale)
    upscale=module.upscale_trial(work,native,'cold_1',port=8189)
    assert len(calls)==upscale['frame_count']==3
    assert len(upscale['frame_rgb_sha256'])==3
    candidate=module.compose_trial(work,native,'cold_1',timeline)
    assert candidate['technical']['width']==1920 and candidate['technical']['height']==1080
    assert candidate['technical']['frames']==3
    assert candidate['narration']['samples']==9000
    assert candidate['quality_status']=='awaiting_final_human_review'
    assert Path(candidate['candidate']).is_file()
    calls.clear()
    again=module.upscale_trial(work,native,'cold_1',port=8189)
    assert again['frames']==upscale['frames'] and calls==[]
