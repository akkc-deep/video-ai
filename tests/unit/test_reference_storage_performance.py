"""Version-bound remote byte verification cache; unversioned objects stay strict."""
import pytest

from unit.test_reference_storage import original, storage, identity_headers, Response


@pytest.mark.parametrize('versions,gets', [(['v1', 'v1'], 1), ([None, None], 2), (['v1', 'v2'], 2)])
def test_only_matching_strong_version_reuses_remote_bytes(tmp_path, monkeypatch, versions, gets):
    row, data = original(tmp_path)
    calls = []
    current = [None]
    def transport(request, **kw):
        method = request.get_method()
        calls.append(method)
        if method == 'HEAD':
            current[0] = versions[len([m for m in calls if m == 'HEAD'])-1]
        headers = identity_headers(row)
        if current[0] is not None: headers['x-tos-version-id'] = current[0]
        return Response(request, body=data if method == 'GET' else b'', headers=headers)
    adapter = storage(monkeypatch, transport)
    receipts = []
    for _ in range(2):
        receipts.append(adapter.ensure_original(row, run_id='fixture-run', before_put=lambda: None))
    assert receipts[0] == receipts[1]
    assert calls.count('HEAD') == 2
    assert calls.count('GET') == gets


def test_head_and_get_version_mismatch_never_admits_cache(tmp_path, monkeypatch):
    row, data = original(tmp_path)
    calls = []
    def transport(request, **kw):
        method = request.get_method(); calls.append(method)
        headers = identity_headers(row)
        headers['x-tos-version-id'] = 'head-version' if method == 'HEAD' else 'get-version'
        return Response(request, body=data if method == 'GET' else b'', headers=headers)
    adapter = storage(monkeypatch, transport)
    for _ in range(2): adapter.ensure_original(row, run_id='fixture-run', before_put=lambda: None)
    assert calls.count('GET') == 2
