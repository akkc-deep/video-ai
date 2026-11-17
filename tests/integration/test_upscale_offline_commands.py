"""Exercise actual CLI/media execution; never load Comfy or a GPU model."""
import json
from pathlib import Path
import subprocess
import sys


def test_offline_pipeline_and_encoding_cli(tmp_path):
    repo=Path(__file__).resolve().parents[2]
    for script,options in [('benchmark_upscale_pipeline.py',['--repeats','1']),('benchmark_scene_encoding.py',[])]:
        target=tmp_path/(script+'.json')
        result=subprocess.run([sys.executable,'-X','utf8',str(repo/'scripts'/script),
            '--offline','--output',str(target),*options],capture_output=True,timeout=120)
        assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
        report=json.loads(target.read_text('utf-8'))
        assert report['gpu_executed'] is False
        assert report['status']=='offline_passed'
