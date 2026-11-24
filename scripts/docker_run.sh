#!/bin/bash
# Docker equivalent of scripts/cse_run.sh for hosts with a Docker daemon.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-oracle}"
IMAGE="${HARBOR_EDA_IMAGE:-orfs-ppa-timing-closure:26Q4-554-g82ac25be5-eda}"
STAMP="$(date +%Y%m%d-%H%M%S)"
JOBROOT="${HARBOR_JOBS_DIR:-$ROOT/../orfs-cal/jobs}"
WORK="${JOBROOT}/orfs-ppa-${MODE}-${STAMP}"
mkdir -p "${WORK}/workspace" "${WORK}/logs/verifier" "${WORK}/logs/agent" \
         "${WORK}/tests" "${WORK}/solution"
cp -a "${ROOT}/environment/starter/." "${WORK}/workspace/"
cp -a "${ROOT}/tests/." "${WORK}/tests/"
mkdir -p "${WORK}/workspace/results" "${WORK}/workspace/out"

run_in() {
  docker run --rm --network=none --cpus="${NUM_CORES:-4}" --memory=10g \
    -e NUM_CORES="${NUM_CORES:-4}" \
    -e TMPDIR=/tmp -e TMP=/tmp -e TEMP=/tmp \
    -e TESTS_DIR=/tests -e WORKSPACE=/workspace -e WORKDIR=/workspace \
    -e HARBOR_VERIFIER_LOGDIR=/logs/verifier \
    -v "${WORK}/workspace:/workspace" \
    -v "${WORK}/logs:/logs" \
    -v "${WORK}/tests:/tests" \
    -v "${WORK}/solution:/solution" \
    -w /workspace \
    "$IMAGE" bash -lc "$1"
}

echo "Image: $IMAGE"
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
      run_in "bash /tests/test.sh"
      echo "----- reward after ${step} -----"
      cat "${WORK}/logs/verifier/reward.txt"
    done
    ;;
  nop)
    cp -f "${ROOT}/steps/step-1-frontend-synth/tests/test.sh" "${WORK}/tests/test.sh"
    chmod +x "${WORK}/tests/test.sh"
    echo "===== nop (step 1, no agent actions) ====="
    run_in "bash /tests/test.sh"
    cat "${WORK}/logs/verifier/reward.txt"
    ;;
  anti-cheat)
    echo "===== anti-cheat: tamper SDC ====="
    sed -i "s/set clk_period 0.84/set clk_period 2.00/" "${WORK}/workspace/constraints/constraint.sdc"
    cp -f "${ROOT}/steps/step-3-route-signoff/tests/test.sh" "${WORK}/tests/test.sh"
    chmod +x "${WORK}/tests/test.sh"
    run_in "bash /tests/test.sh" || true
    echo -n "tamper_sdc reward="; cat "${WORK}/logs/verifier/reward.txt"

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
    run_in "bash /tests/test.sh" || true
    echo -n "delete_rounds reward="; cat "${WORK}/logs/verifier/reward.txt"

    echo "===== anti-cheat: forge 6_report.json ====="
    rm -rf "${WORK}/workspace"
    mkdir -p "${WORK}/workspace/results/nangate45/aes/base"
    cp -a "${ROOT}/environment/starter/." "${WORK}/workspace/"
    mkdir -p "${WORK}/workspace/results/nangate45/aes/base"
    printf '%s\n' '{"wns_setup": 0.25, "tns_setup": 0.0, "wns_hold": 0.10, "drc_violations": 0, "core_area_um2": 1.0, "total_power_w": 1e-6}' \
      > "${WORK}/workspace/results/nangate45/aes/base/6_report.json"
    run_in "bash /tests/test.sh" || true
    echo -n "forge_report reward="; cat "${WORK}/logs/verifier/reward.txt"
    ;;
  *)
    echo "Usage: $0 {oracle|nop|anti-cheat}" >&2
    exit 2
    ;;
esac

mkdir -p "$JOBROOT"
ln -sfn "$WORK" "${JOBROOT}/orfs-ppa-${MODE}-latest"
echo "logs: ${WORK}/logs/verifier/"
