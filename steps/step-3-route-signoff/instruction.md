# Step 3 — 详细布线与签核时序收敛（Route / Signoff）

请完成 Global/Detailed Routing、寄生抽取与 Post-Route 的 Timing / Hold / DRC 修复，交付可签核的最终结果。

## 背景

- 运行：`make route`、`make finish`（推荐直接 `make finish`）
- 清理重跑：`make clean_route`
- 最终签核由 **独立 Verifier 容器** 完成：它会忽略你写出的任何 `*.json` / `*.log` 报告，强制加载黄金 SDC，并从你提交的 `6_final.odb` 重新抽取指标。

## 目标产物

- `/workspace/results/nangate45/aes/base/6_final.odb`
- `/workspace/results/nangate45/aes/base/6_final.gds`
- （如流程生成）`6_final.v`、`6_final.spef`

## 最终评分（在全部硬门控通过之后）

\( R = 0.45\,S_{timing} + 0.30\,S_{area} + 0.15\,S_{power} + 0.10\,S_{phys} \)

- **Timing 45%**：Setup WNS / TNS 相对 Baseline 的收敛；WNS ≥ 0 且 TNS = 0 后按正裕量加分
- **Area 30%**：Core / StdCell 面积相对 Baseline → Oracle 锚点的缩减
- **Power 15%**：OpenSTA Total Power 同样相对锚点缩减
- **Signoff Quality 10%**：Antenna = 0（50%），以及 max_slew / max_cap / max_fanout = 0（50%）

## 硬门控（任一失败则总分为 0）

- 功能仿真 100% 通过，且与黄金 RTL 形式等价（LEC）
- SDC 完整、未被放宽或绕过；端口/协议不变
- 合法生成 `6_final.odb` 与 `6_final.gds`
- `DRC = 0`，`Hold WNS ≥ 0`

伪造报告、放宽时钟或删减加密轮次将被判 0 分。
