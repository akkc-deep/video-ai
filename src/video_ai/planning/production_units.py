"""Lossless automatic units and grounded source references, without I/O or reviews."""
from copy import deepcopy
from pathlib import PurePosixPath, PureWindowsPath
import unicodedata

from .composition import CompositionSettings
from .segments import SegmentedScript, TextSpan, segment_text, speakable, validate_segments
from .storyboard import SOURCE_FACT_FIELDS, _array, _object, _schema_check, _source_references
from ..media.subtitles import layout_text


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError('missing/unknown automatic unit fields')


def _nonempty(value):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty automatic unit string required')


def _candidates(candidates):
    result = tuple(candidates)
    if not 1 <= len(result) <= 8:
        raise ValueError('one to eight original speech candidates required')
    if any(not isinstance(s, TextSpan) or s.kind != 'speech' or
           type(s.start) is not int or type(s.end) is not int or
           not 0 <= s.start < s.end or type(s.text) is not str or
           len(s.text) != s.end-s.start or type(s.unit_id) is not str for s in result):
        raise ValueError('original speech candidates required')
    if len({s.unit_id for s in result}) != len(result) or any(
            left.end > right.start for left, right in zip(result, result[1:])):
        raise ValueError('duplicate or unordered original candidates')
    return result


def _facts_schema(*, final=False):
    string = dict(type='string', minLength=1)
    support = dict(text_start=dict(type='integer', minimum=0),
                   text_end=dict(type='integer', minimum=1), source_quote=string)
    if final:
        support = dict(unit_id=string, **support)
    reference = _object(dict(reference_quote=string, resolved_subject=string,
        context_source_indices=_array(dict(type='integer', minimum=0), minItems=1, uniqueItems=True)))
    return _object(dict(**{key: dict(type=['string', 'null'], minLength=1)
                          for key in SOURCE_FACT_FIELDS[:6]},
        context_sources=_array(_object(support), uniqueItems=True),
        resolved_references=_array(reference)))


def make_units_schema(candidates, known_spans):
    """Wire offsets refer to original text; final source IDs are added locally."""
    candidates = _candidates(candidates)
    _known_catalog(tuple(known_spans))
    return _object({s.unit_id: _array(_object(dict(
        text_end=dict(type='integer', minimum=s.start+1, maximum=s.end),
        semantic_reason=dict(type='string', minLength=1), facts=_facts_schema())), minItems=1)
        for s in candidates})


def _known_catalog(spans):
    catalog = {}
    number = 0
    previous_end = 0
    for span in spans:
        if (not isinstance(span, TextSpan) or type(span.start) is not int or type(span.end) is not int
                or not previous_end <= span.start < span.end or type(span.text) is not str
                or len(span.text) != span.end-span.start):
            raise ValueError('invalid/ambiguous known source span')
        previous_end = span.end
        if span.kind == 'speech':
            number += 1
            if span.unit_id != f'speech_{number:04d}' or not speakable(span.text):
                raise ValueError('known final IDs must be unique and sequential')
            catalog[span.unit_id] = dict(unit_id=span.unit_id, text_start=span.start,
                                        text_end=span.end, text=span.text)
        elif span.kind != 'skip' or span.unit_id is not None or speakable(span.text):
            raise ValueError('invalid known speech/skip source')
    return catalog


def _grapheme_boundaries(text):
    """Conservative Unicode cluster edges, including emoji and combining scripts."""
    edges = {0, len(text)}
    regional_run = 1 if text and 0x1F1E6 <= ord(text[0]) <= 0x1F1FF else 0
    def hangul(c):
        point = ord(c)
        if 0x1100 <= point <= 0x115F or 0xA960 <= point <= 0xA97C: return 'L'
        if 0x1160 <= point <= 0x11A7 or 0xD7B0 <= point <= 0xD7C6: return 'V'
        if 0x11A8 <= point <= 0x11FF or 0xD7CB <= point <= 0xD7FB: return 'T'
        if 0xAC00 <= point <= 0xD7A3: return 'LV' if (point-0xAC00) % 28 == 0 else 'LVT'
        return ''
    for index in range(1, len(text)):
        char, previous = text[index], text[index-1]
        point = ord(char)
        regional = 0x1F1E6 <= point <= 0x1F1FF
        attached = (unicodedata.category(char) in {'Mn', 'Mc', 'Me'}
                    or char == '\u200d' or previous == '\u200d'
                    or 0x1F3FB <= point <= 0x1F3FF or 0xE0020 <= point <= 0xE007F
                    or unicodedata.combining(previous) == 9
                    or (previous == '\r' and char == '\n')
                    or (regional and regional_run % 2 == 1)
                    or (hangul(previous) == 'L' and hangul(char) in {'L', 'V', 'LV', 'LVT'})
                    or (hangul(previous) in {'LV', 'V'} and hangul(char) in {'V', 'T'})
                    or (hangul(previous) in {'LVT', 'T'} and hangul(char) == 'T'))
        if not attached:
            edges.add(index)
        regional_run = regional_run+1 if regional else 0
    return edges


