# VCO-06 正式研究输入交付

用户要求“我要一个可以用于任务的”，并明确要求继续当前任务。本轮已实现正式研究导入、完整分片诊断、探索性自然指标基线及只读消费入口，交付一个实际可被新研究入口读取的纸质素材。**状态为 `research_input_ready`，校色候选资格仍为 `awaiting_qualification`，`ready_for_propose=false`；VCO-06 未完成。**

## 唯一交付入口

- 输入包：`D:/VideoSi/projects/video-ai/vco06-usable-input/20261028-141129-0710d61477d0/delivery.json`
- 使用说明：`D:/VideoSi/projects/video-ai/vco06-usable-input/20261028-141129-0710d61477d0/README.md`
- 本地原图/原片审阅页：`D:/VideoSi/projects/video-ai/vco06-usable-input/20261028-141129-0710d61477d0/review.html`
- 正式研究 run：`D:/VideoSi/projects/video-ai/runs/20261028-145342-f5100beeb167`
- 来源 commit：`research/material/commit.json`，SHA256 `6e7412fd75138d94d522c6b17f1cf9715f41dfc2f742dbfc781542773e0d31f1`。
- 普通全帧报告：`D:/VideoSi/projects/video-ai/runs/20261028-145524-6edf7131048c/logs/continuity/report.json`，SHA256 `0541e93e1cd4724afe92e5465c105edf89c933e56846e15415cf8ffb5590f487`。
- 自然指标开发基线：`research/continuity/natural-baseline.json`，SHA256 `aaf6803584388df0ce4633c0aecd5bc86f9200fe893c0dbfb36197dc66fbf2b5`。

## 实际完成的验证

完整复用原 prompt `dde7b6f2-8c82-4b25-bc2e-9ea84cf75645`，未新增模型请求。核验原 options/manifest、固定模板与参数、实际 LoadImage 字节、生成前参考图转换、模型 stamp、全部原 HTTP 请求清单、唯一 POST、受理回执、成功 history/client/graph/output 和原始输出字节。媒体和证据独占复制到新研究 run，保留原身份与副本身份；没有生成生产片记录或旁白 timeline。

原生视频完整 49 帧，768×432、16fps、3.0625 秒、无音轨；独立参考图及 49 帧全部 VCO-02 ready，实际 RGB 字节全部核验。完整 generated/material frame map、PTS/time_base、尾帧及实际 VCO-02 解码命令身份均已绑定。

实际普通诊断覆盖 48 个 adjacent 和 49 个 reference（含第0帧），97/97 comparable；50/50 ready records 是49视频帧加1张参考图。分片保留全部 vectors、sampled_pairs、原因和源帧证据，根报告不重复嵌入几何点。单比较过大可无损拆分。缺失、错序、跨producer借用分片、缩减区域字段、零采样却声明comparable均拒绝；中断后可重算并复用逐字节相同的已留存分片。

9×9 linearRGB 邻域中位数探索性基线已测完49帧，各帧均保留1024个有效配对。它只用于研究重建差异和色偏统计，不是预注册资格实验，不产生新的自然阈值或合格方向。没有拟合或编码修复候选，没有把降低后的误差宣称为视觉改善。

## 消费与恢复

在仓库根目录执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-research-status'
Invoke-VideoAiNative $VideoAiPython @('-B','scripts/scene_research_material.py',
 'status','--run-dir','D:/VideoSi/projects/video-ai/runs/20261028-145342-f5100beeb167')
```

预期退出0，返回 `research_input_ready`，绑定当前 commit/epoch/assessment/完整49帧。相同请求的 `import --request <包内 final-import-request.json>` 只恢复同一事务；完整 UUID 在独立登记中绑定原请求字节，不可改时间戳或改源另建第二个 run。普通生产 freeze/load 在任何服务动作前拒绝研究 run。

`analyze --run-dir <上述run> --manifest <包内full-pair-manifest.json>` 验证/恢复同一全帧报告；`baseline --run-dir <上述run>` 重放同一探索性开发基线。代码/源字节变化必须据实失效，不能刷新旧SHA或覆盖旧报告。研究 options 独立保存在 `research/options.json`；普通 ProjectConfig 未新增一个可启动生产的开关。

## 软件验证与审查

最终9个定向测试文件88项通过，122.39秒，退出0：`D:/VideoSi/cache/video-ai/logs/vco06-usable-final-tests-3f3b64c043e84887897681b06009d57d.log`。覆盖新来源/分片/数值/CLI/生产边界和现有输入、连续性策略、普通报告兼容。更早失败、修复前69/74项及RED记录保存在包内progress.md和原日志，未当作最终一次合跑。未执行全库回归；VCO-08保持原范围。

独立只读审查发现的UUID跨时间戳分叉、分片producer/input绑定不足、完整区域字段校验不足、分片中断恢复及CLI错误合同问题已在同一修复轮处理，并有针对性的RED/GREEN证据。最大资源规模、全部生产服务的动态路径和科学资格不宣称已得到这88项测试证明。

## 尚未完成的资格

新 `natural-repair-profile.json`、独立新holdout及实际完整播放的校色Precheck尚不存在；候选估计入口只有诚实等待分支，没有可接收手写profile的拟合分支。完整播放反馈已请求，尚未得到有效观看结论。用户“继续当前任务”是继续执行授权，不是观看通过或已知色偏方向。

因此该包可用于新方案中的正式来源消费、完整研究诊断和开发基线，仍不能交给旧 `research_candidate_v1` 或直接执行自然校色propose。现有两个旧失败材料、旧v1/r2阈值及封存profile保持原义；本轮不改判旧结果、不登记VCO-06 COMPLETED、不准备VCO-07、不发布。

## 后续用户反馈

用户在收到原图/原片审阅入口后回复：“没有看到有明显问题，我分辨不出来”。已将原文及确切原片/参考图/交付身份保存在 `D:/VideoSi/projects/video-ai/vco06-usable-input/20261028-141129-0710d61477d0/feedback/20261028-184407-cfdf93583e8d.json`，核验记录为同目录 `20261028-184407-cfdf93583e8d-verification.json`。

该反馈只证明用户未报告明显问题、不能确定色偏；不据此选择算子、标注自然偏色正例或宣布校色改善。未补造完整观看范围、播放器事件、观看时间、正式Precheck或normal/anomaly标签。决定保留原片，不为制造可见差异而强行修色，也不要求用户识别细微色偏。9项已交付媒体/commit/诊断/基线/索引身份复核未变，`ready_for_propose=false`及VCO-06状态保持；独立资格研究仍需继续。

## 后续资格续作

用户要求复用本交付继续后，已完成真实全49帧像素特征重放、规范资格统计和独立审计；当前132项定向检查通过。原输入包/报告/研究run保持原字节，未重复导入或重新生成。结果见 [资格研究续作](VCO-06-qualification-continuation-results.md)，固定定义与尚缺的独立数据/实际标签见 [资格协议](../task-designs/VCO-06-natural-qualification-protocol.md)。仍awaiting_qualification，没有新自然profile、真实候选或改善通过；本记录原先的88项和导入结果保留为历史，不改判。
