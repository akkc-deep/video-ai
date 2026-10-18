"""Durable automatic timeline, envelope report and complete numeric shot slots."""
from dataclasses import fields
from pathlib import Path

from ..config import read_json
from ..media.timing import EnvelopeEstimate, measure_envelope
from ..planning.production_timeline import ProductionTimeline, build_production_timeline
from ..planning.production_timing import AutomaticSlotPlan, build_automatic_slots, validate_automatic_slots
from ..planning.segments import SegmentedScript, TextSpan
from .manifest import now, thaw
from .production_inputs import check_stage_space
from .production_state import (ArtifactStamp, ProductionRefused, object_fields, run_path,
                               validate_report, write_exclusive)
from .production_support import commit_checkpoint, read_report, recover_checkpoint, stamps, sync_manifest_stage


def parse_estimate(data):
    object_fields(data,[f.name for f in fields(EnvelopeEstimate)],'envelope estimate')
    data=dict(data)
    for key in ('thresholds','threshold_boundaries','verified_internal_silences'):
        if not isinstance(data[key],list): raise ProductionRefused('envelope ranges must be JSON arrays')
        data[key]=tuple(tuple(x) if isinstance(x,list) else x for x in data[key])
    return EnvelopeEstimate(**data)


def produce_timeline(frozen,units,audio,*,state,manifest,paths,logger):
    report=read_report(state,'timeline')
    complete=state.snapshot()['stages']['timeline']['status']=='completed'
    if not complete: state.start_stage('timeline');check_stage_space(frozen.config)
    script=SegmentedScript(frozen.script.text,frozen.script.has_bom,tuple(TextSpan(**s) for s in units['spans']))
    timeline=build_production_timeline(script,audio,settings=frozen.config.media.timeline,fps=16)
    if report:
        persisted=ProductionTimeline.from_dict(report['payload'])
        if persisted.as_dict()!=timeline.as_dict(): raise ProductionRefused('timeline differs from original speech/units')
    elif complete: raise ProductionRefused('timeline completed cursor has no report')
    # Speech checkpoints already own measured original envelopes; compare auxiliary timing to them.
    estimates={}
    for clip in timeline.clips:
        path=run_path(state.run_dir,state.run_dir/f'logs/production/checkpoints/speech/{clip.unit_id}.json')
        cp=read_json(path)
        estimates[clip.unit_id]=parse_estimate(cp['payload']['estimate'])
        if estimates[clip.unit_id].samples!=clip.samples: raise ProductionRefused('speech envelope sample count differs')
    plan=build_automatic_slots(timeline,estimates)
    timing_path=run_path(state.run_dir,state.run_dir/'production/timing.json')
    timing_payload=dict(algorithm='pcm_envelope_v1',units=[dict(unit_id=c.unit_id,estimate=thaw(estimates[c.unit_id])) for c in timeline.clips])
    if timing_path.exists():
        timing=read_json(timing_path)
        object_fields(timing,('schema_version','execution_mode','run_id','stage','created_at','status','input_records','payload'),'timing report')
        # The timing report is an auxiliary timeline artifact, so it has its own exact payload.
        from .production_state import _header, _stamps
        _header(timing,state.run_dir);_stamps(timing['input_records'],verify=True)
        if timing['stage']!='timeline' or timing['status']!='completed' or timing['payload']!=timing_payload:
            raise ProductionRefused('timing differs from original speech envelopes')
    elif complete: raise ProductionRefused('timeline completed without timing report')
    else:
        write_exclusive(timing_path,dict(schema_version=1,execution_mode='automatic',run_id=state.run_dir.name,
            stage='timeline',created_at=now(),status='completed',input_records=stamps({'speech':state.run_dir/'production/speech.json'}),payload=timing_payload))
    cp=recover_checkpoint(state,'timeline','automatic-slots')
    if cp:
        saved=AutomaticSlotPlan.from_dict(cp['payload']);validate_automatic_slots(timeline,saved,estimates)
        if cp['outputs']!=stamps({'timing':timing_path}): raise ProductionRefused('automatic slots timing identity differs')
    elif complete: raise ProductionRefused('completed timeline lacks automatic slots checkpoint')
    else:
        state.record_unit('timeline','automatic-slots',status='running')
        commit_checkpoint(state,'timeline','automatic-slots',outputs=stamps({'timing':timing_path}),payload=plan.as_dict())
    if not report:
        state.write_report('timeline',timeline.as_dict(),input_records=stamps({'units':state.run_dir/'production/units.json','speech':state.run_dir/'production/speech.json'}))
    if not complete: state.complete_stage('timeline')
    sync_manifest_stage(manifest,'timeline',state.run_dir/'production/timeline.json')
    for cut in plan.cuts: logger.event('timeline',cut.to_unit_id,'automatic_cut',cut.as_dict())
    return timeline,plan
