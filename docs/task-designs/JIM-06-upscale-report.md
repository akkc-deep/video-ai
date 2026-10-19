# JIM-06 upscale implementation evidence

Task 1 owns the new retained-frame planner, RGB24 extractor, frame PNG transaction, immutable media store/context/result, read-only acceptance facade and upscale runtime. Existing JIM-03..05 files and Git metadata were preserved.

The required first implementation edit created `test_200_retained_frames_upscale_once_without_second_head_drop`. Its inputs use the existing `plan_scene_clips` and `scene_clip_frame_mapping` APIs, with the real 93/92/15 retained budget, generated indices 1..15 for clip three and output indices 0..199. No upstream production budgets were changed.

All Python commands below dot-sourced `scripts/bootstrap.ps1`, initialized the named environment, used `$VideoAiPython -B`, and ran serially. Runtime/log/temp files remain under D:/VideoSi.

| Environment | pytest arguments | Observed result |
|---|---|---|
| jim-06-upscale-red | `tests/unit/test_scene_media.py -k test_200_retained_frames_upscale_once_without_second_head_drop -q --tb=short` | 1 failed in 0.15s; missing `video_ai.planning.scene_media`, exit 1 |
| jim-06-upscale-green | `tests/unit/test_scene_media.py -q --tb=short` | 1 passed in 0.12s, exit 0 |
| jim-06-upscale-records-red | `tests/unit/test_scene_media.py tests/unit/test_scene_media_records.py tests/unit/test_scene_upscale_transactions.py -q --tb=short` | 1 failed, 9 passed in 0.23s; missing private extraction validator, exit 1 |
| jim-06-upscale-first-flow | `tests/unit/test_scene_media.py tests/unit/test_scene_media_records.py tests/unit/test_scene_upscale_transactions.py tests/integration/test_scene_upscale_flow.py -q --tb=short` | 11 passed in 672.44s, exit 0; original-import diagnostic, authentic 66-frame run `20261019-150318-458e9879dfa2` |

The first authentic flow diagnostic uses three admitted JIM-05 source scenes and real source MP4s, original observation acceptance, native extraction and synthetic owned RealESRGAN PNG service output. Its initial fixture has 66 frames. This run imported earlier implementation bytes; it is not final-tree verification. Fresh serial verification and exact final outcomes will be recorded below.

The shared API is `scene_media_context(frozen,units,timeline,*,paths=None,lock=None)` returning frozen/units/timeline/store/bible/plan/image_acceptance/scene_clips/inputs/template/rows. `SceneMediaStore.for_root(relative)` returns an independent stage-rooted store retaining guards/cache/actual lock. `require_scene_upscale_acceptance_record(context)` enables downstream validation in the same context. Private composition/final/delivery facade validators receive that context. All writes are caller-thread checked; network guards only read/hash.

Behavioral tests include exact pure mapping/contributions, fast and quality native pixel extraction and tamper rejection, independent PNG original-task transaction recovery, raw response/accepted/submission interruptions, rejected/failed/conflicting immutable history, queue/history completion races, unknown original task and no second POST, wrong node/prefix/extension/multiple outputs, and read-only replay. The root agent records final fresh verification against the final file hashes.

Remaining real-service boundary: the offline PNG backend verifies protocol, ownership and media behavior; it does not establish actual RealESRGAN visual quality or actual full-film viewing acceptance.

Worker handoff status: **DONE_WITH_CONCERNS**, pending the root agent's fresh final-tree verification and independent review. JIM-06 is not marked complete by this report.

Tests authored after the original-import diagnostic, not yet executed by this worker:

- Expanded `test_scene_upscale_transactions.py`: separate frame schemas and PNG path domain; once-only replay, lost POST and raw-body/response/accepted/submission/terminal interruptions; unknown ID without re-POST; queue/history race, retained failure/conflict, node/prefix/extension/output cardinality; cancelled late send guard.
- Expanded `test_scene_media_records.py`: actual fast/quality source MP4 extraction and full pixel comparison/tamper rejection; actual-lock caller-thread writes; internal reparse rejection; original upstream converted input and positive/empty HTTP body mutation guards; JSON fsync-before-rename crash remnants and immutable recommit; unknown-run/result invariants.
- Expanded `test_scene_media.py`: budget/mapping/Artifact rejection, 1/93/94/200 contribution coverage and strict bool indices.
- Expanded `test_scene_upscale_flow.py`: authentic short replay; extraction/frame/complete outer receipt recovery without re-extracting or POST; later-frame graph/orphan malformed terminal stopping every earlier new submission; transient copy preserving original prompt; cleanup failure withholding ready; authentic 200-frame first-scene chain with exactly 93/92/15 submissions and 200 contributions.

