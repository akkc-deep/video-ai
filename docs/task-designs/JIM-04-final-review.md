# JIM-04 independent whole-change review

Reviewed 2026-10-19 against the complete `JIM-04-design.md` and `JIM-04-plan.md`. Scope included reference configuration and freezing, immutable settings, TOS/HTTPS, Jimeng submission, candidate transactions, selection dispatch, provenance, batch coordination, Wan image admission, and new tests. The prior storage/config review's fixed credential-copy and capability-read findings were not reopened.

Only this report was edited by the reviewer. Reproductions used the bootstrapped Python, real local PNG/plan/selection records, and injected HTTP/socket boundaries. No real cloud, SMTP, paid service, Git writes, or full-suite execution occurred. Root integration/regression verification runs separately.

**Final review status:** All three Important findings below are resolved in the inspected revision. The historical findings and reproductions are retained for traceability. Independent scoped re-verification passed 4 tests; root separately verified the shared-object and real-JPEG regressions. No remaining Critical or Important finding was established. Final combined regression/full-suite results remain the root coordinator's responsibility.

## Critical

None established.

## Important

### 1. Distinct accepted baselines with identical bytes cannot share their content-addressed object

**Locations at reproduction:** `src/video_ai/runtime/production_reference_images.py:102-112` and `src/video_ai/runtime/reference_image_records.py:103-116`. The coordinator's source handling is being revised during this review; inspect the current equivalents before applying any further patch.

Storage is keyed by SHA256, but its immutable intent's `source.path` was required to equal every candidate path that reused the object. Two independently accepted baseline scenes can have equal bytes at different immutable candidate paths. The first creates the object/intent; the second fails with `reference storage intent identity differs`. The read-only `_object` validator independently imposed the same equality, so fixing only upload reuse is insufficient.

**Concrete reproduction:** Start from `scene_proposal()`, add a second entity and scene group, make scene 0002 their independent baseline, and make scene 0003 reference both entities. Supply valid source evidence for scene-group changes. `setup_selection` produces batches `[[scene_0001, scene_0002], [scene_0003]]`; `batch`/`accept_batch` accept both authentic PNG baselines. The existing helper produces identical PNG bytes at their distinct paths. Bind a valid capability with `max_images=2`, then call `produce_reference_batch` with the existing offline cloud fixture. Actual result: `blocked`, `reference storage intent identity differs`; storage calls `HEAD, PUT, HEAD, GET`; zero submits.

Evidence run: `D:/VideoSi/projects/video-ai/runs/20261019-002639-13cea02c3309`. Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-04-final-review-multi-baseline-da994391c2b841baa4ee209ce77cbed3.log`.

Keep the initial object upload source immutable and validate its bytes independently. Each reference must still validate its own accepted original. Preserve two reference positions because the specified deduplication identity includes scene/candidate/SHA, even when the two positions share one object. The initial single-baseline/multiple-use test did not exercise this case. Root has added a dedicated regression and is applying the fix.

### 2. URL lifetime was checked before connection setup, not at actual transmission

**Locations at reproduction:** `src/video_ai/runtime/jimeng_reference_candidates.py:85-87,170` (the pre-submit lifetime check and ownership-only client guard); `src/video_ai/adapters/external_https.py:39-47` (post-connect/send guard).

The caller checked remaining URL lifetime immediately before `client.submit`, but the guard used after DNS/TLS checked only lock ownership. Connection setup could consume the remaining task/download/skew budget and still transmit the paid request.

**Concrete reproduction:** Generate through a real `JimengClient` and `ExternalHttpsClient`, patch only `HTTPSConnection.connect` to install a recording fake socket, and advance the reference module's UTC clock by 4000 seconds inside that connect. The existing fixture's signed URL has a 3600-second TTL. The fake socket recorded two `sendall` calls, including a body containing `image_urls`, after the simulated expiry. An injected offline response failure then stopped the request. No network connection occurred.

Evidence run: `D:/VideoSi/projects/video-ai/runs/20261019-002728-2574b562c643`. Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-04-final-review-send-ttl-f5b240ed4ad141dd9f8471814d7b1489.log`.

The implementer is adding a read-only actual-send guard for URL lifetime and local identities, and restoring the ownership-only guard for original-task query/download recovery. Combine this with finding 1: snapshot every selected reference original, not only the shared object's initial upload source. The original post-DNS ownership test covered lost locks but not elapsed URL budget.

### 3. Submission evidence hashes can be changed without invalidating candidate admission

**Locations:** `src/video_ai/runtime/reference_image_records.py:157-175` (`validate_reference_intent`) and `:179-194` (`verify_reference_provenance`); `src/video_ai/runtime/jimeng_reference_candidates.py` intent creation and accepted-record persistence.

