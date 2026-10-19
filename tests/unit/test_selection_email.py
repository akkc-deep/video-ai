"""Local-only MIME and SMTP contract checks; never contact a mail provider."""
from dataclasses import FrozenInstanceError, asdict, replace
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import ssl
import smtplib
import socketserver
import struct
import zlib
import random
import subprocess
import threading
import time

import pytest

from video_ai.selection_config import parse_selection_email
from video_ai.adapters.selection_email import (
    build_messages, EmailDeliveryUnknown, EmailPreconditionError, EmailRejected, SmtpSender,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def email_batch(tmp_path):
    # Real, fully decodable 1x1 PNG; same candidate ID in distinct scenes.
    import base64
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    scenes, images = [], []
    for index in range(1, 3):
        scene_id = f'scene_{index:04d}'
        path = tmp_path / f'{scene_id}.png'
        path.write_bytes(png)
        candidate = dict(candidate_id='request_01_image_01', request_id='request_01',
                         task_id='task', req_key='model', path=str(path), bytes=len(png),
                         sha256=digest(png), width=1, height=1, format='png')
        scenes.append(dict(scene_id=scene_id, summary='<summary>', original_text='完整原文<&>。\n第二行。',
                           candidates=[candidate], reference_bindings=[dict(kind='subject', id='hero', scene_id='scene_0001')]))
        images.append(dict(kind='original', scene_id=scene_id, candidate_id=candidate['candidate_id'],
                           source_sha256=candidate['sha256'], path=str(path), bytes=len(png),
                           sha256=candidate['sha256'], width=1, height=1))
    batch = dict(run_id='run_test', batch_id='image_batch_0001', scenes=scenes, baseline_bindings=[])
    media = dict(images=images, contact_sheets=[])
    return batch, media


def build(batch, media, **kwargs):
    return build_messages(batch, media, created_at='2026-10-18T10:00:00Z',
                          sender='318575094@qq.com', recipient='318575094@qq.com',
                          max_mime_bytes=kwargs.pop('max_mime_bytes', 15 * 1024 * 1024), **kwargs)


def test_settings_defaults_immutable_and_no_password():
    settings = parse_selection_email(None)
    assert settings.sender == settings.recipient == '318575094@qq.com'
    assert settings.smtp_security == 'ssl' and settings.smtp_port == 465
    assert settings.max_mime_bytes == 15 * 1024 * 1024
    assert 'password' not in asdict(settings)
    with pytest.raises(FrozenInstanceError):
        settings.smtp_port = 25


@pytest.mark.parametrize('value', [
    {'sender': 'other@example.com'}, {'recipient': '318575094@qq.com\r\nBcc: x'},
    {'smtp_security': 'plain'}, {'verify_ssl': False}, {'smtp_port': True}, {'smtp_port': 0},
    {'smtp_port': 65536}, {'smtp_host': 'host\nAUTH secret'}, {'smtp_host': 'host:465'},
    {'smtp_password_env': 'X-Y'}, {'smtp_password_env': 'PASSWORD\n'}, {'password': 'secret'},
    {'max_mime_bytes': True}, {'max_mime_bytes': 0}, {'timeout_seconds': True},
    {'timeout_seconds': float('inf')}, {'timeout_seconds': float('nan')},
    {'timeout_seconds': -1}, [], {'sender': None},
])
def test_settings_reject_unsafe_values(value):
    with pytest.raises(ValueError):
        parse_selection_email(value)


def test_mime_deterministic_complete_escaped_and_real_attachments(email_batch):
    batch, media = email_batch
    messages = build(batch, media)
    assert messages == build(batch, media)
    row = messages[0]
    assert set(row) == {'part', 'total', 'message_id', 'mime_bytes', 'attachment_bindings'}
    assert row['message_id'] == '<run_test.image_batch_0001.part_0001.attempt_0001@video-ai.local>'
    parsed = BytesParser(policy=policy.default).parsebytes(row['mime_bytes'])
    assert all(len(part.get_boundary()) <= 70 for part in parsed.walk() if part.is_multipart())
    for content_type in ('plain', 'html'):
        body = parsed.get_body(preferencelist=(content_type,)).get_content()
        assert 'run_test' in body and 'image_batch_0001' in body
        assert '完整原文' in body and '第二行' in body and 'hero' in body
        assert 'subject' in body and '一致性' in body
        assert 'production/image-selection/image_batch_0001/selection-template.json' in body
        assert 'scene_0001=request_01_image_01' in body
        if content_type == 'html':
            assert '&lt;summary&gt;' in body and '<summary>' not in body
            assert 'http://' not in body and 'https://' not in body
        else:
            for scene in batch['scenes']:
                choice = dict(scene_id=scene['scene_id'], candidate_id='request_01_image_01', sha256=scene['candidates'][0]['sha256'])
                assert json.dumps(choice, ensure_ascii=False, separators=(',', ':')) in body
    attachments = list(parsed.iter_attachments())
    assert len(attachments) == 2
    assert all(part.get_content_type() == 'image/png' for part in attachments)
    assert {digest(part.get_payload(decode=True)) for part in attachments} == {media['images'][0]['sha256']}
    assert {b['scene_id'] for b in row['attachment_bindings']} == {'scene_0001', 'scene_0002'}


def test_full_encoded_paging_and_fallback(email_batch, tmp_path):
    batch, media = email_batch
    # Large opaque payload remains a real PNG (ancillary trailing bytes are ignored by decoders).
    for image in media['images']:
        original = Path(image['path']).read_bytes()
        preview = tmp_path / (image['scene_id'] + '_preview.png')
        preview.write_bytes(original)
        media['images'].append(dict(image, kind='preview', path=str(preview), width=160, height=90))
        path = Path(image['path'])
        path.write_bytes(original + b'a' * 18000)
        image.update(bytes=path.stat().st_size, sha256=digest(path.read_bytes()), source_sha256=digest(path.read_bytes()))
        media['images'][-1]['source_sha256'] = image['sha256']
        next(s for s in batch['scenes'] if s['scene_id'] == image['scene_id'])['candidates'][0].update(bytes=image['bytes'], sha256=image['sha256'])
        if len(media['images']) == 4:
            break
    messages = build(batch, media, max_mime_bytes=10000)
    assert all(len(row['mime_bytes']) <= 10000 for row in messages)
    assert sum(len(row['attachment_bindings']) for row in messages) == 2
    assert all(b['attachment_sha256'] != b['original_sha256'] for row in messages for b in row['attachment_bindings'])
    with pytest.raises(EmailPreconditionError):
        build(batch, media, max_mime_bytes=100)


def test_size_paging_never_drops_candidate_and_uses_stable_total(email_batch):
    batch, media = email_batch
    one = build(dict(batch, scenes=batch['scenes'][:1]), media)[0]
    limit = len(one['mime_bytes']) + 10
    rows = build(batch, media, max_mime_bytes=limit)
    assert len(rows) == 2
    for index, row in enumerate(rows, 1):
        assert row['part'] == index and row['total'] == 2
        assert len(row['mime_bytes']) <= limit
    assert len([b for r in rows for b in r['attachment_bindings']]) == 2


def test_real_incompressible_pngs_respect_full_15_mib_mime_limit(email_batch, tmp_path):
    batch, media = email_batch
    batch['scenes'] = batch['scenes'][:1]
    batch['scenes'][0]['candidates'] = []
    media['images'] = []
    rng = random.Random(42)
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    for index in range(10):
        pixels = b''.join(b'\x00' + rng.randbytes(900 * 3) for _ in range(600))
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 900, 600, 8, 2, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
        path = tmp_path / f'large_{index}.png'
        path.write_bytes(png)
        candidate_id = f'request_01_image_{index + 1:02d}'
        candidate = dict(candidate_id=candidate_id, request_id='request_01', task_id='task', req_key='model',
                         path=str(path), bytes=len(png), sha256=digest(png), width=900, height=600, format='png')
        batch['scenes'][0]['candidates'].append(candidate)
        media['images'].append(dict(kind='original', scene_id='scene_0001', candidate_id=candidate_id,
                                   source_sha256=digest(png), path=str(path), bytes=len(png), sha256=digest(png),
                                   width=900, height=600))
    rows = build(batch, media)
    assert len(rows) == 2
    assert len(rows[0]['attachment_bindings']) < 8  # Encoded-size limit forces split before count limit.
    assert all(len(row['mime_bytes']) <= 15 * 1024 * 1024 for row in rows)
    bindings = [b for row in rows for b in row['attachment_bindings']]
    assert len(bindings) == len({b['candidate_id'] for b in bindings}) == 10
    for row in rows:
        parsed = BytesParser(policy=policy.default).parsebytes(row['mime_bytes'])
        assert len(list(parsed.iter_attachments())) == len(row['attachment_bindings'])


def test_config_email_only_for_new_strategy_and_frozen_raw(runtime_run, tmp_path):
    from video_ai.config import ConfigError, load_config
    from video_ai.runtime.manifest import thaw
    from unit.test_jimeng_config import configured
    old = runtime_run[1]
    loaded = configured(old, tmp_path, selection_email={'smtp_host': 'smtp.example.com'})
    assert parse_selection_email(loaded.raw['selection_email']).smtp_host == 'smtp.example.com'
    assert 'selection_email' not in loaded.__dataclass_fields__
    raw = thaw(old.raw)
    raw['selection_email'] = {}
    with pytest.raises(ConfigError, match='requires paragraph_jimeng_v1'):
        load_config(old.config_file, raw=raw, voice=old.voice)
    with pytest.raises(ConfigError, match='unknown field'):
        configured(old, tmp_path, selection_email={'password': 'do-not-store'})


def test_baseline_inline_cids_and_all_purposes_are_preserved(email_batch):
    batch, media = email_batch
    baseline = dict(media['images'][0], scene_id='scene_0000')
    media['images'] += [baseline, dict(baseline, kind='preview')]
    batch['baseline_bindings'] = [
        dict(kind='subject', id='hero', scene_id='scene_0000', candidate_id=baseline['candidate_id'], sha256=baseline['sha256']),
        dict(kind='style', id='oil_paint', scene_id='scene_0000', candidate_id=baseline['candidate_id'], sha256=baseline['sha256']),
    ]
    media['contact_sheets'] = [dict(path=baseline['path'], bytes=baseline['bytes'], sha256=baseline['sha256'],
                                   width=1, height=1, sources=[dict(scene_id='scene_0001', candidate_id=baseline['candidate_id'], sha256=baseline['sha256'])])]
    result = build(batch, media)
    assert result == build(batch, media)
    parsed = BytesParser(policy=policy.default).parsebytes(result[0]['mime_bytes'])
    plain = parsed.get_body(preferencelist=('plain',)).get_content()
    assert 'oil_paint' in plain and 'hero' in plain
    html_body = parsed.get_body(preferencelist=('html',)).get_content()
    inlines = [part for part in parsed.walk() if part.get_content_disposition() == 'inline']
    assert len(inlines) == 2  # One shared baseline image and one contact sheet.
    for part in inlines:
        assert part['Content-ID'].strip('<>') in html_body
    assert len(list(parsed.iter_attachments())) == 2  # Baselines never acquire candidate ownership.


def test_baseline_preview_wrong_source_is_rejected(email_batch):
    batch, media = email_batch
    baseline = dict(media['images'][0], scene_id='scene_0000')
    media['images'] += [baseline, dict(baseline, kind='preview', source_sha256='0' * 64)]
    batch['baseline_bindings'] = [dict(kind='style', id='style', scene_id='scene_0000',
                                     candidate_id=baseline['candidate_id'], sha256=baseline['sha256'])]
    with pytest.raises(EmailPreconditionError):
        build(batch, media)


def test_contact_sheet_wrong_source_is_rejected(email_batch):
    batch, media = email_batch
    image = media['images'][0]
    media['contact_sheets'] = [dict(path=image['path'], bytes=image['bytes'], sha256=image['sha256'],
                                   width=1, height=1, sources=[dict(scene_id='scene_0001', candidate_id=image['candidate_id'], sha256='0' * 64)])]
    with pytest.raises(EmailPreconditionError):
        build(batch, media)


def test_baseline_only_contact_page_is_not_dropped(email_batch):
    batch, media = email_batch
    image = dict(media['images'][0], scene_id='scene_0000')
    media['images'] += [image, dict(image, kind='preview')]
    batch['baseline_bindings'] = [dict(kind='style', id='style', scene_id=image['scene_id'],
                                     candidate_id=image['candidate_id'], sha256=image['sha256'])]
    media['contact_sheets'] = [dict(path=image['path'], bytes=image['bytes'], sha256=image['sha256'],
                                   width=1, height=1, sources=[dict(scene_id=image['scene_id'], candidate_id=image['candidate_id'], sha256=image['sha256'])])]
    row = build(batch, media)[0]
    parsed = BytesParser(policy=policy.default).parsebytes(row['mime_bytes'])
    assert '整组对照图' in parsed.get_body(preferencelist=('html',)).get_content()


def test_current_baseline_roles_are_explicit_without_fabricated_choice(email_batch):
    batch, media = email_batch
    rows = build(batch, media, baseline_roles=[dict(kind='entity', id='entity_0001', scene_id='scene_0001'),
                                               dict(kind='scene_group', id='group_0001', scene_id='scene_0001')])
    parsed = BytesParser(policy=policy.default).parsebytes(rows[0]['mime_bytes'])
    for content_type in ('plain', 'html'):
        body = parsed.get_body(preferencelist=(content_type,)).get_content()
        assert 'entity_0001' in body and 'group_0001' in body
        assert 'entity' in body and 'scene_group' in body and '本批待选基准用途' in body
    assert batch['baseline_bindings'] == []


@pytest.mark.parametrize('extension,mime_type', [('webp','webp'), ('bmp','bmp'), ('tiff','tiff'),
                                                ('gif','gif'), ('ppm','x-portable-pixmap'), ('jp2','jp2'), ('tga','x-tga')])
def test_real_still_original_is_attached_with_its_mime_type(email_batch, runtime_run, tmp_path, extension, mime_type):
    batch, media = email_batch
    path = tmp_path/('actual.' + extension)
    completed = subprocess.run([str(runtime_run[1].tools['ffmpeg']), '-nostdin', '-v', 'error', '-f', 'lavfi',
                                '-i', 'color=red:s=16x16', '-frames:v', '1', str(path)],
                               capture_output=True, timeout=30, check=False)
    assert completed.returncode == 0, completed.stderr.decode('utf-8', errors='replace')
    data = path.read_bytes()
    candidate = batch['scenes'][0]['candidates'][0]
    candidate.update(path=str(path), bytes=len(data), sha256=digest(data), width=16, height=16, format=extension)
    media['images'][0].update(path=str(path), bytes=len(data), sha256=digest(data), source_sha256=digest(data), width=16, height=16)
    row = build(batch, media)[0]
    parsed = BytesParser(policy=policy.default).parsebytes(row['mime_bytes'])
    attached = next(p for p in parsed.iter_attachments() if p.get_content_type() == 'image/' + mime_type)
    assert attached.get_payload(decode=True) == data


class LocalTransport:
    """Injected local transport; there is no socket or external delivery."""
    def __init__(self, events, *, failure=None, delay=0):
        self.events, self.failure, self.delay = events, failure, delay
        self.sock = None
    def ehlo(self):
        self.events.append('ehlo')
        return 250, b'ok'
    def login(self, sender, password):
        self.events.append('login')
        if self.failure == 'login':
            raise RuntimeError('AUTH secret-password')
        return 235, b'ok'
    def mail(self, sender):
        self.events.append('mail')
        return 250, b'ok'
    def rcpt(self, recipient):
        self.events.append('rcpt')
        return (550 if self.failure == 'rcpt' else 250), b'AUTH secret-password'
    def data(self, data):
        self.events.append('data')
        time.sleep(self.delay)
        if self.failure == 'data':
            raise RuntimeError('AUTH secret-password')
        if self.failure == 'data_exception':
            raise smtplib.SMTPDataError(552, b'AUTH secret-password')
        return (550 if self.failure == 'reject' else 250), b'AUTH secret-password'
    def close(self):
        self.events.append('close')


def smtp(settings=None, *, failure=None, delay=0, connection_delay=0):
    events, contexts = [], []
    def factory(host, port, *, timeout, context):
        contexts.append(context)
        time.sleep(connection_delay)
        return LocalTransport(events, failure=failure, delay=delay)
    return SmtpSender(settings or parse_selection_email(None), smtp_factory=factory), events, contexts


def test_smtp_verified_ssl_and_callback_on_caller_after_rcpt(monkeypatch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    sender, events, contexts = smtp()
    caller = threading.get_ident()
    def before():
        assert threading.get_ident() == caller
        assert events[-1] == 'rcpt'
        events.append('intent')
    assert sender.send(b'mime', before_data=before) == {'smtp_code': 250}
    assert events == ['ehlo', 'login', 'mail', 'rcpt', 'intent', 'data', 'close']
    assert contexts[0].check_hostname and contexts[0].verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize('failure,expected', [('login', EmailPreconditionError), ('rcpt', EmailPreconditionError),
                                             ('data', EmailDeliveryUnknown), ('reject', EmailRejected)])
def test_smtp_safe_failure_classification(monkeypatch, failure, expected):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    sender, events, _ = smtp(failure=failure)
    with pytest.raises(expected) as captured:
        sender.send(b'mime', before_data=lambda: events.append('intent'))
    assert 'secret-password' not in str(captured.value)
    assert 'AUTH' not in str(captured.value)
    assert captured.value.__cause__ is None
    if failure in ('login', 'rcpt'):
        assert 'intent' not in events and 'data' not in events


def test_missing_password_does_not_connect(monkeypatch):
    monkeypatch.delenv('VIDEO_AI_SMTP_AUTH_CODE', raising=False)
    sender, events, _ = smtp()
    with pytest.raises(EmailPreconditionError):
        sender.send(b'mime', before_data=lambda: events.append('intent'))
    assert events == []


def test_total_deadline_includes_late_connection_and_never_calls_callback(monkeypatch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    settings = replace(parse_selection_email(None), timeout_seconds=.03)
    sender, events, _ = smtp(settings, connection_delay=.10)
    start = time.monotonic()
    with pytest.raises(EmailPreconditionError):
        sender.send(b'mime', before_data=lambda: events.append('intent'))
    assert time.monotonic() - start < .09
    time.sleep(.12)
    assert 'mail' not in events and 'intent' not in events and 'data' not in events
    assert events == ['close']


def test_data_timeout_unknown_and_no_late_success(monkeypatch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    settings = replace(parse_selection_email(None), timeout_seconds=.03)
    sender, events, _ = smtp(settings, delay=.10)
    with pytest.raises(EmailDeliveryUnknown):
        sender.send(b'mime', before_data=lambda: events.append('intent'))
    time.sleep(.12)
    assert events.count('data') == 1 and events.count('intent') == 1
    assert 'close' in events


def test_timeout_cancels_paused_data_transition_before_caller_returns(monkeypatch):
    from video_ai.adapters import selection_email
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    paused, release = threading.Event(), threading.Event()
    def boundary(point):
        if point == 'before_data_transition':
            paused.set()
            release.wait(1)
    monkeypatch.setattr(selection_email, '_smtp_boundary', boundary)
    sender, events, _ = smtp(replace(parse_selection_email(None), timeout_seconds=.05))
    try:
        with pytest.raises(EmailPreconditionError):
            sender.send(b'mime', before_data=lambda: events.append('intent'))
        assert paused.is_set()
    finally:
        release.set()
    time.sleep(.05)
    assert 'data' not in events
    assert events.count('intent') == 1


def test_ownership_rechecked_after_intent_and_before_data(monkeypatch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    lost, events = threading.Event(), []
    checks = []
    def owned():
        checks.append(threading.get_ident())
        if lost.is_set():
            raise RuntimeError('AUTH secret-password lost ownership')
    def factory(host, port, *, timeout, context):
        return LocalTransport(events)
    sender = SmtpSender(parse_selection_email(None), smtp_factory=factory, ownership_check=owned)
    with pytest.raises(EmailPreconditionError) as error:
        sender.send(b'mime', before_data=lost.set)
    assert len(checks) >= 2 and 'mail' in events
    assert 'data' not in events and 'secret-password' not in str(error.value)


def test_callback_failure_prevents_data(monkeypatch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    sender, events, _ = smtp()
    def lost_lock():
        raise RuntimeError('lock lost AUTH secret-password')
    with pytest.raises(EmailPreconditionError) as error:
        sender.send(b'mime', before_data=lost_lock)
    assert 'data' not in events
    assert 'secret-password' not in str(error.value)


def test_explicit_data_exception_is_rejected(monkeypatch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    sender, _, _ = smtp(failure='data_exception')
    with pytest.raises(EmailRejected) as error:
        sender.send(b'mime', before_data=lambda: None)
    assert error.value.smtp_code == 552
    assert 'secret-password' not in str(error.value)


def test_caller_interrupt_is_preserved_and_prevents_data(monkeypatch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    sender, events, _ = smtp()
    def interrupt():
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        sender.send(b'mime', before_data=interrupt)
    assert 'data' not in events


def test_local_smtp_receives_actual_mime_data(monkeypatch, email_batch):
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'test-local-password')
    received = []
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b'220 localhost local-only test\r\n')
            while line := self.rfile.readline():
                command = line.split(b' ', 1)[0].strip().upper()
                if command == b'EHLO':
                    self.wfile.write(b'250-localhost\r\n250 AUTH PLAIN\r\n')
                elif command == b'AUTH':
                    self.wfile.write(b'235 authenticated\r\n')
                elif command in (b'MAIL', b'RCPT'):
                    self.wfile.write(b'250 accepted\r\n')
                elif command == b'DATA':
                    self.wfile.write(b'354 send local MIME\r\n')
                    rows = []
                    while (row := self.rfile.readline()) != b'.\r\n':
                        if not row:
                            return
                        rows.append(row[1:] if row.startswith(b'..') else row)
                    received.append(b''.join(rows))
                    self.wfile.write(b'250 accepted local MIME\r\n')
                else:
                    self.wfile.write(b'500 unexpected\r\n')
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def local_factory(host, port, *, timeout, context):
            assert host == 'smtp.qq.com'  # Factory explicitly substitutes localhost, never DNSes this host.
            return smtplib.SMTP('127.0.0.1', server.server_address[1], timeout=timeout)
        row = build(*email_batch)[0]
        sender = SmtpSender(parse_selection_email(None), smtp_factory=local_factory)
        assert sender.send(row['mime_bytes'], before_data=lambda: None) == {'smtp_code': 250}
        assert received == [row['mime_bytes']]
        assert len(list(BytesParser(policy=policy.default).parsebytes(received[0]).iter_attachments())) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
