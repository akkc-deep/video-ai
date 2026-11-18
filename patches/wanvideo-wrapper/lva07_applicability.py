"""Approved exact-set CPU applicability plan, independent of payload execution.

Identity descriptors must come from separately verified artifact admission.
This component compares them; it does not authenticate arbitrary caller claims
or replace a full-model/production admission boundary.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from types import MappingProxyType


class ApplicabilityError(ValueError):
    pass


_POLICY_SHA256 = '9dbc2f5536bab2057147d0ebebc3af7f8a3db1a3c060f8bc41af6a4185dc2587'


@dataclass(frozen=True)
class ApplicabilityPlan:
    role: str
    applicable: object
    excluded: tuple
    manifest: tuple
    full_model_verified: bool = False


@lru_cache(maxsize=1)
def _load():
    root = Path(__file__).parent
    raw = (root/'lva07_img_policy.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != _POLICY_SHA256:
        raise ApplicabilityError('Approved policy identity mismatch')
    policy = json.loads(raw)
    if policy['enabled'] is not True:
        raise ApplicabilityError('Policy is not enabled')
    source = (root/'nodes_model_loading.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                and n.name == 'standardize_lora_key_format')
    if hashlib.sha256(ast.get_source_segment(source, node).encode()).hexdigest() != policy['normalizer_function_sha256']:
        raise ApplicabilityError('Approved normalizer identity mismatch')
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(root/'nodes_model_loading.py'), 'exec'), namespace)
    return policy, namespace['standardize_lora_key_format']


def plan_lora_applicability(role, tensor_metadata, model, identities):
    """Classify exact frozen source/schema keys before any payload/model writes.

    ``model`` may be a CPU-test meta schema; that remains metadata evidence.
    Runtime callers must supply their actually constructed transformer schema.
    """
    policy, normalize = _load()
    if role not in policy['profiles']:
        raise ApplicabilityError('Unknown expert role')
    profile = policy['profiles'][role]
    if not isinstance(identities, dict) or identities != {
            'lora': profile['lora_identity'], 'base': profile['base_identity']}:
        raise ApplicabilityError('Frozen LoRA/base identity mismatch')
    expected = {r['source']: r for r in profile['tensors']}
    if not isinstance(tensor_metadata, dict) or set(tensor_metadata) != set(expected):
        raise ApplicabilityError('Exact source key set mismatch; no general img filter')
    try:
        normalized = normalize({k: k for k in tensor_metadata})
    except ValueError as exc:
        raise ApplicabilityError(str(exc)) from exc
    if len(normalized) != len(expected):
        raise ApplicabilityError('Source normalization lost keys')
    state = model.state_dict()
    if any('img' in k for k in state):
        raise ApplicabilityError('Constructed model has img targets; exception inapplicable')
    applicable, manifest, excluded = {}, [], []
    for key, source in normalized.items():
        row, meta = expected[source], tensor_metadata[source]
        if key != row['normalized'] or not isinstance(meta, dict) or meta.get('shape') != row['shape'] or meta.get('dtype') != row['dtype']:
            raise ApplicabilityError(f'{source}: frozen source schema mismatch')
        target = row['target']
        if row['excluded']:
            if role != 'low' or 'img' not in key or target in state:
                raise ApplicabilityError(f'{source}: exception condition mismatch')
            classification = 'declared_not_applicable'
        else:
            if target not in state or list(state[target].shape) != row['target_shape']:
                raise ApplicabilityError(f'{source}: exact constructed target shape missing')
            dtype_names = {'F16': 'torch.float16', 'BF16': 'torch.bfloat16',
                           'F32': 'torch.float32', 'F64': 'torch.float64',
                           'F8_E4M3': 'torch.float8_e4m3fn'}
            if str(state[target].dtype) != dtype_names.get(row['target_dtype']):
                raise ApplicabilityError(f'{source}: exact constructed target storage dtype mismatch')
            classification = 'applicable_pending_execution'
            applicable[key] = source
        item = MappingProxyType({'source_key': source, 'normalized_key': key, 'target': target,
                                 'classification': classification, 'runtime_consumed': None,
                                 'runtime_applied': None})
        manifest.append(item)
        if row['excluded']:
            excluded.append(item)
    if len(excluded) != profile['excluded_count'] or len(manifest) != profile['source_count']:
        raise ApplicabilityError('Exact policy accounting mismatch')
    return ApplicabilityPlan(role, MappingProxyType(applicable), tuple(excluded), tuple(manifest))
