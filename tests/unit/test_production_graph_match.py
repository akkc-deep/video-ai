import pytest


@pytest.mark.parametrize('other,expected',[(16.0,True),(16.01,False),(True,False),('16',False)])
def test_history_numeric_representation_preserves_full_graph_identity(other,expected):
    from video_ai.runtime.production_comfy import matches
    saved=dict(client_id='client',prompt_id='prompt',number=0)
    graph={'node':{'class_type':'PrimitiveFloat','inputs':{'value':16}}}
    history={'node':{'class_type':'PrimitiveFloat','inputs':{'value':other}}}
    assert matches(('prompt',history,'client',0),saved,graph) is expected


def test_history_seed_float_precision_loss_and_added_node_rejected():
    from video_ai.runtime.production_comfy import matches
    saved=dict(client_id='client',prompt_id='prompt',number=0)
    graph={'node':{'inputs':{'seed':2**53+1}}}
    assert not matches(('prompt',{'node':{'inputs':{'seed':float(2**53+1)}}},'client',0),saved,graph)
    assert not matches(('prompt',dict(graph,extra={}), 'client',0),saved,graph)
