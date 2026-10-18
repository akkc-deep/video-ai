"""TEST ONLY deterministic original-text, PCM and frame-report fixtures."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from video_ai.config import TimelineSettings
from video_ai.media.audio import AudioInfo
from video_ai.planning.segments import SegmentedScript, segment_text
from video_ai.planning.timeline import build_timeline, SlotRange, budget_slots
from video_ai.planning.storyboard import UnitTiming, SemanticCue, SpeechTimingEvidence, plan_slots
from video_ai.runtime.manifest import thaw

def identity(name):
    return dict(path=str(Path('D:/VideoSi/projects/video-ai/runs/20261005-000000-111111111111')/name),bytes=10,mtime_ns=1,sha256='a'*64,verified_at='2026-10-05T00:00:00+08:00')

def inputs(fps=16,transition='cut',seconds=0):
    text='夜色渐深，周围渐静。\r\n水面有灯光倒影。'
    script=SegmentedScript(text,False,segment_text(text))
    audio={s.unit_id:AudioInfo(Path(identity(s.unit_id+'.wav')['path']),'a'*64,96044,48000,1,2,48000) for s in script.spans if s.kind=='speech'}
    timeline=build_timeline(script,audio,settings=TimelineSettings(0,0,0,0),fps=fps)
    units=tuple(UnitTiming(c.unit_id,0,c.samples,0,(),'passed','passed') for c in timeline.clips)
    cues=tuple(SemanticCue('cue_'+str(i),l.unit_id,r.unit_id,r.start_sample,'passed') for i,(l,r) in enumerate(zip(timeline.clips,timeline.clips[1:]),1))
    timing=SpeechTimingEvidence(units,cues)
    slots=plan_slots(timeline,timing=timing)
    budget=budget_slots(timeline,[SlotRange(s.shot_id,s.start_frame,s.end_frame) for s in slots],transition=transition,transition_seconds=seconds)
    shots=[];clips=[];mappings=[];requirements=[]
    for s,b in zip(slots,budget.shots):
        shot=dict(shot_id=s.shot_id,start_frame=s.start_frame,end_frame=s.end_frame,primary_unit_id=s.primary_unit_id,bindings=thaw(s.bindings),budget=thaw(b),visual_requirements=[dict(requirement_id=s.shot_id+':req_0001',unit_id=s.primary_unit_id,source_quote=next(c.text for c in timeline.clips if c.unit_id==s.primary_unit_id),subject='same subject',setting='same scene',negation=None,quantity=None)])
        shots.append(shot)
        n=b.required_native_frames;video=identity(s.shot_id+'.mp4')
        clips.append(dict(shot_id=s.shot_id,primary_unit_id=s.primary_unit_id,budget=thaw(b),source_frames=n,upscaled_frames=n,native_fps=16,width=1920,height=1080,upscaled_identity=video,frames=[dict(frame_index=i+1,source_frame_index=i,upscaled_frame_identity=identity(s.shot_id+f'/{i}.png')) for i in range(n)]))
        mappings.append(dict(shot_id=s.shot_id,source_identity=identity(s.shot_id+'-source.mp4'),upscaled_identity=video,source_frames=n,upscaled_frames=n,native_fps=16,output_fps=fps,coverage_start_frame=b.coverage_start_frame,coverage_end_frame=b.coverage_end_frame,core_start_frame=b.core_start_frame,core_end_frame=b.core_end_frame,source_to_upscaled=list(range(n)),output_to_upscaled=[i*16//fps for i in range(b.required_output_frames)]))
        requirements.append(dict(shot_id=s.shot_id,requirement_id=s.shot_id+':req_0001',requirement_index=0,unit_id=s.primary_unit_id,source_quote=shot['visual_requirements'][0]['source_quote'],clip_shot_id=s.shot_id,role='primary',actual_artifact=video,source_actual_artifact=identity(s.shot_id+'-source.mp4'),local_frames=dict(start=0,end=n),output_frames=dict(start=b.coverage_start_frame,end=b.coverage_end_frame),sample_range=dict(start=b.coverage_start_frame*(48000//fps),end=b.coverage_end_frame*(48000//fps))))
    media=dict(fps=fps,native_fps=16,transition=transition,transition_seconds=seconds)
    storyboard=dict(status='completed',passed=True,shots=shots,transitions=thaw(budget.transitions),effective_media=media,cues=[dict(thaw(c),frame=(2*c.absolute_sample*fps+48000)//96000) for c in cues])
    upscaled=dict(status='completed',passed=True,clips=clips,frame_mappings=mappings,requirement_clips=requirements,effective_media=media,validation=dict(ready_for_composition=True,video_text_semantics_passed=True,motion_semantics_passed=True))
    return timeline,storyboard,upscaled,timing
