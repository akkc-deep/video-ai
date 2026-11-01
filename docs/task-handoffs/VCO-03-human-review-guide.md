# VCO-03 视频观看与表格填写指南

> **当前AI路线已完成：** 无需填表或重复下载。六项证据已集中交付，新几何通道90项完整结果、3个新来源一次检查、50项测试通过。相机新检查3项跳变全检出且12项正常无误报；动作仍有重播弃权，未启用生产。见 [最终交付](VCO-03-AI-final-results.md)。以下为历史记录。

> **当前交付更新：** 用户选择AI实验校准、无需人工表格；该路线已完成240项实验结果，见 [AI校准结果](VCO-03-AI-calibration-results.md)。下文的真人依赖仅保留为原正式benchmark记录，不阻塞本次AI交付。

更新日期：2026-10-25。审阅者：**akkc、qzw**。

> 当前进度更新：两份filled表已接收，标签940项相同、1520项不同，缺观看时间且包含AI建议/整体转录；未自动当作独立真人标签。用户已授权后续AI审核，新增4源技术审核入口：`D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/replacement-manual-intake-20261025/AI-review.html`。下文保留原填写方法供查阅，不要求重复填写原表。


本指南对应已经准备好的 **20 组素材、200 个控制视频**。每位审阅者的判断表有 **2,460 行**，这些行分别记录同一视频的不同区域和不同检测项，并不是 2,460 个视频。

你们已报告“两位真人判断一致”，称呼也已登记。已经确认的画面、选区和修正位置不用重复验收；接下来要把实际观看和逐项判断对应到表格。当前新补下载的 4 个候选素材尚未全部完成审阅准备，**不在这两份判断表中**，之后单独补材料。

## 1. 先打开哪些入口

| 用途 | 入口 |
|---|---|
| 全部表格、填写说明和视频入口 | [统一入口](D:/VideoSi/projects/video-ai/continuity-benchmark/review-akkc-qzw-20261025/index.html) |
| akkc 的视频材料 | [A 视频入口](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/index.html) |
| qzw 的独立视频材料 | [B 视频入口](D:/VideoSi/projects/video-ai/continuity-benchmark/public-sourcing-725743bd99ca43f79aa47a85010ce0e7/remaining-work/manual-intake-20261024/confirmed-roi-controls-002/review-package/reviewer-b.html) |

用浏览器打开 HTML 页面，用 Excel/WPS 打开 CSV 表格。如果本 Markdown 阅读器不能打开本地链接，可复制链接中的 `D:/VideoSi/...` 路径，粘贴到资源管理器地址栏。

视频页面中的旧 A/B 空表链接是原始模板。本轮请填写下面以你们名字命名的表，避免填错版本。

## 2. 需要看哪些视频

以下 20 组，每组包含一个原片区间，以及 10 个控制视频。页面顶部可以按 `source_id` 跳转到对应组。

| 类别 | 页面中的 source_id | 内容辨认提示 | 每个控制的显示帧数 N |
|---|---|---|---:|
| 人物 | `iso_people_01` | 行走人物的腿和鞋 | 120 |
| 人物 | `iso_people_02` | 使用手机的女性 | 120 |
| 人物 | `iso_people_03` | 书写的手与钢笔，使用已修正版本 | 100 |
| 人物 | `iso_people_04` | 黑衣人物 | 96 |
| 动物 | `iso_animals_01` | 牛吃草 | 96 |
| 动物 | `iso_animals_02` | 木桩上的鸟 | 120 |
| 动物 | `iso_animals_03` | 树枝上的蜘蛛 | 120 |
| 动物 | `commons_144217105` | 青蛙，灰白画面 | 120 |
| 交通 | `iso_transport_01` | 地铁/列车视角中的建筑 | 120 |
| 交通 | `iso_transport_02` | 路口的黄色车辆，使用已修正选区 | 120 |
| 交通 | `iso_transport_03` | 航拍路口 | 120 |
| 交通 | `iso_transport_04` | 水面上的帆船 | 240 |
| 户外 | `iso_outdoor_02` | 近景绿叶 | 120 |
| 户外 | `iso_outdoor_03` | 树木与环境画面 | 120 |
| 户外 | `iso_outdoor_04` | 夕阳水面波纹 | 120 |
| 室内 | `iso_indoor_01` | 冲泡咖啡与杯子 | 120 |
| 室内 | `iso_indoor_02` | 熔岩灯，使用已修正背景选区 | 120 |
| 室内 | `iso_indoor_03` | 笔记本键盘与打字 | 100 |
| 室内 | `iso_indoor_04` | 失焦的办公室画面 | 100 |
| 动画 | `animation_caminandes` | Caminandes 羊驼动画 | 96 |

每组都需要看以下 10 个控制视频：

