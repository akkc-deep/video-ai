# LVA-05 Implementation Plan

> For agentic workers: use superpowers:executing-plans, with test-driven-development.

Goal: implement the existing LVA-05 contract as independent experiments; obtain concrete authorization before real GPU measurements.
Spec: `docs/task-designs/LVA-05-design.md` (read completely).

## Constraints and rulings

- Keep old production, schemas, workflows and accepted roots untouched. Existing uncommitted LVA-01–04 dependencies must remain available; work in the supplied v1 checkout, creating only LVA-05 artifacts. No commit/push.
- Serial default; prefetch 48MiB source + 16MiB graph, writeback 32MiB, combined <=96MiB. CPU workers hold pure data only. Coordinator owns HTTP/evidence/promotion.
- No GPU, new models or production restart until a concrete manifest/commands/sample bound have been presented and authorized. No repeated decoding just for reporting.
- Existing implementation-ready design governs behavior. User's “完成任务LVA-05” authorizes implementation without another design approval round.

## Tasks

- [x] 1. RED unit tests for slots/backpressure, strong identity, budgets, worker context and late staging. Implement immutable jobs/config and bounded `UpscalePipeline` using existing read pool.
- [x] 2. RED integration tests using real PNG and fake HTTP with original `ExperimentClient`. Implement frozen identity, original-ID recovery and coordinator receipts/promotion; cover interrupted staging, complete replay, and drift before POST.
- [x] 3. RED encoding tests. Implement fixed libx264/NVENC commands and read-only capability check, one decode per output, pixel/PTS/color comparison and explicit rejection.
- [x] 4. Run prescribed targeted/offline checks, inspect results, prepare exact GPU manifest and bounded owned observer commands. Record actual evidence and remaining GPU/human gates; leave task IN_PROGRESS until satisfied.
- [x] 5. Authorized real serial/prefetch/writeback matrix, fixed-materialization encoding comparison and original-ID recovery complete. Prior genuine source quality preserved by full ordered RGB identity; no new quality decision fabricated. Default adoption rejected from actual mixed/local results; NVENC rejected on pixels, combination untested. Record completion, then prepare successor.

## Progress

- Completion recorded: 12 measured phases/4272 unique GPU frame requests, full RGB matches; actual completed recovery12/12 zeroHTTP/media/GPU. NVENC actual native encode ran but93/93 decoded RGB differ; original software encode still works and matches prior accepted video. Final98 targeted passed/9.51s, five old fixture failures remain disclosed. 12 measured owned services exit0/finalized, no remaining originalPID or8189 listener. Evidence `LVA-05-results.json/.md`, `LVA-05-gpu-results.json`, `LVA-05-gpu-recovery.json`, `LVA-05-completion.json`; no default change, new human decision, promotion or production restart. Task board IN_PROGRESS -> COMPLETED precedes successor design/preparation.
- Requirements-review ruling for the negative branch: design permits “无可重复改善保持默认 serial，交付否决也属明确实验结果”. If the final I/O matrix is rejected for no reproducible benefit and full ordered RGB equals the previously genuinely accepted source, retain that source acceptance as content provenance, claim no new viewing/decision, create no quality-accepted files and do not combine/promote. NVENC pixel rejection does not require viewing, since viewing is explicitly conditional on its technical contract passing. This is a documented interpretation, not invented user acceptance; an advancing/promoted candidate still needs genuine quality/adoption gates. Independent reviewer confirmed this distinction. Final decision awaits remaining actual data.
- Live execution: startup Path conversion and owner-before-listener readiness defects were corrected RED→GREEN (8 focused observer/lifecycle checks). Failed setup roots -01/-02 are retained; neither submitted inference. Revised execution manifest `LVA-05-execution-manifest-v2.json` keeps all source/model/workflow/parameters and sample caps, binds corrected code to new -03 roots under the existing authorization. Low-serial completed 372 frames/501.4124156s, all full RGB equal accepted originals; owned service exited0/finalized. Raw results `LVA-05-gpu-results.json`, current phase/state `LVA-05-gpu-run-state.json`. Continue same authorized serial/individual matrix; no extra permission required.
- GPU authorization received: user replied “同意” to the concrete 5,696-frame +12 encoding-pair request. This authorizes the exact prepared manifest SHA `9cef6989ed1133e41e8ed5151a7f04414c7a629f39c510a26fb52e4bf658cd96`, original accepted inputs, existing model and new LVA-05 roots. Proceed with serial/individual factors; combination still requires actual single-factor technical and genuine quality acceptance. No repeat permission request for these authorized measurements.
- 2026-11-16: read full design, linked handoff, predecessor completion and existing protocol/pool. Observed task READY. Explicit start: user “完成任务LVA-05”. No LVA-05 GPU authorization supplied.
- Final targeted suite 96 passed /9.36s. Legacy flow attempted separately: five pre-existing fixture path-policy setup failures; reported by name, not repaired outside scope. Final CPU/fake-HTTP four-factor/four-repeat benchmark and real software encoding fixture passed. Original workflow SHA unchanged.
- Independent reviewer found five important I/O/launch/lifecycle issues. Focused RED→GREEN regressions and final targeted run cover the corrections; no additional important blocker in follow-up. See `LVA-05-review.md`.
- Ruling: source preparation must supply the new owned input, not merely warm the original disk cache. Effective tools must come from admitted Artifacts, and a Windows Job must cover the pre-owner crash window. These preserve the established design and remove redundant verification/work.
- Exact GPU plan prepared, not executed: 16 phases at most, 5,696 frame requests, 12 paired encoding materializations. Task stays IN_PROGRESS, no successor handoff, no production restart. Next required input is explicit authorization for `LVA-05-experiment-manifest.json`; afterwards real measurements and genuine quality gates remain.

- Successor preparation complete after current-task completion: LVA-06 detailed design linked; fresh builder “nothing important left”; exact next-task handoff linked, NOT_STARTED -> READY. No LVA-06 implementation/tests/GPU started; no authorization inherited.
