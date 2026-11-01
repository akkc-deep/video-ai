"""Synthetic study providers for software tests; never natural or playback evidence."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from video_ai.runtime._scene_continuity_io import artifact
from video_ai.runtime.manifest import now


def save(path,value):
    import json
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode())
    return artifact(path,runtime=False)


def request_fixture(tmp_path,monkeypatch,*,count=24):
    from video_ai.runtime import natural_study_records as records
    from test_natural_repair_engine import conditional
    contexts={};observed={};cases=[]
    config=save(tmp_path/'config.json',dict(fixture_only=True))
    cp=save(tmp_path/'conditional.json',conditional())
    seen=save(tmp_path/'seen.json',dict(schema_version=1,video_sha256=[],reference_sha256=[]))
    for i in range(count):
        split='development' if i<12 else 'holdout';group=f'{split}_{(i%12)//3}'
        folder=tmp_path/f'case_{i}';cid=f'fixture_{i}'
        material=save(folder/'research/material/commit.json',dict(fixture_only=cid))
        video=save(folder/'video.json',dict(fixture_video=cid))
        reference=save(folder/'reference.json',dict(fixture_reference=group))
        record=save(folder/'frame.json',dict(fixture_frame=cid))
        obs=save(folder/'author.json',dict(fixture_label='mild_color_bias' if i%3==0 else 'neutral'))
        manifest=save(folder/'manifest.json',dict(fixture_manifest=cid))
        context=dict(run_id=folder.name,source_kind='research_wan_material_v1',source=video,selected_image=reference,
            commit=material,epoch=record,reference=record,frames=[record],assessment=None,ready_for_propose=False)
        contexts[str(folder)]=context
        observed[obs['path']]=dict(natural_label='mild_color_bias' if i%3==0 else 'neutral',
            operation='exposure' if i%3==0 else None,correction_direction='negative' if i%3==0 else None,
            target_reference_confirmed=True,subject_structure_intact=True,motion_intact=True,
            intentional_lighting_change=False,unresolved=False,hard_noncolor_failure=False)
        cases.append(dict(case_id=cid,scene_group=group,group_basis='Fixture only; synthetic declared families, no real independence claim.',
            domain='fixture',split=split,material=material,manifest=manifest,observations=[obs]))
    request=dict(schema_version=1,study_id=str(uuid4()),config=config,conditional_profile=cp,seen=seen,
        cases=cases,requested_at=now(),reason='Software fixture only, not a natural qualification claim.')
    monkeypatch.setattr(records,'load_research_material_context',lambda path,reader=None:deepcopy(contexts[str(path)]))
    monkeypatch.setattr(records,'opaque_holdout_context',lambda path,reader:deepcopy(contexts[str(path)]))
    monkeypatch.setattr(records,'bind_manifest',lambda *a,**kw:None)
    monkeypatch.setattr(records,'bind_source_registration',lambda *a,**kw:None)
    monkeypatch.setattr(records,'require_complete_observations',lambda *a,**kw:None)
    monkeypatch.setattr(records,'read_author_observations',lambda case,context,reader:deepcopy(observed[case['observations'][0]['path']]))
    return request,contexts,observed
