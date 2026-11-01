"""Independent certificate validation; never reruns or tunes the detector."""
from datetime import datetime
from pathlib import Path
import math


def _ref(ref):
    if not isinstance(ref,dict) or not all(k in ref for k in ('path','bytes','mtime_ns','sha256')):
        raise ValueError('invalid file reference')
    return {k:ref[k] for k in ('path','bytes','mtime_ns','sha256')}


def verify_case_binding(*,case,receipt,source,control,control_ref,label,
                        expected_path,input_sha256,seal,seal_time,
                        closure_digest,environment_fingerprint):
    """Validate already-produced evidence against frozen external expectations.

    Callers must check the case/receipt hashes in the evaluation evidence and
    all frozen source references before calling. This validates relational
    integrity, not independent physical truth of the AI label or producer.
    """
    assert Path(receipt['output']['path'])==Path(expected_path),'wrong producer output'
    assert case['input_sha256']==receipt['input_sha256']==input_sha256,'wrong inputs'
    assert receipt['environment_fingerprint']==environment_fingerprint,'wrong environment'
    assert receipt['source_closure_digest']==closure_digest,'wrong source closure'
    assert receipt['provider_closed'] is True and case['measurement_completed'] is True
    assert case['production_eligible'] is False
    entry=source['entry'];sid=entry['source_id'];variant=control['variant']
    assert case['source_id']==control['source_id']==label['source_id']==sid
    assert case['variant']==label['variant']==variant
    assert case['case_id']==sid+'__'+variant
    assert case['split']==control['split']==entry['split']
    assert _ref(case['control'])==_ref(control_ref)
    assert any(_ref(ref)==_ref(control_ref) for ref in source['controls'])
    assert _ref(case['pack'])==_ref(source['pack'])
    row=case['row'];result=case['result']
    expected=dict(case_id=case['case_id'],source_id=sid,variant=variant,
        genre=entry['genre'],group=entry['scene_group'],source_kind=entry['source_kind'],
        detector_id='temporal_replay',region_id='fixed_clip_start_ROI',
        label=label['final_label'],score=result['score'],state=result['state'])
    assert row==expected,'row differs from frozen label or measured result'
    if result['state']=='comparable':
        assert type(result['score']) in (float,int) and math.isfinite(result['score']) and 0<=result['score']<=1
        assert result['reason']=='measured'
    else:
        assert result['state']=='unverified' and result['score'] is None
        assert result['reason'] in ('insufficient_lookahead','insufficient_history','invalid_support',
            'insufficient_texture','insufficient_motion','timing_mismatch','ambiguous_periodicity','phase_continuous')
    start=datetime.fromisoformat(case['measurement_started_at']);end=datetime.fromisoformat(case['measurement_finished_at'])
    assert end>=start
    if entry['split']=='new_check':
        assert seal is not None and seal_time is not None
        assert _ref(case['threshold_seal'])==_ref(receipt['threshold_seal'])==_ref(seal)
        assert start>datetime.fromisoformat(seal_time),'new check preceded seal'
    else:
        assert entry['split']=='calibration' and case['threshold_seal'] is None and receipt['threshold_seal'] is None and seal is None
    return True


def describe_rows(rows,threshold):
    """Expose denominators omitted by legacy metrics, keeping source clusters."""
    from video_ai.media.continuity_calibration import _wilson
    labeled=[r for r in rows if r['label'] in ('normal','anomaly')]
    comparable=lambda r:r['state']=='comparable' and r['score'] is not None
    classified=[r for r in labeled if comparable(r)]
    measured=[r for r in rows if comparable(r)]
    works=sorted({r['source_id'] for r in labeled if r['label']=='anomaly'})
    successes=0
    for sid in works:
        positives=[r for r in labeled if r['source_id']==sid and r['label']=='anomaly']
        successes+=all(comparable(r) and r['score']>threshold for r in positives)
    return dict(total_cases=len(rows),labeled_cases=len(labeled),classified_labeled_cases=len(classified),
        labeled_abstentions=len(labeled)-len(classified),excluded_label_unverified=sum(r['label']=='unverified' for r in rows),
        measured_all_cases=len(measured),labeled_coverage=len(classified)/len(labeled) if labeled else None,
        all_case_measurement_coverage=len(measured)/len(rows) if rows else None,positive_original_works=len(works),
        all_positive_variants_detected_works=successes,source_success_wilson_descriptive=_wilson(successes,len(works)),
        interval_interpretation='Nominal row intervals are correlated; do not infer source generalization from variant count.',
        source_interval_limit='Descriptive small-source summary; filming/creator independence and representativeness are not certified.')
