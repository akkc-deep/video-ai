"""Regressions from final review: retained defects, measured bodies and memory."""
from copy import deepcopy
import importlib
from pathlib import Path

import pytest

from scene_continuity_helpers import save,artifact
from test_scene_clip_observations import observation_context,expected_context,authored


def media():return importlib.import_module('video_ai.runtime._scene_color_repair_media')


def measured_fixture():
    fit=dict(frame_support=[dict(source_frame_index=i,pairs=81,informative_pairs=81) for i in range(2)])
    before=[dict(source_frame_index=i,mae=3.,p99_error=3.,max_error=3,new_clip=0) for i in range(2)]
    after=[dict(source_frame_index=i,mae=1.,p99_error=1.,max_error=1,new_clip=0) for i in range(2)]
    full=dict(schema_version=1,candidate_id='fixture',frames=[dict(source_frame_index=i,new_clip=0,changed_channels=100,max_change=2,parameter_delta=0.) for i in range(2)])
    decoded=dict(schema_version=1,candidate_id='fixture',scores=dict(before=before,after=after,before_mae=3.,after_mae=1.,passed=True,reasons=[]),
        roundtrip_max=[1,1],full_frames=deepcopy(full['frames']),temporal_error_differences=[0.])
    return fit,full,decoded


@pytest.mark.parametrize('fault',['clip','residual','frame_regression','reason','truncated','nonfinite','roundtrip','weighted_mean'])
def test_saved_measured_bodies_cannot_contradict_success(fault):
    validate=getattr(media(),'validate_measured_checks',None)
    assert callable(validate),'saved full-frame and decoded-score validation missing'
    fit,full,decoded=measured_fixture()
    if fault=='clip':full['frames'][0]['new_clip']=1
    elif fault=='residual':decoded['scores']['after'][0].update(p99_error=3.,max_error=5)
    elif fault=='frame_regression':decoded['scores']['after'][0]['mae']=4.
    elif fault=='reason':decoded['scores']['reasons']=['frame_max_error:0']
    elif fault=='truncated':full['frames'].pop()
    elif fault=='nonfinite':decoded['scores']['after'][0]['mae']=float('nan')
    elif fault=='weighted_mean':decoded['scores']['after_mae']=0.
    else:decoded['roundtrip_max'][1]=3
    with pytest.raises(ValueError):validate(fit,full,decoded,candidate_id='fixture',frames=2,channels=1000)


def test_valid_measured_rows_require_all_native_frames_and_strict_improvement():
    validate=getattr(media(),'validate_measured_checks',None)
    assert callable(validate),'saved full-frame and decoded-score validation missing'
    fit,full,decoded=measured_fixture()
    validate(fit,full,decoded,candidate_id='fixture',frames=2,channels=1000)


@pytest.mark.parametrize('check',['motion_process','appearance_structure'])
def test_retained_original_non_color_failure_survives_new_precheck(observation_context,check):
    from video_ai.runtime._scene_continuity_io import Reader
    mod=importlib.import_module('video_ai.runtime._scene_color_repair_validation')
    validate=getattr(mod,'require_color_only_history',None)
    assert callable(validate),'retained original non-color failure guard missing'
    expected=expected_context(observation_context);failed=authored(expected['template'])
    failed['checks'][check]='failed';failed.update(verdict='failed',issues=[dict(check=check,frames=[0,93],description='fixture_only retained defect')])
    run=Path(observation_context[1]['source']['path']).parents[2]
    ref=artifact(save(run/'production/fixture_only-retained-failure.json',failed))
    with pytest.raises(ValueError):validate(dict(rejected=dict(observation=ref)),[],expected,reader=Reader())


