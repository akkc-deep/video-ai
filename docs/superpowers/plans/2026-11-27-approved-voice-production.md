# Approved voice production implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. User explicitly requested direct completion without further design questions.

**Goal:** New videos generated through make-video use the approved reference narration automatically.

**Architecture:** Freeze the approved recipe and voice assets in each run. Generate paragraph-sized speech through the owned persistent VoxCPM2 service with reference+prompt conditioning, process tempo once and apply one global gain. Use a local timestamp predictor on the processed speech to split actual audio back into the existing canonical subtitle/visual units. Existing frozen GPT runs retain their route.

**Tech Stack:** Python, VoxCPM2, FFmpeg, FunASR local timestamp prediction, existing production state/checkpoints.

**Spec:** `docs/approved-narration.md`, user instruction: “你直接弄好”.

## Global constraints

- Preserve the exact approved reference, prompt transcript, seed 42, cfg 2, steps 20, atempo .95, paragraph silence top-up 850ms and whole-narration RMS -23dBFS.
- No per-paragraph emotion directions, pitch shifts, hum or background sound.
- Real sample boundaries after processing; no timestamps estimated from character counts.
- Preserve historical runs and completed requests, stop only the owned service, never fall back to GPT.
- Work in the existing v4 checkout because required 01–06 modules are uncommitted here; do not move, reset or commit the user's existing work.
- Keep verification focused; no full video render required for a speech-entry change.

## Review focus

- Resume after accepted generation but before the client saves its WAV must query the same request ID.
- Interrupted processing must reuse generated paragraph WAVs and completed production checkpoints.
- Long paragraphs and punctuation-only spans preserve source coverage.
- Subtitle/shot splitting must not alter the concatenated waveform or add pauses twice.
- A mutable global default must not change a frozen historical run.

## Task 1: Frozen recipe and engine conditioning

Files: `tts_config.py`, `config.py`, `voxcpm/engine.py`, `voxcpm/contracts.py`, `adapters/voxcpm.py`, `runtime/production_inputs.py`, `runtime/service_specs.py`; test `tests/unit/test_approved_voice_production.py`.

- [ ] Write failing tests for approved recipe parsing, exact raw conditioning text and run-local asset freeze.
- [ ] Run the targeted tests and observe the missing-feature failures.
- [ ] Add an explicit inline narration recipe to TTS settings; freeze assets per run, include recipe identity in request binding, implement reference+prompt generation.
- [ ] Run targeted tests plus existing backend/assets/production-input regression tests.

## Task 2: Paragraph production, recovery and real alignment

Files: new `runtime/production_vox_speech.py`, `media/speech_alignment.py`, `scripts/align_narration.py`; modify `runtime/production_speech.py`. Tests: `tests/unit/test_approved_voice_production.py`.

- [ ] Write failing tests for paragraph planning, audio-derived cuts and repeat invocation without regeneration.
- [ ] Add the approved production route using durable paragraph checkpoints and the existing Vox task protocol.
- [ ] Process each fresh raw paragraph with atempo .95 once; assemble using existing silence top-up/global gain helper.
- [ ] Run the local timestamp model once per generated paragraph, map measured token boundaries to canonical source units, and save continuous PCM slices and envelope checkpoints.
- [ ] Run focused production speech/timeline regressions; historical GPT path must pass unchanged.

## Task 3: Activate and verify the actual entry

Files: runtime `shared/config/production.json`, default preset, docs, `AGENTS.md`; add reproducible production speech smoke script/report.

- [ ] Activate the approved inline recipe in the actual default production config, with no extra user command required.
- [ ] Run one short real GPU production speech and timeline sample, then resume it and confirm no new generation requests.
- [ ] Run related checks, review the change with a fresh reviewer, fix substantive findings and document actual evidence.
- [ ] Update documentation and report the saved output and the normal entry behavior.

## Ledger

- Ruling: use the current v4 checkout, retaining all uncommitted dependencies; no branch/commit operations are required.
- Ruling: local timestamp prediction is required for timeline compatibility, rather than changing the chosen paragraph delivery or estimating times by character count.
