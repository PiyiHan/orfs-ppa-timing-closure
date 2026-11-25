# ORFS-PPA-Timing-Closure: 端到端数字芯片 PPA 优化与时序收敛任务（Harbor Multi-step）

## 1. 工程背景与考察目标

在真实数字 ASIC 开发中，芯片实现并非一次性的代码生成，而是跨越 **RTL 综合、布局规划（Floorplan）、标准单元布局（Placement）、时钟树综合（CTS）、布线（Routing）与签核（Signoff）** 的长程迭代优化过程。工程师需要在 **性能（Timing / WNS / TNS）、功耗（Power）、面积（Area）以及可布线性（Routability / DRC）** 之间进行持续权衡，并在严格遵守功能正确性与时序约束（SDC）的前提下完成时序收敛。

本任务基于开源 RTL-to-GDSII 工具链 [OpenROAD-flow-scripts (ORFS)](https://github.com/the-openroad-project/openroad-flow-scripts) 与 [Harbor Multi-step 评测框架](https://docs.harborframework.com/tasks/multi-step)，以 **NanGate45 工艺节点下的 AES-128 硬件加密核（`aes_cipher_top`）** 为载体，构造了一道端到端 PPA 优化挑战：黄金时钟为 `0.84 ns`（不可放宽），Baseline 在该约束下 Setup 已收敛，主要差距在 Core Area（功耗几乎持平），Agent 须在硬门控下压缩面积并保持签核质量。

### 核心考察维度

- **长程跨阶段规划（Long-horizon）**：任务拆分为「前端综合 → 布局与 CTS → 布线与签核」三个真实 Tape-out 里程碑，考察 Agent 跨阶段状态交接（Handoff）与迭代求解能力。
- **多工具协同**：综合运用仿真器（Icarus Verilog / Verilator）、逻辑综合与等价性检查（Yosys / EQY）、物理实现（OpenROAD）与静态时序/功耗分析（OpenSTA）。
- **真实工程权衡（PPA Trade-off）**：在硬约束（功能零回归、形式等价、DRC=0、Hold 清洁、SDC 不可放宽）下，同步优化 Setup Timing、Core/Die Area 与 Total Power。
- **指令遵循与防作弊**：引入 [Harbor Separate Verifier](https://docs.harborframework.com/tasks/separate-verifier) 独立验证容器，杜绝放宽时钟约束、伪造报告或删减逻辑等 Reward Hacking 行为。
- **能力边界可观测（Pluggable Skill）**：任务本体保持 Skill-agnostic，同时提供可插拔的 EDA Skill（`skills/orfs-eda-flow/SKILL.md`），支持通过 `--skill` 进行「裸跑 vs. 工具赋能」消融对照。

---

## 2. 工程文件结构与 EDA 工具链

### 2.1 目录结构

```text
orfs-ppa-timing-closure/
├── task.toml                              # Harbor 任务元数据、资源配额、3步编排与 Separate Verifier 配置
├── README.md                              # 任务说明与复现文档
├── environment/
│   ├── Dockerfile                         # 锁定版本 ORFS + 仿真/等价性/分析工具（离线可复现）
│   └── starter/                           # 初始待优化工程（挂入容器 /workspace）
│       ├── rtl/                           # AES-128 RTL 源码
│       ├── constraints/constraint.sdc     # 工作区时钟约束（0.84 ns；Agent 可写，Verifier 对照 golden）
│       ├── config.mk                      # 初始基线 ORFS 配置
│       ├── Makefile                       # 封装各阶段运行与冒烟仿真命令
│       └── tb/tb_smoke.sv                 # 基础冒烟测试平台
├── tests/                                 # 独立验证器资产（对 Agent 不可见）
│   ├── golden/
│   │   ├── constraint.sdc                 # 签核强制使用的黄金 SDC
│   │   ├── rtl_golden/                    # 黄金 RTL（用于形式等价性校验）
│   │   └── tb_signoff.sv                  # 完整黄金测试集（NIST FIPS-197 + 随机向量，约 1006 组）
│   ├── scripts/
│   │   ├── extract_signoff_metrics.tcl    # 从 6_final.odb 独立重算签核 PPA/DRC 的 Tcl 脚本
│   │   └── check_lec.ys                   # Yosys 逻辑等价性检查脚本
│   ├── helpers.py                         # 防作弊校验、仿真/LEC 调用与连续评分引擎
│   └── baselines.json                     # 锁定的 Baseline / Oracle 实测锚点
├── steps/
│   ├── step-1-frontend-synth/             # 阶段 1：前端 RTL/综合优化与 Netlist Handoff
│   │   ├── instruction.md
│   │   ├── tests/test.sh
│   │   └── solution/solve.sh
│   ├── step-2-place-cts/                  # 阶段 2：Floorplan、Placement 与 CTS
│   │   ├── instruction.md
│   │   ├── tests/test.sh
│   │   └── solution/solve.sh
│   └── step-3-route-signoff/              # 阶段 3：详细布线、时序收敛与 PPA 终极签核
│       ├── instruction.md
│       ├── tests/test.sh
│       └── solution/solve.sh
└── skills/
    └── orfs-eda-flow/
        └── SKILL.md                       # 可插拔 ORFS 工具链指南（默认不加载）
```

### 2.2 EDA 工具链与环境隔离设计

| 组件 | 工具与版本 | 职责说明 |
| :--- | :--- | :--- |
| **综合与形式验证** | Yosys / ABC（内置于锁定版 `openroad/orfs`）+ Z3 | RTL 逻辑综合、网表映射与逻辑等价性校验（LEC） |
| **物理实现与签核** | OpenROAD + OpenSTA + KLayout（内置于锁定版 `openroad/orfs`） | Floorplan、Placement、CTS、Routing、寄生抽取、STA/Power/DRC 签核 |
| **工艺库 (PDK)** | NanGate45 (`nangate45`) | 45nm 开源标准单元库，单位为 ns/um，单轮迭代高效且具备真实时序与拥塞特征 |
| **功能仿真** | Icarus Verilog (`iverilog`) + Verilator | RTL 功能仿真、Lint 检查与黄金测试向量回归 |
| **容器架构** | **Single-container 主环境 + Separate Verifier 独立评分容器** | Agent 通过原生 CLI/Makefile 操作本地只读 EDA 工具链（`/OpenROAD-flow-scripts` 设为只读），避免多容器 RPC 失真；评分阶段在全新干净容器内仅基于受检 Artifact 独立重跑签核，彻底隔离评分逻辑与测试集。 |
| **网络与确定性** | `network_mode = "no-network"`，固定 `NUM_CORES = 4` | 全程断网离线运行，固定工具镜像版本与线程数，确保结果严格可复现。 |

---

## 3. Multi-step 流程设计与设计权衡

本任务遵循 [Harbor Multi-step 规范](https://docs.harborframework.com/tasks/multi-step)，采用 3 步递进式里程碑与 `multi_step_reward_strategy = "final"` 聚合策略：

1. **Step 1 — 前端综合探索（`step-1-frontend-synth`）**
   - **目标**：分析关键路径与综合瓶颈，在保持接口与周期级行为不变的前提下优化组合逻辑与综合策略，产出综合网表（ORFS 26Q4 写出 `1_2_yosys.v`；`task.toml` 的 artifact 路径是 `1_synth.v`，Makefile 会拷贝，验证器兼容两者）与 `handoff_notes.md`。
   - **门控策略**：硬约束（功能仿真 100% 通过 + LEC 通过 + 综合无错）设置 `min_reward = 1.0`，任一失败则触发早停；综合后时序与面积作为软性监控指标记录，不因轻度估算负裕量阻断进入后端。
2. **Step 2 — 布局规划、布局与时钟树综合（`step-2-place-cts`）**
   - **目标**：承接前端 Netlist Handoff，通过调优 Floorplan、Placement Density、Cell Padding 与 CTS 策略控制拥塞、Clock Skew 与早期时序违例，产出合法的 `4_cts.odb`。
   - **门控策略**：硬约束为成功生成合法 `4_cts.odb` 且无致命拥塞/工具崩溃；允许将轻度局部违例带入布线阶段精修。
3. **Step 3 — 详细布线与签核时序收敛（`step-3-route-signoff`）**
   - **目标**：完成详细布线、寄生抽取与 Post-Route 时序/Hold/DRC 修复，交付 `6_final.odb` 与 `6_final.gds`，在满足全部硬门控下最大化最终 PPA 综合分。
   - **聚合策略**：采用 `multi_step_reward_strategy = "final"`，以最终端到端签核结果作为整个 Trial 的成绩，避免将中间阶段与终极签核做无意义的算术平均。
4. **上下文交接（Session Resume）设计**
   - 默认不启用 `--resume-trajectory`（每步新起会话，保留文件系统持久化），高度还原芯片工程中「前端交付 Netlist + 报告给后端」的真实 Handoff 场景；同时也支持在评估时传入 `--resume-trajectory` 对比长上下文记忆对后端收敛的增益。

### 3.1 各步可见性、可改范围与产物交接

Agent 侧跨步共享同一 `/workspace`（由 `environment/starter/` 初始化）；Verifier 为 Separate 容器，**只挂载** `task.toml` 中该步 `artifacts` 列出的路径，且看不到 Agent 对话。评分实现在 `tests/helpers.py`（各步 `steps/*/tests/test.sh` 只负责调用 `step1` / `step2` / `step3`）。`tests/` 对 Agent 不可见。

| 步骤 | Agent 可见 | 允许改动 | 主要产出（artifacts） | Verifier（`helpers.py`） |
| :--- | :--- | :--- | :--- | :--- |
| **Step 1** `step-1-frontend-synth` | 全 `/workspace`（RTL、`config.mk`、SDC、Makefile、smoke TB）；**不可见** `tests/` | RTL 组合逻辑结构；`config.mk` 综合相关旋钮；可写 `scripts_override/`、`handoff_notes.md` | `rtl/`、`config.mk`、`constraints/`、`scripts_override/`、综合网表（ORFS 26Q4 写出 `1_2_yosys.v`；`artifacts` 名 `1_synth.v`，Makefile 会拷贝，两者都认）、`handoff_notes.md` | `check_config_integrity` + 黄金 TB 仿真 + RTL↔黄金 LEC + 综合网表存在（`min_reward`） |
| **Step 2** `step-2-place-cts` | 上步残留的 `/workspace`（含网表与配置） | Floorplan / Place / CTS 旋钮（如利用率、密度、`TNS_END_PERCENT` 等）；物理 Tcl 可放 `scripts_override/` | 上列 + `4_cts.odb` | 仅 integrity + 合法 `4_cts.odb`（本步不重跑仿真/LEC） |
| **Step 3** `step-3-route-signoff` | 同上，承接 CTS 结果 | 布线与签核相关旋钮；仍不得放宽 SDC | 上列 + `6_final.odb` / `.v` / `.gds` / `.spef` | integrity + 黄金 TB + LEC；用黄金 SDC 从 `6_final.odb` 重算指标；DRC=0 且 Hold≥0 后才算连续 PPA 分 |

`/workspace` 里的 SDC 与 `config.mk` **对 Agent 可写**（镜像只读的是 ORFS `tools/`、`platforms/`、`flow/scripts/`）。每步都会跑 `check_config_integrity`：周期必须等于 `tests/golden/constraint.sdc` 的 0.84 ns，并拦截时序例外与 `SDC_FILE` 重定向。Step 3 签核不读 Agent 的 SDC/JSON/log，由 `tests/scripts/extract_signoff_metrics.tcl` 强制加载黄金 SDC。

`tests/golden/rtl_golden/` 与 `environment/starter/rtl/` **初始内容相同**，是 Agent 看不见的等价参考；LEC 比的是提交 RTL（及网表）和这份黄金 RTL。`starter/tb/tb_smoke.sv` 只有 2 组向量，给 Agent 做 `make sim-smoke`；Verifier 在 Step 1 与 Step 3 用 `tests/golden/tb_signoff.sv`（NIST + 随机，约 1006 组），故意与 smoke 分开。`tests/scripts/check_lec.ys` 是 LEC 骨架（`helpers.py` 会生成等价脚本）。

Oracle **不是搜索出来的**：各步 `solution/solve.sh` 把手工标定的 `config_stepN.mk` 写入 `config.mk`，再跑对应 `make` 目标。Harbor `--agent oracle` 按步串行调用这些脚本（任务内无顶层 `solution/`）。`aes_ng45_fp.def` 在 solution 目录中，参考配置未启用。

---

## 4. 运行方式与验证流程

### 4.1 前置依赖

- Docker Engine（建议至少分配 **8 vCPU / 16 GB RAM / 20 GB 磁盘**）
- Python 3.12+ 与 [Harbor CLI](https://www.harborframework.com/docs/tasks)（建议锁定 `harbor>=0.24`）

### 4.2 运行命令

```bash
# 1. 运行 Oracle 参考解（验证任务环境、流程完整性与满分复现）
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent oracle

# 2. 无操作 Agent（nop）：不修改 workspace。Step 1 没有综合网表，门控失败。
#    §6 的 Baseline（reward 0.5384）不是这条命令，而是用 starter 的 config.mk 跑完整条 flow。
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent nop

# 3. 评测真实 Agent（Mode A：无 Skill 裸跑，考察先验知识与自主探索能力）
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent opencode \
  --model <your-model-name>

# 4. 评测真实 Agent（Mode B：注入可插拔 EDA Skill，聚焦物理优化与 PPA 权衡能力）
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent opencode \
  --model <your-model-name> \
  --skill ./orfs-ppa-timing-closure/skills/orfs-eda-flow

# 5. （可选）开启跨步对话继承，对比 Context Resume 收益
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent opencode \
  --model <your-model-name> \
  --skill ./orfs-ppa-timing-closure/skills/orfs-eda-flow \
  --resume-trajectory
```

### 4.3 独立验证与防 Reward Hacking 流程

每个阶段结束后，Harbor 启动独立的 Separate Verifier 容器，只挂载该步 `artifacts`（`rtl/`、`config.mk`、`scripts_override/`、综合网表 `1_2_yosys.v` / `1_synth.v`，以及 Step 2 起的 `4_cts.odb`、Step 3 的 `6_final.odb` / `6_final.gds`）。各步实际检查以 §3.1 为准：

1. **每步都做配置与约束完整性审查**：扫描 `config.mk`、workspace SDC 与 Tcl hook，拦截放宽时钟周期、`set_false_path`、`set_multicycle_path`、`SDC_FILE` 重定向等非法操作。
2. **Step 1 与 Step 3 做功能仿真与形式等价**：用 `tb_signoff.sv`（约 1006 组）仿真提交的 RTL，并用 Yosys LEC 对照黄金 RTL。Step 2 不重跑这两项。
3. **仅 Step 3 做独立签核**：不读 Agent 的日志或 JSON，加载 `tests/golden/constraint.sdc`，从 `6_final.odb` 重算 WNS、TNS、Hold、Area、Power、DRC。
4. **写入奖励文件**：生成 `/logs/verifier/reward.txt`（`[0.0, 1.0]` 标量主分）与 `/logs/verifier/reward.json`（Harbor 0.27 要求顶层必须全是有限数字）；门控状态与多维细项写在 `/logs/verifier/reward_details.json`。

---

## 5. 评分维度与评价指标

最终评分采用 **硬门控 × 连续归一化 PPA 加权分**，既保证芯片签核的严肃底线，又为 RL 训练与模型评测提供平滑区分度：

$$R_{\text{final}} = G_{\text{integrity}} \cdot G_{\text{func}} \cdot G_{\text{flow}} \cdot \text{clip}\Big(0.45\, S_{\text{timing}} + 0.30\, S_{\text{area}} + 0.15\, S_{\text{power}} + 0.10\, S_{\text{phys}},\ 0,\ 1\Big)$$

| 评估类别 | 指标 / 维度 | 权重 / 规则 | 判定标准与归一化说明 |
| :--- | :--- | :--- | :--- |
| **硬约束门控** | `G_integrity` | 否决项 (0/1) | SDC 未被篡改、无非法时序例外指令、顶层端口与协议未变 |
| **硬约束门控** | `G_func` | 否决项 (0/1) | 黄金 Testbench 100% 通过且 Yosys LEC 形式等价通过 |
| **硬约束门控** | `G_flow` | 否决项 (0/1) | 合法生成 `6_final.odb`/`6_final.gds`，且 `DRC = 0`、`Hold WNS >= 0` |
| **性能 (Timing)** | `S_timing` | **45%** | $\text{WNS} < 0$ 时按相对 Baseline 收敛进度平滑映射到 $[0, 0.65]$；$\text{WNS} \ge 0$ 且 $\text{TNS} = 0$ 时获基础分 $0.75$，并按裕量向 Oracle 锚点线性递增至 $1.0$ |
| **面积 (Area)** | `S_area` | **30%** | Core Area / StdCell Area 相对 Baseline 到 Oracle 锚点的缩减比例，截断至 $[0, 1]$ |
| **功耗 (Power)** | `S_power` | **15%** | OpenSTA 签核 Total Power 相对 Baseline 到 Oracle 锚点的缩减比例，截断至 $[0, 1]$ |
| **签核质量** | `S_phys` | **10%** | Antenna 违例 = 0（占 50%）+ `max_slew` / `max_cap` / `max_fanout` 违例 = 0（占 50%） |

---

## 6. Oracle 参考解运行结果与复现记录

> 说明：下表是固定镜像、`NUM_CORES=4`、离线环境下的实测结果，并已写入 `tests/baselines.json`。Baseline 是 starter `config.mk` 跑完整条 flow；Oracle 是三步 `solve.sh`。这不是 `harbor --agent nop`，也不是下面第 3–5 条 Agent 命令的成绩。

### 6.1 环境版本锁定

- **基础镜像**：`openroad/orfs:26Q4-554-g82ac25be5@sha256:b59431453d328d6fbf36669e1908b15634c11da51970cc2218a702783dcd6174`
- **工艺库**：`nangate45`
- **目标时钟周期（Golden SDC）**：`0.84`
- **硬件与并发配置**：8 vCPU / 16 GB RAM，`NUM_CORES=4`，`network_mode="no-network"`

### 6.2 Baseline vs. Oracle 实测指标对比

| 阶段 / 指标 | Baseline（初始配置） | Oracle 参考解 | 说明 |
| :--- | :--- | :--- | :--- |
| **Step 1 功能仿真 & LEC** | Pass / Pass | Pass / Pass | 门控通过 |
| **Step 2 CTS 合法性** | `Pass` | Pass | 生成合法 `4_cts.odb` |
| **Setup WNS (ns)** | `0.005438` | `0.006188` | 目标 $\ge 0$ |
| **Setup TNS (ns)** | `0.00` | `0.00` | 目标 $= 0$ |
| **Hold WNS (ns)** | `0.10479` | `0.102505` | 硬门控 $\ge 0$ |
| **Core / StdCell Area ($\mu\text{m}^2$)** | `73516.016 / 20188.868` | `61583.256 / 19797.05` | Core Area 约缩减 16% |
| **Total Power (mW)** | `44.457` | `43.411` | 接近持平（OpenSTA 签核值） |
| **DRC Violations** | `0` | `0` | 硬门控 $= 0$ |
| **Antenna / Slew / Cap Violations** | `0 / 0 / 0` | `0 / 0 / 0` | 签核质量项 |
| **总运行耗时（3 步合计）** | `299 s` | `341 s` | 远低于单步超时阈值 |
| **最终 `reward.txt` 得分** | `0.5384` | **`1.0000`** | 连续 2 次复现一致 |

---

## 7. 数据集扩展路线图

本任务模板可直接复用扩展为体系化的数字芯片 PPA Benchmark 套件：

1. **ORFS 工业设计主力集**：复用 [ORFS](https://github.com/the-openroad-project/openroad-flow-scripts) 内置的 `aes`、`jpeg`、`ibex`、`ethmac` 等设计，覆盖 `nangate45`、`asap7`、`sky130hd` 多工艺节点，为每个设计补齐确定性黄金 Testbench 与 LEC。
2. **CVDP 前后端联合子集**：从 [NVIDIA CVDP Benchmark](https://github.com/NVlabs/cvdp_benchmark)（[arXiv:2506.14074](https://arxiv.org/abs/2506.14074)）中筛选可综合的中等规模模块（特别是 QoR 改进与模块复用类别），直接复用其 Spec 与 Testbench 并接入 ORFS 物理流。
3. **带 Macro/SRAM 高阶物理集**：引入含 SRAM Macro 的设计（如 `tinyRocket` 或 [HighTide](https://vlsida.github.io/HighTide/) 基准设计），扩展考察 Macro Placement、Halo 与 PDN/IR Drop 权衡。
