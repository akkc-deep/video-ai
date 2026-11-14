"""Cooperative pause checks for local admission; mutable signals stay unsealed."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident
from time import monotonic

_control=ContextVar('scene_review_control',default=None)


@contextmanager
def review_admission_control(*, stop_requested=None):
    current=_control.get()
    if stop_requested is None or (current is not None and current['active']
            and current['thread']==get_ident() and current['stop'] is stop_requested):
        yield
        return
    state=dict(active=True,thread=get_ident(),stop=stop_requested,next_poll=0)
    token=_control.set(state)
    try: yield
    finally:
        state['active']=False
        _control.reset(token)


def review_checkpoint(*, force=False):
    state=_control.get()
    if state is None or not state['active'] or state['thread']!=get_ident(): return
    current=monotonic()
    if force or current>=state['next_poll']:
        state['next_poll']=current+0.1
        if state['stop'](): raise KeyboardInterrupt('review admission paused')
