# VCO-07 Task 3 implementation evidence

Scope: admission evidence, frozen input roles, execution-budget records, and conditional protected writer read windows. No archived runner execution, inference, network requests, dependency installation, Git changes, or production-media acceptance was performed.

## Interfaces

- `rendering_mode(frozen)` returns the explicit mode or `None` for either historical branch.
- `load_scene_execution(frozen, plan, timeline, *, reader=None)` returns the full validated budget. Explicit mode requires the persisted budget; historical mode derives an in-memory segmented view with zero writes.
- `ensure_scene_execution(..., *, lock, reader=None)` requires this run's held `RunLock`, derives the whole batch before writing, uses exclusive temporary creation, fsync and rename, and validates existing budgets without replacing them. A missing budget with downstream records, an unowned temporary, or an incomplete temporary is refused. An exact complete temporary belonging to the current lock can recover after interrupted rename.
- `execution_artifact(frozen)` returns the exact `production/scene-rendering/execution-budget.json` Artifact.
- `load_whole_scene_evidence(path, *, reader=None)` returns `root`, `assessment`, `case`, `graph`, sorted deduplicated `artifacts`, directory `inventories`, original `raw` root bytes, and a `guard` with `verify()`. The original pinned assessment and exact generated-run frozen copies with matching sibling closures are supported.
- `verify_whole_scene_frozen(frozen, *, reader=None)` rebuilds semantic evidence and the external closure, verifies exact frozen roles/paths, inventories, and current models/tools/Comfy/workflows. It returns the same evidence context with an environment guard attached to the main guard.
- `verified_scene_execution_write(function)` extends the existing `validation_session()` over an explicit writer invocation. Nested model digests are reused only while mandatory Windows read handles prevent modification. Historical branches retain their original direct invocation behavior.

Budget rendering identity is exactly `canonical_digest(identity_from_options(thaw(options)))`, using the default `reference_settings_sha256=None`; revision invalidation classification is a separate identity. Whole admission is the current run's frozen evidence Artifact.

## Admission and freezing

The accepted root remains `D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/final-assessment.json`, SHA256 `527f08dd69d51b4c7f176284a768dbf9387deb273d644244920be70c79fcb653`.

The reader cross-checks completion, final assessment, original user feedback and full `[0,320)` coverage, compatible/lossless/generated media identities, the original historical unverified technical result, 321 PNG identities, exact mapping, original intent and successful history, exactly one HTTP POST and its acceptance, all 1,874 valid resource records and their aggregate measurements, case/prepared/graph, source inventory, dependency identities, archived product source, and current/archived Comfy source. Historical product code is never executed and is validated against its archive rather than today's changed implementation.

The compatible playback producer was recorded after the initial software archive: its independently recorded immutable experiment-module bytes are verified at their recorded original path. The earlier archive remains independently verified; its differing bytes are not substituted for the later producer.

The original assessment links media and result bytes, while its resource summary contains aggregates rather than per-sample digests. To prevent replacing raw resource or HTTP records while preserving those aggregates, the implementation additionally pins the observed original inventories and the original case/prepared digests:

| Identity | SHA256 |
| --- | --- |
| Resources, 1,874 relative-path Artifacts | `7ec5ca3d2a05e552291d6af6784438a2281a20b82d893a5cf535287d20bb1cee` |
| HTTP, 11,205 relative-path Artifacts | `61930b293f761367e4012afa8f9fec6ac3e2d3912bc75f0dc4279d30e1fad76c` |
| case.json | `5eef75c3761994614053009a222cbd867ea2ff5ffdbf7bcf7894b82eada6a001` |
| prepared.json | `e58dcb08ed461ac3eec356b8384be064b60bbec492632048b7102c38add674af` |

Inventories use canonical JSON digests of ordered `{path,bytes,sha256}` rows with relative POSIX paths. JSON is bounded to 16 MiB and invocation metadata to 64 MiB. Large files use existing streaming protected hashes and ArtifactStamp checks; no size/mtime-only digest shortcut was introduced.

