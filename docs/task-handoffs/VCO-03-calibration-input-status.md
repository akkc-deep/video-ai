# VCO-03 当前校准输入与剩余证据

> **当前AI路线已完成：** 无需填表或重复下载。六项证据已集中交付，新几何通道90项完整结果、3个新来源一次检查、50项测试通过。相机新检查3项跳变全检出且12项正常无误报；动作仍有重播弃权，未启用生产。见 [最终交付](VCO-03-AI-final-results.md)。以下为历史记录。

> **最新AI补充校准 v2：** 13项新增结果完整测量，六项阈值均有数值；新单源检查中动作漏检1项、相机误报7项，如实保留。无需人工填表。见 [本轮结果](VCO-03-AI-followup-results.md)。原版结果以下保留。

> **当前交付更新：** 用户选择AI实验校准、无需人工表格；该路线已完成240项实验结果，见 [AI校准结果](VCO-03-AI-calibration-results.md)。下文的真人依赖仅保留为原正式benchmark记录，不阻塞本次AI交付。

更新：2026-10-25。此文集中说明本轮新增结果，替代旧快照中“还需下载4个文件”的操作提示。

已完成24个候选、2,868个选段原生帧的只读闭包与时间边界核验；四批最长36.52秒，退出码均0。全部来源页、作者署名、许可和许可链接已归并。该24位置选段总数与“另有备用素材、合计25段/2,964帧”的库存计数口径不同，备用段未重复算入这24个位置。

20源正式区域/真值通过现有schema及全帧覆盖检查，已有200控制recipe与最新兼容输入一致。新的20源输入副本保留people03“挡手、改钢笔”选择；旧jobs仍指向默认全主体的source.json，后续不得直接按旧路径重放这两项。

新增4源的40个待构造计划已绑定精确配方、帧身份、显示/原生两套时间和clip边界。它们没有生成RGB或ControlCase，实际控制仍200/240。

## 直接使用的材料

- [24源就绪/来源/许可清单](D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/source-readiness-24.csv)
- [血缘及原12+12分组证据，未冻结](D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/lineage-and-split.evidence.UNFROZEN.json)
- [20源精确schema部分目录，未冻结](D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/catalog-20.partial.UNFROZEN.json)
- [200个已有控制的兼容重放绑定](D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/existing-200-replay-bindings.json)
- [40个待构造计划](D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/pending-40-control-proposals.json)
- [完整审计说明](D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/README.md)
- [最终核验及计数](D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/delivery-final-check.json)

## 当前不能由机器补造的事实

| 缺口 | 已有材料 | 仍缺什么 |
|---|---|---|
| 新增4源区域身份/真值 | 480原生帧、960条AI草稿及原AI审阅页 | 白桦互遮、工具低纹理、星空/光斑同体身份的可信依据；当前正式协议要求确认后的区域和逐帧真值 |
| 独立血缘与分组冻结 | 24源媒体/原始血缘哈希、原12+12位置计划、作者和来源链接 | 原拍摄/生成项目之间是否相关的事实，及据此冻结分组；未发现哈希冲突不等于独立性证明 |
| 正式独立审阅标签 | akkc/qzw两份提交副本、已有反馈及差异核对 | 可追溯的独立逐项判断、观看范围/时间及必要裁定；保留AI建议/整体反馈转录原貌，不能编造缺失字段 |

用户已授权后续AI审核，这些AI结果继续保留AI来源；它们目前不满足既有设计中的真人证据条件。旧表、下载文件、已接受ROI和审阅视频均已复用，不要求重新填整套表或重复下载。

本轮没有运行detector、拟合阈值、评估留出集或启动VCO-04。VCO-03保持BLOCKED。后续须以[既定验收协议](D:/code/py/video-ai/docs/task-designs/VCO-03-design.md)和实际证据解除门槛；当前108项软件测试通过记录继续有效，但不能替代真实校准。
