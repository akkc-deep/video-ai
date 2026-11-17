# LVA-05 concrete GPU commands

Status: prepared only; none of these real commands has run. Execute only after explicit authorization for this manifest.

Manifest SHA256: `9cef6989ed1133e41e8ed5151a7f04414c7a629f39c510a26fb52e4bf658cd96`. All paths and Artifacts are frozen in that file. Do not use the superseded pre-review snapshot.

Run from `E:/code/py/video-ai`. One phase at a time; no existing Comfy listener/production restart. Each phase owns one native process, cold1/warm3, max14,400s, all retained frames. The process closes before quality review. Existing-root invocation is original-ID recovery, never a replacement service.

## Serial and single factors

At most 4,272 GPU frame requests for these twelve phases. A failed original ID is retained; do not create a replacement request to fill the table.

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase low-serial --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase high-serial --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase parent-serial --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase child-serial --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase low-prefetch --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase high-prefetch --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase parent-prefetch --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase child-prefetch --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase low-writeback --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase high-writeback --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase parent-writeback --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase child-writeback --gpu-authorized
```

## Combination gate

Only after both single factors of the same fixture pass technical checks and genuine user quality acceptance. `quality-accepted.json` must contain `decision: accepted` and `report_sha256` bound to that phase’s exact `phase-results.json`; never synthesize a user decision. If no factor improves repeatably, retain serial; do not spend the bound simply to fill a matrix.

At most 1,424 additional frame requests; total cap 5,696.

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase low-pipeline --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase high-pipeline --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase parent-pipeline --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_upscale_pipeline.py --plan docs/task-designs/LVA-05-experiment-manifest.json --phase child-pipeline --gpu-authorized
```

## Independent encoding

Twelve accepted materializations: low/high/parent-child chains, four trials each. New paired libx264 medium/CRF18 and h264_nvenc p4/constqp/QP18 commands preserve other args; no new upscale/Wan. Max12 NVENC and12 CPU encodes. Missing native capability/driver or changed pixels/PTS/count/color never permits alternate flags or adoption. QP and CRF are not equivalent.

```powershell
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case low-cold_1 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case low-warm_1 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case low-warm_2 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case low-warm_3 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case high-cold_1 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case high-warm_1 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case high-warm_2 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case high-warm_3 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case chain-cold_1 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case chain-warm_1 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case chain-warm_2 --gpu-authorized
& E:/VideoAI/shared/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_encoding.py --plan docs/task-designs/LVA-05-experiment-manifest.json --case chain-warm_3 --gpu-authorized
```

## Exact roots

| Phase/case | New root | GPU frame cap |
| --- | --- | ---: |
| low-serial | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-low-serial` | 372 |
| low-prefetch | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-low-prefetch` | 372 |
| low-writeback | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-low-writeback` | 372 |
| low-pipeline | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-low-pipeline` | 372 |
| high-serial | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-high-serial` | 372 |
| high-prefetch | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-high-prefetch` | 372 |
| high-writeback | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-high-writeback` | 372 |
| high-pipeline | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-high-pipeline` | 372 |
| parent-serial | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-parent-serial` | 372 |
| parent-prefetch | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-parent-prefetch` | 372 |
| parent-writeback | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-parent-writeback` | 372 |
| parent-pipeline | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-parent-pipeline` | 372 |
| child-serial | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-child-serial` | 308 |
| child-prefetch | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-child-prefetch` | 308 |
| child-writeback | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-child-writeback` | 308 |
| child-pipeline | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-child-pipeline` | 308 |
| encoding-low-cold_1 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-low-cold_1` | 0 upscale; 1 NVENC |
| encoding-low-warm_1 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-low-warm_1` | 0 upscale; 1 NVENC |
| encoding-low-warm_2 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-low-warm_2` | 0 upscale; 1 NVENC |
| encoding-low-warm_3 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-low-warm_3` | 0 upscale; 1 NVENC |
| encoding-high-cold_1 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-high-cold_1` | 0 upscale; 1 NVENC |
| encoding-high-warm_1 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-high-warm_1` | 0 upscale; 1 NVENC |
| encoding-high-warm_2 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-high-warm_2` | 0 upscale; 1 NVENC |
| encoding-high-warm_3 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-high-warm_3` | 0 upscale; 1 NVENC |
| encoding-chain-cold_1 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-chain-cold_1` | 0 upscale; 1 NVENC |
| encoding-chain-warm_1 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-chain-warm_1` | 0 upscale; 1 NVENC |
| encoding-chain-warm_2 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-chain-warm_2` | 0 upscale; 1 NVENC |
| encoding-chain-warm_3 | `E:\VideoAI\scratch\benchmarks\LVA-05-20261116-01-encoding-chain-warm_3` | 0 upscale; 1 NVENC |


## Interpretation

Native Comfy model/node cache already existed and is audited, not a new optimization. Node/model CPU calls are not physical transfers. Read phase/individual-frame times, recovery mode, I/O/check counters, queue payload, logical storage and device-wide samples separately. No unmeasured value becomes zero and no local-stage times are summed into whole-film throughput. Human acceptance and adoption remain separate.
