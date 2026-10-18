"""Read-only sources, fresh hashes, and exclusive destination publication."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time
from uuid import uuid4

from .manifest import FileIdentity, hash_file, now, thaw
from .paths import PathPolicy, RUNTIME_ROOT

GIB = 1024**3
WORKSPACE_BYTES = 81*(1280*720*3 + 1920*1080*3*2) + 2*GIB
ROOTS = (
    ('D:/AI/tools/ComfyUI_windows_portable','tools/ComfyUI_windows_portable','tool-env'),
    ('D:/AI/tools/GPT-SoVITS-v2pro-20250604-nvidia50','tools/GPT-SoVITS','tool-env'),
    ('D:/AI/tools/ffmpeg','tools/ffmpeg','tool-env'),
    ('C:/Users/qzw19/AppData/Local/Programs/Ollama','tools/ollama','tool-env'),
    ('C:/Users/qzw19/.ollama/models','models/ollama','model'),
    ('D:/AI/tools/ComfyUI_windows_portable/ComfyUI/models','models/comfyui','model'),
    ('D:/AI/tools/GPT-SoVITS-v2pro-20250604-nvidia50/GPT_SoVITS/pretrained_models','models/tts','model'),
    ('D:/AI/tools/video-demo-0.2.2/first-video-dynamic/voice_ref.wav','projects/video-ai/inputs/voice_ref.wav','input'),
    ('C:/Windows/Fonts/msyh.ttc','projects/video-ai/inputs/fonts/msyh.ttc','input'),
    ('D:/AI/tools/ComfyUI_windows_portable/ComfyUI/output/wan14b_task06/ship_start_00002_.png','projects/video-ai/inputs/verification/ship_start.png','input'),
)


@dataclass(frozen=True)
class CopyEntry:
    source: Path
    target: Path
    category: str
    bytes: int
    source_sha256: str | None


def safe_source(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('source must be absolute')
    for part in (path, *path.parents):
        info = part.lstat()
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f'reparse source rejected: {part}')
    return path


def validate_entry(entry):
    source = safe_source(entry.source)
    if not source.is_file():
        raise OSError(f'source is not a regular file: {source}')
    target = PathPolicy().validate_write(entry.target, entry.category)
    if source.resolve() == target:
        raise ValueError('source and target must differ')
    if type(entry.bytes) is not int or entry.bytes < 0:
        raise ValueError('invalid planned size')
    return source, target


def build_copy_plan(inventory_dir: Path) -> tuple[CopyEntry, ...]:
    inventory = json.loads((inventory_dir/'files.json').read_text(encoding='utf-8'))
    known = {str(Path(x['source'])).casefold(): x['sha256'] for x in inventory if x.get('sha256')}
    entries = []
    targets = set()
    for source_name, relative_target, category in ROOTS:
        source = safe_source(Path(source_name))
        target = RUNTIME_ROOT/relative_target
        files = [source] if source.is_file() else scan_files(source)
        for file in files:
            destination = target if source.is_file() else target/file.relative_to(source)
            destination = PathPolicy().validate_write(destination, category)
            key = str(destination).casefold()
            if key in targets:
                raise ValueError(f'duplicate target: {destination}')
            targets.add(key)
            entry = CopyEntry(file, destination, category, file.stat().st_size, known.get(str(file).casefold()))
            validate_entry(entry)
            entries.append(entry)
    return tuple(sorted(entries, key=lambda x: str(x.target).casefold()))


def scan_files(root):
    safe_source(root)
    def fail(exc):raise exc
    for directory, dirs, names in os.walk(root, followlinks=False,onerror=fail):
        for name in dirs:
            safe_source(Path(directory)/name)
        for name in names:
            file = safe_source(Path(directory)/name)
            if not file.is_file():
                raise ValueError(f'nonregular source: {file}')
            yield file


def check_capacity(entries, *, reserve_bytes):
    if type(reserve_bytes) is not int or reserve_bytes < 20*GIB:
        raise ValueError('reserve must be at least 20GiB')
    pending = []
    verified = 0
    for entry in entries:
        source, target = validate_entry(entry)
        if source.stat().st_size != entry.bytes:
            raise OSError(f'source changed since plan: {source}')
        if target.exists():
            original, copied = hash_file(source), hash_file(target)
            if original.sha256 != copied.sha256 or original.bytes != copied.bytes:
                raise FileExistsError(f'target conflict: {target}')
            if entry.source_sha256 and original.sha256 != entry.source_sha256:
                raise OSError(f'source SHA256 differs from inventory: {source}')
            verified += entry.bytes
        else:
            pending.append(entry.bytes)
    free = shutil.disk_usage(RUNTIME_ROOT).free
    needed = sum(pending)+max(pending,default=0)+WORKSPACE_BYTES+reserve_bytes
    return dict(checked_at=now(),passed=needed<=free,free_bytes=free,
                copy_bytes=sum(pending),already_verified_bytes=verified,
                temporary_peak_bytes=max(pending,default=0),component_workspace_bytes=WORKSPACE_BYTES,
                reserve_bytes=reserve_bytes,required_bytes=needed,file_count=len(entries))


def atomic_report(path, data):
    path = PathPolicy().validate_write(path, 'run')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf-8') as file:
        json.dump(thaw(data),file,ensure_ascii=False,allow_nan=False,indent=2)
        file.flush()
        os.fsync(file.fileno())
    for attempt in range(11):
        try:
            os.replace(temp,path)
            break
        except PermissionError as exc:
            if getattr(exc,'winerror',None) not in (5,32,33) or attempt==10:
                raise
            time.sleep(.05)


def copy_verified(entry, *, logger) -> FileIdentity:
    source, target = validate_entry(entry)
    before = source.stat()
    if before.st_size != entry.bytes:
        raise OSError(f'source changed since plan: {source}')
    if target.exists():
        original, copied = hash_file(source), hash_file(target)
        if (source.stat().st_size,source.stat().st_mtime_ns)!=(before.st_size,before.st_mtime_ns):
            raise OSError(f'source changed during validation: {source}')
        if entry.source_sha256 and original.sha256 != entry.source_sha256:
            raise OSError(f'source SHA256 differs from inventory: {source}')
        if original.sha256 != copied.sha256 or original.bytes != copied.bytes:
            raise FileExistsError(f'target conflict: {target}')
        logger.event('preflight',None,'copy_skipped',dict(source=thaw(original),target=thaw(copied)))
        return copied
    target.parent.mkdir(parents=True,exist_ok=True)
    target = PathPolicy().validate_write(entry.target, entry.category)
    temp = target.with_name(target.name+'.copy.'+uuid4().hex+'.tmp')
    logger.event('preflight',None,'copy_started',dict(source=str(source),target=str(target),temporary=str(temp)))
    digest = hashlib.sha256()
    with source.open('rb') as src, temp.open('xb') as dst:
        opened = os.fstat(src.fileno())
        if (opened.st_size,opened.st_mtime_ns)!=(before.st_size,before.st_mtime_ns):
            raise OSError(f'source changed before copy: {source}')
        while chunk := src.read(4*1024*1024):
            digest.update(chunk)
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())
        after = os.fstat(src.fileno())
    safe_source(source)
    current = source.stat()
    if (after.st_size,after.st_mtime_ns,after.st_ino)!=(before.st_size,before.st_mtime_ns,before.st_ino) or (current.st_size,current.st_mtime_ns,current.st_ino)!=(before.st_size,before.st_mtime_ns,before.st_ino):
        raise OSError(f'source changed during copy: {source}')
    if entry.source_sha256 and digest.hexdigest()!=entry.source_sha256:
        raise OSError(f'source SHA256 differs from inventory: {source}')
    identity = hash_file(temp)
    if identity.bytes!=entry.bytes or identity.sha256!=digest.hexdigest():
        raise OSError(f'copied file SHA256/size mismatch: {temp}')
    target = PathPolicy().validate_write(entry.target, entry.category)
    # Windows rename is exclusive (unlike replace); never overwrite a racing target.
    os.rename(temp,target)
    result = FileIdentity(str(target),identity.bytes,identity.mtime_ns,identity.sha256,identity.verified_at)
    logger.event('preflight',None,'copy_verified',dict(source=str(source),target=thaw(result)))
    return result


def migrate(entries, *, logger, report_path):
    journal = logger.path('migration-files.jsonl')
    result = dict(passed=False,started_at=now(),counts=dict(verified=0,skipped=0,conflict=0,failed=0),
                  journal_path=str(journal),total_files=len(entries),finished_at=None)
    atomic_report(report_path,result)
    for entry in sorted(entries,key=lambda e:str(e.target).casefold()):
        failure = None
        try:
            existed = entry.target.exists()
            identity = copy_verified(entry,logger=logger)
            status = 'skipped' if existed else 'verified'
            record = dict(entry=thaw(entry),status=status,identity=thaw(identity),time=now())
        except BaseException as exc:
            failure = exc
            status = 'conflict' if isinstance(exc,FileExistsError) else 'failed'
            record = dict(entry=thaw(entry),status=status,error=str(exc),time=now(),traceback_path=str(logger.exception('preflight',None,exc)))
        result['counts'][status]+=1
        with journal.open('a',encoding='utf-8') as file:
            file.write(json.dumps(record,ensure_ascii=False)+'\n')
            file.flush()
            os.fsync(file.fileno())
        result['last_target']=str(entry.target)
        atomic_report(report_path,result)
        if status in ('conflict','failed'):
            if isinstance(failure,(KeyboardInterrupt,SystemExit)):
                raise failure
            break
    result.update(passed=sum(result['counts'][k] for k in ('verified','skipped'))==len(entries),finished_at=now())
    atomic_report(report_path,result)
    return result