New helper `prepared_scene_sources` supplies authentic admitted native sources; `prepared_upscaled` defaults to a shorter real PCM fixture, selected before scene budgets are committed. Its long-scene option still uses JIM-05's real first-scene 200-frame mapping. No production budget or admitted media is shortened afterward.

Guard self-review changes include recursive capture of all Artifacts referenced by admitted upstream JSON (including converted inputs and raw HTTP bodies), original PCM and frozen copied input bytes; original terminal evidence classification without reading unvalidated status in error handlers; explicit byte-defect-only PNG terminal classification; stage-specific lexical reparse rejection; immutable preparation recovery; pending prefixes remaining read-only; and no newly restored deadline-free guard after transport completion.

Tool boundary: frozen upstream schemas contain tool paths, not historical binary stamps. This implementation captures invocation-local ffmpeg/ffprobe `ArtifactStamp` identities before upstream media admission and rechecks them around guarded work. It does not invent historical binary identity across calls. Frozen model stamps retain existing semantics.

Remaining verification work is concrete: run every current Task 1 unit/integration test in a fresh process, run the explicit long-chain test (not executed by this worker), then run the root's integrated and historical/full regression suites against final hashes. Exhaustive interruption and external service/transport behavior requires that fresh coverage and independent review; the original 11-pass diagnostic alone does not establish those later fixes.

Fresh scoped correction after the delivery integration diagnostic:

- Delivery's authentic flow exposed `AttributeError: 'str' object has no attribute 'read_text'` before Task 3. Direct read-only reconstruction against admitted run `20261019-152318-41fae13c7243` reproduced the exact trace (`scene_media_records.py` recursive inventory read → `config.read_json`). Inventory paths are strings; the strict JSON reader requires `Path`. `capture_admitted_inventory` now converts at the boundary, with a regression that captures nested upstream Artifacts from string inventories.
- `jim-06-upscale-expanded-units`: fresh three Task 1 unit files, runtime pytest cache: **51 passed in 6.27s**, exit 0.
- Delivery review identified a separate caller-thread clone defect. `for_root` constructed a store on the calling worker and rebased writer ownership. Focused RED `test_network_thread_cannot_rebase_writer_ownership_via_for_root`: **1 failed, 11 deselected in 0.19s**. The clone now preserves the original `caller_thread`.
- `jim-06-upscale-expanded-units-green`: fresh `tests/unit/test_scene_media.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_scene_media_records.py -o cache_dir=D:/VideoSi/cache/video-ai/pytest -q --tb=short`: **52 passed in 6.25s**, exit 0.

The three unit files above are now freshly verified; the explicit current-tree authentic integration/recovery/200-frame tests and root-wide regressions remain for the final serial run.

Further independent-review corrections:

- Preserved authentic context then exposed valid promoted preparation receipts whose original staging path had already been renamed. Focused RED for promoted receipt capture: **1 failed, 12 deselected in 0.22s**. Receipt-aware capture now binds existing accepted source/target bytes, tracks the original missing staging path as absent, and rejects late reappearance. Fresh three-unit GREEN: **53 passed in 6.32s**.
- Five focused pending-protocol cases failed RED because absence of `submission.json` skipped retained graph/output conflict, execution failure, rejected POST and orphan raw body. Read-only pending adjudication now evaluates original durable HTTP evidence before returning None; it writes no terminal/accepted/submission and performs no GET. The write recovery path still reconstructs original derived receipts/terminal evidence. Fresh three-unit GREEN after correction: **58 passed in 6.53s**, `jim-06-upscale-pending-green`, exit 0.
- The admitted upscale inventory now receives the same receipt-aware recursive Artifact/HTTP-body capture as the upstream image/source domains. A new authentic integration regression prepares only a later frame's original raw conflicting task and verifies every earlier new POST remains blocked. This integration test is authored but not yet run by the worker.

Latest scoped verification, after those corrections:

