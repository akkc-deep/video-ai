"""Read-only source-video analysis using short excerpts and existing local models."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_record(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.'+uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(args):
    from video_ai.runtime.storage import VideoStorage
    root=VideoStorage().runtime_root
    output=root/'scratch/analysis/reference-voice'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True)
    tools=read_json(root/'shared/config/production.json')['tools']
    excerpts=[dict(name='reference_early',path=str(args.input.absolute()),start=30.,duration=30.,kind='reference'),
              dict(name='reference_middle',path=str(args.input.absolute()),start=300.,duration=30.,kind='reference'),
              dict(name='reference_late',path=str(args.input.absolute()),start=570.,duration=30.,kind='reference')]
    current=read_json(SOURCE/'docs/research/TTS-VOX-06-bright-natural-result.json')
    selected=next(v for v in current['variants'] if v.get('status')=='generated_pending_listening')
    older=read_json(SOURCE/'docs/research/TTS-VOX-06-soft-narration-result.json')
    for name,path,result_path in [('latest_casual',selected['audio_path'],selected['result_path']),
                                  ('previous_soft',older['audio_path'],older['result_path'])]:
        result=read_json(Path(result_path))
        excerpts.append(dict(name=name,path=path,start=0.,duration=None,kind='comparison',source_text=result['source_text']))
    for row in excerpts:
        target=output/(row['name']+'.wav')
        command=[tools['ffmpeg'],'-nostdin','-v','error','-n','-ss',str(row['start']),'-i',row['path']]
        if row['duration'] is not None: command+=['-t',str(row['duration'])]
        command+=['-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(target)]
        subprocess.run(command,check=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        row['analysis_wav']=str(target)
    manifest=dict(source=str(args.input.absolute()),source_duration_seconds=args.duration,runtime_root=str(root),
        output=str(output),reference_sampled_seconds=90,source_modified=False,excerpts=excerpts,
        limitations=['Three 30-second reference excerpts, not a full-video perceptual review',
                    'Mixed soundtrack retained; no speaker separation or identity inference'])
    write_record(output/'manifest.json',manifest)
    print(str(output),flush=True)


def acoustic(output,only=None):
    import numpy as np
    import librosa
    manifest=read_json(output/'manifest.json')
    summaries=read_json(output/'acoustic.json')['files'] if only and (output/'acoustic.json').exists() else []
    for row in manifest['excerpts']:
        if only and row['name']!=only: continue
        summaries=[r for r in summaries if r['name']!=row['name']]
        print('Acoustics: '+row['name'],flush=True)
        audio,sr=librosa.load(row['analysis_wav'],sr=16000,mono=True)
        hop=320
        f0,voiced,prob=librosa.pyin(audio,fmin=65,fmax=500,sr=sr,frame_length=2048,hop_length=hop)
        spectrum=np.abs(librosa.stft(audio,n_fft=2048,hop_length=hop))**2
        total=np.maximum(spectrum.sum(axis=0),1e-20)
        frequencies=librosa.fft_frequencies(sr=sr,n_fft=2048)
        rms=librosa.feature.rms(y=audio,frame_length=2048,hop_length=hop)[0]
        db=20*np.log10(np.maximum(rms,1e-9))
        bands=[]
        for lo,hi in [(65,250),(250,1000),(1000,4000),(4000,7900)]:
            bands.append(spectrum[(frequencies>=lo)&(frequencies<hi)].sum(axis=0)/total)
        centroid=(spectrum*frequencies[:,None]).sum(axis=0)/total
        flatness=librosa.feature.spectral_flatness(S=np.sqrt(spectrum))[0]
        count=min(len(f0),len(db),len(centroid))
        np.savez_compressed(output/(row['name']+'-features.npz'),
            times=np.arange(count)*hop/sr,f0=f0[:count],voiced=voiced[:count],prob=prob[:count],
            rms_db=db[:count],centroid=centroid[:count],flatness=flatness[:count],
            bands=np.array(bands)[:,:count],frequencies=frequencies,spectrum=spectrum[:,:count])
        summaries.append(dict(name=row['name'],duration_seconds=len(audio)/sr,peak_dbfs=float(20*np.log10(max(np.max(np.abs(audio)),1e-9))),
            overall_rms_dbfs=float(20*np.log10(max(np.sqrt(np.mean(audio**2)),1e-9)))))
    write_record(output/'acoustic.json',dict(protocol=dict(sr=16000,frame=2048,hop=320,
        pitch_range_hz=[65,500],pitch_method='pYIN; voiced and probability >= 0.1, speech mask when available'),files=summaries))


def asr(output):
    # All paths refer to existing local models. No downloads or remote services.
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    from funasr import AutoModel
    root=Path(read_json(output/'manifest.json').get('runtime_root',str(output.parents[3])))
    models=root/'shared/tools/GPT-SoVITS/tools/asr/models'
    opts=dict(device='cpu',disable_update=True,disable_pbar=True,ncpu=4,log_level='ERROR')
    recognizer=AutoModel(model=str(models/'speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch'),**opts)
    vad=AutoModel(model=str(models/'speech_fsmn_vad_zh-cn-16k-common-pytorch'),**opts)
    rows=[]
    for row in read_json(output/'manifest.json')['excerpts']:
        print('Speech/VAD: '+row['name'],flush=True)
        intervals=vad.generate(input=row['analysis_wav'])[0].get('value',[])
        result=recognizer.generate(input=row['analysis_wav'])[0] if row['kind']=='reference' else {}
        rows.append(dict(name=row['name'],text=result.get('text',row.get('source_text','')),
            source='local automatic transcription' if row['kind']=='reference' else 'known synthesis source',
            vad_intervals_ms=intervals,raw_asr=result))
        write_record(output/'asr.json',dict(files=rows,transcript_verified=False,
            models='Existing local Paraformer ASR and FSMN VAD; CPU, no download'))


def summarize(output):
    import numpy as np
    manifest=read_json(output/'manifest.json')
    acoustic=read_json(output/'acoustic.json')
    speech={r['name']:r for r in read_json(output/'asr.json')['files']}
    summaries=[]
    f0_plot=[]
    spectra=[]
    for row in manifest['excerpts']:
        data=np.load(output/(row['name']+'-features.npz'))
        initial=next(x for x in acoustic['files'] if x['name']==row['name'])
        transcript=speech[row['name']]
        intervals=transcript['vad_intervals_ms']
        speech_mask=np.zeros(len(data['times']),dtype=bool)
        for start,end in intervals: speech_mask|=(data['times']>=start/1000)&(data['times']<end/1000)
        if not speech_mask.any(): speech_mask=data['rms_db']>max(-55,float(data['rms_db'].max())-30)
        confident=speech_mask & data['voiced'] & (data['prob']>=.1) & np.isfinite(data['f0'])
        values=data['f0'][confident]
        db=data['rms_db'][speech_mask]
        gaps=[(right[0]-left[1])/1000 for left,right in zip(intervals,intervals[1:]) if right[0]-left[1]>=200]
        speech_seconds=sum((end-start)/1000 for start,end in intervals)
        text=transcript['text']
        chinese=len(re.findall('[\u4e00-\u9fff]',text))
        english=len(re.findall("[A-Za-z]+(?:'[A-Za-z]+)?",text))
        pitch=dict(confident_frames=int(confident.sum()),speech_frames=int(speech_mask.sum()))
        if len(values):
            p10,med,p90=np.percentile(values,[10,50,90])
            pitch.update(median_hz=float(med),p10_hz=float(p10),p90_hz=float(p90),
                p10_p90_semitones=float(12*np.log2(p90/p10)))
        summary=dict(initial,kind=row['kind'],source_window_start=row['start'],pitch=pitch,
            spectral_energy_percent=dict(zip(['65-250Hz','250-1000Hz','1-4kHz','4-7.9kHz'],
                [float(x) for x in np.mean(data['bands'][:,speech_mask],axis=1)*100])),
            power_centroid_hz=float(np.median(data['centroid'][speech_mask])),
            spectral_flatness=float(np.median(data['flatness'][speech_mask])),
            speech_frame_rms_dbfs=dict(p10=float(np.percentile(db,10)),median=float(np.median(db)),p90=float(np.percentile(db,90))),
            speech_seconds_vad=speech_seconds,vad_pause_seconds=gaps,
            pause_median_seconds=float(np.median(gaps)) if gaps else None,
            chinese_characters=chinese,english_words=english,
            chinese_characters_per_minute_overall=chinese*60/initial['duration_seconds'],
            chinese_characters_per_minute_speech=chinese*60/speech_seconds if speech_seconds else None,
            transcript=text,transcript_source=transcript['source'])
        summaries.append(summary)
        f0_plot.append(values)
        power=data['spectrum'][:,speech_mask].mean(axis=1)
        power=power/max(power.sum(),1e-20)
        spectra.append(10*np.log10(np.maximum(power,1e-12)))
    report=dict(source=manifest['source'],source_duration_seconds=manifest['source_duration_seconds'],
        reference_sampled_seconds=90,output=str(output),source_modified=False,files=summaries,
        limitations=['Only three 30-second reference excerpts analyzed',
            'Automatic transcript/rates and VAD pauses are estimates; recognition is not manually certified',
            'Spectrum includes retained background sound; no isolated voice/breathiness/identity/gender claim',
            'Digital levels are not listener sound pressure; different recording/mastering levels can bias perception',
            'F0 is measured pitch, not a hypnotic frequency or proof of naturalness'])
    write_record(output/'result.json',report)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    label_map=dict(reference_early='Ref mixed early',reference_middle='Ref mixed middle',reference_late='Ref mixed late',
                   latest_casual='Latest casual',previous_soft='Previous soft',reference_voice_estimate='Ref vocal estimate')
    labels=[label_map.get(r['name'],r['name']) for r in manifest['excerpts']]
    fig,axes=plt.subplots(1,2,figsize=(12,4.2))
    axes[0].boxplot(f0_plot,labels=labels,showfliers=False)
    axes[0].set_ylabel('Confident voiced pitch (Hz)')
    axes[0].tick_params(axis='x',labelrotation=25)
    axes[0].grid(axis='y',alpha=.2)
    for curve,label in zip(spectra,labels): axes[1].plot(data['frequencies'],curve,label=label,lw=1.2)
    axes[1].set_xlim(65,7900); axes[1].set_xscale('log')
    axes[1].set_xlabel('Frequency (Hz)'); axes[1].set_ylabel('Relative speech-window power (dB)')
    axes[1].legend(fontsize=8); axes[1].grid(alpha=.2)
    fig.suptitle('User video vs prior candidates — sampled mixed-track analysis',fontsize=11)
    fig.tight_layout()
    fig.savefig(output/'comparison.png',dpi=160)
    plt.close(fig)
    print(json.dumps([dict(name=r['name'],pitch=r['pitch'],chars_min=r['chinese_characters_per_minute_overall'],
        pause_median=r['pause_median_seconds'],energy=r['spectral_energy_percent'],transcript=r['transcript'][:180]) for r in summaries],ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=['prepare','acoustic','asr','report'],required=True)
    p.add_argument('--input',type=Path)
    p.add_argument('--duration',type=float)
    p.add_argument('--output',type=Path)
    p.add_argument('--only')
    args=p.parse_args()
    if args.phase=='prepare': prepare(args)
    elif args.phase=='acoustic': acoustic(args.output,args.only)
    elif args.phase=='asr': asr(args.output)
    else: summarize(args.output)


if __name__=='__main__': main()
