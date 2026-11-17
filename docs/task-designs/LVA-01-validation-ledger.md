# LVA-01 校验调用台账

本台账依据 2026-11-15 v1 当前源码；定位使用 `文件::函数`，行号由结构化调用报告记录。静态判断不是“已经可删除”的结论。计数与耗时必须区分正常调用、恢复重建和缓存命中，不能以同函数名推断无拦截价值。

## 采集口径

`LocalVideoMetrics` 不重新读文件、stat 或执行命令；从现有函数返回身份取得字节数。`hash_requests` 仅计 `manifest.hash_file` 入口，`hash_computations` 只计真正完成的 `_hash_open_file`/`_read_open_bytes`。直接 protected_bytes 读取也会产生实际哈希，因此后者可能大于前者，不能相减求缓存命中率；像素缓冲区等其他直接 hashlib 调用不在此文件身份口径内。`file_accesses` 是逻辑哈希请求而非操作系统 open/read；未知字节单列。每调用有源码/调用者、normal/recovery、inclusive/self 时间和嵌套 hash/bytes/probe/decode 次数，`unique_files` 为该调用下观察到的独立哈希路径数。

`full_decode_processes` 计无帧数/时间/选择过滤限制的 `ffprobe -count_frames`/`-show_frames` 及 FFmpeg null/rawvideo/framehash/framemd5 **输出格式**命令尝试；有范围限制的工作单列 `partial_decode_processes`，rawvideo 输入格式不算验证解码。它不证明命令成功或已处理所有帧，也不等于唯一视频数。通用编码可能也解码输入，但不纳入“专用完整验证解码”计数。嵌套行共享子计数，不能相加。Comfy 子进程和已有 HTTP worker 不在当前线程范围。原始事件超限则 `complete=false`；未发生观测异常时 `aggregate_complete=true` 表示所选函数的全调用聚合仍完整，不表示全进程指标齐全。只限制原始事件数，不宣称总内存硬上限。

## 当前调用与独立拦截价值

