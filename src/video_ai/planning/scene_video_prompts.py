"""Pure, reviewed clip visual instructions; audit sources never enter the prompt."""
from collections.abc import Mapping
from copy import deepcopy
import json
import re
from pathlib import PureWindowsPath

from .production_scenes import canonical_digest
from ..runtime.manifest import thaw


def _fields(value, names, label):
    if not isinstance(value, Mapping) or set(value) != set(names.split()):
        raise ValueError(label+': exact fields required')


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('nonempty visual/review text required')
    return value


def _sha(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('prompt SHA256 required')


def parse_scene_rendering(value):
    """Parse an explicitly present object; null is never a legacy fallback."""
    explicit = isinstance(value, Mapping) and 'mode' in value
    fields = 'prompt_policy prompt_contract'
    if explicit:
        if value['mode'] not in ('segmented_v1', 'whole_scene_v1'):
            raise ValueError('unknown scene rendering mode')
        fields += ' mode'
        if value['mode'] == 'whole_scene_v1': fields += ' whole_scene_evidence'
    _fields(value, fields, 'scene_rendering')
    if value['prompt_policy'] != 'visual_v2':
        raise ValueError('scene_rendering.prompt_policy must be visual_v2')
    _text(value['prompt_contract'])
    if explicit and value['mode'] == 'whole_scene_v1':
        name = _text(value['whole_scene_evidence'])
        path = PureWindowsPath(name)
        if (not path.is_absolute() or not path.is_relative_to(PureWindowsPath('D:/VideoSi'))
                or '..' in path.parts or any(c in name for c in '*?')
                or path.suffix.lower() != '.json' or ':' in name[2:]):
            raise ValueError('whole_scene_evidence requires an exact absolute D:/VideoSi JSON file')
    return deepcopy(thaw(value))


def validate_scene_video_prompt_contract(contract, *, bible=None, plan=None, wan_inputs=None, script=None, execution=None):
    """Validate structure/review first, then the complete admitted context if supplied."""
    _fields(contract, 'schema_version production_strategy binding style clips review', 'prompt contract')
    if type(contract['schema_version']) is not int or contract['schema_version'] not in (1, 2):
        raise ValueError('unknown prompt contract schema_version')
    whole = contract['schema_version'] == 2
    if contract['production_strategy'] != 'paragraph_jimeng_v1':
        raise ValueError('prompt contract production_strategy differs')
    binding_fields = 'scene_plan_sha256 visual_bible_sha256 wan_inputs_sha256'
    if whole: binding_fields += ' rendering_mode execution_clips_sha256'
    _fields(contract['binding'], binding_fields, 'prompt binding')
    for key, value in contract['binding'].items():
        if key != 'rendering_mode': _sha(value)
    if whole and contract['binding']['rendering_mode'] != 'whole_scene_v1':
        raise ValueError('schema2 prompt requires whole_scene_v1')
    _text(contract['style'])
    clips = contract['clips']
    if not isinstance(clips, (list, tuple)) or not clips:
        raise ValueError('nonempty ordered prompt clips required')
    seen = set()
    for clip in clips:
        _fields(clip, 'clip_id motion camera lighting changes', 'prompt clip')
        cid = _text(clip['clip_id'])
        if re.fullmatch(r'scene_[0-9]{4,}_clip_[0-9]{4,}', cid) is None or cid in seen:
            raise ValueError('unique scene clip prompt ID required')
        seen.add(cid)
        for key in ('motion', 'camera', 'lighting'): _text(clip[key])
        if not isinstance(clip['changes'], (list, tuple)): raise ValueError('prompt changes array required')
        for change in clip['changes']:
            _fields(change, 'kind description sources', 'prompt change')
            if change['kind'] not in ('appearance', 'environment', 'lighting'): raise ValueError('unknown change kind')
            _text(change['description'])
            if not isinstance(change['sources'], (list, tuple)) or not change['sources']:
                raise ValueError('change requires original sources')
            for source in change['sources']:
                _fields(source, 'unit_id text_start text_end quote', 'change source')
                _text(source['unit_id']); _text(source['quote'])
                a,b = source['text_start'],source['text_end']
                if type(a) is not int or type(b) is not int or not 0 <= a < b:
                    raise ValueError('exact change source coordinates required')
    review = contract['review']
    _fields(review, 'reviewer review_method verdict reason content_sha256', 'prompt text review')
    _text(review['reviewer']); _text(review['reason']); _sha(review['content_sha256'])
    if review['review_method'] not in ('human_text', 'agent_text') or review['verdict'] != 'passed':
        raise ValueError('passed text review required')
    if canonical_digest({k:thaw(v) for k,v in contract.items() if k != 'review'}) != review['content_sha256']:
        raise ValueError('prompt review content SHA differs')
    context = (bible,plan,wan_inputs,script)
    if any(v is not None for v in context):
        if any(v is None for v in context): raise ValueError('complete prompt binding context required')
        expected = dict(scene_plan_sha256=canonical_digest(thaw(plan)),visual_bible_sha256=canonical_digest(thaw(bible)),
                        wan_inputs_sha256=canonical_digest(thaw(wan_inputs)))
        budgets = plan['clips']
        if whole:
            from types import SimpleNamespace
            from .scene_execution import derive_scene_execution_clips
            budgets = derive_scene_execution_clips(plan, SimpleNamespace(total_frames=plan['total_frames']), mode='whole_scene_v1')
            expected.update(rendering_mode='whole_scene_v1', execution_clips_sha256=canonical_digest(budgets))
        if execution is not None:
            if ((execution.get('mode') == 'whole_scene_v1') != whole
                    or thaw(execution.get('clips')) != thaw(budgets)):
                raise ValueError('prompt execution mode or clips differ')
        if thaw(contract['binding']) != expected: raise ValueError('prompt contract binding differs from admitted inputs')
        if [c['clip_id'] for c in clips] != [c['clip_id'] for c in budgets]:
            raise ValueError('prompt clips must completely follow committed clip order')
        catalog = {s.unit_id:s for s in script.spans if s.kind == 'speech'}
        scenes = {s['scene_id']:s for s in plan['scenes']}
        for clip,budget in zip(clips,budgets):
            scene = scenes[budget['scene_id']]
            latest = max(catalog[uid].end for uid in scene['unit_ids'])
            for change in clip['changes']:
                for source in change['sources']:
                    unit = catalog.get(source['unit_id']); a,b = source['text_start'],source['text_end']
                    if (unit is None or not unit.start <= a < b <= unit.end or b > latest
                            or source['quote'] != script.text[a:b]):
                        raise ValueError('change source differs from exact original scene text')
    return deepcopy(thaw(contract))


def render_scene_video_prompt(contract, bible, scene, clip_id):
    """Allowlist formal visual fields; JSON quoting prevents newline label injection."""
    def strings(value):
        if not isinstance(value,(list,tuple)): raise ValueError('visual attributes array required')
        return [_text(v) for v in value]
    def selected(name, key, ids):
        rows = {r[key]:r for r in bible[name]}
        if any(i not in rows for i in ids): raise ValueError('missing referenced visual record')
        return [rows[i] for i in ids]
    try:
        clip = next(c for c in contract['clips'] if c['clip_id'] == clip_id)
        if not clip_id.startswith(scene['scene_id']+'_clip_'): raise ValueError('clip belongs to another scene')
        lines = []
        def add(label, value): lines.append(label+': '+json.dumps(value,ensure_ascii=False,allow_nan=False))
        add('STYLE',_text(contract['style']))
        for row in selected('entities','entity_id',scene['entity_ids']):
            add('ENTITY',_text(row['label'])); add('FIXED_ATTRIBUTES',strings(row['fixed_attributes']))
        for row in selected('appearance_variants','variant_id',scene['variant_ids']):
            add('APPEARANCE',strings(row['attributes']))
        for row in selected('scene_groups','group_id',[scene['scene_group_id']]):
            for key in ('environment','time','lighting'): add(key.upper(),_text(row[key]))
            add('SPATIAL_RELATIONS',strings(row['spatial_relations']))
        for key in ('motion','camera','lighting'): add('CLIP_'+key.upper(),_text(clip[key]))
        return '\n'.join(lines)
    except (KeyError,StopIteration,TypeError) as exc:
        raise ValueError('required formal visual prompt fields missing') from exc
