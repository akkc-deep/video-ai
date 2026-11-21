"""Production routing/worker flow; synthetic media only, no model inference."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen

import pytest
from unit.test_production_inputs import production_config


def test_old_completed_native_parent_and_new_fast_child(runtime_run,production_config,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,observation,admit_all
    from video_ai.runtime.wan_production import mode_scope,wrapper_template
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    # Install real read-only media tools within the isolated fixture's allowed tool subtree.
    import os
    from video_ai.runtime.manifest import thaw
    from video_ai.config import load_config
    raw=thaw(production_config.raw)
    for name in ('ffmpeg','ffprobe'):
        target=Path(production_config.tools[name]).with_name('actual-'+runtime_run[1].tools[name].name)
        os.link(runtime_run[1].tools[name],target)
        raw['tools'][name]=str(target)
    raw['media']['font_file']='C:/Windows/Fonts/msyh.ttc'
    config_file=runtime_run[0]/'fast-fixture-config.json';config_file.write_text(json.dumps(raw),encoding='utf-8')
    runtime_run=(runtime_run[0],load_config(config_file),runtime_run[2])
    s=prepared_wan(runtime_run,tmp_path,monkeypatch,long_scene=True);backend=OfflineWan(s)
    first=generate(s,backend)
    assert first.status=='awaiting_continuity_review',first.error
    original={p:p.read_bytes() for p in (s['run']/'production/scene-clips').glob('*/graph.json')}
    for template in first.observation_templates:observation(s,template)
    # Add the actual production Wrapper fields to the offline server's object_info.
    from video_ai.runtime.wan_production_worker import register_production_nodes
    from types import SimpleNamespace
    registry={'WanVideoDecode':type('Decode',(),{'decode':lambda self,**kwargs:None})}
    register_production_nodes(registry,SimpleNamespace(is_matrix=True))
    for name in ('VideoAIWanPrepare','VideoAIWanSampler','VideoAIWanSave','WanVideoDecode'):
        cls=registry[name];backend.remote_info[name]=dict(input=cls.INPUT_TYPES() if hasattr(cls,'INPUT_TYPES') else {},output_node=getattr(cls,'OUTPUT_NODE',False))
    with mode_scope('fast'):
        result=generate(s,backend)
        assert result.status=='awaiting_continuity_review',result.error
        assert any('VideoAIWanPrepare'==node['class_type'] for node in backend.posts[-1]['prompt'].values())
        for path,raw in original.items():assert path.read_bytes()==raw
    before=len(backend.posts)
    # Standalone replay outside the new-default scope must rebuild both exact recipes.
    assert generate(s,backend).status=='awaiting_continuity_review'
    assert len(backend.posts)==before


def test_real_cpu_worker_registers_production_nodes_and_refuses_inference(runtime_run):
    from video_ai.runtime.wan_production import ENVIRONMENT,SOURCE,prepare_launch
    from video_ai.runtime.production_state import RunLock
    run,config,paths=runtime_run
    # Real installed runtime is read only. All probe writes remain in the isolated test run.
    config=replace(config,runtime_root=Path('E:/VideoAI'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with RunLock(run):
        launch=prepare_launch(config,run)
        command=[str(ENVIRONMENT/'python_embeded/python.exe'),'-I','-B','-X','utf8',str(SOURCE/'scripts/serve_wan_production.py'),
            '--run',str(run),'--launch',str(launch),'--port',str(port),'--cpu-probe']
        with (launch.parent/'probe.stdout').open('wb') as stdout,(launch.parent/'probe.stderr').open('wb') as stderr:
            process=subprocess.Popen(command,cwd=ENVIRONMENT/'ComfyUI',stdout=stdout,stderr=stderr,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                end=time.monotonic()+50
                while time.monotonic()<end:
                    assert process.poll() is None,(launch.parent/'probe.stderr').read_text(encoding='utf-8')
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/object_info',timeout=1) as response:info=json.load(response)
                        break
                    except OSError:time.sleep(.2)
                else:pytest.fail((launch.parent/'probe.stderr').read_text(encoding='utf-8'))
                assert {'VideoAIWanPrepare','VideoAIWanSampler','VideoAIWanSave'}<=info.keys()
                assert info['VideoAIWanSave']['output_node'] is True
                assert info['VideoAIWanPrepare']['output']==['WANVIDIMAGE_EMBEDS','WANVIDEOTEXTEMBEDS','WANVAE']
                assert json.loads((launch.parent/'worker.json').read_text())['cpu_probe'] is True
                from urllib.error import HTTPError
                from urllib.request import Request
                with pytest.raises(HTTPError) as refused:
                    urlopen(Request(f'http://127.0.0.1:{port}/prompt',data=b'{"prompt":{},"client_id":"bad"}',headers={'Content-Type':'application/json'}),timeout=2)
                assert refused.value.code==403
                assert not (launch.parent/'admission').exists()
            finally:
                if process.poll() is None:process.terminate()
                process.wait(timeout=10)
