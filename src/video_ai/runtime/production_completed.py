"""Read-only reconciliation of a completed automatic production prefix."""
from pathlib import Path
from ..config import read_json
from ..adapters.common import strict_json
from ..adapters.ollama import parse_completed_response, OllamaFormatError
from ..planning.production_timeline import ProductionTimeline
from ..planning.production_timing import AutomaticSlotPlan, validate_automatic_slots
from .production_state import ArtifactStamp, ProductionRefused, run_path
from .production_support import read_report, recover_http
from .production_inputs import _verify_identity
from .production_comfy import _local_histories, output_from_history, same
from .workflows import WorkflowTemplate


def validate_completed_prefix(frozen,state,manifest,logger):
    run=state.run_dir;snapshot=state.snapshot();backing=manifest.snapshot()
    reports={stage:read_report(state,stage) for stage in snapshot['stages'] if snapshot['stages'][stage]['status']=='completed'}
    units=reports['units']['payload']
    if units['decoded_text']!=frozen.script.text or units['has_bom']!=frozen.script.has_bom:
        raise ProductionRefused('completed units differ from frozen original text')
    timeline=ProductionTimeline.from_dict(reports['timeline']['payload'])
    slots=read_json(run/'logs/production/checkpoints/timeline/automatic-slots.json')['payload']
    from .production_timeline import parse_estimate
    timing=read_json(run/'production/timing.json')
    estimates={row['unit_id']:parse_estimate(row['estimate']) for row in timing['payload']['units']}
    validate_automatic_slots(timeline,AutomaticSlotPlan.from_dict(slots),estimates)
    for stage in ('speech','timeline','storyboard','start_images','source_clips','upscale','composition'):
        if backing['stages'][stage]['status']!='completed':raise ProductionRefused('manifest completed prefix disagrees')
    templates={role:WorkflowTemplate.load(Path(frozen.options['workflow_snapshots'][role]['path']),
        Path(frozen.options['workflow_snapshots'][role+'_mapping']['path']),frozen.config.models) for role in ('sdxl','wan','upscale')}
    speech_rows={row['unit_id']:row for row in reports['speech']['payload']['spans'] if row['kind']=='speech'}
    images={row['shot_id']:row for row in reports['start_images']['payload']['images']}
    sources={row['shot_id']:row for row in reports['source_clips']['payload']['clips']}
    frame_rows={f'{clip["shot_id"]}:frame_{row["frame_index"]:06d}':row for clip in reports['upscale']['payload']['clips'] for row in clip['frames']}
    for stage,records in snapshot['units'].items():
        if stage=='delivery':continue
        for uid,record in records.items():
            if record['status']!='completed':raise ProductionRefused('completed prefix has unfinished unit')
            cp=read_json(run_path(run,record['checkpoint_path']));req=cp['request']
            if req is None:continue
            intent=read_json(run_path(run,req['intent_path']))
            if stage in ('units','storyboard'):
                if intent['context']['client_id']!=req['client_id']:raise ProductionRefused('completed planner client differs')
                raw,_,_=recover_http(logger,uid=uid,url=frozen.config.services['ollama']+'/api/generate',payload=intent['body'],evidence_paths=req['response_paths'])
                try:content=parse_completed_response(strict_json(raw),schema=intent['schema'],request_id=uid,evidence_paths=req['response_paths'])
                except OllamaFormatError:
                    if cp['payload']['format_valid']:raise ProductionRefused('completed planner result differs')
                else:
                    key='proposal' if stage=='units' else 'content'
                    if cp['payload']['format_valid'] and cp['payload'][key]!=content:raise ProductionRefused('completed planner content changed')
            elif stage=='speech':
                if intent['client_id']!=req['client_id'] or intent['text']!=cp['payload']['text'] or cp['payload']['span']!=speech_rows.get(uid):
                    raise ProductionRefused('completed speech request/report differs')
            elif stage in ('start_images','source_clips','upscale'):
                role,kind,mid=('sdxl','image',uid) if stage=='start_images' else ('wan','shot_attempt',uid+':attempt_0001') if stage=='source_clips' else ('upscale','frame',uid)
                saved=backing['units'].get(kind,{}).get(mid,{}).get('submission')
                if saved is None or saved['state']!='completed' or any(req[k]!=saved[v] for k,v in (('intent_path','request_path'),('client_id','client_id'),('prompt_id','prompt_id'))):
                    raise ProductionRefused('original Comfy submission identity changed')
                _verify_identity(backing['workflows'][saved['attempt_id']],run)
                template=templates[role]
                if stage=='start_images':
                    p=cp['payload']['parameters'];prefix=f'{run.name}/start_images/{uid}/attempt_0001'
                    graph=template.instantiate(dict(positive_prompt=p['positive'],negative_prompt=p['negative'],seed=p['seed'],width=p['width'],height=p['height']),output_prefix=prefix)
                    if images.get(uid)!=cp['payload']:raise ProductionRefused('completed image report differs')
                elif stage=='source_clips':
                    p=cp['payload']['clip']['parameters'];prefix=f'{run.name}/source_clips/{uid}/attempt_0001'
                    graph=template.instantiate(dict(positive_prompt=p['positive'],start_image=f'{run.name}/source_clips/{uid}/start.png',
                        width=p['width'],height=p['height'],length=p['length'],fps=p['fps'],seed_high=p['seed_high'],seed_low=p['seed_low']),output_prefix=prefix)
                    if sources.get(uid)!=cp['payload']['clip']:raise ProductionRefused('completed source report differs')
                else:
                    shot,index=uid.split(':');prefix=f'{run.name}/upscale/{shot}/{index}'
                    graph=template.instantiate(dict(image=prefix+'.png'),output_prefix=prefix)
                    row=frame_rows.get(uid)
                    if row is None or any(row[k]!=cp['payload'][k] for k in ('frame_index','source_frame_index','input','input_copy','output','submission')):
                        raise ProductionRefused('completed upscale report differs')
                if not same(intent,graph):raise ProductionRefused('completed graph differs from original parameters')
                found=[]
                for history,_ in _local_histories(logger,mid,req['response_paths']):
                    entry=history.get(req['prompt_id'])
                    if entry is not None:
                        target=output_from_history(entry,saved,graph,template,run,prefix,'.mp4' if role=='wan' else '.png')
                        if target is not None:found.append(target)
                if not found or any(ArtifactStamp.read(p).to_dict()!=cp['outputs']['model_output'] for p in found):
                    raise ProductionRefused('completed original history/output association changed')
    return reports
