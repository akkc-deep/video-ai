# Production Wan fast

The user explicitly requested integration into the ordinary production entry and default fast, then clarified that resumed old tasks must also use fast. Implementation proceeds under that authorization; no inference or external publication is requested by this change.

`make-video` (including `generate_video.cmd`) defaults to `--wan-mode fast`. `control` selects the repaired Wrapper without LoRA; `native` selects the original production workflow. The resolution profile remains separate. Wrapper currently requires 768×432/native16 and 4n+1 frame budgets within 93 frames; unsupported explicit quality/long-scene settings fail clearly before submitting, rather than silently changing their resolution or duration. Temporal-extension jobs retain their distinct backend.

## Approaches

Changing the existing native graph to four steps would skip the tested Wrapper numerical repairs. Replaying the experiment protocol would misuse its exhausted sample authorization and fixed prompts. The chosen implementation adds a production worker and templates, reusing the admitted numerical sampler, paired-LoRA preparation, fp32 VAE, text bridge and block offload. It uses ordinary production Comfy submission/recovery transactions.

## Production and recovery

The public production entry scopes the requested default; standalone historical component APIs retain their existing behavior. New and resumed production requests use fast unless overridden. Existing per-clip graphs determine the backend for already prepared/submitted/completed requests, including ambiguous IDs. Such requests never change graph or resubmit. Subsequent unsent clips switch to fast; already finished clips remain reused. No frozen options/configuration or historical evidence is rewritten. Scene parameters describe actual sampling values; old rows keep their original parameters. Per-request graphs bind the worker protocol version, mode, exact dimensions/frame budget, prompt, seeds, models and output namespace.

The ordinary owned service manager starts the isolated repaired Wrapper interpreter for Wan only. Image generation and upscaling keep their current environments. Historical native GET recovery uses its original backend; the service changes when subsequent new Wrapper work begins. If the old process history is gone and local evidence cannot establish its result, the request remains blocked with its original ID. A paired admission occurs once per worker, following text/image preparation, and its certificates are reused for further clips. Each clip gets private text/image conditioning and a separate evidence directory. The production protocol has no experiment.json, matrix trials, experiment authorization or experiment quota. Original experiment source and guards stay unchanged. Inherited revision clips consult their proven source request before choosing parameters. Standalone readers recognize frozen Wrapper graphs outside the ordinary invocation mode scope.

All worker writes stay within the run. A launch receipt records exact runtime/source/model identities and owns a single worker epoch. Model files are protected and hashed once per owner; verification thereafter checks retained handles. The existing finite HTTP and GET-only ambiguous recovery contract remains. Output encoding performs finite/shape checks once; existing production media validation remains responsible for decoded output and human reviews. No additional video matrix is run.

## Validation

Targeted tests cover default/explicit scope, mixed old/new recovery, full prompt/seed/frame binding, recipe values, unsupported sizes, production templates, owned runtime selection, isolated source/runtime identity, queued once-only behavior, and preservation of the experimental protocol. A CPU worker boot tests real node registration and object_info without model weights or generation. A new GPU generation is outside this implementation validation.
