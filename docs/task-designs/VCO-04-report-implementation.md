# VCO-04 ordinary report verifier implementation evidence

Scope: `src/video_ai/media/continuity_report.py` and `tests/unit/test_continuity_report.py`. No experiment implementation was imported into production. This record concerns software evidence validation; its synthetic media and author strings do not establish actual agent playback, visual accuracy, or a ready production benchmark profile.

## Interfaces

`capture_continuity_engine()` returns exactly `{algorithm, parameters_sha256, implementation, dependency_fingerprint}`. `implementation` is a sorted list of three-field source Artifacts, including the ordinary analyzer, schema, geometry, scores, audit, colorimetry and this verifier; other existing continuity implementation modules are included by the analyzer's existing inventory rule.

`capture_engine_sources()` returns `{engine, versions, build_information, files}`. `versions` is exactly `{python,numpy,opencv}`; `build_information` is the complete OpenCV build text; `files` is the path-sorted original five-field FileIdentity inventory. It calls the analyzer's dependency inventory through an in-memory adapter, without making a logger, writing build text, or changing OpenCV threads.

`validate_continuity_report(report, *, manifest=None, expected_audit_run_dir=None, historical_engine=None, timeout=300, config=None, _budget=None)` accepts a report path or three-field Artifact. `manifest` optionally binds another path or Artifact; production callers supply their frozen config. It returns `{report, manifest, closure}`, where closure is a sorted, deduplicated list of three-field Artifacts.

Internal `_budget` accepts the runtime Reader protocol: `.charge(canonical_path, size)` and `.deadline` (absolute monotonic time). Every distinct parsed report/source/profile/raw-probe JSON path is charged to that object, so multiple clip verifications share one call-wide budget; report-local accounting still applies. The effective deadline is the earlier of the explicit timeout and shared deadline. Local unique-byte accounting is monotonic, including when the reused sealed-profile validator tries to restore its own active-memory counter in `finally`.

Historical callers supply capture metadata plus `archives`, a mapping from every original dependency path to its validated archived Artifact. The runtime validates the epoch archive before invoking this interface. Archives are treated as bytes and never imported or executed.

Historical validation binds `parameters_sha256` to the archived Engine, checks the report's own canonical parameter/input digests, native evidence, exact report/metrics/pair agreement, six detector row schemas, raw finite values and sealed decision use. It does not apply current parameter constants or call current scoring. Current admission continues to require both installed Engine identity and current score reconstruction. The historical interface is consumed only by the runtime's private historical evidence route; it cannot issue current readiness.

## Verification behavior

- Original report location is fixed to the bound audit's `logs/continuity/report.json`. Report and manifest shapes, version, algorithm, parameters, canonical input digest, scope, scene and domain are checked.
- `ColorAnalysisReader` verifies original source, sidecar, source/native frame mapping, processing commands, raw probes, tool identity and RGB files. The analyzer's `_resolve_manifest` verifies regions, declared context, native PTS, clip ownership, comparison endpoints and retained-frame mappings.
- Frame results are reconstructed from source evidence without decoding pixels. Comparison IDs, kinds, endpoint IDs, region ordering, coverage, evidence paths and producer audit are checked. Every persisted pair JSON and metrics JSON must agree exactly with the report, including JSON boolean/number distinctions.
- The six detector classes are checked against persisted measurement/trajectory scores for current admission. Formal profiles use the existing sealed profile validator and applicability logic. Fixture-only profiles and experimental/control manifest schemas cannot enter the ordinary report route.
- The report's original input file set is checked separately from deeper closure traversal. Context/profile/supporting JSON references are recursively followed, so a nested leaf remains protected even if the top report bytes stay unchanged. Every closure file is rehashed at the exit boundary.
- A call-wide timeout, 16 MiB single JSON bound, shared 64 MiB parsed metadata accounting, and the existing frame/comparison/color-reader resource limits apply. No process, logger, frame decoder, registration or feature extraction is invoked by validation.

## Zero-byte package inventory ruling

The installed NumPy RECORD contains actual zero-byte files, including `numpy/py.typed`, `numpy/compat/tests/__init__.py` and `numpy/core/_dtype.pyi`. VCO-03 fingerprints include them. Omitting them would change the prescribed dependency inventory; a byte-identical archive also necessarily contains empty copies.

The root implementer approved a narrow exception: RECORD-declared package files and their exact archived copies may have zero bytes. Other empty closure files require an already validated original CommandResult stdout/stderr reference. Reports, author JSON and ordinary submitted Artifacts remain nonempty.

## Executed RED/GREEN evidence

