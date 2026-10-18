"""Pure automatic envelope cuts; all synchronization claims remain estimated."""
from dataclasses import dataclass
from typing import Mapping

from ..media.timing import EnvelopeEstimate
from ..runtime.manifest import thaw
from .production_timeline import (
    ProductionTimeline, validate_production_timeline, _array, _object, _strict_json,
)
from .storyboard import Binding, StoryboardSlot, _assemble_slots, integer
from .timeline import sample_to_frame


@dataclass(frozen=True)
class AutomaticCut:
    from_unit_id: str
    to_unit_id: str
    cue_sample: int
    frame: int
    uncertainty_samples: int
    error_numerator: int
    basis: str
    alignment_claim: str

    def as_dict(self): return thaw(self)


@dataclass(frozen=True)
class AutomaticSlotPlan:
    slots: tuple[StoryboardSlot, ...]
    cuts: tuple[AutomaticCut, ...]

    def as_dict(self): return thaw(self)

    @classmethod
    def from_dict(cls, data):
        try:
            d = _object(data, cls)
            slots = []
            for item in _array(d['slots'], 'slots'):
                slot = _object(item, StoryboardSlot)
                slot['bindings'] = tuple(Binding(**_object(b, Binding)) for b in _array(slot['bindings'], 'bindings'))
                slots.append(StoryboardSlot(**slot))
            result = cls(tuple(slots), tuple(AutomaticCut(**_object(c, AutomaticCut)) for c in _array(d['cuts'], 'cuts')))
            _validate_plan_fields(result)
            return result
        except (TypeError, AttributeError, KeyError) as exc:
            raise ValueError('invalid automatic slot plan structure') from exc


def _validate_plan_fields(plan):
    def string(value, name):
        if not isinstance(value, str) or not value: raise ValueError(f'{name}: expected nonempty string')
    for slot in plan.slots:
        string(slot.shot_id, 'shot_id'); string(slot.primary_unit_id, 'primary_unit_id')
        integer(slot.start_frame, 'slot start'); integer(slot.end_frame, 'slot end')
        if slot.start_frame >= slot.end_frame: raise ValueError('nonpositive automatic slot')
        for binding in slot.bindings:
            string(binding.unit_id, 'binding unit_id'); string(binding.text, 'binding text')
            for name in ('text_start', 'text_end', 'start_sample', 'end_sample',
                         'start_frame', 'end_frame', 'spoken_overlap_samples'):
                integer(getattr(binding, name), name)
            if type(binding.quantization_edge) is not bool or type(binding.silence_only) is not bool:
                raise ValueError('binding flags must be boolean')
            if binding.text_start >= binding.text_end or binding.start_sample >= binding.end_sample:
                raise ValueError('invalid binding range')
    for cut in plan.cuts:
        string(cut.from_unit_id, 'from_unit_id'); string(cut.to_unit_id, 'to_unit_id')
        for name in ('cue_sample', 'frame', 'uncertainty_samples', 'error_numerator'):
            integer(getattr(cut, name), name)
        if cut.basis not in ('pcm_envelope', 'pcm_start') or cut.alignment_claim != 'estimated':
            raise ValueError('automatic cut must have an estimated PCM basis')


def _validate_estimates(timeline, estimates):
    if not isinstance(estimates, Mapping) or set(estimates) != {c.unit_id for c in timeline.clips}:
        raise ValueError('envelope unit coverage mismatch')
    for clip in timeline.clips:
        unit = estimates[clip.unit_id]
        if not isinstance(unit, EnvelopeEstimate): raise ValueError('expected EnvelopeEstimate')
        if type(unit.schema_version) is not int or unit.schema_version != 1 or unit.algorithm != 'pcm_envelope_v1':
            raise ValueError('invalid envelope algorithm/schema')
        for name in ('samples', 'peak', 'guard_samples', 'spoken_start_sample',
                     'spoken_end_sample', 'boundary_uncertainty_samples'):
            integer(getattr(unit, name), name)
        if (unit.samples != clip.samples or not 8 <= unit.peak <= 32768
                or not 0 <= unit.spoken_start_sample < unit.spoken_end_sample <= clip.samples
                or unit.boundary_uncertainty_samples > clip.samples):
            raise ValueError('envelope sample coverage/range mismatch')
        if not isinstance(unit.thresholds, tuple) or unit.thresholds != (1, 2, 4, 8):
            raise ValueError('invalid envelope thresholds')
        if any(type(v) is not int for v in unit.thresholds): raise ValueError('invalid envelope threshold integer')
        if not isinstance(unit.threshold_boundaries, tuple) or len(unit.threshold_boundaries) != 4:
            raise ValueError('invalid threshold boundaries')
        for interval in unit.threshold_boundaries:
            if not isinstance(interval, tuple) or len(interval) != 2: raise ValueError('invalid threshold interval')
            a, b = interval
            integer(a, 'threshold start'); integer(b, 'threshold end')
            if not 0 <= a < b <= clip.samples: raise ValueError('threshold interval outside PCM')
        cursor = unit.spoken_start_sample
        if not isinstance(unit.verified_internal_silences, tuple): raise ValueError('invalid internal silences')
        for interval in unit.verified_internal_silences:
            if not isinstance(interval, tuple) or len(interval) != 2: raise ValueError('invalid internal silence')
            a, b = interval
            integer(a, 'silence start'); integer(b, 'silence end')
            if not cursor <= a < b <= unit.spoken_end_sample: raise ValueError('invalid internal silence order/envelope')
            cursor = b


def build_automatic_slots(production_timeline: ProductionTimeline,
                          estimates: Mapping[str, EnvelopeEstimate]) -> AutomaticSlotPlan:
    validate_production_timeline(production_timeline)
    _validate_estimates(production_timeline, estimates)
    fps = production_timeline.output_fps
    cuts = []
    for left, right in zip(production_timeline.clips, production_timeline.clips[1:]):
        estimate = estimates[right.unit_id]
        cue = right.start_sample + estimate.spoken_start_sample
        frame = sample_to_frame(cue, fps)
        error = abs(frame * 48000 - cue * fps) + estimate.boundary_uncertainty_samples * fps
        basis = 'pcm_envelope'
        if error > 48000:
            frame = sample_to_frame(right.start_sample, fps)
            basis = 'pcm_start'
        cuts.append(AutomaticCut(left.unit_id, right.unit_id, cue, frame,
                                 estimate.boundary_uncertainty_samples, error, basis, 'estimated'))
    edges = [0] + [c.frame for c in cuts] + [production_timeline.total_frames]
    slots = _assemble_slots(production_timeline, edges, estimates)
    return AutomaticSlotPlan(slots, tuple(cuts))


def validate_automatic_slots(production_timeline: ProductionTimeline, plan: AutomaticSlotPlan,
                             estimates: Mapping[str, EnvelopeEstimate]) -> None:
    if not isinstance(plan, AutomaticSlotPlan): raise ValueError('expected AutomaticSlotPlan')
    try:
        expected = build_automatic_slots(production_timeline, estimates)
        if _strict_json(plan) != _strict_json(expected):
            raise ValueError('automatic slots differ from canonical PCM/envelope coverage')
    except (TypeError, AttributeError, KeyError) as exc:
        raise ValueError('invalid automatic slot plan') from exc
