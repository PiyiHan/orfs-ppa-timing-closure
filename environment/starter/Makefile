# Convenience wrappers around OpenROAD-flow-scripts for this task.
# All flow outputs are written under /workspace/{results,logs,reports,objects}.

FLOW_HOME      ?= /OpenROAD-flow-scripts/flow
WORK_HOME      ?= /workspace
DESIGN_CONFIG  ?= /workspace/config.mk
NUM_CORES      ?= 4

export FLOW_HOME WORK_HOME DESIGN_CONFIG NUM_CORES
export PATH := /OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:/OpenROAD-flow-scripts/tools/install/kepler-formal/bin:$(PATH)

ORFS_MAKE = $(MAKE) -C $(FLOW_HOME) DESIGN_CONFIG=$(DESIGN_CONFIG) WORK_HOME=$(WORK_HOME) NUM_CORES=$(NUM_CORES)

RESULTS = $(WORK_HOME)/results/nangate45/aes/base

.PHONY: help synth floorplan place cts route finish clean clean_synth clean_place clean_cts clean_route sim-smoke

help:
	@echo "Targets: sim-smoke synth floorplan place cts route finish clean"
	@echo "WORK_HOME=$(WORK_HOME) DESIGN_CONFIG=$(DESIGN_CONFIG) NUM_CORES=$(NUM_CORES)"
	@echo "Results: $(RESULTS)"

synth:
	$(ORFS_MAKE) synth

floorplan:
	$(ORFS_MAKE) floorplan

place:
	$(ORFS_MAKE) place

cts:
	$(ORFS_MAKE) cts

route:
	$(ORFS_MAKE) route

finish:
	$(ORFS_MAKE) finish

clean:
	$(ORFS_MAKE) clean_all

clean_synth:
	$(ORFS_MAKE) clean_synth

clean_place:
	$(ORFS_MAKE) clean_place

clean_cts:
	$(ORFS_MAKE) clean_cts

clean_route:
	$(ORFS_MAKE) clean_route

sim-smoke:
	iverilog -g2012 -I /workspace/rtl -o /tmp/tb_smoke.vvp /workspace/rtl/*.v /workspace/tb/tb_smoke.sv
	vvp /tmp/tb_smoke.vvp
