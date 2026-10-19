# JIM-04 Task 1 storage implementation report

Date: 2026-10-19. Scope: `adapters/reference_storage.py`, `adapters/external_https.py`, storage/HTTPS tests. No Git writes, cloud requests, bucket/ACL changes, SMTP or paid generation calls were performed.

## Implemented boundary

`ReferenceStorage(settings, *, http=None, clock=None, ownership_check=None)` accepts the plain dictionary returned by `reference_config.parse_reference_storage`; a dataclass with the same fields is accepted through `asdict`. The adapter checks the bucket/region/endpoint, safe key prefix and finite positive request timeout locally. The configuration parser remains responsible for the full exact configuration schema/defaults and model TTL budget. `clock` is a callable returning an aware `datetime`; the default is UTC now. `http` defaults to `ExternalHttpsClient` and can be replaced with a request-compatible test double. `ownership_check()` is read-only and must not write run-lock state from a network thread.

`check_credentials() -> None` reads `access_key_env`/`secret_key_env` from the current process and validates that values are present and safe for signing. It exposes no credential values and performs no network activity. Missing or malformed values raise `AdapterError(FailureKind.explicit, 'TOS credentials unavailable')`. Each ensure/presign reads credentials anew, allowing environment credential rotation without changing object identity.

`ensure_original(original, *, run_id, before_put) -> dict` consumes the already validated `path/bytes/sha256/width/height/format` original. It additionally rereads the source and checks byte count and SHA256 before networking. Supported original formats are png/jpeg/webp. Run IDs and key segments are safe ASCII, and the deterministic key is `<key_prefix>/<run_id>/<sha256>.original`.

The returned dictionary has exactly `bucket/region/endpoint/key/bytes/sha256/content_type/etag`. ETag is retained as a service entity tag and is never treated as a content digest. No authorization, signed URL, credential, local path or image bytes appear in this public receipt.

The initial request is signed HEAD. Only HEAD 404 permits an upload. Existing objects require matching `Content-Length`, `Content-Type`, `x-tos-meta-sha256`, and a nonempty ETag, followed by a GET of the actual bytes with matching length and SHA256. An upload requires the caller's intent authorization, signs host/content-type/x-tos-* headers, and is followed by the same HEAD+GET verification. There is no request replay in an invocation. A later explicit invocation starts with HEAD again: if an earlier unknown PUT succeeded it verifies/reuses the object; if the object is still 404 it can upload the same content-addressed key.

`before_put()` takes **no arguments** and executes on the thread calling `ensure_original`. For missing objects the network worker reports ready and cannot PUT until the caller finishes this callback and passes deadline/ownership checks. For an existing verified object the callback also executes once before return, allowing a logical intent to be persisted for recovered/reused objects without claiming a PUT occurred. Runtime callers must persist the design's `intent.json` inside this callback and persist `object.json` only after a returned verified receipt. This adapter writes no files. Exceptions or interruption in the callback, expiration during it, or lost ownership revoke permission and cannot authorize a late PUT.

One finite `request_timeout_seconds` budget covers the whole network transaction and callback authorization period. Every network operation receives the remaining budget and controlled response limits. Background work checks cancellation, deadline and read-only ownership before requests, after requests, and after DNS/TLS at the real socket-send boundary. Late HEAD/DNS workers cannot progress to PUT after the caller exits. A callback itself executes synchronously and must return; arbitrary caller code cannot be forcibly interrupted by the adapter.

`presign_get(object_record, *, expires_seconds) -> dict` verifies the configured object bucket/region/endpoint/key boundary, accepts only integer TTL 1..604800 (rejecting bool), and returns exactly `url/issued_at/expires_at`. Times use UTC `...Z`; the URL is generated entirely in memory, with no network or log write. The runtime owns saving only URL SHA256 and these two timestamps in ordinary records. The adapter does not persist the temporary URL.

## HTTPS extensions and failures

`ExternalResponse(status, body, headers={})` preserves the original two positional arguments and adds response headers. `ExternalHttpsClient.request` additionally permits PUT and HEAD and accepts `allow_not_found=False`, `ownership_check=None`, and `strict_url=False`.

`allow_not_found=True` is valid only for HEAD; it permits a HEAD 404 response without weakening GET/POST status errors. HEAD accepts no request body, returns an empty body, and does not compare the remote object's Content-Length to an empty HEAD body. GET/POST preserve prior consumer behavior. Storage sets `strict_url=True`, requiring the transport's final URL to equal the requested URL. The existing no-redirect handler still refuses HTTP redirects for all methods, and proxies remain disabled.

`ownership_check()` runs before transport activity and is attached to the real HTTPS connection: it runs again after DNS/TLS and immediately before HTTP send. Timeouts and caller interruption cancel the same guard. A post-DNS test observes real `HTTPConnection.send` behavior with an injected socket and confirms no HTTP headers or body are transmitted after ownership loss, timeout or interrupted caller exit.

