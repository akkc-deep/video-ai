# 全流程性能优化结果（2026-11-05）

实施依据与范围：[全流程优化实施计划](video-generation-performance-plan.md)。在原工作区增量修改，未回滚其他改动、未写 Git 元数据。生产暂停，没有启动生产服务、请求真实模型/云端、操作暂停进程或清除原锁。离线测试仅使用独立 fixture run、内存 transport/临时 loopback 假服务和本机 FFmpeg，不消费生产任务。

当前生产路线为 `paragraph_jimeng_v1`，未启用 whole/temporal。冻结计划含 107 场景、202 片段、13,306 保留帧、13,562 生成帧、245 份 PCM；模型、采样、2560×1440 图片、两张候选、全部帧、完整原文/旁白、人工审查与发布门槛保持原义。

## 已落地

1. **默认路线输入保护**：将已存在的 Windows 输入保护接入普通生产入口、独立图片/选图和默认 scene writer。封存输入首次仍完整 SHA，后续由持续 native 句柄保护并核对身份；输出、暂存文件和 manifest 不变为不可写。嵌套作用域复用原窗口，不擅自扩展封存范围。
2. **共同前缀**：连续只读的 revision/common 准入使用有限读取事务；同次 `record_common` 构造一次 expected PCM 身份。写标记期间持续保护源文件；非 Windows 回退严格重算。
3. **配音/分镜恢复**：局部 HTTP 请求索引以 unit ID 定位，Windows 文件名变更通知发现新增/删除，不凭目录mtime复用。原始请求由 native 句柄保护；checkpoint/fsync 短释放后重核原字节 SHA 与文件身份。641 request / 600 PCM 不占用成百上千 CRT reader，失败仍释放全部资源。响应关联、重复提交和未知结果拒绝规则保留。
4. **Ollama 装载**：新 owned-stage 请求显式记录 `model_session=owned_stage_v1`，同阶段 `keep_alive=5m`；旧 intent/body 的 `keep_alive=0` 原样恢复。模型、prompt、schema 与采样参数未改；阶段结束仍按原归属关闭服务。
5. **图片等待重叠**：普通图和参考图都在 caller 线程先分别持久化两项 accepted，再查询/下载；没有并行 worker 写记录。先检查全部旧 unknown/terminal/result；拒绝新提交时仍可收集已有 accepted，不创建替代付费任务。既有 task ID、逻辑 request 和候选数保留。
6. **图片校验与选图**：锁、当前请求字节和完整来源检查分层；DNS 后仍核对 request/intent/当前依赖。accepted 的同操作 expected 重建、相同 active cursor 的 activation 和辅助双 `_run` 消重，纯读事务共享配置。
7. **TOS**：首次完整 GET 验证后，仅强版本号、ETag 与完整对象身份同时匹配才复用该版本的字节证明；每次仍 HEAD。无版本/null/变更或 HEAD/GET 不一致保持原严格 GET，未建立不可靠的全局永久缓存。
8. **邮件预览/分页**：四尺寸预览共享一次输入解码，同字节晋升复用工具检查，维持旧 JPEG 字节；恢复仍重渲染证明，防止 media.json 与衍生图成对篡改。MIME 保留最终完整大小检查，复用每页最新编码和不可变字节摘要，避免保存所有试排副本。
9. **SMTP**：同批次成功页复用连接/EHLO/login，每页仍独立授权、intent/receipt。拒绝、超时、未知 DATA、caller 未接收 receipt 或关闭 scope 均使会话失效，不回池、不自动重发。
10. **Wan/提帧**：同一媒体事务内复用相同 SHA 与工具身份的视频完整检查，关闭/外线程复制后失效。默认提帧批量执行完整 PNG CRC/IHDR、尺寸、序号及每帧全 RGB SHA，与独立源解码逐帧比较；无抽样。PNG 用 framehash 输出，避免第二整段 RGB 内存；promotion 后按同内容证明复用。
11. **Comfy 能力与轮询**：`/object_info` 绑定自有服务实例/PID/启动时间/template，变化即失效；原 prompt 的增量 history 归并保留所有矛盾证据，首次与完成后 queue 检查保留。等待/读取仅做截止/取消，每次 socket 写仍完整来源核验，caller 写响应 body/metadata 前分别完整检查。
12. **合成与恢复**：逐帧复制保留每源 SHA、运行锁和 fsync；整批来源全量检查改为复制批次前后各一次。音视频合并为一次 FFmpeg 完整解码，PTS、音频样本及 AAC packet 检查保留。已完成 upscale 进度复用同一次完整帧重建，不再重复一次。

## 可复现实测

