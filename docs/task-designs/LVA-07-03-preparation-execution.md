# LVA-07-03 隔离环境准备执行结果

2026-11-19（Asia/Shanghai）。用户对已呈现的具体四阶段清单回复“同意”，授权 sources、runtime、wheels、install。**四阶段现已完成；这只证明独立源码、runtime 和依赖安装就绪，不是 LVA-07-04 的 worker/workflow/恢复 harness 已完成。**

机器回执：`docs/task-designs/LVA-07-03-preparation-execution.json`。环境目录：`E:/VideoAI/scratch/benchmarks/LVA-07-04-environment`。

## 实际交付

| 阶段 | 结果 | 直接证据 |
| --- | --- | --- |
| sources | 固定 Comfy commit 的1332个原始Git blobs导出验真；Wrapper固定241文件下载验真，加既有修复/策略形成244文件、48,125,397 bytes的完整快照 | 环境目录 `sources.json` |
| runtime | 独立复制45,784文件、4,157,540,147 bytes；381个指定二进制与事先SHA256一致；独立 `_pth` 绑定本副本路径 | `runtime.json` |
| wheels | 15个固定wheel、339,836,898 bytes，逐一核对大小/SHA；生成本地名称/版本/哈希安装锁 | `wheelhouse/`、`additional-wheels.lock`、`wheels.json` |
| install | 仅在独立副本离线安装；原87个版本保持，加15个共102个分发；`pip check` exit0，输出 `No broken requirements found.` | `pip-install.log`、`install.json` |

Wrapper上游固定 `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`，Comfy固定 `2c75dc1b379a59e0880619d029607af5169a62ef`。本地为完整固定源码快照，没有伪造带历史的Git checkout或将CPU部分副本commit冒充完整commit。

两个已修改文件及三份修复/策略文件的SHA均与既有审定产物一致。完整快照指纹列在 `sources.json`，其摘要绑定到执行回执。六份已有推理模型没有复制、下载或读取payload；完整源码自带的2,865,751-byte可选face_landmark.onnx按获批源码清单取得，没有加载。

## 实际验证与空间

最终审计命令：

```powershell
& .tools/python/python.exe -I E:/VideoAI/scratch/benchmarks/LVA-07-03-planning/verify_execution.py
git diff --check
```

审计实际exit0；直接检查四份阶段回执、固定源码/修复指纹、87+15个实际安装版本、pip check结果，以及独立解释器启动与sys.path。解释器确认为Python3.13.14，路径全部位于独立环境根内；没有导入torch或节点。未重复大模型/二进制全量哈希、CPU payload实验、视频解码或产品全库测试。

首轮最终目录观察为50,063文件、5,106,830,024 bytes（普通文件大小合计，非文件系统分配峰值）；低于8GiB预留。wheel下载339,836,898 bytes加Wrapper原始文件47,250,651 bytes，下载payload合计387,087,549 bytes；不含HTTP协议开销。已保留失败导出和修补副本，额外约53MB亦在预算余量内。RAM/VRAM峰值未测，不用预留量冒充峰值。

完整核验回执：`E:/VideoAI/scratch/benchmarks/LVA-07-03-planning/execution-verification.json`。该回执每次审计会记录观察时点及文件数/大小，后续日志/pyc小幅增加不代表新的模型或安装动作。

## 发现与修正

1. 首次 `git archive` 继承Windows Git换行转换，将固定LF blobs转成CRLF，身份检查在Wrapper下载前拒绝。原现场保存在 `E:/VideoAI/scratch/benchmarks/LVA-07-03-planning/source-attempt-1`。用单文件固定blob复现后，仅对此次Git命令加入 `-c core.autocrlf=false -c core.eol=lf`，重新导出通过。
2. `git apply` 同样继承了换行转换，两个修补后文件与审定SHA不符。诊断证实唯一差别为CRLF；独立两文件复现确认相同命令级配置可得到精确审定SHA。保留CRLF文件后，只对本轮新快照中两文件恢复已证明的LF字节，逐一核对SHA并完成sources回执；没有重新下载241文件。保留位置为 `source-attempt-2-patched-crlf/`。

三处Git调用均已在准备命令中固定局部换行配置；未改变全局Git或生产设置。失败与修正过程、原审批脚本SHA和修正脚本SHA均保留在执行JSON。原审批脚本及授权前证据另存于同一planning目录，旧摘要记录表示历史身份。

## 边界与任务状态

本轮只执行已批准的四阶段：0 GPU torch/Wrapper节点导入、0 Comfy服务、0生成POST、0 GPU采样、0完整模型准入、0推理模型payload读取。没有需要退出的owned Comfy服务；Git和Python准备子进程均已结束。原生workflow、即梦、产品runtime、已有模型和旧run没有成为写入目标。

LVA-07-03保留COMPLETED并追加执行证据；LVA-07-04保留NOT_STARTED、Design=None、Handoff=None。环境前置已有实际交付，不能再写成“尚未建立任何隔离环境”；后端、工作流和恢复harness仍未实现。

剩余前提具体为：实际节点导入/注册与object_info，受限的私有单专家所有权和双侧原子发布，静态增量跨sampler reload/offload的保持方式，以及实际profile/sigma/完整模型Low290重新对账。102个分发安装及pip check不能证明DLL/API或双14B模型兼容。完整投入决定继续为 `insufficient_evidence`；不据环境安装结果自动启动服务、加载模型或采样。

为解除第一个实际注册未知，已另行准备 `LVA-07-03-node-probe-plan.md` 与 `LVA-07-03-probe-nodes.ps1`：CPU模式、单个owned本地服务、仅GET九个节点schema、限时180秒及4GiB私有commit上限、退出/端口证据。当前只执行了默认只读展示、语法和互操作编译/布局核对；没有实际服务或节点探测。该提案未授权，不与前面已完成的四阶段混算。
