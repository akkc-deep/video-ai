# JIM-04 verification

## Outcome and scope

Implemented prepared-run reference generation: immutable model/capability/storage binding, stable selected originals published through content-addressed TOS, actual controlled `image_urls` submissions, one-submission recovery, strict provenance, existing batch mail/selection and complete Wan start-image admission. All cloud/SMTP/socket boundaries in tests are substitutes; local PNG/JPEG decode and email media use real tools. No real upload, paid generation, mail delivery, model service, Wan request or visual-quality assertion occurred.

The approved design remains `JIM-04-design.md`. The request, intent, accepted task, provenance, candidate and Wan public schemas are unchanged. An additional `submit-evidence.json` binds the canonical intent digest before network transmission. Byte-identical accepted baselines share an object while preserving separate scene/candidate reference positions and independently validating each original.

## Acceptance evidence

1. `test_actual_reference_requests_fixed_baseline_and_complete_wan_images` captures real `JimengClient` encoded HTTP bodies: two associated scenes directly reference the same exact accepted baseline, both entity/background uses remain, shared Bible prompt is exact. `test_distinct_baselines_with_identical_bytes_share_object_preserving_uses` checks two original positions and one object upload. Real JPEG is covered separately.
2. Configuration tests cover explicit primary/fallback selection, strict capability/evidence/format/numeric validation and immutable supplementation. Batch limit tests prove zero storage/paid requests for byte/dimension/format/prompt/TTL violations; missing baseline stops before settings or network. Candidate-level invalid sources/uses/count/expired URL and changed configuration tests protect the actual submit boundary.
3. Storage tests independently calculate fixed TOS4 GET/HEAD/PUT vectors, verify real byte digests/metadata, caller-thread intent callback, reuse/conflicts/unknown PUT, finite deadlines and cancellation. Durable production JSON is checked for secrets and signed URLs. Storage exposes no bucket/ACL creation or modification API.
4. Unknown submission never replays; accepted/query/download and durable-boundary recovery retain the original task. Actual-send guards check ownership, remaining URL budget and original/object/settings/request hashes after DNS/TLS; accepted-task recovery continues after input URL expiration. Submission evidence hash mutation is refused.
5. Existing notification/selection interfaces send actual local MIME via SMTP substitutes. Selection without complete actual-observation fixture produces no Wan input; complete choices plus explicit all-images observation produce ordered exact original inputs. Plain-text-only historical related candidates cannot pass reference admission. Original/provenance mutation invalidates admission. Owned/external lock and lock-release-error results remain independent schema 2.

## Verification runs

All Python used `. ./scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment`, and `& $VideoAiPython -B -m pytest ...`. Runtime/cache/logs remain under D:/VideoSi. No Git executable was available and .git is read-only; local changes are retained without commits.

- Storage delegate: 86 passed in 8.98s. Detail: `JIM-04-storage-report.md`.
- Root configuration: 36 initial missing-module RED; 63 new/config/input GREEN, then review-specific credential and stable-read RED/GREEN. Latest config/input 44 passed in 1.98s.
- Candidate delegate: 29 targeted and 96 relevant historical tests before final safety fixes. Final focused mutation/unknown/DNS-TTL 4 passed in 17.13s, expired-input recovery/TTL 2 passed in 9.20s. Detail: `JIM-04-candidates-report.md`.
- Root initial combined new tests: 112 passed in 314.78s, output `D:/VideoSi/cache/video-ai/logs/jim-04-targeted.txt`. This predates the final combined review verification and is not presented as the final tree result.
- Final new tests: **118 passed in 360.71s (0:06:00), exit 0**, output `D:/VideoSi/cache/video-ai/logs/jim-04-targeted-final.txt`.
- Final design-listed historical tests: **186 passed in 200.44s (0:03:20), exit 0**, output `D:/VideoSi/cache/video-ai/logs/jim-04-historical-final.txt`.
- Final whole suite: **3012 passed in 3840.59s (1:04:00), exit 0**, output `D:/VideoSi/cache/video-ai/logs/jim-04-full-final.txt`. All three verification commands ran sequentially in the same bootstrapped session, with no intervening implementation edits and no failures or warnings in the final summaries.
- File identities for the verified implementation and tests: `D:/VideoSi/cache/video-ai/logs/jim-04-verified-files.json` (20 files; final whole suite includes the added original/provenance admission mutation assertions). All 20 SHA256 values matched after final testing.

## Independent review

`JIM-04-storage-config-review.md` records two reproduced and fixed Important findings: unchecked unused fallback config could persist credentials, and capability validation/copy used separate reads. Exact stable-buffer validation occurs before saving; 7 independent focused checks passed.

`JIM-04-final-review.md` records three reproduced and fixed Important findings: shared-object source alias conflict, actual-send TTL gap, and unanchored submit evidence. JPEG normalization was also corrected. Scoped independent re-review: 4 passed, 22 deselected in 20.17s; no remaining Critical/Important finding established.

## Limits

Real model capability material must be supplied by a named verifier; fixture limits do not describe the service. Existing TOS bucket privacy, account permission, remote reference fetching, real QQ delivery and visual quality remain JIM-08 acceptance. Full new-script coordination and Wan/video generation remain later tasks. JIM-04's five code/substitute acceptance outcomes are verified, and its completion was recorded on 2026-10-19.