| 表格中的 variant | 页面含义 | 观看时留意 |
|---|---|---|
| `unchanged` | 原样对照 | 原区间本身的变化；也是同组色彩比较的基准 |
| `allowed_lighting` | 已声明的缓慢光照变化 | 亮度变化及其可见程度 |
| `allowed_camera` | 已声明的连续运镜 | 连续平移和缩放 |
| `occlusion` | 主体局部遮挡 | 遮挡部位、时段，以及对应区域能否比较 |
| `seam_color` | 中点色彩变化 | 中点前后是否发生明显色彩跳变 |
| `local_color` | 主体局部色偏 | 指定局部是否变色，其他区域是否受影响 |
| `gradual_drift` | 逐渐色漂 | 相对原样对照是否逐渐偏色 |
| `cumulative_drift` | 三段累计色漂 | 三段之间是否累计偏色 |
| `motion_reset` | 运动重置控制 | 主体运动是否重复、重播或突然重置 |
| `camera_jump` | 中点相机跳变 | 整体画面是否突然跳动 |

这些名称说明构造方式，**不替代你们实际看到的判断**。变化太弱、无法判断时，可以填 `unverified`。

## 3. 怎么看、按什么顺序填写

1. **两人分别使用自己的表。** akkc 填 `akkc.csv`，qzw 填 `qzw.csv`；各自记录真实判断，不由 AI 或另一份表代填。
2. **一次处理一组素材。** 先完整看该组原片区间，再完整看 `unchanged`。比较颜色时，以同组 `unchanged` 控制为直接基准。
3. **依次完整播放该组其余 9 个控制。** 不只看封面、联系表或中点截图。需要时可以暂停或回放，但实际观看应覆盖完整区间。
4. **看完一个控制，再填它对应的多行。** 在表格里筛选 `case_id`，或用页面中的 `case_slot_id` 查找对应视频。通常一个控制有 12 行；`iso_people_03` 有手、钢笔、背景三个区域，每个控制有 18 行。
5. **每行按指定区域和检测项判断。** 不只填写与变体同名的一项；例如 `local_color` 视频，也要分别判断其相机跳变、运动重置等项目。
6. **同一控制的多行可以复用同一次真实观看记录。** 不需要为了每一行重新播放，`viewed_at` 也可以填写同一次实际观看时间。

如果之前已经完整看过当前这个版本，并能确认具体判断和观看信息，可以复用已有观看事实。记不清某项结果或观看时间时，先留空并说明缺项，不凭猜测补齐，也不把填表时间自动当作观看时间。

### 视频与表格怎样对应

| 表格列 | 用途 |
|---|---|
| `source_id` | 找到所属素材组 |
| `case_slot_id` / `case_id` | 找到具体控制视频 |
| `variant` | 该控制的构造类型 |
| `base_review_video` | 原片区间的完整本地路径 |
| `control_review_video` | 这一行对应的控制视频完整路径 |
| `region_id` | 本行判断的区域 |
| `detector_id` | 本行判断的变化类型 |

## 4. 哪些表需要填

| 表格 | 谁填 | 当前内容 | 是否需要填写 |
|---|---|---|---|
| [akkc.csv](D:/VideoSi/projects/video-ai/continuity-benchmark/review-akkc-qzw-20261025/akkc.csv) | akkc | 200 个控制、2,460 行判断 | 需要 |
| [qzw.csv](D:/VideoSi/projects/video-ai/continuity-benchmark/review-akkc-qzw-20261025/qzw.csv) | qzw | 同一批控制的独立判断 | 需要 |
| [lineage.csv](D:/VideoSi/projects/video-ai/continuity-benchmark/review-akkc-qzw-20261025/lineage.csv) | 确知来源事实的人补一份即可 | 20 个来源的原片/项目关系 | 只补有依据的信息；不知道可留空 |

以下表格**当前不用填写**：

- 旧的 `labels-reviewer-A.blank.csv`、`labels-reviewer-B.blank.csv`：本轮使用上面的命名表，不重复填旧模板。
- 已经确认过的 `roi-review.csv`、旧选区/轨迹草稿：不重复验收已确认内容。
- 第三人裁定表：你们已报告判断一致，目前不用填；如果实际逐项记录出现分歧，再由另一位第三人裁定对应项。
- 新增 4 个候选素材的控制判断表：尚未全部准备好，之后单独提供，不在现有表里强行补行。
- `catalog.json`、`labels.json` 等正式 JSON：由我整理和校验，不需要你们手写。

## 5. 两份判断表怎么填

### 5.1 只填写这 5 列

| 列名 | 填写内容 | 注意 |
|---|---|---|
| `label` | 下节四个英文值中的一个 | 根据本行的区域和检测项判断 |
| `viewed_start` | 实际完整看过该控制时，填写本行 `required_viewed_start` | 通常为 `0`；没完整看过则先留空 |
| `viewed_end` | 实际完整看过时，填写本行 `required_viewed_end` | 按该行数值，不要全部填 `120` |
| `viewed_at` | 本人实际观看该控制的时间，带时区 | 格式：`YYYY-MM-DDTHH:MM:SS+08:00`；不能确认就先留空，并在理由中说明 |
| `rationale` | 一句实际判断理由 | 说明哪里变化、哪里无法比较，或为什么无法确定 |

