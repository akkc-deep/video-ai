# VCO-03 剩余工作执行清单

> **2026-10-26 重播补充工作已完成：** 复用12校准源并检查3个此前未测来源，共90项控制。新检查9项字面片段重播均检出、6项正常无误报、3项周期弃权，覆盖率83.3%；62项定向测试及完整证据核验通过。无需填表、下载或额外确认。详见 [最新补充交付](VCO-03-temporal-replay-results.md)。既有六项结果及原正式Benchmark状态保留。

> **当前AI路线已完成：** 无需填表或重复下载。六项证据已集中交付，新几何通道90项完整结果、3个新来源一次检查、50项测试通过。相机新检查3项跳变全检出且12项正常无误报；动作仍有重播弃权，未启用生产。见 [最终交付](VCO-03-AI-final-results.md)。以下为历史记录。

> **最新v3接点实验：** 已完成校准侧接点聚合与工作像素噪声处理，26项测试通过；新独立检查未执行。见 [v3结果](VCO-03-AI-events-v3-results.md)。无需人工填表；本页旧结果保留。

> **最新AI补充校准 v2：** 13项新增结果完整测量，六项阈值均有数值；新单源检查中动作漏检1项、相机误报7项，如实保留。无需人工填表。见 [本轮结果](VCO-03-AI-followup-results.md)。原版结果以下保留。

> **当前交付更新：** 用户选择AI实验校准、无需人工表格；该路线已完成240项实验结果，见 [AI校准结果](VCO-03-AI-calibration-results.md)。下文的真人依赖仅保留为原正式benchmark记录，不阻塞本次AI交付。

更新日期：2026-10-24。供另一个会话接手当前 VCO-03 的素材准备、人工审阅组织和真实校准使用。本清单细化既定剩余工作，不新增项目任务，不改变设计或任务状态。

**2026-10-25后续执行更新：** 已修复原生不等间隔PTS和指定局部目标的正式校准兼容问题，106项定向检查通过；20源/2,388帧核验和people03十变体1,000帧RGB复算通过。集中交付见remaining-delivery文末最新记录；仍缺4源及真实独立标签/血缘分组，保持BLOCKED。

**前轮执行更新（历史）：** 最新20源ROI/真值由用户确认，已构造并核对200个真实控制/23,880显示帧；240位置尚缺40。双人控制审阅、校准和profile均为0，另有来源/血缘/分组及青蛙时基兼容问题。新入口与证据见交付文末最新更新。下文早期计数是历史快照；VCO-03仍BLOCKED。

**最新进度（2026-10-25 AI审核）：** 新增4文件已全部下载并通过完整解码/颜色检查，480原生帧及960条AI选区草稿就绪；24位置均有原生帧草案，但ROI正式确认仍20源、控制仍200/240。已接收两份2460行表，结构错误0；标签940相同/1520不同且含AI建议/整体转录、观看时间缺失。后续AI审核获授权，结果明确保留AI来源；未伪造真人标签、未拟合或跑留出。最新入口和证据见交付文末。下方旧阶段计数保留为历史。

**2026-10-25 当前输入审计：** 24候选/2,868选段原生帧及20正式真值已复核；200控制配方重放一致，新增40项仅为待构造计划。最新108项软件检查沿用。来源血缘、原分组及正式输入缺口见 [当前集中说明](VCO-03-calibration-input-status.md)，不用按下方旧快照重下4文件或重填整套旧表。

## 接手指令（可直接复制到另一个任务）

> 请接手 VCO-03 的剩余工作。工作目录为 `D:/code/py/video-ai`，先完整阅读 `docs/task-designs/VCO-03-design.md`，再读本清单和 `docs/task-handoffs/VCO-03-handoff.md`，按下列顺序执行。用户已授权自行寻找并下载具有明确使用许可的公开视频，不再询问用户提供素材目录或是否允许搜集。复用现有候选、下载文件和证据，不重做已交付的软件。持续完成所有当前可执行的下载、身份/颜色核验、连续区间准备、ROI 草稿和审阅材料；某个来源失败时处理其他来源并寻找许可清楚的替代来源。不得因为最终需要真人审阅而提前停止这些准备工作。需要真人确认的内容保持草稿；完成可独立推进的工作后，集中交付具体待审材料和操作说明。收到真实标注后，再做冻结、校准和一次留出评估。不得伪造真人观看、签名或标签，不自动启动 VCO-04。

## 接手前事实快照与权威来源

