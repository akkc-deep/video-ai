"""Actual image review admission; technical validation never supplies approval."""
import hashlib
import json
from pathlib import Path

from ..config import read_json
from .production_state import ProductionRefused,write_exclusive


def review_binding(storyboard,images):
    if [s['shot_id'] for s in storyboard['shots']]!=[r['shot_id'] for r in images['images']]:
        raise ProductionRefused('visual review image coverage differs')
    rows=[]
    for shot,row in zip(storyboard['shots'],images['images']):
        path=Path(row['image']['path'])
        rows.append(dict(shot_id=shot['shot_id'],path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source_requirements=storyboard.get('historical_requirements',{}).get(shot['shot_id'],shot['visual_requirements'])))
    digest=hashlib.sha256(json.dumps(storyboard,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return dict(storyboard_sha256=digest,images=rows)


def require_image_review(run,storyboard,images):
    run=Path(run);binding=review_binding(storyboard,images)
    review=run/'production/visual-review.json'
    if not review.exists():
        draft=run/'production/visual-review-required.json';draft.parent.mkdir(parents=True,exist_ok=True)
        if not draft.exists():write_exclusive(draft,dict(schema_version=1,status='review_required',
            actual_image_semantics='unverified',binding=binding,
            instruction='Inspect actual PNGs against every original source requirement and cross-shot appearance. '
                'Supply visual-review.json only after actual viewing. Technical checks cannot approve semantics.'))
        raise ProductionRefused('actual image visual review required before any Wan batch; see '+str(draft))
    record=read_json(review)
    expected={'schema_version','review_method','reviewer','viewed_images','verdict','reason','binding'}
    if (set(record)!=expected or type(record['schema_version']) is not int or record['schema_version']!=1
        or record['review_method'] not in ('human_image','agent_image') or record['viewed_images'] is not True
        or record['verdict']!='passed' or any(not isinstance(record[k],str) or not record[k].strip() for k in ('reviewer','reason'))):
        raise ProductionRefused('actual image visual review is missing, failed or unverified')
    if record['binding']!=binding:raise ProductionRefused('visual review binding differs from actual images/storyboard')
    # Freeze approval as evidence, not just a transient boolean. Generation
    # reports/checkpoints bind both the author file and this accepted snapshot.
    accepted=run/'production/visual-review-accepted.json'
    digest=hashlib.sha256(review.read_bytes()).hexdigest()
    receipt=dict(schema_version=1,review_path=str(review),review_sha256=digest,record=record)
    if accepted.exists():
        if read_json(accepted)!=receipt:raise ProductionRefused('accepted visual review evidence changed')
    else:write_exclusive(accepted,receipt)


def require_preview_observation(run,storyboard,images):
    """Permit reviewed experiments, with failed findings preserved as failed.

    This is exclusively for the 3-5 shot preview script, never make-video.
    An observation is NOT an approval receipt and cannot admit production.
    """
    run=Path(run)
    if not 3<=len(storyboard['shots'])<=5:raise ProductionRefused('only 3 to 5 bounded preview shots allowed')
    path=run/'samples'/('image-revision-observation.json' if (run/'samples/images-revision.json').exists() else 'image-observation.json')
    if not path.exists():raise ProductionRefused('actual image observation required before preview videos')
    record=read_json(path)
    fields={'schema_version','scope','review_method','reviewer','viewed_images','verdict','binding','observations'}
    if (set(record)!=fields or type(record['schema_version']) is not int or record['schema_version']!=1
        or record['scope']!='preview_only' or record['review_method'] not in ('agent_image','human_image')
        or record['viewed_images'] is not True or record['verdict'] not in ('passed','failed','unverified')
        or not isinstance(record['reviewer'],str) or not record['reviewer'].strip()):
        raise ProductionRefused('invalid bounded preview observation')
    if record['binding']!=review_binding(storyboard,images):raise ProductionRefused('preview observation binding changed')
    observations=record['observations']
    if (not isinstance(observations,list) or [r.get('shot_id') for r in observations]!=[s['shot_id'] for s in storyboard['shots']]
        or any(set(r)!={'shot_id','observation'} or not isinstance(r['observation'],str) or not r['observation'].strip() for r in observations)):
        raise ProductionRefused('preview requires per-image actual observations')
    return path
