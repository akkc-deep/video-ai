# VoxCPM2 Installation and Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 TTS-VOX-10 的固定版本安装、离线迁移、明确默认切换与回退。
**Architecture:** Python 部署模块处理资产、配置与验证；PowerShell 复用现有联网下载入口，迁移恢复调用同一模块。
**Tech Stack:** Python 3.12、Windows PowerShell、官方 VoxCPM2。
**Spec:** `docs/task-designs/TTS-VOX-10-design.md`

## Global Constraints

固定批准音色及当前完整配方；不修改历史任务，不静默回退，不做生成期间额外模型检查。保留当前工作区的全部既有未提交工作。

## Review Focus

缺少批准资产；旧850ms默认；重复安装；不同运行根/带空格路径；离线环境基础解释器旧路径。对应测试分别验证明确失败、显式升级、幂等、配置重定位和真实解释器启动。

### Task 1: 部署与配置事务

- [x] 先测试批准资产导入、缺失/冲突拒绝、激活幂等、原始字节回退与历史不变。
- [x] 运行新增测试，确认缺少接口导致失败。
- [x] 实现 `src/video_ai/voxcpm/deployment.py`，更新 `scripts/configure_approved_narration.py`。
- [x] 运行同一测试至通过。

### Task 2: Windows 安装与迁移入口

- [x] 先测试迁移 venv/共享配置重定位及新安装的批准默认。
- [x] 新增 `scripts/install_voxcpm2.ps1`，接入 online/local 和迁移恢复。
- [x] 运行相关安装/迁移及批准旁白回归，记录既有失败。

### Task 3: 真实验收与使用文档

- [x] 在当前安装运行离线检查与幂等激活；在 scratch 隔离目录检查重定位环境。
- [x] 用正式生产语音函数生成短样本并恢复，保存本任务结果，不覆盖07报告。
- [x] 独立代码审查，修复实际问题，更新安装使用文档和任务定义的完成证据。

执行决定：在当前 v4 工作区实施，所需07/09及批准默认代码尚未提交，独立 HEAD 工作树会缺少这些直接依赖；不搬动或提交用户现有改动。

完成证据：docs/research/TTS-VOX-10-result.json。安装相关32 passed；扩展136 passed / 3 skipped / 5项既有字体夹具失败。真实GPU正文两段8.959583秒、恢复不新增请求；带空格新根依赖启动及精确字节回退通过。独立审查已完成，反馈的重要问题均已修正。未提交或推送用户工作区改动。