- 任务板：`docs/task-handoffs/video-continuity-optimization-task-board.md`，VCO-03 为 `BLOCKED`。
- 完整契约：`docs/task-designs/VCO-03-design.md`，尤其第 7、7.1、8、9 节及 Acceptance。
- 软件验证记录：`docs/task-designs/VCO-03-verification.md`。已记录五文件定向检查 101 passed、退出 0；本清单整理时未重跑。
- 软件已交付：只读颜色 reader、六类分数、控制构造器、校准/留出评估和四个离线命令。无需从头实现。
- 候选 24 个，六题材各 4 个；已下载 3 个视频；Caminandes 仅 1 个分析帧已实际验证。
- 完整连续区间及 ROI/真值 0，已构造真实控制 case 0，真人审阅 0，真实校准 profile 0。
- 候选页面数量不等于已准入源数量；240 个 case 草稿位置不等于已构造或已审阅 case。

以下路径是现有输入：

| 名称 | 绝对路径 |
|---|---|
| 素材工作目录 S | `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7` |
| 候选清单 | S 下 `public-source-candidates.json`、`public-source-candidates.csv` |
| 当前状态及初查 | S 下 `sourcing-status.json`、`download-inspection.json`、`curation-verification.json` |
| 许可与来源证据 | S 下 `provenance/`；下载文件与凭据在 `media/` |
| 单帧验证记录 | S 下 `caminandes-one-frame-preparation.json` |
| 单帧 VCO-02 audit | `D:/VideoSi/projects/video-ai/runs/20261024-124505-baf05a594401` |
| 准备草稿目录 P | `D:/VideoSi/projects/video-ai/continuity-benchmark/preparation-a94b200fad4842de9847302838bcab81` |
| 草稿输入 | P 下 `source-intake.draft.json`、`review-queue.draft.json`、`review-queue.draft.csv`、`preparation-status.json` |
| 实际配置 | `D:/VideoSi/projects/video-ai/config/production.json`，只读加载，输出使用独立 audit run |
| 环境入口 | `D:/code/py/video-ai/scripts/bootstrap.ps1` |

S、P 只是本清单的路径缩写，不是可直接传入 CLI 的路径。所有实际命令使用展开后的绝对文件路径。

## 执行清单与完成标准

下面序号是 VCO-03 内的工作项，不是任务板中的新任务。勾选须有实际文件、命令结果或真人记录作为证据。

### 1. 核对入口并建立持续进度记录（自动）

- [x] 读取上述现有输入，核对 3 个媒体的 SHA 与下载凭据，保留源文件原字节和 mtime。
- [x] 区分“候选、已下载、颜色可用、完整区间、ROI 已确认、控制已构造、真人已审阅、已评估”各阶段计数。
- [x] 在 S 下另存 `remaining-progress.json`，逐源写明当前阶段、证据绝对路径、失败原因和下一动作；不把本清单的计划写成执行结果。

**完成标准：** 接手者能定位现有资产和缺口；无需重新搜索已保存的 24 个候选或重下已核验的 3 个文件。

**第一具体动作：** 读取 S 下的候选清单、状态和下载初查，从 Caminandes 已验证帧附近检查可用连续区间，同时继续处理其余来源的可达下载；不以等待 `labels.json` 为首步。

### 2. 补齐可用素材与使用依据（自动）

- [x] 完成其余候选的下载尝试；每次记录来源 URL、许可页面/条款、作者、下载结果、媒体身份及必要署名/改编说明。（20 个 ISO 原媒体实际下载/一次续传均失败；Spring 等动画替代版本亦留证；失败不计完整素材。）
- [ ] 原站不可达时寻找有明确许可的替代来源，保存替换关系及原因。不能用只有预览页、许可不明或尚未下载的候选填满正式目录。
- [ ] 六题材 people / animals / transport / outdoor / indoor / animation，各获得 4 个可用独立 source scene，共 24 个；每源能选择连续至少 4 秒、有可标主体/背景和可观察运动的片段。
- [ ] 保留拒绝/失败项。单个站点超时不阻止继续处理其他来源；不无限重试同一地址。

**已知情况：** ISO Republic 本地下载曾超时；公开 Blender 镜像 `https://mirrors.aliyun.com/blender/demo/movies/` 可达。Big Buck Bunny、Elephants Dream teaser、Caminandes 已下载。动画仅占六题材中的一类，继续下载同类不能补齐其余五类。

**完成标准：** 24 个实际本地文件及许可证据齐全，题材数量满足要求；这一步仍不等于颜色或独立性准入通过。

### 3. 核验颜色并准备连续原生分析帧（自动）

