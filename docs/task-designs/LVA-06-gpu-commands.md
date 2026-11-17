# LVA-06 GPU commands

Prepared only. Execution requires specific authorization for this exact manifest. Old production stays paused.

Manifest file SHA256: `ba88dfc0950e905e527d73e11e8ddc660593540c78502588065403b35c779d26`

CLI canonical manifest SHA256: `c9f66424f4316c210a96d826f27b63c0c3f31986fcd3a62e52803a4c752953a8`

Pure plan SHA256: `220c087ed0a5a94ac8f5e1ff263dda522871ca6fb3424ca37efdf2c3474d7758`

Limits: 16 Wan requests; 1424 serial full-frame upscales; 12 libx264 medium/CRF18 compositions; 7 owned services.
No downloads, NVENC, fast mode, paid calls, production resume or duplicate baseline/final matrix.

Run low, high, chain in order; each command stops for genuine reviews and closes its owned service first.
After recording a decision, use the same original command/root to continue. Never create a replacement for an unknown request.

## low

Root: `E:\VideoAI\scratch\benchmarks\LVA-06-20261116-072639-e2a8e6-low`

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_final_local_video.py --run-batch low --plan docs/task-designs/LVA-06-experiment-manifest.json --authorize-plan-sha256 c9f66424f4316c210a96d826f27b63c0c3f31986fcd3a62e52803a4c752953a8 --output docs/task-designs/LVA-06-gpu-run-state.json
```

Native review gates: native, final.

## high

Root: `E:\VideoAI\scratch\benchmarks\LVA-06-20261116-072639-e2a8e6-high`

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_final_local_video.py --run-batch high --plan docs/task-designs/LVA-06-experiment-manifest.json --authorize-plan-sha256 c9f66424f4316c210a96d826f27b63c0c3f31986fcd3a62e52803a4c752953a8 --output docs/task-designs/LVA-06-gpu-run-state.json
```

Native review gates: native, final.

## chain

Root: `E:\VideoAI\scratch\benchmarks\LVA-06-20261116-072639-e2a8e6-chain`

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_final_local_video.py --run-batch chain --plan docs/task-designs/LVA-06-experiment-manifest.json --authorize-plan-sha256 c9f66424f4316c210a96d826f27b63c0c3f31986fcd3a62e52803a4c752953a8 --output docs/task-designs/LVA-06-gpu-run-state.json
```

Native review gates: parent, child_continuity, final.

## Record genuine review

Use the exact `review`/`media_artifacts` returned by the stopped batch. A decision file must contain task_id=LVA-06, kind, decision=accepted/rejected, the complete unchanged media_artifacts list and user_evidence quoting the actual user decision (preferably with time/message source). No generated acceptance file is supplied.
Use `--record-review DECISION_JSON --plan docs/task-designs/LVA-06-experiment-manifest.json --root EXACT_BATCH_ROOT`, then repeat the original run command. The same-media quality reuse is allowed only when explicitly granted by the user for these files.

## Recovery and summary

Replace `--run-batch` with `--recover` using the same fixture, manifest digest and output. Existing phase roots attach only to original IDs; stopped unknown diffusion is not restarted.
Read-only summary: `--summarize LOW_ROOT/batch-measurement.json HIGH_ROOT/batch-measurement.json CHAIN_ROOT/batch-measurement.json --output docs/task-designs/LVA-06-gpu-results.json`. This validates saved technical bindings and actual later final decisions; no service/HTTP/media generation.

All timing starts at a new actual selection handoff before preparation. Final review is separate; incomplete/rejected quality has null usable cost. Full 107-scene throughput remains unmeasured.
