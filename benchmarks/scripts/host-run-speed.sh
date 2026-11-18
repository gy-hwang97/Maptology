#!/usr/bin/env bash

# Build and run the single-search speed benchmark in Docker.
#
# This is the script you run on the host for speed only. Inside the container
# it calls container-run-speed.sh. The Docker image is rebuilt on every run
# unless MAPTOLOGY_SKIP_IMAGE_BUILD=1.
#
# Examples:
#   bash benchmarks/run-benchmarks_Nix.sh
#   bash benchmarks/scripts/host-run-speed.sh --estimate --workloads 500
#   bash benchmarks/scripts/host-run-speed.sh --workloads 500 --output-prefix my-run
#   bash benchmarks/scripts/host-run-speed.sh --workloads full --output-prefix my-full-run
#
# Host directories inputs/, sources/, assets/, runs/, results/, and raw/ are
# bind-mounted so downloads and timed outputs persist outside the container.
set -euo pipefail

IMAGE_NAME="${MAPTOLOGY_BENCHMARK_IMAGE:-maptology-benchmark-single-search}"
CONTAINER_NAME="${MAPTOLOGY_BENCHMARK_CONTAINER:-maptology-benchmark-single-search}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAPER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PAPER_DIR/.." && pwd)"

WORKLOADS=""
HAS_OUTPUT_PREFIX=0
OUTPUT_PREFIX=""
ESTIMATE=0
DOCKER_ARGS=()

usage() {
  cat <<'EOF'
Usage: host-run-speed.sh [options]

  -h, --help              Show this help

Speed run:
  --estimate              Print a time estimate only (no searches)
  --workloads N|full
                          Default: 500.
                          N      = that many distinct strings per dataset
                          full   = every evaluation row
  --output-prefix NAME    Required unless --estimate.
                          Exports results/NAME.tsv, results/NAME.pdf,
                          results/NAME-rounds.tsv, results/NAME-setup.tsv,
                          and raw/NAME.tsv.gz
  --repeats N             Number of completed rounds (default: 1)
  --resume RUN_FOLDER     Resume an unfinished runs/... folder

The Docker image is rebuilt on every run. Inputs and assets are prepared
automatically when missing or out of date. Preparation and per-method
index/mapper loading are outside search timing (setup times go to
setup-times.tsv; search times go to speed-*.tsv).
If results/NAME.tsv and results/NAME.pdf already exist, the benchmark is not
executed. If only the table exists, the chart is created from that table.

Or edit the prefixes in run-benchmarks_Nix.sh to run accuracy and then speed.

Examples:
  bash benchmarks/scripts/host-run-speed.sh --estimate --workloads 500
  bash benchmarks/scripts/host-run-speed.sh --workloads 500 --output-prefix speed-500
  bash benchmarks/scripts/host-run-speed.sh --workloads full --output-prefix speed-full
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --estimate)
      ESTIMATE=1
      DOCKER_ARGS+=(--estimate)
      shift
      ;;
    --workloads)
      value="${2:?--workloads requires a positive integer or full}"
      if [[ "$value" != "full" && ! "$value" =~ ^[1-9][0-9]*$ ]]; then
        echo "--workloads must be a positive integer or full (got: $value)" >&2
        usage >&2
        exit 2
      fi
      DOCKER_ARGS+=(--workloads "$value")
      WORKLOADS="$value"
      shift 2
      ;;
    --output-prefix)
      value="${2:?--output-prefix requires a name}"
      if [[ -z "$value" || "$value" == *"/"* || "$value" == *"*"* ]]; then
        echo "--output-prefix must be a non-empty file basename (no / or *)" >&2
        usage >&2
        exit 2
      fi
      DOCKER_ARGS+=(--output-prefix "$value")
      OUTPUT_PREFIX="$value"
      HAS_OUTPUT_PREFIX=1
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      DOCKER_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$WORKLOADS" ]]; then
  WORKLOADS=500
  DOCKER_ARGS+=(--workloads 500)
fi

if [[ "$ESTIMATE" -eq 0 && "$HAS_OUTPUT_PREFIX" -eq 0 ]]; then
  echo "--output-prefix is required unless --estimate is set." >&2
  usage >&2
  exit 2
fi

if [[ "$ESTIMATE" -eq 0 ]]; then
  RESULTS_TSV="$PAPER_DIR/results/${OUTPUT_PREFIX}.tsv"
  RESULTS_PDF="$PAPER_DIR/results/${OUTPUT_PREFIX}.pdf"

  write_speed_graph() {
    echo "Creating speed graph..."
    (
      cd "$PAPER_DIR"
      Rscript code/create_figures.R --speed \
        "results/${OUTPUT_PREFIX}.tsv" \
        "results/${OUTPUT_PREFIX}.pdf"
    )
  }

  if [[ -f "$RESULTS_TSV" && -f "$RESULTS_PDF" ]]; then
    echo "Speed benchmark will not be executed because the output files already exist:"
    echo "  $RESULTS_TSV"
    echo "  $RESULTS_PDF"
    exit 0
  fi

  if [[ -f "$RESULTS_TSV" ]]; then
    echo "Speed benchmark will not be executed because the results already exist:"
    echo "  $RESULTS_TSV"
    write_speed_graph
    exit 0
  fi
fi

source "$SCRIPT_DIR/host-docker.sh"
host_build_image
if [[ "$WORKLOADS" == "full" ]]; then
  echo "A full speed run can take many hours because text2term searches one string at a time."
fi
host_run_container ./scripts/container-run-speed.sh "${DOCKER_ARGS[@]+"${DOCKER_ARGS[@]}"}"

if [[ "$ESTIMATE" -eq 0 ]]; then
  write_speed_graph
fi
