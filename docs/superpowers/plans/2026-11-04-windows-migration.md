# Windows migration implementation plan

**Goal:** Export the installed video production stack and restore it on another Windows x64 computer with a D: drive, then offer the existing generation command.

**Architecture:** A PowerShell script copies the current working source, runtime tools, models, project inputs/configuration and orchestration environment into a directory bundle using Robocopy. It carries Python 3.12 itself and repairs the restored virtual environment, avoiding a dependency on the old Windows account or online package installation. Small CMD launchers provide double-click entry points.

**Constraints:** Keep canonical D:\VideoSi and D:\code\py\video-ai paths. Preserve current generation behavior. Do not run inference or repeatedly hash model files as migration checks. Include local service credentials privately without printing them. Do not overwrite an unrelated target installation by default. Do not modify existing development changes.

**Platform assumption:** Windows x64, local D: drive and an NVIDIA GPU/driver compatible with the bundled runtime. Hardware and driver compatibility cannot be provided by a file-copy script.

- [x] Add focused tests for copying paths containing spaces, native failure propagation, virtual-environment relocation, secret loading and refusal to overwrite unrelated installations.
- [x] Implement export/restore/generate in `scripts/migrate_windows.ps1`; export the base interpreter and preserve supplementary project resources needed by native video generation. Exclude ordinary runs/productions and temporary tool output unless history is requested.
- [x] Add `export_migration.cmd`, `generate_video.cmd` and `docs/windows-migration.md`; place a restore launcher inside each exported bundle. Carry the Microsoft runtime installer and install it only when missing.
- [x] Run focused script tests and PowerShell syntax checks. Used tiny fixtures; did not export hundreds of GB or run video generation during development. Result: 19 migration/bootstrap tests passed; PowerShell parser passed. Verified the actual pinned evidence directories are selected. Independent review identified credential re-export and older VC runtime handling; both were corrected.

**Review focus:** Nonzero Robocopy exit codes, partial exports, redirected/nested destinations, old user-specific Python paths, credentials missing from the new process, and clear distinction between environment readiness and generated video delivery.
