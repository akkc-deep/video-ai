"""Fresh, explicitly attributed source interpretations; not output acceptance."""
from pathlib import Path
from dataclasses import dataclass
from ..config import read_json
from ..planning.storyboard import source_catalog,validate_semantic_specs,GROUNDED_POLICY,depiction_anchor
from .manifest import _timestamp,thaw
from .timeline_checks import _fresh


@dataclass(frozen=True)
class VisualContract:
    facts: dict
    depiction_policy: str | None = None


def _keys(value,fields,name):
    if not isinstance(value,dict) or set(value)!=set(fields.split()):raise ValueError(f'{name}: missing/unknown fields')


def _text(value,name):
    if not isinstance(value,str) or not value.strip():raise ValueError(f'{name}: nonempty text required')


def check_contract_presence(run,identities):
    if (run/'logs/storyboard/visual-contract.json').exists()!=('visual_contract' in identities):
        raise OSError('source contract presence changed during storyboard')


def load_visual_contract(run,slots,identities):
    check_contract_presence(run,identities)
    if 'visual_contract' not in identities:return None
    path=run/'logs/storyboard/visual-contract.json'
    _fresh(thaw(identities['visual_contract']),run=run,expected=path);data=read_json(path)
    version=data.get('schema_version');policy=data.get('depiction_policy')
    _keys(data,'schema_version run_id script_identity timing_review_identity review_method reviewer reviewed_at verdict reason units'+(' depiction_policy' if version==2 else ''),'source contract')
    if type(version) is not int or version not in (1,2) or data['run_id']!=run.name or data['review_method']!='agent_source':
        raise ValueError('source contract schema/run/method')
    if version==2 and policy!=GROUNDED_POLICY:raise ValueError('unknown source depiction policy')
    _timestamp(data['reviewed_at']);_text(data['reviewer'],'source reviewer');_text(data['reason'],'source reason')
    if data['verdict']!='passed':raise ValueError('source contract not passed')
    for key,input_key in [('script_identity','script_copy'),('timing_review_identity','timing')]:
        expected=identities[input_key];fresh=_fresh(data[key],run=run,expected=Path(expected.path))
        if (fresh.bytes,fresh.sha256)!=(expected.bytes,expected.sha256):raise ValueError('source contract input binding differs')
    catalog=source_catalog(slots);specs={}
    if not isinstance(data['units'],list):raise ValueError('source contract unit array')
    for entry in data['units']:
        _keys(entry,'unit_id source_quote facts verdict reason','source contract unit')
        uid=entry['unit_id']
        if not isinstance(uid,str) or uid not in catalog or uid in specs or entry['source_quote']!=catalog[uid]['text']:
            raise ValueError('source contract unit/quote/duplicate')
        if entry['verdict']!='passed':raise ValueError('source unit not passed')
        _text(entry['reason'],'source unit reason');specs[uid]=entry['facts']
    validate_semantic_specs(specs,slots)
    if policy is not None:
        for facts in specs.values():depiction_anchor(facts)
    _fresh(thaw(identities['visual_contract']),run=run,expected=path)
    return VisualContract(specs,policy)