def test_color_only_failed_original_remains_an_explicit_research_exception(observation_context):
    from video_ai.runtime._scene_continuity_io import Reader
    mod=importlib.import_module('video_ai.runtime._scene_color_repair_validation')
    validate=getattr(mod,'require_color_only_history',None)
    assert callable(validate),'retained original color-only exception missing'
    expected=expected_context(observation_context);failed=authored(expected['template'])
    failed['checks']['color_clothing']='failed';failed.update(verdict='failed',issues=[dict(check='color_clothing',frames=[0,93],description='fixture_only mild color issue')])
    run=Path(observation_context[1]['source']['path']).parents[2]
    ref=artifact(save(run/'production/fixture_only-color-only-failure.json',failed))
    validate(dict(rejected=dict(observation=ref)),[],expected,reader=Reader())


def test_full_frame_checks_use_bounded_chunks_instead_of_full_int16_temporaries():
    import numpy as np
    import tracemalloc
    function=getattr(media(),'frame_changes',None)
    assert callable(function),'bounded full-frame checks missing'
    before=np.full((1080,1920,3),100,np.uint8);after=np.full_like(before,102)
    tracemalloc.start()
    try:
        result=function(before,after)
        peak=tracemalloc.get_traced_memory()[1]
    finally:tracemalloc.stop()
    assert result==dict(new_clip=0,changed_channels=6220800,max_change=2)
    assert peak<8*1024*1024,'full-frame validation must not allocate full int16 images'


def test_reference_byte_copy_keeps_original_selected_image_identity(runtime_run):
    from video_ai.runtime._scene_continuity_io import Reader
    mod=importlib.import_module('video_ai.runtime._scene_color_repair_validation')
    function=getattr(mod,'verify_reference_source',None)
    assert callable(function),'selected still byte-copy proof missing'
    run=runtime_run[0];raw=b'fixture_only original selected PNG bytes'
    original=run/'selected.original';copy=run/'reference.png';original.write_bytes(raw);copy.write_bytes(raw)
    function(dict(source=artifact(copy)),dict(selected_image=artifact(original)))
    copy.write_bytes(b'wrong bytes')
    with pytest.raises(ValueError):function(dict(source=artifact(copy)),dict(selected_image=artifact(original)))


def test_streamed_native_tail_png_preserves_rgb_and_explicit_srgb(runtime_run):
    import numpy as np
    import cv2
    from types import SimpleNamespace
    from uuid import uuid4
    from video_ai.media.colorimetry import _png_metadata
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime.production_scene_color_repair import RepairStore
    run,config,_=runtime_run;folder=Path('candidates')/str(uuid4())
    frozen=SimpleNamespace(config=config,options={'script_path':str(run/'production/script.txt')})
    image=(np.arange(36*64*3,dtype=np.uint16).reshape(36,64,3)*17%251).astype(np.uint8)
    with RunLock(run) as lock:
        store=RepairStore(frozen,lock);(store.root/folder).mkdir(parents=True)
        ref=media()._write_last_frame(store,folder,image,reader=Reader())
    path=Path(ref['path']);parsed,risks=_png_metadata(path)
    assert parsed['srgb_intent']==0 and risks==[]
    decoded=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    assert np.array_equal(decoded[:,:,::-1],image)


def test_working_budget_includes_a_larger_independent_reference(runtime_run):
    with pytest.raises(ValueError,match='resource_limit'):
        media().dimensions(dict(width=64,height=36),2048,run=runtime_run[0],reference_bytes=32*1024*1024)


def test_repair_writer_charges_output_metadata_before_persisting(runtime_run):
    from types import SimpleNamespace
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime.production_scene_color_repair import RepairStore
    run,config,_=runtime_run;frozen=SimpleNamespace(config=config,options={'script_path':str(run/'production/script.txt')})
    with RunLock(run) as lock:
        store=RepairStore(frozen,lock);reader=Reader();reader.bytes=67108860;store.reader=reader
        with pytest.raises(ValueError,match='resource_limit'):store.write(Path('fixture_only.json'),{'value':'more than four bytes'})
        assert not (store.root/'fixture_only.json').exists()