def _refinement(text, spans):
    original = segment_text(text)
    edges = _grapheme_boundaries(text)
    for span in spans:
        containers = [base for base in original if base.start <= span.start < span.end <= base.end]
        if len(containers) != 1 or span.text != text[span.start:span.end]:
            raise ValueError('automatic units cannot merge/rewrite original boundaries')
        base = containers[0]
        if base.kind == 'skip' and span != base:
            raise ValueError('original skip boundary must be preserved')
        if base.kind != span.kind:
            raise ValueError('automatic subdivision must preserve original speech kind')
        if span.kind == 'speech' and not speakable(span.text):
            raise ValueError('automatic speech subdivision must contain speakable text')
        boundary = base.boundary if span.end == base.end else 'phrase'
        if span.boundary != boundary:
            raise ValueError('automatic subdivision boundary differs')
        if span.start not in edges or span.end not in edges:
            raise ValueError('automatic boundary splits a grapheme cluster')


def _layout(span, measure, settings):
    if not isinstance(settings, CompositionSettings):
        raise ValueError('CompositionSettings required')
    layout_text(span.text, measure=measure, width=1920-2*(settings.margin+settings.outline))


def _resolve_facts(facts, span, catalog, *, wire):
    _schema_check(facts, _facts_schema(final=not wire), 'facts')
    result = deepcopy(facts)
    for source in result['context_sources']:
        matches = [entry for entry in catalog.values() if
            (source['text_start'], source['text_end'], source['source_quote']) ==
            (entry['text_start'], entry['text_end'], entry['text'])]
        if len(matches) != 1 or matches[0]['text_end'] > span.start:
            raise ValueError('unknown/future/ambiguous or inexact context source span/quote')
        if wire:
            source['unit_id'] = matches[0]['unit_id']
        elif source['unit_id'] != matches[0]['unit_id']:
            raise ValueError('context final source ID differs')
    _source_references(result, span.text, catalog)
    return result


def apply_units_proposal(script, candidates, proposal, *, known_spans, measure, composition_settings):
    """Return (batch spans including intervening skips, final-ID semantic specs)."""
    if not isinstance(script, SegmentedScript) or type(script.has_bom) is not bool:
        raise ValueError('SegmentedScript required')
    canonical = segment_text(script.text)
    if script.spans != canonical:
        raise ValueError('original canonical script required for proposals')
    candidates = _candidates(candidates)
    original_speech = [s for s in canonical if s.kind == 'speech']
    try:
        first = original_speech.index(candidates[0])
    except ValueError as exc:
        raise ValueError('unknown original candidate') from exc
    if tuple(original_speech[first:first+len(candidates)]) != candidates:
        raise ValueError('batch must contain consecutive original speech candidates')
    known = tuple(known_spans)
    catalog = _known_catalog(known)
    _refinement(script.text, known)
    prior_speech = [s for s in known if s.kind == 'speech']
    position = 0
    for original in original_speech[:first]:
        pieces = [s for s in prior_speech if original.start <= s.start < s.end <= original.end]
        if not pieces or pieces[0].start != original.start or pieces[-1].end != original.end or any(
                left.end != right.start for left, right in zip(pieces, pieces[1:])):
            raise ValueError('known spans must cover all preceding original speech')
        position += len(pieces)
    if position != len(prior_speech) or any(s.end > candidates[0].start for s in known):
        raise ValueError('known sources must precede the candidate batch')
    _schema_check(proposal, make_units_schema(candidates, known))
    spans, specs = [], {}
    number = len(catalog)
    for candidate in candidates:
        spans.extend(s for s in canonical if s.kind == 'skip' and
                     (spans[-1].end if spans else candidates[0].start) <= s.start < candidate.start)
        start = candidate.start
        for row in proposal[candidate.unit_id]:
            end = row['text_end']
            if type(end) is not int or not start < end <= candidate.end:
                raise ValueError('strictly increasing integer original text ends required')
            number += 1
            span = TextSpan(start, end, script.text[start:end], 'speech',
                            candidate.boundary if end == candidate.end else 'phrase', f'speech_{number:04d}')
            _refinement(script.text, (span,))
            _layout(span, measure, composition_settings)
            resolved = _resolve_facts(row['facts'], span, catalog, wire=True)
            specs[span.unit_id] = dict(semantic_reason=row['semantic_reason'], facts=resolved,
                                      interpretation_method='automated_source')
            spans.append(span)
            catalog[span.unit_id] = dict(unit_id=span.unit_id, text_start=start, text_end=end, text=span.text)
            start = end
        if start != candidate.end:
            raise ValueError('proposal omits original candidate tail')
    return tuple(spans), specs


