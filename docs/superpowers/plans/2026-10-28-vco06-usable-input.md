# VCO-06 usable input implementation plan

> **For agentic workers:** Use superpowers:executing-plans task by task. Preserve this checkout's existing work; `.git` is read-only.

**Goal:** Deliver an actual, reproducible VCO-06 research input, with verified Wan origin, complete native frames and an ordinary full-sequence report; continue to enforce the separate candidate qualification and playback gates.

**Architecture:** A research-only importer verifies the existing direct Wan transaction and VCO-02 records, copies evidence into a new locked run, and seals a research context. A separate schema2 report reuses unchanged ordinary geometry while storing comparisons once in bounded shards. Natural patch metrics are diagnostic until independent qualification exists.

**Tech Stack:** Existing Python 3.12, NumPy, OpenCV and FFmpeg; no installation.

**Spec:** `docs/task-designs/VCO-06-natural-input-design.md`

## Global Constraints

- Preserve legacy v1, sealed r2 and old failures; no changes to calibration-frozen software.
- No new model requests for importing or measuring the two existing materials.
- Native 16fps, all frames/PTS, independently selected sRGB reference; no production eligibility.
- Per JSON 16MiB; live metadata 64MiB; deduplicated JSON input 256MiB; 300s operation deadline.
- Do not invent playback or natural labels, numerical thresholds, production clip records or a narration timeline.
- Full repository regression remains VCO-08. Run focused tests and relevant compatibility checks here.

## Review Focus

- Edited local index cannot hide a second POST or substitute a graph/input/output; derive transaction inventory from the original run.
- Import recovery must revalidate source and retained bytes, including after copy interruption.
- Full report must include the first reference comparison and every failure; reject any missing/reordered/foreign shard.
- Candidate qualification cannot become true merely because import or diagnostics succeeded.
- Old production entrypoints reject research configuration before services or external effects.

### Task 1: Transaction verification and research import

Files: `runtime/research_material_records.py`, `runtime/production_research_material.py`, `scripts/scene_research_material.py`; tests `tests/unit/test_research_material_records.py`.

Interfaces: `verify_wan_material(index_path, *, config, timeout=300) -> dict`; `import_research_material(request_path, *, paths, logger=None, timeout=300) -> dict`; `load_research_material_context(run_dir, *, reader=None) -> dict`.

- [x] RED: missing implementation; source graph/client/output mismatch, duplicate POST, identity drift, incomplete/native-time analysis, recovery drift and no-profile state assertions.
- [x] GREEN: verify complete original HTTP inventory, template parameters, model stamps, frozen options/manifest, successful history and exact selected/model-input bytes; validate VCO-02 read-only evidence. Exclusive copy/commit/new research options under held RunLock. No production freeze or fabricated script.
- [x] Verify: focused pytest and actual paper-material import/status; repeat status and compare original identities.

### Task 2: Full-sequence sharded report

Files: `media/research_pair_report.py`; tests `tests/unit/test_research_pair_report.py`, `tests/integration/test_research_material_flow.py`.

Interfaces: `analyze_research_pairs(manifest, *, config, paths, logger, timeout=300) -> tuple`; `validate_research_pair_report(path, *, manifest, config, timeout=300) -> dict`.

- [x] RED: full F-1 adjacent plus F reference coverage, deleted/reordered/foreign shard refusal and >16MiB aggregate with bounded independent shards.
- [x] GREEN: reuse ordinary measurement and geometry with original parameters; compact JSON root/shards, all coordinates/reasons, source/tool identities and explicit research schema.
- [x] Verify: run focused CPU flow and actual 49-frame report; retain all incomparable results.

### Task 3: Natural diagnostic baseline and guarded qualification state

Files: `media/natural_color_repair.py`; tests `tests/unit/test_natural_color_repair.py`; actual result in the new research run.

Interfaces: `natural_patch_features(reference, current, coordinates, regions) -> dict`; unqualified proposal reports `awaiting_qualification`, never renders media.

- [x] RED: constant color versus high-frequency texture, complete 9x9 support, fixed coordinate reuse, no-profile refusal.
- [x] GREEN: implement declared linearRGB median/log2 statistics, preserve raw RGB diagnostics and full-frame support failures.
- [x] Verify: CPU baseline on the actual reference comparisons, no threshold fitting or manufactured labels.

### Task 4: Task delivery and review

- [x] Expose import/status/analyze commands; production configuration guard and compatibility tests.
- [x] Produce one exact input index with run/commit/report identities and runnable commands; explicitly distinguish research_input_ready from ready_for_propose.
- [x] Review all changes in fresh context, fix important findings with RED/GREEN tests. Preserve archive, verification and implementation ledger.
- [ ] Resume independent qualification and candidate work only when the prerequisite protocol, data and actual playback evidence exist. Missing empirical evidence remains a real gate, not a default value.

## Verification command

Dot-source `scripts/bootstrap.ps1`, call `Initialize-VideoAiEnvironment`, then `Invoke-VideoAiNative $VideoAiPython` with `-B -m pytest`, the four new test files, relevant configuration/continuity compatibility tests, unique `D:/VideoSi/cache/video-ai/temp/` basetemp and external pytest cache. Record each RED/GREEN exit code; no commits in this restricted checkout.
