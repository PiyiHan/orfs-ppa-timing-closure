#!/bin/bash
# Harbor separate-verifier entry for step-1-frontend-synth.
# Always writes /logs/verifier/reward.txt and exits 0 so the score is captured.
set +e
set -u

export TESTS_DIR="${TESTS_DIR:-/tests}"
export WORKSPACE="${WORKSPACE:-/workspace}"
export WORKDIR="${WORKDIR:-$WORKSPACE}"
export HARBOR_VERIFIER_LOGDIR="${HARBOR_VERIFIER_LOGDIR:-/logs/verifier}"

# When tests/ is overlaid, helpers.py may live at /tests/helpers.py
# or one directory above the step tests/ (task-level tests/).
HELPER=""
for c in \
    "${TESTS_DIR}/helpers.py" \
    "/tests/helpers.py" \
    "$(cd "$(dirname "$0")/../../../tests" 2>/dev/null && pwd)/helpers.py"
do
  if [ -f "$c" ]; then
    HELPER="$c"
    break
  fi
done

mkdir -p "${HARBOR_VERIFIER_LOGDIR}"
if [ -z "$HELPER" ]; then
  echo "ERROR: helpers.py not found" | tee "${HARBOR_VERIFIER_LOGDIR}/error.txt"
  echo 0.0000 > "${HARBOR_VERIFIER_LOGDIR}/reward.txt"
  exit 0
fi

# Make sure shared golden/scripts are visible even if only step tests/ is mounted.
if [ ! -d /tests/golden ] && [ -d "$(dirname "$HELPER")/golden" ]; then
  export TESTS_DIR="$(dirname "$HELPER")"
fi

python3 "$HELPER" step1
rc=$?
if [ ! -f "${HARBOR_VERIFIER_LOGDIR}/reward.txt" ]; then
  echo 0.0000 > "${HARBOR_VERIFIER_LOGDIR}/reward.txt"
fi
exit 0
