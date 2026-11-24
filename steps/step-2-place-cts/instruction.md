# Step 2 — 布局规划、布局与时钟树综合（Floorplan / Place / CTS）

你是一名后端物理设计工程师。前端已交付综合网表 `1_synth.v` 以及（如有）`handoff_notes.md`。请完成 Floorplan、Placement 与 CTS，为最终布线打下基础。

## 背景

- 工作目录：`/workspace`（文件系统在步骤间保持）
- 运行：`make floorplan`、`make place`、`make cts`，或直接 `make cts` 跑到 CTS
- 清理重跑：`make clean_place` / `make clean_cts`
- 约束仍然由 `/workspace/constraints/constraint.sdc` 给出（0.65 ns 时钟，不可放宽）

## 目标

产出合法的 `/workspace/results/nangate45/aes/base/4_cts.odb`。

请重点控制：

- 布线拥塞（utilization、placement density、cell padding）
- Clock skew 与 CTS 缓冲策略
- Post-CTS 的 Setup/Hold 早期违例（允许把轻度局部违例带入布线阶段精修）

可调常见旋钮（名称以 ORFS 文档为准，例如）：`CORE_UTILIZATION`、`CORE_ASPECT_RATIO`、`CORE_MARGIN`、`PLACE_DENSITY`、`PLACE_DENSITY_LB_ADDON`、`CELL_PAD_IN_SITES_GLOBAL_PLACEMENT`、`CTS_BUF_DISTANCE`、`TNS_END_PERCENT` 等。可将物理脚本放在 `/workspace/scripts_override/`（如使用）。

## 硬约束

- 必须成功生成合法 `4_cts.odb`，不得出现致命工具崩溃或不可恢复的布线溢出。
- 仍不得放宽 SDC、添加时序例外或重定向 `SDC_FILE`。
- 不得破坏前端网表的功能与端口定义。
