"""Real ffmpeg coverage for immutable, traceable selection mail media."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
from image_helpers import write_png


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


@pytest.fixture
def sheet_context(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.logging import RunLogger
    run, config, paths = runtime_run
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config = replace(config, tools=dict(config.tools, ffmpeg=actual.tools['ffmpeg'], ffprobe=actual.tools['ffprobe']),
                     media=replace(config.media, font_file=actual.media.font_file))
    return run, dict(config=config, paths=paths, logger=RunLogger(run, production=True))


def candidate(run, scene='scene_0002', number=1):
    path = write_png(run / f'{scene}-{number}.png', 80, 160)
    raw = path.read_bytes()
    return dict(candidate_id=f'request_01_image_{number:02d}', request_id='request_01', task_id='task-1',
                req_key='test', path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                width=80, height=160, format='png')


def batch_for(run, count=1):
    return dict(schema_version=2, production_strategy='paragraph_jimeng_v1', run_id=run.name,
                batch_id='image_batch_0002', batch_index=2, source_sha256='1'*64, units_sha256='2'*64,
                timeline_sha256='3'*64, scene_plan_sha256='4'*64, visual_bible_sha256='5'*64,
                baseline_bindings=[], delivery=dict(sender='318575094@qq.com', recipient='318575094@qq.com', max_mime_bytes=15*1024*1024),
                scenes=[dict(scene_id='scene_0002', summary='summary', unit_ids=['unit_0002'], text_start=0,
                             text_end=4, original_text='text', reference_bindings=[], candidate_manifest={},
                             candidates=[candidate(run, number=i) for i in range(1, count+1)])])


def test_real_previews_contain_original_and_offer_all_fallback_sizes(sheet_context):
    from video_ai.media.selection_sheet import prepare_email_media
    from video_ai.media.images import _command
    run, kwargs = sheet_context
    batch = batch_for(run)
    original = Path(batch['scenes'][0]['candidates'][0]['path'])
    before = original.read_bytes()
    media = prepare_email_media(batch, **kwargs)
    assert set(media) == {'schema_version', 'run_id', 'batch_id', 'scene_manifest_sha256', 'images', 'contact_sheets'}
    assert media['scene_manifest_sha256'] == hashlib.sha256(canonical(batch)).hexdigest()
    assert [(r['kind'], r['width'], r['height']) for r in media['images']] == [
        ('original', 80, 160), ('preview', 960, 540), ('preview', 640, 360), ('preview', 320, 180), ('preview', 160, 90)]
    for row in media['images']:
        assert set(row) == {'kind', 'scene_id', 'candidate_id', 'source_sha256', 'path', 'bytes', 'sha256', 'width', 'height'}
        raw = Path(row['path']).read_bytes()
        assert (row['bytes'], row['sha256']) == (len(raw), hashlib.sha256(raw).hexdigest())
        assert row['source_sha256'] == hashlib.sha256(before).hexdigest()
    preview = media['images'][1]
    pixels = _command((kwargs['config'].tools['ffmpeg'], '-nostdin', '-v', 'error', '-i', preview['path'],
                       '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'), unit_id='pixels', **kwargs).stdout_path.read_bytes()
    assert max(pixels[:3]) < 5
    center = (270*960+480)*3
    assert all(abs(a-b) < 5 for a, b in zip(pixels[center:center+3], (120, 150, 200)))
    assert original.read_bytes() == before
    assert json.loads((run/'production/image-selection/image_batch_0002/mail/media.json').read_text()) == media
    published = [Path(row['path']) for row in media['images'] + media['contact_sheets']]
    timestamps = [path.stat().st_mtime_ns for path in published]
    assert prepare_email_media(batch, **kwargs) == media
    assert [path.stat().st_mtime_ns for path in published] == timestamps


def test_contact_pages_include_selected_baseline_once_and_cover_all_candidates(sheet_context):
    from video_ai.media.selection_sheet import prepare_email_media
    run, kwargs = sheet_context
    batch = batch_for(run, count=8)
    prior = deepcopy(batch)
    prior.update(batch_id='image_batch_0001', batch_index=1)
    prior['scenes'] = [dict(batch['scenes'][0], scene_id='scene_0001', candidates=[candidate(run, 'scene_0001')])]
    chosen = prior['scenes'][0]['candidates'][0]
    selection = {key: chosen[key] for key in ('candidate_id', 'sha256', 'path', 'bytes', 'req_key', 'request_id', 'task_id')}
    selection['scene_id'] = 'scene_0001'
    folder = run/'production/image-selection/image_batch_0001'
    folder.mkdir(parents=True)
    (folder/'batch.json').write_bytes(canonical(prior))
    accepted = dict(schema_version=2, production_strategy='paragraph_jimeng_v1', run_id=run.name,
                    batch_id='image_batch_0001', scene_manifest_sha256=hashlib.sha256(canonical(prior)).hexdigest(),
                    scene_plan_sha256=prior['scene_plan_sha256'], visual_bible_sha256=prior['visual_bible_sha256'],
                    selections=[selection], baseline_bindings=[], source_submission_sha256='6'*64)
    (folder/'accepted.json').write_bytes(canonical(accepted))
    batch['baseline_bindings'] = [dict(kind=kind, id=ident, scene_id='scene_0001', candidate_id=chosen['candidate_id'], sha256=chosen['sha256'])
                                  for kind, ident in [('character', 'hero'), ('style', 'main')]]
    media = prepare_email_media(batch, **kwargs)
    originals = [r for r in media['images'] if r['kind'] == 'original']
    assert len(originals) == 9 and originals[0]['scene_id'] == 'scene_0001'
    sheets = media['contact_sheets']
    assert [(r['width'], r['height'], len(r['sources'])) for r in sheets] == [(960, 1080, 8), (960, 270, 1)]
    expected = [dict(scene_id=r['scene_id'], candidate_id=r['candidate_id'], sha256=r['sha256']) for r in originals]
    assert [s for row in sheets for s in row['sources']] == expected
    for sheet in sheets:
        assert set(sheet) == {'path', 'bytes', 'sha256', 'width', 'height', 'sources'}
        raw = Path(sheet['path']).read_bytes()
        assert sheet['sha256'] == hashlib.sha256(raw).hexdigest()
    assert len(batch['baseline_bindings']) == 2


def test_resume_refuses_tampered_preview_and_changed_batch(sheet_context):
    from video_ai.media.selection_sheet import prepare_email_media
    run, kwargs = sheet_context
    batch = batch_for(run)
    media = prepare_email_media(batch, **kwargs)
    changed = deepcopy(batch)
    changed['scenes'][0]['original_text'] = 'replacement'
    with pytest.raises(ValueError, match='identity|conflict'):
        prepare_email_media(changed, **kwargs)
    preview = Path(media['images'][1]['path'])
    preview.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed|identity|conflict'):
        prepare_email_media(batch, **kwargs)
    assert preview.read_bytes() == b'tampered'


@pytest.mark.parametrize('derivative', ['preview', 'contact_sheet'])
def test_resume_refuses_paired_derivative_and_manifest_tampering(sheet_context, derivative):
    from video_ai.media.selection_sheet import prepare_email_media
    from video_ai.media.images import _command
    run, kwargs = sheet_context
    batch = batch_for(run)
    media = prepare_email_media(batch, **kwargs)
    row = media['images'][1] if derivative == 'preview' else media['contact_sheets'][0]
    replacement = run/'replacement.jpg'
    _command((kwargs['config'].tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-f', 'lavfi',
              '-i', f'color=c=red:s={row["width"]}x{row["height"]}', '-frames:v', '1',
              '-q:v', '3', replacement), unit_id='replacement', **kwargs)
    raw = replacement.read_bytes()
    assert hashlib.sha256(raw).hexdigest() != row['sha256']
    Path(row['path']).write_bytes(raw)
    row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest = run/'production/image-selection/image_batch_0002/mail/media.json'
    manifest.write_bytes(canonical(media))
    with pytest.raises(ValueError, match='conflict'):
        prepare_email_media(batch, **kwargs)
    assert Path(row['path']).read_bytes() == raw
    assert json.loads(manifest.read_text()) == media


def test_partial_preparation_reuses_identical_files_and_refuses_conflicting_orphan(sheet_context):
    from video_ai.media.selection_sheet import prepare_email_media
    run, kwargs = sheet_context
    batch = batch_for(run)
    media = prepare_email_media(batch, **kwargs)
    manifest = run/'production/image-selection/image_batch_0002/mail/media.json'
    manifest.unlink()
    preview = Path(media['images'][1]['path'])
    before = preview.stat().st_mtime_ns
    assert prepare_email_media(batch, **kwargs) == media
    assert preview.stat().st_mtime_ns == before
    manifest.unlink()
    preview.write_bytes(b'unbound partial artifact')
    with pytest.raises(ValueError, match='conflict'):
        prepare_email_media(batch, **kwargs)
    assert preview.read_bytes() == b'unbound partial artifact'
    assert not manifest.exists()


def test_lost_parent_lock_stops_before_derivative_commit(sheet_context, monkeypatch):
    from video_ai.media import selection_sheet
    from video_ai.runtime.production_state import RunLock
    run, kwargs = sheet_context
    batch = batch_for(run)
    command = selection_sheet._command
    with RunLock(run) as held:
        owner = held.path.read_bytes()
        def lose_lock(args, **options):
            result = command(args, **options)
            if '-c:v' in args:
                held.path.write_bytes(b'{"changed":true}')
            return result
        monkeypatch.setattr(selection_sheet, '_command', lose_lock)
        try:
            with pytest.raises(ValueError, match='lock ownership'):
                selection_sheet.prepare_email_media(batch, **kwargs)
        finally:
            held.path.write_bytes(owner)
    mail = run/'production/image-selection/image_batch_0002/mail'
    assert not (mail/'media.json').exists()
    assert not list((mail/'previews').glob('*.jpg'))


@pytest.mark.parametrize('failure', ['sha', 'dimensions', 'label', 'corrupt'])
def test_refuses_changed_or_undecodable_original_and_unsafe_labels(sheet_context, failure):
    from video_ai.media.selection_sheet import prepare_email_media
    run, kwargs = sheet_context
    batch = batch_for(run)
    row = batch['scenes'][0]['candidates'][0]
    if failure == 'sha': row['sha256'] = '0'*64
    if failure == 'dimensions': row['width'] = 40
    if failure == 'label': row['candidate_id'] = "bad':drawtext=text=unsafe"
    if failure == 'corrupt':
        Path(row['path']).write_bytes(b'invalid image')
        row.update(bytes=13, sha256=hashlib.sha256(b'invalid image').hexdigest())
    with pytest.raises((ValueError, RuntimeError)):
        prepare_email_media(batch, **kwargs)
    assert not (run/'production/image-selection/image_batch_0002/mail/media.json').exists()