- Extraction command evidence mutation had focused RED **2 failed, 13 deselected in 0.22s** (nonempty stdout and empty stderr changed behind the accepted extraction JSON). Owned log JSON now contributes only strict actual `COMMAND_FIELDS` output paths to live guards. Descriptive old pre-promotion image identities inside immutable logs remain descriptive; preparation receipts bind their promoted live media. A regression contains a missing historical staging identity and still verifies both command byte guards.
- Fresh three-unit run `jim-06-upscale-command-log-identity-green`, exact arguments `tests/unit/test_scene_media.py tests/unit/test_scene_upscale_transactions.py tests/unit/test_scene_media_records.py -o cache_dir=D:/VideoSi/cache/video-ai/pytest -q --tb=short`: **60 passed in 6.62s**, exit 0.
- Direct read-only authentic preserved-run context finally GREEN using `python -B D:/VideoSi/cache/video-ai/jim06-context-repro.py` after bootstrap `jim-06-inventory-promoted-context-green-2`: **ADMITTED 6 frames; 284 positive Artifacts; 93 empty evidence files; 12 promoted original paths**, exit 0. This reconstructs original units and timeline from the admitted run's frozen script and real original WAVs. No media was regenerated and no accepted record repaired by this check.
- Raw pending rejected/failed/conflicting protocol evidence now produces read-only failed/blocked progress rows with original evidence, even if interruption omitted the terminal index. `for_root` preserves caller-thread identity and all positive/empty/absent/tool guards. Source frozen for integrated validation after this check.

Outstanding review concern explicitly sent to the root agent: source-domain JSON inventory is currently captured after initial semantic acceptance, so a new authored record appearing between the original require call and inventory capture should receive a before/after inventory check. The standalone atomic capture/admission race is not established by the current 60 unit tests; root review must resolve it before task acceptance.

Admission-to-capture race resolved after independent confirmation:

- Focused RED `jim-06-admission-snapshot-red`: **6 failed, 15 deselected in 0.39s**. Four controlled source semantic-gate unit seams inserted a new failed JSON or changed existing JSON after clip/image admission; the original implementation entered the upscale pipeline. Two upscale-acceptance seams similarly adopted new/changed post-validation JSON and replaced earlier guards. These tests isolate the boundary sequencing and do not replace real upstream acceptance evidence.
- `SceneMediaStore.snapshot_json` now retains the immutable original raw JSON bytes, Artifact identities and full JSON inventories before semantic admission. Source context checks that snapshot after clip acceptance, after plan/image acceptance, before adoption, after capture and before return. Upscale acceptance applies the same sequence around its semantic require. Adoption parses original captured bytes, rather than reopening changed records, and rechecks the filesystem afterward. No second media decode is used.
- `bind_artifact` preserves earlier positive, empty and absent byte guards instead of replacing previously admitted identities. Additional regressions mutate JSON during snapshot adoption and attempt replacement of an earlier Artifact guard.
- Fresh three-unit run `jim-06-admission-snapshot-final-units`, same explicit runtime-cache command as above: **69 passed in 6.80s**, exit 0. The previously listed admission-to-capture race is no longer outstanding in this implementation.

Final scoped review corrections:

- Fixed-file options snapshots retain their original raw bytes without interpreting historical external configuration source identities as run-local media. Focused RED **1 failed, 24 deselected in 0.23s**, followed by **70 passed in 6.81s**. The actual preserved context was GREEN at that point.
- Before-gate PCM/command evidence race: same-size PCM mutation with restored stat, and append to an originally empty stderr, at clip/image gate seams produced **4 focused RED failures in 0.64s**. `capture_unhashed_inputs` now binds original PCM SHA and command stdout/stderr before semantic admission; `verify_admission_snapshot` audits those old bytes afterward without another media decode. JSON-declared media/body Artifacts remain bound by the original snapshot's own recorded SHA. Original guards are preserved rather than overwritten. Three-unit GREEN **74 passed in 7.21s**.
- Known later model output preflight: both a committed submission without output preparation and completed raw history without submission skipped PNG validation before earlier new POSTs. Six controlled runtime regressions (wrong format, wrong size and temporary local tool failure × both prefixes) produced **6 RED failures in 0.68s**. Runtime preflight now fully validates known owned PNGs before returning an incomplete frame prefix. Raw protocol reconstruction only returns the original Artifact; protocol-only tests do not decode synthetic media. Temporary tooling failure blocks the invocation without persisting an invalid-media terminal.
- Latest fresh three-unit run `jim-06-owned-png-preflight-green`, exact runtime-cache arguments above: **80 passed in 7.58s**, exit 0. Current-tree full authentic, long-chain, historical and complete-suite verification remains assigned to the root agent.
- Final actual preserved-source context check after all Task 1 code changes: bootstrap `jim-06-final-preserved-context`, `python -B D:/VideoSi/cache/video-ai/jim06-context-repro.py`: **ADMITTED 6 frames; 284 positive Artifacts; 93 empty evidence files; 12 promoted original paths**, exit 0. Task 1 source/tests frozen afterward; serial test lease released directly to composition as requested.
