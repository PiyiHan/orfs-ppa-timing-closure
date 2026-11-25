# ORFS-PPA-Timing-Closure: 端到端数字芯片 PPA 优化与时序收敛任务（Harbor Multi-step）

## 1. 工程背景与考察目标

在真实数字 ASIC 开发中，芯片实现并非一次性的代码生成，而是跨越 **RTL 综合、布局规划（Floorplan）、标准单元布局（Placement）、时钟树综合（CTS）、布线（Routing）与签核（Signoff）** 的长程迭代优化过程。工程师需要在性能、面积、功耗与可布线性之间反复权衡，并在严格遵守功能正确性与时序约束的前提下完成签核。

本任务基于开源 RTL-to-GDSII 工具链 [OpenROAD-flow-scripts (ORFS)](https://github.com/the-openroad-project/openroad-flow-scripts) 与 [Harbor Multi-step 评测框架](https://docs.harborframework.com/tasks/multi-step)，以 NanGate45 工艺节点下的 **AES-128 硬件加密核（`aes_cipher_top`）** 为载体。在 `0.84 ns` 的紧时钟约束下，设计已接近该架构的频率极限，进一步压缩时钟周期的空间很小；因此，任务的核心优化目标是在**严格守住 `0.84 ns` 时序收敛、DRC 清零与功能等价**等硬门控的前提下，通过综合与物理实现调优显著压缩芯片面积、兼顾功耗并保持签核质量。

### 核心考察维度

* **长程跨阶段规划**：将完整实现拆分为「前端综合 → 布局与 CTS → 布线与签核」三个真实 Tape-out 里程碑，考察 Agent 跨阶段状态交接与迭代收敛能力。

* **多工具协同**：综合运用仿真器（Icarus Verilog / Verilator）、逻辑综合与形式等价性检查（Yosys / Kepler Formal）、物理实现（OpenROAD）与静态时序/功耗分析（OpenSTA）。

* **真实 PPA 权衡**：在不可放宽的时序、功能与物理规则硬约束下，平衡 Core/StdCell Area、Setup/Hold Slack 与 Total Power。

* **指令遵循与防作弊**：采用 [Harbor Separate Verifier](https://docs.harborframework.com/tasks/separate-verifier) 独立验证容器，杜绝放宽时钟约束、伪造报告或删减逻辑等 Reward Hacking 行为。

* **能力边界可观测**：任务本体保持 Skill-agnostic，另提供可插拔的 EDA Skill（`skills/orfs-eda-flow/SKILL.md`），支持通过 `--skill` 开展「无 Skill 裸跑 vs. 工具赋能」消融对照。

## 2. 工程文件结构与 EDA 工具链

### 2.1 目录结构

```
orfs-ppa-timing-closure/
├── task.toml                              # 任务元数据、资源配额、3 步编排与 Separate Verifier 配置
├── README.md                              # 任务说明与复现文档
├── environment/
│   ├── Dockerfile                         # 锁定版本 ORFS + 仿真/形式验证/分析工具（离线可复现）
│   └── starter/                           # 初始待优化工程（挂入容器 /workspace）
│       ├── rtl/                           # AES-128 RTL 源码
│       ├── constraints/constraint.sdc     # 目标时钟约束（0.84 ns）
│       ├── config.mk                      # 初始基线 ORFS 配置
│       ├── Makefile                       # 各阶段运行与冒烟仿真快捷入口
│       └── tb/tb_smoke.sv                 # 基础冒烟测试平台
├── tests/                                 # 独立验证资产（对 Agent 不可见）
│   ├── golden/
│   │   ├── constraint.sdc                 # 签核强制加载的黄金 SDC
│   │   ├── rtl_golden/                    # 黄金 RTL（用于形式等价性校验）
│   │   └── tb_signoff.sv                  # 黄金测试集（NIST FIPS-197 + 随机向量，约 1006 组）
│   ├── scripts/
│   │   ├── extract_signoff_metrics.tcl    # 从 6_final.odb 独立重算签核 PPA 与 DRC
│   │   └── check_lec.ys                   # Yosys 逻辑等价性检查参考脚本
│   ├── helpers.py                         # 防作弊校验、仿真/LEC 调用与连续评分引擎
│   └── baselines.json                     # 锁定的 Baseline 与 Oracle 实测锚点
├── steps/
│   ├── step-1-frontend-synth/             # Step 1：前端综合与 Netlist Handoff
│   │   ├── instruction.md
│   │   ├── tests/test.sh
│   │   └── solution/{solve.sh, config_step1.mk}
│   ├── step-2-place-cts/                  # Step 2：Floorplan、Placement 与 CTS
│   │   ├── instruction.md
│   │   ├── tests/test.sh
│   │   └── solution/{solve.sh, config_step2.mk}
│   └── step-3-route-signoff/              # Step 3：详细布线、时序收敛与终极签核
│       ├── instruction.md
│       ├── tests/test.sh
│       └── solution/{solve.sh, config_step3.mk}
└── skills/
    └── orfs-eda-flow/
        └── SKILL.md                       # 可插拔 ORFS 工具链指南（默认不加载）

```

### 2.2 EDA 工具链与环境隔离

| 组件 | 工具与配置 | 职责说明 | 
| ----- | ----- | ----- | 
| **综合与形式验证** | Yosys / ABC + Kepler Formal + Z3 | RTL 逻辑综合、网表映射与逻辑等价性校验（LEC） | 
| **物理实现与签核** | OpenROAD + OpenSTA + KLayout | Floorplan、Placement、CTS、Routing、寄生抽取与 PPA/DRC 签核 | 
| **工艺库（PDK）** | NanGate45 (`nangate45`) | 45nm 开源标准单元库，单轮全流程约 5 分钟，适合多轮迭代 | 
| **功能仿真** | Icarus Verilog (`iverilog`) + Verilator | RTL 功能回归仿真与 Lint 检查 | 
| **容器架构** | Single-container 主环境 + Separate Verifier | Agent 通过原生 CLI/Makefile 操作本地只读 EDA 工具链；评分阶段在全新独立容器中仅基于受检 Artifact 重跑签核 | 
| **网络与确定性** | `network_mode = "no-network"`，`NUM_CORES = 4` | 全程断网离线运行，锁定镜像 Digest 与线程数，保证严格可复现 | 

## 3. Multi-step 流程与核心设计

### 3.1 三阶段里程碑与门控策略

任务遵循 [Harbor Multi-step 规范](https://docs.harborframework.com/tasks/multi-step)，按真实数字后端里程碑拆分为 3 个阶段。Agent 在各阶段间共享持久化的 `/workspace` 文件系统，Verifier 则作为独立容器仅挂载该步声明的 `artifacts` 进行校验：

| 阶段 | 核心目标与允许改动 | 关键产物（Artifacts） | 阶段门控与验证策略 | 
| ----- | ----- | ----- | ----- | 
| **Step 1** `step-1-frontend-synth` | 分析综合瓶颈，可优化 RTL 组合逻辑与综合旋钮，完成前端综合并撰写 `handoff_notes.md` | `rtl/`、`config.mk`、综合网表（`1_synth.v`）、`handoff_notes.md` | **硬门控早停**（`min_reward = 1.0`）：配置完整性审查 + 黄金 TB 仿真 + RTL 形式等价 + 综合网表合法；综合预估时序仅作软性参考 | 
| **Step 2** `step-2-place-cts` | 承接前端网表，调优利用率、布局密度、Cell Padding 与 CTS 策略，控制拥塞与早期违例 | 上步产物 + `scripts_override/` + `4_cts.odb` | **硬门控早停**（`cts_pass = 1.0`）：配置完整性审查 + 生成合法 `4_cts.odb`；允许轻度局部时序违例带入布线阶段精修 | 
| **Step 3** `step-3-route-signoff` | 完成详细布线、寄生抽取与 Post-Route 时序/Hold/DRC 修复，交付可签核版图 | 上步产物 + `6_final.odb` / `.v` / `.gds` | **全套终极签核**：配置审查 + 黄金 TB + 形式等价 + 黄金 SDC 独立重算 PPA 与 DRC；全部硬门控通过后输出连续 PPA 综合分 | 

### 3.2 奖励聚合与上下文交接（Handoff）

* **最终签核聚合（`multi_step_reward_strategy = "final"`）**：Trial 最终成绩直接取最后执行步骤的得分，避免将中间里程碑与终极签核做无意义的算术平均；若前序步骤触发 `min_reward` 早停，则任务直接以失败结束。

* **默认无上下文继承**：默认不开启 `--resume-trajectory`，每步新起对话会话但保留工作区文件。这一设定还原了芯片工程中「前端通过网表与文档向后端 Handoff」的真实协作边界，同时也支持评测时开启 `--resume-trajectory` 对比长上下文记忆的收益。

### 3.3 资产隔离与防作弊边界

* **工具只读、工作区可写**：镜像中 ORFS 的 `tools/`、`platforms/` 与 `flow/scripts/` 均设为只读；`/workspace` 内的设计与配置允许 Agent 自由迭代，但每步都会执行静态完整性检查，拦截修改时钟周期、添加时序例外或重定向 `SDC_FILE` 等违规操作。

* **冒烟测试与签核测试分离**：工作区仅提供包含 2 组向量的 `tb_smoke.sv` 供 Agent 快速自测；Verifier 持有对 Agent 完全不可见的 `tests/golden/`（包含黄金 RTL、黄金 SDC 与约 1006 组 NIST/随机向量的 `tb_signoff.sv`）。

* **独立重算签核指标**：Step 3 评分不读取 Agent 产生的任何报告或日志，而是由 Verifier 强制加载黄金 SDC 并直接从 `6_final.odb` 重算时序、面积、功耗与 DRC。

### 3.4 Oracle 参考解的设定与运行

由于 PPA 优化属于无唯一闭式解的工程权衡问题，任务采用专家手工标定的分阶段参考配置作为 Oracle（`steps/step-{1,2,3}/solution/config_stepN.mk`）。各步对应的 `solution/solve.sh` 会将参考配置写入工作区并执行相应的 `make` 目标；运行 `harbor run --agent oracle` 时，Harbor 按步串行执行三个阶段的参考脚本，在固定离线环境下稳定跑通全流程并获得满分 `1.0000`。

## 4. 运行方式与验证流程

### 4.1 前置依赖

* Docker Engine（建议至少分配 **8 vCPU / 16 GB RAM / 20 GB 磁盘**）

* Python 3.12+ 与 [Harbor CLI](https://www.harborframework.com/docs/tasks)（建议 `harbor>=0.24`）

### 4.2 运行命令

```
# 1. 运行 Oracle 参考解（验证环境、全流程走通与满分复现）
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent oracle

# 2. 运行无操作基线（验证 Step 1 缺失网表时的早停门控）
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent nop

# 3. 评测 Agent（无 Skill 裸跑，考察先验知识与自主探索能力）
harbor run \
  --path ./orfs-ppa-timing-closure \
  --agent opencode \
  --model <your-model-name>

# 4. 评测 Agent（注入可插拔 EDA Skill，聚焦物理优化与 PPA 权衡能力）
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

### 4.3 独立验证与评分输出

每个阶段结束后，Separate Verifier 按顺序完成以下校验并写出评分结果：

1. **配置与约束审查（每步）**：扫描 `config.mk`、工作区 SDC 与 `scripts_override/`，拦截放宽时钟周期、`set_false_path`、`set_multicycle_path`、`SDC_FILE` 重定向等非法操作。

2. **功能仿真与形式等价（Step 1 / Step 3）**：使用 `tb_signoff.sv` 仿真提交的 RTL，并对照黄金 RTL 与网表执行形式等价性检查。

3. **独立签核抽取（Step 3）**：加载 `tests/golden/constraint.sdc`，直接从 `6_final.odb` 重算 WNS、TNS、Hold、Area、Power、DRC 与电气违例。

4. **写入奖励文件**：输出 `/logs/verifier/reward.txt`（`[0.0, 1.0]` 标量主分）与 `/logs/verifier/reward.json`（顶层均为有限数值以兼容 Harbor 0.27），同时将门控明细与原始 PPA 指标写入 `/logs/verifier/reward_details.json`。

## 5. 评分维度与评价指标

最终评分采用 **硬门控 × 连续归一化 PPA 加权分**，兼顾签核底线与优化区分度：

$$
R_{\text{final}} = G_{\text{integrity}} \cdot G_{\text{func}} \cdot G_{\text{flow}} \cdot \text{clip}\Big(0.45\, S_{\text{timing}} + 0.30\, S_{\text{area}} + 0.15\, S_{\text{power}} + 0.10\, S_{\text{phys}},\ 0,\ 1\Big)
$$

| 评估类别 | 指标 / 维度 | 权重 / 规则 | 判定标准与归一化说明 | 
| ----- | ----- | ----- | ----- | 
| **硬约束门控** | `G_integrity` | 否决项 (0/1) | SDC 未被篡改、无非法时序例外指令、顶层端口与协议未变 | 
| **硬约束门控** | `G_func` | 否决项 (0/1) | 黄金 Testbench 100% 通过且形式等价性检查通过 | 
| **硬约束门控** | `G_flow` | 否决项 (0/1) | 合法生成 `6_final.odb` 与 `6_final.gds`，且 `DRC = 0`、`Hold WNS >= 0` | 
| **性能（Timing）** | `S_timing` | **45%** | $\text{WNS} < 0$ 时按相对 Baseline 收敛进度平滑映射到 $[0, 0.65]$；$\text{WNS} \ge 0$ 且 $\text{TNS} = 0$ 时获基础分 $0.75$，并按裕量向 Oracle 锚点线性递增至 $1.0$ | 
| **面积（Area）** | `S_area` | **30%** | Core Area 相对 Baseline 到 Oracle 锚点的缩减比例，截断至 $[0, 1]$ | 
| **功耗（Power）** | `S_power` | **15%** | OpenSTA 签核 Total Power 相对 Baseline 到 Oracle 锚点的缩减比例，截断至 $[0, 1]$ | 
| **签核质量** | `S_phys` | **10%** | Antenna 违例 = 0（占 50%）+ `max_slew` / `max_cap` / `max_fanout` 违例 = 0（占 50%） | 

## 6. Oracle 参考解运行结果与复现记录

以下数据均在锁定镜像、`NUM_CORES = 4` 与完全离线环境下实测得到，并已固化为 `tests/baselines.json` 中的评分锚点（Baseline 为初始 `starter/config.mk` 跑通全流程的实测基线，Oracle 为三步 `solve.sh` 串行执行的实测结果）。

### 6.1 环境版本锁定

* **基础镜像**：`openroad/orfs:26Q4-554-g82ac25be5@sha256:b59431453d328d6fbf36669e1908b15634c11da51970cc2218a702783dcd6174`

* **工艺库**：`nangate45`

* **目标时钟周期（Golden SDC）**：`0.84 ns`

* **硬件与并发配置**：8 vCPU / 16 GB RAM，`NUM_CORES = 4`，`network_mode = "no-network"`

### 6.2 Baseline vs. Oracle 实测指标对比

| 阶段 / 指标 | Baseline（初始配置） | Oracle 参考解 | 说明 | 
| ----- | ----- | ----- | ----- | 
| **Step 1 功能仿真 & LEC** | Pass / Pass | Pass / Pass | 门控通过 | 
| **Step 2 CTS 合法性** | Pass | Pass | 生成合法 `4_cts.odb` | 
| **Setup WNS (ns)** | `0.005438` | `0.006188` | 满足 $\ge 0$ | 
| **Setup TNS (ns)** | `0.00` | `0.00` | 满足 $= 0$ | 
| **Hold WNS (ns)** | `0.10479` | `0.102505` | 硬门控 $\ge 0$ | 
| **Core / StdCell Area (**$\mu\text{m}^2$**)** | `73516.016 / 20188.868` | `61583.256 / 19797.05` | Core Area 缩减约 16.2% | 
| **Total Power (mW)** | `44.457` | `43.411` | 略有下降（OpenSTA 签核值） | 
| **DRC Violations** | `0` | `0` | 硬门控 $= 0$ | 
| **Antenna / Slew / Cap Violations** | `0 / 0 / 0` | `0 / 0 / 0` | 签核质量满分 | 
| **总运行耗时（3 步合计）** | `299 s` | `341 s` | 远低于单步超时阈值 | 
| **最终 `reward.txt` 得分** | `0.5384` | **`1.0000`** | 连续 2 次复现一致 | 
