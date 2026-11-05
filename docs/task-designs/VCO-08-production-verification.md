# VCO-08 生产接入验收证据

验收：**已通过（2026-11-04）**。主任务五项 Acceptance 均有下列证据；任务状态以任务板为准。

固定证据根 `C`：`D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification/allocator-async-candidate-v1`。

| 主任务 Acceptance | 最终证据 | 结果 |
| --- | --- | --- |
| ① 真实时序条件及完整身份 | C 四窗真实采样；续窗实际父 raw `[80,93)`、13 帧、48 层 clean KV，每窗 4,076,863,488 字节；固定模型、27 源数值核心及 bundle。生产 provider 的 raw13/Generator 输入有定向和集成验证；当前 8 源五阶段真实资源及普通 exporter 独立准入均已通过。 | 通过 |
| ② 历史/新增唯一贡献、完整时基 | C 实际 320 帧、768×432、16fps、20 秒；`93+80+80+67`，边界 93/173/253，原生 raw 逐像素一致。320 四窗/334 五窗事务及同 run 重放已最终复验；完整 PCM/字幕、真实 CPU 超分/合成和旧模式兼容有独立 fixture_only 证据。 | 通过 |
| ③ 主体/色彩/构图/镜头/动作 | C `trial-001/chain-004/dynamic-review.json` 实际 human_video 完整观看接受，SHA `4beaf4aca19f19e1a5d1a4c28deddb525fd118a8c5e32d20891b0ed35440421f`；技术、静态和动态分账，曝光及出框变化已披露。最终验证保留静态后继、完整新链及 VCO-04 原始拒绝、作者和风险回应门禁。 | 通过；视觉范围限该案例 |
| ④ 失败/unknown/恢复/失效 | 跨 run 修订 `test-d79dfdc3193f4759afa3f9c36be52c05.log` 2 passed/3508.22 秒、exit 0：父 raw93/Generator 继承、仅后继一次采样、混合链新观看及原事件/来源不变。早期 video/cache launch unknown 公开入口 `test-56f22a27a1ea4ad3a475090840b9b54c.log` 两场景 2 passed/186.78 秒、exit 0；成功 latent 仅解码、缓存复用及终态身份也有定向证据。 | 通过 |
| ⑤ 实验/生产准入分离 | 当前生产资源根 `c8da3bd7e9c2441cbb9594255a959a20` 五阶段 complete、真实 worker/runner exit 0；普通 exporter 导出独立生产准入。5,326 个唯一测试节点的覆盖核对完成，未知 0、未解决失败 0，最终源码 SHA 匹配。生产为显式 opt-in，不自动发布。 | 通过 |

## 最终准入与资源

- [独立生产准入](/D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification/allocator-async-candidate-v1/production-native16-admission.json)：185,810 字节，SHA `1e56f31d5bb2c885342d250daaf9209bc38ff21383c9f3226cfbb30eac5c8d47`，`assessment.ready=true`。
- [当前生产资源收据](/D:/VideoSi/projects/video-ai/inputs/vco08-production-resource/c8da3bd7e9c2441cbb9594255a959a20/production-resource.json)：`first/clean_history/continuation/vae_encode_13/vae_decode_93` 全部完成；实际 latent `[1,16,24,54,96]`、13 帧编码 `[1,16,4,54,96]`、93 帧解码 `[93,432,768,3]`、48 层 BF16 KV 4,076,863,488 字节。
- 同根 `completion.json` 的 worker_exit_code=0、resource_trigger=null；runner9324、worker23784及外层 session13689均结束。最小空闲 physical/commit/GPU 分别为 15,522,332,672 / 6,660,816,896 / 18,701,352,960 字节；峰值 GPU allocated/reserved 为 7,127,267,462 / 8,187,281,408 字节。
- 新增采样、文本编码、视频输出均 0；time_limit_seconds/max_gpu_allocated_bytes 均为 null。旧 `88e4a41c0c1745268d4bb686ae28930a` 仅保留为历史。

正常命令由 `C/production-staging/run_final_closeout_checks.ps1` 经项目 bootstrap 调用 `scripts/export_temporal_evidence.py --runtime <新资源根>/runtime.json --production-preflight <新资源根>/production-resource.json --target C/production-native16-admission.json`。bootstrap 日志 `vco08-production-admission-final-49c1e3f00363453884d30eb4991be482.log` 记录 exporter 和覆盖核对均实际 exit 0。

