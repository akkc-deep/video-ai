"""Real frozen inputs/revisions with offline Wan; no GPU or cloud request."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from integration.test_scene_revision_flow import revision_source,revision_request,tree_identity
from unit.test_scene_video_prompts import contract_for,reviewed


def prompt_revision(setup, tmp_path, *, motion=None):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.reference_image_records import require_reference_image_acceptance
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix
    from video_ai.runtime.image_selection_records import load_committed_plan
    frozen=setup['frozen'];units,timeline=load_scene_common_prefix(frozen)
    bible,plan=load_committed_plan(frozen,units,timeline)
    wan=require_reference_image_acceptance(frozen,units,timeline)
    contract=contract_for(bible,plan,wan)
    if motion:contract['clips'][0]['motion']=motion;reviewed(contract)
    source=tmp_path/'visual-prompts.json';source.write_text(json.dumps(contract,ensure_ascii=False),encoding='utf-8')
    raw=thaw(frozen.options['config_snapshot']['raw'])
    raw['scene_rendering']=dict(prompt_policy='visual_v2',prompt_contract=str(source))
    config=tmp_path/'visual-config.json';config.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    path,request=revision_request(setup)
    request.update(kind='reconfigure',scene_ids=[],choices=[],config_path=str(config))
    path.write_text(json.dumps(request),encoding='utf-8')
    return create_scene_revision(setup['run'],path),source,contract


@pytest.fixture(scope='module')
def visual_revision(revision_source,tmp_path_factory):
    before=tree_identity(revision_source['run'])
    result,source,contract=prompt_revision(revision_source,tmp_path_factory.mktemp('visual-revision'))
    assert result.status=='revision_ready',result.error
    assert tree_identity(revision_source['run'])==before
    return result,source,contract


@pytest.fixture(scope='module')
def visual_setup(visual_revision,revision_source):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix,revision_scope
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.production_scene_pipeline import produce_scene_pipeline
    from scene_clip_helpers import OfflineWan
    result,_,_=visual_revision;frozen=load_frozen_inputs(result.run_dir)
    with revision_scope():
        units,timeline=load_scene_common_prefix(frozen)
        bible,plan=load_committed_plan(frozen,units,timeline)
    setup=dict(run=result.run_dir,frozen=frozen,units=units,timeline=timeline,bible=bible,plan=plan,
        config=frozen.config,paths=RuntimePaths.from_config(frozen.config),logger=RunLogger(result.run_dir,production=True))
    backend=OfflineWan(setup)
    def forbidden(*a,**kw):raise AssertionError('inherited plan/images must not issue new cloud, mail or planner requests')
    with RunLock(result.run_dir) as held:
        first=produce_scene_pipeline(frozen,paths=setup['paths'],logger=setup['logger'],lock=held,
            dependencies=dict(planner=forbidden,image_client_factory=forbidden,reference_client_factory=forbidden,
                smtp_factory=forbidden,wan_client_factory=backend.factory,wan_service_factory=backend.service_factory))
    assert first.status=='awaiting_continuity_review',first.error
    return setup,backend,first


def test_prompt_revision_freezes_reviewed_bytes_and_reuses_all_images(revision_source,visual_revision,visual_setup):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision,load_scene_common_prefix,revision_scope
    from video_ai.runtime.scene_clip_records import scene_context,graph_for
    before=tree_identity(revision_source['run'])
    result,source,contract=visual_revision
    assert result.status=='revision_ready',result.error
    assert tree_identity(revision_source['run'])==before
    frozen=load_frozen_inputs(result.run_dir)
    with revision_scope():proof=require_scene_revision(frozen)
    assert all(proof['invalidation']['dirty'][k]==[] for k in ('common','plan','images','choices','image_group'))
    assert proof['invalidation']['dirty']['clips']
    bound=frozen.options['execution_policy']['input_identities']['scene_video_prompts']
    assert Path(bound['path'])==result.run_dir/'production/scene-video-prompts.json'
    assert Path(bound['path']).read_bytes()==source.read_bytes()
    assert bound['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text('external source may change after freeze',encoding='utf-8')
    frozen=load_frozen_inputs(result.run_dir)
    with revision_scope():
        units,timeline=load_scene_common_prefix(frozen)
        context=scene_context(frozen,units,timeline)
    assert context['inputs']['prompt_policy']=='visual_v2'
    assert context['inputs']['prompt_contract']['sha256']==bound['sha256']
    assert all('VISUAL_BIBLE_JSON' not in r['parameters']['positive'] for r in context['rows'])
    assert all('sources' not in r['parameters']['positive'] for r in context['rows'])
    assert context['rows'][0]['comparison_images']
    assert not list((result.run_dir/'production/jimeng').rglob('intent.json'))
    assert tree_identity(revision_source['run'])==before


def test_contract_drift_stops_before_any_new_submission(visual_revision,visual_setup):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    result,source,_=visual_revision
    assert result.status=='revision_ready',result.error
    frozen=load_frozen_inputs(result.run_dir);units,timeline=load_scene_common_prefix(frozen)
    bound=Path(frozen.options['execution_policy']['input_identities']['scene_video_prompts']['path'])
    raw=bound.read_bytes();stamp=bound.stat()
    before=tree_identity(result.run_dir)
    # Same length and stat: only a fresh content hash detects this drift.
    try:
        bound.write_bytes(raw.replace(b'agent_text',b'human_text'));os.utime(bound,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with pytest.raises(ValueError):load_frozen_inputs(result.run_dir)
        from video_ai.runtime.production_scene_clips import produce_scene_clips
        def forbidden(*a,**kw):raise AssertionError('must reject before client/service construction')
        outcome=produce_scene_clips(frozen,units,timeline,paths=RuntimePaths.from_config(frozen.config),
            logger=RunLogger(result.run_dir,production=True),client_factory=forbidden,service_factory=forbidden)
        assert outcome.status=='blocked',outcome.error
        assert sorted((result.run_dir/'production/scene-clips').glob('*/intent.json'))==sorted(
            result.run_dir/p for p in before if p.startswith('production\\scene-clips\\') and p.endswith('intent.json'))
    finally:
        bound.write_bytes(raw);os.utime(bound,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))


def test_send_guard_rehashes_contract_after_successful_preflight(visual_setup):
    from video_ai.runtime.scene_revision_records import revision_scope
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_clip_records import scene_context,graph_for
    setup,backend,_=visual_setup
    with RunLock(setup['run']) as held,revision_scope():
        context=scene_context(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],lock=held)
        row=context['rows'][0];store=context['store']
        request=store.read(store.clip_dir(row['budget']['clip_id'])/'request.json')
        guard=store.capture_guard(request,graph_for(context,row));guard()
        path=setup['run']/'production/scene-video-prompts.json'
        raw=path.read_bytes();stamp=path.stat();posts=len(backend.posts)
        try:
            path.write_bytes(raw.replace(b'agent_text',b'human_text'));os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with pytest.raises(ValueError):guard()
            assert len(backend.posts)==posts
        finally:
            path.write_bytes(raw);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))


def test_later_revision_uses_frozen_contract_when_external_source_has_changed(visual_setup):
    from video_ai.runtime.production_scene_revision import _target_configuration,configuration_identity
    from video_ai.planning.scene_revision import identity_from_options
    setup,_,_=visual_setup
    source=setup['frozen']
    target=setup['run'].parent/'20261023-000000-abcdef123456'
    config,_,_=_target_configuration(source,target,dict(kind='regenerate_clips'))
    bound=source.options['execution_policy']['input_identities']['scene_video_prompts']
    assert config.raw['scene_rendering']['prompt_contract']==bound['path']
    assert configuration_identity(config)['rendering']==identity_from_options(source.options)['rendering']


@pytest.fixture(scope='module')
def visual_completed(visual_setup):
    from scene_clip_helpers import generate,admit_all
    setup,backend,first=visual_setup
    count=len(backend.posts)
    resumed=generate(setup,backend)
    assert resumed.status=='awaiting_continuity_review',resumed.error
    assert len(backend.posts)==count
    ready=admit_all(setup,backend,result=resumed)
    assert ready.status=='source_clips_ready',ready.error
    assert len(backend.posts)==len(setup['plan']['clips'])
    return setup,backend


def test_visual_clips_resume_and_continue_without_duplicate_requests(visual_completed):
    from scene_clip_helpers import generate
    setup,backend=visual_completed;before=len(backend.posts)
    assert generate(setup,backend).status=='source_clips_ready'
    assert len(backend.posts)==before
    root=setup['run']/'production/scene-clips'
    parent=json.loads((root/'scene_0001_clip_0001/request.json').read_text(encoding='utf-8'))
    child=json.loads((root/'scene_0001_clip_0002/request.json').read_text(encoding='utf-8'))
    assert '从已选图当前姿态' in parent['parameters']['positive']
    assert '从父片当前状态' in child['parameters']['positive']
    assert parent['parameters']['positive'] != child['parameters']['positive']


def test_inherited_video_guard_captures_frozen_prompt_bytes(visual_completed):
    from video_ai.runtime._scene_revision_origins import capture_origin
    from video_ai.runtime.scene_revision_records import revision_scope
    setup,_=visual_completed
    with revision_scope():
        capture=capture_origin(setup['frozen'],'clip',setup['plan']['clips'][0]['clip_id'])
        path=setup['run']/'production/scene-video-prompts.json'
        raw=path.read_bytes();stamp=path.stat()
        try:
            path.write_bytes(raw.replace(b'agent_text',b'human_text'))
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with pytest.raises(ValueError):capture['guard'].verify_captured_bytes()
        finally:
            path.write_bytes(raw);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))


def test_unreviewed_contract_cannot_prepare_a_revision(revision_source,tmp_path):
    from video_ai.runtime.production_scene_revision import configuration_identity
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    from unit.test_scene_video_prompts import fixture
    contract=fixture()[-1];contract['review']['verdict']='unverified'
    path=tmp_path/'unreviewed.json';path.write_text(json.dumps(contract),encoding='utf-8')
    raw=thaw(revision_source['frozen'].config.raw)
    raw['scene_rendering']=dict(prompt_policy='visual_v2',prompt_contract=str(path))
    config=load_config(revision_source['frozen'].config.config_file,raw=raw)
    with pytest.raises(ValueError):configuration_identity(config)