def _planner(planner, originals):
    _keys(planner, 'model request_paths batches')
    if planner['model'] != 'qwen3:8b':
        raise ValueError('production units model must be qwen3:8b')
    paths = planner['request_paths']
    if type(paths) is not list or not paths or any(type(path) is not str or
            not (PureWindowsPath(path).is_absolute() or PurePosixPath(path).is_absolute()) for path in paths):
        raise ValueError('absolute actual request evidence paths required')
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate request evidence paths')
    batches = planner['batches']
    if type(batches) is not list or not batches:
        raise ValueError('ordered production unit batches required')
    candidate_ids = []
    for index, batch in enumerate(batches, 1):
        _keys(batch, 'batch_id candidate_ids request_ids')
        batch_id = f'units_batch_{index:04d}'
        if batch['batch_id'] != batch_id or type(batch['candidate_ids']) is not list or not 1 <= len(batch['candidate_ids']) <= 8:
            raise ValueError('invalid sequential batch/candidate count')
        requests = batch['request_ids']
        if requests not in ([batch_id+'_initial'], [batch_id+'_initial', batch_id+'_correction']):
            raise ValueError('invalid batch initial/correction request IDs')
        candidate_ids.extend(batch['candidate_ids'])
    if candidate_ids != [s.unit_id for s in originals if s.kind == 'speech']:
        raise ValueError('planner batch original candidate coverage differs')


def validate_production_units(payload, *, measure, composition_settings):
    """Strictly reconstruct a complete units payload; automatic semantics stay automatic."""
    _keys(payload, 'decoded_text has_bom spans semantic_specs planner')
    text = payload['decoded_text']
    if type(text) is not str or type(payload['has_bom']) is not bool or type(payload['spans']) is not list:
        raise ValueError('exact decoded text/BOM/span types required')
    spans = []
    for row in payload['spans']:
        _keys(row, 'start end text kind boundary unit_id')
        if (type(row['start']) is not int or type(row['end']) is not int
                or any(type(row[key]) is not str for key in ('text', 'kind', 'boundary'))
                or (row['unit_id'] is not None and type(row['unit_id']) is not str)):
            raise ValueError('strict original span field types required')
        spans.append(TextSpan(**row))
    spans = tuple(spans)
    validate_segments(text, spans)
    _refinement(text, spans)
    speech = [s for s in spans if s.kind == 'speech']
    specs = payload['semantic_specs']
    if not speech or type(specs) is not dict or set(specs) != {s.unit_id for s in speech}:
        raise ValueError('automatic semantic unit coverage differs')
    catalog = {}
    for span in speech:
        spec = specs[span.unit_id]
        _keys(spec, 'semantic_reason facts interpretation_method')
        _nonempty(spec['semantic_reason'])
        if spec['interpretation_method'] != 'automated_source':
            raise ValueError('automatic source interpretation required')
        _resolve_facts(spec['facts'], span, catalog, wire=False)
        _layout(span, measure, composition_settings)
        catalog[span.unit_id] = dict(unit_id=span.unit_id, text_start=span.start, text_end=span.end, text=span.text)
    _planner(payload['planner'], segment_text(text))
    return SegmentedScript(text, payload['has_bom'], spans)
