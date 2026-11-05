"""OS-held lifecycle locks; process exit releases ownership without deleting evidence."""
from contextlib import contextmanager
import os
from pathlib import Path
import threading

_held = threading.local()


@contextmanager
def storage_lock(path: Path):
    """Reentrant in this thread, nonblocking across threads and processes."""
    path = Path(path)
    key = str(path.absolute()).casefold()
    held = getattr(_held, 'paths', None)
    if held is None:
        held = _held.paths = {}
    if key in held:
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    file = path.open('a+b')
    locked = False
    try:
        if file.seek(0, os.SEEK_END) == 0:
            file.write(b'\0'); file.flush()
        file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('storage occupied by another operation; retry after it finishes') from exc
        locked = True
        held[key] = 1
        yield
    finally:
        if locked:
            held.pop(key, None)
            file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_UN)
        file.close()
