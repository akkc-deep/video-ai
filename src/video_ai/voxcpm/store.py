"""One owner, durable task identities, explicit recovery and atomic audio receipts."""
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

from ..runtime.manifest import now
from ..runtime.storage_files import safe_path, write_record
from ..runtime.storage_lock import storage_lock
from .contracts import ApiError, fingerprint, valid_id, wav_metadata

_owners = set()
_owners_lock = threading.Lock()
TERMINAL = {'completed', 'failed', 'cancelled'}


def state_directory(directory, runtime_root):
    root = Path(runtime_root).absolute()
    directory = safe_path(Path(directory).absolute(), root)
    if not any(directory.is_relative_to(root / name) and directory != root / name for name in ('work', 'scratch')):
        raise ValueError('state directory must be inside existing work or scratch')
    return directory


class JobStore:
    def __init__(self, directory, runtime_root):
        self.runtime_root = Path(runtime_root).absolute()
        self.directory = state_directory(directory, self.runtime_root)
        self._key = str(self.directory).casefold()
        with _owners_lock:
            if self._key in _owners:
                raise ValueError('state directory already owned')
            _owners.add(self._key)
        self._lease = None
        self.db = None
        self.lock = threading.RLock()
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._lease = storage_lock(safe_path(self.directory/'service.lock', self.directory))
            self._lease.__enter__()
            for name in ('tasks.sqlite3', 'tasks.sqlite3-wal', 'tasks.sqlite3-shm'):
                safe_path(self.directory/name, self.directory)
            self.db = sqlite3.connect(self.directory/'tasks.sqlite3', check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, '
                'request TEXT NOT NULL, status TEXT NOT NULL, result TEXT, error TEXT, created TEXT NOT NULL, updated TEXT NOT NULL)')
            self.db.commit()
            self.recover()
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self._lease is not None:
            self._lease.__exit__(None, None, None)
            self._lease = None
        with _owners_lock:
            _owners.discard(self._key)

    def _task(self, row):
        return dict(request_id=row['id'], engine='voxcpm2', fingerprint=row['fingerprint'],
            request=json.loads(row['request']), status=row['status'],
            result=json.loads(row['result']) if row['result'] else None,
            error=row['error'], created_at=row['created'], updated_at=row['updated'])

    def get(self, request_id):
        valid_id(request_id)
        with self.lock:
            row = self.db.execute('SELECT * FROM tasks WHERE id=?', (request_id,)).fetchone()
            if row is None:
                raise ApiError(404, 'unknown request_id')
            return self._task(row)

    def submit(self, request):
        identity = fingerprint(request)
        request_id = request['request_id']
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM tasks WHERE id=?', (request_id,)).fetchone()
            if row is not None:
                if row['fingerprint'] != identity:
                    raise ApiError(409, 'request_id already exists with different frozen inputs')
                return self._task(row), False
            stamp = now()
            self.db.execute('INSERT INTO tasks VALUES (?,?,?,?,NULL,NULL,?,?)',
                (request_id, identity, json.dumps(request, ensure_ascii=False), 'queued', stamp, stamp))
            return self.get(request_id), True

    def _set(self, request_id, status, *, result=None, error=None):
        self.db.execute('UPDATE tasks SET status=?, result=?, error=?, updated=? WHERE id=?',
            (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error, now(), request_id))

    def claim(self, binding):
        with self.lock, self.db:
            rows = self.db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY rowid").fetchall()
            for row in rows:
                if json.loads(row['request'])['binding'] != binding:
                    self._set(row['id'], 'failed', error='input_changed: model/reference binding differs')
                    continue
                self._set(row['id'], 'running')
                return self.get(row['id'])

    def cancel(self, request_id):
        with self.lock, self.db:
            task = self.get(request_id)
            if task['status'] == 'queued':
                self._set(request_id, 'cancelled')
            elif task['status'] == 'running':
                self._set(request_id, 'cancel_requested')
            return self.get(request_id)

    def stop_pending(self, error=None):
        with self.lock, self.db:
            for row in self.db.execute("SELECT id,status FROM tasks WHERE status NOT IN ('completed','failed','cancelled')").fetchall():
                if error:
                    self._set(row['id'], 'failed', error=error)
                else:
                    self.cancel(row['id'])

    def output_path(self, request_id):
        valid_id(request_id)
        name = hashlib.sha256(request_id.encode()).hexdigest()
        return safe_path(self.directory/'tasks'/name/'sample.wav', self.directory)

    def temporary(self, request_id):
        return safe_path(self.output_path(request_id).with_suffix('.partial.wav'), self.directory)

    def finish(self, request_id, temporary, metrics):
        with self.lock, self.db:
            task = self.get(request_id)
            if task['status'] == 'cancel_requested':
                temporary.unlink(missing_ok=True)
                self._set(request_id, 'cancelled')
            elif task['status'] == 'running':
                metadata = wav_metadata(temporary)
                for key in ('sample_count', 'sample_rate'):
                    if key in metrics and metadata[key] != metrics[key]:
                        raise ValueError('generated WAV differs from model output')
                output = self.output_path(request_id)
                temporary.replace(output)
                result = dict(metadata, generation_time_ms=metrics['generation_time_ms'],
                    duration_ms=metadata['sample_count'] * 1000 / metadata['sample_rate'],
                    audio_path=output.relative_to(self.directory).as_posix())
                write_record(output.with_suffix('.json'), dict(fingerprint=task['fingerprint'], result=result))
                self._set(request_id, 'completed', result=result)
            else:
                raise ValueError('cannot finish a task which is not running')
            return self.get(request_id)

    def fail(self, request_id, error):
        with self.lock, self.db:
            task = self.get(request_id)
            self._set(request_id, 'cancelled' if task['status'] == 'cancel_requested' else 'failed', error=str(error))
            self.temporary(request_id).unlink(missing_ok=True)

    def recover(self):
        with self.lock, self.db:
            rows = self.db.execute("SELECT * FROM tasks WHERE status IN ('running','cancel_requested')").fetchall()
            for row in rows:
                output = self.output_path(row['id'])
                if row['status'] == 'cancel_requested':
                    self._set(row['id'], 'cancelled')
                    output.unlink(missing_ok=True)
                    output.with_suffix('.json').unlink(missing_ok=True)
                else:
                    try:
                        receipt = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
                        result = receipt['result']
                        metadata = wav_metadata(output)
                        if (receipt['fingerprint'] != row['fingerprint']
                                or result['audio_path'] != output.relative_to(self.directory).as_posix()
                                or any(result.get(k) != v for k, v in metadata.items())):
                            raise ValueError('completion receipt differs')
                        self._set(row['id'], 'completed', result=result)
                    except (OSError, ValueError, KeyError, TypeError, EOFError) as error:
                        self._set(row['id'], 'failed', error=f'interrupted: no valid committed receipt ({error})')
                self.temporary(row['id']).unlink(missing_ok=True)
