#!/bin/bash
# Oracle for step-2-place-cts: install the reference config.mk and run `cts`.
set -euo pipefail

WORKDIR="${WORKDIR:-${WORKSPACE:-/workspace}}"
SOLDIR="/solution"
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "${SOLDIR}/config_step2.mk" ]; then
  if [ -f "${HERE}/config_step2.mk" ]; then
    SOLDIR="$HERE"
  else
    echo "ERROR: oracle config_step2.mk not found" >&2
    exit 1
  fi
fi

export PATH="/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:/OpenROAD-flow-scripts/tools/install/kepler-formal/bin:${PATH:-}"
export FLOW_HOME="${FLOW_HOME:-/OpenROAD-flow-scripts/flow}"
export WORK_HOME="$WORKDIR"
export DESIGN_CONFIG="${WORKDIR}/config.mk"
export NUM_CORES="${NUM_CORES:-4}"

mkdir -p "$WORKDIR"
cp -f "${SOLDIR}/config_step2.mk" "${WORKDIR}/config.mk"
# Keep the golden-equivalent starter SDC; never rewrite the period.
if [ ! -f "${WORKDIR}/constraints/constraint.sdc" ]; then
  echo "ERROR: missing ${WORKDIR}/constraints/constraint.sdc" >&2
  exit 1
fi

cd "$WORKDIR"
make -C "$WORKDIR" cts NUM_CORES="$NUM_CORES" WORK_HOME="$WORKDIR" DESIGN_CONFIG="$DESIGN_CONFIG"
