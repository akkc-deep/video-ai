# VCO-05 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次真实20秒隔离验证，保留完整成功或失败证据。

**Architecture:** 新增实验模块，复用VCO-01 renderer及既有视频probe，不修改生产接口。独立证据目录及自有服务，一次提交、GET恢复、原run只读。

**Tech Stack:** Python3.12、pytest、ComfyUI、FFmpeg、Windows内存API、nvidia-smi。

**Spec:** docs/task-designs/VCO-05-design.md

## Global Constraints

- 321请求/320保留/[0,320)、768×432、16fps、40步/CFG3.5/Euler/simple/切换15。
- 原案例首片seed、已有Wan2.2双专家；原run不写回，不自动重试/降规格。
- 期限从冻结配置读取，失败停止；完整动态观察缺项保留unverified。
- .git只读；全库留到VCO-08；跨题材追加另需授权。

## Review Focus

- POST接受后断线/进程崩溃只查原身份，不能第二次提交。
- case/graph/模型/PNG/提示任一漂移在发送前拒绝。
- 另一进程抢端口或锁不得管理外部进程。
- 恶意输出metadata/非321帧/非16fps不能生成通过。
- 软件或采样通过不能变成完整动态观看通过。

### Task 1: 冻结契约与一次提交

**Files:** 新增experiments/whole_scene_case.py、whole_scene_runner.py、tests/unit/test_whole_scene_experiment.py。
**Interfaces:** prepare_case(source_run,scene_id,contract_path,root)、verify_case(root)、execute_case(root)。消费已有完整VCO-01契约及已准入原图，输出独立case/graph/intent/result/HTTP及资源。

- [x] 写失败测试并记录RED：预算、身份漂移、模糊接受、重复调用、锁竞争及错误停止。
- [x] 实现冻结及一次提交/GET恢复、自有服务与资源日志，运行上述文件至GREEN。

### Task 2: 原生媒体与真实首例

**Files:** 新增whole_scene_media.py、scripts/experiments/vco05_whole_scene.py、tests/integration/test_whole_scene_media.py；新增验证交付。
**Interfaces:** 消费Task1冻结case及唯一history output，audit_output(root,output)产出原生帧、映射、probe、无损审阅片及分项状态。

- [x] 写RED：321帧实际CPU样本，审阅320帧RGB/PTS正确；非法输出拒绝。
- [x] 实现媒体审计并GREEN，运行VCO-01必要兼容检查，记录命令/退出码。
- [x] 完整冻结原run及模型身份，准备只读案例与文本审查；执行一次真实首例并保存结果，失败即停止。
- [x] 核对源run/源码身份及git diff --check，独立审查重要问题并修复，逐项登记真实验收。完成仅按有证据结果判定，不推进未获授权的实验。

## Ledger

Pre-flight: Task2消费Task1 case/graph/output；均使用上述root与原生321/320契约，无接口冲突。用户要求完成任务，沿既有已选B阶段方案直接实施；不增加中途设计审批。工具隔离于新增模块和独立证据根，.git只读不创建worktree。

Task1: complete。独立审查四项问题均RED→GREEN；追加自有服务退出立即停止和全局GPU互斥。2026-10-27最终软件检查122 passed，日志 `D:/VideoSi/cache/video-ai/logs/vco05-software-final-63c6db8a196f45319ef094a890f81e50.log.pytest.txt`。提交受.git只读限制，所有修改留在工作区。

Task2: 媒体实现及真实CPU验证已GREEN。兼容生成集成检查进行中；真实GPU尚未开始。最终冻结根为 `D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321`，首个prepare目录仅为发送前软件完善的历史快照，superseded.json明确POST=0，不能当作第一次GPU试验。

Task2 latest: 唯一首例真实技术通过，321原片/320无损RGB审阅片/20秒及映射、1874资源采样、源run/依赖不变均有实际结果。独立审查处置已完成；没有完整动态播放证据，任务不登记完成。

Ruling: 完整旧生成文件扩展检查在历史反复篡改审计阶段终止，保留中断日志、不登记通过；本次旧生产源码未变，必要兼容收窄为结果schema、原失败测试顺序及未准入零服务/零POST三项，3 passed。代价是本任务未验证完整旧生成文件的全部用例，全库仍按原安排留至VCO-08。

Task2 completion: 播放兼容修复34项检查及最终媒体血缘复核通过，新版交付后用户“没问题，继续吧”，按前序全片动态验收询问登记当前样片接受。user-observation.json和final-assessment.json绑定新版SHA、原片和无损证据，历史unverified快照不改签。本轮授权首例任务完成；不追加跨题材GPU任务、不启用生产，原JIM-08独立续接未因此完成。
