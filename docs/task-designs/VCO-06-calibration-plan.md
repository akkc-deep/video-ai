# VCO-06 Offline Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用既有24源取得受限修复算子参数上限及一次检查，为VCO-06设计提供数据。
**Architecture:** 独立CPU实验；已知对应的源帧采样、恒定受限变换、校准/封存/检查分离；不改生产。
**Tech Stack:** Python3.12、NumPy2.2.6、OpenCV4.12、pytest及已有RGB审计记录。
**Spec:** docs/task-designs/VCO-06-calibration-design.md

## Global Constraints

- 原24源12/12 split不变；未知/漂移拒绝，原生时间不裁短。
- 网格1/64..1 log2单位；恒定参数；2码值p99预算；先拟合封存再一次检查。
- oracle对应与AI来源明确记账，production_eligible=false；不启动生成、不写原样本。
- 全库留VCO-08；.git只读，保留未提交成果。

## Review Focus

- 注入参数泄漏到估计器，导致虚假重建通过。
- 平均改善掩盖裁切或单帧失败。
- 跳过失败强度扩大上限，或holdout回流拟合。
- 把已知对应上的结果当成现实视频匹配/剧情判别。
- 原样本、封存或已检查结果被覆盖后继续混用。

### Task 1: 算子和校准守卫

**Files:** scripts/experiments/vco06_repair_calibration.py；tests/unit/test_vco06_repair_calibration.py。
**Interfaces:** transform(rgb,operation,parameters)、estimate(reference,current,operation,context)、score(reference,current,repaired)、fit_bounds(rows)、evaluate(rows,sealed)。估计器不接收recipe；fit只收calibration行。

- [x] 写已知RGB增益/色度控制、identity/门槛/裁切、连续前缀与split泄漏RED。
- [x] 实现最小算子、裁切拒绝和拟合，运行定向测试GREEN。

### Task 2: 取样及封存实验

**Files:** 同上实验入口；独立D:/VideoSi项目证据根。
**Interfaces:** prepare(root)、measure_source(root,source_id)、seal(root)、check_source(root,source_id)、finalize(root)。prepare冻结协议和全部source身份；阶段入口拒绝乱序/源码漂移。

- [x] 只读核验24源、记录每帧原生时间及ROI样本，前后输入身份一致。
- [x] 测量12个calibration源后写不可变seal。
- [x] 一次处理原12个holdout源，保存全部失败/弃权，不回调。
- [x] 汇总实验profile、限制和结果，独立审查一次；基于实测完成VCO-06详细实施设计；后继交接按任务板工作流单独记录，不开始生产校色实现。

## Ledger

Pre-flight: Task1的estimate/score/fit_bounds供Task2使用；已知对应仅为条件校准，不代替未来配准。用户已选择先做离线AI校色校准，本阶段为后继准备，VCO-06生产实现尚未开始。任务板NOT_STARTED及None引用保持到完整实施设计形成，准备完成再转READY。

Task 1: complete。首轮15项RED，算子/封存守卫分阶段GREEN，fresh-context审查后闭包硬拒绝、独立输入身份、修复方向和128MiB预算均补RED→GREEN，最终22 passed（vco06-calibrator-final-7daea24cbfaf47de91bd2f4ee5a19697）。正式冻结前复跑22 passed（vco06-freeze-a18f1d81cece4cc0bb85efaa443fd522）。未做全库回归，未修改生产入口。

Task 2: Ruling: 首次正式根AI-repair-calibration-20261027的首源完成74项后闭包拒绝。根因是ColorAnalysisReader返回五字段身份（额外verified_at），而实验四字段身份作全字典比较。实际path/bytes/mtime_ns/SHA一致，非源漂移。保留失败根，修复适配时只提取四个身份字段，不放松字节验证；新回归同时证明真实内容变动仍拒绝。RED 1 failed/22 passed，GREEN 23 passed，日志vco06-reader-identity-red-776029fe79c545b9872c94e7bc5c19ce、vco06-reader-identity-green-0ef6ca01e8ca44fe851503930ed052c1。未访问holdout、未调整算子/网格/误差预算。以新根AI-repair-calibration-20261027-r2重新冻结，旧根不覆盖。该工程修复若错误的代价是身份漂移被误报或漏报，回归保留真实漂移拒绝检查。

Task 2: complete。r2实际24源/2868原生帧/1776控制全部闭包核验；eligible 11 calibration+12 holdout、六题材，82项弃权保留。12源校准后封存，原12源一次检查后finalize，4/10方向条件合格，production_eligible=false；其余方向不扩大/回调。完整结果、输入/封存/检查身份及全部日志见 `docs/task-handoffs/VCO-06-calibration-results.md`。收尾phase guard+两split_collect+fit_bounds/evaluate复算与保存结果一致（vco06-closeout-verification-12f1af07532b4eb5b1f7c12ffb198469，exit0），原数据及生产run只读、无模型请求、全库仍留VCO-08。

Design builder check: fresh reviewer提出一个重要实施问题——修复manifest和当前assessment报告的配对关系未定。已冻结独立选图参考manifest→本intent自有ordinary pair_report，只消费每原生帧repair_ref_*、ref在left/current在right；原assessment/before报告只管scene风险，after单独复制原前缀集合测量。不会混入adjacent/parent_join或漏首帧，不修改VCO-04固定首帧参考规则。

Design engineering call: 真实容器探针显示FFV1/NUT缺少可直接复用VCO-02的色彩支持，RGB H264同样不在原支持域。选择显式sRGB/BT.709 YUV444 CRF0主候选+High/yuv420p CRF16观看副本；主候选RGB整数转换不宣称无损，全部解码仍需原p99/max/裁切门槛。64×36四帧探针16fps与完整颜色声明正确，RGB往返最大1码值，日志vco06-yuv444-feasibility-24d4d3c556a44e3fa4e2ec2c7b477488，exit0；不是全片视觉验收。

Closeout: `vco06-phase-order-verification-be186bddd99443de85ecf5e8cfb40135.log`明确12 calibration结果均早于seal、12 holdout结果均晚于seal且早于evaluation。最终 `vco06-final-check-680a607c9d2f4772a1f5c9e231c1afc8.log` 为23 passed/exit0，重验冻结software/顶层证据不变、VCO-05仍COMPLETED、VCO-06 READY且设计/交接引用一致、产品模块尚未创建。git diff --check退出0（仅既有autocrlf提示）。按先设计回填→写handoff→关联→NOT_STARTED转READY完成后继准备，没有启动产品实施或新推理。无deferred minor。
