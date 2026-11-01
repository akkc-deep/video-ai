# VCO-08 LongCat 研究实录

状态：**IN_PROGRESS**。用户已同意LongCat前置研究，任务板已按NOT_STARTED -> READY -> IN_PROGRESS启动；合同为`docs/task-designs/VCO-08-design.md`。本文不记VCO-08整体完成，不记真实多窗或正式16fps生产通过。

## 当前操作入口

研究目录：`D:/VideoSi/projects/video-ai/vco08-preflight/20261101-1238/`。

固定模型下载已启动一次，当前运行中的native session为**2400**，日志`D:/VideoSi/cache/video-ai/logs/vco08-fixed-checkpoint-download-chunked-1d26e01713d04445b4c465fc3cb27d78.log`。只监测该进程，不另启下载器；完成收据将为研究目录`download-result.json`。目标`D:/VideoSi/models/vco08-longcat/03b55529b1d1d4045f5fbe14d65c8c6e8116b278/`，选择23文件共77,577,230,776字节。尚未登记完整下载。VAE已完成并验证，文本编码器/DiT仍在下载过程。

一次试验配置已冻结在`trial-001/case.json`：首窗93、续窗各13历史+80新增，总93→173→253，原生15fps；首图为原已接受scene3飞行图SHA d29e1f20...，首窗seed42、续窗沿父RNG状态，不继承旧观看。**尚无扩散视频调用、无窗intent/真实输出、无新的观看或生产启用。** 运行器/监督器及调用前检查仍在准备；不能因下载完成自动执行一个未完成审查的runner。

**软件准备最新登记（2026-11-01本轮）：** runner/监督器已完成独立增量审查，三个P2已解决，结论“nothing important left”，仅针对当前研究代码。软件冻结为`trial-001/software.json`，21项执行代码SHA及固定依赖版本，文件SHA256 `68501cce7639c3b049d240f4605871eaf20351065a4471b85d2b484b774134a4`；11份官方原始代码Git blob已全部核对，只有声明的禁用BSA提前导入/终行差异。冻结后不修改这些执行代码。文本编码器/VAE已完成；仍等待同一下载进程的DiT及完整收据。下一步是下载结束后执行`checkpoint_layout_probe.py`，核对真实checkpoint与同一case/software/下载身份；通过后才执行`supervise_window.py --stage 1`一次。没有case-start/window-start或扩散intent，不应另外启动下载器或提前运行worker。

**更新于真实文本准备之后（2026-11-01 14:00+08）：** 上述68501冻结为准备期历史版本，已原字节归档。实际UMT5准备暴露只读mmap页面读后仍驻留工作集：6.49秒时RSS16.94GB、可用物理内存0.60GB，commit仍11.70GB；原guard正确退出，无扩散intent/试验起点。新增`mapped_residency.py`仅对当前进程的MEM_MAPPED/PAGE_READONLY/COMMIT参数页调用VirtualUnlock，私有Tensor/KV跳过，不修改文件/数值或其他进程。微软文档依据为`https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualunlock`；ERROR_NOT_LOCKED也会移出本进程working set。64MiB实际映射探针释放约67.10MB RSS、refault值及原文件SHA不变；tiny mmap/T5数值回归通过。确认无case/window-start、intent或layout后，显式准备期修订并保留revision JSON，当前22项软件SHA为 **`97b69cdde5da11b1815c7cce2805f6a45370f71890616e97cce2ffd72f79edeb`**。独立增量复核已通过。

修复后的真实文本编码25.01秒完成，观测RSS最高1,713,790,976字节、GPU tensor峰值2,143,301,632字节，物理内存始终约15.5GB以上可用；缓存`trial-001/text-context.safetensors` SHA `53c254856bcb45c0fd1cb8081bb5391538a9c0b672687e1605c1ef13404e77c5`。这只是两份文本提示准备，未开启case/window或扩散；真实首窗将复用该精确缓存，不重跑编码。源码/依赖/首图/案例数值协议未改变，只修复本进程映射驻留行为。下载仍为同一session2400/PID39904，尚待完整DiT和当前97b69身份的layout检查。

## 已完成的真实检查

所有Python先沿仓库`scripts/bootstrap.ps1`初始化日志/缓存，再使用Invoke-VideoAiNative与-B。纯stdlib用编排Python3.12；数值探针用现有嵌入式Python3.13.14 / Torch2.13.0+cu130。研究包只写独立python-deps，未覆盖生产包。

