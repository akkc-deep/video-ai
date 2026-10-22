"""Public revision preparation uses real accepted images/PCM and no network."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture(scope='module')
def revision_source(tmp_path_factory):
    from video_ai.config import load_config
    from video_ai.runtime.paths import RuntimePaths,create_run
    from scene_pipeline_helpers import prepared_pipeline
    config=load_config(Path(__file__).resolve().parents[2]/'config/production.example.json')
    paths=RuntimePaths.from_config(config)
    with pytest.MonkeyPatch.context() as patch:
        setup=prepared_pipeline((create_run(paths),config,paths),tmp_path_factory.mktemp('revision-source'),patch)
        patch.setenv('VIDEO_AI_SMTP_AUTH_CODE','synthetic-test-only')
        yield setup


def revision_request(setup, *, kind='reselect_images'):
    from video_ai.runtime.image_selection_records import _candidates
    run = setup['run']; frozen = setup['frozen']; scene = setup['plan']['scenes'][0]
    _, candidates = _candidates(frozen,scene,run/'production/jimeng'/scene['scene_id']/'candidates.json')
    value = dict(schema_version=2,production_strategy='paragraph_jimeng_v1',revision_id=str(uuid4()),
        source_run_id=run.name,source_options_sha256=hashlib.sha256((run/'production/options.json').read_bytes()).hexdigest(),
        requested_at=datetime.now(timezone.utc).isoformat(),kind=kind,scene_ids=[scene['scene_id']],clip_ids=[],
        choices=[{**{k:candidates[-1][k] for k in ('candidate_id','sha256')},'scene_id':scene['scene_id']}],
        config_path=None,image_model=None,output_path=None,reason='Choose another baseline')
    path = run.parent/('revision-'+uuid4().hex+'.json')
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return path,value


def tree_identity(run):
    return {str(p.relative_to(run)):(p.stat().st_mtime_ns,p.stat().st_size,
            hashlib.sha256(p.read_bytes()).hexdigest()) for p in run.rglob('*') if p.is_file()}


def test_prepare_revision_is_local_retains_origin_and_freezes_explicit_imports(revision_source):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision,load_scene_common_prefix
    setup = revision_source
    request,_ = revision_request(setup)
    before = tree_identity(setup['run'])
    result = create_scene_revision(setup['run'],request)
    assert result.status == 'revision_ready',result.error
    assert result.exit_code == 0 and result.run_dir != setup['run']
    assert tree_identity(setup['run']) == before
    frozen = load_frozen_inputs(result.run_dir)
    assert frozen.options['scene_revision']['path'] == str(result.revision_commit)
    proof = require_scene_revision(frozen)
    assert 'common:all' in proof['imports'] and 'plan:all' in proof['imports']
    assert 'image:scene_0001' in proof['imports']
    assert 'choice:scene_0001' not in proof['imports']
    assert 'image_group:all' not in proof['imports']
    units,timeline = load_scene_common_prefix(frozen)
    assert units == setup['units']
    assert timeline.total_frames == setup['timeline'].total_frames
    assert [c.samples for c in timeline.clips] == [c.samples for c in setup['timeline'].clips]
    assert all(c.pcm.path.is_relative_to(result.run_dir) for c in timeline.clips)
    from video_ai.runtime.image_selection_records import load_committed_plan,_candidates
    from video_ai.runtime.reference_settings import load_reference_settings
    bible,plan = load_committed_plan(frozen,units,timeline)
    assert plan['run_id']==result.run_id and bible['run_id']==result.run_id
    scene = plan['scenes'][0]
    bound,candidates = _candidates(frozen,scene,result.run_dir/'production/jimeng'/scene['scene_id']/'candidates.json')
    assert Path(bound['path']).is_relative_to(result.run_dir/'production/scene-revision/views')
    assert all(Path(c['path']).is_relative_to(result.run_dir) for c in candidates)
    assert load_reference_settings(frozen)['run_id']==setup['run'].name
    assert create_scene_revision(setup['run'],request).to_dict() == result.to_dict()
    assert tree_identity(setup['run']) == before


@pytest.mark.parametrize('point',['intent','view','import','imports','commit','options','ready'])
def test_revision_preparation_recovers_every_commit_boundary_without_rewriting_source(revision_source,monkeypatch,point):
    import video_ai.runtime.production_scene_revision as revision
    setup=revision_source;request,_=revision_request(setup)
    before=tree_identity(setup['run']);raised=[]
    def interrupt(event):
        if event==point and not raised:raised.append(event);raise KeyboardInterrupt(event)
    monkeypatch.setattr(revision,'boundary',interrupt)
    first=revision.create_scene_revision(setup['run'],request)
    assert first.status=='interrupted',(point,first.error)
    assert tree_identity(setup['run'])==before
    monkeypatch.setattr(revision,'boundary',lambda event:None)
    recovered=revision.create_scene_revision(setup['run'],request)
    assert recovered.status=='revision_ready',(point,recovered.error)
    assert recovered.run_dir==first.run_dir
    assert tree_identity(setup['run'])==before


def test_revision_refuses_live_source_lock_without_source_or_target_writes(revision_source):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_state import RunLock
    setup=revision_source;request,_=revision_request(setup)
    with RunLock(setup['run']):
        before=tree_identity(setup['run'])
        result=create_scene_revision(setup['run'],request)
        assert result.status=='blocked' and result.run_dir is None
        assert tree_identity(setup['run'])==before


def test_inherited_common_refuses_original_pcm_same_stat_byte_changes(revision_source):
    import os
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    setup=revision_source;request,_=revision_request(setup)
    result=create_scene_revision(setup['run'],request)
    assert result.status=='revision_ready',result.error
    pcm=setup['timeline'].clips[0].pcm.path;raw=pcm.read_bytes();stamp=pcm.stat()
    pcm.write_bytes(raw[:44]+bytes([raw[44]^1])+raw[45:])
    os.utime(pcm,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    before=tree_identity(result.run_dir)
    try:
        with pytest.raises(ValueError):load_frozen_inputs(result.run_dir)
        assert tree_identity(result.run_dir)==before
    finally:
        pcm.write_bytes(raw);os.utime(pcm,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))


def test_revision_must_not_reserve_the_original_unpublished_output(revision_source):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    setup=revision_source
    path,value=revision_request(setup)
    from video_ai.runtime.manifest import thaw
    model=Path('D:/VideoSi/models/tests')/uuid4().hex/'RealESRGAN_x4plus.pth'
    model.parent.mkdir(parents=True);model.write_bytes(b'test model identity only; never loaded')
    raw=thaw(setup['frozen'].options['config_snapshot']['raw']);raw['models']['upscale']=str(model)
    config=path.with_name('target-config-'+path.name);config.write_text(json.dumps(raw),encoding='utf-8')
    value.update(kind='reconfigure',scene_ids=[],choices=[],config_path=str(config),
        output_path=setup['frozen'].options['output_paths']['movie'])
    path.write_text(json.dumps(value),encoding='utf-8')
    before=tree_identity(setup['run'])
    result=create_scene_revision(setup['run'],path)
    assert result.status=='blocked' and result.run_dir is None,result.error
    assert 'output' in result.error['message'].lower()
    assert tree_identity(setup['run'])==before


def test_revision_target_cannot_be_nested_inside_the_read_only_source(revision_source):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.manifest import thaw
    setup=revision_source;path,value=revision_request(setup)
    raw=thaw(setup['frozen'].options['config_snapshot']['raw'])
    raw['project_root']=str(setup['run']/'nested-project')
    config=path.with_name('nested-target-'+path.name)
    config.write_text(json.dumps(raw),encoding='utf-8')
    value.update(kind='reconfigure',scene_ids=[],choices=[],config_path=str(config))
    path.write_text(json.dumps(value),encoding='utf-8')
    before=tree_identity(setup['run'])
    result=create_scene_revision(setup['run'],path)
    assert result.status=='blocked' and result.run_dir is None,result.error
    assert tree_identity(setup['run'])==before


def test_accepted_original_task_without_technical_commit_blocks_new_revision(revision_source,monkeypatch):
    import video_ai.runtime.production_scene_clips as clips
    from scene_clip_helpers import OfflineWan
    from video_ai.runtime.production_scene_revision import create_scene_revision
    setup=revision_source;backend=OfflineWan(setup)
    setup['revision_wan_backend']=backend
    original=clips._technical
    def stop(*args,**kwargs):raise KeyboardInterrupt('accepted original task before technical commit')
    monkeypatch.setattr(clips,'_technical',stop)
    interrupted=clips.produce_scene_clips(setup['frozen'],setup['units'],setup['timeline'],
        paths=setup['paths'],logger=setup['logger'],**backend.kwargs)
    assert interrupted.status=='interrupted' and len(backend.posts)==1
    path,value=revision_request(setup)
    value.update(kind='regenerate_clips',scene_ids=[],choices=[],clip_ids=[setup['plan']['clips'][0]['clip_id']])
    path.write_text(json.dumps(value),encoding='utf-8')
    before=tree_identity(setup['run'])
    result=create_scene_revision(setup['run'],path)
    assert result.status=='blocked' and result.run_dir is None,result.error
    assert tree_identity(setup['run'])==before and len(backend.posts)==1
    monkeypatch.setattr(clips,'_technical',original)
    recovered=clips.produce_scene_clips(setup['frozen'],setup['units'],setup['timeline'],
        paths=setup['paths'],logger=setup['logger'],**backend.kwargs)
    assert recovered.status=='awaiting_continuity_review',recovered.error
    assert len(backend.posts)==len(setup['plan']['scenes'])


@pytest.mark.parametrize('batch_index',[1,2])
def test_unrelated_later_batch_draft_does_not_invalidate_an_imported_baseline_choice(revision_source,batch_index):
    from video_ai.runtime._scene_revision_origins import capture_origin
    from video_ai.runtime.production_image_selection import consume_image_selection
    from video_ai.runtime.scene_revision_records import revision_scope
    setup=revision_source;run=setup['run']
    with revision_scope():
        captured=capture_origin(setup['frozen'],'choice','scene_0003')
        template=json.loads((run/f'production/image-selection/image_batch_{batch_index:04d}/selection-template.json').read_text(encoding='utf-8'))
        template.update(intent='draft',selections=[],observation=None)
        path=run/'unrelated-later-batch-draft.json';path.write_text(json.dumps(template),encoding='utf-8')
        before=tree_identity(run)
        result=consume_image_selection(setup['frozen'],setup['units'],setup['timeline'],path,paths=setup['paths'],logger=setup['logger'])
        if batch_index==1:
            assert result.status=='blocked' and 'active batch' in result.error['message']
            assert tree_identity(run)==before
        else:assert result.status=='awaiting_image_selection',result.error
        captured['guard'].verify_captured_bytes()


def test_second_revision_preserves_explicit_choice_and_traces_original_candidate(revision_source):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision
    setup=revision_source;path,value=revision_request(setup)
    first=create_scene_revision(setup['run'],path)
    assert first.status=='revision_ready',first.error
    source=load_frozen_inputs(first.run_dir)
    next_request=dict(value,revision_id=str(uuid4()),source_run_id=first.run_id,
        source_options_sha256=hashlib.sha256((first.run_dir/'production/options.json').read_bytes()).hexdigest(),
        kind='regenerate_images',scene_ids=['scene_0002'],choices=[])
    path2=path.with_name('second-'+path.name);path2.write_text(json.dumps(next_request),encoding='utf-8')
    before=tree_identity(first.run_dir)
    second=create_scene_revision(first.run_dir,path2)
    assert second.status=='revision_ready',second.error
    proof=require_scene_revision(load_frozen_inputs(second.run_dir))
    assert 'choice:scene_0003' in proof['imports']
    assert proof['imports']['image:scene_0003'][0]['source_run_id']==first.run_id
    original=require_scene_revision(source)
    assert original['imports']['image:scene_0003'][0]['source_run_id']==setup['run'].name
    old=original['imports']['image:scene_0003'][0]['view']['candidates'][0]
    new=proof['imports']['image:scene_0003'][0]['view']['candidates'][0]
    assert (new['task_id'],new['request_id'],new['sha256'])==(old['task_id'],old['request_id'],old['sha256'])
    assert Path(new['path']).is_relative_to(second.run_dir)
    assert tree_identity(first.run_dir)==before
    # C -> B -> A must retain A's original byte guard throughout this call.
    import os
    from video_ai.runtime.scene_revision_records import revision_scope,require_revision_import
    from video_ai.runtime.image_selection_records import _candidates
    original_scene=next(s for s in setup['plan']['scenes'] if s['scene_id']=='scene_0003')
    _,candidates=_candidates(setup['frozen'],original_scene,setup['run']/'production/jimeng/scene_0003/candidates.json')
    image=Path(candidates[0]['path']);raw=image.read_bytes();stamp=image.stat()
    current=load_frozen_inputs(second.run_dir)
    try:
        with revision_scope():
            admitted=require_scene_revision(current)
            image.write_bytes(bytes([raw[0]^1])+raw[1:]);os.utime(image,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with pytest.raises(ValueError):require_revision_import(current,'image','scene_0003',context=admitted)
            with pytest.raises(ValueError):require_scene_revision(current)
            with pytest.raises(ValueError):admitted['guard'].verify_captured_bytes()
            from types import SimpleNamespace
            from video_ai.runtime._scene_revision_copy import RevisionStore,copy_identity
            from video_ai.runtime.production_state import RunLock
            from video_ai.runtime.production_scene_pipeline import record_invocation
            with RunLock(second.run_dir) as held:
                target_before=tree_identity(second.run_dir)
                bound={k:candidates[0][k] for k in ('path','bytes','sha256')}
                with pytest.raises(ValueError):
                    copy_identity(RevisionStore(second.run_dir,held),'image:scene_0003','image','scene_0003',
                        'candidate_000001',bound,guard=admitted['guard'])
                admitted['guard'].lock=held
                with pytest.raises(ValueError):admitted['guard'].verify_global()
                with pytest.raises(ValueError):record_invocation(current,'advance',SimpleNamespace(),[],lock=held)
                assert tree_identity(second.run_dir)==target_before
    finally:image.write_bytes(raw);os.utime(image,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))


@pytest.mark.parametrize('mode',['regenerate','reference_settings'])
def test_later_batch_only_revision_advances_from_inherited_baselines(revision_source,monkeypatch,mode):
    from video_ai.production import make_video
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from integration.test_jimeng_reference_flow import configured_cloud
    import video_ai.runtime.production_reference_images as reference
    setup=revision_source;path,value=revision_request(setup,kind='regenerate_images')
    value.update(scene_ids=['scene_0002'],choices=[])
    if mode=='reference_settings':
        from copy import deepcopy
        from video_ai.runtime._scene_revision_reference import source_reference_context
        from video_ai.runtime.manifest import thaw
        raw=thaw(setup['frozen'].options['config_snapshot']['raw'])
        context=source_reference_context(setup['frozen'])
        raw.update(deepcopy(context['values']))
        raw['reference_generation']=deepcopy(context['marker']['model_settings'])
        raw['reference_storage']=deepcopy(context['marker']['storage'])
        raw['reference_storage']['clock_skew_seconds']+=1
        config=path.with_name('reference-only-'+path.name);config.write_text(json.dumps(raw),encoding='utf-8')
        value.update(kind='reconfigure',scene_ids=[],config_path=str(config))
    path.write_text(json.dumps(value),encoding='utf-8')
    revision=create_scene_revision(setup['run'],path)
    assert revision.status=='revision_ready',revision.error
    invalidation=json.loads((revision.run_dir/'production/scene-revision/invalidation.json').read_text(encoding='utf-8'))
    assert invalidation['dirty']['common']==[] and invalidation['dirty']['plan']==[]
    assert invalidation['dirty']['images']==['scene_0002']
    import video_ai.runtime.jimeng_candidates as baseline
    def no_new_baseline(*args,**kwargs):pytest.fail('inherited baseline was submitted again')
    monkeypatch.setattr(baseline,'generate_candidates',no_new_baseline)
    import video_ai.runtime.production_scene_clips as clips
    monkeypatch.setattr(clips,'produce_scene_clips',lambda *a,**kw:pytest.fail('image wait entered a model stage'))
    cloud,smtp,offline=configured_cloud(setup,monkeypatch)
    if mode=='reference_settings':offline['storage'].settings['clock_skew_seconds']+=1
    original_http=cloud.official_request
    def guarded(method,url,**kwargs):
        if kwargs.get('ownership_check') is not None:kwargs['ownership_check']()
        return original_http(method,url,**kwargs)
    monkeypatch.setattr(cloud,'official_request',guarded)
    produce=reference.produce_reference_batch
    def substituted(*args,**kwargs):
        kwargs.update({k:offline[k] for k in ('storage','client_factory','smtp_factory')})
        return produce(*args,**kwargs)
    monkeypatch.setattr(reference,'produce_reference_batch',substituted)
    before=tree_identity(setup['run'])
    result=make_video(run_dir=revision.run_dir)
    assert result.status=='awaiting_image_selection',result.error
    assert result.batch_id=='image_batch_0002'
    assert len(cloud.submits)==2 and len(smtp.messages)==1
    assert not (revision.run_dir/'production/image-selection/image_batch_0001').exists()
    assert tree_identity(setup['run'])==before


def test_imported_choice_cannot_be_changed_through_a_new_owned_batch(revision_source):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.runtime.production_image_selection import prepare_image_batch,consume_image_selection
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    from integration.test_image_selection_flow import SMTP
    setup=revision_source;path,_=revision_request(setup)
    result=create_scene_revision(setup['run'],path)
    assert result.status=='revision_ready',result.error
    frozen=load_frozen_inputs(result.run_dir);units,timeline=load_scene_common_prefix(frozen)
    bible,plan=load_committed_plan(frozen,units,timeline)
    paths=RuntimePaths.from_config(frozen.config);logger=RunLogger(result.run_dir,production=True);smtp=SMTP()
    pending=prepare_image_batch(frozen,units,timeline,
        [result.run_dir/'production/jimeng'/sid/'candidates.json' for sid in plan['batches'][0]],
        batch_index=1,paths=paths,logger=logger,smtp_factory=smtp.factory)
    assert pending.status=='awaiting_image_selection',pending.error
    batch=json.loads((Path(pending.selection_template).parent/'batch.json').read_text(encoding='utf-8'))
    value=json.loads(Path(pending.selection_template).read_text(encoding='utf-8'))
    value.update(intent='accept',selections=[dict(scene_id=s['scene_id'],candidate_id=s['candidates'][-1]['candidate_id'],
        sha256=s['candidates'][-1]['sha256']) for s in batch['scenes']])
    selection=result.run_dir/'changed-inherited-choice.json';selection.write_text(json.dumps(value),encoding='utf-8')
    refused=consume_image_selection(frozen,units,timeline,selection,paths=paths,logger=logger)
    assert refused.status=='blocked',refused.error
    assert not (Path(pending.selection_template).parent/'accepted.json').exists()


@pytest.mark.parametrize('effect',['image_manifest','image_terminal','smtp'])
def test_revision_cannot_hide_unfinished_paid_result_or_unknown_mail(revision_source,tmp_path,effect):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    setup=revision_source;run=setup['run'];sid=setup['plan']['scenes'][1]['scene_id']
    path,value=revision_request(setup,kind='regenerate_images')
    value.update(scene_ids=[sid],choices=[])
    path.write_text(json.dumps(value),encoding='utf-8')
    if effect in ('image_manifest','image_terminal'):
        # Paid results exist but their scene commit was interrupted.
        sid=setup['plan']['scenes'][0]['scene_id'];value['scene_ids']=[sid]
        path.write_text(json.dumps(value),encoding='utf-8')
        missing=[run/'production/jimeng'/sid/'candidates.json',run/'production/image-selection',
                 run/'production/reference-images',run/'production/jimeng'/setup['plan']['scenes'][1]['scene_id']]
    else:
        batch=run/'production/image-selection/image_batch_0002'
        missing=[batch/'accepted.json',run/'production/image-selection/complete-acceptance.json',
                 run/'production/reference-images/wan-inputs.json',*batch.glob('mail/part_*/attempt_*/receipt.json')]
    if (run/'production/scene-clips').exists():missing.append(run/'production/scene-clips')
    moved=[];terminals=[]
    try:
        for i,original in enumerate(missing):
            backup=tmp_path/f'preserved-{i}';original.rename(backup);moved.append((original,backup))
        if effect=='image_terminal':
            for intent in (run/'production/jimeng'/sid).glob('request_*/intent.json'):
                terminal=intent.with_name('terminal.json');assert not terminal.exists()
                terminal.write_text('{}',encoding='utf-8');terminals.append(terminal)
        before=tree_identity(run)
        result=create_scene_revision(run,path)
        assert result.status=='blocked' and result.run_dir is None,result.error
        if effect!='image_terminal':assert 'unknown/running' in result.error['message'],result.error
        assert tree_identity(run)==before
    finally:
        for terminal in terminals:terminal.unlink()
        for original,backup in reversed(moved):backup.rename(original)


@pytest.mark.parametrize('mutation',['choice_dependency','content_edge','request','snapshot_omission'])
def test_rehashed_revision_proof_still_requires_actual_dependencies_and_plan(revision_source,mutation):
    from copy import deepcopy
    from dataclasses import replace
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.production_state import json_bytes
    from video_ai.runtime.scene_revision_records import artifact,require_scene_revision
    setup=revision_source;path,_=revision_request(setup)
    result=create_scene_revision(setup['run'],path)
    assert result.status=='revision_ready',result.error
    frozen=load_frozen_inputs(result.run_dir);proof=require_scene_revision(frozen)
    commit=deepcopy(proof['commit'])
    def save(path,value):
        path=Path(path);path.write_bytes(json_bytes(value));return artifact(path)
    if mutation in ('choice_dependency','snapshot_omission'):
        sidecar,bound=proof['imports']['choice:scene_0003'];sidecar=deepcopy(sidecar)
        if mutation=='choice_dependency':sidecar['dependency_import_ids'].remove('image:scene_0003')
        else:
            snapshot=sidecar['source_json_snapshot']
            omitted=next(row for row in snapshot['files'] if Path(row['path']).name=='candidates.json')
            snapshot['files'].remove(omitted)
        replacement=save(bound['path'],sidecar)
        index=json.loads(Path(commit['imports']['path']).read_text(encoding='utf-8'))
        index['imports']=[replacement if b['path']==bound['path'] else b for b in index['imports']]
        commit['imports']=save(commit['imports']['path'],index)
    elif mutation=='content_edge':
        invalidation=deepcopy(proof['invalidation']);invalidation['content_edges'].pop()
        commit['invalidation']=save(commit['invalidation']['path'],invalidation)
    else:
        request=json.loads(Path(commit['request']['path']).read_text(encoding='utf-8'))
        request['reason']='Changed request with a new internally consistent file SHA'
        commit['request']=save(commit['request']['path'],request)
    options=deepcopy(frozen.options);options['scene_revision']=save(result.revision_commit,commit)
    with pytest.raises(ValueError):require_scene_revision(replace(frozen,options=options))


def test_common_reconfiguration_prepares_and_uses_new_automatic_prefix(revision_source,monkeypatch):
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.production import make_video
    import video_ai.production as production
    import video_ai.runtime.production_storyboard as units_module
    from video_ai.runtime.production_state import ProductionRefused
    setup=revision_source;path,value=revision_request(setup)
    raw=thaw(setup['frozen'].options['config_snapshot']['raw'])
    raw['media']['timeline']['opening_seconds']=0.25
    config=path.with_name('common-target-'+path.name);config.write_text(json.dumps(raw),encoding='utf-8')
    value.update(kind='reconfigure',scene_ids=[],choices=[],config_path=str(config))
    path.write_text(json.dumps(value),encoding='utf-8')
    before=tree_identity(setup['run'])
    result=create_scene_revision(setup['run'],path)
    assert result.status=='revision_ready',result.error
    def stop(*args,**kwargs):raise ProductionRefused('new automatic units reached; no model called')
    monkeypatch.setattr(units_module,'produce_units',stop)
    monkeypatch.setattr(production,'_finish_prefix',lambda *args:None)
    resumed=make_video(run_dir=result.run_dir)
    assert resumed.status=='blocked' and resumed.active_stage=='units',resumed.error
    assert 'automatic units reached' in resumed.error['message']
    assert (result.run_dir/'production/production-state.json').exists()
    assert not (result.run_dir/'production/units.json').exists()
    assert tree_identity(setup['run'])==before


@pytest.mark.parametrize('scene_index',[0,1])
def test_explicitly_regenerated_bad_later_image_preserves_valid_earlier_choice(revision_source,scene_index):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision
    setup=revision_source;sid=setup['plan']['scenes'][scene_index]['scene_id']
    manifest=json.loads((setup['run']/'production/jimeng'/sid/'candidates.json').read_text(encoding='utf-8'))
    image=Path(manifest['candidates'][0]['path']);original=image.read_bytes()
    request,value=revision_request(setup,kind='regenerate_images');value.update(scene_ids=[sid],choices=[])
    request.write_text(json.dumps(value),encoding='utf-8')
    try:
        image.write_bytes(b'broken original image')
        before=tree_identity(setup['run'])
        result=create_scene_revision(setup['run'],request)
        assert result.status=='revision_ready',result.error
        proof=require_scene_revision(load_frozen_inputs(result.run_dir))
        assert 'choice:scene_0003' in proof['imports']
        assert 'image:'+sid not in proof['imports']
        assert tree_identity(setup['run'])==before
    finally:image.write_bytes(original)


def test_rehashed_revision_origin_read_window_hashes_frozen_font_once(revision_source,monkeypatch):
    import os
    if os.name!='nt':pytest.skip('protected digest reuse requires Windows mandatory sharing')
    import video_ai.runtime.manifest as manifest
    from video_ai.runtime._scene_revision_origins import capture_origin
    setup=revision_source;font=Path(setup['frozen'].options['execution_policy']['input_identities']['font']['path'])
    original=manifest._hash_open_file;calls=[]
    def counted(stream,path):
        if path==font:calls.append(path)
        return original(stream,path)
    monkeypatch.setattr(manifest,'_hash_open_file',counted)
    capture_origin(setup['frozen'],'choice','scene_0003')
    assert len(calls)==1
    capture_origin(setup['frozen'],'choice','scene_0003')
    assert len(calls)==2


def test_rehashed_revision_reselected_baseline_supports_new_reference_submission(revision_source,monkeypatch):
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.runtime.production_image_selection import prepare_image_batch,consume_image_selection
    from video_ai.runtime.production_reference_images import produce_reference_batch
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    from integration.test_image_selection_flow import SMTP
    from integration.test_jimeng_reference_flow import configured_cloud
    setup=revision_source;path,_=revision_request(setup)
    result=create_scene_revision(setup['run'],path)
    assert result.status=='revision_ready',result.error
    frozen=load_frozen_inputs(result.run_dir);units,timeline=load_scene_common_prefix(frozen)
    _,plan=load_committed_plan(frozen,units,timeline)
    paths=RuntimePaths.from_config(frozen.config);logger=RunLogger(result.run_dir,production=True);smtp=SMTP()
    pending=prepare_image_batch(frozen,units,timeline,
        [result.run_dir/'production/jimeng'/sid/'candidates.json' for sid in plan['batches'][0]],
        batch_index=1,paths=paths,logger=logger,smtp_factory=smtp.factory)
    assert pending.status=='awaiting_image_selection',pending.error
    batch=json.loads((Path(pending.selection_template).parent/'batch.json').read_text(encoding='utf-8'))
    value=json.loads(Path(pending.selection_template).read_text(encoding='utf-8'))
    value.update(intent='accept',selections=[dict(scene_id=s['scene_id'],candidate_id=s['candidates'][i]['candidate_id'],sha256=s['candidates'][i]['sha256'])
        for s,i in zip(batch['scenes'],[-1,0])])
    selected=result.run_dir/'confirmed-mixed-batch.json';selected.write_text(json.dumps(value),encoding='utf-8')
    accepted=consume_image_selection(frozen,units,timeline,selected,paths=paths,logger=logger)
    assert accepted.status=='image_batch_accepted',accepted.error
    cloud,_,kwargs=configured_cloud(setup,monkeypatch);kwargs.pop('reference_settings_path')
    original_http=cloud.official_request
    def guarded_http(method,url,**arguments):
        if arguments.get('ownership_check') is not None:arguments['ownership_check']()
        return original_http(method,url,**arguments)
    monkeypatch.setattr(cloud,'official_request',guarded_http)
    referenced=produce_reference_batch(frozen,units,timeline,batch_index=2,paths=paths,logger=logger,**kwargs)
    assert referenced.status=='awaiting_image_selection',referenced.error
    assert len(cloud.submits)==2
    assert not (result.run_dir/'production/jimeng/scene_0001').exists()