Whole freezing preserves original root bytes at `production/scene-rendering/whole-scene-evidence.json`. The exact closure is `{schema_version:1,algorithm:"whole_scene_admission_closure_v1",root,artifacts}` and both files have exact FileIdentity roles `whole_scene_evidence` and `whole_scene_evidence_closure`. An inherited frozen root alias is replaced with the target root, while the external evidence closure continues to anchor the original pinned assessment. Explicit segmented and both historical branches acquire no whole roles. Prompt schema/mode compatibility is checked while freezing and loading.

## Verification ledger

All Python invocations used `. ./scripts/bootstrap.ps1`, `Initialize-VideoAiEnvironment`, and `Invoke-VideoAiNative $VideoAiPython`.

| Check | Result | Log under `D:/VideoSi/cache/video-ai/logs/` |
| --- | --- | --- |
| Initial records RED | 3 failed: runtime module absent | `vco07-task3-red-d423b7c92365429482cd63a7fb6bd538.log` |
| Initial records GREEN | 3 passed | `vco07-task3-records-bbb7da52e3d5443988a050cab006894e.log` |
| Expanded evidence checks | 2 failures exposed unpinned raw resource/HTTP whitespace; corrected with original inventory pins | `vco07-task3-evidence-d525ff49694f4a2bba4fcfffc341e950.log` |
| Records + production inputs | 39 passed | `vco07-task3-evidence-93f4b7e27a494d0285c445d858554bf3.log` |
| Expanded records + production inputs | 44 passed, 63.14 seconds | `vco07-task3-final-d7789016e94d421b85d8f891327aaa97.log` |
| Writer scope RED | 1 failed: requested decorator absent | `vco07-task3-scope-red-77313e76ded24709ab7f453757a8a931.log` |
| Writer scope + expanded frozen/inherited-root round trip | 2 selected passed, 24.22 seconds | `vco07-task3-scope-green-9d62035426ad4796afee76710927dbb4.log` |
| Original raw inventory pin calculation | Exit 0, 1,874 resource / 11,205 HTTP identities | `vco07-task3-pins-dfc81469970f4974bfec4e3374d7ce3b.log` |
| Final real read-only evidence/environment audit | Exit 0, 18,453 deduplicated Artifacts, six inventories, pinned root and actual current models/tools/Wan workflow/mapping/Comfy checked | `vco07-task3-final-audit-4aa8b6f863824fb5875e8118a63254b6.log` |

The final audit script is `D:/VideoSi/cache/video-ai/temp/vco07-task3-audit.py`. Its current-configuration environment check supplies `advisory_v1` only in memory; it does not enable whole mode or modify production configuration. Earlier audit invocation corrections (PowerShell inline quoting and legitimate pre-service `pid:null` resource records) are retained in their command logs. Pre-service samples require empty process RSS; active samples require the recorded owned-process RSS.

`tests/unit/test_scene_execution_records.py::fixture_evidence(root, monkeypatch)` builds a protocol-only accepted-evidence fixture with 321 tiny PNGs and 1,874 resource JSONs, tiny software/model/tool files, exact linked records and the real graph validator. It patches only pinned identities. Integration callers with independently supplied model/tool config fixtures may explicitly patch `verify_current_environment`; the actual evidence validator remains exercised. The fixture is not a real visual observation.

The new VCO-07 product Python implementation is intentionally not compared with old VCO-05 product dependencies. Task3 does not create a separate current-product source-identity artifact. Root must record the current `src/video_ai` implementation, relevant scripts and workflows in a separate exact software inventory before real production validation and retain that inventory's Artifact in the verification/operations evidence. This is an outstanding operation-level record, not an admission equivalence check; no additional unreviewed frozen role or writer artifact was added here.

Remaining project work belongs to root integration/verification and actual VCO-07 acceptance. This report makes no production source-video, upscale, composition, final-observation or delivery claim.
