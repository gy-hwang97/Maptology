#!/usr/bin/env bash
# Runs inside the benchmark container. Ensures inputs/assets are ready, then
# scores suggestions against the correct terms and copies the tables using
# the output prefix.
set -euo pipefail

cd /app/benchmarks

export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export PYTHONUTF8=1
unset MAPTOLOGY_BENCHMARK_ASSETS || true

OUTPUT_PREFIX=""
SAMPLE=""

usage() {
  cat <<'EOF'
Usage: container-run-accuracy.sh [options]

Options:
  -h, --help              Show this help
  --output-prefix NAME    Required.
                          Writes results/NAME.tsv (top-1 and top-5 summary),
                          results/NAME.pdf, and raw/NAME.tsv.gz (one row per
                          evaluation row and method)
  --sample N              Score only N rows per dataset (code check)

Inputs and assets are prepared automatically when missing or out of date.
Without --sample, every evaluation row is scored for all six methods.
EOF
}

source ./scripts/prepare-benchmark.sh

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-prefix)
      OUTPUT_PREFIX="${2:?--output-prefix requires a name}"
      if [[ -z "$OUTPUT_PREFIX" || "$OUTPUT_PREFIX" == *"/"* || "$OUTPUT_PREFIX" == *"*"* ]]; then
        echo "--output-prefix must be a non-empty file basename (no / or *)" >&2
        usage >&2
        exit 2
      fi
      shift 2
      ;;
    --sample)
      SAMPLE="${2:?--sample requires a positive integer}"
      if [[ ! "$SAMPLE" =~ ^[1-9][0-9]*$ ]]; then
        echo "--sample must be a positive integer (got: $SAMPLE)" >&2
        usage >&2
        exit 2
      fi
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

if [[ -z "$OUTPUT_PREFIX" ]]; then
  echo "--output-prefix is required." >&2
  usage >&2
  exit 2
fi

mkdir -p inputs sources assets runs results raw
ensure_prepared

if [[ -n "$SAMPLE" ]]; then
  echo "Starting accuracy benchmark (sample=$SAMPLE rows per dataset)..."
else
  echo "Starting accuracy benchmark (every evaluation row, six methods)..."
fi

BEFORE_RUNS="$(find runs -maxdepth 1 -type d -name 'accuracy-*' 2>/dev/null | sort || true)"

if [[ -n "$SAMPLE" ]]; then
  python -B code/run_accuracy.py --sample "$SAMPLE"
else
  python -B code/run_accuracy.py
fi

AFTER_RUNS="$(find runs -maxdepth 1 -type d -name 'accuracy-*' 2>/dev/null | sort || true)"
NEW_RUN=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if ! grep -Fxq "$path" <<<"$BEFORE_RUNS"; then
    NEW_RUN="$path"
  fi
done <<<"$AFTER_RUNS"

if [[ -z "$NEW_RUN" ]]; then
  NEW_RUN="$(find runs -maxdepth 1 -type d -name 'accuracy-*' 2>/dev/null | sort | tail -n 1 || true)"
fi

if [[ -n "$NEW_RUN" && -d "$NEW_RUN" ]]; then
  if [[ -f "$NEW_RUN/accuracy-results.tsv" ]]; then
    cp "$NEW_RUN/accuracy-results.tsv" "results/${OUTPUT_PREFIX}.tsv"
    echo "Copied accuracy-results.tsv -> results/${OUTPUT_PREFIX}.tsv"
  fi
  if [[ -f "$NEW_RUN/accuracy-per-row.tsv" ]]; then
    gzip -c "$NEW_RUN/accuracy-per-row.tsv" > "raw/${OUTPUT_PREFIX}.tsv.gz"
    echo "Copied compressed per-row scores -> raw/${OUTPUT_PREFIX}.tsv.gz"
  fi
  echo "Run folder: $NEW_RUN"
else
  echo "Warning: could not locate a run folder to export." >&2
fi

if [[ -f "results/${OUTPUT_PREFIX}.tsv" ]]; then
  echo "Creating accuracy graph..."
  Rscript code/create_figures.R \
    "results/${OUTPUT_PREFIX}.tsv" \
    "results/${OUTPUT_PREFIX}.pdf"
fi
