"""Exercise the real make-video speech/timeline stages with the approved voice, then resume."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.config import load_config,read_json
from video_ai.runtime.manifest import create_manifest,thaw
from video_ai.runtime.paths import RuntimePaths,create_run,RUNTIME_ROOT
from video_ai.runtime.production_inputs import freeze_inputs,load_frozen_inputs
from video_ai.runtime.production_state import ProductionStateStore
from video_ai.runtime.production_storyboard import produce_units
from video_ai.runtime.production_speech import produce_speech
from video_ai.runtime.production_timeline import produce_timeline
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.storage_files import write_record


def task_count(run):
    with sqlite3.connect(run/'production/vox/service/tasks.sqlite3') as db:
        return db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=RUNTIME_ROOT/'shared/config/production.json')
    parser.add_argument('--run',type=Path)
    parser.add_argument('--task-id',choices=['TTS-VOX-07','TTS-VOX-10'],default='TTS-VOX-07')
    args=parser.parse_args()
    config=load_config(args.config); paths=RuntimePaths.from_config(config)
    run=args.run or create_run(paths)
    print('Production speech smoke run: '+str(run),flush=True)
    if args.run:
        from video_ai.runtime.manifest import ManifestStore
        frozen=load_frozen_inputs(run)
        state=ProductionStateStore.open(run); manifest=ManifestStore.open(run,verify_integrity=False)
    else:
        raw=thaw(config.raw); recipe=read_json(config.runtime_root/'shared/config/tts/default-narration.json')
        raw['tts']=dict(engine='voxcpm2',model_revision=recipe['model_revision'],narration=recipe)
        raw['services']['tts']='http://127.0.0.1:9881'
        source=run/'smoke-config.json';write_record(source,raw)
        config=load_config(source)
        frozen=freeze_inputs(config,run,text='当夜色慢慢降临，我们仰望星空。遥远的光，仍在安静地旅行。\n每一颗星，都有属于自己的故事。',cpu_planner=True)
        state=ProductionStateStore.create(run)
        manifest=create_manifest(run,frozen.config,inputs=frozen.options['execution_policy']['input_identities'],models={},workflows={},verify_integrity=False)
        state.start_stage('preflight');state.write_report('preflight',dict(checks=[dict(name='speech-only-smoke',passed=True,details='frozen production inputs; no visual generation requested')]))
        state.complete_stage('preflight')
    logger=RunLogger(run,production=True)
    units=produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
    audio=produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
    timeline,slots=produce_timeline(frozen,units,audio,state=state,manifest=manifest,paths=paths,logger=logger)
    before=task_count(run)
    audio2=produce_speech(load_frozen_inputs(run),units,state=state,manifest=manifest,paths=paths,logger=logger)
    timeline2,_=produce_timeline(frozen,units,audio2,state=state,manifest=manifest,paths=paths,logger=logger)
    assert audio==audio2 and timeline==timeline2 and task_count(run)==before
    report=dict(task_id=args.task_id,status='passed',run=str(run),voice_id=frozen.config.tts.narration['voice_id'],
        narration=read_json(run/'production/vox/narration.json')['metadata'],generation_requests=before,
        completed_resume_no_new_requests=True,canonical_units=len(audio),timeline_samples=timeline.total_samples,
        speech_samples=timeline.total_speech_samples,slots=len(slots.slots),listening='user-approved recipe; no new subjective claim',full_video=False)
    write_record(run/(args.task_id.lower()+'-result.json'),report)
    write_record(SOURCE/('docs/research/'+args.task_id+'-speech-result.json' if args.task_id=='TTS-VOX-10'
                         else 'docs/research/TTS-VOX-07-result.json'),report)
    print(json.dumps(dict(status='passed',run=str(run),requests=before,speech_seconds=timeline.total_speech_samples/48000),ensure_ascii=False),flush=True)


if __name__=='__main__': main()
