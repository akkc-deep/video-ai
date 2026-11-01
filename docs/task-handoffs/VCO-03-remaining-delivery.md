# VCO-03 剩余清单执行交付

**最新：20源ROI已确认，200/240真实控制已构造并复核；双人控制标签/评估为0。下文前轮0计数是历史快照，当前以文末“用户最新版ROI确认后的更新”和新待审入口为准。**

2026-10-24 手动下载续办：21/21 请求文件完整解码；18 个新来源颜色 resolved，已完成 2,172 个连续原生 ready 帧。复用旧三段 312 帧后，共 21 段 / 2,484 个完整 ready 原生帧。31 个待确认项目来源共 3,593 帧播放/逐帧材料、7,186 行未签署 ROI；240 个原有 case 位置保留，实际 ROI 确认/控制/真人审阅/评估均为 0。

拟用 24 个位置已有 20 个颜色/原生帧就绪：people 4、animals 4、transport 4、outdoor 3、indoor 4、animation 1；另有一段人物备用。至少还缺 outdoor 1、animation 3，内容/独立血缘未确认还可能增加替换需求。Spring 和狗缺必要颜色声明，黄花现有解释不受支持；不得补猜 Rec.709。任务保持 **BLOCKED**，未启动 VCO-04；软件实现、生产配置和原媒体未改。

## 直接打开的材料

- [集中审阅入口](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-package/index.html)：31 源按 ready/拟用位置排序，复用旧封存包的十源资产。
- [操作说明](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-package/README.txt) · [区间/血缘确认空表](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-package/source-decisions.blank.csv)。
- [240 个待构造位置](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-package/case-queue.draft.csv) · [许可/署名/改编说明](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-package/attributions.json)。
- [逐源进度](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-progress.json) · [新验证结果](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/followup-verification.json) · [命令与退出码](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/commands-index.json)。

## 八阶段计数

| 阶段 | 实际计数与边界 |
|---|---|
| 候选 | 复用原24个位置，六题材各4；来源/分组仍未冻结。新发现4个许可明确的替代来源，下载均超时，不计完整素材。 |
| 已下载 | 旧11个媒体版本/10项目来源 + 新21文件/21项目来源 = 32版本/31待确认项目来源。4个包复制MP4派生副本不增加来源数。 |
| 颜色可用 | 21项目来源：旧3 + 新18。新21中，狗/Spring unknown、黄花 unsupported；旧7个不适用来源保持拒绝。 |
| 完整原生区间 | 21段、2,484个选中ready原生帧，其中新18段2,172帧；内容/无切镜/血缘仍待真人确认。 |
| ROI已确认 | 0。31源3,593帧、7,186行未签署主体/背景粗框；author/reviewed_at/confirmed为空，起点anchors与未来truth分开。 |
| 控制已构造 | 0。240个原case_slot_id完整保留，rendered_media_path为空；原片播放另列，不能当作控制。 |
| 真人已审阅 | 0。两份独立空表各2,880行，另有第三人裁定空表；当前不得提前填标签。 |
| 已评估 | 0。没有正式catalog/labels、12/12冻结、阈值拟合、留出评估或真实profile。 |

## 实际完成与复用

用户手动下载的21文件均完整解码。`854167-hd_1920_1080_25fps.mp4` 与旧下载前缀及原预期长度吻合；用户明确确认 `video.mp4` 是办公室来源、下载器自动改名，该确认只登记来源对应，不冒充完整观看或ROI确认。办公室文件mtime变化但字节/SHA一致时保留旧记录，并在新audit重做颜色初查；未放宽身份校验。

Spring原WebM保留，新增独立视频包复制MP4：原生PTS/time_base、名义fps、尺寸、流/逐帧颜色和每个压缩视频包SHA均相同；容器平均速率头差异留证。其primaries/transfer缺失，所以只有审阅材料，没有分析RGB。

