# Build and run notes (not part of the frozen README wording)

This file records how to build the complete image, convert it for CSE
Singularity, and reproduce the Harbor oracle / nop / anti-cheat checks.
The task README.md is the exam document; only measured numbers in section 6
are filled in after calibration.

## Image

Pinned base: `openroad/orfs:26Q4-554-g82ac25be5`

- Index digest: `sha256:0c364e5fb49913cd8432e3b620f1e40958d913bc8d6be045147deda91e803832`
- linux/amd64 manifest: `sha256:b59431453d328d6fbf36669e1908b15634c11da51970cc2218a702783dcd6174`

The Dockerfile layers Icarus Verilog, Verilator, Z3, Python and (best-effort)
EQY on top of that pin, then marks ORFS `tools/`, `flow/platforms/` and
`flow/scripts/` root:root and `a-w`. No host bind of oss-cad-suite is required.

Verified in the complete image:

- Yosys 0.68+post
- Icarus Verilog 12.0
- Verilator 5.032
- Z3 4.13.3
- Python 3.14.4

```bash
# On a linux/amd64 Docker host (or Docker Desktop with --platform linux/amd64):
cd environment
docker build -t orfs-ppa-timing-closure:26Q4-554-g82ac25be5-eda .
docker save orfs-ppa-timing-closure:26Q4-554-g82ac25be5-eda \
  -o orfs-ppa-timing-closure-26Q4-554-g82ac25be5-eda.tar
```

On CUHK CSE (no Docker daemon, no fakeroot subuid). Keep the tarball and SIF
on the research disk, never in the `/data/d0` home quota:

```bash
source ~/harbor_eda/env.sh
singularity build \
  "$HARBOR_EDA_ROOT/images/orfs-ppa-timing-closure-26Q4-554-g82ac25be5-eda.sif" \
  docker-archive://path/to/orfs-ppa-timing-closure-26Q4-554-g82ac25be5-eda.tar
```

## Official Harbor (machine with a Docker daemon)

```bash
harbor run --path . --agent oracle
harbor run --path . --agent nop
```

`task.toml` declares `network_mode = "no-network"`. Allocate about 8 vCPU / 16 GB RAM.

## CSE Singularity wrapper

`scripts/cse_run.sh` honors the Harbor reward contract
(`/logs/verifier/reward.txt`, `/logs/verifier/reward.json`) when official
`harbor run -e singularity` cannot be used:

```bash
source ~/harbor_eda/env.sh
./scripts/cse_run.sh oracle          # three-step oracle
./scripts/cse_run.sh nop             # no-op agent
./scripts/cse_run.sh anti-cheat      # three cheat cases, expect 0.0000
```

Calibration logs should be kept under a jobs directory on the research disk
(gitignored, not committed).
