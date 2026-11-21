# LVA-07-05 RGB Layout Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, focusedRED/GREEN and one scopedreview.

**Goal:** Feed nativeVAEstridedRGBto encoder aspackedC-orderbytes.
**Architecture:** Oneboundarynormalization inrgb_frames, samevalues and sourcebytehash.
**Tech Stack:** ExistingNumPy/FFmpeg, noinstall.
**Spec:** docs/task-designs/LVA-07-05-encode-layout-design.md

## Global Constraints
Originalinputs/models/fp32/93frames/16fps/768x432/40vs4;18private24RSS20GPU; nooldIDrePOST, humancontrolacceptancebeforefast.

## Review Focus
ExactRGB/T/H/Wordering, unchangedrounding/finiteguard, memoryviewhashandcommunicatepacked, non-CnativefixturewithonefullRGBdecodeproof reuse.

### Task1
- [x] RED nativeCHWT->THWC layoutunit andexisting93frameactualencode/proofcase.
- [x] Addnp.ascontiguousarray toquantizedoutput; GREENaffectedWrapper suite; scopedreview; archive/deliver2files.
### Task2
- [x] Newsealed06ownedcombinedprepare/pair/control, humanreviewthenfast; retainactualhistory/outputs/exit.

Final evidence: docs/task-designs/LVA-07-05-completion.json. Both original videos technically and actually human accepted; owned service exited0/unforced/port closed.
