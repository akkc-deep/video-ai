"""Explicit revised inference settings retain the installed fixed TTS baseline."""
from dataclasses import dataclass,field
from pathlib import Path

from ..config import load_config,read_json
from ..planning.recovery import validate_changes
from .manifest import ManifestStore,FileIdentity,hash_file,thaw
from .pipeline_import import load_pipeline_import,fresh,same_identity

_SEAL=object()


@dataclass(frozen=True)
class VoiceRevision:
    run_dir: Path
    changes_identity: FileIdentity
    baseline_identity: FileIdentity
    _seal: object=field(default=None,repr=False,compare=False)


def voice_revision(config,run,script):
    snapshot=ManifestStore.open(run).snapshot()
    if 'pipeline_import' not in snapshot['workflows']:return None
    receipt=load_pipeline_import(run)
    parent=run.parent/receipt['parent_run_id'];old=ManifestStore.open(parent).snapshot()
    if receipt['changes_identity'] is None:
        if old['inputs'].get('voice_revision') is None:return None
        verify_reused_voice(config,parent,{})
        original=load_config(Path(old['config_snapshot']['path']))
        inherited=voice_revision(original,parent,Path(fresh(old['inputs']['script']).path))
        if inherited is None:raise ValueError('inherited voice revision has no sealed original author')
        for identity in (inherited.changes_identity,inherited.baseline_identity):
            bound=receipt['source_identities'].get(identity.path)
            if bound is None or not same_identity(identity,fresh(bound)):raise ValueError('inherited voice authorization absent from current import closure')
        for key,path in (('config',config.config_file),('voice',config.voice.config_file),('script',script)):
            if Path(fresh(snapshot['inputs'][key]).path)!=Path(path):raise ValueError('inherited voice current input differs')
        return VoiceRevision(run,inherited.changes_identity,inherited.baseline_identity,_SEAL)
    identity=fresh(receipt['changes_identity']);changes=read_json(Path(identity.path))
    board=read_json(parent/'storyboard.json') if (parent/'storyboard.json').exists() else {'shots':[]}
    validate_changes(changes,run_id=parent.name,shot_ids=tuple(s['shot_id'] for s in board['shots']))
    if not same_identity(hash_file(config.config_file),changes['config_identity']):raise ValueError('revised voice current config is not author-bound')
    for key,path in (('config',config.config_file),('voice',config.voice.config_file),('script',script)):
        if Path(fresh(snapshot['inputs'][key]).path)!=Path(path):raise ValueError('revised speech input path differs')
    baseline=old['inputs'].get('voice_revision_baseline',old['inputs'].get('voice'))
    if baseline is None:raise ValueError('revised voice requires the original installed voice baseline')
    return VoiceRevision(run,identity,fresh(baseline),_SEAL)


def verify_revision(config,script,revision):
    if not isinstance(revision,VoiceRevision) or revision._seal is not _SEAL:raise ValueError('voice revision requires a consumed author request')
    current=voice_revision(config,revision.run_dir,script)
    if current is None or not same_identity(current.changes_identity,revision.changes_identity) or not same_identity(current.baseline_identity,revision.baseline_identity):
        raise ValueError('voice revision origin changed')
    return current


def revised_voice_files(revision,files):
    """Require every current voice leaf in this consumed import closure."""
    receipt=load_pipeline_import(revision.run_dir);result={}
    for name,path in files.items():
        identity=hash_file(path);bound=receipt['source_identities'].get(identity.path)
        if bound is None or not same_identity(identity,fresh(bound)):raise ValueError('current revised voice leaf absent from immutable author closure: '+name)
        result[name]=identity
    return result


def verify_reused_voice(config,parent,identities):
    """Full imported PCM must match the child's current voice semantics."""
    original=load_config(Path(ManifestStore.open(parent).snapshot()['config_snapshot']['path'])).voice
    old,new=thaw(original),thaw(config.voice)
    paths=('gpt_weights','sovits_weights','bert_root','hubert_root','reference_audio')
    for value in (old,new):
        for key in ('config_file','raw',*paths):value.pop(key,None)
    if old!=new:raise ValueError('reused speech current voice parameters differ from original')
    for name in paths:
        a,b=Path(getattr(original,name)),Path(getattr(config.voice,name))
        if name.endswith('_root'):
            if not a.is_dir() or not b.is_dir() or a.resolve()!=a or b.resolve()!=b:raise ValueError('reused voice model directory redirected')
            left={p.relative_to(a).as_posix():p for p in a.rglob('*') if p.is_file()}
            right={p.relative_to(b).as_posix():p for p in b.rglob('*') if p.is_file()}
            if set(left)!=set(right):raise ValueError('reused voice model content coverage differs')
            pairs=tuple((left[key],right[key]) for key in sorted(left))
        else:pairs=((a,b),)
        for left,right in pairs:
            x=hash_file(left);y=x if left==right else hash_file(right)
            if (x.bytes,x.sha256)!=(y.bytes,y.sha256):raise ValueError('reused speech current voice content differs')
            identities['voice-current/'+y.path]=y
