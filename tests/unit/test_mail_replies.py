"""Read-only mailbox behavior using local IMAP fixtures; no network or secrets."""
from email.message import EmailMessage
from email import policy
from email.parser import BytesParser
import imaplib
import re
import ssl

import pytest

from video_ai import mail_replies


def reply(body='确认提交', *, sender='318575094@qq.com', parent='<pending@example>', html=False):
    message = EmailMessage()
    message['From'] = sender
    message['Message-ID'] = '<reply@example>'
    message['In-Reply-To'] = parent
    message.set_content(body, subtype='html' if html else 'plain')
    return message


class FakeImap:
    def __init__(self, messages=None, *, fail=None, validity=b'9042'):
        self.messages = messages or {}
        self.fail = fail
        self.validity = validity
        self.operations = []

    def login(self, account, password):
        assert account == '318575094@qq.com'
        assert password == 'local-test-password'
        if self.fail == 'login':
            raise imaplib.IMAP4.error('local-test-password sensitive server text')
        return 'OK', [b'authenticated']

    def select(self, mailbox, readonly=False):
        assert mailbox == 'INBOX'
        assert readonly is True, 'mailbox must be examined without writable selection'
        return ('NO' if self.fail == 'select' else 'OK'), [b'3']

    def response(self, name):
        assert name == 'UIDVALIDITY'
        return name, [self.validity]

    def uid(self, command, *args):
        self.operations.append((command, args))
        if command == 'SEARCH':
            if self.fail == 'search':
                return 'NO', [b'sensitive server text']
            return 'OK', [b' '.join(self.messages)]
        assert command == 'FETCH', 'UID STORE, COPY and other mutation commands are forbidden'
        assert 'BODY.PEEK[]' in args[1]
        if self.fail == 'fetch':
            raise OSError('sensitive server text')
        raw = self.messages[args[0]]
        return 'OK', [(b'1 (BODY[] {999}', raw), b')']

    def logout(self):
        self.operations.append(('LOGOUT', ()))
        return 'BYE', [b'logout']


@pytest.fixture
def make_reader(monkeypatch):
    def credentials(*names):
        assert names == ('VIDEO_AI_SMTP_AUTH_CODE',)
        return ('local-test-password',)
    monkeypatch.setattr(mail_replies, 'read_credentials', credentials)

    def make(fake):
        def factory(host, port, *, ssl_context, timeout):
            assert host == 'imap.qq.com'
            assert port == 993
            assert timeout == 30
            assert ssl_context.verify_mode == ssl.CERT_REQUIRED
            assert ssl_context.check_hostname
            return fake
        return mail_replies.ImapReplyReader(imap_factory=factory)
    return make


def test_matching_reply_uses_read_only_peek_and_uidvalidity_identity(make_reader):
    fake = FakeImap({b'73': reply('scene_0004=request_04_image_02\n确认提交').as_bytes()})
    result = make_reader(fake).poll(['<pending@example>'])
    assert result == [mail_replies.MailReply('9042:73', '<reply@example>', '318575094@qq.com',
                                           'scene_0004=request_04_image_02\n确认提交')]
    searches = [args for command, args in fake.operations if command == 'SEARCH']
    assert any('In-Reply-To' in args for args in searches)
    assert any('References' in args for args in searches)
    assert len([item for item in fake.operations if item[0] == 'FETCH']) == 1
    assert fake.operations[-1][0] == 'LOGOUT'


def test_only_approved_sender_and_exact_pending_thread_are_returned(make_reader):
    reference = reply(parent='<different@example>')
    reference['References'] = '<older@example> <pending@example>'
    messages = {
        b'1': reply(sender='attacker@example').as_bytes(),
        b'2': reply(parent='<pending@example.evil>').as_bytes(),
        b'3': reply(parent='<old@example>').as_bytes(),
        b'4': reference.as_bytes(),
    }
    assert [item.key for item in make_reader(FakeImap(messages)).poll(['<pending@example>'])] == ['9042:4']


