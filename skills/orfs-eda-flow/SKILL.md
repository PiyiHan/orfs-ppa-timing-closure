---
name: orfs-eda-flow
description: OpenROAD-flow-scripts (ORFS) RTL-to-GDSII 流程操作、时序分析与物理设计调优指南。
---

# ORFS EDA Flow Skill

本 Skill 说明如何使用 OpenROAD-flow-scripts（ORFS）完成 RTL-to-GDSII，以及如何阅读 OpenSTA 时序与常见物理违例。它只覆盖通用方法论，不提供某一道题的最优参数。

## 环境与入口

- 典型安装根目录：`/OpenROAD-flow-scripts`，flow 目录：`$FLOW_HOME=/OpenROAD-flow-scripts/flow`
- 将 `WORK_HOME` 指到当前设计目录，用 `DESIGN_CONFIG` 指向该设计的 `config.mk`
- 常用封装：`make synth|floorplan|place|cts|route|finish`
- 增量清理（避免每次从综合重跑）：`make clean_place`、`make clean_cts`、`make clean_route`、`make clean_synth`
- 固定线程数有助于复现：`export NUM_CORES=4`（ORFS 会把它传给 `openroad -threads`）

工具不在 PATH 时，先：

```bash
export PATH="/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:$PATH"
# 或: source /OpenROAD-flow-scripts/env.sh
```

日志与结果按 `$(WORK_HOME)/{logs,reports,results,objects}/$PLATFORM/$DESIGN_NICKNAME/$FLOW_VARIANT/` 组织，默认 variant 为 `base`。

## 综合（Yosys / ABC）常用变量

在 `config.mk` 中常见：

| 变量 | 作用 |
| --- | --- |
| `VERILOG_FILES` | RTL 文件列表 |
| `SDC_FILE` | 约束文件 |
| `ABC_AREA` | 倾向面积的 ABC 优化 |
| `SYNTH_HIERARCHICAL` / `OPENROAD_HIERARCHICAL` | 层次化综合/优化 |
| `SWAP_ARITH_OPERATORS` | 算术算子变换，有时改善时序 |
| `SYNTH_ARGS` | 传给 Yosys 的额外参数 |

综合后先看 `1_synth.v` 是否生成，再用 OpenSTA 或 ORFS 报告查看预估 WNS/面积。预估负裕量不等于最终签核失败，但严重的组合逻辑瓶颈应在前端消化。

## Floorplan / Placement / CTS / Routing 旋钮

| 变量 | 阶段 | 说明 |
| --- | --- | --- |
| `CORE_UTILIZATION` | Floorplan | 核利用率；过低浪费面积，过高易拥塞 |
| `CORE_ASPECT_RATIO` / `CORE_MARGIN` | Floorplan | 核形状与边距 |
| `PLACE_DENSITY` / `PLACE_DENSITY_LB_ADDON` | Place | 布局密度及下界增量 |
| `CELL_PAD_IN_SITES_GLOBAL_PLACEMENT` | Place | 全局布局单元间距，影响拥塞与时序 |
| `CTS_BUF_DISTANCE` / CTS 缓冲单元相关变量 | CTS | 时钟树缓冲间距与单元选择 |
| `TNS_END_PERCENT` | Repair | 时序修复覆盖的 TNS 百分比 |
| `SETUP_REPAIR_PHASES` | Repair | 建立时间修复策略 |
| `SKIP_INCREMENTAL_REPAIR` | Repair | 跳过部分增量修复（拥塞 workaround 时可见） |

不要通过改 SDC 来“修复”时序。应调整物理/综合旋钮或在允许范围内改写组合逻辑。

## OpenSTA 诊断

在 OpenROAD/OpenSTA Tcl 中常用：

```tcl
read_db <design.odb>
report_checks -path_delay max -fields {slew cap input_pins nets} -format full_clock_expanded
report_checks -path_delay min
report_wns
report_tns
report_clock_skew
report_check_types -max_slew -max_cap -max_fanout -violators
report_power
report_design_area
```

读路径时关注：启动点（input delay 或寄存器）、组合深度、高扇出网、未经缓冲的长线、时钟 latency/skew。Hold 违例优先检查 CTS 与 post-route repair，而不是放宽约束。

## 常见报错与排查

| 现象 | 建议 |
| --- | --- |
| `1_synth.v` 未生成 / Yosys error | 检查 `VERILOG_FILES`、`include` 路径、顶层模块名是否与 `DESIGN_NAME` 一致 |
| Global Route congestion overflow | 降低利用率或密度、增大 padding、检查 floorplan 通道；必要时清理后重做 place |
| Detailed routing / DRC 残留 | 先看拥塞热点与 antenna；不要在违例热区继续堆密度 |
| Setup WNS 很差但拥塞不高 | 回看综合逻辑级数与 `report_checks -path_delay max` 的关键路径 |
| Hold WNS 为负 | 检查时钟树、`report_checks -path_delay min`；用 ORFS hold repair 而不是改 clock period |
| OpenSTA 无时钟 / 约束丢失 | 确认 `SDC_FILE` 被加载，且 `create_clock` 打在正确端口上 |
| 工具读写权限错误 | 设计输出必须写在 `WORK_HOME`；不要修改 ORFS 只读的 `platforms/` 或 `tools/` |

## 推荐迭代顺序

1. 确认功能和接口：仿真（或至少冒烟）通过后再烧流程。
2. `make synth`，阅读综合日志与初步路径。
3. `make cts`，看拥塞估计、skew 和 post-CTS WNS/TNS。
4. `make finish`，以 post-route 的 WNS/TNS、Hold、DRC、面积与功耗为准做最终取舍。
5. 每次只改少量旋钮并记录，避免同时大幅度改 floorplan 与密度导致无法归因。
