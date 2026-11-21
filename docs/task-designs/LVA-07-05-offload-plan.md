# LVA-07-05 Block Offload Repair Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, focusedRED/GREEN and one final scopedreview.

**Goal:** Avoid native CPUcopy commit crash by restoring frozenCPUsource storages on blockoffload.
**Architecture:** Local lazy per-owner block.to scope, preserving nativekernels, mutablebuffers and exactmethodcleanup.
**Tech Stack:** Existing Python/PyTorch/Comfy, no install.
**Spec:** docs/task-designs/LVA-07-05-offload-design.md

## Global Constraints
Originalmodels/math/inputs/664text/93frames/humangate;12private24RSS20allocator; no originalunknownIDrePOST or oldfullmatrix.

## Review Focus
NativeParameter.data ownership, sourceconstness/staticoverlays, immutableLoRA vsmutablebuffers, lazycapture aftersetter, exception/restoration and perowneronly.

### Task1
- [x] Add tests/unit/test_wan_wrapper_offload.py RED for sourcecopyavoidance/bufferstate/restoration/guards.
- [x] Implement wan_wrapper_offload.py and Sampler scope. GREENaffectedWrapper tests and actualbounded firstblockprobe.
- [x] One scopedreview, fiximportantonce withRED/GREEN, archive/deliver taskfiles.

### Task2
- [x] Newsealedroot/auth/source and owned combinedprepare; originalfirstblockadapter alreadypassed beforepair.
- [ ] Freshpair thencontrol; actualacceptance beforefast; recordnativeerrors/unknowns andexit.
