import argparse,json,sys,time
from pathlib import Path
from collections import Counter
import os
from video_ai.runtime import scene_revision_records as r, verification
from video_ai.runtime.production_inputs import load_frozen_inputs
from video_ai.runtime.production_image_selection import load_prepared_inputs
from video_ai.runtime.scene_clip_records import scene_context
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--limit',type=float,default=90);p.add_argument('--baseline',action='store_true');a=p.parse_args()
run=Path('E:/VideoAI/work/0002-旅行者2号-即梦版/process/revisions/08')
read_opens=Counter(); stable_reads=Counter(); hash_reads=Counter(); hash_bytes=Counter(); byte_reads=Counter(); byte_sizes=Counter()
report={'stages':{},'calls':{},'writes':False,'baseline':a.baseline,'mode':'read-only sealed-input preparation; no observation receipts written'};counts=Counter();start=time.perf_counter()
def audit(event,args):
 if event=='open' and isinstance(args[0],(str,bytes)) and args[2]& (1|2|64|512|1024):
  if Path(args[0]).absolute().is_relative_to(Path('E:/VideoAI/work')):raise RuntimeError('production writes forbidden')
 if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)) and not args[2]& (1|2|64|512|1024):
  read_opens[os.fsdecode(args[0])]+=1
 if event.startswith('socket.'):raise RuntimeError('network forbidden')
sys.addaudithook(audit)
def measure(name,fn):
 t=time.perf_counter()
 before=(read_opens.copy(),stable_reads.copy(),hash_reads.copy(),byte_reads.copy())
 try:return fn()
 finally:
  report['stages'][name]=time.perf_counter()-t
  report.setdefault('io_by_stage',{})[name]={label:dict((counter-old).most_common(25)) for label,counter,old in zip(('read_open_attempts','stable_byte_read_calls','actual_hash_reads','actual_content_reads'),(read_opens,stable_reads,hash_reads,byte_reads),before)}
  report['calls']=dict(counts)
  Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf8')
  print(name,report['stages'][name],flush=True)
# Targeted counters avoid profiling every Python function call.
from functools import wraps
from video_ai.runtime import reference_image_records
from video_ai.planning import production_timeline
def counted(fn):
 @wraps(fn)
 def wrapped(*args,**kwargs):
  counts[fn.__name__]+=1
  if time.perf_counter()-start>a.limit:raise TimeoutError("measurement deadline")
  return fn(*args,**kwargs)
 return wrapped
if a.baseline:
 import subprocess
 original=subprocess.check_output(['git','show','HEAD:src/video_ai/runtime/reference_image_records.py']).decode('utf8')
 prior=original[original.index('def _prior('):original.index('def _format(')]
 exec(prior,reference_image_records.__dict__)
 original=original[original.index('def verify_reference_provenance('):original.index('@revision_read_transaction()',original.index('def verify_reference_provenance('))]
 exec(original,reference_image_records.__dict__)
 # Restore the pre-fix fresh boundary, including overlap between distinct guards.
 exec("""def _verify_read_boundary(state):
    current = dict(active=True, thread=get_ident(), checked=set())
    token = _guard_pass.set(current)
    artifact_token = _artifact_batch.set(None)
    try:
        for expected, read in tuple(state['inputs'].values()):
            if canonical_digest(thaw(read())) != expected:
                raise ProductionRefused('revision local read input changed')
        for guard in tuple(state['checked']):
            guard.verify_captured_bytes()
    finally:
        _artifact_batch.reset(artifact_token)
        current['active'] = False
        _guard_pass.reset(token)
""",r.__dict__)
from video_ai.runtime import manifest
_original_stable=r.stable_bytes
_original_hash=manifest._hash_open_file
def stable_counted(path,**kwargs):
 stable_reads[str(path)]+=1
 return _original_stable(path,**kwargs)
def hash_counted(stream,path):
 hash_reads[str(path)]+=1
 hash_bytes[str(path)]+=path.stat().st_size
 return _original_hash(stream,path)
_original_content=verification._read_open_bytes
def content_counted(file,path):
 value=_original_content(file,path)
 byte_reads[str(path)]+=1
 byte_sizes[str(path)]+=len(value[0])
 return value
verification._read_open_bytes=content_counted
r.stable_bytes=stable_counted
manifest._hash_open_file=hash_counted
reference_image_records.verify_reference_provenance=counted(reference_image_records.verify_reference_provenance)
production_timeline.validate_production_timeline=counted(production_timeline.validate_production_timeline)
try:
 with verification.whole_input_protection(immutable_roots=(run.parent,)),r.revision_scope(),r.revision_artifact_batch(),r.revision_read_transaction():
  frozen=measure('frozen',lambda:load_frozen_inputs(run))
  units,timeline=measure('prepared',lambda:load_prepared_inputs(frozen))
  measure('review_preparation',lambda:scene_context(frozen,units,timeline))
  window=verification._whole_inputs.get()
  report['protected_byte_cache']={'paths':len(window.byte_contents),'bytes':window.byte_content_size,'native_entries':len(window.entries)}
 report['status']='completed'
except Exception as e:report['status']=type(e).__name__;report['error']=str(e)
finally:
 report['hash_io']={'read_operations':sum(hash_reads.values()),'unique_paths':len(hash_reads),'duplicate_paths':[(p,n) for p,n in hash_reads.items() if n>1],'bytes':sum(hash_bytes.values())}
 report['content_io']={'read_operations':sum(byte_reads.values()),'unique_paths':len(byte_reads),'bytes':sum(byte_sizes.values()),'duplicate_paths':[(p,n) for p,n in byte_reads.items() if n>1],'top':byte_reads.most_common(30)}
 report['io_totals']={'read_open_attempts':sum(read_opens.values()),'stable_byte_reads':sum(stable_reads.values()),'actual_hash_reads':sum(hash_reads.values()),'actual_hash_input_bytes':sum(hash_bytes.values()),'stable_reads_top':stable_reads.most_common(30),'hash_reads_top':hash_reads.most_common(30),'notes':'open counts are attempted read opens, not physical disk reads; stable_bytes counts API calls; actual_content_reads and actual_hash_reads count actual application byte-read operations, not physical disk IO.'}
 sys.setprofile(None);report['seconds']=time.perf_counter()-start;report['calls']=dict(counts);Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf8');print({key:report[key] for key in ('status','stages','seconds','calls') if key in report},flush=True)


