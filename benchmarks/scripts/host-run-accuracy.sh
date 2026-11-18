#!/usr/bin/env bash

# Build and run the accuracy benchmark in Docker.
#
# This is the script you run on the host for accuracy only. Inside the
# container it calls container-run-accuracy.sh. The Docker image is rebuilt
# on every run unless MAPTOLOGY_SKIP_IMAGE_BUILD=1.
#
# Examples:
#   bash benchmarks/scripts/host-run-accuracy.sh --output-prefix accuracy
#   bash benchmarks/scripts/host-run-accuracy.sh --output-prefix accuracy-check --sample 3
#
# Host directories inputs/, sources/, assets/, runs/, results/, and raw/ are
# bind-mounted so downloads and scored outputs persist outside the container.
set -euo pipefail

IMAGE_NAME="${MAPTOLOGY_BENCHMARK_IMAGE:-maptology-benchmark-single-search}"
CONTAINER_NAME="${MAPTOLOGY_BENCHMARK_CONTAINER:-maptology-benchmark-single-search}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAPER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PAPER_DIR/.." && pwd)"

HAS_OUTPUT_PREFIX=0
OUTPUT_PREFIX=""
SAMPLE=""
DOCKER_ARGS=()

usage() {
  cat <<'EOF'
Usage: host-run-accuracy.sh [options]

  -h, --help              Show this help

Accuracy run:
  --output-prefix NAME    Required.
                          Exports results/NAME.tsv (top-1 and top-5 summary),
                          results/NAME.pdf (accuracy bar chart), and
                          raw/NAME.tsv.gz (one row per evaluation row
                          and method)
  --sample N              Score only N rows per dataset (code check)

The Docker image is rebuilt on every run. Inputs and assets are prepared
automatically when missing or out of date. Without --sample, every
evaluation row is scored for all six methods. text2term makes that a long run.
If results/NAME.tsv and results/NAME.pdf already exist, the benchmark is not
executed. If only the table exists, the chart is created from that table.

Or edit the prefixes in run-benchmarks_Nix.sh to run accuracy and then speed.

Examples:
  bash benchmarks/scripts/host-run-accuracy.sh --output-prefix accuracy
  bash benchmarks/scripts/host-run-accuracy.sh --output-prefix accuracy-check --sample 3
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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
    --sample)
      SAMPLE="${2:?--sample requires a positive integer}"
      if [[ ! "$SAMPLE" =~ ^[1-9][0-9]*$ ]]; then
        echo "--sample must be a positive integer (got: $SAMPLE)" >&2
        usage >&2
        exit 2
      fi
      DOCKER_ARGS+=(--sample "$SAMPLE")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$HAS_OUTPUT_PREFIX" -eq 0 ]]; then
  echo "--output-prefix is required." >&2
  usage >&2
  exit 2
fi

RESULTS_TSV="$PAPER_DIR/results/${OUTPUT_PREFIX}.tsv"
RESULTS_PDF="$PAPER_DIR/results/${OUTPUT_PREFIX}.pdf"

source "$SCRIPT_DIR/host-docker.sh"

write_accuracy_graph() {
  echo "Creating accuracy graph..."
  host_build_image
  host_run_container Rscript \
    code/create_figures.R \
    "results/${OUTPUT_PREFIX}.tsv" \
    "results/${OUTPUT_PREFIX}.pdf"
}

if [[ -f "$RESULTS_TSV" && -f "$RESULTS_PDF" ]]; then
  echo "Accuracy benchmark will not be executed because the output files already exist:"
  echo "  $RESULTS_TSV"
  echo "  $RESULTS_PDF"
  exit 0
fi

if [[ -f "$RESULTS_TSV" ]]; then
  echo "Accuracy benchmark will not be executed because the results already exist:"
  echo "  $RESULTS_TSV"
  write_accuracy_graph
  exit 0
fi

host_build_image
if [[ -n "$SAMPLE" ]]; then
  echo "Accuracy code check: $SAMPLE rows per dataset."
else
  echo "Accuracy scores every evaluation row for six methods (text2term is the slow part)."
fi
host_run_container ./scripts/container-run-accuracy.sh "${DOCKER_ARGS[@]+"${DOCKER_ARGS[@]}"}"
