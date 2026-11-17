"""Real PNG, original durable client, fake HTTP only; no model/GPU."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from image_helpers import write_png
from unit.test_upscale_pipeline import artifact


def fixture(tmp_path, *, factor='pipeline', n=3):
    from video_ai.experiments.upscale_experiment import freeze_manifest
    root=tmp_path/'experiment';root.mkdir()
    assets={}
    for role in ('model','tool','workflow'):
        path=tmp_path/(role+'.bin');path.write_bytes(role.encode());assets[role]=artifact(path)
    frames=[]
    for i in range(1,n+1):
        path=root/'input'/f'frame_{i:06d}.png';path.parent.mkdir(exist_ok=True);write_png(path,16,16)
        graph={'1':{'inputs':{'image':path.name}},'5':{'inputs':{'filename_prefix':f'frame_{i:06d}'}}}
        frames.append(dict(frame_id=i,source=artifact(path),graph=graph))
    manifest=dict(schema_version=1,task_id='LVA-05',factor=factor,artifacts=assets,
        parameters=dict(width=16,height=16),frames=frames,source_binding={'native':'synthetic test only'})
    profile=freeze_manifest(root,manifest)
    return root,manifest,profile


class Transport:
    def __init__(self,root):self.root=root;self.calls=[];self.history={};self.fail_get=False
    def __call__(self,method,route,payload=None):
        self.calls.append((method,route))
        if method=='POST':
            assert set(payload)=={'prompt','client_id'}
            pid=str(uuid4());graph=payload['prompt'];name=graph['5']['inputs']['filename_prefix']+'.png'
            output=self.root/'output'/name;output.parent.mkdir(exist_ok=True);write_png(output,16,16)
            self.history[pid]=dict(prompt=[0,pid,graph,{'client_id':payload['client_id']}],
                status={'completed':True,'status_str':'success'},
                outputs={'5':{'images':[dict(type='output',filename=name,subfolder='')]}})
            return dict(prompt_id=pid,node_errors={})
        if self.fail_get:raise ConnectionError('tracking interrupted')
        if route=='/history':return deepcopy(self.history)
        if route=='/queue':return {'queue_running':[],'queue_pending':[]}
        pid=route.split('/')[-1];return {pid:deepcopy(self.history[pid])} if pid in self.history else {}


def run(root,profile,http,**kw):
    from video_ai.experiments.upscale_experiment import run_frames
    return run_frames(root,profile_sha256=profile,http=http,**kw)


def proof(paths,**kwargs):
    import hashlib
    return [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]


def test_complete_replay_zero_http_and_zero_local_producer(tmp_path):
    root,m,profile=fixture(tmp_path);transport=Transport(root)
    first=run(root,profile,transport,pixel_proof=proof)
    assert first['frame_count']==3 and len(first['frame_rgb_sha256'])==3
    assert sum(method=='POST' for method,_ in transport.calls)==3
    transport.calls.clear()
    def forbidden(*a,**k):raise AssertionError('completed media must not decode again')
    again=run(root,profile,transport,pixel_proof=forbidden)
    assert again==first and transport.calls==[]


@pytest.mark.parametrize('cut',['history','captured','staged','promoted','receipt'])
def test_interrupted_frame_recovers_original_id_without_repost(tmp_path,cut):
    root,m,profile=fixture(tmp_path,n=2);transport=Transport(root);stopped=[]
    def interrupt(event,index):
        if index==1 and event==cut and not stopped:
            stopped.append(True);raise InterruptedError(cut)
    with pytest.raises(InterruptedError):run(root,profile,transport,pixel_proof=proof,checkpoint=interrupt)
    posts=sum(method=='POST' for method,_ in transport.calls)
    result=run(root,profile,transport,pixel_proof=proof)
    assert result['frame_count']==2
    assert result['mode']=='recovery'
    assert result['submit_and_tracking_seconds'] is None
    assert sum(method=='POST' for method,_ in transport.calls)==2
    assert posts==(1 if cut in ('history','captured') else 2)
    assert len(list((root/'frames').glob('*.png')))==2


def test_partial_private_staging_is_not_accepted(tmp_path):
    root,m,profile=fixture(tmp_path,n=1);transport=Transport(root)
    def interrupt(event,index):
        if event=='captured':
            (root/'private').mkdir(exist_ok=True);(root/'private'/'stale.part').write_bytes(b'half')
            raise InterruptedError()
    with pytest.raises(InterruptedError):run(root,profile,transport,pixel_proof=proof,checkpoint=interrupt)
    result=run(root,profile,transport,pixel_proof=proof)
    assert result['frame_count']==1 and (root/'private/stale.part').read_bytes()==b'half'
    assert sum(method=='POST' for method,_ in transport.calls)==1


@pytest.mark.parametrize('role',['model','tool','workflow','source','manifest'])
def test_identity_drift_rejected_before_post(tmp_path,role):
    root,m,profile=fixture(tmp_path);transport=Transport(root)
    path=(root/'frozen/manifest.json' if role=='manifest' else
          Path(m['frames'][0]['source']['path']) if role=='source' else Path(m['artifacts'][role]['path']))
    path.write_bytes(b'X'*path.stat().st_size)
    with pytest.raises((ValueError,json.JSONDecodeError)):run(root,profile,transport,pixel_proof=proof)
    assert transport.calls==[]


def test_unknown_original_request_uses_get_only(tmp_path):
    from video_ai.experiments.upscale_experiment import PipelineExperimentClient, frame_job
    root,m,profile=fixture(tmp_path,n=1);transport=Transport(root)
    client=PipelineExperimentClient(root,profile_sha256=profile,http=transport)
    job=frame_job(m,profile,m['frames'][0]);client.bind(job,m['frames'][0]['graph'])
    folder=root/'trials'/client.trial_id(job);folder.mkdir(exist_ok=True)
    client.api.write_once(folder/'intent.json',dict(client_id=str(uuid4()),graph=m['frames'][0]['graph'],
        graph_sha256=client.api.digest(m['frames'][0]['graph'])))
    with pytest.raises(client.api.OutcomeUnknown):run(root,profile,transport,pixel_proof=proof)
    assert transport.calls and all(method=='GET' for method,_ in transport.calls)


def test_conflicting_promoted_target_is_never_blindly_accepted(tmp_path):
    root,m,profile=fixture(tmp_path,n=1);transport=Transport(root)
    def interrupt(event,index):
        if event=='captured':raise InterruptedError()
    with pytest.raises(InterruptedError):run(root,profile,transport,pixel_proof=proof,checkpoint=interrupt)
    (root/'frames').mkdir(exist_ok=True);(root/'frames/frame_000001.png').write_bytes(b'unproven')
    with pytest.raises(ValueError):run(root,profile,transport,pixel_proof=proof)
    assert sum(method=='POST' for method,_ in transport.calls)==1


def test_old_readonly_source_materializes_new_owned_input(tmp_path):
    from video_ai.experiments.upscale_experiment import freeze_manifest
    root,m,profile=fixture(tmp_path,n=1)
    source=Path(m['frames'][0]['source']['path']);old=tmp_path/'accepted-extraction.png'
    old.write_bytes(source.read_bytes());source.unlink()
    # Replace test setup's frozen manifest before beginning any request.
    (root/'frozen/manifest.json').unlink()
    m['frames'][0]['source']=artifact(old);profile=freeze_manifest(root,m)
    transport=Transport(root)
    result=run(root,profile,transport,pixel_proof=proof)
    assert source.read_bytes()==old.read_bytes() and result['frame_count']==1
