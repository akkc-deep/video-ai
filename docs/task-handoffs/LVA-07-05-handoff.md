# Pause Handoff

## Handoff Type

pause

## Task Link

- **Task board:** docs/task-handoffs/jimeng-local-video-acceleration-v1-task-board.md
- **Task ID:** LVA-07-05
- **Transition:** IN_PROGRESS -> BLOCKED
- **Design document:** docs/task-designs/LVA-07-05-design.md

## Current State

2026-11-20 T5修复已交付；53相关测试通过、独立审阅0重要/严重项。新组20261120-02原文本准备成功：positive664/negative512维4096 float32，T5弱引用释放已证明，native阶段1.6414728s，进程提交峰值11879981056 bytes低于12GiB。原文/模型未换，未截断。

同worker原pair dfac5207-c443-4464-b638-f1e1e61d8354已完整成功，high1500/low1459适用及290排除、两head前向证明保留。完整阶段2253.834s，只读取原ID结果，没有重复POST。

control原prompt77da1e64-b42c-4c6d-8b4f-7f83b492faad在节点10/LVA07Prepare失败，原固定Wrapper nodes.py:1155 vae.model.to(offload_device)分配15925248 bytes失败。编码已走完，CPU回迁未完成；没有Wan采样/解码/MP4/质量，fast未提交。native peak_pagefile12884893696，距12GiB仅8192bytes，主机仍约16GiB空闲。源失败/trace保存，不重POST。

owned PID11824/epochd5425839-da87-4be4-9832-b591bd9d580b合作exit0/unforced/port_closed，2422.25s；服务RSS观察19295608832 bytes。当前无GPUworker。pair是历史证明不可直接放行新epoch。

## Changed Files

- wan_wrapper_text.py、wan_wrapper_nodes.py、wan_wrapper_backend.py、两个Wrapper CLI/controller、04contract及三个测试文件：T5先行同epoch缓存/释放、664-token上下文、12GiB提交限额。
- docs/task-designs/LVA-07-05-text-design.md / text-plan.md / text-results.json / text-review.json：既得修复/测试/审阅/实际文本。
- 当前root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-02：授权/280源快照、原文本缓存和回执、pair/两witness、control原history.failed、failure-native-resources、experiment-assessment、service-result。
- docs/task-designs/LVA-07-results.json/.md、任务板/本交接：当前失败与未验收事实。

## Verification

消费实际既得结果，不为交接重复校验：53pytest通过6.51s；独立审阅0重要/严重；prepare-text原ID3f13770f-1c2f-4809-bb89-bcf5f87e14c7成功、664/512float32/encoder_released；原pair双专家真实准入2253.834s；control仅一次POST，history明确VAE回迁CPU分配失败，原生峰值距12GiB8192bytes；服务合作exit0/未强制/端口关闭。

## Remaining Work

先单独诊断VAE编码后CPU回迁的提交峰值，在原模型/fp32/93帧预算下验证内存生命周期修复，再评估新源/新组边界；不要先重复完整pair。实际control技术/真实接受后fast，双方质量/计时/资源与退出仍待完成。不换模型或截断提示词，不重发旧失败ID。

## Resume Task

LVA-07-05：完成最小原低运动control/fast及实际人工质量。

## Start Here

顺序来源：05design与text-design；当前experiment-assessment及原history.failed/failure-native-resources；固定Wrapper nodes.py:1155及WanVideoVAE.encode/clear_cache；原fixture、pair/witness/lease与预算。

第一动作是独立VAE回迁内存探针，保持12GiB/RSS24GiB/allocator20GiB，比较回迁前释放allocator空闲缓存是否消除瞬时峰值；在小探针通过前不再次完整pair。实际不限时/本机预算/继续修复授权持续，不重复索取。

## Blocker

- **Reason:** VAE编码后CPU回迁触及12GiB提交限额，完整视频/质量尚无结果。
- **Resolution condition:** 原输入/fp32/93帧的受限VAE准备及回迁有实际通过证据，再按BLOCKED -> READY -> IN_PROGRESS继续新源新epoch。

## Risks

T5与pair已实际通过不能代替采样/解码/质量；VAE缓存/allocator生命周期尚待证实，禁止运行中放宽或以重复视频覆盖失败。06保持NOT_STARTED。