| 离线样本/指标 | 原路径 | 新路径 | 说明 |
| --- | --- | --- | --- |
| 12 帧 128×72 提帧与完整像素证明 | 1.360404 秒、53 个媒体进程 | 0.187901 秒、6 个媒体进程 | 约 7.24 倍；每帧 PNG SHA 一致 |
| 24 张真实 PNG、64 个历史文件的复制 | 平均 2.480126 秒；48 次完整来源检查 | 平均 0.273413 秒；2 次完整来源检查 | 减少 88.98%；SHA/锁/fsync 都保留 |
| 24 个既有 HTTP 请求恢复 | 24 次目录枚举、576 次请求解析 | 1 次目录枚举、至多48次解析 | 新名称通知仍触发刷新/重复拒绝；具体解析点随关闭句柄改造减少 |
| common PCM 构造 | 每 PCM 2 次哈希入口 | 每 PCM 1 次 | Windows 持续保护；其他平台严格回退 |
| 预览（含拼图） | 5 个渲染命令、11 次探测 | 2 个渲染命令、6 次探测 | JPEG 字节兼容、恢复真实性检查保留 |
| MIME 示例 | 完整编码5次、摘要6次 | 编码3次、摘要2次 | 最终 MIME 大小仍核实 |
| SMTP 两页 | 2 次连接认证 | 1 次 | 每页DATA/receipt独立 |
| 同强版本 TOS 两次验证 | HEAD×2＋GET×2 | HEAD×2＋GET×1 | 无强版本时没有这项节省 |
| 4 次 history 的假任务 | queue请求5次 | queue请求2次 | 保留首/末queue矛盾检查 |
| 2MiB假 concrete GET | 41次完整来源guard | 1次发送guard | 响应持久化前另有完整caller检查 |

这些样本分别测本地处理和协议放大，不能相加为整片节省时间。没有真实云端推理、GPU推理或生产下载耗时对比。

复现：

```powershell
D:/VideoSi/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_extraction.py
D:/VideoSi/envs/video-ai/Scripts/python.exe -X utf8 scripts/benchmark_scene_frame_copy.py
```

报告：`D:/VideoSi/cache/video-ai/logs/scene-extraction-benchmark.json`、`scene-frame-copy-benchmark.json`。这两个脚本新建独立 fixture，不操作原生产 run。

原生产第19场景另以禁止网络/生产写入的脚本恢复：`4.290063 / 4.303860 / 4.275560` 秒，平均 **4.289828 秒**；与前两轮末的约4.20秒相近，未因本轮调度改造回退到最初19.59秒。配置仍每次完整加载2次，三次 `verify_artifact` 总数仍43,434。报告：`reference-recovery-pipeline-after.json`。此次首次 loader 12.492146秒，未控制磁盘缓存与并行测试负载，不能据此宣称冷启动提速；预热完整 loader 为1.35秒左右。

## 验证与保全

- 最新全组合新增性能契约：**67 passed / 12.52秒**。
- 最新真实小型完整候选/放大/成片整合：**1 passed / 162.31秒**，保留完整原PCM、字幕与 `awaiting_final_review`，未发布。
- 合成中断、原命令恢复、CLI拒绝边界：**24 passed / 619.50秒**；后续局部收紧由新鲜整合与定向单元覆盖。
- 前缀领域：193 passed / 1 excluded；排除 `tests/unit/test_ollama.py::test_single_structured_request_records_raw_evidence`（会启动临时loopback HTTP服务器，本组只使用内存transport）。文件保护长文本资源边界、旧/新 intent 合约均覆盖。
- 图片领域：162项单元、67项最终候选/参考集成、61项最新MIME/SMTP分别通过，存在重叠，不合计成总数。较早领域集成123通过+1个旧拒绝异常类型断言失败，已接受 native `PermissionError` 的正确拒绝并由最终集覆盖。GBK默认读取UTF8的两项环境错误通过统一 `-X utf8` 消除，未改历史产物。
- 视频领域：226项单元通过；4项集成覆盖逐片观察、只读重放、缺失外层索引、未来坏帧及临时copy恢复原prompt；最后framehash/scope收紧另有46项真实媒体/PNG/deadline及最新整合覆盖。
- 独立最终只读代码审查未发现 Critical/Important。实现期发现的CRT资源泄漏、fsync重锁、复制上下文、preview原图写开、SMTP未确认连接回池等问题均先有失败回归再修正。
- 原run仍有19份场景汇总、40份accepted任务记录；第20场景两份result和原图保留、尚无candidates汇总。最新只读基准比较原图、accepted/result/candidates及原锁SHA，均未变化。暂停标记仍为paused，owner/token与原锁一致。

## 明确保留与待真实运行验证

保留跨网络的 accepted 真实性重建、新 activation forward transition 的二次核对、无强版本TOS的HEAD+GET、邮件恢复重渲染、所有片段/帧的恢复预检、父片观察门槛以及逐帧GPU提交。没有通过跳过坏证据、降低画质或增加并发未知intent换速度。

服务装载、云端候选等待重叠、GPU吞吐、远端下载和全片推进收益仍未实测。跨人工审核等待常驻服务、并发GPU推理、跨invocation语义准入缓存未引入；这些需要额外资源/服务版本与完整依赖约束，不属于本次能用离线事实安全替代的检查。视频制作继续暂停，等待用户明确通知恢复。