新18源通过既有 `decode_analysis_frame` 分批生成全部真实srgb_rgb24_v1，再由 `load_color_analysis_set` 实际读取RGB、核对长度/SHA与退出闭包。复用旧三个ready区间，不重新实现分析器、不重下旧原件。新来源的每批预算/退出码/原文件身份保存在对应interval-state及audit。

静帧整理发现并保留被拒绝初选：模特/鸟入画前空镜、蜘蛛早段主体裁切、咖啡杯尚无注入、熔岩灯初段无液滴；Spring初选在167→168切镜，改为[168,264)。当前草稿已重新取区间。这些不是人工完整观看记录。

已为全部新来源生成逐帧图、完整播放副本、原生索引、主体/背景身份说明、粗关键帧插值ROI、起点锚点和联系表。列车视角主体出画、办公室失焦、水面无稳定主体、暗液滴形变及弱运动均具体标明，可能应拒绝/替换；框存在不代表准入。

## 连续原生区间

以下为全部颜色ready候选，半开原帧区间。精确原生PTS/time_base及身份见对应source-review.json/frame-index.json。均未获真人内容/ROI确认。

| 来源 | 原帧区间 | 帧数 |
|---|---:|---:|
| animation_caminandes | [240,336) | 96 |
| commons_144217105 | [240,360) | 120 |
| iso_animals_01 | [5,101) | 96 |
| iso_animals_02 | [40,160) | 120 |
| iso_animals_03 | [96,216) | 120 |
| iso_indoor_01 | [200,320) | 120 |
| iso_indoor_02 | [300,420) | 120 |
| iso_indoor_03 | [5,105) | 100 |
| iso_indoor_04 | [5,105) | 100 |
| iso_outdoor_02 | [6,126) | 120 |
| iso_outdoor_03 | [6,126) | 120 |
| iso_outdoor_04 | [6,126) | 120 |
| iso_people_01 | [6,126) | 120 |
| iso_people_02 | [6,126) | 120 |
| iso_people_03 | [5,105) | 100 |
| iso_people_04 | [48,144) | 96 |
| iso_transport_01 | [22,142) | 120 |
| iso_transport_02 | [6,126) | 120 |
| iso_transport_03 | [6,126) | 120 |
| iso_transport_04 | [12,252) | 240 |
| shotstack_scott | [120,216) | 96 |

## 集中交给真人的内容

打开新审阅入口，先处理拟用于24位置的ready片段。完整播放，填写区间/同一主体背景/血缘/题材接受或拒绝及理由，再逐帧修订每源 `roi-review.csv` 的归一化框和visibility。实际确认者逐行填写author、带时区reviewed_at、confirmed及必要证据路径。另存填写后的表并给出绝对路径，无需手写JSON。不能确认的对象、出画、遮挡或独立性如实拒绝/待确认。

**暂勿填写双人case标签。** 相应真实ROI/truth就绪后才通过既有控制入口构造10类实际变体，再交两位不同真人独立完整观看原段及变体并逐case/region/detector标注；分歧由不同第三人实际裁定。机器静帧检查、插值、用户文件名确认均不能代替这些步骤。

## 尚缺的自动输入

拟用 24 个位置已有 20 个颜色/原生帧就绪：people 4、animals 4、transport 4、outdoor 3、indoor 4、animation 1；另有一段人物备用。至少还缺 outdoor 1、animation 3，内容/独立血缘未确认还可能增加替换需求。Spring 和狗缺必要颜色声明，黄花现有解释不受支持；不得补猜 Rec.709。

