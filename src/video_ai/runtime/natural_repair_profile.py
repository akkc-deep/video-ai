"""Read-only natural profile authority, replayed against complete frozen evidence."""
from pathlib import Path
from .natural_study_records import StudyReader,fields,timestamp
from .production_state import ProductionRefused


def load_natural_repair_profile(path,*,reader=None):
    from . import natural_study as s
    r=reader or StudyReader();ref=r.cap(path);p=Path(ref['path'])
    if p.name!='natural-repair-profile.json': raise ProductionRefused('explicit natural profile required')
    value=r.any(ref);fields(value,s.PROFILE_FIELDS)
    root,receipt,req,config,conditional=s._frozen(p.parent)
    eref,evaluation,holdout,sealed=s._evaluation(root,receipt,req,config,conditional,replay=True)
    dev_ref,_,dev=s._index(root,receipt,req,config,conditional,'development')
    if dev_ref!=sealed['development']: raise ProductionRefused('development index changed during profile replay')
    r=StudyReader();r.cap(ref)
    final=r.any(root/'finalization.json')
    if final['status']!='qualified' or final['profile']!=ref or final['evaluation']!=eref:
        raise ProductionRefused('natural profile lacks qualified finalization identity')
    passed,_=s.qualification_reviews(root,dev+holdout,eref,final['observations'])
    directions,domains=s.qualified_scope(dev,holdout,evaluation,passed)
    expected=dict(schema_version=1,algorithm=s.ALGORITHM,purpose='offline_natural_repair_qualification',production_eligible=False,
        evidence_only=True,protocol=receipt['protocol'],inputs=receipt['inputs'],software=receipt['software'],
        conditional_profile=req['conditional_profile'],thresholds=r.cap(root/'thresholds.SEALED.json'),evaluation=eref,
        qualified_domains=sorted(domains),qualified_directions=directions,limitations=s.LIMITATIONS,created_at=final['created_at'])
    if not directions or not domains or value!=expected: raise ProductionRefused('natural profile differs from replayed qualification')
    if timestamp(value['created_at'])<timestamp(evaluation['created_at']): raise ProductionRefused('profile predates evaluation')
    r.verify_all()
    if reader is not None: reader.cap(ref)
    return value


def direction_thresholds(profile,operation,direction,*,domain):
    if domain not in profile['qualified_domains'] or dict(operation=operation,correction_direction=direction) not in profile['qualified_directions']:
        raise ProductionRefused('natural domain/direction is unqualified')
    sealed=StudyReader().any(profile['thresholds'])
    return sealed['directions'][operation+':'+direction]['thresholds']