- [ ] 逐源保存 probe、原始色彩声明和 VCO-02 独立 sidecar，记录 resolved / unknown / conflicting / unsupported 的实际结果。
- [ ] Big Buck Bunny 当前版本缺必要色彩声明；Elephants Dream teaser 缺 primaries 且涉及不支持解释。寻找原始颜色证据或可用替代版本/来源；不得通过补猜 Rec.709 或改写标签准入。
- [ ] 每源明确一个连续、无内部切镜的至少 4 秒候选区间，保留原 fps、分辨率、原生 PTS/time_base 和半开区间边界。内容选择可先列草案，人工确认另行记录。
- [ ] 以显式帧索引的小批次，调用现有 VCO-02 接口实际生成所选区间内每个原帧的 `srgb_rgb24_v1` 记录与 RGB，再由 `load_color_analysis_set` 只读复核。
- [ ] 核验帧索引/PTS 连续性、ready 覆盖、RGB 字节长度与 SHA、退出时的源身份；保存每批预算、命令、退出码和 audit 路径。

**完成标准：** 24 源各有完整连续区间的 ready 分析帧和可复核原生时间证据。单帧、抽帧联系表或普通 JPEG 解码均不满足本项。

**复用参考：** `D:/VideoSi/cache/video-ai/temp/vco03_verify_caminandes_frame.py` 是已有单帧准备脚本，只作为接口参考；扩展准备须新建脚本/新 audit，不能覆盖原 audit 或把它直接当完整区间工具。

### 4. 核对独立血缘并冻结分组计划（自动整理，事实不明时需人工确认）

- [x] 按源媒体 SHA、原片/项目、相邻或重叠区间及衍生关系整理 lineage；证据不足时明确列为待确认。（当前 8 项及已知 BBB/封装同源关系在审阅包 lineage 草稿，未冻结。）
- [ ] 相同原片、同图衍生或同生成血缘归入同一个 `scene_group`，禁止跨 split。不同 URL、片名或裁剪段不能自动证明独立。
- [ ] 六题材各列 2 个 calibration group、2 个 holdout group，总计 12/12；在拟合前冻结实际源身份和分组。
- [ ] 不依据 detector 表现选素材、移动分组或回看留出结果调参数。

**完成标准：** 24 个独立源的依据和限制可追溯，分组无已知血缘泄漏；所有仍需人工确认的事实显式列出。

### 5. 准备 ROI、逐帧真值及正式目录（自动准备，真人确认）

- [ ] 为每源准备 subject/background 的区域身份说明、每个 clip 的起点 anchor 草稿，以及覆盖每个原帧的 box / visibility / 可选 mask 草稿。
- [ ] 将自动或插值辅助结果明确标为 draft，输出便于逐帧确认的审阅材料和帧索引；未确认内容不得填写成人工 `author` / `reviewed_at`。
- [ ] 汇总需要真人确认的区间、区域身份、遮挡和轨迹；机器可先完成全部源的草稿，不因第一个未确认项停止其他源的准备。
- [ ] 实际确认后，按设计精确 schema 生成独立 `regions`、`truth` 和必要 `context` 文件，再生成真实 `catalog.json` 并绑定 FileIdentity。
- [ ] 未来帧 truth 仅交控制构造器和评估器；测量器只收到每 clip 起点 anchor，不泄漏未来 box / mask / visibility。

**完成标准：** 正式目录 24 源的依赖可访问、结构和身份有效；草稿与已确认真值清晰区分。正式字段不能为了让校验器接受而伪造人工记录。

### 6. 构造 240 个控制 case 并交付完整审阅包（自动，依赖相应真值就绪）

- [ ] 每源按既有 recipe 构造 10 类：`unchanged`、`allowed_lighting`、`allowed_camera`、`occlusion`、`seam_color`、`local_color`、`gradual_drift`、`cumulative_drift`、`motion_reset`、`camera_jump`，合计 240 个。
- [ ] 使用已有 `build_control_case` 控制通道，保存 recipe、父记录身份、padding mask、原生时间和实验 display_map。不得以普通 manifest 伪装重排帧。
- [ ] 生成可完整播放的原区间/变体材料、逐帧核对材料、case 索引和未填写标签模板；写明源/显示帧区间、区域、detector 及材料路径。
- [ ] 将仍缺人工 ROI/真值的 case 标为待构造；可准备其审阅队列和说明，不能为了出预览绕过正式证据接口或虚构已确认 truth。
- [ ] 控制输出保存在独立目录，不改源媒体或原 VCO-02 证据；播放材料标明是审阅用途，不能反向充当原生颜色分析帧。