| 检查 | 实际结果 | 日志名（均在D:/VideoSi/cache/video-ai/logs/） |
|---|---|---|
| 系统资源/元数据 | 物理33,346,146,304字节、查询时可用17,633,955,840；commit余量18,238,980,096；磁盘余164,726,112,256。HF直连超时，Python经hf-mirror取得固定revision及30文件元数据 | vco08-resource-probe-38a9e16b82c8436b8847f2de815c1ff4.log |
| 模型清单/小配置 | 六项配置/index大小及Git blob正确；DiT1022项/F32数据54,324,285,696字节，T5 242项/22,723,641,344字节；受限Range读取首shard header证实F32 | vco08-model-manifest-d5633fac98474cf68fbc4c5398d77a41.log |
| CPU原生机制 | 未适配attention实际拒绝；SDPA/eager误差≤1.79e-7，4历史latent clean KV/full误差3.58e-7；更早历史改变新增输出，BSA拒绝 | vco08-tiny-adapter-probe-root-fix-c019b0d7e48b4d53a67bd8fce6ac56a0.log |
| CUDA小模型最终内核限制 | F32 tiny eager逐层加载与驻留误差3.58e-7；正式BF16 efficient-only路径本次驻留/卸载差0；cache/full差0.004971；失败层恢复CPU，峰值34,680,832字节 | vco08-efficient-only-tiny-cuda-f039f61152d3423bb75571d898c51de0.log |
| 只读mmap | 851,000字节随机小checkpoint的assign零复制、计算后原CPU data_ptr恢复、原SHA不变；缺key/错shape/重复tensor拒绝 | vco08-tiny-backing-probe-shape-fix-0855505c10e34919a1a3c230823ee085.log |
| 实际模型meta布局/API | DiT13,581,071,424参数/1022项；UMT5 5,680,910,336参数，唯一共享alias encoder.embed_tokens.weight→shared.weight；VAE126,892,531参数/194项；官方原图480p桶480×832。无预训练权重加载 | vco08-runtime-shape-probe-complete-deps-6a2e6940f19546188a7830e23d5d9398.log |
| 实际规模attention内核 | CFG batch2、32头、head128，q35880/k37440及q31200/k37440；flash不适用、efficient适用，math明确禁止；0.586/0.446秒、峰值3,874,291,712/3,531,603,968字节 | vco08-full-shape-efficient-attention-3eb3aa940427438da83266f6a6b134a6.log |
| UMT5卸载/alias | 随机小UMT5驻留/卸载差0、shared embedding对象与CPU引用恢复，prehook预算拒绝后恢复CPU | vco08-tiny-text-staging-probe-7daeb40be85649b89d8080a1dc7a022f.log |
| 实际VAE单图重建 | 官方VAE文件SHA d6e524b3...核对通过；latent[1,16,1,60,104]、decoded[1,3,1,480,832]有限；峰值3,335,620,608字节，0.477秒，RGB平均绝对重建差0.858。只是VAE，不是扩散/视频质量通过 | vco08-vae-roundtrip-probe-2574e46c4d5b48eb9ec729903b71448c.log |
| 冻结案例 | case.json与原选图副本已准备，模型manifest SHA 27bc85656592f2d99ebc29da08ef2b13fb78c669e653aa1170ef2933cad5425a；无视频调用 | vco08-prepare-trial-40ab70d687f84985a0ef08a2c41e9d54.log |
| 媒体格式 | 五帧合成RGB的lossless解码像素完全相同，viewing副本15fps/PTS/帧数正确；有损RGB差2.303，不宣称像素/色彩链通过 | vco08-media-io-probe-2b57fa849d884843a4468e44820538dc.log |
| 恢复故障检查 | 七项合成故障检查通过：持久化剩余预算/到期拒绝、电影pending中断后保留/重做提交、数组/JSON一致重放及漂移拒绝、父结果/sample收据绑定拒绝；没有真实模型调用 | vco08-recovery-fault-probe-7d283433ed8b4705a9a9714df1ba6f3e.log |
| runner结构 | --check退出0，报告93→173→253；明确完整下载尚未完成，真实模型调用0 | vco08-runner-structure-check-7bac4f9e16e44162bde4e488d2b4a7a6.log |
| 真实文本准备RED | 只读mmap驻留累积触发物理内存阈值，退出1，未产生文本缓存或扩散intent | vco08-real-text-context-preparation-743406848b784b4eba7ad7e8ac1ccd6e.log |
| 本进程映射回收 | 64MiB只读文件映射RSS下降67,100,672字节，refault数据和文件SHA不变，private tensor未触及 | vco08-mapped-residency-probe-c3ff253e51dc45b382599e7d7a3cd4df.log |
| 准备期软件修订 | 旧68501原字节归档，未启动试验前更新为22项97b69；案例/依赖不变，revision证据保留 | vco08-preparation-software-revision-5fdbe233074e4bf285ca65b409d9bae4.log |
| 真实文本准备GREEN | 25.01秒完成，RSS≤1.714GB、GPU allocation≤2.144GB，文本缓存SHA53c254...已绑定；扩散0 | vco08-real-text-context-residency-fix-e192819522324144b7a651c891d1ad63.log |

