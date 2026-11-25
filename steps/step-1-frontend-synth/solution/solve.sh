#!/bin/bash
# Oracle for step-1-frontend-synth: install the reference config.mk and run `synth`.
set -euo pipefail

WORKDIR="${WORKDIR:-${WORKSPACE:-/workspace}}"
SOLDIR="/solution"
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "${SOLDIR}/config_step1.mk" ]; then
  if [ -f "${HERE}/config_step1.mk" ]; then
    SOLDIR="$HERE"
  else
    echo "ERROR: oracle config_step1.mk not found" >&2
    exit 1
  fi
fi

export PATH="/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:/OpenROAD-flow-scripts/tools/install/kepler-formal/bin:${PATH:-}"
export FLOW_HOME="${FLOW_HOME:-/OpenROAD-flow-scripts/flow}"
export WORK_HOME="$WORKDIR"
export DESIGN_CONFIG="${WORKDIR}/config.mk"
export NUM_CORES="${NUM_CORES:-4}"

mkdir -p "$WORKDIR"
cp -f "${SOLDIR}/config_step1.mk" "${WORKDIR}/config.mk"
# Keep the golden-equivalent starter SDC; never rewrite the period.

if [ ! -f "${WORKDIR}/constraints/constraint.sdc" ]; then
  echo "ERROR: missing ${WORKDIR}/constraints/constraint.sdc" >&2
  exit 1
fi

cat > "${WORKDIR}/handoff_notes.md" <<'EOF'
# Frontend handoff (oracle)

- RTL: official OpenCores `aes_cipher_top` (ports and latency unchanged).
- Suggested backend starting point: CORE_UTILIZATION=30, PLACE_DENSITY_LB_ADDON=0.20, TNS_END_PERCENT=100, SETUP_REPAIR_PHASES=PARALLEL_EVAL.
- Clock: do not relax the golden SDC period.
EOF

cd "$WORKDIR"
make -C "$WORKDIR" synth NUM_CORES="$NUM_CORES" WORK_HOME="$WORKDIR" DESIGN_CONFIG="$DESIGN_CONFIG"