新尝试的3D工具/星空图形、树枝瀑布/白桦叶4个来源都有明确CC0页面及直链，但原生下载仍握手/读取超时；完整失败记录及部分文件在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-attempts/`。不无限重试，不计作取得或颜色可用；原许可/来源网页证据在同级replacement-source-research.json。后续从这些实际缺口继续，不能用下载数量、不同URL、签名或改颜色标签补足独立源。

## 新验证结果与边界

新21源逐源检查完成，18源共2,172帧实际RGB/只读退出闭包通过；旧三段312帧也重新只读核对，合计2,484个选中帧。旧封存包2,769个文件身份无变化。旧523份记录/522个不同源帧的历史验证保留，其中有探索/拒绝帧；不能把它们加进本次选中区间凑数。

新包验证了31源/3,593帧/7,186行未签署ROI、原240个case ID、两份2,880行空表及全部离线链接；16/16冻结软件文件的大小/mtime/SHA未变。逐源结果、实际命令/日志/退出码、最终封存身份见上述验证及commands-index；所有数据准备命令采用显式小批次，未启动校准。历史101项软件检查未重跑，本次没有生产代码/测试/依赖/实际配置改动，全库仍留VCO-08。

旧封存包继续保留在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/review-package`；旧进度/文档快照在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/prior-progress-and-documents`。新进度已写回S/remaining-progress.json。后续使用本次manual helper，**不要运行带旧312/10源硬编码计数的vco03_sync_delivery.py或旧final-check来覆盖新进度**。VCO-03仍BLOCKED，不准备VCO-04。


用户内容反馈更新：用户表示“我认为里面的视频都没有问题”。按上一轮明确要求的20段拟用ready视频范围，已登记内容接受意见；原话、范围解释、片段身份在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/user-content-feedback.json`。没有据此补签完整播放区间、逐帧ROI、独立血缘或双人控制标签。下一步集中核对入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/roi-review.html`（20段、2,388帧/4,776行框草稿）。原封存审阅包不变，ROI确认/控制/评估计数仍为0，VCO-03保持BLOCKED。


ROI修订：用户指出熔岩灯iso_indoor_02的n=368蓝色背景框包含液滴，已在独立版本 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/roi-revisions/iso_indoor_02-background-v2` 修订背景框并检查全部120帧。主体框、原生RGB/PTS、旧封存包保持原样；仍未签署ROI。后续使用 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/roi-revisions/latest-revisions.json` 中的覆盖路径，不用旧背景框生成正式truth。更新待审入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/roi-review-v2.html`。


ROI修订：路口iso_transport_02的n=125主体框偏到相邻车辆，现已为全部120帧修订黄色车主体粗框；背景/原生证据不变，仍待逐帧确认。新版本 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/roi-revisions/iso_transport_02-subject-v2` 已并入latest-revisions.json，保留此前熔岩灯修订。待审入口更新为 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/review-feedback-001/roi-review-v3.html`。


2026-10-24 用户最新版ROI确认后的更新：用户表示“全部看完了 现在没问题了”，已按此前明确的20段最新版逐帧材料登记接受，实际作者标识conversation_user，reviewed_at使用该确认接收时间并在凭据解释；不虚构姓名、第二审阅者或控制观看。对应2,388帧/4,776行ROI已生成独立精确schema的regions/truth，使用两项最新修订覆盖路径。

已通过既有build_control_case/ControlProvider和真实VCO-02 reader构造这20源的200个控制（总240位置仍缺40），共23,880个实验显示帧，保留原生/实验两套时间、recipe、原帧身份、每帧控制RGB摘要、原尺寸padding mask及完整播放/逐帧材料。全部播放N与每帧PTS逐一核对；另对每case首/中/末帧实际重构RGB及padding，共600帧，核对PNG与原生控制缩图。未使用普通manifest冒充重播；原片/原分析记录不改。

新双人待审入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/review-package/index.html`；独立A/B空表、裁定表、240位置与200真实播放路径在该目录。两份表各2,880行，其中2,400行为已构造待观看、480行未构造不得填。尚无任何真人控制标签；variant名称不签出anomaly/normal。

验证：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/control-delivery-verification.json`，逐源verification/与sealed-case-identities/保存闭包。原两版封存审阅包合计8785文件与16/16冻结软件身份未变；未重跑pytest。审阅编码试运行曾因-r与passthrough冲突、concat微秒逐段取整漂移而拒绝，已保留失败audit；使用累计边界微秒差和原生tick末帧duration，严格复核所有PTS后才登记构造成功。校验脚本曾误比较FileIdentity的verified_at观测时间，改为既有稳定身份比较；大小/mtime/SHA仍严格核对。

