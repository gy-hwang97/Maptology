#!/usr/bin/env bash
# Runs the accuracy benchmark, then the single-search speed benchmark.
# Edit the settings below, then run this script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ACCURACY_PREFIX=accuracy-test-all-terms
SPEED_WORKLOADS=500
REPEATS=5
SPEED_PREFIX=speed-test-${SPEED_WORKLOADS}-terms-$REPEATS-repeats

bash "$SCRIPT_DIR/scripts/host-run-accuracy.sh" \
  --output-prefix "$ACCURACY_PREFIX"

MAPTOLOGY_SKIP_IMAGE_BUILD=1 \
  bash "$SCRIPT_DIR/scripts/host-run-speed.sh" \
  --workloads "$SPEED_WORKLOADS" \
  --repeats "$REPEATS" \
  --output-prefix "$SPEED_PREFIX"
