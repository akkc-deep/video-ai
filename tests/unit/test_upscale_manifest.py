"""Select actual parent/child by source identity, not shared fixture label."""
import json
from pathlib import Path
import pytest


def test_parent_child_common_fixture_id_does_not_overwrite_source(tmp_path):
    from video_ai.experiments.upscale_manifest import select_native_case
    parent=tmp_path/'parent';child=tmp_path/'child';parent.mkdir();child.mkdir()
    (parent/'fixture.json').write_text(json.dumps(dict(fixture_id='parent_child',requires_new_parent=False,
        source_clip_id='scene_0003_clip_0001',budget={'parent_clip_id':None})))
    # Child contains a parent fixture too, just like the real LVA-01 directory.
    (child/'fixture.json').write_bytes((parent/'fixture.json').read_bytes())
    (child/'child-fixture.json').write_text(json.dumps(dict(fixture_id='parent_child',requires_new_parent=True,
        source_clip_id='scene_0003_clip_0002',budget={'parent_clip_id':'scene_0003_clip_0001'})))
    cases=[dict(root=str(child),fixture_id='parent_child',trials=[{'trial_id':'cold_1_child'}]),
           dict(root=str(parent),fixture_id='parent_child',trials=[{'trial_id':'cold_1'}])]
    assert select_native_case(cases,'parent')[1]['source_clip_id']=='scene_0003_clip_0001'
    assert select_native_case(cases,'child')[1]['source_clip_id']=='scene_0003_clip_0002'
    with pytest.raises(ValueError):select_native_case(cases+cases,'parent')


def test_phase_summary_keeps_method_counts_and_device_samples_separate(tmp_path):
    from video_ai.experiments.upscale_manifest import summarize_phase
    events=[dict(kind='session',started_at_unix=100),
        dict(kind='node',prompt_id='p1',stage='upscale.model_loader',seconds=.2),
        dict(kind='node',prompt_id='p1',stage='upscale.inference',seconds=1.1),
        dict(kind='node',prompt_id='p2',stage='upscale.inference',seconds=1.),
        dict(kind='model',prompt_id='p1',stage='comfy.model_load',seconds=.1),
        dict(kind='gpu',offset_seconds=1,devices=[dict(utilization_percent=4,used_mib=400)]),
        dict(kind='gpu',offset_seconds=2,devices=[dict(utilization_percent=3,used_mib=500)]),
        dict(kind='summary',finalized=True)]
    (tmp_path/'node-metrics.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in events))
    result=dict(frame_timings=[dict(prompt_id='p1',trial='cold_1',frame_id=1,tracking_invocation_seconds=2),
                               dict(prompt_id='p2',trial='warm_1',frame_id=2,tracking_invocation_seconds=1.5)])
    report=summarize_phase(tmp_path,result)
    assert report['node_calls']['upscale.model_loader']==1
    assert report['node_calls']['upscale.inference']==2
    assert report['model_method_calls']['comfy.model_load']==1
    assert report['device_sampled_peak_vram_mib']==500
    assert report['physical_model_load_count'] is None