总体仍BLOCKED：至少还缺1户外/3动画可用来源，独立血缘与12/12 split尚未确认/冻结；两位真人需独立完整观看原区间及真实变体并逐region/detector填标签，分歧由第三位真人裁定。另外已实际发现青蛙原片的1/1000时基有33/34步长，当前校准入口仅接收恒定步长；此兼容问题单列，不能靠改原PTS或跳过检查解决。本轮没有拟合/留出/真实profile，也不启动VCO-04。


控制审阅本轮反馈更新：用户表示“其他的没问题了”。已保留people_03的手部遮挡/钢笔色偏两项位置问题，以及20项allowed_lighting和熔岩灯两项drift的“不明显”观察；其余项目登记为未提出额外构造问题，不按variant或“没问题”自动写出normal/anomaly。汇总原话和范围解释：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/review-feedback/round-001-summary.json`。people_03两种操作的新选区已做100帧草稿，当前待用户确认：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/correction-drafts/people_03-targets-v3/index.html`；旧控制和正式truth尚未替换，须确认新区域后再重建受影响的控制。没有第二位审阅者、完整case/region/detector标签或裁定记录；当前仍不校准，BLOCKED不变。


people_03选区修订：用户指出第85帧粉色钢笔选区不准。原生放大图确认旧轮廓碰到拇指且关键帧插值未跟上写字运动；已在100帧新草稿中使用原生轮廓和逐帧笔环位置对齐，保持绿色手部框不变。第85帧拇指/纸面取样点未选中、笔杆/笔尖内部点选中；整体仍待真人确认，未重建控制或替换正式truth。最新待审页：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-001/correction-drafts/people_03-targets-v5/index.html`；本次反馈和检查在confirmed-roi-controls-001/review-feedback/people03-target-n85-001.json。v4失败的严格像素检查及原audit保留，没有将失败草稿提升为真值。


2026-10-25 people_03修订更新：用户回复“这次可以了”，已将最新版v5选区接受意见与版本身份独立登记（接受范围按对话解释，不补造额外原片观看、case标签或第二人）。正式手部/钢笔/背景三类区域与100帧真值已分别保存；钢笔使用已接受的原尺寸mask。

新版本 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002` 复用190个旧控制，重建people_03的10个；其中两项按用户明确目标分别选择hand遮挡、pen局部色偏。仍使用既有verified reader、build_control_case和ControlProvider，在像素生成前显式记录recipe.local_region_ids选择；未改生产源码/算法幅度。全部100帧检查色偏在钢笔mask之外像素不变、遮挡严格符合手框上半部规则；其余8类800帧原生控制RGB与旧版逐一完全相同。10类又独立重算30帧RGB/PNG/padding，播放帧数与所有原生实验PTS通过。

请从 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/people03-corrected.html` 直接查看修订的两项；完整200控制新入口是 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/index.html`。其他来源和旧版均保留，不重计成210个case。手/笔独立region后，正式ROI为4,876行，双人空表各2,940行（2,460行已构造待审，480行未构造）。没有将“其他没问题”写成normal/anomaly，实际双人标签与校准均0。

新校准兼容限制必须保留：当前校准循环默认选择所有subject区域，还不会重放这两项用户指定的目标子集。对应选择、输入和构造器适配器已存 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/calibration-target-replay-requirements.json`，正式校准前须支持并验证精确重放，不能用默认的双subject构造替代本次已审阅的两项。此前青蛙33/34毫秒步长、4个来源缺口、血缘/split、独立双人标签与裁定依赖仍在，任务保持BLOCKED，无留出或VCO-04启动。数据辅助脚本改变不影响16/16冻结实现身份，未重跑pytest。

验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/correction-delivery-verification.json`；日志/退出码见同级commands-index.json。最新进度已写回S/remaining-progress.json。


