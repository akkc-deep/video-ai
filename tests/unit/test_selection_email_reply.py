"""Interactive mail remains local and preserves exact source image bindings."""
import base64
import hashlib
import json
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace

import pytest

from video_ai.adapters.selection_email import build_messages, EmailPreconditionError


def reply_batch(tmp_path, *, scenes=3, candidates=4, large_preview_bytes=0):
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    images, rows = [], []
    for index in range(1, scenes + 1):
        scene_id = f'scene_{index:04d}'
        choices = []
        for number in range(1, candidates + 1):
            candidate_id = f'request_01_image_{number:02d}'
            pixels = png + bytes([index, number])
            source = pixels + b'original' * 3000
            digest = hashlib.sha256(source).hexdigest()
            for kind, data, width in [('original', source, 1920),
                                      ('preview', pixels + b'large' * large_preview_bytes, 960),
                                      ('preview', pixels + b'small', 320)]:
                path = tmp_path / f'{scene_id}-{candidate_id}-{kind}-{width}.png'
                path.write_bytes(data)
                images.append(dict(kind=kind, scene_id=scene_id, candidate_id=candidate_id,
                    source_sha256=digest, path=str(path), bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(), width=width, height=width))
            choices.append(dict(candidate_id=candidate_id, sha256=digest))
        rows.append(dict(scene_id=scene_id, summary='场景摘要', original_text='交付原文。',
                         candidates=choices, reference_bindings=[]))
    return dict(run_id='run_reply', batch_id='image_batch_0001', scenes=rows,
                baseline_bindings=[]), dict(images=images, contact_sheets=[])


def build(batch, media, **kwargs):
    return build_messages(batch, media, created_at='2026-11-29T01:00:00Z',
        sender='318575094@qq.com', recipient='318575094@qq.com',
        max_mime_bytes=kwargs.pop('max_mime_bytes', 15 * 1024 * 1024), **kwargs)


def test_reply_mode_one_preview_per_candidate_and_complete_explicit_template(tmp_path):
    batch, media = reply_batch(tmp_path)
    rows = build(batch, media, reply_mode=True)
    assert len(rows) == 1
    assert rows == build(batch, media, reply_mode=True)
    parsed = BytesParser(policy=policy.default).parsebytes(rows[0]['mime_bytes'])
    plain = parsed.get_body(preferencelist=('plain',)).get_content()
    assert rows[0]['message_id'] == parsed['Message-ID']
    assert rows[0]['message_id'] in plain
    assert '确认=提交' in plain and '.png' in plain
    assert '一致性' in plain
    for scene in batch['scenes']:
        assert plain.splitlines().count(scene['scene_id'] + '=填写候选编号') == 1
        for candidate in scene['candidates']:
            assert candidate['candidate_id'] in plain
            assert candidate['sha256'] in plain
    images = [p for p in parsed.walk() if p.get_content_maintype() == 'image']
    assert len(images) == len(list(parsed.iter_attachments())) == 12
    originals = {image['sha256'] for image in media['images'] if image['kind'] == 'original'}
    assert all(hashlib.sha256(p.get_payload(decode=True)).hexdigest() not in originals for p in images)
    assert len(rows[0]['attachment_bindings']) == 12
    assert {b['original_sha256'] for b in rows[0]['attachment_bindings']} == originals


def test_reply_mode_downsizes_whole_batch_instead_of_splitting(tmp_path):
    batch, media = reply_batch(tmp_path, large_preview_bytes=1500)
    rows = build(batch, media, reply_mode=True, max_mime_bytes=26000)
    assert len(rows) == 1 and len(rows[0]['mime_bytes']) <= 26000
    assert len(rows[0]['attachment_bindings']) == 12
    small = {r['sha256'] for r in media['images'] if r['width'] == 320}
    assert any(b['attachment_sha256'] in small for b in rows[0]['attachment_bindings'])
    with pytest.raises(EmailPreconditionError, match='minimum batch preview MIME exceeds size limit'):
        build(batch, media, reply_mode=True, max_mime_bytes=100)


def test_reply_mode_requires_previews_instead_of_sending_originals(tmp_path):
    batch, media = reply_batch(tmp_path, scenes=1, candidates=1)
    media['images'] = [r for r in media['images'] if r['kind'] == 'original']
    with pytest.raises(EmailPreconditionError, match='candidate preview unavailable'):
        build(batch, media, reply_mode=True)


def test_reply_mode_preserves_legacy_default_bytes(tmp_path):
    batch, media = reply_batch(tmp_path)
    assert build(batch, media) == build(batch, media, reply_mode=False)
    assert len(build(batch, media)) == 2


def test_mail_reply_context_restores_nested_and_exception_state():
    from video_ai.mail_workflow_context import mail_reply_mode, mail_reply_context
    assert mail_reply_mode() is False
    with mail_reply_context():
        assert mail_reply_mode() is True
        with mail_reply_context(False):
            assert mail_reply_mode() is False
        assert mail_reply_mode() is True
        with pytest.raises(RuntimeError):
            with mail_reply_context(False):
                raise RuntimeError('local')
        assert mail_reply_mode() is True
    assert mail_reply_mode() is False


@pytest.mark.parametrize('initial_reply_mode', [False, True])
def test_interrupted_notification_keeps_original_mime_mode(runtime_run, tmp_path, monkeypatch, initial_reply_mode):
    from video_ai.mail_workflow_context import mail_reply_context
    from video_ai.runtime import production_image_selection as selection
    from video_ai.runtime import _scene_revision_origins as origins
    run = runtime_run[0]
    batch, media = reply_batch(tmp_path, scenes=1, candidates=2)
    batch['run_id'] = run.name
    batch['delivery'] = dict(sender='318575094@qq.com', recipient='318575094@qq.com',
                             max_mime_bytes=15 * 1024 * 1024)
    monkeypatch.setattr(selection, 'prepare_email_media', lambda *args, **kwargs: media)
    monkeypatch.setattr(origins, 'inherited', lambda *args: dict(bible=dict(baselines=[])))
    interrupted = True

    def write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert path.read_bytes() == raw
        else:
            path.write_bytes(raw)

    def save(path, value):
        if interrupted and path.name == 'notification.json':
            raise InterruptedError('simulated local crash')
        write(path, json.dumps(value, sort_keys=True).encode())

    store = SimpleNamespace(run=run, owned=lambda: None, bytes=write, save=save)
    frozen = SimpleNamespace(config=None)
    with mail_reply_context(initial_reply_mode), pytest.raises(InterruptedError):
        selection._notification(store, frozen, batch, paths=None, logger=None)
    mail = run / 'production/image-selection/image_batch_0001/mail'
    original = {path: path.read_bytes() for path in mail.rglob('message.eml')}
    interrupted = False
    with mail_reply_context(not initial_reply_mode):
        result = selection._notification(store, frozen, batch, paths=None, logger=None)
    assert result['parts'] and all(path.read_bytes() == raw for path, raw in original.items())
    monkeypatch.setattr(selection, 'prepare_email_media', lambda *a, **k: pytest.fail('historical media rebuilt'))
    with mail_reply_context(not initial_reply_mode):
        assert selection._notification(store, frozen, batch, paths=None, logger=None) == result
