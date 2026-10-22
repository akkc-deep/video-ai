# JIM-08 Local Planner Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install the approved Qwen3 14B and bind new scene requests to it while preserving old 8B runs.

**Architecture:** Add optional raw configuration `scene_planner_model`, defaulting to `qwen3:8b`, limited to that model and `qwen3:14b`. The frozen raw configuration already binds request identity; request construction, injected planners and response validation must use that exact model. Preserve legacy intent/schema/settings shapes and all three previous wire variants.

**Tech Stack:** Python 3.12, pytest, PowerShell, local Ollama, existing JSON and HTTP evidence.

**Spec:** `docs/task-designs/JIM-08-design.md` and the approved upgrade proposal in `docs/task-designs/JIM-08-verification.md`.

## Global Constraints

- Git metadata is read-only; no checkout, branch, commit, worktree or push.
- Bootstrap and Initialize before each Python invocation; Python/media run serially; unique D-drive basetemp.
- Keep original input/PCM/subtitles, native16/cut/1080p, 32768 context guard and 8192 output budget, initial plus one correction.
- Default and old units/storyboard use 8B. Jimeng remains 4.0. No third requests to failed runs, unknown resubmission or fabricated acceptance.
- Credentials never appear in logs. Current-version bare full suite and source identity checks precede completion claims.

## Review Focus

- Unknown/null/legacy-strategy planner settings must fail locally, rather than being ignored.
- Wrong response model must not be accepted or authorize a correction.
- A saved plausible alternate model cannot rebind original HTTP evidence.
- Existing completed/interrupted 8B requests must replay with no extra HTTP despite new 14B configurations elsewhere.
- Model pulling must use an owned loopback server and D-drive storage without touching the foreign default service.

### Task 1: Configuration and model-bound adapter

**Files:** `src/video_ai/config.py`, `src/video_ai/adapters/ollama.py`, `tests/unit/test_scene_planner_model.py`, `tests/unit/test_ollama.py`.

**Interfaces:** `parse_scene_planner_model(value='qwen3:8b') -> str`; optional `model='qwen3:8b'` in `ollama_body`, `OllamaPlanner`, and model-bound response parsing (`expected_model` in `parse_completed_response`). 14B is valid only for scene requests; ordinary requests remain 8B.

- [ ] Write tests for explicit/default configuration, null/unknown rejection, legacy strategy rejection, 14B scene body with unchanged budgets, 8B ordinary body, exact response model binding.
- [ ] Run new tests RED; implement minimal parameter propagation; run new and affected unit tests GREEN.

### Task 2: Frozen scene model, installation and independent run

**Files:** `src/video_ai/runtime/production_scene_plan.py`, `tests/integration/test_scene_planning.py`, task-specific D-drive configuration, `config/README.md`.

**Interfaces:** Select model from frozen raw config with the parser above. Validate injected `OllamaPlanner.model`, reconstruct old wire with the frozen model, pass it to response validation. No schema/settings identity changes for old runs.

- [ ] Add RED integration cases for 14B initial/correction/replay, wrong-model refusal with no second POST, frozen config/intent mutation refusal, and preservation of existing 8B recovery.
- [ ] Implement binding; run affected integration and adapter/config modules GREEN.
- [ ] Pull qwen3:14b using an owned server bound to a free loopback port with `OLLAMA_MODELS=D:/VideoSi/models/ollama`; record exit/status/manifest and compare official metadata. Stop only the owned server.
- [ ] Prepare a new task-specific 14B config, preserving existing configs, frozen runs, image model, voice/media and text. Use public make-video in an independent run; record actual timeline/planning and cloud/selection gate outcomes without acceptance assumptions.

### Task 3: Verification and task record

**Files:** `docs/task-designs/JIM-08-verification.md`, task board, prepared full-regression script and runtime logs.

- [ ] Obtain an independent read-only review under requesting-code-review; address concrete findings with tests.
- [ ] Once source is stable, run `D:/VideoSi/cache/video-ai/logs/jim-08-grounding-full-regression.ps1` serially (bare pytest, verbose evidence, unique basetemp); verify exit, coverage, and before/after SHA.
- [ ] Record real model and human gates separately, continuing original JIM-08 acceptance only when actual selection/observations arrive. Do not mark JIM-08 complete from an install or test pass.

## Execution Ledger