2026-10-25 修订材料接受：用户对刚交付的people_03手部遮挡/钢笔局部色偏两项新版回复“没问题”。已按实际控制文件及播放文件身份登记为作用位置/画面可接受，关闭本轮位置问题；原话在 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-feedback/people03-corrected-material-acceptance.json`。此前22项弱可见性反馈与已解释的people_01现象继续保留。该意见没有扩写为case/region/detector的normal/anomaly标签，也未补造观看范围/时间、第二位真人或裁定。下一位真人独立审阅入口为 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/reviewer-b.html`，B表仍为空。本轮画面与位置反馈已汇总；正式标签、其余素材/血缘/split、时间兼容及目标选择重放仍未齐，VCO-03保持BLOCKED，无校准。


### 2026-10-25 继续任务：校准兼容修复与集中材料

用户要求“继续任务啊”。本轮复用已确认素材/ROI/200个控制，修复青蛙33/34ms原生PTS被等间隔门槛误拒、已接受的挡手/钢笔变色不能由正式校准重放的问题。catalog source可选control_targets绑定真实授权及subject ID并参与corpus SHA；profile复核也直接核对原区域身份和原生时序，拒绝修改后重新计算身份的控制时间/角色。参数、变换幅度、原媒体与已审材料保持原样。

最终五文件检查106 passed，退出0，日志 `D:/VideoSi/cache/video-ai/logs/vco03-compatibility-final-targeted-458c8400d9774061a402c853099cf89c.log`；初始5项RED及profile篡改链RED均有记录，修复后GREEN。实际20源/2,388帧原生区间核验通过；people03全部10变体/1,000帧正式构造器RGB及padding与既有材料一致。封存审阅材料/控制共39,207个唯一文件身份未变；历史16软件身份中5个按本修复改变，其余11个保持一致，新快照在本轮目录，旧快照保留。独立审查的一项Important已按RED/GREEN修复；一项Minor保留：普通profile适用域保守检查整片时步，区间外时步可能导致弃权。未运行全库、真实拟合或留出。