def test_empty_matches_and_empty_pending_ids_do_not_fail(make_reader):
    assert make_reader(FakeImap()).poll(['<pending@example>']) == []
    reader = mail_replies.ImapReplyReader(imap_factory=lambda *a, **kw: pytest.fail('must not connect'))
    assert reader.poll([]) == []


@pytest.mark.parametrize('failure,category', [
    ('login', 'authentication_failed'), ('select', 'mailbox_unavailable'),
    ('search', 'search_failed'), ('fetch', 'fetch_failed'),
])
def test_server_failures_expose_only_safe_categories(make_reader, failure, category):
    fake = FakeImap({b'1': reply().as_bytes()}, fail=failure)
    with pytest.raises(mail_replies.MailboxError) as caught:
        make_reader(fake).poll(['<pending@example>'])
    assert str(caught.value) == category
    assert fake.operations[-1][0] == 'LOGOUT'


def test_connection_failure_is_redacted(monkeypatch):
    monkeypatch.setattr(mail_replies, 'read_credentials', lambda *names: ('local-test-password',))
    def factory(*args, **kwargs):
        raise OSError('secret connection details')
    with pytest.raises(mail_replies.MailboxError, match='^connection_failed$'):
        mail_replies.ImapReplyReader(imap_factory=factory).poll(['<pending@example>'])


def test_missing_credentials_never_contacts_server(monkeypatch):
    monkeypatch.setattr(mail_replies, 'read_credentials', lambda *names: (None,))
    with pytest.raises(mail_replies.MailboxError, match='^credentials_unavailable$'):
        mail_replies.ImapReplyReader(imap_factory=lambda *a, **kw: pytest.fail('must not connect')).poll(['<x@y>'])


def test_uidvalidity_required_for_durable_identity(make_reader):
    with pytest.raises(mail_replies.MailboxError, match='^mailbox_identity_unavailable$'):
        make_reader(FakeImap(validity=None)).poll(['<pending@example>'])


@pytest.mark.parametrize('body,expected', [
    ('确认提交\n\n> scene_0004=request_04_image_02\n> 确认提交', '确认提交'),
    ('scene_0004=request_04_image_02\n确认提交\n\nOn Sun, Nov 29, User wrote:\n确认发布',
     'scene_0004=request_04_image_02\n确认提交'),
    ('确认提交\n\n在 2026年11月29日，Video AI 写道：\n确认发布', '确认提交'),
    ('确认提交\n------------------ 原始邮件 ------------------\n确认发布', '确认提交'),
    ('确认提交\nFrom: Video AI\nSent: Sunday\nTo: User\nSubject: review\n确认发布', '确认提交'),
    ('> 确认提交\n> scene_0004=request_04_image_02', ''),
    ('\n\nOn Sunday, Video AI wrote:\n确认提交', ''),
    ('确认提交\n\nOn Sunday, November 29,\nVideo AI <video@example> wrote:\n确认发布', '确认提交'),
    ('确认提交\n------------------ Original ------------------\n确认发布', '确认提交'),
])
def test_plain_reply_excludes_quoted_original(body, expected):
    assert mail_replies.extract_reply_text(reply(body)) == expected


@pytest.mark.parametrize('body,expected', [
    ('<div>确认提交</div><blockquote><p>确认发布</p></blockquote>', '确认提交'),
    ('<div>scene_0004=request_04_image_02<br>确认提交</div><div class="gmail_quote">确认发布</div>',
     'scene_0004=request_04_image_02\n确认提交'),
    ('<div>确认提交</div><div id="divRplyFwdMsg">发件人: Video AI</div><div>确认发布</div>', '确认提交'),
    ('<div>确认提交</div><div class="qqmail_quote">确认发布</div>', '确认提交'),
    ('<blockquote>确认提交</blockquote>', ''),
])
def test_html_reply_excludes_quoted_original(body, expected):
    assert mail_replies.extract_reply_text(reply(body, html=True)) == expected


