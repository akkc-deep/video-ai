"""Run-local exclusive raw evidence and append-only structured events."""
import json
import os
import sys
import time
from pathlib import Path
from threading import RLock
import traceback
from uuid import uuid4

from .manifest import now, thaw, validate_run_dir
from .paths import PathPolicy, _validate_spelling


class RunLogger:
    def __init__(self, run_dir, *, production=False):
        if type(production) is not bool:
            raise ValueError('production must be boolean')
        self.run_dir = validate_run_dir(run_dir)
        self.production = production
        self.root = PathPolicy().validate_write(self.run_dir / ('logs/production' if production else 'logs'), 'run')
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.started_at = time.monotonic()

    def path(self, relative_name):
        relative = Path(_validate_spelling(relative_name))
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('log path must remain relative to logs')
        path = PathPolicy().validate_write(self.root / relative, 'run')
        if not path.is_relative_to(self.root):
            raise ValueError('log path escape')
        return path

    def open_exclusive(self, relative_name):
        path = self.path(relative_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path, path.open('xb', buffering=0)

    def save_bytes(self, relative_name, data):
        path, file = self.open_exclusive(relative_name)
        with file:
            file.write(data)
            if self.production:
                file.flush()
                os.fsync(file.fileno())
        return path

    def save_json(self, relative_name, data):
        return self.save_bytes(relative_name, json.dumps(thaw(data), ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8'))

    def event(self, stage, unit_id, event, details):
        data = dict(time=now(), stage=stage, unit_id=unit_id, event=event, details=thaw(details))
        text = json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n'
        with self._lock, self.path('events.jsonl').open('a', encoding='utf-8', newline='\n') as file:
            file.write(text)
            file.flush()
            if self.production:
                os.fsync(file.fileno())

    def exception(self, stage, unit_id, exc):
        data = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).encode('utf-8')
        path = self.save_bytes(f'errors/{uuid4().hex}.txt', data)
        self.event(stage, unit_id, 'exception', {'message':str(exc), 'traceback_path':str(path)})
        return path

    def progress(self,stage,unit_id=None,*,frame=None,total=None):
        details=dict(elapsed_seconds=round(time.monotonic()-self.started_at,3))
        label=f'[make-video] {stage}' + (f' {unit_id}' if unit_id else '')
        if frame is not None:
            if type(frame) is not int or type(total) is not int or not 0<=frame<=total:
                raise ValueError('progress requires integer frame/total')
            details.update(frame=frame,total=total);label+=f' {frame}/{total}'
        self.event(stage,unit_id,'progress',details)
        print(f'{label} elapsed={details["elapsed_seconds"]:.1f}s',file=sys.stderr,flush=True)