新增候选下载3项中途/握手超时、1项403，均留有限尝试证据；未把partial计为下载。仍缺1户外/3动画。集中入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/index.html`；补缺下载入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/manual-downloads-20261025-remaining/download-links.html`；兼容20源清单 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/final-code-verification/prepared-sources.compatible.partial.json`；验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/continuation-verification.json`；命令/退出码 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/continuation-20261025/commands-index.json`。已审位置意见不需重复确认；正式A/B逐case-region-detector独立标签仍为0，独立血缘及12/12分组未冻结，真实profile为0。VCO-03仍BLOCKED，VCO-04不启动。


2026-10-25 新下载及真人称呼更新：新增4候选实际下载到旧manual-downloads-20261024目录，本轮已完整解码/颜色resolved 3项（白桦、星空、光斑），3D工具仍为xltd临时文件。白桦和光斑各120个原生帧已就绪，共240帧；星空为稀疏暗背景，自动区间提议未通过普通非黑/纹理启发式，已保留整片联系表，尚未确认区间/稳定区域，未伪造ROI或构造控制。新增ROI确认/控制/真实标签仍为0。

用户明确“我和另一位真人判断一致”，随后提供“我叫akkc，另一个人叫qzw”；已保存真实声明与称呼，历史conversation_user对应akkc，未据此补猜逐项类别或观看时间。两份现有200控制的命名表各2460行，仅预填author；来源核对表另存一份。全部当前填写入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/review-akkc-qzw-20261025/index.html`，说明列明只填label/viewed_start/viewed_end/viewed_at/rationale，evidence_path可由导入程序绑定本表，原ROI和旧空白模板不用重填。新增材料进度 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/latest-progress.json`。未改生产源码/测试，未重跑已通过的106项；未执行真实校准或后继任务。


### 2026-10-25 已交两表与后续AI审核

用户先后报告akkc/qzw已填完，并明确“后面的视频我也都让ai审核”。已保留两份提交副本并核对2460行/200控制：结构错误均0，标签相同940、不同1520，双方viewed_at各缺2460。akkc原证据标为AI代填建议，qzw为整体未发现异常反馈转录，故不把表格差异自动记作已验证真人分歧，也不伪造观看时间、裁定或正式标签。接收/差异证据 `D:\VideoSi\projects\video-ai\continuity-benchmark\public-sourcing-725743bd99ca43f79aa47a85010ce0e7\remaining-work\manual-intake-20261024\replacement-manual-intake-20261025\received-reviews-7db6c87e6fe5\submission-verification.json`。

新增4文件全部完整解码且颜色resolved，各120原生帧共480帧，经原VCO-02 reader与_source_timing复核，完整播放N及每帧PTS全核对；新增960条AI选区草稿保持author=null/confirmed=false。AI检查首尾联系表及概览；星空/光斑未建立可靠同体/背景身份，工具黑背景缺纹理，不能据技术就绪保证正式校准适用性。24位置均有原生帧草案，但正式ROI仍20源、控制仍200/240，来源独立血缘/split仍未冻结。AI入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review.html`；验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review-verification.json`。16项软件身份未变，未重跑既有106项测试；未拟合、未跑留出、未启动VCO-04，任务仍BLOCKED。


### 2026-10-25 原始诊断样例交付

用户同意继续完成带分数、定位和不可比原因的诊断报告。本轮只使用原计划校准侧people_02的10种已有控制，另补people_01的原样/运动重播/相机跳变3种，未改样本归组、未读取留出侧结果、未读取判断表参与计算。现有build_control_case/ColorAnalysisReader/measure_continuity实际计算13个控制、1,560显示帧（各另含1固定参考）、3,107完整比较，输出11,704条分数记录。每次命令<=300秒，校准/阈值拟合入口已在数据脚本中禁止。

为保留16MiB单文件上限，原始比较逐pair分块落盘，未删比较/降采样/修改参数。3,107块身份复核、39块指标摘要独立重算通过；16个软件文件身份保持。原样人物02背景仅覆盖全图3格，119时间比较均无相机支持；人物01原样40/119时间比较具备相机支持，保留其它弃权，不把无分数当正常。六类分数已有可核对的对照，但无异常阈值、无准确率/真人验收通过。

HTML含并排原样/变体、区域与比较类型选择、同来源同项目一致纵轴、曲线点/峰值显示时间定位及算法轨迹框；Markdown、CSV、SVG可独立查看。浏览器两次无头交互检查受本机图形/权限及超时限制未完成，未宣称通过；JS语法和本地资源另验。入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/index.html`；摘要 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/README.md`；证据 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/evidence-verification.json`；来源和命令 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/diagnostic-provenance.json`、`D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/commands-and-browser-status.json`。本轮为数据/报告，未改生产源码或重跑已有106项定向测试，未拟合、未跑留出、未启动VCO-04。VCO-03正式验收仍未完成，状态保持BLOCKED。

最终发布校验：13案例全部3,107块身份再核对、39块摘要重算通过；发布页面45个本地资源（去重计数以实际证据为准）、JS语法和SVG结构通过。最终凭据 `D:/VideoSi/projects/video-ai/continuity-benchmark/diagnostic-report-20261025/delivery-final-check.json`。浏览器交互未自动验证的限制继续保留。


### 2026-10-25 背景覆盖改进试验

用户询问下一步后，继续对已定位的背景支持不足做独立AI输入试验：保留people_02原主体/背景，增补右侧沙发候选，仅提供clip起点/参考锚点；原样、重播、跳变各120帧重算。360控制RGB与旧材料一致，717比较中原两个区域1,434项色彩测量/可比性完全相同，16项软件身份未改。新支持数量和运动/相机分数见 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/README.md`，验证 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/experiment-verification.json`。

v1数据脚本因共享region_ids列表的重复追加触发资源保护，失败状态保留；v2按比较独立复制列表并验证无重复后成功，未放宽资源或算法阈值。新增框仍为AI候选，不替代正式ROI/真值，不改变原200控制或13个独特诊断case计数（共16次输入版本测量），不拟合/读留出/读标签。入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/index.html`；正式VCO-03仍未完成。


