from copy import deepcopy
import hashlib
import pytest


def template(config, name):
    from video_ai.runtime.workflows import WorkflowTemplate
    path = config.workflows[name]
    return WorkflowTemplate.load(path,path.with_suffix('.mapping.json'),config.models)


def remote_info(t):
    info = {cls:{'input':{'required':{},'optional':{}},'output_node':False} for cls in t.mapping['nodes'].values()}
    for refs in (t.mapping['inputs'],t.mapping['models']):
        for ref in refs.values():
            cls = t.mapping['nodes'][ref['node_id']]
            info[cls]['input']['required'][ref['input']] = ['STRING',{}]
    cls = t.mapping['nodes'][t.mapping['output']['node_id']]
    info[cls]['output_node'] = True
    return info


@pytest.mark.parametrize('name',['sdxl','wan','upscale'])
def test_instances_use_mapping_and_preserve_source(runtime_run,name):
    config = runtime_run[1]
    t = template(config,name)
    path = config.workflows[name]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    image_key = next((name for name, ref in t.mapping['inputs'].items() if ref['input'] == 'image'), None)
    replacements = {image_key:'input/shot_0001.png'} if image_key else {}
    instance = t.instantiate(replacements,output_prefix='run/shot_0001')
    ref = t.mapping['inputs']['output_prefix']
    assert instance[ref['node_id']]['inputs'][ref['input']] == 'run/shot_0001'
    if image_key:
        ref = t.mapping['inputs'][image_key]
        assert instance[ref['node_id']]['inputs'][ref['input']] == replacements[image_key]
    instance[next(iter(instance))]['inputs']['test_mutation'] = True
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert 'test_mutation' not in t.graph[next(iter(t.graph))]['inputs']
    t.validate_remote(remote_info(t))


def test_template_missing_remote_class_and_input(runtime_run):
    t = template(runtime_run[1],'wan')
    info = remote_info(t)
    del info['LoadImage']
    with pytest.raises(ValueError,match='LoadImage'):
        t.validate_remote(info)
    info = remote_info(t)
    del info['LoadImage']['input']['required']['image']
    with pytest.raises(ValueError,match='image'):
        t.validate_remote(info)
    info = remote_info(t)
    info['SaveVideo']['output_node'] = False
    with pytest.raises(ValueError,match='output'):
        t.validate_remote(info)


def test_template_rejects_unknown_keys_placeholders_and_bad_prefix(runtime_run):
    t = template(runtime_run[1],'upscale')
    with pytest.raises(ValueError,match='unknown'):
        t.instantiate({'made_up':1},output_prefix='x')
    with pytest.raises(ValueError,match='image'):
        t.instantiate({},output_prefix='x')
    for prefix in ('../escape','C:/bad','x:bad','NUL'):
        with pytest.raises(ValueError):
            t.instantiate({'image':'frame.png'},output_prefix=prefix)


def test_wan_preserves_successful_legacy_dynamic_codec(runtime_run):
    t = template(runtime_run[1],'wan')
    graph = t.instantiate({'start_image':'start.png'},output_prefix='clip')
    output = graph[t.mapping['output']['node_id']]['inputs']
    assert output['codec'] == 'auto'
    assert output['format.codec'] == 'h264'
