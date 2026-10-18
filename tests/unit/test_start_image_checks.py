import json
from pathlib import Path
import pytest
from start_image_helpers import make_images_run,fake_media,image_review


@pytest.mark.parametrize('changed',['directions','basis'])
def test_committed_consumer_rechecks_visual_directions_and_failed_basis(storyboard_run,monkeypatch,changed):
    from video_ai.runtime.start_image_checks import prepare_start_images,finalize_start_images,load_committed_start_images
    from video_ai.runtime.manifest import hash_file,thaw
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    board=json.loads((run/'storyboard.json').read_text(encoding='utf-8'))
    basis=run/'failed-review-basis.json'
    entries=[dict(req,verdict='failed') for shot in board['shots'] for req in shot['visual_requirements']]
    basis.write_text(json.dumps(dict(global_verdict='failed',entries=entries)),encoding='utf-8')
    directions=run/'logs/start-images/visual-directions.json';directions.parent.mkdir(parents=True,exist_ok=True)
    data=dict(schema_version=1,run_id=run.name,storyboard_identity=thaw(hash_file(run/'storyboard.json')),
        review_basis_identity=thaw(hash_file(basis)),shots={shot['shot_id']:dict(positive=shot['image_prompt'],
        negative='',reason='A reviewed static correction.',requirement_ids=[req['requirement_id'] for req in shot['visual_requirements'] if req['unit_id']==shot['primary_unit_id']]) for shot in board['shots']})
    directions.write_text(json.dumps(data),encoding='utf-8')
    assert prepare_start_images(config,run_dir=run,image_inputs_path=inputs).status=='review_required'
    path,_=image_review(run)
    assert finalize_start_images(config,run_dir=run,review_path=path).passed
    assert load_committed_start_images(run)['passed'] is True
    (directions if changed=='directions' else basis).write_text('{}',encoding='utf-8')
    with pytest.raises((ValueError,OSError)):load_committed_start_images(run)


def test_user_images_need_full_review_before_commit(storyboard_run,monkeypatch):
    from video_ai.runtime.start_image_checks import prepare_start_images,finalize_start_images,load_committed_start_images
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    before=store.snapshot()
    result=prepare_start_images(config,run_dir=run,image_inputs_path=inputs)
    assert result.status=='review_required' and not result.passed and result.image_count==3
    assert store.snapshot()['stages']['start_images']['status']=='running'
    assert set(store.snapshot()['units']['image'])=={'shot_0001','shot_0002','shot_0003'}
    with pytest.raises(ValueError):load_committed_start_images(run)
    path,_=image_review(run)
    assert finalize_start_images(config,run_dir=run,review_path=path).passed
    report=load_committed_start_images(run)
    assert report['validation']['ready_for_source_clips'] is True
    assert report['validation']['motion_semantics']==report['validation']['sync']=='unverified'
    for name in ('speech','timeline','storyboard'):assert store.snapshot()['stages'][name]==before['stages'][name]
    store.record_stage('source_clips','running')
    assert load_committed_start_images(run)['passed'] is True


@pytest.mark.parametrize('bad',['missing','duplicate','failed','unverified','png','timestamp','unknown','evidence','bool','motion','media_note','note_png','note_reference'])
def test_any_missing_or_stale_visual_review_refused(storyboard_run,monkeypatch,bad):
    from video_ai.runtime.start_image_checks import prepare_start_images,finalize_start_images
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    prepare_start_images(config,run_dir=run,image_inputs_path=inputs);path,data=image_review(run)
    if bad=='missing':data['entries'].pop()
    if bad=='duplicate':data['entries'].append(data['entries'][0])
    if bad in ('failed','unverified'):data['entries'][0]['verdict']=bad
    if bad=='png':data['entries'][0]['image_identity']['sha256']='a'*64
    if bad=='timestamp':data['reviewed_at']='2000-01-01T00:00:00+00:00'
    if bad=='unknown':data['extra']=True
    if bad=='evidence':Path(data['entries'][0]['evidence_identity']['path']).write_text('changed')
    if bad=='bool':data['entries'][0]['requirement_index']=False
    if bad=='motion':data['motion_semantics']='passed'
    if bad=='media_note':
        from video_ai.runtime.manifest import hash_file,thaw
        draft=json.loads((run/'images-draft.json').read_text())
        candidate=next(v for k,v in draft['request_evidence'].items() if '/media-' in k)
        data['entries'][0]['evidence_identity']=candidate
    if bad in ('note_png','note_reference'):
        from video_ai.runtime.manifest import hash_file,thaw
        note_path=Path(data['entries'][0]['evidence_identity']['path']);note=json.loads(note_path.read_text())
        if bad=='note_png':note['entries'][0]['image_identity']['sha256']='a'*64
        else:note['references']=[dict(entity_id='made-up',identity={})]
        note_path.write_text(json.dumps(note),encoding='utf-8')
        for entry in data['entries']:entry['evidence_identity']=thaw(hash_file(note_path))
    path.write_text(json.dumps(data),encoding='utf-8')
    result=finalize_start_images(config,run_dir=run,review_path=path)
    assert not result.passed and store.snapshot()['stages']['start_images']['status']=='failed'
    assert not (run/'images.json').exists()