### 2026-10-25 背景试验边界核查与统计更正

新增背景后仅改善可测量性，尚未证明检测更准确。原样people02第60帧clip起点框与前段传播框中心相差约[-0.000543,-0.000293]，该重置位移进入速度；仅从保存的该帧速度扣除此分量，第60/61帧分数由75.9977/77.7987降为1.1613/1.7490。此为单变量敏感性复算，未修改生产算法，也不当作正式修复验收。

camera_jump真正发生的第60帧，原背景与AI背景均registration_failed，故相机/运动分数为空；第80帧峰值不能算定位成功。已更正试验表原camera_jump相机支持数为59/119（可用分数56条），不再误写0/119。下一自动工作先隔离跨clip锚点重置对运动测量的影响，再研究跳变处配准失败；只用原定校准侧，不读取留出或拟合阈值。用户暂不需重复观看/补表。

最新说明：[背景试验](D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/README.md)；逐帧核查 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/boundary-investigation.json`；最终身份核查 `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/delivery-final-check.json`。原200控制、13独特诊断case、16项软件身份保持，正式VCO-03仍BLOCKED，未启动VCO-04。


### 2026-10-25 运动边界修复与背景支持复测（最新）

用户要求“继续处理吧”。`continuity_analysis.py` 当前帧对速度改由已通过匹配的左→右仿射作用于左框中心计算，clip起点anchor仍用于选区及后续跟踪，避免anchor重置进入运动速度。两项真实纹理回归先RED（静止误测0.64、平移误测-0.1102），修复后26项分析器单元检查GREEN。独立AI代码审查无Critical/Important问题，未冒充真人视频审阅。

同一people02校准侧、相同右侧AI背景输入复测：原样第60/61帧75.9977/77.7987降至1.1613/1.7490；重播48.6539/50.8001，实际图像变化仍保留。代码前后717比较/三区域2,151项匹配与颜色结果完全相同。原窗口背景跳变时仅10个点通过筛选、原右沙发仅2个，不降低12点门槛。

独立AI背景输入试验改用宽窗户与顶部植物/遮篷；从clip起点传播并使用相同匹配器，两区域跳变对最终13向量覆盖全图4格，C中119/119时间比较可估计相机。新增两个背景区域第60帧camera_jump均5852.9661，峰值第60帧；原样同帧3.5604。原背景本身该帧仍跟踪失败、分数为空，不能写成原区域已恢复。新区域是基于静态概览及有限支持探查调整的AI草稿，并非正式ROI或独立验证集；顶部植物独立运动及跨片背景身份仍待正式核验。原两区域1,434项颜色测量/可比性保持一致。

五个指定测试文件合计108 passed。首次合跑325.54秒超出300秒单命令预算，记录保留且不登记预算合规；随后按文件分成五次270秒硬超时的检查，各批结果/实际时长见commands-and-checks.json。未执行全库；未改匹配参数/阈值、源片、原200控制、正式ROI或判断表。16项软件身份中仅分析器和本单元测试改变，旧快照/旧依赖指纹保留；新测量在独立audit，旧profile不得复用。本轮新增6次测量，原始诊断累计22次、独特case仍13。

入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/motion-registration-fix-20261025/index.html`；说明 `.../README.md`；数值 `.../before-after.csv`；完整测量证据 `.../experiment-verification.json`；命令 `.../commands-and-checks.json`；新软件身份 `.../software-identities.json`；最终交付核查 `.../delivery-final-check.json`。这些省略号均指前述同一目录。

下一步仍以正式准入、独立血缘/12+12分组、可追溯标签和真实校准依赖为准；本轮只证实该校准侧样例的代码修复和测量支持，不宣称整体准确率通过。用户当前无需重复下载、观看或填表。VCO-03保持BLOCKED，VCO-04保持NOT_STARTED。


### 2026-10-25 校准输入依赖审计与40个待构造计划（最新）

