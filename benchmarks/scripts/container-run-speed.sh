#!/usr/bin/env bash
# Runs inside the benchmark container. Ensures inputs/assets are ready, then
# runs the single-search speed benchmark and copies summary tables into
# results/ using the output prefix.
set -euo pipefail

cd /app/benchmarks

export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export PYTHONUTF8=1
unset MAPTOLOGY_BENCHMARK_ASSETS || true

ESTIMATE=0
WORKLOADS="500"
OUTPUT_PREFIX=""
REPEATS=1
EXTRA=()

usage() {
  cat <<'EOF'
Usage: container-run-speed.sh [options]

Options:
  -h, --help              Show this help
  --estimate              Print time estimate only
  --workloads N|full
                          Default: 500.
                          N      = that many distinct strings per dataset
                          full   = every evaluation row
  --output-prefix NAME    Required unless --estimate.
                          Writes results/NAME.tsv, results/NAME-rounds.tsv,
                          results/NAME-setup.tsv, and raw/NAME.tsv.gz
  --repeats N             Default: 1
  --resume RUN_FOLDER     Resume an existing runs/... folder

Inputs and assets are prepared automatically when missing or out of date.
That preparation, and each method's index/mapper load, are outside search timing.
EOF
}

source ./scripts/prepare-benchmark.sh

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workloads)
      WORKLOADS="${2:?--workloads requires a positive integer or full}"
      if [[ "$WORKLOADS" != "full" && ! "$WORKLOADS" =~ ^[1-9][0-9]*$ ]]; then
        echo "--workloads must be a positive integer or full (got: $WORKLOADS)" >&2
        exit 2
      fi
      shift 2
      ;;
    --output-prefix)
      OUTPUT_PREFIX="${2:?--output-prefix requires a name}"
      if [[ -z "$OUTPUT_PREFIX" || "$OUTPUT_PREFIX" == *"/"* || "$OUTPUT_PREFIX" == *"*"* ]]; then
        echo "--output-prefix must be a non-empty file basename (no / or *)" >&2
        usage >&2
        exit 2
      fi
      shift 2
      ;;
    --repeats)
      REPEATS="${2:?--repeats requires a positive integer}"
      shift 2
      ;;
    --estimate)
      ESTIMATE=1
      EXTRA+=("$1")
      shift
      ;;
    --resume)
      EXTRA+=(--resume "${2:?--resume requires a run folder path}")
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

if [[ "$ESTIMATE" -eq 0 && -z "$OUTPUT_PREFIX" ]]; then
  echo "--output-prefix is required unless --estimate is set." >&2
  usage >&2
  exit 2
fi

mkdir -p inputs sources assets runs results raw

# Estimates do not need downloads or indexes.
if [[ "$ESTIMATE" -eq 0 ]]; then
  ensure_prepared
fi

echo "Starting timed single-search benchmark (workloads=$WORKLOADS repeats=$REPEATS)..."
echo "Note: per-method index/mapper load is recorded in setup-times.tsv, not in search times."
BEFORE_RUNS="$(find runs -maxdepth 1 -type d -name 'speed-single-cold-*' 2>/dev/null | sort || true)"

python -B code/run_speed.py --workloads "$WORKLOADS" --repeats "$REPEATS" "${EXTRA[@]+"${EXTRA[@]}"}"

if [[ "$ESTIMATE" -eq 1 ]]; then
  exit 0
fi

AFTER_RUNS="$(find runs -maxdepth 1 -type d -name 'speed-single-cold-*' 2>/dev/null | sort || true)"
NEW_RUN=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if ! grep -Fxq "$path" <<<"$BEFORE_RUNS"; then
    NEW_RUN="$path"
  fi
done <<<"$AFTER_RUNS"

# Resume / re-complete: prefer the --resume target if present in EXTRA.
for ((i = 0; i < ${#EXTRA[@]}; i++)); do
  if [[ "${EXTRA[$i]}" == "--resume" ]]; then
    NEW_RUN="${EXTRA[$((i + 1))]}"
  fi
done

if [[ -z "$NEW_RUN" ]]; then
  NEW_RUN="$(find runs -maxdepth 1 -type d -name 'speed-single-cold-*' 2>/dev/null | sort | tail -n 1 || true)"
fi

if [[ -n "$NEW_RUN" && -d "$NEW_RUN" ]]; then
  for src in speed-results.tsv speed-rounds.tsv setup-times.tsv; do
    if [[ -f "$NEW_RUN/$src" ]]; then
      case "$src" in
        speed-results.tsv) dest="results/${OUTPUT_PREFIX}.tsv" ;;
        speed-rounds.tsv) dest="results/${OUTPUT_PREFIX}-rounds.tsv" ;;
        setup-times.tsv) dest="results/${OUTPUT_PREFIX}-setup.tsv" ;;
      esac
      cp "$NEW_RUN/$src" "$dest"
      echo "Copied $src -> $dest"
    fi
  done
  if [[ -f "$NEW_RUN/speed-timings.tsv" ]]; then
    gzip -c "$NEW_RUN/speed-timings.tsv" > "raw/${OUTPUT_PREFIX}.tsv.gz"
    echo "Copied compressed timings -> raw/${OUTPUT_PREFIX}.tsv.gz"
  fi
  echo "Run folder: $NEW_RUN"
else
  echo "Warning: could not locate a run folder to export." >&2
fi