Final bare suite completed09:55:56+08: **3651passed in20068.38s (5:34:28), pytest exit0**. Original prefix a1596fa456d04178b7cbbed7197dd9cc;378 files before/after identical. PowerShell runner exited1 solely because Group-Object node treated OrderedDictionary rows as a missing property and falsely grouped all nodes together. Preserve original error/result; independent Python audit `jim-08-root-final-full-audit-3605d610b6474dfb8cbfb8cbab6c9730-audit.json` verifies3651 unique passed nodes, raw output SHA, all378 current files and unchanged task config/script identities. Only runtime runner grouping changed to explicit scriptblock; full3651 OrderedDictionary rows reproduce original false group and corrected zero duplicates (`a1596fa4...-runner-grouping-audit.json`). No production/test change after full suite. Current JIM-08 staysIN_PROGRESS awaiting real batch2 choices, whole-group review and actual QQ receipt; no Wan/final/publication yet. Independent work finished; below are historical execution snapshots.

Fresh bare full suite started04:21:27+08, prefix `jim-08-grounding-full-regression-a1596fa456d04178b7cbbed7197dd9cc`. Stable source, unique basetemp, serial Python/media, all-node coverage and before/after identity checks required. Await actual terminal result; earlier partial rounds remain historical evidence only.

Latest: recovery regression47passed in333.38s, exit0 (`jim-08-reference-recovery-green-6e644e5b2421470fb7ca9f72a270b941.log`), including old/compact original-task recovery with expired inputs and mandatory submission-evidence safety. Incremental read-only review clean. Serial normal-TLS OpenSSL anonymous rangeGET at04:21:09 returnedHTTP403 for exact baseline object (`jim-08-anonymous-reference-openssl-db94d1b31d394bd39866523034a67f43-audit.json`); no ACL change or bucket-wide claim. Fresh full suite next; no Wan or human acceptance assumed.

Current recovery correction: full suite cdbc8ea5 stopped04:11:23 after248pass/1fail of3651 collected,378 source identities unchanged, no terminal completion. Existing expired-input-URL recovery and new compact equivalent both genuinely RED: requiring result unconditionally blocked original accepted-task recovery. Keep request/intent/submit-evidence/accepted mandatory; require result only when candidates manifest exists, validate any present result strictly. Without manifest/result query the original accepted task, no presign or submit. Read-only incremental review found no remaining concrete issue. Affected three-module GREEN running under prefix `jim-08-reference-recovery-green-6e644e5b2421470fb7ca9f72a270b941`; fresh bare full suite must follow. Real batch2 human gates unchanged. Earlier paragraphs below are historical snapshots.

Current: final reference repair28pass in228.64s, exact actual prompt799/784bytes≤immutable800. Same-run reference advance completed4 genuine outputs with verified TOS original and SMTP250 for batch2; exit3 awaiting_image_selection, user choices/group observation/actual receipt pending. New final bare suite started03:57:12+08, collected3651, prefix `jim-08-grounding-full-regression-cdbc8ea5bfb749eba2f52b22af35e98f`; no completion/pass claim until all nodes and identity checks finish. Native TLS anonymous-read probes unverified; defer proper OpenSSL read-only check until serial Python suite ends. Preserve all prior stopped/failed evidence.

Reference capacity repair: observed full prompt2548/2533bytes exceeded immutable800bytecap. Old build_reference_prompt stays exact; only a new unsubmitted scene whose full format exceeds cap attempts deterministic typed visual fields, all visual strings and owner associations retained, citations remain in original Bible. Already-persisted requests select only exact known formats; completed provenance requires all original request/intent/submit-evidence/accepted/result plus exact IDs/digests/task identity before any cloud operation. No model/cap/baseline switch. Read-only review's three concrete recovery/representation findings were RED-tested and fixed; final three modules28pass in228.64s. Actual frozen run official-function audit799/784bytes, samecap800. Public reference advance prefix `jim-08-real-reference-compact-4871591f6c064de49cbb7fdf489d6ffa` now running; final bare suite waits this serial real call ending. Earlier fresh full run59e3d586 stopped98pass/0fail before source repair;375-file identity unchanged and interruption retained, no completed suite claim.

Latest: first full suite interrupted after368pass/3fail,375-file before/after unchanged, no terminal pytest completion claim. Failure RED confirmed old local HTTP fixture parsed legal source-rules suffix as part of JSON; only fixture changed to raw_decode, original assertions retained,3pass. Fresh full suite started03:22:06+08 prefix `jim-08-grounding-full-regression-59e3d586f7964bb092797401ec59178d`. User's left baseline choice consumed via original CLI exit0. Reference advance stopped locally with prompt2548/2533bytes exceeding frozen800byte cap; no cloud/reference/Wan. Read-only repair design review pending; no capability expansion or prompt rewrite performed. Report only concise progress every30minutes per user's new preference.

