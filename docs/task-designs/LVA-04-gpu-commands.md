# LVA-04 proposed download and GPU commands

Prepared-command snapshot. User subsequently authorized the pinned downloads and bounded GPU matrix. Downloads, quality low-motion cold1/warm3 and one fast low-motion original request executed; fast admission rejected mixed delta formats before sampling. Both services stopped. Remaining prepared roots were not submitted. See LVA-04-results.md; do not blindly run the remainder after this rejection.
Manifest: `docs/task-designs/LVA-04-gpu-manifest.json`. Fixed official revision, filenames, byte counts, SHA256, model identities, environment/source/binary hashes and all new roots are recorded there.

Two LoRAs total **1,374,118,048 bytes** (~1.37 GB decimal). Download uses staging, full size/SHA admission and atomic no-overwrite promotion. It never installs packages or changes the original models.

Run from `E:/code/py/video-ai` after authorization:

```powershell
$lva04Python = 'E:/VideoAI/shared/envs/video-ai/Scripts/python.exe'
$lva04ManifestPath = 'E:/code/py/video-ai/docs/task-designs/LVA-04-gpu-manifest.json'
& $lva04Python -X utf8 scripts/benchmark_wan_fast.py --action download --manifest $lva04ManifestPath --authorized-download
```

First prepare the quality low-motion control; use `fast_experimental` for its paired distill phase only after download admission:

```powershell
$lva04Manifest = Get-Content -LiteralPath $lva04ManifestPath -Raw | ConvertFrom-Json
$lva04Mode = 'quality'
$lva04Fixture = 'low_motion'
$lva04Root = $lva04Manifest.proposed_roots.$lva04Mode.$lva04Fixture
$lva04SourceRoot = $lva04Manifest.source_roots.$lva04Fixture
& $lva04Python -X utf8 scripts/benchmark_wan_fast.py --action prepare --mode $lva04Mode --factor distill --manifest $lva04ManifestPath --experiment-root $lva04Root --source-root $lva04SourceRoot --port 8189
$lva04Digest = (Get-Content -LiteralPath (Join-Path $lva04Root 'frozen/profile.json') -Raw | ConvertFrom-Json).profile_sha256
$lva04Launcher = Start-Process -FilePath $lva04Python -WindowStyle Hidden -PassThru -ArgumentList @('-X', 'utf8', 'E:/code/py/video-ai/scripts/observe_fast_comfy.py', '--experiment-root', $lva04Root, '--profile-digest', $lva04Digest, '--port', '8189', '--max-seconds', '3600', '--authorized-gpu') -RedirectStandardOutput (Join-Path $lva04Root 'launcher.stdout') -RedirectStandardError (Join-Path $lva04Root 'launcher.stderr')
```

Wait for `worker-attestation.json` and confirm the listener belongs to the exact `service-owner.json` PID before running the phase. If startup fails, retain logs and original identities; do not silently retry with another process or recipe.

```powershell
& $lva04Python -X utf8 scripts/benchmark_wan_fast.py --action run --experiment-root $lva04Root --port 8189 --authorized-gpu
Wait-Process -Id $lva04Launcher.Id -Timeout 30
```

The phase runs cold_1/warm_1/warm_2/warm_3 serially, requests its exact owned PID to stop on success or failure, and has a 3600-second outer service limit. Wait for `service-result.json` and actual process exit before review. Do not start another phase concurrently. If a request's result is unknown, recovery uses the original root/intent/GET only; never replace the historical owned service or re-POST.

After technical inspection, request full human video review. No automatic acceptance receipts are created. If native LoRA admission, sigma, finite IMAGE, frame/PTS or quality fails, retain the evidence and reject the candidate. Do not proceed to accelerated factors on failure.

The remaining initial-input phases use `high_motion` and `parent_child` with the same two modes and roots in the manifest. At most **32 native trials** total across two profiles × four fixtures × four repeats; failed candidates or human gates stop the applicable chain. These are native experiments, not full-film throughput.

After the new parent for a mode has stopped and has explicit SHA-bound human acceptance, prepare the child's fresh service using that **same profile's parent**:

```powershell
$lva04Root = $lva04Manifest.proposed_roots.$lva04Mode.child
$lva04ParentRoot = $lva04Manifest.proposed_roots.$lva04Mode.parent_child
& $lva04Python -X utf8 scripts/benchmark_wan_fast.py --action prepare --mode $lva04Mode --factor distill --manifest $lva04ManifestPath --experiment-root $lva04Root --source-root $lva04Manifest.source_roots.parent_child --parent-root $lva04ParentRoot --parent-trial cold_1 --port 8189
```

The child uses the accepted cold_1 parent's actual retained tail as its fixed input for cold1/warm3; it records that dependency. Quality and fast tails can differ and are never presented as identical input pixels. Original child prompt, seeds and full frame budget are retained. Then launch/run/stop/review as above. Parent rejection stops that chain.

Sage, cache, compile and combination are explicitly rejected in this environment; do not install them or claim a measured speed. Production adoption and default-mode changes remain separate decisions.
