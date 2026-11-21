from pathlib import Path

import numpy as np
import pytest

from video_ai.experiments import wan_wrapper_media as media


def test_81_frame_media_keeps_generated_and_exact_77_retained_last(tmp_path,monkeypatch):
    ffmpeg=media.DEFAULT_FFMPEG;ffprobe=media.DEFAULT_FFPROBE
    if not Path(ffmpeg).exists():pytest.skip('fixed FFmpeg unavailable')
    # Small pixels, real video codec/PTS/PNG pipeline. Each frame is distinguishable.
    frames=np.empty((81,16,32,3),np.float32)
    for i in range(81):frames[i]=(.2+i/200,.4,.6)
    target=tmp_path/'output/lva07/control/cold_1.mp4';calls=[];original=media.baseline_api
    def api():
        obj=original();command=obj.media_command
        def counted(root,name,*args,**kw):calls.append(name);return command(root,name,*args,**kw)
        obj.media_command=counted;return obj
    monkeypatch.setattr(media,'baseline_api',api)
    partial=media.encode_frames(tmp_path,target,frames,width=32,height=16,expected_frames=81)
    proof=media.promote_encoded(tmp_path,target,partial,width=32,height=16,expected_frames=81,save_frames=True)
    assert len(proof['frames'])==81
    retained,rproof=media.retain_matrix_frames(tmp_path,target,proof,start=1,count=77,width=32,height=16)
    assert target.exists() and retained!=target and rproof['technical']['frames']==77
    assert len(rproof['technical']['pts'])==77 and rproof['technical']['pts'][0]['pts']==0
    assert len(rproof['frames'])==77
    assert calls.count('decode-rgb24')==2  # One decode for each distinct generated/retained artifact.
    before=retained.read_bytes()
    assert media.retain_matrix_frames(tmp_path,target,proof,start=1,count=77,width=32,height=16)[0]==retained
    assert retained.read_bytes()==before and calls.count('decode-rgb24')==2
    binding=media.read(retained.with_suffix('.trim-binding.json'))
    assert binding['source_start']==1 and binding['source_end']==78
    assert binding['source_frames'][-1]['sha256']==proof['frames'][77]['sha256']
    assert rproof['last_frame_sha256']==rproof['frames'][-1]['sha256']


def test_wrong_frame_count_fails_before_starting_encoder(tmp_path,monkeypatch):
    monkeypatch.setattr(media.subprocess,'Popen',lambda *a,**kw:pytest.fail('no encoder'))
    with pytest.raises(ValueError):media.encode_frames(tmp_path,tmp_path/'bad.mp4',np.zeros((93,16,32,3),np.float32),
                                                         width=32,height=16,expected_frames=81)


def test_postprocess_refuses_missing_original_human_review(tmp_path):
    from video_ai.experiments import wan_wrapper_matrix_postprocess as post
    with pytest.raises((ValueError,FileNotFoundError)):post.reviewed_source(tmp_path,'cold_1')


def test_chain_copies_verified_parent_once_and_reuses_completed_frames(tmp_path):
    from video_ai.experiments import wan_wrapper_matrix_postprocess as post
    from video_ai.experiments.wan_fast_profiles import artifact
    source=tmp_path/'parent.png';source.write_bytes(b'parent exact frame')
    child=tmp_path/'child.png';child.write_bytes(b'child exact frame')
    rows=[dict(path=str(p),sha256=artifact(p).sha256) for p in (source,child)]
    folder=tmp_path/'chain'
    post.copy_chain_frames(folder,rows,expected=2)
    assert (folder/'frames/frame_000001.png').read_bytes()==b'parent exact frame'
    post.copy_chain_frames(folder,rows,expected=2)
    child.write_bytes(b'other frame')
    with pytest.raises(ValueError):post.copy_chain_frames(folder,rows,expected=2)


def test_interrupted_postprocess_archives_owner_before_reusing_frame_prefix(tmp_path):
    from video_ai.experiments import wan_wrapper_matrix_postprocess as post
    from video_ai.experiments.wan_fast_profiles import write_once
    work=tmp_path/'work';write_once(work/'service-owner.json',dict(pid=100,process_started_at='original'))
    write_once(work/'service-result.json',dict(exited=True,port_closed=True,exit_code=1))
    receipt=work/'postprocess/low_motion_cold_1/frame_000001.json';write_once(receipt,dict(prompt_id='original',sha256='a'*64))
    before=receipt.read_bytes()
    assert post.archive_previous_service(work) is True
    assert receipt.read_bytes()==before
    assert (work/'service-epochs/100-original/service-owner.json').exists()
    assert (work/'service-epochs/100-original/service-result.json').exists()
    write_once(tmp_path/'alive/service-owner.json',dict(pid=101,process_started_at='active'))
    with pytest.raises((ValueError,FileNotFoundError)):post.archive_previous_service(tmp_path/'alive')


