"""Fresh author records. These readers never infer an author's verdict."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from ..config import read_json
from ..planning.segments import SegmentedScript
from ..planning.speech_semantics import validate_reviewed_spans, reviewed_timestamp, _keys, _text
from .manifest import FileIdentity, ManifestStore, hash_file, thaw, now, _identity
from .timeline_checks import _run_path, _local, _again
from .paths import PathPolicy, _validate_spelling

ROLES=('voice_acceptance','timing','visual_contract','storyboard','start_images','source_clips','upscale','final_review','full_film_acceptance')


def fresh_identity(record, *, expected=None, run=None):
    _identity(record,artifact='category' in record)
    reviewed_timestamp(record['verified_at'])
    path=Path(record['path'])
    if run is not None: path=_local(run,path)
    else:
        # Check spelling and redirects on each use, before hash_file resolves it.
        validated=Path(_validate_spelling(path)).resolve(strict=True)
        if validated != path: raise ValueError('noncanonical author input path')
    if expected is not None and path != Path(expected): raise ValueError('author identity path mismatch')
    actual=hash_file(path)
    keys=('path','bytes','sha256') if 'category' in record else ('path','bytes','mtime_ns','sha256')
    if any(getattr(actual,k)!=record[k] for k in keys): raise OSError(f'author input identity changed: {path}')
    return actual


@dataclass(frozen=True)
class ReviewedSpeech:
    script: SegmentedScript
    identity: FileIdentity
    script_identity: FileIdentity
    review: object


def load_unit_review(path, *, script_path, run_dir=None) -> ReviewedSpeech:
    path=Path(path).absolute(); script_path=Path(script_path).absolute()
    if run_dir is not None:
        run=_run_path(run_dir); path=_local(run,path)
        if path != run/'logs/pipeline/unit-review.json': raise ValueError('canonical run unit-review required')
    identity=hash_file(path); review=read_json(path)
    source=fresh_identity(review.get('script_identity'),expected=script_path)
    parsed=SegmentedScript.read(script_path)
    spans=validate_reviewed_spans(parsed.text,review)
    _again({'unit_review':identity,'source':source})
    return ReviewedSpeech(SegmentedScript(parsed.text,parsed.has_bom,spans),identity,source,MappingProxyType(review))


def load_reviews(run_dir, path=None):
    run=_run_path(run_dir)
    if path is None: return MappingProxyType({})
    path=_local(run,Path(path).absolute())
    if path.parent!=run/'logs/pipeline' or path.suffix!='.json': raise ValueError('review index must be a run pipeline JSON')
    identity=hash_file(path); data=read_json(path)
    _keys(data,'schema_version run_id created_at entries')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name:
        raise ValueError('review index schema/run mismatch')
    reviewed_timestamp(data['created_at'])
    if not isinstance(data['entries'],dict) or set(data['entries'])-set(ROLES): raise ValueError('unknown review role')
    identities={'index':identity}; results={}; seen=set()
    for role,record in data['entries'].items():
        current=fresh_identity(record,run=run)
        author=Path(current.path)
        canonical={'visual_contract':run/'logs/storyboard/visual-contract.json',
            'start_images':run/'logs/start-images/semantic-review.json','source_clips':run/'logs/source-clips/semantic-review.json',
            'upscale':run/'logs/upscale/semantic-review.json'}
        if role in canonical and author!=canonical[role]:raise ValueError('review role requires its canonical author path')
        if role in ('timing','storyboard') and author.parent!=run/'logs/storyboard':raise ValueError('storyboard author review must be in logs/storyboard')
        if role in ('final_review','full_film_acceptance') and (not author.is_relative_to(run/'logs/validation') or author.suffix!='.json'):
            raise ValueError('final author review must be JSON in logs/validation')
        normalized=current.path.casefold()
        if normalized in seen: raise ValueError('duplicate review path')
        seen.add(normalized); identities[role]=current; results[role]=Path(current.path)
    _again(identities)
    return MappingProxyType(results)


def validate_voice_acceptance(run, data, report, segments_identity):
    _keys(data,'schema_version run_id segments_identity reference_identity preview_identity audio_identities review_method reviewer reviewed_at listened accepted user_statement')
    if (type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name
            or data['review_method']!='human_audio' or data['listened'] is not True or data['accepted'] is not True):
        raise ValueError('current voice acceptance requires human audio listening and acceptance')
    _text(data['reviewer']);_text(data['user_statement']);reviewed_timestamp(data['reviewed_at'])
    identities={}
    expected={'segments_identity':segments_identity.path,'reference_identity':report['reference_replay']['pcm']['path'],
        'preview_identity':report['listening_preview']['identity']['path']}
    for key,path in expected.items():identities['acceptance/'+key]=fresh_identity(data[key],run=run,expected=Path(path))
    if identities['acceptance/segments_identity'].sha256!=segments_identity.sha256:raise ValueError('voice acceptance segments mismatch')
    speech=[s for s in report['spans'] if s['kind']=='speech']
    if not isinstance(data['audio_identities'],list) or len(data['audio_identities'])!=len(speech):raise ValueError('voice acceptance audio coverage')
    for item,span in zip(data['audio_identities'],speech):
        _keys(item,'unit_id text raw pcm samples')
        if (item['unit_id']!=span['unit_id'] or item['text']!=span['text'] or type(item['samples']) is not int
                or item['samples']!=span['samples']):raise ValueError('voice acceptance original text/samples/order mismatch')
        for key in ('raw','pcm'):
            bound=fresh_identity(item[key],run=run,expected=Path(span[key]['path']))
            actual=fresh_identity(span[key],run=run)
            if (bound.bytes,bound.sha256)!=(actual.bytes,actual.sha256):raise ValueError('voice acceptance audio mismatch')
            identities[f'acceptance/{span["unit_id"]}/{key}']=bound
    _again(identities);return identities


def accept_voice_review(config, run_dir, path) -> FileIdentity:
    """Bind a human's exact current audio review to a new immutable receipt."""
    from .speech_checks import load_committed_speech
    run=_run_path(run_dir);path=_local(run,Path(path).absolute());store=ManifestStore.open(run)
    if 'voice_acceptance' in store.snapshot()['workflows']:raise ValueError('voice acceptance already registered')
    loaded=load_committed_speech(run);identity=hash_file(path);data=read_json(path)
    identities=validate_voice_acceptance(run,data,loaded['report'],loaded['input_identities']['segments'])
    identities.update(loaded['input_identities']);identities['author']=identity
    _again(identities)
    target=_local(run,run/'logs/pipeline'/f'voice-acceptance-{uuid4().hex}.json');target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8',newline='\n') as file:
        json.dump(data,file,ensure_ascii=False,allow_nan=False,indent=2);file.flush();os.fsync(file.fileno())
    receipt=hash_file(target)
    if read_json(target)!=data:raise OSError('voice receipt readback differs')
    _again(identities);_again({'receipt':receipt})
    store.update(lambda snapshot:snapshot['workflows'].update(voice_acceptance=thaw(receipt)))
    return receipt
