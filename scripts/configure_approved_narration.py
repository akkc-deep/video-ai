"""Activate the approved narration recipe for new make-video runs, retaining a config backup."""
import argparse
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.config import load_config
from video_ai.runtime.paths import RUNTIME_ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=RUNTIME_ROOT/'shared/config/production.json')
    parser.add_argument('--restore-backup',type=Path,help='Explicitly restore a same-directory pre-switch backup')
    args=parser.parse_args()
    from video_ai.voxcpm.deployment import activate, restore_backup
    if args.restore_backup:
        print('Backup: '+str(restore_backup(args.config,args.restore_backup)))
        print('Restored: '+str(args.config))
        return
    config=load_config(args.config)
    backup=activate(args.config,config.runtime_root,SOURCE)
    if backup: print('Backup: '+str(backup))
    print('Active: '+str(args.config)+' / provided-reference-narration-v1')


if __name__=='__main__': main()
