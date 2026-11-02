"""Durable native work policy; replay never depends on the caller's scope."""
from ..planning.start_images import keys


def unlimited_policy():
    return dict(time_limits='unlimited_v1', timeout_seconds=None)


def unlimited_receipt(record):
    if 'execution_policy' not in record:
        return False
    value = record['execution_policy']
    keys(value, 'time_limits timeout_seconds', 'native execution policy')
    if value['time_limits'] != 'unlimited_v1' or value['timeout_seconds'] is not None:
        raise ValueError('native execution policy differs')
    return True


def receipt_fields(record):
    unlimited_receipt(record)
    return ' execution_policy' if 'execution_policy' in record else ''