The reader checks only the syntax of `submit_body_sha256` and each `reference_urls[].sha256`. No subsequent immutable record binds the canonical digest of the complete intent. Provenance binds the logical request, which deliberately excludes temporary URLs and their evidence. Consequently, changing only the actual-send evidence in an otherwise valid intent leaves all candidate/provenance checks satisfied.

**Concrete reproduction:** Use `reference_setup` and `generate_reference` to finish a valid scene. In `request_01/intent.json`, set `submit_body_sha256` to 64 zeroes and the first URL hash to 64 ones, leaving every other file untouched. `reference_candidates(...)` still returns both candidates successfully. These are valid-format, deliberately incorrect hashes, so the test is not a malformed-schema case.

Evidence run: `D:/VideoSi/projects/video-ai/runs/20261019-002748-84510b7a3b62`. Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-04-final-review-intent-tamper-83123a6d02ac4ca686b40390885562f4.log`.

The actual request's audit evidence needs a canonical-digest binding that read-only admission checks. Preserve the required public record schemas and URL secrecy; an additional immutable evidence receipt is one possible approach. Add independent mutations of body hash, URL hash/order, and otherwise-valid timestamps. Existing provenance-tamper tests mutate an object ETag and do not cover this unanchored intent evidence.

## Minor / resolved during review

The coordinator compared the decoder's `mjpeg` format directly to capability formats (`jpeg`) and indexed a MIME map lacking `mjpeg`, while the reference-record reader already normalized it. This prevented valid real JPEG baselines from entering reference generation. Root independently reproduced the real-JPEG failure and has applied normalization at capability/storage boundaries, preserving original candidate metadata. The dedicated real-JPEG regression is the appropriate verification; no duplicate reviewer test was run.

## Other observations and limits

The reviewed normal path preserves fixed accepted originals, Bible order and multi-use bindings, sends explicit reference URLs in the actual body, preflights all scene capability limits before starting cloud work, retains logical-request identity across original-task recovery, and routes reference manifests to strict read-only verification. Wan construction consumes complete selection/observation acceptance and requires reference provenance for every associated scene. Legacy request dispatch remains separate. No implicit fallback or paid replay route was established in the inspected paths.

This local review does not establish real-service TOS interoperability, model permissions, remote URL fetchability, email delivery, or visual consistency; those remain the explicitly scoped JIM-08 observations.

## Fix re-review and verification

- **Finding 1 resolved:** `production_reference_images.py:105-118` preserves and independently hashes the initial object source. `reference_image_records.py:103-130` requires that source to be a previously accepted original with matching actual bytes, while each current reference is independently resolved against its accepted candidate. `_submission_guard` additionally snapshots each selected original path, including paths distinct from the initial upload source. Root's dedicated shared-object regression passed **1 test in 16.77s**; output `D:/VideoSi/cache/video-ai/logs/jim-04-shared-object-green.txt`.
- **Finding 2 resolved:** `jimeng_reference_candidates.py:61-91` creates the read-only transmission guard. It checks URL lifetime and hashes selected originals, object evidence, settings, capability and current request evidence at the transport's actual-send boundary. The request-specific guard is restored to ownership-only after submission, and the HTTP request retains its already-captured guard for a late worker. Independent scoped tests passed both the post-DNS TTL refusal and expired-input original-task recovery.
- **Finding 3 resolved:** `jimeng_reference_candidates.py:114` writes `submit-evidence.json` before transmission. `reference_image_records.py:189-200` binds the complete canonical intent digest and checks exact evidence fields; provenance verification and accepted-task recovery require that binding. The public intent/request/provenance/accepted/Wan structures remain unchanged. Independent tests now reject separate valid-format mutations of the actual body hash and URL hash.
- **JPEG resolved:** The coordinator normalizes decoder `mjpeg` to storage/capability `jpeg` at `production_reference_images.py:91`, preserving the original candidate metadata. Root's dedicated real-JPEG regression passed **1 test in 17.89s**; output `D:/VideoSi/cache/video-ai/logs/jim-04-jpeg-green.txt`.

Independent final command, after bootstrap:

```powershell
& $VideoAiPython -B -m pytest tests/integration/test_reference_candidates.py -k 'single_intent_hash_tampering or submit_ttl_guard or original_task_query_recovery' -q --tb=short
```

Result: **4 passed, 22 deselected in 20.17s**, exit 0. Bootstrap log: `D:/VideoSi/cache/video-ai/logs/jim-04-final-review-fixes-cbfb34b423ca491c9bde7e08db4baec9.log`.