用户要求继续任务。本轮只读复用24候选/2,868原生帧，四批各6源经既有ColorAnalysisReader、_source_timing和原始血缘提取核验，最长36.52秒，退出0；20源正式regions/truth通过schema及全帧覆盖检查，4源保持unsigned AI草稿。来源/作者/许可均已补入新24源CSV，包括原空表漏填的Caminandes/青蛙。已选24源未发现已验证媒体原始血缘跨源/跨split冲突，未据此宣称独立性已证实；原12+12位置分配与每题材2+2保持，未冻结。

全部200已有控制recipe及display_map长度与兼容20源输入一致。新副本显式复用兼容清单中的people03 control_targets（hand遮挡、pen改色）；原jobs仍指向无此字段的旧source.json，故新的重放绑定直接指向本批sources-20，避免再走默认全主体。旧源、控制和视频不覆盖。

新增4源的40个待构造计划已绑定实际120原生帧身份、官方_recipe、显示/原生双时间和clip边界；未调用构造器/测量器、未生成RGB或新ControlCase，实际控制仍200。20源部分catalog经过纯结构校验，但缺24源/独立血缘/冻结/正式标签，不能直接运行真实校准。软件16项身份保持，沿用108项定向通过记录，未重复pytest。

统一当前说明 `docs/task-handoffs/VCO-03-calibration-input-status.md`；入口 `D:/VideoSi/projects/video-ai/continuity-benchmark/admission-audit-20261025/index.html`；全部证据、40计划、200重放绑定和来源CSV均在同目录，最终核验delivery-final-check.json。三类真实缺口集中为新增区域/真值、独立血缘与分组、正式审阅记录；保留AI来源，不伪造标签/时间/独立性，不要求重复下载或重填整套旧表。无拟合/留出/VCO-04，VCO-03状态保持BLOCKED。


### 2026-10-25 用户选择AI实验校准并完成（当前交付路线）

用户明确“ai校准的就可以，我不想填表格”，授权独立AI实验路线；设计 `docs/task-designs/VCO-03-AI-experiment.md`。已冻结24来源/12+12分组及2,940条AI弱标签，原表、真人ROI和正式benchmark协议分别保留；AI-only annotation没有冒充真人。当前不需要用户填写表格，旧人工依赖不阻塞本AI路线。

240控制位置均有结果：230完整测量、10固定metadata资源弃权；54,730完整比较、27,710含参考实验帧请求。120校准case结果齐备后只拟合一次，封存阈值身份后才算120检查case。4项有实验阈值：seam4.85805、local8.41253、drift8.41262、camera8.97361；累计/动作缺有效正常类，保持null。相机检查端到端召回28.6%，不隐去弱项。标签940 normal/133 anomaly/120 not_comparable/1747 unverified，新增4源480项全部unverified；不按recipe补造正负，不使用qzw整体normal转录作独立标签。

临时数据脚本初期一次reader超时和JSON格式膨胀拒绝均保留；紧凑分块不放宽16MiB/64MiB资源门槛。两帧缓存32次原生像素/掩码一致性通过；按码值LUT加速构造与原provider的5源/6变体/120帧原生像素/掩码逐字节相同，已有20源的后续快路径逐帧对照原控制RGB摘要。生产算法16项身份保持，不重跑已有108项软件检查。

独立AI代码审查提出“失败producer不能借新receipt获认证”和“检查侧须绑定封存阈值身份”两项Important；4项预期RED→5项GREEN（含有效receipt正例），原source失败产物隔离，合法续算保持原producer/输入摘要/依赖/闭包绑定。10资源失败仅从其原已闭合失败receipt派生空分数与弃权，不补造完整比较。

统一交付 `docs/task-handoffs/VCO-03-AI-calibration-results.md`；报告/实验profile/评估/CSV/冻结输入/最终核验均在 `D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025`。experimental-profile始终production_eligible=false，普通profile校验实际拒绝，没有启动VCO-04。原正式benchmark状态单独保留；本AI实验路线已完成，后续不再索要人工表。
