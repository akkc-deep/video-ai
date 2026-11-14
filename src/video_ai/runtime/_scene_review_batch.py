"""Owning, append-only review batches; source and scene proofs remain current."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import get_ident
from time import perf_counter

from ..planning.production_scenes import canonical_digest
from .manifest import thaw
from .production_state import ProductionRefused
from .scene_revision_records import revision_artifact_batch, revision_read_transaction
from .verification import whole_input_protection, _whole_inputs
from .scene_review_control import review_admission_control, review_checkpoint

_current = ContextVar('scene_review_batch',default=None)


class ReviewBatch:
    def __init__(self, context, *, stop_requested=None, notify=None):
        self.context=context; self.store=context['store']; self.thread=get_ident()
        self.window=_whole_inputs.get(); self.active=True
        self.stop_requested=stop_requested; self.notify=notify
        self.identity=self._identity(); self.progress=None; self.records={}; self.scenes={}; self.guards={}
        self.phase=None; self.received=0; self.started=perf_counter()

    def _identity(self):
        context=self.context
        return canonical_digest(dict(options=thaw(context['frozen'].options),
            config=thaw(context['frozen'].config),
            **{key:thaw(context.get(key)) for key in
               ('inputs','rows','plan','bible','wan','execution','execution_budget','units','timeline')}))

    def checkpoint(self):
        if (not self.active or self.thread!=get_ident() or self.window is not _whole_inputs.get()
                or self.window.closed or self.store is not self.context['store']):
            raise ProductionRefused('review batch is outside its owning protected scope')
        self.store.assert_owned()
        review_checkpoint(force=True)

    def verify_context(self):
        if self.identity!=self._identity(): raise ProductionRefused('review batch admitted context changed')

    def report(self, phase, *, clip_id=None):
        if self.notify is not None and (phase!=self.phase or clip_id is not None):
            self.notify(dict(phase=phase,received=self.received,clip_id=clip_id,
                             elapsed_seconds=perf_counter()-self.started))
        self.phase=phase

    def _read_scene(self, context, scene):
        from .scene_clip_records import scene_progress
        from ._continuity_byte_guard import capture_reads
        self.checkpoint()
        with revision_read_transaction(), capture_reads() as capture:
            state, records=scene_progress(context,scene)
        self.guards[scene['scene_id']]=capture.finish()
        self.scenes[scene['scene_id']]=(state,records)
        return state,records

    def snapshot(self):
        self.checkpoint()
        self.verify_context()
        if self.progress is None:
            from .production_scene_clips import collect_progress
            self.report('review_preparation')
            self.progress,self.records=collect_progress(self.context,scene_reader=self._read_scene)
        return deepcopy((self.progress,self.records))

    def verify(self, *, changed_scene=None, created=()):
        """Only exact files appended by this receiver may change a baseline."""
        self.checkpoint()
        self.verify_context()
        with revision_read_transaction():
            self.store.verify_global()
            for sid,guard in self.guards.items():
                self.checkpoint()
                if sid==changed_scene and created:
                    paths={str(Path(path)) for path in created}
                    inventories=[]
                    for inventory in guard.inventories:
                        additions={path for path in paths if Path(path).parent==Path(inventory.path)
                                   and inventory.kind=='json_direct' and path.endswith('.json')}
                        inventories.append(replace(inventory,expected=tuple(sorted(set(inventory.expected)|additions))))
                    guard=replace(guard,absences=tuple(path for path in guard.absences if path not in paths),
                                  inventories=tuple(inventories))
                guard.verify()

    def refresh(self, cid, *, created=()):
        sid=next(row['budget']['scene_id'] for row in self.context['rows'] if row['budget']['clip_id']==cid)
        self.verify(changed_scene=sid,created=created)
        scene=next(scene for scene in self.context['plan']['scenes'] if scene['scene_id']==sid)
        self._read_scene(self.context,scene)
        scenes=[]; self.records={}
        for scene in self.context['plan']['scenes']:
            state,records=self.scenes[scene['scene_id']]
            scenes.append(state); self.records.update(records)
        self.progress=dict(self.progress,scenes=scenes)
        return deepcopy((self.progress,self.records))

    def wrote_template(self, cid, path):
        """Admit only the exact deterministic template just written by _finish."""
        from ._continuity_byte_guard import capture_reads
        sid=next(row['budget']['scene_id'] for row in self.context['rows'] if row['budget']['clip_id']==cid)
        guard=self.guards[sid];name=str(path)
        if name not in guard.absences: return
        with capture_reads() as capture: self.store.read(path)
        self.guards[sid]=replace(guard,files=guard.files+capture.finish().files,
                                absences=tuple(path for path in guard.absences if path!=name))


def review_batch(context):
    batch=_current.get()
    if batch is not None and batch.context is context:
        batch.checkpoint()
        return batch
    return None


@contextmanager
def review_admission_batch(context, *, stop_requested=None, notify=None):
    existing=review_batch(context)
    if existing is not None:
        yield existing
        return
    with review_admission_control(stop_requested=stop_requested), whole_input_protection(), revision_artifact_batch():
        batch=ReviewBatch(context,stop_requested=stop_requested,notify=notify)
        token=_current.set(batch)
        try:
            batch.checkpoint()
            yield batch
            batch.verify()
        finally:
            batch.active=False
            _current.reset(token)
