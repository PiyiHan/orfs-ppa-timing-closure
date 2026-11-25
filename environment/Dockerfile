# Complete Harbor environment for orfs-ppa-timing-closure.
# Pin: official OpenROAD-flow-scripts image (linux/amd64) plus simulation /
# formal extras. Do not use openroad/orfs:latest.
#
# Base tag:     openroad/orfs:26Q4-554-g82ac25be5
# Index digest: sha256:0c364e5fb49913cd8432e3b620f1e40958d913bc8d6be045147deda91e803832
# amd64 digest: sha256:b59431453d328d6fbf36669e1908b15634c11da51970cc2218a702783dcd6174
#
# Build (on an amd64 Docker host, or with --platform linux/amd64):
#   docker build -t orfs-ppa-timing-closure:26Q4-554-g82ac25be5-eda .

FROM openroad/orfs:26Q4-554-g82ac25be5@sha256:b59431453d328d6fbf36669e1908b15634c11da51970cc2218a702783dcd6174

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Hong_Kong \
    ORFS_ROOT=/OpenROAD-flow-scripts \
    FLOW_HOME=/OpenROAD-flow-scripts/flow \
    NUM_CORES=4 \
    PLATFORM=nangate45 \
    DESIGN_CONFIG=/workspace/config.mk \
    WORK_HOME=/workspace

# Official ORFS env.sh prepends these; keep them first so yosys/openroad resolve.
ENV PATH="/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:/OpenROAD-flow-scripts/tools/install/kepler-formal/bin:/opt/orfs-python/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# iverilog / verilator / z3 / jq / python are required at runtime with network off.
# eqy is best-effort (Yosys built-in equiv_* is the LEC fallback).
RUN apt-get update && apt-get install -y --no-install-recommends \
        iverilog \
        verilator \
        python3 \
        python3-pip \
        jq \
        z3 \
        make \
        git \
        diffutils \
        ca-certificates \
        time \
        file \
        gcc \
        g++ \
    && (python3 -m pip install --break-system-packages --no-cache-dir eqy \
        || python3 -m pip install --no-cache-dir eqy \
        || echo "eqy pip install skipped; LEC will use yosys equiv_*") \
    && rm -rf /var/lib/apt/lists/*

# Prevent the agent from rewriting official tools, PDKs, or flow scripts.
RUN chown -R root:root \
      /OpenROAD-flow-scripts/flow/platforms \
      /OpenROAD-flow-scripts/flow/scripts \
      /OpenROAD-flow-scripts/tools \
    && chmod -R a-w \
      /OpenROAD-flow-scripts/flow/platforms \
      /OpenROAD-flow-scripts/flow/scripts \
      /OpenROAD-flow-scripts/tools

WORKDIR /workspace
COPY starter/ /workspace/

RUN mkdir -p /workspace/results /workspace/logs /workspace/reports /workspace/objects \
             /logs/verifier /logs/agent /tests /solution \
    && chmod -R a+rwX /workspace /logs

# Fail the image build if any required tool is missing.
# Avoid `set -o pipefail` with `head` (SIGPIPE / exit 141).
RUN bash -lc 'set -e; \
    command -v yosys && yosys -V | sed -n 1p; \
    command -v openroad && openroad -version; \
    command -v iverilog && command -v vvp && iverilog -V 2>&1 | sed -n 1p; \
    command -v verilator && verilator --version | sed -n 1p; \
    python3 --version; \
    z3 --version; \
    command -v jq; \
    command -v make'

CMD ["/bin/bash"]
