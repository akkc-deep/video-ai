"""Archive aliases must be rejected before any byte reaches the target."""
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.skipif(os.name!='nt',reason='Windows junction path contract')
def test_archive_junction_is_refused_before_writing_through_it(runtime_run):
    from video_ai.runtime._scene_color_repair_engine import archive_engine
    from video_ai.runtime._scene_continuity_io import Reader,artifact
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime.production_scene_color_repair import RepairStore
    from video_ai.runtime.production_state import RunLock
    run,config,_=runtime_run;frozen=SimpleNamespace(config=config,options={'script_path':str(run/'production/script.txt')})
    relative=Path('candidates')/str(uuid4());outside=run/'fixture_only-outside-archive';outside.mkdir()
    source=run/'fixture_only-source.bin';source.write_bytes(b'fixture_only archive source bytes')
    capture=dict(engine=dict(algorithm='constant_color_repair_v1',implementation=[artifact(source)],
        dependency_fingerprint='0'*64,encoding={}),versions=dict(python='fixture_only',numpy='fixture_only',opencv='fixture_only'),
        build_information='fixture_only',files=[thaw(hash_file(source))])
    with RunLock(run) as lock:
        store=RepairStore(frozen,lock);parent=store.root/relative/'engine';parent.mkdir(parents=True)
        link=parent/'files';cmd=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/cmd.exe'
        subprocess.run([str(cmd),'/d','/c','mklink','/J',str(link),str(outside)],check=True,capture_output=True,timeout=10)
        assert link.is_junction()
        with pytest.raises(ValueError):archive_engine(store,relative,capture,reader=Reader())
        assert list(outside.iterdir())==[],'alias rejection must precede the first archive write'