def test_two_native_worker_epochs_have_independent_metrics_and_stop_paths(tmp_path,monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    from video_ai.experiments.wan_wrapper_backend import SOURCE
    from video_ai.runtime import resources
    spec=importlib.util.spec_from_file_location('native_epoch_worker_test',SOURCE/'scripts/observe_local_comfy.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    work=tmp_path/'work';work.mkdir();(work/'experiment.json').write_text('{}');comfy=tmp_path/'comfy';comfy.mkdir()
    (work/'node-metrics.jsonl').write_text('prior epoch remains immutable\n')
    monkeypatch.setattr(native.runpy,'run_path',lambda *a,**kw:None)
    monkeypatch.setattr(resources,'find_nvidia_smi',lambda:None);monkeypatch.chdir(tmp_path)
    for epoch in ('first','second'):
        folder=work/'service-epochs'/epoch
        native.worker(SimpleNamespace(experiment_root=work,comfy_root=comfy,metrics_root=folder,stop_root=folder,port=8189))
        assert (folder/'node-metrics.jsonl').exists()
    assert (work/'node-metrics.jsonl').read_text()=='prior epoch remains immutable\n'


def test_wan_and_upscale_share_exclusive_gpu_ownership(tmp_path):
    from video_ai.experiments.wan_wrapper_matrix_observer import GpuOwnership
    with GpuOwnership(tmp_path/'gpu.lock'):
        with pytest.raises((OSError,ValueError)):
            with GpuOwnership(tmp_path/'gpu.lock'):pytest.fail('second owner must not enter')
    with GpuOwnership(tmp_path/'gpu.lock'):pass


def test_upscale_collects_archived_original_output_without_contacting_new_worker(tmp_path,monkeypatch):
    import importlib.util
    from copy import deepcopy
    from uuid import uuid4
    from video_ai.experiments import wan_wrapper_backend as b
    spec=importlib.util.spec_from_file_location('archived_upscale_test',b.SOURCE/'scripts/postprocess_local_gpu.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    work=tmp_path/'work';work.mkdir();b.write_once(work/'experiment.json',dict(port=8189))
    source=tmp_path/'source.png';source.write_bytes(media._png_rgb(bytes([90])*16*8*3,16,8))
    item=dict(path=str(source))
    from video_ai.experiments.wan_fast_profiles import artifact
    item['sha256']=artifact(source).sha256
    fixture=dict(fixture_id='fixture',parameters=dict(width=16,height=8))
    result=dict(retained_frames=1,retained='unused.mp4',retained_sha256='a'*64)
    graph=deepcopy(b.read(b.SOURCE/'workflows/upscale_api.json'))
    graph['1']['inputs']['image']='upscale/fixture_cold_1/frame_000001.png'
    graph['5']['inputs']['filename_prefix']='upscale/fixture_cold_1/frame_000001'
    folder=work/'trials/upscale_fixture_cold_1_000001';pid=str(uuid4());cid=str(uuid4())
    b.write_once(folder/'intent.json',dict(client_id=cid,graph=graph,graph_sha256=b.digest(graph)))
    b.write_once(folder/'accepted.json',dict(prompt_id=pid,recovered=False))
    output=work/'output/archive/original.png';output.parent.mkdir(parents=True)
    output.write_bytes(media._png_rgb(bytes([100])*1920*1080*3,1920,1080))
    b.write_once(folder/'history.completed.json',{pid:dict(prompt=[0,pid,graph,{'client_id':cid}],status={'completed':True},
        outputs={'5':{'images':[dict(filename='original.png',subfolder='archive',type='output')]}})})
    monkeypatch.setattr(native.ExperimentClient,'wait',lambda *a,**kw:pytest.fail('completed original archive needs no new worker/POST'))
    value=native.upscale_trial(work,tmp_path/'native','cold_1',port=8189,result_provider=lambda *_:result,
                               fixture_provider=lambda *_:fixture,source_frames=[item],restarted=True)
    assert value['frames'][0]['prompt_id']==pid and value['frames'][0]['source_sha256']==item['sha256']
