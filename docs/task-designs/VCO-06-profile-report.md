# VCO-06 sealed profile loader evidence

Implemented `_scene_color_repair_profile.py` without importing or executing the calibration experiment. `load_profile(path, *, reader)` returns the unchanged plain profile dictionary. `verified_profile(path, *, reader)` returns `(profile, closure)`, where closure is a sorted, unique list of exact `{path,bytes,sha256}` Artifacts. The records wrapper delegates to this loader.

Validation covers the exact profile schema and evidence-only identity; independent frozen-input and seal identities; original-index source equality; immutable protocol; current Python/NumPy/OpenCV versions and the full frozen software inventory; archived calibrator byte equality; 24 distinct sources/groups with the preserved 12/12 six-genre split; original source byte identities; independently stamped result files and matching source-pack metadata/bytes; native frame metadata and baseline eligibility; calibration-before-seal-before-holdout/evaluation times; sealed bounds; evaluation/profile equality; complete holdout case coverage and qualified-direction derivation. The existing optional original `control_targets` authorization variant is preserved and included in the closure.

All file hashing uses 1 MiB reads with deadline checks, including large original RGB receipts. Four/five-field historical identities are projected to Artifacts after validating bytes, SHA256 and optional mtime; `verified_at` is validated independently. Large result bodies retain their independently bound complete hashes. Bounded prefix/suffix metadata and selected scalar control summaries are parsed and charged against Reader's cumulative 64 MiB budget; bulk per-frame scores are skipped. No historical result is refitted or remeasured.

Tests use complete compact 24-source `fixture_only` closures. `tests/repair_profile_helpers.py:make_profile` shares that fixture with integration tests and supports an explicitly synthetic `green_axis=True` qualification variant. The fixture does not claim real media or calibration qualification.

Every Python invocation began with `. ./scripts/bootstrap.ps1; Initialize-VideoAiEnvironment '<label>'`. Pytest used `Invoke-VideoAiNative $VideoAiPython @('-m','pytest',...,'-q','--tb=short','-o','cache_dir=D:/VideoSi/cache/video-ai/pytest/vco06-profile','--basetemp=D:/VideoSi/cache/video-ai/pytest-tmp/<label>')`. Runs were serial under the root agent's test token.

| Label / check | Result | Log in D:/VideoSi/cache/video-ai/logs |
|---|---|---|
| vco06-profile-red / profile unit tests | 22 expected missing-loader failures | vco06-profile-red-60ca59e41dcf4b48895672c5afbf5c4c.log |
| vco06-profile-green | Import error from an unused helper import; corrected | vco06-profile-green-ab11442818b745928fd36223fbd0c266.log |
| vco06-profile-green2 | Fixture original index overlapped its study; corrected fixture layout | vco06-profile-green2-389da3de5cd64e3891b96e07e48fe014.log |
| vco06-profile-green3 | 22 passed | vco06-profile-green3-d35c6cb9c5f24043aa580d9216ea1283.log |
| vco06-profile-real-r2 | Found existing optional control_targets source variant | vco06-profile-real-r2-8783bb6eaf3e47bfa146510442e23a97.log |
| vco06-profile-control-red | Expected refusal of unsupported original control_targets variant | vco06-profile-control-red-bef5cdb1cd7249f1afecd1a39bbfd6bb.log |
| vco06-profile-real-r2-2 / read-only actual r2 verification | Passed: 12,004 closure Artifacts; 12,209,702 parsed metadata bytes; original four qualified directions | vco06-profile-real-r2-2-52455251f1a44e7190709264076d1491.log |
| vco06-profile-final / profile + numeric + existing calibration unit tests | 104 passed: 25 profile, 56 numeric, 23 calibration | vco06-profile-final-bbef01b08ce6455497d167e8ce4a156d.log |

The final tests include >64 MiB of independently hashed opaque result rows while charging <2 MiB of parsed metadata, stage-order rejection, same-size/mtime byte drift, original-source drift, forged qualification, missing software inventory, dependency-version drift, changed original index/protocol, inconsistent source-pack metadata, independent result identity mismatch and deadline expiry.

The fixture's initial `green_axis=True` integration extension landed after the first combined run; subsequent verification below covers both variants. Full-suite regression remains deferred to VCO-08. No commits, subprocess media processing, measurement refits, network or model calls were performed by this loader task.

## Review corrections

The read-only review in `VCO-06-numeric-profile-review.md` found four material gaps. Five adversarial tests first failed as expected in `vco06-review-red-d927aad04fad46648e8bd252c75592bc.log`: post-hash same-size/restored-mtime changes, duplicate identity mtime rebinding, widened declaration with all measurement bytes retained, missing calibration coverage and oversized frame materialization. Corrections rehash every closure dependency at closeout, reject changed duplicate stat identities, require calibration coverage, and reject frame counts before creating NumPy frame views.

The loader now streams exactly 74 saved control summaries per source, retaining only provenance/decision/amplitude scalar fields and lexically skipping bulk frame-score/fit values. It replays the original contiguous-level/max-amplitude bound reduction and holdout/context-count reduction from these unchanged saved summaries, then requires exact equality with the seal/evaluation. This is verification of recorded arithmetic closeout, not pixel fitting, remeasurement, recalibration or a new holdout evaluation. The compact fixture now contains all 74 original protocol cases per source; synthetic green-axis qualification is preserved.

`vco06-review-green-c0a4cd7ea5de4ef0a79e1b36d6ddd154.log` records 86 numeric/profile tests passing. Actual r2 was revalidated with streaming saved-summary replay and final byte rehash: 12,004 Artifacts, 12,723,957 charged metadata bytes, 105.11 seconds, original four qualified directions; raw log `vco06-profile-reviewed-real-r2-6c5f78548174402cbd0eea55df0a0f6b.log`. The final combined run additionally covers a coherent forged holdout-pass declaration and both fixture axis variants.

Final reviewed command: bootstrap label `vco06-reviewed-core-final`, pytest files `tests/unit/test_color_repair.py tests/unit/test_scene_color_repair_profile.py tests/unit/test_vco06_repair_calibration.py`, same options above. Result **111 passed in 22.24s** (57 numeric, 31 profile, 23 calibration). Log: `D:/VideoSi/cache/video-ai/logs/vco06-reviewed-core-final-a67983d8da154afc996e907c2ac3d015.log`.
