# LVA-05 independent review and fixes

Review was required by `superpowers:requesting-code-review`/inline execution. One clean-context read-only reviewer inspected only the new LVA-05 implementation, tests, source planner and launch/encoding scripts. Other pre-existing workspace modifications were excluded. No reviewer GPU run or edit occurred.

| Finding | Correction | Regression/evidence |
| --- | --- | --- |
| Prefetch source bytes were discarded while Comfy still read its input | Coordinator materializes a distinct new owned input using prepared bytes or the same bounded serial fallback; HTTP verifies that new input | `test_old_readonly_source_materializes_new_owned_input`, RED then GREEN |
| ffprobe `-show_frames` decoded the complete encoded video before another RGB decode | Metadata-only probe; all actual PTS/count/RGB hashes from one demux-timebase framehash decode | `test_encoded_evidence_uses_one_decode_with_actual_timebase`, RED then GREEN; real offline FFmpeg fixture |
| Launch reloaded effective Python/Comfy paths from mutable config | `pinned_tools` uses admitted Python/main Artifacts; configuration itself is captured | `test_effective_tools_are_taken_from_pinned_artifacts`, observer identity refusals, RED then GREEN |
| Existing-root recovery returned without stopping the original service or recording phase results | Recovery joins common `finally`/`stop_owner` and the result path, without replacement Popen | `test_existing_phase_recovery_stops_owner_and_writes_results`, RED then GREEN |
| Terminating only the supervisor could orphan Comfy on Windows | Verify child PID/start binding, stop/reap child first; observer also owns a kill-on-close Windows Job | `test_stop_timeout_terminates_verified_child_before_supervisor`; real CPU child killed by Job-handle close, RED then GREEN |

Reviewer follow-up confirmed all reported findings fixed and no further confirmed important functional blocker. The final targeted suite is 96 passed. Additional coordinator regression refuses full-pixel mismatch rather than permitting human approval to waive it.

Review does not certify GPU/model compatibility, measured gains or human visual quality. Those require the prepared authorized experiments. Known legacy fixture path-policy failures remain separately disclosed.

## Authorized execution follow-up

Actual startup revealed two gaps not reached by the initial offline fixtures: a frozen configuration string needed `Path` conversion; owner publication precedes TCP readiness. Both were reproduced RED→GREEN, with 8 focused observer/lifecycle tests passing. The read-only reviewer found no important defects in those corrections. Failed setup roots were retained and produced zero inference intents; corrected source identities and new -03 roots are bound by `LVA-05-execution-manifest-v2.json`, with the authorized model/source/workflow/parameters/sample limits unchanged.

For a genuinely negative experiment, the requirements reviewer cites the design's explicit “交付否决也属明确实验结果” branch. Matching complete ordered RGB to previously genuinely accepted sources may establish unchanged content provenance; it is not a new human decision. Rejected, unpromoted I/O candidates need no redundant new viewing to report their negative result. NVENC viewing is explicitly conditional on all technical contracts passing. Never create acceptance records or claim new viewing from this ruling; unexecuted combination remains untested, and no usable-video cost is reported before final quality acceptance.
