from copy import deepcopy
from types import SimpleNamespace

import pytest

from video_ai.experiments import wan_wrapper_backend as b
from tests.unit.test_wan_wrapper_backend import profiles


def matrix_module():
    from video_ai.experiments import wan_wrapper_matrix
    return wan_wrapper_matrix


def contracts():
    values = {}
    for key, seed, frames, keep, start in [('low',264244520398999,93,93,0),('high',264244520399048,93,93,0),
                                         ('parent',264244520399004,93,93,0),('child',264244520399005,81,77,1)]:
        values[key] = dict(seed_high=seed, seed_low=0, generated_frames=frames, retained_frames=keep,
                           retained_source_start=start, source_fixture_sha256='a'*64,
                           prompt_sha256='b'*64, expected_tokens={'prompt_embeds':664,'negative_prompt_embeds':512})
    return values


def ps():
    return matrix_module().create_profiles(profiles()['control'].identity_dict()['common'],contracts(),kind='offline_fixture')


def f(key='high'):
    c=contracts()[key]
    return dict(matrix_fixture=key,input_relative='start.png',input_sha256='c'*64,positive='positive',negative='negative',
                seed_high=c['seed_high'],seed_low=0,source_clip_id='parent' if key=='parent' else key,
                expected_tokens=c['expected_tokens'],source_fixture_sha256='a'*64,
                prompt_sha256='b'*64,budget=dict(generated_frames=c['generated_frames'],retained_frames=c['retained_frames'],
                retained_source_start=c['retained_source_start']))


def test_v2_preserves_fixture_seeds_and_child_frame_budget():
    m=matrix_module();p=ps()
    for key,seed,length in [('high',264244520399048,93),('parent',264244520399004,93),('child',264244520399005,81)]:
        g=m.graph(p['control'],f(key),'cold_1')
        assert g['30']['inputs']['seed']==seed
        assert g['10']['inputs']['num_frames']==length
        assert g['40']['inputs']['seed']==0
    assert p['control'].digest()!=p['fast'].digest()
    assert p['control'].identity_dict()['schema_version']==2


def test_v2_fifth_trial_and_edited_seed_are_refused():
    m=matrix_module();p=ps()['control']
    with pytest.raises(ValueError):m.graph(p,f(),'warm_4')
    fixture=f();fixture['seed_high']=264244520398999
    with pytest.raises(ValueError):m.graph(p,fixture,'cold_1')
    c=contracts();c['child']['generated_frames']=93
    with pytest.raises(ValueError):m.create_profiles(profiles()['control'].identity_dict()['common'],c,kind='offline_fixture')


def test_warm_graphs_change_cache_token_without_seed_or_recipe_change():
    m=matrix_module();p=ps()['fast'];graphs=[m.graph(p,f(),t) for t in ['cold_1','warm_1','warm_2','warm_3']]
    assert len({b.digest(g) for g in graphs})==4
    assert [g['30']['inputs']['trial_token'] for g in graphs]==['cold_1','warm_1','warm_2','warm_3']
    assert all(g['30']['inputs']['seed']==264244520399048 for g in graphs)
    assert all(g['10']['inputs']['trial_token']==g['40']['inputs']['trial_token'] for g in graphs)


def test_profile_does_not_allow_arbitrary_source_or_frame_configuration():
    p=ps()['fast'].identity_dict();p['settings']['num_frames']=93
    with pytest.raises(ValueError):b.WrapperProfile.from_dict(p)
    p=ps()['fast'].identity_dict();p['fixture_contracts']['child']['retained_frames']=81
    with pytest.raises(ValueError):b.WrapperProfile.from_dict(p)


def test_authorization_cannot_be_reused_for_another_group(tmp_path):
    m=matrix_module();p=ps();fixture=f('high')
    marker=m.freeze_group(tmp_path/'groups/high-control',p,fixture,matrix_root=tmp_path,group='high-control',matrix_sha256='e'*64)
    auth=dict(task_id='LVA-07-06',approved=True,user_evidence='同意',matrix_sha256='e'*64,
              groups=['low-control'],max_samples=32,max_samples_per_group=4,max_service_seconds=None,
              max_upscale_frames=2848,max_final_outputs=24)
    with pytest.raises(ValueError):m.authorize_group(tmp_path/'groups/high-control',auth)


def test_summary_does_not_count_unreviewed_video_as_accepted():
    m=matrix_module()
    summary=m.summarize_rows([dict(trial='warm_1',seconds=10,quality='accepted'),
                              dict(trial='warm_2',seconds=20,quality='pending'),
                              dict(trial='warm_3',seconds=30,quality='rejected')])
    assert summary['warm']['n']==3
    assert summary['warm']['p50_seconds']==20
    assert summary['warm']['p95_seconds']==29
    assert summary['accepted']==1 and summary['pending']==1 and summary['rejected']==1


def test_v2_worker_exposes_tokens_and_preserves_v1_schema(tmp_path):
    from video_ai.experiments.wan_wrapper_nodes import WorkerContext,register_nodes
    m=matrix_module();p=ps()
    m.freeze_group(tmp_path/'groups/high-control',p,f(),matrix_root=tmp_path,group='high-control',matrix_sha256='e'*64)
    c=WorkerContext(tmp_path/'groups/high-control',mode='cpu',epoch='one');registry={}
    register_nodes(registry,c)
    assert registry['LVA07Prepare'].INPUT_TYPES()['required']['trial_token'][0]=='STRING'
    assert registry['LVA07Sampler'].INPUT_TYPES()['required']['trial_token'][0]=='STRING'
    legacy=tmp_path/'legacy';b.freeze_comparison(legacy,profiles(),__import__('tests.unit.test_wan_wrapper_backend',fromlist=['fixture']).fixture())
    old={};register_nodes(old,WorkerContext(legacy,mode='cpu',epoch='one'))
    assert 'trial_token' not in old['LVA07Prepare'].INPUT_TYPES()['required']


