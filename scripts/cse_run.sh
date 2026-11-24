#!/bin/bash
# Run oracle / nop / anti-cheat inside the complete Singularity image,
# writing the Harbor contract files under $WORK/logs/verifier/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "${HARBOR_EDA_ROOT:-}/env.sh" ]; then
  # shellcheck disable=SC1091
  source "${HARBOR_EDA_ROOT}/env.sh"
elif [ -f "$HOME/harbor_eda/env.sh" ]; then
  # shellcheck disable=SC1091
  source "$HOME/harbor_eda/env.sh"
fi

MODE="${1:-oracle}"
TAG="26Q4-554-g82ac25be5-eda"
SIF="${HARBOR_EDA_SIF:-}"
if [ -z "$SIF" ]; then
  for c in \
      "${HARBOR_EDA_ROOT:-}/images/orfs-ppa-timing-closure-${TAG}.sif" \
      "${ROOT}/images/orfs-ppa-timing-closure-${TAG}.sif" \
      "${HARBOR_EDA_ROOT:-}/images/oss-eda-full.sif"
  do
    if [ -n "$c" ] && [ -f "$c" ]; then
      SIF="$c"
      break
    fi
  done
fi
if [ -z "${SIF:-}" ] || [ ! -f "$SIF" ]; then
  echo "ERROR: complete SIF not found. Build the Docker image, docker-save it," >&2
  echo "and singularity-build docker-archive://... on the research disk." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
JOBROOT="${HARBOR_JOBS_DIR:-${HARBOR_EDA_ROOT:-$ROOT}/jobs}"
WORK="${JOBROOT}/orfs-ppa-${MODE}-${STAMP}"
mkdir -p "${WORK}/workspace" "${WORK}/logs/verifier" "${WORK}/logs/agent" \
         "${WORK}/tests" "${WORK}/solution"

cp -a "${ROOT}/environment/starter/." "${WORK}/workspace/"
cp -a "${ROOT}/tests/." "${WORK}/tests/"
mkdir -p "${WORK}/workspace/results" "${WORK}/workspace/out"

COMMON=(
  singularity exec
  --contain
  --writable-tmpfs
  --pwd /workspace
  --no-home
  -B "${WORK}/workspace:/workspace"
  -B "${WORK}/logs:/logs"
  -B "${WORK}/tests:/tests"
)

run_in() {
  "${COMMON[@]}" -B "${WORK}/solution:/solution" "$SIF" bash -lc "export TMPDIR=/tmp TMP=/tmp TEMP=/tmp; export NUM_CORES=${NUM_CORES:-4}; $1"
}

echo "Image: $SIF"
echo "Work:  $WORK"
echo "Mode:  $MODE"

case "$MODE" in
  oracle)
    for step in step-1-frontend-synth step-2-place-cts step-3-route-signoff; do
      rm -rf "${WORK}/solution"
      mkdir -p "${WORK}/solution"
      cp -a "${ROOT}/steps/${step}/solution/." "${WORK}/solution/"
      chmod +x "${WORK}/solution/solve.sh" || true
      echo "===== oracle ${step} ====="
      run_in "bash /solution/solve.sh"
      cp -f "${ROOT}/steps/${step}/tests/test.sh" "${WORK}/tests/test.sh"
      chmod +x "${WORK}/tests/test.sh"
      run_in "export TESTS_DIR=/tests; bash /tests/test.sh"
      echo "----- reward after ${step} -----"
      cat "${WORK}/logs/verifier/reward.txt"
    done
    ;;
  nop)
    cp -f "${ROOT}/steps/step-1-frontend-synth/tests/test.sh" "${WORK}/tests/test.sh"
    chmod +x "${WORK}/tests/test.sh"
    echo "===== nop (step 1, no agent actions) ====="
    run_in "export TESTS_DIR=/tests; bash /tests/test.sh"
    cat "${WORK}/logs/verifier/reward.txt"
    ;;
  anti-cheat)
    # 1) Tamper SDC clock
    echo "===== anti-cheat: tamper SDC ====="
    rm -rf "${WORK}/workspace"
    mkdir -p "${WORK}/workspace"
    cp -a "${ROOT}/environment/starter/." "${WORK}/workspace/"
    sed -i "s/set clk_period 0.65/set clk_period 2.00/" "${WORK}/workspace/constraints/constraint.sdc" || true
    cp -f "${ROOT}/steps/step-3-route-signoff/tests/test.sh" "${WORK}/tests/test.sh"
    chmod +x "${WORK}/tests/test.sh"
    run_in "export TESTS_DIR=/tests; bash /tests/test.sh" || true
    echo -n "tamper_sdc reward="
    cat "${WORK}/logs/verifier/reward.txt"

    # 2) Delete cipher rounds (force the round counter to finish immediately)
    echo "===== anti-cheat: delete rounds ====="
    rm -rf "${WORK}/workspace"
    mkdir -p "${WORK}/workspace"
    cp -a "${ROOT}/environment/starter/." "${WORK}/workspace/"
    python3 - "$WORK/workspace/rtl/aes_cipher_top.v" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text()
t = t.replace("if(ld)\t\tdcnt <= #1 4'hb;", "if(ld)\t\tdcnt <= #1 4'h1;")
p.write_text(t)
print("patched", p)
PY
    run_in "export TESTS_DIR=/tests; bash /tests/test.sh" || true
    echo -n "delete_rounds reward="
    cat "${WORK}/logs/verifier/reward.txt"

    # 3) Forge 6_report.json without a real signoff database
    echo "===== anti-cheat: forge 6_report.json ====="
    rm -rf "${WORK}/workspace"
    mkdir -p "${WORK}/workspace/results/nangate45/aes/base"
    cp -a "${ROOT}/environment/starter/." "${WORK}/workspace/"
    mkdir -p "${WORK}/workspace/results/nangate45/aes/base"
    cat > "${WORK}/workspace/results/nangate45/aes/base/6_report.json" <<'JSON'
{"wns_setup": 0.25, "tns_setup": 0.0, "wns_hold": 0.10, "drc_violations": 0, "core_area_um2": 1.0, "total_power_w": 1e-6}
JSON
    run_in "export TESTS_DIR=/tests; bash /tests/test.sh" || true
    echo -n "forge_report reward="
    cat "${WORK}/logs/verifier/reward.txt"
    ;;
  *)
    echo "Usage: $0 {oracle|nop|anti-cheat}" >&2
    exit 2
    ;;
esac

ln -sfn "$WORK" "${JOBROOT}/orfs-ppa-${MODE}-latest"
echo "logs: ${WORK}/logs/verifier/"
