# LVA-07-05 Windows commit budget for original decode

## Evidence / architecture decision
-04 original40stepcontrol875719f4 fullysampled: high30/low50nativeforwards, 664/512text, noLoRA, high469.190755s/low772.960827s. NativeVAEdecode failed atconv2d after1.357s; nativepeak12884738048 is160KiB below12GiBJobcommit cap. Hostavailable18.0GB, no matchingDisplay/nvlddmkm reset observed. Owned39592 exited0/unforced/closedport afterrequest; noMP4/fast.
Same originalfp32 VAE/93frames/768x432, no tiling, synthetic-shaped latent7GiBprivate baseline:12GiBJob fails withCUDAOOM despite17.58GiBfreeVRAM;32GiBdiagnostic passes93x432x768x3finite float32CPUoutput andCPUVAEReturn. Nativecommitpeak15279673344(~14.23GiB), RSSpeak3045167104(~2.84GiB). This is logicalcommit including GPUallocations, not physicalRSS exhaustion. Selected18GiBcommit leaves~3.77GiB above measuredpeak; retainedphysicalRSS24/GPUallocator20/startRAM14/freeVRAM21/singleWan. Validate selected18GiB independently beforeproductlaunch. Changingprecision/tiling/frames would alter established behavior; retaining12 cannotfit measuredpeak.

## Contract / implementation call
Under continuing usermachine-budget/unlimited/repair authorization, sealedcontractGPUprocess_private_commit_bytes=18GiB. CPUJob4GiB stays. Add min_available_commit_bytes=26GiB (18+8reserve), controller-only GlobalMemoryStatusEx preflight before childlaunch; publish observedproof. Do not apply26GiBglobal floor inside boundedchild, whoseWindowsstatus can reflect itsJob quota. No model/math/input/quality change, no perframevalidation. No service in-place capchange or oldfailedIDrePOST.

## Verification
FocusedREDcap18/globalcommit26 gating; affectedWrapper suiteGREEN once, one finalscopedreview/fixpass. Actual18GiBoriginaldecodeprobe mustpass. Newroot05sameoriginalinputs/source/auth, jointprepare thenfreshpair/control, realhumanacceptance beforefast. Priorfailedsamplerequests preserved; max2 actualvideos. No video acceptance or throughput conclusion fromsyntheticdecodeprobe.
