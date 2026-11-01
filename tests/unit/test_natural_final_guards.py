"""Final independent-review regressions; constructed declarations only."""
from copy import deepcopy
from pathlib import Path
import pytest
from natural_study_helpers import save


def test_failed_receipt_cannot_redirect_away_from_retained_failed_bytes(tmp_path):
    from test_natural_candidate_records import review_fixture
    from video_ai.runtime.natural_candidate_records import read_review_receipt
    from video_ai.runtime.natural_study_records import copy_original
    from video_ai.runtime.manifest import now
    passed,expected=review_fixture(tmp_path/'media');failed=deepcopy(passed)
    failed['checks']['motion_process']='failed';failed['verdict']='failed'
    failed['issues']=[dict(check='motion_process',media=failed['source'],frames=[0,49],description='fixture defect')]
    bad=save(tmp_path/'failed.json',failed);good=save(tmp_path/'passed.json',passed)
    folder=tmp_path/passed['candidate_id']/'reviews'/bad['sha256'];copy_original(bad,folder/'raw.json')
    receipt=save(folder/'receipt.json',dict(schema_version=1,observation=good,verdict='passed',created_at=now()))
    with pytest.raises(ValueError): read_review_receipt(Path(receipt['path']),expected,identity=passed['candidate_id'])


def test_one_case_deadline_stops_launching_more_controls(runtime_run,monkeypatch):
    from video_ai.runtime import natural_study_measure as m
    from video_ai.media import research_pair_report as reports
    from video_ai.runtime.natural_study_records import StudyReader,put_json
    from test_natural_repair_statistics import constant
    run,config,paths=runtime_run;clock=[0];calls=[]
    class Budget(StudyReader):
        def __init__(self,*a,**kw): super().__init__(*a,**kw);self.end=clock[0]+300
        def check(self):
            if clock[0]>=self.end: raise TimeoutError('case deadline')
    manifest=save(run/'fixture-manifest.json',dict(fixture=True))
    case=dict(case_id='fixture',scene_group='g',domain='fixture',split='development',manifest=manifest)
    context=dict(commit=manifest,epoch=manifest)
    author=dict(natural_label='unverified',operation=None,correction_direction=None,unresolved=True,hard_noncolor_failure=False)
    monkeypatch.setattr(m,'StudyReader',Budget)
    monkeypatch.setattr(m,'case_context',lambda *a,**kw:context)
    monkeypatch.setattr(m,'read_author_observations',lambda *a,**kw:author)
    def ordinary(*a,**kw): put_json(kw['logger'].root/'continuity/report.json',dict(fixture=True));return {},[]
    monkeypatch.setattr(reports,'analyze_research_pairs',ordinary)
    def variant(*a,**kw):
        calls.append(kw.get('recipe'))
        if len(calls)==2: clock[0]=301
        frames=[constant(0,0),constant(1,0)]
        return dict(before=frames,after=frames,frames=[],full_frame=[])
    monkeypatch.setattr(m,'measure_variant',variant)
    with pytest.raises(TimeoutError): m.measure_case(case,config=config,conditional_profile={},out=run/'evidence',paths=paths)
    assert len(calls)==2
