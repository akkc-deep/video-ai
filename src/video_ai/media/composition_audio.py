"""Exact original PCM placement and documented, delay-free optional mixing."""
from array import array
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import math
from pathlib import Path
import sys
import wave

from ..planning.timeline import validate_timeline
from ..runtime.manifest import hash_file
from ..runtime.timeline_checks import _again


def sample_count(seconds):
    return int((Decimal(str(seconds))*48000).to_integral_value(rounding=ROUND_HALF_UP))


def pcm_chunks(path,*,channels=1,samples=None):
    with wave.open(str(path),'rb') as f:
        n=f.getnframes()
        if (f.getframerate(),f.getnchannels(),f.getsampwidth(),f.getcomptype())!=(48000,channels,2,'NONE') or (samples is not None and n!=samples):
            raise ValueError('invalid PCM format/count')
        remaining=n
        while remaining:
            count=min(65536,remaining);data=f.readframes(count)
            if len(data)!=count*channels*2:raise ValueError('truncated PCM')
            yield data
            remaining-=count
        if f.readframes(1):raise ValueError('extra PCM samples')


def _zero_chunks(samples):
    while samples:
        n=min(samples,65536);yield bytes(n*2);samples-=n


def narration_chunks(timeline):
    validate_timeline(timeline)
    cursor=0
    for clip in timeline.clips:
        if clip.start_sample<cursor:raise ValueError('overlapping narration')
        yield from _zero_chunks(clip.start_sample-cursor)
        ident=hash_file(clip.pcm.path)
        if ident.sha256!=clip.pcm.sha256 or ident.bytes!=clip.pcm.bytes:raise OSError('original PCM changed')
        yield from pcm_chunks(clip.pcm.path,samples=clip.samples)
        _again({'pcm':ident})
        cursor=clip.end_sample
    yield from _zero_chunks(timeline.total_frames*(48000//timeline.output_fps)-cursor)


def _record(timeline,sha):
    return dict(sample_rate=48000,channels=1,sample_width=2,samples=timeline.total_frames*(48000//timeline.output_fps),speech_samples=timeline.total_speech_samples,silence_samples=timeline.total_silence_samples,padding_samples=timeline.video_padding_samples,payload_sha256=sha,
        clips=[dict(unit_id=c.unit_id,start_sample=c.start_sample,end_sample=c.end_sample,pcm_sha256=c.pcm.sha256,samples=c.samples) for c in timeline.clips])


def write_narration(timeline,target):
    sha=hashlib.sha256()
    with Path(target).open('xb') as file, wave.open(file,'wb') as f:
        f.setparams((1,2,48000,0,'NONE',''))
        for chunk in narration_chunks(timeline):sha.update(chunk);f.writeframesraw(chunk)
    record=_record(timeline,sha.hexdigest())
    if validate_narration(timeline,target)!=record:raise ValueError('narration readback mismatch')
    return record


def validate_narration(timeline,path):
    validate_timeline(timeline)
    with wave.open(str(path),'rb') as f:
        samples=timeline.total_frames*(48000//timeline.output_fps)
        if (f.getframerate(),f.getnchannels(),f.getsampwidth(),f.getcomptype(),f.getnframes())!=(48000,1,2,'NONE',samples):raise ValueError('narration format/samples differ')
        sha=hashlib.sha256()
        for chunk in narration_chunks(timeline):
            if f.readframes(len(chunk)//2)!=chunk:raise ValueError('narration payload/silence differs from original')
            sha.update(chunk)
        if f.readframes(1):raise ValueError('extra narration samples')
    return _record(timeline,sha.hexdigest())


def _values(typecode,data):
    values=array(typecode,data)
    if sys.byteorder!='little':values.byteswap()
    return values


def _mixed(narration,music,settings):
    voice=_values('h',b''.join(pcm_chunks(narration)))
    raw=Path(music).read_bytes()
    if not raw or len(raw)%8:raise ValueError('music must contain complete stereo float32 samples')
    song=_values('f',raw)
    if any(not math.isfinite(x) for x in song):raise ValueError('nonfinite music PCM')
    N=len(voice);M=len(song)//2
    requested=sample_count(settings.music_loop_crossfade_seconds);C=min(requested,(M-1)//2)
    step=M-C;fade=min(sample_count(settings.music_fade_seconds),N//2)
    loops=1 if N<=M else 1+(N-M+step-1)//step
    def music_value(index,ch):
        cycle=min(index//step,loops-1)
        local=index-cycle*step
        # Every overlap occupies the first C samples of a later copy.
        if cycle and local<C:
            right=0.5 if C==1 else local/(C-1)
            value=song[(step+local)*2+ch]*(1-right)+song[local*2+ch]*right
        else:value=song[local*2+ch]
        if fade:
            gain=min(1,index/max(1,fade-1),(N-1-index)/max(1,fade-1))
            value*=gain
        return value
    # Use the periodic source peak as a conservative bound after loop/fade.
    music_peak=max(abs(x) for x in song)
    original_peak=max((abs(x)/32768 for x in voice),default=0)
    narration_gain=0.90/original_peak if original_peak>0.90 else 1.0
    narration_peak=original_peak*narration_gain
    music_gain=min(settings.music_gain,max(0,0.95-narration_peak)/music_peak) if music_peak else 0.0
    output=array('h');peak=0
    for i,value in enumerate(voice):
        for ch in (0,1):
            mixed=value*narration_gain+music_value(i,ch)*music_gain*32768
            quantized=max(-32768,min(32767,math.floor(mixed+0.5)))
            output.append(quantized);peak=max(peak,abs(quantized))
    if peak>0.95*32768+1:raise ValueError('mixed audio exceeds peak budget')
    if sys.byteorder!='little':output.byteswap()
    payload=output.tobytes()
    return payload,dict(sample_rate=48000,channels=2,sample_width=2,samples=N,music_samples=M,
        requested_crossfade_samples=requested,crossfade_samples=C,loop_step_samples=step,
        loop_count=loops,hard_seam=C==0,
        requested_fade_samples=sample_count(settings.music_fade_seconds),fade_samples=fade,
        original_narration_peak=original_peak,narration_gain=narration_gain,narration_peak=narration_peak,
        music_peak=music_peak,requested_music_gain=settings.music_gain,music_gain=music_gain,
        peak=peak/32768,payload_sha256=hashlib.sha256(payload).hexdigest())


def mix_music(narration,music,target,*,settings):
    payload,record=_mixed(narration,music,settings)
    with Path(target).open('xb') as file,wave.open(file,'wb') as f:
        f.setparams((2,2,48000,0,'NONE',''));f.writeframes(payload)
    if validate_mix(narration,music,target,settings=settings)!=record:raise ValueError('mix readback differs')
    return record


def validate_mix(narration,music,target,*,settings):
    expected,record=_mixed(narration,music,settings)
    if b''.join(pcm_chunks(target,channels=2,samples=record['samples']))!=expected:raise ValueError('mixed PCM differs from documented gains/loop/fades')
    return record
