# Baseline (intentionally poor) ORFS configuration for aes_cipher_top / nangate45.
# Agents may retune synthesis and physical knobs in this file, but must not
# redirect SDC_FILE, change the clock period, or add timing exceptions.

export DESIGN_NICKNAME = aes
export DESIGN_NAME     = aes_cipher_top
export PLATFORM        = nangate45

# Keep Verilog / SDC paths inside /workspace so Harbor artifacts stay self-contained.
export VERILOG_FILES = $(sort $(wildcard /workspace/rtl/*.v))
export SDC_FILE      = /workspace/constraints/constraint.sdc

# Inferior floorplan / placement starting point: oversized die, loose density,
# almost no timing repair. The flow is still expected to complete.
export CORE_UTILIZATION = 25
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 2
export PLACE_DENSITY = 0.40
export TNS_END_PERCENT = 5
export SKIP_INCREMENTAL_REPAIR = 1
