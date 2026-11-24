# Step 1 — 前端综合探索（Frontend Synthesis）

你是一名数字前端工程师，需要对 NanGate45 工艺下的 AES-128 加密核 `aes_cipher_top` 做综合前/综合阶段优化，并向前端后端交接一份可用的门级网表。

## 背景

- 工作目录：`/workspace`
- RTL：`/workspace/rtl/`（顶层 `aes_cipher_top`，端口为 `clk, rst, ld, done, key[127:0], text_in[127:0], text_out[127:0]`）
- 时钟约束：见 `/workspace/constraints/constraint.sdc`。当前黄金时钟周期为 **0.84 ns**（含 0.210 ns clock latency 与 20% I/O delay）。**严禁放宽周期或添加时序例外。**
- 冒烟仿真：`make sim-smoke`（仅含少量公开向量；完整黄金测试集对 Agent 不可见）
- 综合：`make synth`（OpenROAD-flow-scripts，结果写入 `/workspace/results/nangate45/aes/base/`）
- 初始 `config.mk` 故意使用较差的综合/物理默认值。

## 目标

在 **保持端口签名与输入到输出的周期精确行为不变** 的前提下，分析关键路径与综合瓶颈，优化组合逻辑和/或综合策略，产出：

1. `/workspace/results/nangate45/aes/base/1_synth.v`
2. `/workspace/handoff_notes.md`（给后端的交接说明：关键路径观察、已尝试的综合旋钮、建议的布局密度/利用率等）

允许修改 `rtl/` 内部组合逻辑结构（例如逻辑共享、表达式整理），以及 `config.mk` 中的综合相关变量。综合后的预估时序/面积仅作诊断，轻度负裕量不会单独阻断进入后端。

## 硬约束

- 不得修改顶层端口、复位/握手协议或加解密延迟（Latency）。
- 不得修改或绕过 SDC：禁止改 `CLOCK_PERIOD` / `clk_period`、禁止 `set_false_path`、`set_multicycle_path`、`set_disable_timing`，禁止重定向 `SDC_FILE`。
- 功能必须与黄金参考（NIST FIPS-197 及随机向量）周期精确一致，并通过 Yosys 形式等价性检查（LEC）。
- 综合必须成功，不得引入非法 latch 或工具错误。

本步任一门控失败将触发任务早停。
