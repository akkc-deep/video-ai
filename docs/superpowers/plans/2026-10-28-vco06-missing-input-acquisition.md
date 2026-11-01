# VCO-06 Missing Input Acquisition Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. User explicitly asked the agent to supply the missing inputs; continue within the approved natural research design without another approval stop. Preserve this dirty checkout; no .git writes, new dependencies or full suite.

**Goal:** Supply a preregistered collection of new real Wan videos, explicit control recipes and a usable full-playback observation intake instead of asking the user to find datasets.

**Architecture:** A new independent acquisition module creates eight authored, explicitly sRGB reference scenes and freezes 24 exact requests before any model submission. Three seeds per scene remain one group, with four groups per split. All outputs and unsuccessful attempts remain in the denominator. Existing Wan clients, frozen inputs, source verification and research import remain authoritative. A separate observation portal records actual playback and explicit author judgments; missing judgments stay unverified.

**Tech Stack:** Existing Python 3.12, NumPy/OpenCV, stdlib PNG encoding, local Wan/ComfyUI, FFmpeg and browser HTML. No installation.

**Spec:** docs/task-designs/VCO-06-natural-input-design.md; docs/task-designs/VCO-06-natural-qualification-protocol.md.

## Global Constraints

- New collection only, 24 requests maximum, 8 scene groups, 12 complete 49-frame 768x432 native16 outputs planned per split. No automatic replacements or retries.
- New references are authored sRGB rendered still lifes. This is an engineering choice after public downloads failed and local photos lacked color declarations. They are not natural photographs; qualification cannot claim photographic/general-domain coverage. Actual unmodified Wan outputs can be studied for naturally arising reconstruction/color errors; no positive or improvement label is assigned by construction.
- Each scene has distinct geometry/material/layout. Same reference or related variants never cross splits. Reference creation/inspection precedes new outputs; holdout output metrics/inspection remain unavailable to calibration until seal.
- Collection manifest freezes all reference hashes, source renderer, config, template/model identities, seeds/prompts, group/split, budgets and controls before submission. Future videos are not represented by invented identities; collection.FROZEN is not inputs.FROZEN or protocol.FROZEN.
- Keep original paper/cloth/old24 excluded from new holdout; retain historical artifacts unchanged.
- No artificial color shift in acquisition. Controls stay separate and cannot count as natural positives. No qualification/profile/candidate without real evidence.
- One original POST per case; persist intent before starting service/submitting. Existing intent only restores original request via saved prompt; ambiguous requests never receive another POST. Stop the batch on unknown/execution failure. Tests and GPU work are serial.
- No new dependencies, production admission, publication, .git mutation or full suite.

## Review Focus

- Duplicate seeds/scene families/sRGB reference hashes across splits reject freeze.
- Frozen plan or reference drift blocks any service action.
- An interrupted request cannot be resent under a new run or replaced with a new case.
- Collection completion is technical acquisition only, not natural qualification; preserve null labels and all failed cases.
- Playback telemetry and frame coverage never manufacture a human's semantic judgment or accept unknown/partial playback as a valid natural label.

### Task 1: Immutable acquisition records and authored reference scenes

Files: src/video_ai/experiments/natural_acquisition.py, tests/unit/test_natural_acquisition.py.

Interfaces: render_reference(scene_index) -> uint8 RGB array; freeze_collection(root, config_path) -> dict; load_collection(root) -> dict. Freeze writes exclusive artifacts and exact 24 cases, returns Artifact-backed inventory. load checks all frozen identities before any action. Rendering uses known sRGB code values by authorship, with PNG sRGB chunk and receipt; never relabel unknown pixels.

- [ ] RED: split/group/count coverage, immutable freeze, drift, all reference hashes distinct, PNG CRC/declaration, fixed frame budget, unsafe root.
- [ ] GREEN: implement creation and validation. Root is a new explicit directory under D:/VideoSi/projects/video-ai/vco06-natural-qualification/.
- [ ] Verify unit tests through bootstrap and Invoke-VideoAiNative; preserve logs.

### Task 2: Real serial acquisition and technical source preparation

Files: src/video_ai/experiments/natural_acquisition_runtime.py, scripts/experiments/vco06_acquire.py, tests/unit/test_natural_acquisition_runtime.py.

Interfaces: acquire_case(root, case_id) -> dict; prepare_case(root, case_id) -> dict; collection_status(root) -> dict. CLI freeze/acquire/prepare/status. Reuse existing service ownership, template, exact submission, output validation, color analysis and research import. Each case has durable run locator and immutable generation request/result/source-index; status always lists all24 cases. Prepare does not run holdout natural metrics.