def test_multipart_prefers_plain_body_and_ignores_attached_original():
    message = reply('确认提交\n> 确认发布')
    message.add_alternative('<p>HTML should not be concatenated</p>', subtype='html')
    message.add_attachment('确认发布'.encode(), maintype='text', subtype='plain', filename='original.txt')
    assert mail_replies.extract_reply_text(message) == '确认提交'


def test_read_count_is_bounded(make_reader):
    fake = FakeImap({str(i).encode(): reply().as_bytes() for i in range(1, 251)})
    result = make_reader(fake).poll(['<pending@example>'])
    assert 0 < len(result) <= 100
    assert len([item for item in fake.operations if item[0] == 'FETCH']) <= 100


def test_oversized_body_is_not_a_reply(make_reader):
    fake = FakeImap({b'1': reply('x' * 1_100_000).as_bytes()})
    assert make_reader(fake).poll(['<pending@example>']) == []


def test_new_replies_are_not_starved_by_a_long_matching_thread(make_reader):
    fake = FakeImap({str(i).encode(): reply().as_bytes() for i in range(1, 251)})
    result = make_reader(fake).poll(['<pending@example>'])
    assert '9042:250' in {item.key for item in result}


def test_credential_file_failure_is_redacted(monkeypatch):
    def fail(*names):
        raise ValueError('sensitive local file details')
    monkeypatch.setattr(mail_replies, 'read_credentials', fail)
    with pytest.raises(mail_replies.MailboxError, match='^credentials_unavailable$'):
        mail_replies.ImapReplyReader().poll(['<pending@example>'])


def test_malformed_search_reply_is_a_safe_failure(make_reader):
    class MalformedSearch(FakeImap):
        def uid(self, command, *args):
            return 'OK', None
    with pytest.raises(mail_replies.MailboxError, match='^search_failed$'):
        make_reader(MalformedSearch()).poll(['<pending@example>'])


LOGICAL_ID = '<logical.image_batch_0002@video-ai.local>'
REWRITTEN_ID = '<tencent_actual_notification@qq.com>'


def notification(*, field='Message-ID', custom_header=False):
    message = EmailMessage()
    message['From'] = 'Video AI <318575094@qq.com>'
    message['To'] = '318575094@qq.com'
    message['Message-ID'] = REWRITTEN_ID
    if custom_header:
        message['X-Video-AI-Request-ID'] = LOGICAL_ID
    message.set_content(f'{field}: {LOGICAL_ID}\nscene_0004=request_04_image_02\n确认提交')
    return message


class SearchingImap(FakeImap):
    """Apply HEADER/BODY searches and partial FETCH limits as a server would."""

    def uid(self, command, *args):
        self.operations.append((command, args))
        if command == 'SEARCH':
            found = []
            for uid, raw in self.messages.items():
                message = BytesParser(policy=policy.default).parsebytes(raw)
                if args[1] == 'HEADER':
                    content = '\n'.join(str(value) for value in message.get_all(args[2], []))
                    token = args[3].strip('"')
                else:
                    assert args[1] == 'BODY'
                    token = args[2].strip('"')
                    content = '\n'.join(str(part.get_content()) for part in message.walk()
                                        if part.get_content_type() in {'text/plain', 'text/html'})
                if token.lower() in content.lower():
                    found.append(uid)
            return 'OK', [b' '.join(found)]
        assert command == 'FETCH'
        assert 'BODY.PEEK[]' in args[1]
        limit = int(re.search(r'<0\.(\d+)>', args[1]).group(1))
        raw = self.messages[args[0]][:limit]
        return 'OK', [(b'1 (BODY[] {999}', raw), b')']