Failure categories:

| Condition | Result |
| --- | --- |
| Unsafe configuration, timeout or expiry argument | local `ValueError` |
| Missing credentials, malformed original/run ID, unreadable or changed source | `AdapterError(explicit)` before any network |
| Existing object metadata or actual bytes conflict | `AdapterError(invalid_result)`, never overwrite |
| HEAD/GET non-success other than explicitly allowed HEAD 404, transport error or deadline | `AdapterError(unavailable)` |
| PUT transport/status/deadline uncertainty | `AdapterError(ambiguous)`, no automatic replay |
| Caller callback/ownership/deadline failure before PUT | `AdapterError(unavailable)` with a fixed safe message |
| Transaction deadline/ownership loss after PUT has been attempted | conservatively `AdapterError(ambiguous)` unless a more specific safe adapter failure already exists |
| Caller KeyboardInterrupt/SystemExit | cancellation is set, then the original interruption propagates |

Messages do not contain raw transport errors, request URLs, authorization headers, credentials or media bytes. The runtime must stop generation whenever storage fails and only persist public object identity. The implementation exposes no bucket creation, ACL, delete or policy API.

## RED/GREEN evidence

All Python execution used the required bootstrap pattern:

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment '<label below>'
& $VideoAiPython -B -m pytest <arguments below>
```

1. Label `jim-04-storage-red`, arguments `tests/unit/test_reference_storage.py -q`: **1 failed**, expected `ModuleNotFoundError: No module named 'video_ai.adapters.reference_storage'`. This was the first implementation action: an independent GET presign oracle with UTC 2026-10-18T00:00:00Z, AK test-ak, SK test-sk, cn-beijing/test-bucket, key `video-ai-references/fixture-run/` plus 64 `a` plus `.original`, TTL 3600. Its canonical request bytes and HMAC derivation do not call production signing helpers. The final test also verifies a separate fixed HEAD header canonical vector. A PUT header vector uses captured actual upload headers and independently constructed canonical bytes.
2. Label `jim-04-storage-sign-green`, same arguments: **1 passed** after pure presign implementation.
3. Label `jim-04-storage-behavior-red`, arguments `tests/unit/test_reference_storage.py tests/unit/test_external_https.py -q --tb=short`: **18 failed, 1 passed** on missing ensure_original/HEAD/ownership behavior. The missing ownership parameter also produced two expected background-thread TypeError warnings in that RED run; final runs have no such warnings.
4. Label `jim-04-storage-behavior-green`, arguments including `tests/unit/test_jimeng.py`: **8 failed, 40 passed**. This exposed existing Jimeng test transports returning an origin-only final URL: an unconditional exact-URL check had changed the old behavior. The adapter now enables exact-URL checking only when requested by storage; existing behavior remains compatible.
5. Label `jim-04-storage-adapter-green`, arguments `tests/unit/test_reference_storage.py tests/unit/test_external_https.py tests/unit/test_jimeng.py -q --tb=short`: **48 passed**.
6. Label `jim-04-storage-regression`, the final broad arguments below before the interruption regression was added: **85 passed**.
7. Label `jim-04-storage-interrupt-red`, arguments `tests/unit/test_external_https.py::test_interrupted_caller_cancels_late_connection -q --tb=short`: **1 failed**. A caller interrupted during blocked DNS could still send headers/body when DNS returned. Root cause: the wait path set cancellation only on timeout. Setting cancellation on every exceptional caller exit fixes the same post-DNS request guard.
8. Label `jim-04-storage-final`, final verification:

```powershell
& $VideoAiPython -B -m pytest tests/unit/test_reference_storage.py tests/unit/test_external_https.py tests/unit/test_jimeng.py tests/unit/test_jimeng_inputs.py tests/integration/test_jimeng_candidates.py -q --tb=short
```

**86 passed in 8.98s, exit 0**, no warnings. Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-04-storage-final-a60481d2c2034af59ce2a34a4c53dfaf.log`.

Coverage includes Chinese source path/raw byte digest, missing-object upload, verified reuse and logical intent, metadata/size/type/ETag conflicts, changed bytes, 403, same-host changed URL refusal, unknown PUT followed by explicit recovery, callback thread identity, callback errors/expiry/ownership loss, late HEAD cancellation, real socket-send guard after DNS, interrupted caller cancellation, invalid local identity zero network, TTL bounds, credential rotation, and existing Jimeng unit/input/integration behavior.

The project-wide suite is intentionally left to the root agent's serial final verification, as requested; it was not run concurrently here. Real bucket privacy, real TOS access, service-side reference-image fetching and model visual quality remain JIM-08 observations and are not proven by these substitutes.