| 入口（均在 src/video_ai 下） | 正常路径 / 恢复路径 | 独立拦截价值 | 后续去留条件 / 当前分类 |
| --- | --- | --- | --- |
| `runtime/scene_clip_records.py::SceneClipStore.verify_global` | 阶段、HTTP guard、媒体事务/晋升；恢复同样进入 | 锁归属、已准入输入内容、JSON 目录集合、模型 stamp 漂移 | **候选热点**。完整闭包相同且有强保护作用域才可复用；锁/内容/目录/模型变化仍拒绝。不能整函数删除。 |
| 同文件 `capture_guard` 及返回 `guard` | 每 clip/HTTP 操作构造；恢复重建原 request/graph | 当前请求字节、依赖、模型、父观察目录和新子片接受门槛 | **必要边界 + 候选共同依赖重复**。保留每 socket 写、每响应持久化及父片门槛，不能因 GET 重复而跳过所有权。 |
| 同文件 `validate_artifact` / `artifact` | 输入、请求、证据、复制前后、恢复旧媒体 | 对比 path/bytes/SHA，拒绝未授权来源 | **必要内容证明**。同调用域保护下命中可能已不读字节，先看实际 hash 而非入口数。 |
| 同文件 `validate_clip` | 生成前/后、进度与接受重建；恢复旧请求和媒体 | request/graph/submission/媒体 receipt、帧映射、末帧、人工观察和父子绑定 | **必要恢复闭包**。仅可分层复用无变化依赖；必须保留旧产物真实性和手动接受。 |
| 同文件 `validate_media_receipt` / `_decode_video` | `_media` 先查旧 receipt、晋升、生成后验证 | 准备→晋升所有权、原始/保留帧完整视频、帧数/PTS、工具身份 | **已有 media_cache**。恢复必须重新建立工具和字节证明；相同 invocation 已复用，不重做历史优化。 |
| `runtime/production_scene_clips.py::_technical` / `generated_producer` / `source_producer` | 新输出复制+inspect，source trim 和 last frame；恢复 producer 可不运行 | 生成帧数、trim 范围、末帧准确位置 | **历史覆盖**：`_technical` 已有 `@inspection_reuse()`。相同字节 staging/target/trim 的 inspect 入口仍存在但完整 probe/decode 可命中缓存。不能把源代码连续调用直接登记为重复完整解码。 |
| 同文件 `_media` | source 验真→producer→guard→receipt→promotion；恢复先 receipt | 新产物归属、来源不漂移、内容晋升、不可变结果 | **必要事务边界**，本项不改。 |
| `media/video.py::inspect_video` / `inspection_reuse` | 首次 inspect 执行 2 个 FFprobe + 1 个 FFmpeg；相同内容作用域内复用 | 帧数、PTS、格式尺寸和完整解码；缓存 key 含内容 SHA、尺寸、媒体工具 stamp | **2026-11-05 已优化**。实验观察到了第二次入口解码为0。恢复新 scope 重新完整验证。 |
| `runtime/scene_comfy_transactions.py::_record_http` | request→call→guard→body→guard→response metadata；恢复收集原 GET 证据 | 锁丢失/来源漂移时禁止写证据；durable intent/accepted/history 真实链 | **必要边界 + 候选重复全局闭包**。不可移除 body/metadata 两个写入准入。 |
| 同文件 `recover_or_submit_scene_clip` / `validate_scene_submission` | 首次 intent/POST/accepted/queue/history；恢复已有ID/原意图 GET-only | 矛盾 accepted、未知结果、队列与 history 变化、服务重启不盲重发 | **必要恢复协议**。LVA-01 不改变任何 ID 或提交动作。 |
| 同文件 `_remote_validate` / `_HistoryTracker.advance` | 首次 object_info；同 owned 实例/template 内缓存；history 只增量归并 | 能力和实例身份；保留矛盾证据 | **2026-11-05 已优化**。本项不重做 object_info/轮询缓存，不把历史收益登记新收益。 |
| `adapters/scene_comfy.py` socket ownership checks | caller/网络线程发送前；恢复 GET 发送 | 每次实际写 socket 核对来源与所有权 | **已有 send_checks_only**，读等待取消/截止不扫描共同依赖。当前线程 profiler 不完整覆盖已有网络 worker，需独立定向测试。 |
| `runtime/scene_media_records.py::SceneMediaStore.verify_global` / `verify_captured_bytes` | 超分每帧及合成 guard；恢复预检 | 输入闭包、连续性、模型/tool、有效执行证明 | **部分已有 certificate/read guard 复用**。计真实下层 hash，不能把所有入口视作全量遍历。 |
| 同文件 `capture_guard` | 每帧提交及响应；恢复重建 | request/graph 与捕获来源 | **已去重一层**：global 刚核验的完全相同 guard_paths 不重做 validate_artifact；新/移除/重绑仍核对。 |
| `runtime/production_scene_upscale.py::_extract` / `_copy` / `_produce` | 整批预检、提帧、逐帧输入/输出复制、最后 complete；恢复验证旧帧后跳过 producer | 全帧/序号/像素、源内容、恢复 prefix、工具及所有权 | **仍有候选共同 global/model stamp 调用**；提帧批证明和 completed 进度复用已完成，禁止逐PNG回退/漏验。 |
| `runtime/_scene_upscale_records.py::validate_extraction` / `validate_png_receipt` / `validate_frame` / `validate_upscale_frames` | 新/旧提帧 receipt 和每帧完整身份，恢复扫描 prefix | 帧全集、来源像素、晋升和原 accepted 请求绑定 | **必要恢复 + 已有 media_cache**。作用域、工具/源/内容变化须失效；不能减少保留帧。 |
| `runtime/production_scene_composition.py::_capture_composition_guard` / `_candidate_ready` / `_commit` | materialize/encode/晋升/commit；恢复已有命令和候选 | 来源不漂移、输出晋升、命令真实性及最终候选身份 | **候选重复闭包 + 必要晋升**。比较 base/store 的实际交集及保护窗口后才能复用，不能删最终完整内容证明。 |
| 同文件 `_inspect` 与 `_scene_composition_commands.py::media_operation` | 编码/探测和最终候选验真；恢复既有输出重新构建完整证明 | 帧数/PTS/音频样本/AAC/字幕音轨与编码证据 | **音视频合并完整解码已优化**；不把历史 2→1 算新收益。 |
| `runtime/_scene_composition_materialized.py::copy_frame_sequence` | 复制整批帧前后各 global；恢复已完成复制证据 | 每源 SHA、持锁、fsync、全量来源批次证明 | **2026-11-05 已优化**：不是每帧全库校验；不能重复实施。 |
| `runtime/verification.py::protected_hash` / `protected_bytes` / `_NativeInput.verify` | 受保护窗口首次 hash，命中核对 native 句柄/文件身份；恢复新进程清空 | 同大小/mtime 回滚替换、路径重绑定、强保护有效性 | **既有内容缓存/冷准入优化**。不把逻辑命中算实际读/哈希；弱平台严格回退，不能持久化或跨重启缓存。 |
| `runtime/scene_revision_records.py::verify_artifact` / `RevisionGuard.verify_global` | revision 依赖闭包和 imported artifacts；恢复原来源重建 | 文件/目录集合、父 revision、来源/图谱/内容和锁 | **已有 batch、checkpoint、共同祖先与 protected read 优化**。本任务不触碰已有未提交的冷准入改动，也不认领其收益。 |
| `runtime/production_state.py::ArtifactStamp.verify` | global 和 guard 各模型/tool stamp；恢复同样验证 | 模型/tool 大小、mtime 和文件存在 | **metadata 检查，不是模型 SHA 全读**。独立统计 `model_stamp_checks`；不能仅凭模型体积宣称存在数十GB重复哈希。 |

