from pathlib import Path
import numpy as np
import pytest

from video_ai.experiments import wan_wrapper_media as m


@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_nonfinite_rejected_before_encoder(tmp_path,value,monkeypatch):
    frames=np.full((93,4,8,3),.4,dtype=np.float32);frames[0,0,0,0]=value
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**kw:pytest.fail('encoder invoked'))
    with pytest.raises(ValueError,match='finite'):m.encode_frames(tmp_path,tmp_path/'bad.mp4',frames,width=8,height=4)
    assert not (tmp_path/'bad.mp4').exists()


def test_quantization_and_shape_contract():
    frames=np.full((93,4,8,3),.5,dtype=np.float32)
    assert m.rgb_frames(frames,width=8,height=4)[0,0,0,0]==128
    with pytest.raises(ValueError):m.rgb_frames(frames[:92],width=8,height=4)


def test_synthetic_93_frames_one_decode_and_process_proof(tmp_path,monkeypatch):
    ffmpeg='E:/VideoAI/shared/tools/ffmpeg/bin/ffmpeg.exe';ffprobe='E:/VideoAI/shared/tools/ffmpeg/bin/ffprobe.exe'
    if not Path(ffmpeg).exists():pytest.skip('fixed media tool unavailable')
    frames=np.empty((3,93,432,768),dtype=np.float32).transpose(1,2,3,0)
    assert not frames.flags.c_contiguous  # Native VAE C,T,H,W -> T,H,W,C view.
    frames[:]=(.3,.5,.7)
    for i in range(93):frames[i,:,i%768,:]=.9
    target=tmp_path/'output/lva07/control_1.mp4'
    partial=m.encode_frames(tmp_path,target,frames,ffmpeg=ffmpeg)
    calls=[];original=m.baseline_api
    def api():
        obj=original();command=obj.media_command
        def counted(root,name,*args,**kw):calls.append(name);return command(root,name,*args,**kw)
        obj.media_command=counted;return obj
    monkeypatch.setattr(m,'baseline_api',api)
    m.promote_encoded(tmp_path,target,partial,ffmpeg=ffmpeg,ffprobe=ffprobe)
    info=m.inspect_media(tmp_path,target,width=768,height=432,expected_frames=93,ffmpeg=ffmpeg,ffprobe=ffprobe)
    assert info['technical']['frames']==93 and len(info['technical']['pts'])==93
    assert calls.count('decode-rgb24')==1
    proof_path=target.with_suffix('.media-proof.json');original_proof=proof_path.read_bytes()
    proof=__import__('json').loads(original_proof);proof['source_sha256']='0'*64
    proof_path.write_text(__import__('json').dumps(proof))
    from video_ai.experiments import wan_wrapper_backend as b
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    ps=profiles();f=fixture()
    for mode in ps:
        v=ps[mode].identity_dict();v['common']['tool']=dict(ffmpeg={'path':ffmpeg},ffprobe={'path':ffprobe});ps[mode]=b.WrapperProfile.from_dict(v)
    with pytest.raises(ValueError,match='promot'):
        m.collect_media(tmp_path,target,trial_id='control_1',prompt_id='fixture',profile=ps['control'],fixture=f,graph=b.build_graph(ps['control'],f))
    proof_path.write_bytes(original_proof)
    assert Path(info['last_frame']).is_file()
    # Same live invocation proof avoids repeat decode; restart must inspect once again.
    assert m.inspect_media(tmp_path,target,width=768,height=432,expected_frames=93,ffmpeg=ffmpeg,ffprobe=ffprobe)==info
    assert calls.count('decode-rgb24')==1
    from uuid import uuid4
    from video_ai.experiments import wan_wrapper_backend as b
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    ps=profiles();f=fixture()
    for mode in ps:
        v=ps[mode].identity_dict();v['common']['tool']=dict(ffmpeg={'path':ffmpeg},ffprobe={'path':ffprobe});ps[mode]=b.WrapperProfile.from_dict(v)
    b.freeze_comparison(tmp_path,ps,f);graph=b.build_graph(ps['control'],f);pid=str(uuid4())
    c=b.WrapperExperimentClient(tmp_path,profile_digest=ps['control'].digest(),port=8297,http=lambda *a:pytest.fail('completed0HTTP'))
    c.bind('control_1',graph);folder=tmp_path/'trials/control_1'
    intent=dict(client_id=str(uuid4()),graph=graph,graph_sha256=b.digest(graph));b.write_once(folder/'intent.json',intent)
    b.write_once(folder/'accepted.json',dict(prompt_id=pid,recovered=True))
    b.write_once(folder/'history.completed.json',{pid:dict(prompt=[0,pid,graph,{'client_id':intent['client_id']}],status={'completed':True},
        outputs={'108':{'images':[dict(filename='control_1.mp4',subfolder='lva07',type='output')]}})})
    result=m.collect_media(tmp_path,target,trial_id='control_1',prompt_id=pid,profile=ps['control'],fixture=f,graph=graph)
    b.write_once(folder/'technical-complete.json',result)
    assert c.recover('control_1',graph)==result
    assert calls.count('decode-rgb24')==1
    (folder/'technical-complete.json').unlink()
    assert c.recover('control_1',graph)==result
    assert calls.count('decode-rgb24')==1
    changed=dict(result,tools=dict(ffmpeg='C:/untrusted.exe',ffprobe=ffprobe))
    with pytest.raises(ValueError,match='tool'):m.validate_result(tmp_path,changed,profile=ps['control'])
    # An explicit offline review fixture binds the *control* profile, not fast's different SHA.
    marker=b.read(tmp_path/'experiment.json');epoch=str(uuid4())
    b.write_once(tmp_path/'service-owner.json',dict(epoch=epoch))
    b.write_once(tmp_path/'admission/pair.json',dict(epoch=epoch,profile_sha256=ps['fast'].digest(),
        comparison_sha256=marker['comparison_sha256'],full_model_verified=True))
    review=dict(decision='accepted',human_evidence='offline-review-fixture; not a real human quality result',
        comparison_sha256=marker['comparison_sha256'],control_profile_sha256=ps['control'].digest(),
        fixture_sha256=b.digest(f),control_graph_sha256=b.digest(graph),prompt_id=pid,media_sha256=result['generated_sha256'])
    b.write_once(tmp_path/'reviews/control_1.json',review)
    fast=b.WrapperExperimentClient(tmp_path,profile_digest=ps['fast'].digest(),port=8297,http=lambda *a:pytest.fail('gate should be offline'))
    fast._fast_gate()
    assert ps['fast'].digest()!=ps['control'].digest()
    # A stale service epoch invalidates admission without touching producer or HTTP.
    (tmp_path/'service-owner.json').write_text(__import__('json').dumps(dict(epoch=str(uuid4()))))
    with pytest.raises(ValueError,match='live'):fast._fast_gate()
    b.write_once(tmp_path/'service-result.json',dict(exited=True,port_closed=True,exit_code=0))
    b.write_once(folder/'observation-accepted.json',dict(decision='accepted',profile_sha256=ps['control'].digest(),prompt_id=pid,
        **{role+'_sha256':result[role+'_sha256'] for role in ('generated','retained','last_frame')}))
    child=fixture();child.update(requires_new_parent=True,input_sha256=result['last_frame_sha256'],budget={'parent_clip_id':f['source_clip_id']})
    binding=b.accepted_parent_binding(tmp_path,'control_1',ps['control'].digest(),child)
    child['parent_binding']=binding
    b.verify_parent(child,ps['control'].digest())
    with pytest.raises(ValueError):b.verify_parent(dict(child,input_sha256='0'*64),ps['control'].digest())
    with pytest.raises(ValueError):b.verify_parent(child,ps['fast'].digest())
    approval=folder/'observation-accepted.json';saved=approval.read_bytes();approval.write_text('{}')
    with pytest.raises(ValueError):b.verify_parent(child,ps['control'].digest())
    approval.write_bytes(saved)
    m.clear_proofs()
    assert c.recover('control_1',graph)==result
    assert calls.count('decode-rgb24')==2
    with pytest.raises(ValueError):m.encode_frames(tmp_path,target,frames,ffmpeg=ffmpeg)
    (tmp_path/'verified-synthetic.mp4').write_bytes(target.read_bytes())
    with target.open('r+b') as f:f.write(b'corrupt!')
    with pytest.raises((ValueError,RuntimeError)):c.recover('control_1',graph)


def test_native_decoded_layout_packs_exact_rgb_values():
    import hashlib
    planar=(np.arange(3*93*4*8,dtype=np.float32)%256/255).reshape(3,93,4,8)
    frames=planar.transpose(1,2,3,0)
    assert not frames.flags.c_contiguous
    actual=m.rgb_frames(frames,width=8,height=4)
    assert actual.flags.c_contiguous
    expected=np.clip(np.rint(frames*255),0,255).astype(np.uint8).tobytes(order='C')
    assert memoryview(actual).tobytes()==expected
    assert hashlib.sha256(memoryview(actual)).digest()==hashlib.sha256(expected).digest()
