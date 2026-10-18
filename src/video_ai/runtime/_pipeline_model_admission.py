"""Current model content is admitted only by an immutable explicit revision."""
from pathlib import Path

from ..config import read_json
from .manifest import ManifestStore,hash_file,thaw
from .pipeline_import import load_pipeline_import,fresh,same_identity


def revised_files(config,run,files, *, model_stage=None):
    snapshot=ManifestStore.open(run).snapshot()
    if 'pipeline_import' not in snapshot['workflows']:return None
    receipt=load_pipeline_import(run)
    parent=run.parent/receipt['parent_run_id']
    if receipt['changes_identity'] is None:
        original=ManifestStore.open(parent).snapshot()
        if snapshot['config_snapshot']!=original['config_snapshot']:
            raise ValueError('inherited model revision current frozen configuration differs')
        inherited=revised_files(config,parent,files)
        if inherited is None:return None
        authorization=inherited['revision_authorization']
        bound=receipt['source_identities'].get(authorization.path)
        if bound is None or not same_identity(authorization,fresh(bound)):
            raise ValueError('inherited model authorization absent from immutable import closure')
    else:
        authorization=fresh(receipt['changes_identity']);changes=read_json(Path(authorization.path))
        from ..planning.recovery import validate_changes
        board=read_json(parent/'storyboard.json') if (parent/'storyboard.json').is_file() else {'shots':[]}
        validate_changes(changes,run_id=parent.name,shot_ids=tuple(row['shot_id'] for row in board['shots']))
        if not same_identity(hash_file(config.config_file),changes['config_identity']):raise ValueError('model revision config is not author-bound')
        if changes['base_run_id']!=receipt['parent_run_id']:raise ValueError('model revision parent differs')
    result={}
    for name,path in files.items():
        current=hash_file(path);bound=receipt['source_identities'].get(current.path)
        if bound is None or not same_identity(current,fresh(bound)):
            raise ValueError('revised model/workflow not frozen in import identity closure: '+name)
        result[name]=current
    result['revision_authorization']=authorization
    if model_stage is not None:
        from ._pipeline_model_paths import prepare_or_consume_model_binding,binding_identities
        binding=prepare_or_consume_model_binding(config,run,model_stage)
        if binding is None:raise ValueError('revised model execution requires an actual loader binding')
        result['model_loader_binding']=binding['identity']
        result['model_loader_identities']=binding_identities(binding)
    return result


def fixed_graph(template,baseline_graph,baseline_mapping):
    """Preserve full node/input topology and fixed parameters, including links."""
    actual=thaw(template.graph);expected=thaw(baseline_graph)
    mapping=thaw(template.mapping);baseline_mapping=thaw(baseline_mapping)
    # WorkflowTemplate.load independently verifies this current exact digest.
    for value in (mapping,baseline_mapping):value.pop('template_sha256')
    if mapping!=baseline_mapping:raise ValueError('revised fixed workflow mapping differs')
    if set(actual)!=set(expected):raise ValueError('revised workflow complete node set differs')
    variable={(ref['node_id'],ref['input']) for group in ('inputs','models') for ref in template.mapping[group].values()}
    for node,reference in expected.items():
        record=actual[node]
        if record.get('class_type')!=reference.get('class_type') or set(record.get('inputs',{}))!=set(reference.get('inputs',{})):
            raise ValueError('revised workflow node/input topology differs')
        for name,value in reference['inputs'].items():
            if (node,name) not in variable and record['inputs'][name]!=value:
                raise ValueError('revised workflow fixed parameter/link differs')
