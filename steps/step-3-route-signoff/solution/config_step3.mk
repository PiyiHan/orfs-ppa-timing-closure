# Oracle physical / synthesis configuration (quality reference, not a claimed global optimum).
# Keeps the golden SDC path and does not introduce timing exceptions.

export DESIGN_NICKNAME = aes
export DESIGN_NAME     = aes_cipher_top
export PLATFORM        = nangate45

export VERILOG_FILES = $(sort $(wildcard /workspace/rtl/*.v))
export SDC_FILE      = /workspace/constraints/constraint.sdc

# Tighter floorplan and more aggressive timing repair than the starter.
export CORE_UTILIZATION = 40
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 2
export PLACE_DENSITY_LB_ADDON = 0.20
export TNS_END_PERCENT = 100
export SETUP_REPAIR_PHASES = PARALLEL_EVAL
export SKIP_INCREMENTAL_REPAIR = 1
export SWAP_ARITH_OPERATORS = 1
export OPENROAD_HIERARCHICAL = 1