## LVA-02 的输入与限制

优先从实际调用报告按 self 时间与真实 hashed_bytes 找候选；每个候选补齐作用域所有者、内容/工具/规则身份、锁与强保护条件、失效入口、恢复的第一次完整证明。保留提交、body/metadata 持久化、媒体晋升、发布、父片人工接受边界。没有 GPU 和完整生产上下文实测时，本台账只证明调用路径与离线放大，不证明每项在当前真实生产中的耗时排名。

## LVA-02 最终去留依据

原LVA-01数字及历史分类保留。后续实测见 `docs/task-designs/LVA-02-results.json` / `.md`：

| 原候选 | scope / key / 失效 | 前后实测与去留 |
| --- | --- | --- |
| global / send重复Artifact | 单次线程内fresh read-pass；store/type/frozen/root/revision/strict函数及完整Artifact身份，现存lease和完整ByteGuard；窗口/代次/线程/绑定变化失效 | normal严格12,876→8,982，命中3,894；实际SHA6,704不变。墙钟18.908746→20.756011秒，**默认保留strict**；实验helper仍可用于后续研究。 |
| JSON共同目录 | 路径+递归规则+完整expected集合；首查、退出双查，向外层capture重放；新增/删除/重定向/不同expected拒绝 | 同规则放大样本4次→2次（包括退出），无window仍4。原生产直接glob计数不完整，不作精确收益依据；默认strict。 |
| media guard / composition前后捕获 | 独立guard自己退出flush；不跨发送/响应写入缓存；跨store不共享语义结论 | 接线可由candidate_scene_validation显式实验启用，生产默认strict；合成单独收益未测，不推广。 |
| 模型/tool stamp、ownership、父片接受 | 每个原边界继续执行 | normal stamp952、恢复28，guard66不减；不删除、不宣称模型哈希节省。 |
| _technical / inspect / trim / 末帧 | 原inspection_reuse内容/tool身份；恢复新invocation原路验真 | 生产源码原样；normal媒体79、恢复34，实际解码64/28不变；历史优化不重做。 |
| intent / accepted / queue / history / 输出晋升 | 原schema、原ID、socket与body/metadata各边界 | 不改变协议；新helper捕获溢出/失效与真实恢复定向测试具名记录。无新GPU/整片收益结论。 |
