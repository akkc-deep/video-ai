# VCO-07 observer optimization — independent supplemental review

Verdict: CHANGES_REQUESTED. No demonstrated Critical write/POST bypass; three Important capture-safety regressions identified by static inspection. The unchanged final verification mitigates persistent aliases, but does not make the optimized capture interface equivalent to its original alias-rejection contract.

Scope: only the current `observe_file` duplicate fast path, the current `observe_inventory` parent-sharing optimization, and the three new tests at `tests/unit/test_continuity_byte_guard.py:239`, `:251`, and `:264`. Existing scanner kinds and parent integration were not re-reviewed. Supporting definitions of `_validate_spelling`, `safe_path`, and `hash_file` were read to resolve the actual path semantics. No tests, reproductions, full suite, production/GPU/network operations, agents, or .git writes were run; only this requested report was written.

The parent reports regression RED `c7f2f0ae35df486ca83fef774b964204`: 2 failed, 1 passed; related GREEN `e244e32a83444abba600117eec405e5d`: 223 passed in 40.47 seconds. Those results were not independently rerun or their logs inspected. Isolated timings of 0.322 to 0.173 seconds for 1,000 hash captures and 1.417 to 0.345 seconds for 10 inventories of 1,000 entries are parent-reported, not accepted-tree evidence. The stopped approximately ten-minute capture/native -1 result is not a pass. The parent reported the replacement read-only benchmark as still running; this review makes no claim about its outcome.

## Important 1 — duplicate file observation no longer rejects redirected parents

Location: `src/video_ai/runtime/_continuity_byte_guard.py:313` through line 315.

Membership in every builder proves that the spelling was previously checked; it does not prove that its ancestors remain unredirected. `lstat()` prevents following a link at the final component, but follows redirected intermediate directories. A concrete counterexample is: observe `root/parent/file`; rename `parent` to another location on the same volume; install a directory junction at the original `parent` pointing to the renamed directory; observe the original identity again. The leaf is still the identical regular file, with unchanged device/inode/nlink/size/mtime and digest fields. Every new fast-path check succeeds, although the original `_safe()` would reject the junction.

The original public interface also allows observing a previously obtained FileIdentity/dict directly, so the comment that an actual hash caller validates its read is not a sufficient precondition for this fast path. Even for instrumented hashing, caller validation and observation are separate operations; this code establishes no protected ancestor lifetime between them.

Final `ByteGuard.verify()` will reject a junction that remains installed. If it is restored before verification, the capture can still finish successfully despite the alias being present during an observation. This is an Important regression in the frozen capture contract, not a demonstrated bypass of unchanged final per-write guards.

Required correction: retain fresh ancestor-redirection validation for duplicate observations, or reuse it only with an explicit validated mechanism that keeps the checked directory ancestry stable for the whole reuse interval. A matching pathname or unchanged leaf ownership alone is insufficient. Add a regression that preserves the actual leaf inode via parent rename/junction and requires the duplicate observation to fail and poison the capture. The new test at line 264 replaces the leaf inode and therefore does not cover this case.

## Important 2 — inventory no longer rejects canonical leaf-name aliases

Location: `src/video_ai/runtime/_continuity_byte_guard.py:354` through line 367.

The old per-entry `_safe(value)` included `Path.resolve(strict=False) == path`. The new sequence checks lexical spelling, canonical parent, and leaf link/reparse metadata, but never checks canonical resolution of the leaf itself. `_validate_spelling()` rejects ADS, trailing dots/spaces, device names and similar forms; it does not reject an NTFS 8.3 short-name alias. On a volume/file with an existing short name, an entry such as `LONGFI~1.JSON` has a safe canonical parent and is an ordinary regular leaf according to lstat, while resolving to the distinct long filename. The old implementation rejects that alias; the new observer accepts it.

The unchanged exact inventory verification will normally later reject the short spelling against enumerated long names. That mitigation does not satisfy the specified canonical-only observation contract and can emit a proof that fails immediately even without an intervening filesystem change.

Required correction: preserve canonical validation of each leaf spelling, or provide an equivalent validated identity/name check without the repeated ancestor walk. Add a Windows short-name regression where that filesystem capability is available; explicitly account for unavailable short names instead of treating ordinary sibling files as coverage. This finding is specific to resolvable leaf aliases, not case differences already treated equivalently by WindowsPath.

## Important 3 — batching parent checks introduces an observation-wide alias gap

Location: `src/video_ai/runtime/_continuity_byte_guard.py:360` through line 369.

Checking a distinct parent once before its first entry and once after the complete caller-supplied iterable is consumed is not equivalent to checking it for each entry. A deterministic counterexample can use a real expected generator: yield the first entry in an ordinary child directory; before yielding the second sibling, rename that directory and put a junction at its old location; after the second yield resumes, remove the junction and restore the directory before exhausting the generator. The second leaf lstat follows the junction, and the final `_safe(parent)` sees the restored ordinary directory. The new observer accepts the inventory; the original per-entry `_safe(second)` rejects while the junction is installed. No concurrent test thread or precisely timed syscall race is needed to expose the changed behavior.

Final verification cannot observe a redirection that was restored before capture closed. Existing path checks were not globally atomic either, but this optimization adds a much wider unchecked interval spanning arbitrary generator execution and many sibling observations. The before/after pathname checks do not pin the ancestry and do not establish that it was unchanged throughout that interval.

Required correction: validate each entry's current ancestry, or use a mechanism that prevents directory replacement/redirection during the whole shared validation interval. Add a real-filesystem generator regression for this establish/yield/restore sequence and require rejection with a poisoned capture. The new sibling performance test at line 251 only counts `_safe` calls and verifies an unchanging directory; it cannot establish the safety claimed in the implementation comment.

## Preserved checks and limits

The inspected modifications retain collector locking, immutable emitted rows, bounded expected consumption, duplicate identity conflicts, byte/mtime and leaf ownership/nlink comparisons, observation error poisoning, root validation, lexical absolute/containment checks, per-leaf link/reparse rejection for inventory entries, and the unchanged complete verification path. Parent sharing is local to one observation and does not introduce a retained mutable proof cache. No independent issue was found in those aspects.

The three new tests establish the intended reduction in helper calls and continued rejection of a replaced leaf. They do not cover the three alias cases above; the reported aggregate pass count does not settle those gaps. No additional Minor finding is raised for formatting or for the already assigned accepted-tree performance measurement. Production acceptance and the deferred VCO-08 full suite remain outside this review.

## Coordinator disposition (08:48+08)

All three Important findings accepted. The optimized capture shortcuts were
removed, rather than treating later verification as an equivalent capture check.
Each file observation again calls `_safe`, and every inventory entry again calls
`_safe`, retaining its leaf canonical/8.3 rejection. Fresh leaf lstat also retains
ownership checks. New real-filesystem tests reproduce a duplicate file through a
same-inode parent junction and a generator that installs/restores a junction
between siblings. Canonical-resolution assertions cover every entry and every
repeat. Valid failed-first run ef4c977c1ca343b6a6e7682aca82a0eb:4 failed; complete
relevant eight-file run cd69008c02c742ff9afec2303e560fb4:225 passed/41.24s/exit0.
No trusted-observer bypass was introduced. This is the coordinator's test-backed
fix disposition; the independent report above is preserved. Actual-tree strict
capture is still running separately; no production acceptance claimed.
