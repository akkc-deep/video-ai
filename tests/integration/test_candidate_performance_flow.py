"""Ordinary image tasks overlap cloud waiting on the caller thread."""
import pytest
from integration.test_jimeng_candidates import candidate_setup, generate
from unit.test_production_inputs import production_config


@pytest.mark.parametrize('candidate_setup', [2], indirect=True)
def test_two_ordinary_tasks_are_accepted_before_polling(candidate_setup, monkeypatch):
    _, client, state, _ = candidate_setup
    state['urls'] = 1
    events = []
    submit, query = client.submit, client.query
    def submitting(*a, **kw): events.append('submit'); return submit(*a, **kw)
    def querying(*a, **kw): events.append('query'); return query(*a, **kw)
    monkeypatch.setattr(client, 'submit', submitting)
    monkeypatch.setattr(client, 'query', querying)
    result = generate(candidate_setup)
    assert events == ['submit', 'submit', 'query', 'query']
    assert len(result['candidates']) == 2
    assert generate(candidate_setup) == result
    assert events == ['submit', 'submit', 'query', 'query']


def test_ordinary_submit_rechecks_request_bytes_after_dns(candidate_setup, monkeypatch):
    import os
    from http.client import HTTPSConnection
    from video_ai.adapters.external_https import ExternalHttpsClient
    from video_ai.adapters.common import AdapterError
    _, client, _, run = candidate_setup
    sent = []
    class Socket:
        def sendall(self, data): sent.append(data)
        def close(self): pass
        def shutdown(self, *a): pass
    def connect(connection):
        path = run/'production/jimeng/scene_0001/request_01/request.json'
        metadata = path.stat(); raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1])+raw[1:])
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        connection.sock = Socket()
    monkeypatch.setattr(HTTPSConnection, 'connect', connect)
    client.http = ExternalHttpsClient()
    with pytest.raises((AdapterError, ValueError)): generate(candidate_setup)
    assert not sent
    assert not list((run/'production/jimeng/scene_0001').rglob('accepted.json'))
