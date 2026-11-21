# LVA-07-05 VAE memory handoff repair

## Goal and evidence
Preserve original six models, fp32 VAE,768x432/93frames, prompts/seeds and actual human gate. Existing text664/512 and full pair passed, but control77da1e64 failed at nativeVAE CPUoffload, private peak12GiB-8192. No sampling/video. No source change while worker alive; that worker exited0.

## Approaches and decision
Chosen implementation call under continued user repair/machine-budget authorization: reclaim unused CUDA pool at VAE return/offload boundaries, plus prepare/cache original image conditioning before pair in the existing durable prepare-text phase. This is a routine memory-lifecycle choice, not a user-selected new product behavior. Raising private cap alone leaves a large avoidable pool overlap; spatial tiling/dtype/frame changes alter established behavior and are excluded.
Native isolated93-frame/fp32 probe under12GiB passed, beforeCPUoffload allocated519534796/reserved8287944704 bytes. Scoped trim reduced private11766525952->4336513024 and CPUoffload passed. Synthetic CPUpressure probe failed earlier in encoding; it is not an exact replay of the Comfy warm state and is not proof of operational success.

## Contract
Keep12GiB private/RSS24GiB/allocator20GiB, startup14/21 and text-ready phase4/20GiB. Same original UUID POSTonce/GETrecovery. No cross-epoch cache restoration.
`vae_memory_scope(vae)` intercepts only that VAE's encode/decode returns and outer/model CPUto calls, invokes native soft_empty_cache, restores exact instance attributes in finally. No tensor math change, global monkeypatch, per-forward scan/hash or cache flush inside temporal loops.
Existing prepare-text now prepares original image via nativeLoadImage and WanVideoImageToVideoEncode after T5release, before pair; exact CPUimage tensors and CPUVAE retained privately. Receipt publishes only after both complete and includes inputSHA/shapes/finiteness/fp32/CPUproof. Failure clears all caches. Admission requires both. GenerationPrepare clones CPUconditioning, returns same CPUVAE and originaltext; no late T5/encode. NativeDecode is subclassed under its existing registry key and same schema to scope cleanup across finalimageCPUtransfer/offload; guard GPU and shared contextlock.
No full pair before actual new-worker combined preparation passes. Old original terminal IDs stay terminal; max2 actual videos and humancontrol acceptance remain.

## Acceptance and limits
Focused RED/GREEN covers pool overlap, inherited/overridden method restoration including exceptions, no cleanup on failed return, both scopedto paths, early image preparation/cache gating and no late imageencode. A single final scoped review. Actual new-worker combined prep first, then fresh pair/control. Native isolated probe proves lifecycle operation, not video quality or sampler success.

Review fix: original image path/expectedbytes/SHA joins the same protected InputLeases window before all native preparation, preventing cached conditioning from a changed input. One check/window, not per-frame validation.