@pytest.mark.parametrize('target',['png','source','input_map','review','evidence','config'])
def test_committed_consumer_detects_all_input_changes(storyboard_run,monkeypatch,target):
    from video_ai.runtime.start_image_checks import prepare_start_images,finalize_start_images,load_committed_start_images
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    prepare_start_images(config,run_dir=run,image_inputs_path=inputs);review,data=image_review(run)
    assert finalize_start_images(config,run_dir=run,review_path=review).passed
    paths=dict(png=run/'shots/shot_0001/start.png',source=run/'user.png',input_map=inputs,review=review,
        evidence=Path(data['entries'][0]['evidence_identity']['path']),config=config.config_file)
    path=paths[target];before=path.read_bytes();path.write_bytes(before+b' ')
    try:
        with pytest.raises((ValueError,OSError)):load_committed_start_images(run)
    finally:
        if target=='config':path.write_bytes(before)


@pytest.mark.parametrize('bad',['lock','orphan','unknown_shot','bad_dimensions'])
def test_invalid_inputs_never_start_generation(storyboard_run,monkeypatch,bad):
    from video_ai.runtime.start_image_checks import prepare_start_images,StartImageRefusal
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    if bad=='lock':(run/'.start-images.lock').write_text('foreign')
    if bad=='orphan':(run/'images-draft.json').write_text('orphan')
    if bad=='unknown_shot':
        data=json.loads(inputs.read_text());data['shots']['shot_9999']=str(run/'user.png');inputs.write_text(json.dumps(data))
    if bad=='bad_dimensions':
        with pytest.raises(StartImageRefusal):prepare_start_images(config,run_dir=run,width=1024,height=1024)
    elif bad in ('lock','orphan'):
        with pytest.raises(StartImageRefusal):prepare_start_images(config,run_dir=run,image_inputs_path=inputs)
    else:assert not prepare_start_images(config,run_dir=run,image_inputs_path=inputs).passed
    assert store.snapshot()['stages']['start_images']['status']=='pending'


def test_orphan_final_report_cannot_be_consumed(storyboard_run,monkeypatch):
    from video_ai.runtime.start_image_checks import prepare_start_images,finalize_start_images,load_committed_start_images
    from video_ai.runtime.manifest import ManifestStore
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    prepare_start_images(config,run_dir=run,image_inputs_path=inputs);review,_=image_review(run)
    original=ManifestStore._write
    def fail(self,data):
        if data['stages']['start_images']['status']=='completed':raise OSError('commit failed')
        return original(self,data)
    monkeypatch.setattr(ManifestStore,'_write',fail)
    assert not finalize_start_images(config,run_dir=run,review_path=review).passed
    assert (run/'images.json').exists()
    with pytest.raises(ValueError):load_committed_start_images(run)


@pytest.mark.parametrize('bad',['only_map','no_probe','no_decode','no_convert','other_shot','absolute_alias'])
def test_media_command_coverage_is_mandatory(storyboard_run,monkeypatch,bad):
    from video_ai.runtime import start_image_checks as sc
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    assert sc.prepare_start_images(config,run_dir=run,image_inputs_path=inputs).status=='review_required'
    board=sc.load_committed_storyboard(run);draft=json.loads((run/'images-draft.json').read_text())
    image=draft['images'][0]
    if bad=='only_map':image['evidence_identities']=['logs/start-images/input-map.json']
    if bad in ('no_probe','no_decode','no_convert'):
        marker={'no_probe':'probe','no_decode':'decode','no_convert':'convert'}[bad]
        image['evidence_identities']=[n for n in image['evidence_identities'] if marker not in n]
    if bad=='other_shot':image['evidence_identities']=draft['images'][1]['evidence_identities']
    if bad=='absolute_alias':
        key=next(iter(draft['request_evidence']));item=draft['request_evidence'][key]
        draft['request_evidence'][item['path'].replace('\\','/')]=item
    with pytest.raises((ValueError,OSError)):sc._validate_draft(config,run,draft,board,store.snapshot())


def test_completed_image_commit_survives_post_write_interrupt(storyboard_run,monkeypatch):
    from video_ai.runtime import start_image_checks as sc
    from video_ai.runtime.manifest import ManifestStore
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    assert sc.prepare_start_images(config,run_dir=run,image_inputs_path=inputs).status=='review_required'
    review,_=image_review(run);original=ManifestStore._write
    def interrupted(self,data):
        original(self,data)
        if data['stages']['start_images']['status']=='completed':raise KeyboardInterrupt()
    monkeypatch.setattr(ManifestStore,'_write',interrupted)
    assert sc.finalize_start_images(config,run_dir=run,review_path=review).passed
    assert sc.load_committed_start_images(run)['passed'] is True


def test_foreign_replaced_image_lock_is_retained(storyboard_run,monkeypatch):
    from video_ai.runtime import start_image_checks as sc
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    original=sc.adapt_image
    def replace_owner(*a,**kw):
        result=original(*a,**kw);(run/'.start-images.lock').write_text('{"token":"foreign"}')
        return result
    monkeypatch.setattr(sc,'adapt_image',replace_owner)
    assert not sc.prepare_start_images(config,run_dir=run,image_inputs_path=inputs).passed
    assert (run/'.start-images.lock').read_text()=='{"token":"foreign"}'
    assert store.snapshot()['stages']['start_images']['status']=='failed'


def test_diagnostic_write_failure_preserves_failed_stage(storyboard_run,monkeypatch):
    from video_ai.runtime import start_image_checks as sc
    from video_ai.runtime.logging import RunLogger
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    sc.prepare_start_images(config,run_dir=run,image_inputs_path=inputs);path,data=image_review(run)
    data['entries'][0]['verdict']='failed';path.write_text(json.dumps(data))
    def disk_full(*a,**kw):raise OSError('diagnostic disk full')
    monkeypatch.setattr(RunLogger,'exception',disk_full)
    assert not sc.finalize_start_images(config,run_dir=run,review_path=path).passed
    assert store.snapshot()['stages']['start_images']['status']=='failed'
