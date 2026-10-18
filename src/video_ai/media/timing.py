"""Reproducible PCM envelope estimates, never human or word alignment claims."""
from array import array
from dataclasses import dataclass
from pathlib import Path
import sys
import wave


@dataclass(frozen=True)
class EnvelopeEstimate:
    schema_version: int
    algorithm: str
    samples: int
    peak: int
    thresholds: tuple[int, ...]
    threshold_boundaries: tuple[tuple[int, int], ...]
    guard_samples: int
    spoken_start_sample: int
    spoken_end_sample: int
    boundary_uncertainty_samples: int
    verified_internal_silences: tuple[tuple[int, int], ...]


def measure_envelope(path: Path) -> EnvelopeEstimate:
    with wave.open(str(path),'rb') as file:
        if (file.getframerate(),file.getnchannels(),file.getsampwidth(),file.getcomptype())!=(48000,1,2,'NONE'):
            raise ValueError('envelope estimation requires 48kHz mono PCM16')
        n=file.getnframes();raw=file.readframes(n)
        if n<1 or len(raw)!=n*2 or file.readframes(1):raise ValueError('invalid/truncated PCM payload')
    values=array('h',raw)
    if sys.byteorder!='little':values.byteswap()
    thresholds=(1,2,4,8);bounds=[];peak=max(abs(v) for v in values)
    if peak<8:raise ValueError('no reliable signal envelope')
    for threshold in thresholds:
        first=next(i for i,v in enumerate(values) if abs(v)>=threshold)
        last=next(i for i in range(n-1,-1,-1) if abs(values[i])>=threshold)+1
        bounds.append((first,last))
    onset_low=min(a for a,b in bounds);onset_high=max(a for a,b in bounds)
    offset_low=min(b for a,b in bounds);offset_high=max(b for a,b in bounds)
    start=(onset_low+onset_high)//2;end=(offset_low+offset_high+1)//2
    guard=240  # 5 ms guard in addition to full multi-threshold spread.
    uncertainty=max(start-onset_low,onset_high-start,end-offset_low,offset_high-end)+guard
    if start>=end:raise ValueError('signal estimate has no positive envelope')
    silences=[];cursor=start
    while cursor<end:
        if values[cursor]:cursor+=1;continue
        a=cursor
        while cursor<end and not values[cursor]:cursor+=1
        if cursor-a>=240:silences.append((a,cursor))
    return EnvelopeEstimate(1,'pcm_envelope_v1',n,peak,thresholds,tuple(bounds),guard,start,end,uncertainty,tuple(silences))