**完成标准：** 240 个真实构造结果可追溯，审阅者能逐个找到并完整播放；模板不能按 variant 自动签出 anomaly / normal 真值。

### 7. 完成双人独立观看及分歧裁定（真实人工）

- [ ] 两位不同真人独立完整观看原区间及每个控制变体，逐 case / region / detector 填标签、理由、观看时间和证据。
- [ ] `viewed_interval` 覆盖完整显示区间 `[0,N)`；标签允许 anomaly / normal / not_comparable / unverified，不因构造意图强制正负例。
- [ ] 分歧由不同的第三人实际裁定，保留独立记录和证据身份；一致项不制造裁定记录。
- [ ] 生成并冻结符合设计 schema 的真实 `labels.json`，绑定 corpus SHA；核验作者、时间、区间、证据和分歧处理。

**完成标准：** 双人独立观看记录及必要裁定完整。AI、多代理、静帧审查、自动分数均不能冒充这两位真人。

**真实等待点：** 无真人时，先完成所有可独立执行的准备，再集中交付待确认项、完整播放路径、标签表和填写说明；此时可报告“准备阶段完成/人工审阅待完成”，不能报告 VCO-03 全部完成。

### 8. 校准、一次留出评估及验收记录（自动，依赖正式输入齐全）

- [ ] 用现有校验器核验正式 catalog / labels 及依赖闭包；满足既定阻塞解除条件后，才按任务板记录合法状态转换。
- [ ] 只在 12 个 calibration group 拟合，先封存 `thresholds.json`，再对 12 个 holdout group 评估一次；不以重新运行留出调参。
- [ ] 六类主 detector：`seam_color`、`local_color`、`color_drift`、`cumulative_color`、`motion_reset`、`camera_jump`，分别保留实际结果和不可用原因。
- [ ] 每类 detector 的 calibration 和 holdout balanced error 均严格小于 0.5；每个 split 的正、负类各覆盖至少 6 个独立 source scene，六题材均有有效样本，才满足既定最低可用性。
- [ ] 保存 TP/FP/TN/FN、FPR/FNR、precision/recall、端到端召回、覆盖率、弃权及六题材/source 分层结果、95% Wilson 区间；异常上的弃权计入端到端漏检。
- [ ] 保留 `catalog-snapshot.json`、`labels-snapshot.json`、`thresholds.json`、控制/逐 case 结果、`evaluation.json` 和 `profile.json` 的实际 audit 绝对路径与身份。
- [ ] 六类均有真实 ready profile 和留出证据才可登记全部完成；partial / unverified 如实保留，不降低匹配门槛、改标签或重复使用留出集凑通过。
- [x] 更新 `VCO-03-verification.md`、当前 handoff 和任务板的实际证据；仅数据准备未改源码时不重复跑软件测试。若确实修复源码，执行设计指定定向检查；全库回归仍留到 VCO-08。（本轮数据核对退出 0，未改生产源码/测试，未运行校准或 pytest；不代表第 8 项其余门槛通过。）

**完成标准：** 设计 Acceptance 全部有证据对应。只创建 JSON、校验命令退出 0 或 fixture_only 测试通过均不足以完成真实验收。

## 执行入口与交付要求

所有 Python 命令先通过既有 bootstrap；以下仅是入口示例，整理本清单时未执行：

```powershell
. ./scripts/bootstrap.ps1
Initialize-VideoAiEnvironment 'vco03-remaining-cli-help'
Invoke-VideoAiNative $VideoAiPython @('-B','D:/code/py/video-ai/scripts/continuity_audit.py','--help')
exit $VideoAiExitCode
```

现有子命令为 `validate-catalog`、`annotation-template`、`calibrate`、`analyze`。它们要求显式 `--config`，其余输入使用 `--catalog`、`--labels` 或 `--manifest` 的绝对文件路径。校准前必须满足上面的人工和冻结条件。返回码 0 为命令成功保存结果，2 为拒绝，3 为不足/不适用，124 为超时；结构校验成功不代表实际素材、标注或校准通过。

每次交付给出：实际完成的清单项、八阶段计数、产物绝对路径、命令日志/退出码、失败或待确认项和下一具体动作。素材、RGB、大文件和运行产物放 D:/VideoSi；源码与交接文档留仓库。准备命令显式分批，沿用单命令 300 秒、校准总预算 600 秒的既定限制；超时保留现场，不无限后台重启。

`.git` 只读，保留已有 VCO-02/VCO-03 工作区改动。不启动模型推理、GPU 服务、付费生成、生产发布或后继任务。本次授权足以继续公开许可素材准备，无需重复请求搜集许可。
