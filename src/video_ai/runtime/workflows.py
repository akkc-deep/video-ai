"""Validate versioned template mappings without contacting generation services."""
import hashlib
from pathlib import Path
import re
from copy import deepcopy
from collections.abc import Mapping

from ..config import read_json
from .paths import _validate_spelling


def safe_comfy_path(value, *, allow_empty=False):
    """Comfy paths are relative names, never Windows aliases or traversal."""
    if value == '' and allow_empty:
        return value
    if not isinstance(value, str) or not value:
        raise ValueError('expected nonempty relative Comfy path')
    path = Path(_validate_spelling(value))
    if path.is_absolute() or path.drive or path.root or '..' in path.parts:
        raise ValueError('Comfy path must be relative and contained')
    return value


class WorkflowTemplate:
    def __init__(self, graph, mapping):
        self.graph = deepcopy(graph)
        self.mapping = deepcopy(mapping)

    @classmethod
    def load(cls, workflow_path, mapping_path, models):
        validate_workflow(workflow_path, mapping_path, models)
        return cls(read_json(workflow_path), read_json(mapping_path))

    def instantiate(self, replacements, *, output_prefix):
        if not isinstance(replacements, Mapping) or set(replacements) - set(self.mapping['inputs']):
            raise ValueError('unknown workflow replacement')
        if 'output_prefix' in replacements:
            raise ValueError('output_prefix must be supplied by the named argument')
        safe_comfy_path(output_prefix)
        graph = deepcopy(self.graph)
        for name, value in dict(replacements, output_prefix=output_prefix).items():
            ref = self.mapping['inputs'][name]
            graph[ref['node_id']]['inputs'][ref['input']] = deepcopy(value)
        for name, ref in self.mapping['inputs'].items():
            value = graph[ref['node_id']]['inputs'][ref['input']]
            if ref['input'] == 'image' or name == 'output_prefix':
                if not isinstance(value, str) or '__' in value or '{{' in value or '<' in value or '>' in value:
                    raise ValueError(f'{name}: placeholder must be replaced')
                safe_comfy_path(value)
        return graph

    def validate_remote(self, object_info):
        if not isinstance(object_info, Mapping):
            raise ValueError('object_info must be object')
        for node, cls in self.mapping['nodes'].items():
            if cls not in object_info or not isinstance(object_info[cls], Mapping):
                raise ValueError(f'node {node}: remote class missing: {cls}')
        for group in ('inputs', 'models'):
            for name, ref in self.mapping[group].items():
                cls = self.mapping['nodes'][ref['node_id']]
                inputs = object_info[cls].get('input', {})
                required, optional = inputs.get('required', {}), inputs.get('optional', {})
                if ref['input'] not in required and ref['input'] not in optional:
                    raise ValueError(f'{name}: remote field missing: {ref["node_id"]}.{ref["input"]}')
        cls = self.mapping['nodes'][self.mapping['output']['node_id']]
        if object_info[cls].get('output_node') is not True:
            raise ValueError(f'{cls}: remote output node is not declared')


def validate_workflow(workflow: Path, mapping_file: Path, models) -> None:
    graph = read_json(workflow)
    mapping = read_json(mapping_file)
    if type(mapping.get('schema_version')) is not int or mapping['schema_version'] != 1:
        raise ValueError(f'{mapping_file}: schema_version must be 1')
    if mapping.get('workflow') != workflow.name:
        raise ValueError(f'{mapping_file}: workflow filename mismatch')
    for name in ('source_sha256', 'template_sha256'):
        if not isinstance(mapping.get(name), str) or not re.fullmatch('[0-9a-f]{64}', mapping[name]):
            raise ValueError(f'{mapping_file}: invalid {name}')
    nodes = mapping.get('nodes')
    if not isinstance(nodes, dict) or set(nodes) != set(graph):
        raise ValueError(f'{workflow}: template node set mismatch')
    for node, expected_class in nodes.items():
        if not isinstance(graph[node], dict) or graph[node].get('class_type') != expected_class:
            raise ValueError(f'{workflow}: node {node}: class_type mismatch')
        inputs = graph[node].get('inputs')
        if not isinstance(inputs, dict):
            raise ValueError(f'{workflow}: node {node}: inputs must be object')
        for field, value in inputs.items():
            if isinstance(value, list):
                if (len(value) != 2 or not isinstance(value[0], str) or value[0] not in graph
                        or type(value[1]) is not int or value[1] < 0):
                    raise ValueError(f'{workflow}: node {node}.{field}: invalid node link')

    def mapped_value(reference):
        if not isinstance(reference, dict) or set(reference) != {'node_id', 'input'}:
            raise ValueError(f'{mapping_file}: expected node_id/input reference')
        node, field = reference['node_id'], reference['input']
        if not isinstance(node, str) or not isinstance(field, str) or node not in graph or field not in graph[node]['inputs']:
            raise ValueError(f'{workflow}: missing mapped node/input {node}.{field}')
        return graph[node]['inputs'][field]

    for group in ('inputs', 'models'):
        if not isinstance(mapping.get(group), dict) or not mapping[group]:
            raise ValueError(f'{mapping_file}: {group} must be nonempty object')
        for name, reference in mapping[group].items():
            value = mapped_value(reference)
            if group == 'models' and (name not in models or models[name].name != value):
                raise ValueError(f'{workflow}: model filename mismatch: {name}')
    output = mapping.get('output')
    if not isinstance(output, dict) or output.get('collection') != 'images':
        raise ValueError(f'{mapping_file}: expected observed output collection images')
    outputs = [node for node, data in graph.items() if data['class_type'] in ('SaveImage', 'SaveVideo')]
    if outputs != [output.get('node_id')]:
        raise ValueError(f'{workflow}: expected one mapped output node')
    with workflow.open('rb') as file:
        if hashlib.file_digest(file, 'sha256').hexdigest() != mapping['template_sha256']:
            raise ValueError(f'{workflow}: template SHA256 differs from versioned mapping')
