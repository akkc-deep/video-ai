"""Call-local unlimited formal production; request timeouts stay independent."""
from contextvars import ContextVar
from functools import wraps

from ..adapters.common import positive_timeout

_production = ContextVar('unlimited_production_execution', default=False)


def unlimited_execution():
    return _production.get()


def production_execution(operation):
    """Apply current production policy without rewriting historical run inputs."""
    @wraps(operation)
    def execute(*args, **kwargs):
        token = _production.set(True)
        try:
            return operation(*args, **kwargs)
        finally:
            _production.reset(token)
    return execute


def command_timeout(seconds, maximum=None):
    """None is an actual unlimited wait, never a larger finite substitute."""
    if unlimited_execution():
        return None
    seconds = positive_timeout(seconds)
    return seconds if maximum is None else min(maximum, seconds)


def execution_deadline(seconds, now):
    seconds = command_timeout(seconds)
    return None if seconds is None else now + seconds


def execution_remaining(deadline, now):
    if deadline is None:
        return None
    remaining = deadline - now
    if remaining <= 0:
        raise TimeoutError('media budget expired')
    return remaining


def request_timeout(deadline, seconds, now):
    """A missing operation deadline never removes the finite network bound."""
    seconds = positive_timeout(seconds)
    return seconds if deadline is None else min(seconds, execution_remaining(deadline, now))


def historical_command_timeout(value):
    # Read legacy finite completions and current unlimited completions. The
    # command arguments, owned paths, raw outputs and durable finish event are
    # still compared in full by the consumer.
    return value is None or type(value) in (int,float) and value == 300


def command_receipt_policy(record):
    """Validate explicit current receipts independently of an invocation scope."""
    if record['timeout_seconds'] is None:
        return record.get('time_limits') == 'unlimited_v1'
    return (type(record['timeout_seconds']) is int and record['timeout_seconds'] == 300
            and 'time_limits' not in record)