`author` 已填好。其余列保持原样，尤其不要改 `frame_start`、`frame_end`、`display_frame_count`、`required_viewed_start`、`required_viewed_end`。

`evidence_path` **可以先留空**。我导入时会绑定你们实际填写完成的 CSV 作为记录依据，不要求另外寻找截图。

### 5.2 label 的四个值

| 填写值 | 含义 | 判断理由写法举例 |
|---|---|---|
| `anomaly` | 该区域确有对应的不连续或色偏 | “中点后主体颜色突然变化” |
| `normal` | 该项可以判断，未见对应异常 | “该背景未见相机跳变” |
| `not_comparable` | 遮挡、出画、身份变化等使对应无法有效比较 | “遮挡期间看不到该部位，无法比较” |
| `unverified` | 变化不明显、证据不足或本人无法确定 | “变化太弱，无法确定是否逐渐偏色” |

上面的理由只是写法示例，不是预填答案。

**这里判断的是视频中的对应变化，不是检查控制视频是否制作正确。** 例如，局部色偏控制确实出现明显色偏时，对应项目可以是 `anomaly`；“钢笔选区已经修好”属于构造确认，不能据此把所有项目统一填成 `normal`。已声明的合理光照、运镜或遮挡，也不因画面发生变化就直接判为异常。

### 5.3 region_id 表示哪里

| 值 | 本行判断区域 |
|---|---|
| `subject` | 已声明的主体 |
| `background` | 已声明的背景 |
| `hand` | 手部，出现在修正后的 `iso_people_03` |
| `pen` | 钢笔，出现在修正后的 `iso_people_03` |

### 5.4 detector_id 表示判断什么

| 值 | 判断内容 |
|---|---|
| `seam_color` | 中点/接缝前后是否突然变色 |
| `local_color` | 指定主体或局部区域是否出现色偏 |
| `color_drift` | 相对原样参考，色彩是否逐渐偏移 |
| `cumulative_color` | 跨三段的色彩是否累计偏移 |
| `motion_reset` | 主体运动是否突然重复或重置 |
| `camera_jump` | 整体相机画面是否突然跳动 |

### 5.5 显示帧范围怎么填

`[0, N)` 表示完整观看第 `0` 到第 `N-1` 帧，结束边界填写 `N`：

| 本行 required_viewed_end | 完整看过后填 viewed_start | 完整看过后填 viewed_end |
|---:|---:|---:|
| 96 | 0 | 96 |
| 100 | 0 | 100 |
| 120 | 0 | 120 |
| 240 | 0 | 240 |

这只是完整观看后的填写方法，不能用要求范围代替尚未完成的观看。

### 5.6 一行示例

假设某行要求检查“某控制视频的背景有没有相机跳变”，完整观看范围是 `[0,120)`，本人实际看完后未见跳变，可以这样记录：

| 列 | 示例填写方式 |
|---|---|
| `label` | `normal` |
| `viewed_start` | `0` |
| `viewed_end` | `120` |
| `viewed_at` | 填本人实际观看时间，不能照抄示例时间或用当前时间补签 |
| `rationale` | `完整观看后，背景未见整体相机跳变` |

该示例不代表任何一个现有视频已经得到这个判断。

## 6. 来源核对表 lineage.csv 怎么填

这一表核对“素材是否来自同一原片或同一生成项目”，不是判断画面质量。只填写有依据的信息；不要求你们凭画面猜来源，我也会继续整理已保存的来源证据。

| 列名 | 填写内容 |
|---|---|
| `same_original_or_generation_group` | 确知的原片名、拍摄片段或生成项目名。同一原片的裁剪、转封装或衍生版本写同一个名称；未知可留空或填 `unknown` |
| `independence_evidence` | 支持上述关系的网页、文件路径或具体事实；没有依据就留空或说明未知 |
| `reviewer` | 实际填写者，`akkc` 或 `qzw` |
| `confirmed_at` | 实际核对这些来源事实的时间，格式同 `viewed_at` |

其他列和 `status` 保持原样，由我依据记录整理最终分组。不同网址、不同文件名或同一作者名，本身都不能直接证明原片/生成血缘是否独立。

## 7. 保存后怎么交给我

1. 用 Excel/WPS 打开 CSV，保留原表头、列和现有行。
2. 使用 **CSV UTF-8** 格式另存，建议文件名如下，避免覆盖原始表：

   ```text
   akkc-filled.csv
   qzw-filled.csv
   lineage-filled.csv
   ```

3. 保存到当前表格目录即可：

   ```text
   D:\VideoSi\projects\video-ai\continuity-benchmark\review-akkc-qzw-20261025
   ```

4. 告诉我已填写文件的保存路径。若只有部分填写完成，也可以先交部分，不用为了填满表格猜标签或观看时间。
5. 我负责检查缺项、格式、真实记录的对应关系及分歧，再生成正式 JSON 并绑定文件身份。正式输入完整以前，不运行真实校准和留出评估。

如果你们另有已经保存的逐项判断记录，可以直接提供其路径，由我转换格式，不必重新抄进这两份表。