Public CLI new transport first response accepted; run `20261021-014723-4ebdc1fecab2` exit3 awaiting_image_selection. Actual duration28.9375s; three shared-subject scenes/7 planned clips. Jimeng4.0 produced two actual2560x1440 PNG candidates, QQ SMTP250 accepted; human receipt/selection and TOS/Wan/final are still unverified. Fresh bare3630-item suite started01:50:35 +08 with375-file before snapshot, prefix `jim-08-grounding-full-regression-25bcafeba7a14b6eacef7ed1014deb8f`, pending results. No other Python/media while it runs.

Final affected regression after both review repairs: nine modules230pass in57.35s, exit0 (`jim-08-environment-final-targeted-3ee5bc7736714da3bc2f7de8bffefb3c.log`). Independent public CLI transport run `20261021-014723-4ebdc1fecab2` started with original14B config/v3 script. Full bare suite awaits this serial Python invocation finishing.

Ruling: Richer group feedback still failed in independent run `20261021-013014-60de3e1d11da` (exit2, 473frames/29.5625s). Repair the observed wire representation inside the same Ollama protocol: only when every nonempty paragraph has one finalized speech unit and scene count is fixed, require keyed scene slots, bind exact paragraph/unit coverage in the decoder, encode citations as source IDs expanded losslessly, and let each scene define an environment with current/prior sources or explicitly reuse a previous slot. No grouping/meaning invented by the decoder; canonical validation and all downstream records/gates remain. Multiple-unit paragraphs retain old wire. Preserve five historical/current wire families in exact recovery.

Environment transport RED2fail/4pass, unit GREEN31pass. Initial integration collection failed from duplicate test-module basename; rename integration module to `test_scene_environment_recovery.py`. Broad retry261pass/6setup errors exposed missing imported `production_config` fixture, then corrected import. The six cases subsequently passed; retain all failed logs.

Read-only review found an Important capacity/recovery defect: compact new format can fit while an earlier unused legacy candidate cannot. Genuine RED1fail/6pass (`jim-08-recovery-capacity-red-2d799f3a4062407bbef8d9d35a837f95.log`). Add `SceneCapacityError` only at existing full-input guard; skip only this error for historical candidate reconstruction and still require full body match. Real new requests retain guard. Related six modules150pass. Review follow-up confirmed fix and suggested explicit unmatched sentinel rejection; body=null RED1fail (`jim-08-unmatched-intent-red-704d2a6758af4dad944ca73c128e8407.log`), added `original_body is None` refusal. Final broader targeted run in progress; full bare suite and real transport run still pending.

Ruling: Execute inline under the user's explicit upgrade approval and existing completion request; the concrete scope was already presented and approved. Do not repeat a plan/permission ceremony. Use read-only review at the end; no implementer subagents.

Ruling: Use native Windows logs and file snapshots instead of skill git/Bash helpers because Git metadata is read-only and Python/media execution must remain serial.

Ruling: For the new 14B sample only, use closing_seconds=3 instead of the assistant-prepared 6.7: the same v3 narration most recently measured 33.6875s, so this targets 30s without cutting or speeding speech. All old configs/runs stay intact. This means the real run is not a pure timing-controlled model experiment; duration must be measured again, and no exact 30s claim follows from this estimate.

Task 1: RED6fail/8pass, then four affected modules97pass. Task 2 model binding: RED8fail/2pass, then eight modules202pass. Official 14B pull exit0 and all installed blob SHA verified. Read-only model-binding review found no concrete issue.

Ruling: The first real 14B run still emitted entity_00意图 references. Add lexical constraints for internal IDs to the outgoing wire only and exact available-key diagnostics to the original error; preserve four old/new wire variants and generic feedback replay. This is an observed defect repair under JIM-08, not another model switch or acceptance bypass. RED5fail, then nine modules246pass; seven extra historical replay cases added afterward await execution.

Ruling: User now explicitly accepts actual full duration ("不用严格是30秒，实际多长就是多长"); report the measured timeline and do not keep changing narration or frozen timing to reach exactly30s.

Ruling: After keys were constrained, the next initial proposal split the same environment into three groups; its generic correction merged all future actions into shared metadata. Add exact group-change feedback (first-use cutoff/eligible sources/old and proposed environment plus action-vs-location guidance), keeping rejection semantics and historical generic replay. RED1fail, four modules129pass; saved-proposal budget32510/32768 verified locally. One extra generic-group replay test awaits execution. The next independent real run keeps the same config/text; no third attempt on either failed run.