每项JSON证据均在研究目录同名probe结果中。这里的数值探针不代表完整模型资源或视频动态接受。GPU测试串行，没有同时运行完整模型视频推理。

## 已知失败与修正

- 初始PowerShell传Python -c的嵌套引号被剥离，元数据命令SyntaxError；改用脚本文件，未触及模型。
- .NET/curl的HF直连超时、mirror Schannel凭据错误；Python OpenSSL访问mirror正常，不关闭TLS验证。仅使用固定源身份和受限Range。
- 嵌入式Python隔离sys.path最初不含脚本根，native_adapter导入失败；显式加入研究根后通过。
- 官方旧tokenizers0.19缺少本机Python3.13 wheel，pip尝试构建时maturin不可用，退出2；不继续编译Rust。最终隔离使用transformers4.57.3/现有tokenizers0.22.2，其余固定版本及Windows loguru、ftfy依赖已补齐。没有把失败安装记为通过。
- 最初CUDA FP32位级相同断言失败，最大差3.58e-7；改按数值容差检查，保留真实误差，不宣称位级相同。BF16本次实测差0也不外推所有输入。
- mmap探针最初取一维tensor再flatten，未真正制造错shape，断言失败；改为取多维tensor制造实际shape差异。只复用已核实同一随机种子内容的自有小checkpoint，未重复模型试验。
- 下载初次遇到合法chunked小文件HTTP200无Content-Length而拒绝，退出1；只修复该header处理，仍验证确切字节及Git blob/SHA。当前下载GET沿同一清单执行，传输中断仅恢复同一byte range，不是GPU重试。

## 独立只读审查

按brainstorming技能的builder check派发独立审查`vco08_research_review`。首轮指出：需禁止SDPA math回退，并冻结真实窗口时限/资源阈值。已补齐高效内核限制、实际规模检查以及3600秒/窗、10800秒/案例、物理/commit/GPU/磁盘阈值和owned-worker监督职责。增量审查结论为“nothing important left”，**仅限当前研究合同及机制探针**。完整下载、真实checkpoint绑定、runner/监督器实现与审查仍是实际调用前门槛。

随后对完整runner作独立只读调用前审查，指出三个P2：媒体提交中断恢复、重启预算重置、已成功latent的父链重绑定不足。已改为原子pending媒体/JSON、持久化case/window起点及收据/父链完整绑定；上述七项故障检查已退出0，正在收回独立增量复核。此前审查不代替这次runner审查，不提前记真实调用准入通过。

后续增量只读复核已返回：上述三项P2均解决，当前代码增量“nothing important left”；完整下载/真实checkpoint布局/效果仍未代证。源代码固定核对命令退出0（11/11），日志`vco08-pin-source-check-d60b439802c34875882f539ff4e115a1.log`；冻结命令退出0，日志`vco08-freeze-software-e4773178535c41968d5e6a7109b4b365.log`。最终结构检查`vco08-runner-final-structure-8b38e62717de469d91be0e9040c2c79f.log`退出0，明确download_complete=false、new_diffusion_calls=0。

## 尚未完成

完整23文件下载与收据；runner/监督器、预训练checkpoint严格绑定及调用前检查；真实三窗技术/资源结果与静态提前拒绝筛查；完整动态播放反馈；正式16fps适配/生产准入/失效恢复；项目最终全库。所有这些均不得从小探针或VCO-07的整段完成结果推断已通过。
