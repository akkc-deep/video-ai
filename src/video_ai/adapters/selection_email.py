"""Deterministic local MIME building and bounded, explicitly authorized SMTP DATA."""
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime
import hashlib
import html
import json
import os
from pathlib import Path
import queue
import re
import smtplib
import ssl
import threading
import time

from ..selection_config import SelectionEmailSettings, parse_selection_email


class EmailPreconditionError(ValueError):
    """No DATA was started. Messages contain only a fixed safe category."""


class EmailRejected(ValueError):
    """The server explicitly rejected DATA."""
    def __init__(self, message='SMTP DATA rejected', *, smtp_code=None):
        super().__init__(message)
        self.smtp_code = smtp_code


class EmailDeliveryUnknown(ValueError):
    """DATA began, but acceptance is unconfirmed. Never retry automatically."""


def _smtp_boundary(point):
    """Thread transition boundary for deterministic local fault injection."""


def _date(created_at):
    try:
        value = (datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                 if isinstance(created_at, str) else created_at)
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError
        return format_datetime(value.astimezone(timezone.utc))
    except (TypeError, ValueError, OverflowError):
        raise EmailPreconditionError('invalid mail creation time') from None


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise EmailPreconditionError('invalid mail identity')
    return value


def _read_media(row, cache):
    path = str(row['path'])
    if path not in cache:
        try:
            data = Path(path).read_bytes()
        except OSError:
            raise EmailPreconditionError('mail media unavailable') from None
        cache[path] = data
    data = cache[path]
    if (type(row['bytes']) is not int or len(data) != row['bytes']
            or hashlib.sha256(data).hexdigest() != row['sha256']):
        raise EmailPreconditionError('mail media identity mismatch')
    return data


