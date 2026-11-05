# 全流程性能优化实施计划

用户已授权将只读审查发现的重复开销一并优化。沿用此前约束：在当前工作目录原位修复，保留其他未提交改动，不写 Git 元数据；生成暂停，不启动生产服务、不请求云端、不操作原锁/暂停进程。保持模型、采样参数、画质、全部原文与音频、每场景两张候选、所有保留帧及人工观察门槛。未知提交不重发，既有 task/prompt ID、图片和恢复证据不改写。

当前 run：`20261104-053708-1a5f92e2ac83`；`paragraph_jimeng_v1`，未设置 scene_rendering/scene_continuity；继承 common+plan，107 scenes / 202 clips / 13,306 retained frames / 245 PCM。下游视频、放大、合成尚未生成，离线收益以调用计数和小型真实媒体基准为准，不编造云端节省秒数。

## 决策

优先复用已经证明且仍受保护的事实、合并相邻重复工作，并把全量来源检查移到明确事务边界。维持兼容的既有记录与恢复路径；不会因优化而直接重建旧付费请求。并发优先采用 caller 线程的“先取得两个 accepted ID，再收集原任务”，避免 worker 写记录/共享可变客户端。远端、跨 invocation 或跨服务复用仅在有明确身份与失效条件时启用，否则使用原严格路径。

## 任务与文件归属

- [x] A 输入/配音/分镜：`scene_pipeline_records.py` 的重复 common_value、`production_support.py` 及 speech/storyboard 的响应目录扫描；同阶段 Ollama 装载复用保留旧 intent/body。prefix agent 负责，不编辑全局 verification、图片/视频/合成模块。
- [x] B 图片/选图/邮件：普通图片入口的检查点、accepted/activation 重算、辅助 `_run` 重载、两候选提交与等待拆分、TOS 验证身份缓存、预览单解码多输出/晋升复用、MIME 编码及 SMTP 会话。image agent 负责 image/reference/selection/adapters/storage/email 模块，不编辑全局 verification、prefix/video/合成模块。
- [x] C Wan/逐帧放大：提帧与 PNG 完整证明批处理、promotion 后内容复用、Wan 同源技术检查复用、`/object_info` 服务实例缓存、轮询/恢复扫描和 transport guard 边界。video agent 负责 clips/upscale/media/scene_upscale/frames/video/adapters/scene_comfy 模块，不编辑全局 verification、图片、prefix、合成模块。
- [x] D 总入口/合成/交付：默认路线的输入保护边界，纯读阶段复用、逐帧复制的全局检查改为批次检查并保留每源 SHA/锁、合并音视频重复解码、恢复/交付重复准入；root 负责 `verification.py`、`scene_revision_records.py`、`production.py`、`production_scene_pipeline.py`、composition/delivery 相关模块。
- [x] E 集成：独立审查每组改动，运行有意义的离线回归和前后基准，核对零生产写入/零网络/原 run 保全，记录实测与未测范围。

## 验证契约

先观察性能/正确性失败用例再改代码。重点覆盖：同大小+恢复mtime的字节变化、路径/文件身份替换、目录新增/缺失、复制/关闭上下文、实际send后置检查、未知付费intent、accepted/result恢复、旧记录/旧请求body、无额外候选/帧/推理请求。复用不能仅由mtime或可编辑汇总文件授权，不删除审查门槛，不将未启用whole/temporal的优化冒充默认路线收益。

每组只写自己的新测试文件或已分配领域测试，使用已有 `D:/VideoSi/envs/video-ai/Scripts/python.exe`、独立 `--basetemp`、`-p no:cacheprovider`。不跑真实模型或生产CLI，不做无关全仓测试。共享接口变化通过root协调。

## 进度与实施裁决

- 已完成的前置两轮参考图优化：19.594 → 5.427 → 4.203 秒；见 reference-generation-speed-fix.md。本计划不重复实施。
- 本次方案选择和实现已获用户直接授权；省略重复方案确认。工作区含大量必要既有改动且 Git 只读，继续原位增量修改与只读审查。
- A 审查修正：请求索引及 common PCM 保护使用 `_NativeInput`，不保留成百上千 CRT 文件对象；fsync 短释放后核对原 SHA/文件身份，任一重锁失败仍处理其他租约。新增 641 request / 600 PCM 资源回归，最新领域 193 passed / 1 excluded。
- B 审查裁决：保留跨网络的 accepted 真实性重建，仅消除同一纯读事务内的重复；TOS 缺少强版本时保留原 HEAD+GET；邮件恢复仍重渲染防成对篡改，原图只读且不再次 r+b fsync；会话只有 caller 确认成功的 DATA 才能复用。
- C 审查修正：检查复用限定 active/owner thread；PNG 批解码输出完整逐帧 framehash，不保存第二整段 RGB。完整检查、所有帧/像素身份均保留。
- D 实测：24 张真实 PNG、64 个历史文件的离线复制从每帧全局检查 48 次降到批次边界 2 次，三次平均 2.480126 → 0.273413 秒（88.98%）；SHA/锁/fsync 均保留，不外推整片耗时。
- D 已完成 43 项最新定向回归（2.81秒）、24 项真实合成/恢复/CLI集成（619.50秒）；全组合新鲜 smoke 1 passed（162.31秒）。最新所有新增性能契约合并集 67 passed（12.52秒）。独立最终静态审查未发现 Critical/Important。
- 原生产 run 第19场景最终只读基准：4.290063 / 4.303860 / 4.275560秒；依旧每次2次冻结加载，原图/任务/汇总/锁摘要未变化，真实网络与生产写入均为0。首次loader12.492146秒受冷启动/并行离线测试影响，未作严格冷磁盘对比；不能声称该项改善。
- 最终实施与量化结果见 [全流程优化结果](video-generation-performance-results.md)。
