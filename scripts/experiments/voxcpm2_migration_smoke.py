"""Reproduce dependency relocation locally using immutable file hardlinks, without downloads."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.runtime.paths import RUNTIME_ROOT
from video_ai.runtime.storage_files import safe_path,write_record


def mirror(origin,target):
    """Link immutable binaries; copy mutable configuration before relocation."""
    for folder, dirs, files in os.walk(origin):
        dirs[:]=[name for name in dirs if name!='__pycache__']
        destination=target/Path(folder).relative_to(origin);destination.mkdir(parents=True,exist_ok=True)
        for name in files:
            src=Path(folder)/name;dst=destination/name
            if name.endswith(('.cfg','.pth','.json','.yaml','.yml')):
                shutil.copy2(src,dst)
            else:os.link(src,dst)


def main():
    root=RUNTIME_ROOT/'scratch/benchmarks/TTS-VOX-10'/datetime.now().strftime('%Y%m%d-%H%M%S')/'relocated runtime'
    safe_path(root,RUNTIME_ROOT/'scratch');root.mkdir(parents=True)
    print('Relocation fixture: '+str(root),flush=True)
    for relative in ['shared/envs/voxcpm2','shared/tools/python312','shared/tools/GPT-SoVITS/runtime',
                     'shared/models/VoxCPM2','shared/models/funasr/timestamp',
                     'shared/assets/voices/provided-reference-narration-v1']:
        mirror(RUNTIME_ROOT/relative,root/relative)
    (root/'shared/tools/VoxCPM/.git').mkdir(parents=True)
    shutil.copy2(RUNTIME_ROOT/'shared/tools/VoxCPM/.git/HEAD',root/'shared/tools/VoxCPM/.git/HEAD')
    # Only shared active records are needed; no historical videos are copied or changed.
    config=root/'shared/config/production.json';config.parent.mkdir(parents=True,exist_ok=True)
    active=json.loads((RUNTIME_ROOT/'shared/config/production.json').read_text(encoding='utf-8-sig'))
    write_record(config,active)
    old_voice=Path(active['voice_config'])
    target_voice=root/old_voice.relative_to(RUNTIME_ROOT);target_voice.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(old_voice,target_voice)
    default=root/'shared/config/tts/default-narration.json'
    default.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(RUNTIME_ROOT/'shared/config/tts/default-narration.json',default)
    # Legacy metadata still required by load_config; mirror only its small reference, not weights.
    voice=json.loads(old_voice.read_text(encoding='utf-8-sig'))
    reference=Path(voice['reference_audio']);target=root/reference.relative_to(RUNTIME_ROOT)
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True);os.link(reference,target)
    env=dict(os.environ,VIDEO_AI_RUNTIME_ROOT=str(root),PYTHONPATH=str(SOURCE/'src'),PYTHONUTF8='1')
    command=[str(RUNTIME_ROOT/'shared/envs/video-ai/Scripts/python.exe'),'-B','-m','video_ai.voxcpm.deployment']
    common=['--runtime-root',str(root),'--source-root',str(SOURCE),'--config',str(config)]
    subprocess.run(command+['relocate']+common,env=env,check=True)
    subprocess.run(command+['verify']+common,env=env,check=True)
    report=dict(task_id='TTS-VOX-10',status='passed',relocated_root=str(root),
        method='local isolated file-hardlink mirror; mutable configurations copied',
        downloads=False,full_clean_machine_install=False,inference=False)
    write_record(root.parent/'migration-result.json',report)
    write_record(SOURCE/'docs/research/TTS-VOX-10-migration-result.json',report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