@pytest.mark.parametrize('field,custom_header', [
    ('Message-ID', False), ('Request-ID', False), ('Request-ID', True),
])
def test_tencent_rewritten_message_id_is_bound_through_verified_original(make_reader, field, custom_header):
    original = notification(field=field, custom_header=custom_header)
    original.add_attachment(b'x' * 2_200_000, maintype='application', subtype='octet-stream', filename='previews.bin')
    incoming = reply('scene_0004=request_04_image_02\n确认提交', parent=REWRITTEN_ID)
    fake = SearchingImap({b'2734': original.as_bytes(), b'2735': incoming.as_bytes()})
    result = make_reader(fake).poll([LOGICAL_ID])
    assert [item.key for item in result] == ['9042:2735']
    origin_fetches = [args for command, args in fake.operations if command == 'FETCH' and args[0] == b'2734']
    assert len(origin_fetches) == 1
    assert int(re.search(r'<0\.(\d+)>', origin_fetches[0][1]).group(1)) <= 65_536


@pytest.mark.parametrize('problem', ['sender', 'recipient', 'mismatch', 'quoted', 'reply_headers', 'references', 'quoted_html'])
def test_unverified_original_cannot_authorize_alias(make_reader, problem):
    original = notification()
    if problem == 'sender':
        original.replace_header('From', 'attacker@example')
    elif problem == 'recipient':
        original.replace_header('To', 'attacker@example')
    elif problem == 'mismatch':
        original.set_content(f'Message-ID: <other@video-ai.local>\nDiscussing {LOGICAL_ID}')
    elif problem == 'quoted':
        original.set_content(f'> Message-ID: {LOGICAL_ID}\n> 确认提交')
    elif problem == 'quoted_html':
        original.set_content(f'<div>我的回复</div><blockquote>Message-ID: {LOGICAL_ID}</blockquote>', subtype='html')
    elif problem == 'references':
        original['References'] = '<other@example>'
    else:
        original['In-Reply-To'] = '<other@example>'
    fake = SearchingImap({b'2734': original.as_bytes(), b'2735': reply(parent=REWRITTEN_ID).as_bytes()})
    assert make_reader(fake).poll([LOGICAL_ID]) == []


def test_verified_alias_cache_avoids_origin_scan_and_resets_with_uidvalidity(make_reader):
    fake = SearchingImap({b'2734': notification().as_bytes(), b'2735': reply(parent=REWRITTEN_ID).as_bytes()})
    reader = make_reader(fake)
    assert len(reader.poll([LOGICAL_ID])) == 1
    fake.operations.clear()
    assert len(reader.poll([LOGICAL_ID])) == 1
    assert all(not (command == 'SEARCH' and ('BODY' in args or 'X-Video-AI-Request-ID' in args))
               for command, args in fake.operations)
    assert all(not (command == 'FETCH' and args[0] == b'2734') for command, args in fake.operations)
    fake.validity = b'9043'
    fake.messages.pop(b'2734')
    assert reader.poll([LOGICAL_ID]) == []


@pytest.mark.parametrize('signature', ['\n\n318575094\n318575094@qq.com', '\n\n-- \n318575094\n318575094@qq.com'])
def test_approved_qq_signature_is_removed_from_authored_json(signature):
    assert mail_replies.extract_reply_text(reply('{"确认提交": true}' + signature)) == '{"确认提交": true}'


def test_approved_mailbox_inside_authored_json_is_preserved():
    body = '{"reviewer": "318575094@qq.com", "account": "318575094"}'
    assert mail_replies.extract_reply_text(reply(body)) == body


def test_custom_request_header_can_bind_without_body_marker(make_reader):
    original = notification(custom_header=True)
    original.set_content('Preview attached; no logical marker in body.')
    fake = SearchingImap({b'2734': original.as_bytes(), b'2735': reply(parent=REWRITTEN_ID).as_bytes()})
    assert [item.key for item in make_reader(fake).poll([LOGICAL_ID])] == ['9042:2735']


def test_cached_alias_does_not_authorize_a_different_pending_request(make_reader):
    fake = SearchingImap({b'2734': notification().as_bytes(), b'2735': reply(parent=REWRITTEN_ID).as_bytes()})
    reader = make_reader(fake)
    assert len(reader.poll([LOGICAL_ID])) == 1
    assert reader.poll(['<different.image_batch_0003@video-ai.local>']) == []
