"""Request-scoped interactive mail mode for newly created notifications."""
from contextlib import contextmanager
from contextvars import ContextVar


_reply_mode = ContextVar('video_ai_mail_reply_mode', default=False)


def mail_reply_mode() -> bool:
    return _reply_mode.get()


@contextmanager
def mail_reply_context(enabled: bool = True):
    token = _reply_mode.set(enabled)
    try:
        yield
    finally:
        _reply_mode.reset(token)