All commands used `. ./scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment`, then `Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',...)`, serially coordinated with the root agent. No full suite, GPU, model/network/service/SMTP action was requested.

| Run | Result | Bootstrap log |
| --- | --- | --- |
| `vco04-report-red`, `tests/unit/test_continuity_report.py -x` | exit 1; expected assertion that the readonly verifier module was missing | `D:/VideoSi/cache/video-ai/logs/vco04-report-red-de06612c1eb94f829b9506f3d7cb680f.log` |
| first `vco04-report-green`, same file | 4 passed, then a test helper passed a string to `hash_file`; corrected helper to construct Path | `D:/VideoSi/cache/video-ai/logs/vco04-report-green-344e5fbdb0eb42678c0ede406ba2df88.log` |
| `vco04-report-history-red`, `-k historical -x` | exit 1; expected rejection of a zero-byte RECORD archive before the approved exception | `D:/VideoSi/cache/video-ai/logs/vco04-report-history-red-5e67299b365a4cf3baf73217ab75309e.log` |
| `vco04-report-green`, complete file | exit 0; 7 passed in 38.33 seconds | `D:/VideoSi/cache/video-ai/logs/vco04-report-green-96fdb3162c3741bea25da6f200fefe2a.log` |
| `vco04-report-nested-red`, `-k context_nested -x` | exit 1; expected missing nested context leaf in closure | `D:/VideoSi/cache/video-ai/logs/vco04-report-nested-red-63d8a8280883451babe4b3418188fa3b.log` |
| `vco04-report-final-green`, complete file | exit 0; 8 passed in 44.84 seconds | `D:/VideoSi/cache/video-ai/logs/vco04-report-final-green-fccd07a5055844f69f9907baec03f306.log` |
| `vco04-report-upgrade-red`, `-k historical -x` | exit 1; expected rejection of archived history after current parameters diverged, exposing coupling to the installed score implementation | `D:/VideoSi/cache/video-ai/logs/vco04-report-upgrade-red-c28db76f28a945e488f8e48e7e68c98f.log` |
| `vco04-report-upgrade-green`, complete file | 1 passed then 1 failed; structural detector validator rejected legitimate repeated same-frame endpoints; corrected that rule | `D:/VideoSi/cache/video-ai/logs/vco04-report-upgrade-green-c5dbf75b9c96401aa21000d811be8417.log` |
| `vco04-report-upgrade-final`, complete file | exit 0; 8 passed in 47.03 seconds | `D:/VideoSi/cache/video-ai/logs/vco04-report-upgrade-final-ae08b73a221343948eb0477bbb47b04c.log` |
| `vco04-report-budget-red`, `-k budget` | exit 1; 2 expected failures: sealed-profile finally refunded the byte count, and the public validator lacked shared-budget support | `D:/VideoSi/cache/video-ai/logs/vco04-report-budget-red-23a5288c9bd64011830b2dbd79455d6d.log` |
| `vco04-report-budget-green`, `-k budget` | exit 0; 2 passed, 8 deselected in 0.18 seconds | `D:/VideoSi/cache/video-ai/logs/vco04-report-budget-green-733ea71954e247288e7cd66f0c9f93e0.log` |
| `vco04-report-budget-final`, complete file | exit 0; 10 passed in 46.92 seconds | `D:/VideoSi/cache/video-ai/logs/vco04-report-budget-final-45e3f400b026482ea2809ca3e93256ec.log` |

The positive test uses real small CPU FFmpeg/VCO-02 audit evidence and patches command execution and measurement to fail during verification. It snapshots the source and audit trees before and after validation. Rejections cover source edits preserving size/mtime, changed/missing pair files, changed PNG evidence, wrong producer audit, wrong bound manifest, unknown fields, boolean schema version, wrong native PTS, comparison mismatch, detector `passed`, build fingerprint drift, experiment/control/fixture schemas, deadline and Artifact hash/shape errors. Historical tests prove installation capture is unnecessary when archive metadata is supplied, then deliberately replace current parameters and make current scoring raise: archived historical validation still succeeds while current admission rejects the old report. Recursive context tests prove a deeper leaf is included and later byte drift is rejected.

No positive ready `purpose=real_benchmark` corpus was available in this task. Its existing sealed validator is reused; the test results do not claim production calibration acceptance.

The budget regressions use two-byte JSON documents with a three-byte budget to avoid a large benchmark corpus or large allocation. One invokes the actual profile validator wrapper while substituting its expensive inner corpus validation with a metadata read, then proves its `finally` assignment cannot refund the read. The other invokes the public report verifier on two different incomplete reports, proves both parsing attempts share the budget, proves a repeated path is not double-counted, and proves the shared deadline is respected.
