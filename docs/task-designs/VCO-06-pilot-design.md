# VCO-06 小批结构稳定性试采

2026-10-29。承接用户“那你继续工作啊”和此前提出的小批试采路线。本文件是VCO-06的执行补充，不替换主设计、旧24次采集计划、旧资格门槛或任务板Design引用。执行者选择本轮最多4次本地Wan请求；该数字是本轮预算决定，不声称用户指定了4次。用户已要求继续该新工作，文档、软件、预算冻结和预算内执行连续完成，不重复索要同一项继续授权。

## Goal

用最多4个新的完整原生视频验证：减少镜头/物体动作、增强可跟踪表面结构，能否得到结构稳定、无额外物体的开发素材。观察是否存在可研究的恒定偏色，不保证正例，不预先写已知修正轴。交付真实原片、生成前参考、请求证据、全部49帧技术记录和可查看入口。

## Scope

- 新建独立pilot根和schema，不覆盖原24段、13份用户导出、12段实际缓存、旧profile和失败。
- 固定4张新768×432 RGB8 sRGB参考、每张1个预先固定seed、49帧/16fps、无父片、原输出完整保留。仅development探索，不创建或查看holdout，不计正式跨4组资格覆盖。
- 参考采用纹理明确的平面刚性展示：织纹、石面、木纹、瓷砖四种布局。共同制作工具/部分材质与旧实验有关，全部列为development_seen，不称为4个独立盲测场景组。
- 固定相机、无物体动作是新的明确拍摄意图。原生视频仍需完整实际观看；没有预期动作不能伪装成复杂动作测试通过。结果只适用于该受限静态展示域。
- 新预算最多4次POST，总原生视频时长12.25秒。真实耗时取决于服务与硬件；参考上一轮每请求约3分钟作安排依据，不作时限保证。不调用付费云端、邮件、发布、生产采纳或额外模型；不安装依赖、不写Git，全库仍留VCO-08。

## Approach

1. 用现有NumPy/OpenCV直接创作具有明确sRGB定义的PNG；纹理和边缘在生成前固定，不对未知照片补标签。四张图和生成代码原字节在首次请求前归档、哈希并冻结。
2. 新 `pilot.FROZEN.json` 精确记录4个case、固定prompt/seeds、config、4个模型stamp、软件与workflow身份、max_requests=4、development-only、无替换/无自动补单。`collection-receipt.json` 的collection指向pilot冻结文件，供原来源绑定helper读取；旧 `load_collection` 必须拒绝该新schema，不能冒充旧24段collection。
3. 新版本consumer使用原reference gate、原事务/完成核验及原请求恢复helper；新writer显式调用自身 `load_pilot`，不monkeypatch旧加载器，不修改4份冻结采集文件。请求之前再次校验冻结输入和实际LoadImage字节。独占case目录先于服务/POST；同case存在时只核验或恢复原请求，未知结果停批，不替换seed/参考。
4. 使用现有本地ServiceManager拥有并关闭本轮Comfy服务；发现外部占用则保留现场并停止，不接管外部服务。所有请求串行；推理结束并关闭服务后再运行技术准备和测试。
5. 技术准备沿用VCO-02所有49帧sRGB/PTS检查，mapping放case/evidence、分析放新audit，避免把输入写进干净audit。建立真实source-index并调用正式研究source验证和import；复用原事务格式，不伪造production clip。
6. 复用现有观察页模板，4个case均development，保留其自己的pilot身份/缓存空间。静帧或自动解码只作技术检查；人类标签默认unverified，不自动认定色偏、结构、动作或改善。
7. 预算耗尽后停止。若技术/匹配失败或实际观看仍只有形变、局部/时间颜色变化，保留失败并结束该试采；没有正例时不启动扩展采集。不提前承诺下一批、更宽阈值或候选。

本轮不能独立生成自然资格profile：原协议需要每split至少12段/4组、每方向跨4组已知轴自然正例、中性与有害控制、development→seal→一次新holdout。pilot即使发现一个候选源，也只是后续正式输入设计的依据；扩展采集需另有明确冻结计划与预算。

## Files

- 新 `src/video_ai/experiments/natural_pilot.py`：4张参考、精确pilot schema、冻结/加载与字节保护。
- 新 `src/video_ai/experiments/natural_pilot_runtime.py`：预算内单次生成/原请求恢复、全49帧准备和正式导入；不绕过来源验证。
- 新 `scripts/experiments/vco06_pilot.py`：freeze/acquire/prepare/status/portal，root显式本地路径，不提供强制覆盖、额外seed、忽略风险或holdout开关。
- 新 `tests/unit/test_natural_pilot.py`、`tests/unit/test_natural_pilot_runtime.py`：预算/漂移/重入/别名/来源/只读状态/CLI行为。
- 新 `docs/superpowers/plans/2026-10-29-vco06-pilot.md`：实施和实测账本。
- 新 `docs/task-handoffs/VCO-06-pilot-results.md`：实际请求数、成功/失败、原件保护、入口和未完成项。

## Tests

Python全部bootstrap后通过Invoke-VideoAiNative串行执行；实现前分别RED，然后最小GREEN。无GPU运行时才测试。

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco06-pilot-tests'
Invoke-VideoAiNative $VideoAiPython @('-B','-m','pytest',
 'tests/unit/test_natural_pilot.py','tests/unit/test_natural_pilot_runtime.py',
 'tests/unit/test_natural_acquisition.py','tests/unit/test_natural_acquisition_runtime.py',
 'tests/unit/test_natural_acquisition_observation.py','tests/unit/test_natural_material_preparation.py',
 '-q','--tb=short','--basetemp',"D:/VideoSi/cache/video-ai/temp/vco06-pilot-$VideoAiCommandId",
 '-o','cache_dir=D:/VideoSi/cache/video-ai/pytest')
exit $VideoAiExitCode
```

预期exit0；不是已测结果。覆盖：4次精确上限/新case/不同输入、old schema隔离、split/seed/prompt/预算漂移拒绝；source/helper闭包不变；未知旧intent不POST、重复完成只读；相同参考身份的独立性不夸大；所有49帧/PTS、别人的source-index/import拒绝；外部服务不接管；status/portal不暴露holdout或声称自然通过。

## Acceptance

- [ ] 首次POST前已有不可变4次预算、真实参考身份、prompt/seed/config/software/model stamps及来源排除说明。
- [ ] 预算内真实请求最多4次，保存唯一原请求/受理/history/output；失败、未知和未开始项全部列出，不补单。
- [ ] 成功原片全49帧、原生16fps、无音轨贡献、明确色彩、真实正式研究导入及可查看入口；不能只交付mock或合成视频。
- [ ] 原24段/13份观察/已有软件冻结身份不变；相应定向测试与实际命令有证据。
- [ ] 实际标签、结构稳定性、单轴偏色和后续资格明确分别记账；没有资格不生成profile或校色候选，不登记VCO-06完成。

## Risks

固定镜头可能仍有重建形变或时间漂移，也可能完全没有需要校色的偏差。四种材质只是探索布局，不能冒充新的独立资格组。显示器关闭不影响远控观看，浏览器回调仍可能缺项；使用已有分离时间记录/本人确认，不再以强行补49回调作验收。现有静态观看工具不能给完整视频标签；本轮交付时按实际能力保留未确认，不虚构用户看过新视频。
