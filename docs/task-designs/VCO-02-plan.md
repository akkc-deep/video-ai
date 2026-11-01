# VCO-02 implementation ledger

Authority: `docs/task-designs/VCO-02-design.md`; board: `docs/task-handoffs/video-continuity-optimization-task-board.md`.

- [x] 1. Pure parsing, PNG metadata and unchanged legacy probe contract, RED then GREEN.
- [x] 2. Strict entries, frozen source/evidence/tools, independent audit sidecars and bounded commands.
- [x] 3. Explicit zscale analysis frames, persisted-sidecar validation and ordered chain diagnostics.
- [x] 4. Real CPU fixtures: ranges/transfers, compression controls, five stages, source immutability and failures.
- [x] 5. Targeted regression, fresh review and verification report; full suite moved to the last project task by explicit user instruction.
- [x] 6. Close VCO-02 only, as requested; preserve successor state and links without starting or designing it in this closeout.

Pre-flight: parser output is consumed by sidecars; sidecars and frozen probe evidence are consumed by decode; chain consumes both. Shared schema/unknown rules are fixed in the design. No conflicting interface found.

Ruling: keep implementation in the existing workspace and retain this ledger — the task design explicitly requires preserving uncommitted predecessor inputs and forbids writes to read-only .git; no worktree, commit or cleanup scripts that mutate git will run. No change to production inputs.

## Evidence ledger

- Parser RED: `vco02-red-parser-409ee6ae03b2493fa28090c50e179caa.log`: 7 expected failures for missing interface. GREEN: `vco02-green-parser-2c044037315d4642be4611573e48905c.log`: 7 passed.
- Audit/decode RED: `vco02-red-audit-ebfb7386e6534867ba07099e74885ca1.log` and `vco02-red-decode-f354b6d7e85b440586a74185c63cfcdc.log`: runtime interface absent. Real decode GREEN: `vco02-green-control-2d89c5824c8847c29013fc9aed148238.log`: 6 passed.
- Unrelated mapping proof RED: `vco02-red-chain-4583eb52c8594b7da757df79a438679c.log`; all initial controls GREEN: `vco02-chain-controls-6acfa09048c44d779daf70ff86c3e4e8.log`: 29 passed, 120.19s.
- Timeout/malformed-frame RED: `vco02-red-failures-a0da4feb0e304c5ca31f3831a78e814e.log`: 5 failures; GREEN unit run: `vco02-green-failures-6176d5ec2ae949c08fee6af1f37af6ea.log`: 28 passed.
- Fresh read-only review by `/root/vco02_review`: six Important findings (partial frame-only metadata, native-tail proof, nested/persisted sidecar proof, processing input SHA, recorded edges, final-video provenance), all addressed in code/tests; unsupported PNG format classification treated as required behavior and fixed too. No deferred finding.
- Strict-sidecar RED: `vco02-red-strict-sidecar-5cc761f1548a446a8475e314a37f2662.log`: analysis_space/risk mutations escaped; partial-tag RED: `vco02-red-partial-tags-2e015ddabafa4fe4a40dbc1aa5f87ded.log`. Subsequent GREEN: `vco02-green-strict-86c72c33ef1140cdab7106c30b120831.log`: 45 passed, 2 deselected.
- Traceable five-stage and roundtrip controls: `vco02-proof-controls-1a702c28e101448fbe215663aea13be1.log`: 2 passed, 90.69s; unit hardening: `vco02-hardened-unit-3d568f26bde14773be5fc970f0e8c175.log`: 32 passed.
- Independent BT.709 chroma coefficients, legal/full ranges and RGB tolerance 2: `vco02-color-patches-3e38d1b1d0cb4fdc9d945dff7d3404ba.log`: 2 passed, 4.47s. This tolerance applies only to the lossless synthetic fixture.
- All log basenames above are under `D:/VideoSi/cache/video-ai/logs/`. Real fixtures showed that generic FFmpeg color options alone omitted primaries/transfer in this build; fixtures now declare input characteristics and x264 VUI explicitly. Parser correctly retained unknown before that fixture correction.

Ruling: freeze the actual zscale BT.1886 display convention and explicit normalized mapping export contract in the design — required to make analysis reproducible and SHA-bound without inventing production provenance. These conventions do not establish real-camera intent; unsupported promotion/model records remain unknown.

- 2026-10-23 18:21 recovery: original full-suite worker no longer exists; its log ends at 412 passed, zero observed failures, with no summary/exit_code. This is incomplete verification, not a successful full run. Rechecked all 375 frozen source/test/script files: zero changes (`vco02-recover-check-9d9df8b2ba2b4ba99e00e329b41d991d.log`). Started a new bare full-suite attempt using the hidden finite helper `D:/VideoSi/cache/video-ai/temp/vco02-full-retry-6c75e743.ps1`; durable status at `D:/VideoSi/cache/video-ai/logs/vco02-full-retry-6c75e743-status.json`. Original evidence retained; task remains IN_PROGRESS.

## Closeout — 2026-10-24

- User instruction: “最后一个任务再做全库回归，这个任务完成的话收尾吧”. This supersedes per-task bare-full-suite timing and limits this turn to VCO-02 closeout.
- The running helper and Python workers were stopped after verifying their recorded start times and process names. `taskkill /T` was denied; native `Stop-Process` successfully stopped the three owned PIDs. Status is `deferred_by_user`; no automatic restart. Last partial outcome: 700 passed, zero observed failures/errors, no full-suite success claim.
- Final verification: 166 targeted checks + 2 independent color-patch checks passed with exit 0. 375/375 frozen source/test/script identities unchanged; no added files in those sets. Evidence: `D:/VideoSi/cache/video-ai/logs/vco02-closeout-d51fe33e30e64759a94b7d716b341685.log` and `vco02-closeout-identity-20261023.json` in the same log directory.
- Completion is supported by all four outcome-level acceptance mappings in `VCO-02-verification.md`. Full regression remains pending for the project's last task. No VCO-03 design, implementation or handoff is created in this closeout.
