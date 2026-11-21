import json
from dataclasses import replace
from pathlib import Path

import pytest

from video_ai.experiments import wan_wrapper_backend as b


def fixture():
    return dict(input_relative='start.png', input_sha256='a'*64,
                source_clip_id='fixture-clip',
                positive='fixture positive', negative='fixture negative',
                seed_high=264244520398999, seed_low=0, requires_new_parent=False)


def profiles():
    common = dict(source={'root': str(b.SOURCE), 'identity':'fixture'}, runtime={'python':'cpu-fixture'},
                  tool={'ffmpeg':'fixture'}, models={r:{'path':r+'.safetensors'} for r in b.MODEL_ROLES},
                  policy={'sha256':b.POLICY_SHA})
    return {mode:b.WrapperProfile.create(mode, common, kind='offline_fixture') for mode in ('control','fast')}


def test_fixed_modes_share_comparison_but_not_profile(tmp_path):
    ps=profiles(); marker=b.freeze_comparison(tmp_path,ps,fixture())
    assert ps['control'].digest()!=ps['fast'].digest()
    assert marker['comparison_sha256']==b.comparison_identity(ps,fixture())['comparison_sha256']
    assert ps['control'].identity_dict()['recipe']['lora_strengths']==[0.,0.]
    assert ps['fast'].identity_dict()['recipe']['timesteps']==[1000,937,833,625]
    assert 'fixture' not in ps['fast'].identity_dict()
    assert b.prepare(tmp_path,ps['fast'])['comparison_sha256']==marker['comparison_sha256']


@pytest.mark.parametrize('part',['mode','cfg','common','graph','fixture'])
def test_drift_fails_before_http(tmp_path,part):
    ps=profiles();b.freeze_comparison(tmp_path,ps,fixture())
    p=tmp_path/'frozen/profiles/fast.json'; v=json.loads(p.read_text())
    if part=='mode': v['profile']['mode']='control'
    elif part=='cfg':v['profile']['recipe']['cfg']=2
    elif part=='common':v['profile']['common']['runtime']['python']='other'
    elif part=='graph':p=tmp_path/'frozen/graphs/fast.json';v={}
    else:p=tmp_path/'fixture.json';v={}
    p.write_text(json.dumps(v))
    with pytest.raises(ValueError):b.prepare(tmp_path,ps['fast'])


def test_graph_roles_and_full_sigma_splits():
    ps=profiles()
    for mode,steps,split in [('control',40,15),('fast',4,2)]:
        graph=b.build_graph(ps[mode],fixture())
        assert set(graph)=={'97','10','30','40','50','108'}
        assert graph['40']['inputs']['samples']==['30',0]
        assert graph['50']['inputs']['vae']==['10',2]
        assert graph['10']['inputs']['num_frames']==93
        recipe=ps[mode].identity_dict()['recipe']
        assert recipe['steps']==steps and recipe['split']==split
        assert len(recipe['sigmas'])==steps+1
        assert not recipe['pure_backend_equivalence']


def test_common_difference_and_arbitrary_recipe_refused(tmp_path,monkeypatch):
    ps=profiles(); value=ps['fast'].identity_dict();value['common']['runtime']['x']=1
    ps['fast']=b.WrapperProfile.from_dict(value)
    with pytest.raises(ValueError,match='common'):b.freeze_comparison(tmp_path,ps,fixture())
    value['recipe']['steps']=5
    with pytest.raises(ValueError,match='recipe'):b.WrapperProfile.from_dict(value)
    # Editing both a manifest descriptor and a profile cannot replace the fixed models.
    manifest=b.read(b.SOURCE/'docs/task-designs/LVA-07-environment-manifest.json')
    aliases={'wan_high':'base_high','wan_low':'base_low','text_encoder':'t5'}
    value=profiles()['control'].identity_dict();value['kind']='experiment'
    value['common']['models']={aliases.get(m['role'],m['role']):{k:m[k] for k in ('path','bytes','sha256','header_sha256')} for m in manifest['models']}
    for group in ('source','runtime','tool'):value['common'][group]['artifacts']=[{'fixture':'descriptor'}]
    b.WrapperProfile.from_dict(value)
    value['common']['models']['base_high']['sha256']='0'*64
    for row in manifest['models']:
        if row['role']=='wan_high':row['sha256']='0'*64
    original=b.read
    monkeypatch.setattr(b,'read',lambda path:manifest if Path(path).name=='LVA-07-environment-manifest.json' else original(path))
    with pytest.raises(ValueError,match='pin'):b.WrapperProfile.from_dict(value)


def test_missing_parent_binding_refused(tmp_path):
    f=fixture();f['requires_new_parent']=True
    ps=profiles();b.freeze_comparison(tmp_path,ps,f)
    c=b.WrapperExperimentClient(tmp_path,profile_digest=ps['control'].digest(),port=8297,http=lambda *a:pytest.fail('HTTP'))
    with pytest.raises(ValueError,match='parent'):c.submit('control_1',b.build_graph(ps['control'],f))


def test_current_http_schema_required_arguments_choices_and_output_slots():
    from copy import deepcopy
    schemas=b.read(Path(__file__).resolve().parents[1]/'fixtures/lva07_wrapper_schemas.json')
    b.capabilities(schemas,origin='verified_current_worker_http',epoch='fixture')
    for mutation in ('argument','choice','slot'):
        changed=deepcopy(schemas)
        if mutation=='argument':del changed['LVA07Sampler']['input']['required']['model_name']
        elif mutation=='choice':changed['CLIPLoader']['input']['required']['type'][0]=['stable_diffusion']
        else:changed['LVA07Prepare']['output'][2]='IMAGE'
        with pytest.raises(ValueError):b.capabilities(changed,origin='verified_current_worker_http',epoch='fixture')


def test_gpu_worker_refuses_offline_fixture_even_with_authorization(tmp_path):
    from video_ai.experiments.wan_wrapper_nodes import WorkerContext
    ps=profiles();marker=b.freeze_comparison(tmp_path,ps,fixture())
    ctx=WorkerContext(tmp_path,mode='gpu',epoch='fixture',authorization=dict(task_id='LVA-07-05',approved=True,
        user_evidence='fixture',comparison_sha256=marker['comparison_sha256'],max_samples=2))
    with pytest.raises(ValueError,match='fixture'):ctx.require_gpu()
