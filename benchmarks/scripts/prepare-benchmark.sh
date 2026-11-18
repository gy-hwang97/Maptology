# Sourced inside the benchmark container after cd to /app/benchmarks.
# Downloads and index builds stay outside search timing.

inputs_ready() {
  python -B - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "code")
import benchmark_common as common

inputs = Path("inputs")
for dataset in common.DATASETS:
    path = inputs / ("eval-" + dataset + ".tsv")
    if not path.is_file() or path.stat().st_size == 0:
        sys.exit(1)
PY
}

assets_ready() {
  python -B - <<'PY'
import hashlib
import json
import sys
from pathlib import Path

folder = Path("assets")
manifest = folder / "asset-manifest.json"
if not manifest.is_file():
    sys.exit(1)
report = json.loads(manifest.read_text(encoding="utf-8"))
for name, digest in report["files"].items():
    path = folder / name
    if not path.is_file():
        sys.exit(1)
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            hasher.update(block)
    if hasher.hexdigest() != digest:
        sys.exit(1)
PY
}

ensure_prepared() {
  # Download / index / cache work happens here only. It is never inside the
  # search timer in run_speed.py / single_speed_worker.py.
  local need_inputs=0
  local need_assets=0
  if inputs_ready; then
    echo "Inputs already prepared (not timed)."
  else
    need_inputs=1
  fi
  if assets_ready; then
    echo "Assets already prepared (not timed)."
  else
    need_assets=1
  fi
  if [[ "$need_inputs" -eq 1 ]]; then
    echo "Preparing fixed inputs (outside benchmark timer)..."
    python -B code/build_inputs.py
  fi
  if [[ "$need_assets" -eq 1 ]]; then
    echo "Preparing EFO indexes and text2term cache (outside benchmark timer)..."
    python -B code/prepare_assets.py
  fi
}
