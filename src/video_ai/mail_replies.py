"""Bounded, read-only IMAP reply collection for the approved production mailbox."""
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
import imaplib
import re
import ssl

from .credentials import read_credentials


APPROVED_MAILBOX = '318575094@qq.com'
_MAX_MESSAGES = 100
_MAX_MESSAGE_BYTES = 1_048_576
_ORIGINAL_PREFIX_BYTES = 65_536
_MAX_PENDING_IDS = 100
_ERROR_CATEGORIES = frozenset({
    'credentials_unavailable', 'connection_failed', 'authentication_failed',
    'mailbox_unavailable', 'mailbox_identity_unavailable', 'search_failed',
    'fetch_failed', 'invalid_request', 'invalid_settings',
})


class MailboxError(RuntimeError):
    """An operational failure containing a fixed category, never server text."""

    def __init__(self, category):
        super().__init__(category if category in _ERROR_CATEGORIES else 'connection_failed')


@dataclass(frozen=True)
class MailboxSettings:
    host: str = 'imap.qq.com'
    port: int = 993
    mailbox: str = 'INBOX'
    poll_seconds: float = 30
    timeout_seconds: float = 30


@dataclass(frozen=True)
class MailReply:
    key: str
    message_id: str
    sender: str
    text: str


class _ReplyHTML(HTMLParser):
    """Flatten a body while excluding common webmail quote containers."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.stack = []
        self.stopped = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        identity = (attrs.get('id', '') + ' ' + attrs.get('class', '')).lower()
        if 'divrplyfwdmsg' in identity or 'stopspelling' in identity:
            self.stopped = True
        hidden = (tag in {'blockquote', 'script', 'style', 'head'}
                  or any(marker in identity for marker in ('gmail_quote', 'qqmail_quote', 'yahoo_quoted'))
                  or 'display:none' in attrs.get('style', '').replace(' ', '').lower())
        excluded = self.stopped or hidden or (self.stack and self.stack[-1][1])
        if tag not in {'br', 'hr', 'img', 'meta', 'link', 'input', 'wbr', 'source'}:
            self.stack.append((tag, bool(excluded)))
        if not excluded and tag in {'br', 'div', 'p', 'li', 'tr', 'hr'}:
            self.text.append('\n')

    def handle_endtag(self, tag):
        excluded = self.stopped or (self.stack and self.stack[-1][1])
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not excluded and tag in {'div', 'p', 'li', 'tr'}:
            self.text.append('\n')

    def handle_data(self, data):
        if not self.stopped and not (self.stack and self.stack[-1][1]):
            self.text.append(data)


def _body_parts(message):
    if message.get_content_disposition() == 'attachment' or message.get_content_type() == 'message/rfc822':
        return
    if message.is_multipart():
        for part in message.get_payload():
            yield from _body_parts(part)
    elif message.get_content_type() in {'text/plain', 'text/html'}:
        yield message


def _without_quotes(text):
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    authored = []
    for index, line in enumerate(lines):
        stripped = line.strip().replace('\xa0', ' ')
        wrapped_attribution = any(
            re.match(r'^On\b.{0,1000}\bwrote\s*[:：]\s*$',
                     ' '.join(item.strip() for item in lines[index:index + length]), re.I)
            for length in range(1, 5)
        ) if re.match(r'^On\b', stripped, re.I) else False
        if (wrapped_attribution
                or re.match(r'^在\s*.{0,1000}(?:写道|寫道)\s*[:：]\s*$', stripped)
                or re.match(r'^[\s_-]*(?:Original(?: Message)?|Forwarded message|原始邮件|原始郵件|转发邮件)[\s_:-]*$', stripped, re.I)):
            break
        if re.match(r'^(?:From|发件人|寄件者)\s*[:：]', stripped, re.I):
            following = '\n'.join(lines[index + 1:index + 8])
            if re.search(r'^(?:Sent|Date|To|Subject|发送时间|收件人|主题|主旨)\s*[:：]', following, re.I | re.M):
                break
        if stripped.startswith('>'):
            continue
        authored.append(line.rstrip())
    # HTML block boundaries can introduce blank lines; keep user paragraph boundaries.
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(authored)).strip()
    # QQ's account card is an exact trailing two-line signature, not reply JSON.
    result = re.sub(r'(?:\n[ \t]*)+(?:--[ \t]*\n)?318575094\n318575094@qq\.com$', '', result)
    return result.rstrip()


def extract_reply_text(message) -> str:
    """Return newly authored plain text, excluding attachments and quoted mail."""
    parts = list(_body_parts(message))
    part = next((item for item in parts if item.get_content_type() == 'text/plain'), None)
    if part is None:
        part = next(iter(parts), None)
    if part is None:
        return ''
    payload = part.get_payload(decode=True)
    if payload is None:
        text = str(part.get_payload())
    else:
        try:
            text = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
        except LookupError:
            text = payload.decode('utf-8', errors='replace')
    if part.get_content_type() == 'text/html':
        parser = _ReplyHTML()
        parser.feed(text)
        text = ''.join(parser.text)
    return _without_quotes(text)


def _safe_call(category, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception:
        raise MailboxError(category) from None


def _ok(response, category):
    if (not isinstance(response, tuple) or len(response) != 2
            or response[0] not in ('OK', b'OK') or not isinstance(response[1], (list, tuple))):
        raise MailboxError(category)
    return response[1]


def _pending_ids(values):
    if isinstance(values, str):
        values = [values]
    result = set()
    try:
        for value in values:
            if not isinstance(value, str) or not re.fullmatch(r'<?[^<>\s"\\]+>?', value):
                raise MailboxError('invalid_request')
            result.add('<' + value.strip('<>') + '>')
            if len(result) > _MAX_PENDING_IDS:
                raise MailboxError('invalid_request')
    except TypeError:
        raise MailboxError('invalid_request') from None
    return result


def _search(connection, *criteria):
    data = _ok(_safe_call('search_failed', connection.uid, 'SEARCH', None, *criteria), 'search_failed')
    return {token for chunk in data if isinstance(chunk, bytes)
            for token in chunk.split() if token.isdigit()}


def _fetch_prefix(connection, uid, limit):
    data = _ok(_safe_call('fetch_failed', connection.uid, 'FETCH', uid,
                         f'(BODY.PEEK[]<0.{limit}>)'), 'fetch_failed')
    return next((item[1] for item in data if isinstance(item, tuple)
                 and len(item) == 2 and isinstance(item[1], bytes)), None)


def _approved_address(message, header):
    addresses = getaddresses(message.get_all(header, []))
    return len(addresses) == 1 and addresses[0][1].lower() == APPROVED_MAILBOX


def _thread_ids(message):
    references = ' '.join(str(value) for header in ('In-Reply-To', 'References')
                          for value in message.get_all(header, []))
    return set(re.findall(r'<[^<>\s]+>', references))


def _original_alias(message, logical_id):
    """Trust the delivered ID only on a self-addressed, unquoted original."""
    if (not _approved_address(message, 'From') or not _approved_address(message, 'To')
            or message.get_all('In-Reply-To') or message.get_all('References')):
        return None
    exact_values = {logical_id, logical_id[1:-1]}
    marker_matches = any(str(value).strip() in exact_values
                         for value in message.get_all('X-Video-AI-Request-ID', []))
    if not marker_matches:
        fields = re.findall(r'^(?:Message-ID|Request-ID):[ \t]*(\S+)[ \t]*$',
                            extract_reply_text(message), re.I | re.M)
        marker_matches = bool(exact_values.intersection(fields))
    alias = str(message.get('Message-ID', '')).strip()
    return alias if marker_matches and re.fullmatch(r'<[^<>\s"\\]+>', alias) else None


class ImapReplyReader:
    def __init__(self, settings=None, *, credential_name='VIDEO_AI_SMTP_AUTH_CODE', imap_factory=None):
        self.settings = settings or MailboxSettings()
        self.credential_name = credential_name
        self.imap_factory = imap_factory or imaplib.IMAP4_SSL
        self._aliases = {}

    def poll(self, message_ids) -> list[MailReply]:
        """Read up to 100 matching messages without changing IMAP flags or folders."""
        pending = _pending_ids(message_ids)
        if not pending:
            return []
        settings = self.settings
        if (not isinstance(settings.timeout_seconds, (int, float))
                or not 0 < settings.timeout_seconds <= 300):
            raise MailboxError('invalid_settings')
        password, = _safe_call('credentials_unavailable', read_credentials, self.credential_name)
        if not password:
            raise MailboxError('credentials_unavailable')
        connection = _safe_call('connection_failed', self.imap_factory,
                                settings.host, settings.port,
                                ssl_context=ssl.create_default_context(), timeout=settings.timeout_seconds)
        try:
            _ok(_safe_call('authentication_failed', connection.login, APPROVED_MAILBOX, password), 'authentication_failed')
            _ok(_safe_call('mailbox_unavailable', connection.select, settings.mailbox, readonly=True), 'mailbox_unavailable')
            identity = _safe_call('mailbox_identity_unavailable', connection.response, 'UIDVALIDITY')
            try:
                validity = identity[1][0].decode('ascii')
                if not validity.isdecimal():
                    raise ValueError
            except (TypeError, IndexError, AttributeError, UnicodeError, ValueError):
                raise MailboxError('mailbox_identity_unavailable') from None
            self._aliases = {key: values for key, values in self._aliases.items()
                             if key[0] == validity and key[1] in pending}
            bindings = {logical: {logical} | self._aliases.get((validity, logical), set())
                        for logical in pending}
            replies, fetched, matched = {}, set(), set()

            def collect(thread_ids):
                uids = set()
                for thread_id in sorted(thread_ids):
                    for header in ('In-Reply-To', 'References'):
                        uids.update(_search(connection, 'HEADER', header, '"' + thread_id + '"'))
                for uid in sorted(uids - fetched, key=int)[-(_MAX_MESSAGES - len(fetched)):]:
                    if len(fetched) >= _MAX_MESSAGES:
                        break
                    fetched.add(uid)
                    raw = _fetch_prefix(connection, uid, _MAX_MESSAGE_BYTES + 1)
                    if raw is None or len(raw) > _MAX_MESSAGE_BYTES:
                        continue
                    message = BytesParser(policy=policy.default).parsebytes(raw)
                    if not _approved_address(message, 'From'):
                        continue
                    references = _thread_ids(message)
                    owners = {logical for logical, aliases in bindings.items() if aliases & references}
                    if not owners:
                        continue
                    matched.update(owners)
                    replies[uid] = MailReply(f'{validity}:{uid.decode("ascii")}',
                                            str(message.get('Message-ID', '')).strip(), APPROVED_MAILBOX,
                                            extract_reply_text(message))

            collect(set().union(*bindings.values()))
            # QQ can rewrite SMTP Message-ID. Discover its delivered ID from the
            # notification's stable marker, never from an arbitrary quoted reply.
            prefixes = {}
            new_aliases = set()
            for logical in sorted(pending - matched):
                if (validity, logical) in self._aliases:
                    continue
                token = '"' + logical[1:-1] + '"'
                originals = (_search(connection, 'HEADER', 'X-Video-AI-Request-ID', token)
                             | _search(connection, 'BODY', token))
                for uid in sorted(originals, key=int)[-_MAX_MESSAGES:]:
                    if uid not in prefixes:
                        if len(prefixes) >= _MAX_MESSAGES:
                            break
                        raw = _fetch_prefix(connection, uid, _ORIGINAL_PREFIX_BYTES)
                        prefixes[uid] = (BytesParser(policy=policy.default).parsebytes(raw[:_ORIGINAL_PREFIX_BYTES])
                                         if raw is not None else None)
                    if prefixes[uid] is None:
                        continue
                    alias = _original_alias(prefixes[uid], logical)
                    if alias:
                        self._aliases.setdefault((validity, logical), set()).add(alias)
                        bindings[logical].add(alias)
                        new_aliases.add(alias)
            if new_aliases:
                collect(new_aliases)
            return [replies[uid] for uid in sorted(replies, key=int)]
        finally:
            try:
                connection.logout()
            except Exception:
                pass