- [ ] RED: frozen drift before dispatch, repeated/unfinished intent refuses POST, complete result resumes read-only, status preserves missing cases/labels, CLI bad case.
- [ ] GREEN: adapt existing actual material generation sequence to the frozen cases. Keep one owned service per case, close it in finally. Technical preparation uses native all-frame VCO-02 and official verify/import, not fixture data.
- [ ] Run focused tests and relevant original source/CLI checks serially.
- [ ] Freeze actual collection before first POST, execute all24 cases serially, then prepare/import successful outputs; preserve failures and stop unknown cases without replacement.

### Task 3: Observation intake, controls and delivery

Files: scripts/experiments/vco06_observe.html, docs/task-handoffs/VCO-06-missing-input-delivery.md, current continuation results.

- [ ] Supply browser file-based playback/observation intake with actual frame presentation tracking, no seeking/hidden-page passes, explicit source/reference identity, reviewer/time/known-axis/target-intent and default unknown judgments. Save raw observation JSON only on explicit author action, never auto-mark passed.
- [ ] Freeze exact control recipe parameters with acquisition plan (identity, fixed inverse, wrong/over-correction, mixed/local/time-varying shifts, clipping and structure changes), separate from natural output counts. Controls are a frozen recipe, not proof of construction or observation.
- [ ] Deliver actual counts, artifact identities, reference-domain restriction, raw unknown/failed observations and concrete next executable step. Do not call it a qualified dataset or complete VCO-06 when observations/positive coverage are missing.
- [ ] Fresh scoped review via applicable requesting-code-review skill, fix material findings RED/GREEN, verify source preservation. No commit/branch cleanup.

## Execution ledger

