"""Only explicitly registered, fresh ephemeral files can be removed."""
from dataclasses import dataclass,field
from pathlib import Path

from .manifest import FileIdentity, thaw,hash_file,ManifestStore
from .pipeline_evidence import fresh_identity,write_exclusive
from .timeline_checks import _local, _run_path


@dataclass(frozen=True)
class OwnedTemporary:
    identity: FileIdentity
    ephemeral: bool
    _token: object=field(default=None,repr=False,compare=False)


@dataclass(frozen=True)
class OwnedDirectory:
    path: Path
    _token: object=field(default=None,repr=False,compare=False)


_CREATED_FILES={}
_CREATED_DIRS={}


def create_owned_temporary(run_dir,path,payload):
    run=_run_path(run_dir);path=_local(run,Path(path));token=object()
    identity=write_exclusive(run,path,payload,raw=True)
    _CREATED_FILES[token]=(run,identity)
    return OwnedTemporary(identity,True,token)


def create_owned_directory(run_dir,path):
    run=_run_path(run_dir);path=_local(run,Path(path));token=object()
    path.mkdir(exist_ok=False)
    stat=path.stat();_CREATED_DIRS[token]=(run,path,stat.st_ino,stat.st_ctime_ns)
    return OwnedDirectory(path,token)


def _registered_references(run):
    if not (run/'manifest.json').is_file():return set()
    from ._candidate_evidence import capture_bound_identities
    snapshot=ManifestStore.open(run).snapshot()
    identities=capture_bound_identities(snapshot,run=run)
    references={identity.path for identity in identities.values()}
    # Stage/unit artifacts use the historical artifact shape, not FileIdentity.
    for record in [*snapshot['stages'].values(),*(record for units in snapshot['units'].values() for record in units.values())]:
        for artifact in record['artifacts']:
            path=_local(run,Path(artifact['path']));identity=hash_file(path)
            if (identity.bytes,identity.sha256)!=(artifact['bytes'],artifact['sha256']):
                raise OSError('registered artifact changed before cleanup')
            references.add(str(path))
            if path.suffix.lower()=='.json':
                references.update(value.path for value in capture_bound_identities({'artifact':thaw(identity)},run=run).values())
    return references


def cleanup_owned_temporaries(run_dir, registrations, *, referenced=(), created_directories=()):
    run = _run_path(run_dir)
    registrations = tuple(registrations)
    references = _registered_references(run)|{fresh_identity(value).path for value in referenced}
    selected = []
    for registration in registrations:
        if (not isinstance(registration, OwnedTemporary) or type(registration.ephemeral) is not bool
                or _CREATED_FILES.get(registration._token)!=(run,registration.identity)):
            raise ValueError('explicit temporary registration required')
        if not registration.ephemeral:
            continue
        record = thaw(registration.identity)
        path = _local(run, Path(record['path']))
        relative = path.relative_to(run)
        if (relative.parts[0] in ('logs', 'workflows', 'shots', 'audio', 'staging', 'references')
                or path.suffix.lower() in ('.json', '.jsonl', '.wav', '.png', '.mp4', '.srt', '.ass')
                or path.name.startswith('.') or path.name == 'script.txt'):
            raise ValueError('permanent provenance/media cannot be cleaned')
        if str(path) in references:
            continue
        fresh_identity(registration.identity)
        if path in selected:
            raise ValueError('duplicate temporary registration')
        selected.append(path)
    directories=[]
    for directory in created_directories:
        if not isinstance(directory,OwnedDirectory):raise ValueError('exclusive directory creation proof required')
        path=_local(run,directory.path);stat=path.stat()
        if _CREATED_DIRS.get(directory._token)!=(run,path,stat.st_ino,stat.st_ctime_ns):
            raise ValueError('directory ownership changed')
        if path==run or path.name in ('logs','workflows','shots','audio','staging','references'):
            raise ValueError('permanent run directory cannot be cleaned')
        directories.append(directory)
    # Check every file before the first deletion, then recheck at each mutation.
    by_path = {Path(thaw(r.identity)['path']): r for r in registrations}
    for path in selected:
        fresh_identity(by_path[path].identity)
        _local(run, path).unlink()
        _CREATED_FILES.pop(by_path[path]._token)
    for directory in directories:
        path = _local(run,directory.path);stat=path.stat()
        if _CREATED_DIRS.get(directory._token)!=(run,path,stat.st_ino,stat.st_ctime_ns):
            raise ValueError('directory ownership changed')
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            _CREATED_DIRS.pop(directory._token)
    return tuple(selected)