def test_v2_worker_rejects_skipped_and_replayed_trial_claims(tmp_path,monkeypatch):
    from uuid import uuid4
    from video_ai.experiments.wan_wrapper_nodes import WorkerContext
    m=matrix_module();p=ps();root=tmp_path/'groups/high-control'
    m.freeze_group(root,p,f(),matrix_root=tmp_path,group='high-control',matrix_sha256='e'*64)
    c=WorkerContext(root,mode='gpu',epoch='one');monkeypatch.setattr(c,'require_gpu',lambda:None)
    c.pair=SimpleNamespace(receipt={'epoch':'one','full_model_verified':True})
    def envelope(trial):
        g=m.graph(p['control'],f(),trial);v=dict(client_id=str(uuid4()),prompt=g)
        b.write_once(root/'trials'/trial/'intent.json',dict(client_id=v['client_id'],graph=g,graph_sha256=b.digest(g)))
        return v
    with pytest.raises(ValueError):c.claim_prompt(envelope('warm_1'))
    cold=envelope('cold_1');claim=c.claim_prompt(cold)
    assert claim['trial_id']=='cold_1'
    c.active_trial='warm_2'
    with pytest.raises(ValueError):c.claim_prompt(cold)
    assert c.active_trial=='warm_2'  # A rejected replay cannot corrupt in-flight evidence.


def test_v2_image_preparation_uses_81_frame_shape(tmp_path,monkeypatch):
    import numpy as np
    from contextlib import nullcontext
    from video_ai.experiments import wan_wrapper_vae as v
    m=matrix_module();p=ps()['control'];fixture=f('child');seen=[]
    vae=SimpleNamespace(dtype='torch.float32',model=SimpleNamespace(parameters=lambda:[]))
    def invoke(name,**kw):
        if name=='LoadImage':return ['image']
        if name=='WanVideoVAELoader':return [vae]
        seen.append(kw['num_frames']);return [dict(image_embeds=np.zeros((16,21,54,96),dtype=np.float32))]
    c=SimpleNamespace(profiles={'control':p},models={'vae':{'path':'original.safetensors'}},stage=lambda *_:nullcontext(),invoke=invoke)
    monkeypatch.setattr(v,'vae_memory_scope',lambda *_:nullcontext())
    image,_,proof=v.prepare_native_image(c,fixture)
    assert seen==[81] and proof['image_embeds_shape']==[16,21,54,96]


def test_fixture_specific_text_context_preserves_full_700_tokens():
    import numpy as np
    from video_ai.experiments.wan_wrapper_text import validate_conditioning,set_context_length
    value=[[np.zeros((1,700,4096),dtype=np.float32),{}]]
    assert validate_conditioning(value,max_tokens=700) is value
    transformer=SimpleNamespace(text_len=512)
    assert set_context_length(transformer,(),{'context':[value[0][0][0]]},max_tokens=700)==700
    with pytest.raises(ValueError):validate_conditioning(value)


def test_sealed_authorization_cannot_move_to_another_matrix_root(tmp_path):
    import shutil,json
    m=matrix_module();p=ps();fixture=f();first=tmp_path/'first';second=tmp_path/'second'
    manifest=dict(task_id='LVA-07-06',matrix_root=str(first.resolve()),port=8297,groups=list(m.GROUPS),trials=list(m.TRIALS),
                  profiles={mode:profile.digest() for mode,profile in p.items()},fixtures={'high':fixture})
    saved=dict(matrix_sha256=b.digest(manifest),manifest=manifest)
    b.write_once(first/'frozen/manifest.json',manifest);b.write_once(first/'matrix.json',saved)
    gr=first/'groups/high-control';m.freeze_group(gr,p,fixture,matrix_root=first,group='high-control',matrix_sha256=saved['matrix_sha256'])
    auth=dict(task_id='LVA-07-06',approved=True,user_evidence='同意',matrix_sha256=saved['matrix_sha256'],groups=list(m.GROUPS),
              max_samples=32,max_samples_per_group=4,max_service_seconds=None,max_upscale_frames=2848,max_final_outputs=24)
    assert m.authorize_group(gr,auth)['group']=='high-control'
    shutil.copytree(first,second);marker=b.read(second/'groups/high-control/experiment.json');marker['matrix_root']=str(second.resolve())
    (second/'groups/high-control/experiment.json').write_text(json.dumps(marker),encoding='utf-8')
    with pytest.raises(ValueError):m.authorize_group(second/'groups/high-control',auth)


def test_final_acceptance_binds_candidate_audio_and_subtitles(tmp_path,monkeypatch):
    m=matrix_module();work=tmp_path/'postprocess/high-fast-cold_1';work.mkdir(parents=True)
    candidate=work/'candidate.mp4';candidate.write_bytes(b'actual reviewed candidate')
    b.write_once(work/'operation-complete.json',dict(candidate=dict(candidate=str(candidate),candidate_sha256=__import__('hashlib').sha256(candidate.read_bytes()).hexdigest(),
        subtitles_sha256='d'*64,narration={'sha256':'e'*64})))
    monkeypatch.setattr(m,'matrix_manifest',lambda _:dict(matrix_sha256='f'*64))
    result=m.review_final(tmp_path,'high-fast','cold_1','accepted','fixture final human review')
    assert result['subtitles_sha256']=='d'*64 and result['narration']['sha256']=='e'*64
    assert result['candidate_sha256']==__import__('hashlib').sha256(candidate.read_bytes()).hexdigest()
    assert not (tmp_path/'groups/high-fast/reviews/cold_1.json').exists()