## 最终软件覆盖

[逐节点覆盖账](/D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification/allocator-async-candidate-v1/regression-final-coverage.json)：1,853,412 字节，SHA `4afb0b07350ff1e1b6961539237ab16e8016217134369b94291ece77fcd05a67`。按保留的有效前缀和新增/受影响复验合并，5,326 个唯一节点全部有通过证据，unverified_nodes/unresolved_failures 均为空；当前全部 src/tests/scripts 源 SHA 与最后修复批库存一致。

| 批次 | 完整终态 | 后续处置 |
| --- | --- | --- |
| 原已验证前缀及实施前批 | 751 PASS；另 2,607 PASS；原 timeout 故障注入修复 5 项通过 | 按精确节点与影响范围保留 |
| `regression-remaining-final-ac534ed13ab54c3e89b020f46ca962ab` | 1,754 PASS / 14 FAIL，1300.17 秒，exit 1，源码不变 | 最小对象/None 兼容、公共 whole 读保护、fixture 祖先与有限 reader 测试边界修复；`test-63b6b9d2cbda4ddda126e1b3444d9f53.log` 108 PASS/14.54 秒 |
| `regression-final-affected-0360546c33894fc1b445fa064630af77` | 658 PASS / 1 FAIL，9327.22 秒，exit 1，源码不变 | 旧 `_prefix` 的 native scope 可选字段分流修复 |
| `regression-final-repair-6d1e7f5cbd9645dab00f2b718969c4fe` | 21 PASS，34.52 秒，exit 0，源码不变 | 包含该失败公共节点及原生/旧 continuity 门禁；全部发现的失败已解决 |

六条原生修订集成按 `c0e3a23a`、`d79dfdc3`、`56f22a27` 三份完整退出 0 的日志各两项保留。最终账为每个节点记录具体证据，保留失败历史及其解决收据，不重复无影响前缀或长原生修订。

日志位于 `D:/VideoSi/cache/video-ai/logs/`。CPU 集成中的模型数值、KV 或观看替身明确标记 fixture_only，不作为真实模型或人工观看结果。

独立最终审查已完成：`C/production-staging/final-review-findings.md`，0 Critical、3 Important、0 Minor；无弃权项。三项 Important 均已真实 RED→GREEN：早期 video/cache launch unknown、fresh native active-role 预检及缺失聚合 schema4 恢复。定向 61/29/38 项、公开入口两场景及最终覆盖均有通过证据；无未处理重要问题或延后 Minor。`git diff --check` 通过；遵循既有 Git 只读约束保留工作区与证据。

## 实施裁决

按执行账本原顺序保留六项裁决及错误代价：

1. 生产不加 320 帧硬上限，完整时间轴与视觉资格范围分开。更长新链可能质量下降，须完整新观看。
2. 为先落地生产源码，在明确节点边界结束旧 4375 批，保留 2607 个完整 PASS 并只续 1768 余项。错误代价是未完成节点必须重跑，未将中断计为通过。
3. native 冻结跳过 inactive Wan 角色并保留原 raw 路径。若下游仍依赖 Wan，必须修复真实分流，不能静默回落；fresh native 与旧兼容已复验。
4. 已定位重复闭包缺陷后受控结束旧媒体测试 75a2da4c；未终态 dots 计 0 PASS。错误代价是完整重验，该媒体路径后来已通过 c0e3a23a 两条集成。
5. whole 祖先 fixture 明确标 whole；有限 reader 仅在测试注入，正式生产无总时限。错误标记会失去声称的祖先/时间策略覆盖，已用完整正负断言和生产无期限检查验证。
6. 已定位单操作四次重复准入后受控结束 877c7e6f，用严格 operation-local memo 降为一次，仍逐次检查实际 bytes/inventory。错误代价是该未知节点须完整重验；跨操作/字节漂移拒绝及后续原生修订均已通过。

研究和正式生产均无执行总时限或人工内存/显存占用配额。实际空闲资源余量与一次采样、unknown 不重试、成功 latent 仅解码的守卫保留。Windows Terminal/AweSun 本次放行授权保存在 `C/production-desktop-authorization.json`；不关闭应用。

视觉资格范围为实际接受的单白鹭四窗 320 帧/20 秒。其他题材、更长新链和实际新成片须其自身完整观看；本次生产封装资源前向及 CPU fixture 不赋予新视频视觉接受。操作方式见 [生产说明](../jimeng-candidates.md)。
