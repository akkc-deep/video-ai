# Portable video storage implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Default to E:/VideoAI, keep shared dependencies separate, and allow all process data for one video to be deleted without affecting its deliveries.

**Architecture:** A single runtime layout resolver supplies Python and PowerShell with the same configured root. VideoStorage retains numbered videos, revision recovery and lifecycle locking, but allocates bundles under work and deliveries under output. Internal revision folders may remain nested to preserve recovery semantics.

**Tech Stack:** Python standard library, PowerShell, pytest.

**Spec:** User-approved layout in this conversation: shared/{models,tools,envs,config,assets}, work/<number-title>, output/<number-title>/vNNN, scratch; default E:/VideoAI.

## Global Constraints

- Source root is detected from the checkout; no fixed drive requirement.
- A video bundle owns its inputs, audio, images, clips, frames, render temporaries, service temporaries and records, including every revision.
- Model weights and interpreters never live in disposable caches.
- Published deliveries remain readable after removing the work bundle.
- No extra model hashing, media decoding or per-frame checks during generation.
- No model downloads, real video generation, or deletion of user data during implementation verification.

## Review Focus

- Configured roots with spaces and a drive other than D work in both launchers.
- Cleanup refuses active tasks, outside paths and redirected directories.
- A delivered video's whole bundle can be removed while final bytes remain intact.
- Recovery and managed-output recognition follow the new directory structure.
- Tests and service temp files cannot spill into shared dependencies or another video.

### Task 1: Unified runtime layout

**Files:** src/video_ai/runtime/paths.py, src/video_ai/config.py, scripts/bootstrap.ps1, installation and launch scripts, config examples.

**Interfaces:** Central root and category resolution; default E:/VideoAI, optional process environment VIDEO_AI_RUNTIME_ROOT; SOURCE_ROOT derived from the module checkout.

- [ ] Add failing tests for default/configured roots, spaces, category confinement and source-root detection.
- [ ] Run the focused path/config tests to establish failures.
- [ ] Replace hardcoded runtime/source roots and D-drive checks with layout-derived paths; align PowerShell startup, tool installation and config generation.
- [ ] Run path/config/bootstrap and installation tests.

### Task 2: Self-contained video bundles

**Files:** src/video_ai/runtime/storage.py, runtime/storage_files.py, runtime/service_specs.py, runtime/services.py and generation modules identified by path searches; tests/unit/test_storage*.py.

**Interfaces:** VideoStorage.video_dir returns <root>/work/<number-title>; output_dir returns <root>/output/<number-title>; managed_location and managed_output recognize revision paths beneath work. Index and sequence live in shared/config/storage, rebuildable service caches in scratch.

- [ ] Add failing synthetic lifecycle tests for the new locations, revision recovery and retained deliveries.
- [ ] Update allocation, recognition, output publication and cleanup boundaries together.
- [ ] Route task-specific Comfy inputs/output/temp/user and subprocess temp/cache/logs into the bundle; restore process environment after use.
- [ ] Remove production requirements on hardcoded historical run artifacts, replacing necessary capability records with configured shared resources or clear setup errors.
- [ ] Verify close/clean refuses active bundles and removes all process bytes while retaining final deliveries and shared dependencies.

### Task 3: Entry points, documentation and regression verification

**Files:** README.md, config/README.md, docs storage documentation, scripts, tests fixtures and integration tests.

- [ ] Update fixtures for the new structure without weakening cleanup safety assertions.
- [ ] Document root selection, new-video/resume usage, and close/clean preview and execution commands.
- [ ] Search executable code and launch scripts for remaining old absolute paths; classify historical documentation separately.
- [ ] Run focused storage/isolation/recovery/launcher tests, then the offline suite if available; report actual results and unavailable external services.
- [ ] Review the final diff for directory escapes, service ownership and delivery independence. Do not create runtime directories outside the workspace or delete existing data during validation.