def _subtype(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8'):
        return 'jpeg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'webp'
    if data.startswith(b'BM'):
        return 'bmp'
    if data.startswith((b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+')):
        return 'tiff'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    if data.startswith(b'\x00\x00\x00\x0cjP  \r\n\x87\n'):
        return 'jp2'
    if data.startswith(b'\xff\x4f\xff\x51'):
        return 'j2c'
    if data[:2] in (b'P3', b'P6') and data[2:3] in b' \t\r\n':
        return 'x-portable-pixmap'
    if data[:2] in (b'P2', b'P5') and data[2:3] in b' \t\r\n':
        return 'x-portable-graymap'
    if data.endswith(b'TRUEVISION-XFILE.\x00'):
        return 'x-tga'
    raise EmailPreconditionError('unsupported still-image mail media')


def _purposes(batch, scene, baseline_roles):
    result = []
    for role in baseline_roles:
        if role['scene_id'] == scene['scene_id']:
            result.append('本批待选基准用途: ' + json.dumps(role, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    for binding in scene.get('reference_bindings', ()):
        result.append(json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    for binding in batch.get('baseline_bindings', ()):
        # Keep every kind/id purpose even when several purposes share one image.
        result.append(json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    return result or ['当前批基准/候选选择；以已提交的 visual-bible 基准关系为准。']


def _encode(batch, media, entries, *, part, total, attempt, date, sender, recipient, cache, baseline_roles):
    identity = f'{batch["run_id"]}.{batch["batch_id"]}.part_{part:04d}.attempt_{attempt:04d}'
    message_id = f'<{identity}@video-ai.local>'
    message = EmailMessage(policy=policy.SMTP)
    message['From'], message['To'], message['Date'] = sender, recipient, date
    message['Message-ID'] = message_id
    message['Subject'] = f'候选图选择 {batch["run_id"]} {batch["batch_id"]} {part}/{total}'
    text = [f'Run: {batch["run_id"]}', f'Batch: {batch["batch_id"]}', f'页码: {part}/{total}',
            '请检查所有分页中的图片，逐 scene 选择一张；整组主体一致性和风格一致性需要实际看图核实。',
            '仅复制候选编号不代表一致性通过；observation 不应预填 passed。',
            f'选图骨架: production/image-selection/{batch["batch_id"]}/selection-template.json',
            '复制所选候选下方 JSON 行到 selections 数组；草稿 intent=draft，完整接受时改 intent=accept。',
            '保留骨架身份及基准字段；observation 可为 null，整组实际观察另行填写。']
    for scene in batch['scenes']:
        selected = [entry for entry in entries if entry['scene']['scene_id'] == scene['scene_id']]
        if not selected:
            continue
        text += ['', f'Scene: {scene["scene_id"]}', f'摘要: {scene["summary"]}',
                 '完整原文:', scene['original_text'], '基准用途:'] + _purposes(batch, scene, baseline_roles)
        for entry in selected:
            candidate, image = entry['candidate'], entry['attachment']
            text += [f'{scene["scene_id"]}={candidate["candidate_id"]}',
                     json.dumps(dict(scene_id=scene['scene_id'], candidate_id=candidate['candidate_id'],
                                     sha256=candidate['sha256']), ensure_ascii=False, separators=(',', ':')),
                     f'原图 SHA256: {candidate["sha256"]}',
                     f'附件: {"原图" if image["kind"] == "original" else "邮件副本"}; '
                     f'来源原图 SHA256: {image["source_sha256"]}; 附件 SHA256: {image["sha256"]}']
    plain = '\n'.join(text) + '\n'
    message.set_content(plain)
    html_body = '<html><body><pre>' + html.escape(plain) + '</pre>'
    inline = []
    keys = {(entry['scene']['scene_id'], entry['candidate']['candidate_id']) for entry in entries}
    # Baselines may be repeated for comparison; candidate attachments are never repeated.
    baseline_keys = {(b['scene_id'], b['candidate_id']) for b in batch.get('baseline_bindings', ())}
    for scene_id, candidate_id in sorted(keys | baseline_keys):
        previews = [r for r in media['images'] if r['kind'] == 'preview'
                    and (r['scene_id'], r['candidate_id']) == (scene_id, candidate_id)]
        if previews:
            own = next((e for e in entries if (e['scene']['scene_id'], e['candidate']['candidate_id'])
                        == (scene_id, candidate_id)), None)
            chosen = own['attachment'] if own and own['attachment']['kind'] == 'preview' else previews[0]
            inline.append((chosen, f'{scene_id}={candidate_id}'))
    for sheet in media.get('contact_sheets', ()):
        if any((s['scene_id'], s['candidate_id']) in keys | baseline_keys for s in sheet['sources']):
            inline.append((sheet, '整组对照图'))
    for index, (row, label) in enumerate(inline, 1):
        cid = f'{identity}.image_{index:04d}@video-ai.local'
        html_body += f'<p>{html.escape(label)}</p><img src="cid:{cid}" alt="{html.escape(label, quote=True)}">'
    message.add_alternative(html_body + '</body></html>', subtype='html')
    html_part = message.get_body(preferencelist=('html',))
    for index, (row, _) in enumerate(inline, 1):
        data = _read_media(row, cache)
        html_part.add_related(data, maintype='image', subtype=_subtype(data),
                              cid=f'<{identity}.image_{index:04d}@video-ai.local>',
                              disposition='inline')
    bindings = []
    for entry in entries:
        candidate, row = entry['candidate'], entry['attachment']
        data = _read_media(row, cache)
        subtype = _subtype(data)
        scene_id = entry['scene']['scene_id']
        message.add_attachment(data, maintype='image', subtype=subtype,
                               filename=f'{scene_id}={candidate["candidate_id"]}.{subtype}')
        bindings.append(dict(scene_id=scene_id, candidate_id=candidate['candidate_id'],
                             original_sha256=candidate['sha256'], attachment_sha256=row['sha256']))
    for index, item in enumerate(message.walk()):
        if item.is_multipart():
            token = hashlib.sha256(identity.encode('ascii')).hexdigest()[:32]
            item.set_boundary(f'video-ai.{token}.boundary_{index:04d}')
    return dict(part=part, total=total, message_id=message_id,
                mime_bytes=message.as_bytes(), attachment_bindings=bindings)


def build_messages(batch, media, *, created_at, sender, recipient, max_mime_bytes, attempt=1, baseline_roles=None) -> list[dict]:
    """Greedily pack measured complete MIME, preserving one attachment per candidate."""
    parse_selection_email(dict(sender=sender, recipient=recipient, max_mime_bytes=max_mime_bytes))
    _identifier(batch['run_id'])
    _identifier(batch['batch_id'])
    if type(attempt) is not int or attempt <= 0:
        raise EmailPreconditionError('invalid mail attempt')
    date, cache, entries = _date(created_at), {}, []
    baseline_roles = () if baseline_roles is None else baseline_roles
    if not isinstance(baseline_roles, (list, tuple)):
        raise EmailPreconditionError('invalid baseline roles')
    for role in baseline_roles:
        if (not isinstance(role, dict) or set(role) != {'kind', 'id', 'scene_id'}
                or any(not isinstance(role[key], str) or not role[key].strip() for key in role)):
            raise EmailPreconditionError('invalid baseline role')
    seen = set()
    for scene in batch['scenes']:
        _identifier(scene['scene_id'])
        for candidate in scene['candidates']:
            _identifier(candidate['candidate_id'])
            key = (scene['scene_id'], candidate['candidate_id'])
            if key in seen:
                raise EmailPreconditionError('duplicate mail candidate')
            seen.add(key)
            originals = [r for r in media['images'] if r['kind'] == 'original'
                         and (r['scene_id'], r['candidate_id']) == key]
            previews = sorted((r for r in media['images'] if r['kind'] == 'preview'
                               and (r['scene_id'], r['candidate_id']) == key),
                              key=lambda row: (-row['width'], -row['height']))
            if len(originals) != 1 or originals[0]['sha256'] != candidate['sha256']:
                raise EmailPreconditionError('candidate original identity mismatch')
            alternatives = originals + previews
            for image in alternatives:
                if image['source_sha256'] != candidate['sha256']:
                    raise EmailPreconditionError('candidate preview source mismatch')
                _read_media(image, cache)
            entries.append(dict(scene=scene, candidate=candidate, alternatives=alternatives,
                                attachment=originals[0]))
    if not entries:
        raise EmailPreconditionError('empty mail batch')
    source_hashes = {(e['scene']['scene_id'], e['candidate']['candidate_id']): e['candidate']['sha256']
                     for e in entries}
    for baseline in batch.get('baseline_bindings', ()):
        key = (baseline['scene_id'], baseline['candidate_id'])
        if key in source_hashes and source_hashes[key] != baseline['sha256']:
            raise EmailPreconditionError('baseline source identity mismatch')
        source_hashes[key] = baseline['sha256']
        images = [r for r in media['images'] if (r['scene_id'], r['candidate_id']) == key]
        originals = [r for r in images if r['kind'] == 'original']
        if len(originals) != 1 or originals[0]['sha256'] != baseline['sha256']:
            raise EmailPreconditionError('baseline original identity mismatch')
        if not any(r['kind'] == 'preview' for r in images):
            raise EmailPreconditionError('baseline preview unavailable')
        for image in images:
            if image['source_sha256'] != baseline['sha256']:
                raise EmailPreconditionError('baseline preview source mismatch')
            _read_media(image, cache)
    for sheet in media.get('contact_sheets', ()):
        seen_sources = set()
        if not 1 <= len(sheet['sources']) <= 8:
            raise EmailPreconditionError('invalid contact sheet source count')
        for source in sheet['sources']:
            key = (source['scene_id'], source['candidate_id'])
            if key in seen_sources or source_hashes.get(key) != source['sha256']:
                raise EmailPreconditionError('contact sheet source identity mismatch')
            seen_sources.add(key)
        _read_media(sheet, cache)

    def encode(group, part, total):
        return _encode(batch, media, group, part=part, total=total, attempt=attempt, date=date,
                       sender=sender, recipient=recipient, cache=cache, baseline_roles=baseline_roles)

    def fit_single(entry, part, total):
        for alternative in entry['alternatives']:
            entry['attachment'] = alternative
            if len(encode([entry], part, total)['mime_bytes']) <= max_mime_bytes:
                return
        raise EmailPreconditionError('minimum candidate MIME exceeds size limit')

    groups = []
    for entry in entries:
        fit_single(entry, len(groups) + 1, 1)
        if groups and len(groups[-1]) < 8 and len(encode(groups[-1] + [entry], len(groups), 1)['mime_bytes']) <= max_mime_bytes:
            groups[-1].append(entry)
        else:
            groups.append([entry])
    # Total-page headers can grow; remeasure actual final headers after every split.
    while True:
        total, revised, changed = len(groups), [], False
        for index, group in enumerate(groups, 1):
            if len(encode(group, index, total)['mime_bytes']) <= max_mime_bytes:
                revised.append(group)
            elif len(group) > 1:
                revised.extend([group[:-1], group[-1:]])
                changed = True
            else:
                fit_single(group[0], index, total)
                revised.append(group)
        groups = revised
        if not changed:
            result = [encode(group, index, len(groups)) for index, group in enumerate(groups, 1)]
            if any(len(row['mime_bytes']) > max_mime_bytes for row in result):
                raise EmailPreconditionError('candidate MIME exceeds size limit')
            return result


class SmtpSender:
    """Only the caller runs before_data; late DNS/SMTP workers cannot authorize DATA."""
    def __init__(self, settings, *, smtp_factory=None, ownership_check=None):
        self.settings = settings if isinstance(settings, SelectionEmailSettings) else parse_selection_email(settings)
        self.smtp_factory = smtp_factory or smtplib.SMTP_SSL
        self.ownership_check = ownership_check or (lambda: None)

    def send(self, mime_bytes, *, before_data) -> dict:
        settings = self.settings
        password = os.environ.get(settings.smtp_password_env)
        if not password or '\r' in password or '\n' in password:
            raise EmailPreconditionError('SMTP credential unavailable')
        deadline = time.monotonic() + settings.timeout_seconds
        responses = queue.Queue()
        permit, cancelled = threading.Event(), threading.Event()
        transition_lock = threading.Lock()
        phase = 'preparing'
        connection = []

        def remaining():
            result = deadline - time.monotonic()
            if cancelled.is_set() or result <= 0:
                raise TimeoutError
            return result

        def socket_timeout(client):
            timeout = remaining()
            if getattr(client, 'sock', None) is not None:
                client.sock.settimeout(timeout)

        def cancel():
            nonlocal phase
            # A caller returning a precondition error has irrevocably cancelled
            # DATA. The worker's sending transition uses this same mutex.
            with transition_lock:
                sending = phase == 'sending'
                if not sending:
                    phase = 'cancelled'
                cancelled.set()
            permit.set()
            return sending

        def sending():
            with transition_lock:
                return phase == 'sending'

        def worker():
            nonlocal phase
            client = None
            outcome = ('precondition', None)
            try:
                client = self.smtp_factory(settings.smtp_host, settings.smtp_port,
                                           timeout=remaining(), context=ssl.create_default_context())
                connection.append(client)
                socket_timeout(client)
                code, _ = client.ehlo()
                if not 200 <= code < 300:
                    raise ValueError
                socket_timeout(client)
                client.login(settings.sender, password)
                socket_timeout(client)  # Late connection/authentication cannot start MAIL.
                self.ownership_check()
                remaining()
                code, _ = client.mail(settings.sender)
                if not 200 <= code < 300:
                    raise ValueError
                socket_timeout(client)
                code, _ = client.rcpt(settings.recipient)
                if not 200 <= code < 300:
                    raise ValueError
                remaining()
                responses.put(('ready', None))
                if not permit.wait(remaining()):
                    raise TimeoutError
                socket_timeout(client)
                _smtp_boundary('before_data_transition')
                with transition_lock:
                    self.ownership_check()
                    remaining()
                    if phase != 'authorized':
                        raise TimeoutError
                    phase = 'sending'
                code, _ = client.data(mime_bytes)
                remaining()
                if type(code) is not int:
                    raise ValueError
                if 200 <= code < 300:
                    outcome = ('accepted', code)
                elif 400 <= code < 600:
                    outcome = ('rejected', code)
                else:
                    outcome = ('unknown', None)
            except smtplib.SMTPDataError as error:
                if (sending() and not cancelled.is_set() and time.monotonic() < deadline
                        and type(error.smtp_code) is int and 400 <= error.smtp_code < 600):
                    outcome = ('rejected', error.smtp_code)
                else:
                    outcome = ('unknown' if sending() else 'precondition', None)
            except BaseException:
                outcome = ('unknown' if sending() else 'precondition', None)
            finally:
                if client is not None:
                    try:
                        client.close()
                    except BaseException:
                        pass
                responses.put(outcome)

        thread = threading.Thread(target=worker, name='video-ai-smtp', daemon=True)
        thread.start()
        try:
            while True:
                try:
                    stage, code = responses.get(timeout=remaining())
                except (queue.Empty, TimeoutError):
                    if cancel():
                        raise EmailDeliveryUnknown('SMTP DATA deadline exceeded') from None
                    raise EmailPreconditionError('SMTP preparation deadline exceeded') from None
                if stage == 'ready':
                    try:
                        remaining()
                        before_data()
                        with transition_lock:
                            remaining()
                            phase = 'authorized'
                    except Exception:
                        raise EmailPreconditionError('SMTP intent authorization failed') from None
                    permit.set()
                elif stage == 'accepted':
                    return {'smtp_code': code}
                elif stage == 'rejected':
                    raise EmailRejected(smtp_code=code)
                elif stage == 'unknown':
                    raise EmailDeliveryUnknown('SMTP DATA outcome unknown')
                else:
                    raise EmailPreconditionError('SMTP preparation failed')
        finally:
            cancel()
            # Closing a normal socket interrupts outstanding I/O; late DNS clients close in worker.
            for client in connection:
                sock = getattr(client, 'sock', None)
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
