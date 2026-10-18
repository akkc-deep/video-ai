"""Strict run-local author inputs and independently reconstructed final gates."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from ..config import read_json
from ..planning.final_review import validate_final_review, validate_acceptance
from .manifest import hash_file, thaw, _identity
from .timeline_checks import _local, _again


def equal_identity(a,b):
    for record in (a,b):
        _identity(record)
        if any(v is None for v in record.values()):raise ValueError('complete file identity required')
        if datetime.fromisoformat(record['verified_at'])>datetime.now().astimezone():raise ValueError('future identity verification time')
    return all(a[k]==b[k] for k in ('path','bytes','mtime_ns','sha256'))


def fresh(record,*,run=None,expected=None):
    _identity(record)
    path=Path(record['path'])
    if run is not None:path=_local(run,path)
    if expected is not None and path!=expected:raise ValueError('unexpected identity path')
    if path.resolve(strict=True)!=path:raise ValueError('redirected identity path')
    identity=hash_file(path)
    if not equal_identity(record,thaw(identity)):raise OSError('file identity changed: '+str(path))
    return identity


def author_path(run,path):
    path=_local(run,Path(path).absolute())
    root=_local(run,run/'logs/validation')
    if not path.is_relative_to(root) or path==root or path.suffix!='.json':raise ValueError('author input must be JSON in this run logs/validation')
    return path


def load_final_review(run,candidate,review_path,*,acceptance_path=None):
    candidate_id=hash_file(_local(run,run/'candidate-validation.json'))
    candidate=deepcopy(candidate);candidate['candidate_validation_identity']=thaw(candidate_id)
    review_path=author_path(run,review_path)
    acceptance_path=author_path(run,acceptance_path) if acceptance_path is not None else None
    if review_path==acceptance_path:raise ValueError('review and acceptance author files must be distinct')
    review_id=hash_file(review_path);review=read_json(review_path)
    collection={review_path.relative_to(run).as_posix():thaw(review_id)}
    identities={'candidate_validation':candidate_id,'review':review_id}
    # The shared verified closure follows composition/source reports too: their
    # frame contributors need to stay fresh through this final manifest gate.
    from ._candidate_evidence import capture_bound_identities
    identities.update(capture_bound_identities(candidate,run=run))
    observations={};cue_observations={}
    for field,destination in [('entries',observations),('cue_entries',cue_observations)]:
        rows=review.get(field,[])
        if not isinstance(rows,list):raise ValueError('review entries must be a list')
        for row in rows:
            if not isinstance(row,dict) or 'evidence_identity' not in row:continue
            record=row['evidence_identity'];path=author_path(run,Path(record['path']))
            if path in (review_path,acceptance_path):raise ValueError('observation must be a distinct author file')
            identity=fresh(record,run=run,expected=path);key=path.relative_to(run).as_posix()
            if key in (cue_observations if destination is observations else observations):raise ValueError('continuous and cue observations must be distinct files')
            if key not in destination:destination[key]=read_json(path)
            collection[key]=thaw(identity);identities[key]=identity
    timeline_id=fresh(candidate['input_identities']['timeline'],run=run)
    timeline=read_json(Path(timeline_id.path));identities['timeline']=timeline_id
    validation=dict(candidate['validation'])
    validation.update(validate_final_review(review,candidate,timeline,observations=observations,cue_observations=cue_observations))
    _again(identities)
    return dict(candidate=candidate,review=review,identities=identities,
                collection=collection,validation=validation,candidate_identity=thaw(candidate_id),
                review_identity=thaw(review_id))


def load_gate(run,candidate,review_path,acceptance_path):
    gate=load_final_review(run,candidate,review_path,acceptance_path=acceptance_path)
    acceptance_path=author_path(run,acceptance_path);acceptance_id=hash_file(acceptance_path)
    acceptance=read_json(acceptance_path)
    gate['validation'].update(validate_acceptance(acceptance,gate['candidate'],
        dict(gate['review'],final_review_identity=gate['review_identity']),gate['collection']))
    gate.update(acceptance=acceptance,acceptance_identity=thaw(acceptance_id))
    gate['identities']['acceptance']=acceptance_id
    _again(gate['identities'])
    return gate