- User: “你先把缺少的东西补上”. Existing generation authorization in approved natural input design remains applicable. This request prioritizes acquisition and usable observation infrastructure.
- Preflight: existing source verifier accepts real direct unparented Wan transactions; prior real49-frame requests took about3minutes. About195GB free measured. Public picsum fetch failed via PowerShell/curl TLS and Python timeout; all10 inspected ordinary wallpaper/photo references had no ICC/sRGB/EXIF declaration. Existing eight touchkeyboard refs have ICC but include related/seen families, so will not be recycled as independent new holdout.
- Ruling: authored reference renders define sRGB at creation and avoid false relabeling. Domain restriction is explicit; whether natural reconstruction biases occur remains empirical. Cost if this restricted domain yields no qualifying positives: honest unqualified collection, no automatic replacement generations.
- Pre-flight interfaces: Task2 consumes Task1 frozen case/reference identities; Task3 consumes Task2 actual outputs without natural metrics or automatic labels. No legacy frozen source edits are required.
- Records RED: 6 failures/9 missing-module setup errors, log vco06-acquisition-records-red-e4acade0e1284ef0aebecc2fc6eaf9ec.log. Initial GREEN revealed using the file-only local() validator on a directory; changed only directory validation to local(exists=False)+is_dir. Records15 passed, vco06-acquisition-records-green-fixed-c5c34b1b40e948ac9dea8f62888b1f8a.log.
- Runtime RED8: vco06-acquisition-runtime-red-2f749246fc854335bce81de80bfadf63.log. Combined35 passed, vco06-acquisition-combined-green-4ad4aa4ead984f53922ed5c869c80ee1.log.
- Independent read-only review found four Important issues: renderer provenance outside runtime, missing durable-acceptance recovery, insufficient completed source transaction proof/import status proof, and relocated relative configuration paths. All fixed before actual freeze. Runtime source archive is verified; original acceptance uses existing recover_http(durable=False) without POST; saved results require actual manifest/template/POST/history/output; recorded imports validate current official context; frozen config normalizes resolved paths.
- Observation review found four Important issues: missed pause/buffer events, validation/archive reread race and playback time ordering, normal Downloads path rejection, and premature holdout exposure. All fixed before actual freeze. Browser event regression uses installed Node and real HTML script with fake DOM; it is a software test, not actual video observation. Portal/intake now development-only; holdout requires separate sealed evaluation workflow.
- Review regression RED17 and RED9 preserved in vco06-acquisition-review-observation-red-d95a15ac189641f8a185aecd57ac5972.log and vco06-acquisition-review-fixes-red-9898a8adbc804f00ac8905c3a485b10b.log. Corrected two fixture gaps (missing case_id, legacy config instead of jimeng config), then confirmed three targeted behavioral failures in vco06-acquisition-review-red-fixture-corrected-c3a6c6b2e09f4feb9318f2de460f8e07.log; no test was changed to accept defective behavior.
- Final pre-acquisition61 passed27.10s, exit0, no skip: vco06-acquisition-review-fixed-green-c3a39ab0c31448c18813ad45373c5422.log. Tests: new acquisition records/runtime/observation plus original research_material_records and research_material_cli. Actual original real Wan transaction also passed the new read-only transaction verifier, vco06-acquisition-original-transaction-check-73e8dbaeedc94110a749da486f5e3241.log. No GPU request yet at this ledger point.
- Actual collection frozen at D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-acquire-62d31ee3276941ecb65e35e23e4db250; collection.FROZEN.json35818 bytes/SHA55d624f985b95dedae2aefdb99e2712d8a26edf20afb67335f43994f577e7d74. Freeze log vco06-freeze-new-collection-bbc63ec4edf24ddabee4b96d4edba7ee.log. All24 acquisition command is ACTIVE in exec session51041, log vco06-acquire-preregistered-24-bf326f52ebfe4a518113736ed068f18e.log. Do not launch another batch while it is active. First8 cases have emitted generated; read current log for progress rather than relying on this snapshot. Continue to all24, then run prepare --case all serially and export the development portal. No holdout natural metrics/visual review.
- Original568 protected files bytes/SHA/mtime and451 existing Python bytes remain unchanged. A repeated PowerShell nested-array inventory mistake falsely flagged source drift; retain preservation-before-checker-error.json, corrected preservation-before.json rechecks the original baseline and passes. No baseline refreshed.
- Pending post-GPU verification: added test_browser_counts_frame_zero_already_presented_while_paused to tests/unit/test_natural_acquisition_observation.py. It has NOT RUN; do not mix tests with active GPU inference. After acquisition finishes, run it RED, then make the smallest HTML-only fix if it reproduces missing already-presented frame0 (retain real RVFC metadata during paused preload and bind that visible frame at start). The HTML is not part of acquisition software hashes; do not modify any frozen Python module/CLI. Run the final relevant suite before exporting the portal.
- Plugin Management searches for video analysis / TwelveLabs / Gemini found generation/editing/public-video-analysis integrations, none of the returned connections supplied a usable installed local complete-video observer. No plugin installed, uploads made or semantic labels invented. Detailed delivery draft docs/task-handoffs/VCO-06-missing-input-delivery.md must be refreshed with actual final counts/commands/results before final response.
- Actual acquisition COMPLETED24/24, exit0; log vco06-acquire-preregistered-24-bf326f52ebfe4a518113736ed068f18e.log ends acquisition_complete and exit_code=0. No replacement or repeated prompt. GPU phase ended before tests resumed.
- Preloaded-frame0 regression reproduced RED1 in vco06-observer-preloaded-frame-zero-red-24d03b1d2427477cba4c7ba69a0f01c4.log. HTML-only fix retains real RVFC presentation metadata for the current source while paused and binds actual visible frame0 at start; no assumed frame or reduced coverage. Neutral label wording now requires affirmative color agreement rather than inability to see an issue. Current62 tests passed27.27s, vco06-acquisition-final-software-7863ccfc2fc842e89a125a8cf02ec350.log. Frozen acquisition Python/CLI/collection unchanged.
- Original frozen prepare branch failed before color inspection: mapping JSON under audit logs violated the unchanged colorimetry._audit guard. Failure retained in vco06-prepare-import-preregistered-24-8fdef5e628514c048f2caf71168b97ef.log. No movie/model failure, source-index or import was fabricated. Ruling: create versioned consumer adapter natural_material_preparation.py + vco06_prepare.py, save mapping under case/evidence, then reuse official prepare_case verification/import after creating a valid real all-frame source-index. Do not alter frozen producer source or refresh its SHA. Cost: original fresh-index prepare construction is historical; use v2 for new technical preparation.
- V2 RED3: vco06-preparation-v2-red-8ad15ae0c101400292257668b106e4ab.log. First combined run64 passed/1failed showed verified_at changed between repeated hash_file reads. Preserve the first source evidence timestamp and compare path/bytes/SHA/mtime for immutable reuse; no byte or mtime check removed.65 passed27.14s in vco06-preparation-v2-final-software-8228e2cc98584ce18e1dc66a5cb0714e.log.
- V2 independent scoped review found a cross-case resume binding gap. RED4 foreign valid transaction/index/config/completion cases in vco06-preparation-v2-binding-red-41201ab46a3145d79d170a73edfaab6a.log. Before official import, v2 now binds index request/result/reference, existing import request config/index and complete receipts to this exact case; afterwards it verifies the retained import result/current context/source/reference. Final69 passed28.09s, exit0/no skip: vco06-preparation-v2-binding-final-software-9eb09ac319844b0cb128534e611c65ac.log.
- Current ACTIVE operation is technical preparation/import only, exec session34839; vco06-prepare-v2-real-24-fb37f9b166e241ef815a5f6e53fcd62f.log. First3 real sources have emitted research_input_ready; read log for current progress. Do not rerun acquire or edit frozen modules. After prepare all24 exits0: export development portal via vco06_acquire.py portal, run root/tools/closeout_acquisition.py (new current helper, not archived code), write README/delivery docs, update VCO-06 blocker snapshot without transition, verify final identities. Actual natural observations remain0.
