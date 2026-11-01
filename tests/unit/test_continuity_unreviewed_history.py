"""Unconsumed historical reports cannot imply an authored defect."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.fixture
def history_case(runtime_run):
    from video_ai.runtime.manifest import now
    run,_,_=runtime_run;aid=str(uuid4());cid='scene_0001_clip_0001'
    binding={'clip_id':cid,'clips':[{'source':{'sha256':'1'*64},'source_frames':[0,2]}]}
    def ref(name):return dict(path=str(run/name),bytes=1,sha256='2'*64)
    epoch={'artifact':ref('epoch.json')}
    folder=run/'production/scene-continuity/jobs'/aid;folder.mkdir(parents=True)
    value=dict(schema_version=1,run_id=run.name,assessment_id=aid,epoch=epoch['artifact'],clip_id=cid,
        job=ref('job.json'),attempt=ref('attempt.json'),binding=binding,manifest=ref('manifest.json'),
        report=ref('not-consumed-report.json'),closure=[],concerns=[],created_at=now())
    path=folder/'assessment.json';path.write_text(json.dumps(value),encoding='utf-8')
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt')})
    context={'store':SimpleNamespace(run_dir=run),'rows':[{'budget':{'clip_id':cid}}]}
    return SimpleNamespace(run=run,aid=aid,path=path,value=value,binding=binding,epoch=epoch,frozen=frozen,context=context)


def historical(case,reader=None):
    from video_ai.runtime.scene_continuity_records import _historical_failures
    from video_ai.runtime._scene_continuity_io import Reader
    return _historical_failures(case.frozen,[],None,case.binding,reader=reader or Reader(),
        context=case.context,source={},chain=[case.epoch])


def write_raw(case,value):
    root=case.run/'production/scene-continuity/reviews';root.mkdir(parents=True,exist_ok=True)
    (root/'raw.json').write_text(json.dumps(value),encoding='utf-8')


def test_absent_author_evidence_does_not_consume_an_unused_old_report(history_case):
    assert historical(history_case) is False


def test_later_author_evidence_is_not_hidden_by_an_earlier_absence_check(history_case):
    case=history_case;assert historical(case) is False
    write_raw(case,dict(assessment_id=case.aid,verdict='failed'))
    with pytest.raises(OSError):historical(case)


@pytest.mark.parametrize('state',['failed','passed','unverified'])
def test_any_matching_author_record_retains_full_historical_validation(history_case,state):
    case=history_case;write_raw(case,dict(assessment_id=case.aid,verdict=state))
    with pytest.raises(OSError):historical(case)


def test_receipt_without_a_raw_record_retains_full_validation(history_case):
    case=history_case;root=case.run/'production/scene-continuity/reviews'/case.aid;root.mkdir(parents=True)
    (root/'receipt.json').write_text('{}',encoding='utf-8')
    with pytest.raises(OSError):historical(case)


@pytest.mark.parametrize('changed',['assessment_id','run_id','schema_version'])
def test_lightweight_identity_is_verified_before_absence_can_skip_report(history_case,changed):
    from video_ai.runtime.production_state import ProductionRefused
    case=history_case;value=dict(case.value)
    value[changed]=str(uuid4()) if changed=='assessment_id' else ('wrong-run' if changed=='run_id' else True)
    case.path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ProductionRefused):historical(case)


def test_unrelated_raw_json_is_still_strictly_read(history_case):
    case=history_case;write_raw(case,dict(assessment_id=str(uuid4())))
    path=case.run/'production/scene-continuity/reviews/raw.json'
    path.write_text('{"assessment_id":"x","assessment_id":"y"}',encoding='utf-8')
    with pytest.raises(ValueError,match='duplicate'):historical(case)


@pytest.mark.parametrize('limit',['time','bytes'])
def test_absence_optimization_never_resets_reader_limits(history_case,limit):
    from video_ai.runtime._scene_continuity_io import Reader
    from video_ai.runtime.production_state import ProductionRefused
    reader=Reader()
    if limit=='time':reader.deadline=0
    else:reader.bytes=64*1024*1024
    with pytest.raises((TimeoutError,ProductionRefused)):historical(history_case,reader)
