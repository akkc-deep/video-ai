# LVA-07 独立 CPU 节点注册探测提案

2026-11-19。环境四阶段安装已完成、102分发/pip check通过。下一项未知是完整Wrapper在本机能否实际导入/注册，以及固定版本的真实HTTP节点schema。**本提案尚未执行，不是LVA-07-04的完整实施设计或完成证据。**

## 固定命令

```powershell
# 默认只读展示，不创建进程或探测目录
& ./docs/task-designs/LVA-07-03-probe-nodes.ps1

# 仅在取得本提案具体授权后执行
& ./docs/task-designs/LVA-07-03-probe-nodes.ps1 -Run
```

入口调用已准备的 `E:/VideoAI/scratch/benchmarks/LVA-07-04-environment/python_embeded/python.exe`，执行相邻ComfyUI的 `main.py`。Wrapper/Comfy身份与四阶段实际回执一致：上游a743固定完整修复快照、Comfy固定2c75导出、原87版本加15固定wheel。运行前核对四份阶段marker摘要及244份Wrapper源码SHA；禁止来源漂移。默认只读入口现已验证没有创建目标目录。

## 执行范围与资源

- 仅新建 `E:/VideoAI/scratch/benchmarks/LVA-07-04-node-probe` 下input/output/temp/user/cache、stdout/stderr、计划/进程所有权/结果和9份schema。`-B`禁止写入模块pyc；不写旧run或生产目录。
- 启动一个自有隐藏Comfy进程，`--cpu`，`CUDA_VISIBLE_DEVICES`为空，HF/Transformers离线，固定仅监听127.0.0.1:8297。端口占用即停止；不关闭已有进程，不另换地址或端口。
- 仅允许已固定的Wrapper custom node目录；不启用管理器或assets，不自动打开浏览器，模型目录只读提供文件名枚举。不调用模型加载/编码/采样方法，不发生成POST，不提交视频。
- 唯一HTTP行为为GET九个 `/object_info/<class>`：ModelLoader、BlockSwap、VAELoader、T5TextEncoder、TextEncode、ImageToVideoEncode、Sampler、Decode、LoraSelect。GET前确认监听PID为刚创建的owned进程，地址为127.0.0.1；不误读其他服务。
- 无新下载或安装。预留512MiB磁盘；两份日志各16MiB阈值，每个schema响应上限2MiB。Windows Job对owned进程设置4GiB私有commit硬限、最多一个进程和关闭job时清理；250ms观察RSS，超过4GiB立即停止。这是私有commit硬限加RSS停止阈值，不宣称采样间隙的RSS绝对峰值被精确限制。
- 子进程探测截止180秒，单次HTTP超时2秒，收尾等待最多10秒；启动前身份核对及本地C#互操作编译另计。仅CPU注册，不分配GPU推理预算。
- 无论成功或失败都仅结束本次owned进程，关闭job并恢复调用进程的临时环境变量；记录PID/start identity、进程退出和端口关闭。保留错误、schema和日志，不自动重试。

## 通过标准与未验证边界

通过要求九个节点均实际返回对应schema、监听者所有权正确、限额未触发、最终owned PID退出及端口关闭。进程exit0本身或没有告警不构成注册通过；缺少节点/字段、DLL/API错误和owned退出异常均报告失败。

结果只关闭实际节点/接口证据缺口，不代表LoRA已应用、完整双专家内存已解决、静态增量跨reload/offload已保持或40/4步工作流已验收。用户未批准前保持0节点探测、0服务启动，不以此提案准备LVA-07-04为READY。

## 本轮已做的命令核对

PowerShell Parser语法检查通过；C# Windows Job互操作类型可编译，Win64结构大小144 bytes符合EXTENDED_LIMIT_INFORMATION；默认只读展示执行通过且未创建probe目录。没有实例化Job、启动Comfy子进程、导入节点或访问HTTP。曾在核对命令中触发PowerShell对Marshal.SizeOf的object重载误绑定；显式选Type重载后144-byte布局检查通过，未执行实际probe。

该提案由LVA-07-04任务Scope“需要启动服务的节点能力探测按具体清单授权执行”要求单独取得具体授权；前面的下载/复制/安装许可已完整执行，不重复索取。
