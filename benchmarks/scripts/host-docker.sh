# Sourced by the host benchmark scripts.
# Caller sets PAPER_DIR, REPO_ROOT, IMAGE_NAME, and CONTAINER_NAME.

host_build_image() {
  if [[ "${MAPTOLOGY_SKIP_IMAGE_BUILD:-0}" == "1" ]]; then
    local runtime
    runtime="$(docker image inspect --format '{{ index .Config.Labels "maptology.graph_runtime" }}' "$IMAGE_NAME" 2>/dev/null || true)"
    if [[ "$runtime" == "r-tidyverse" ]]; then
      echo "Reusing image '$IMAGE_NAME' (already built in this run)."
      return 0
    fi
    echo "Rebuilding image '$IMAGE_NAME' so the charts can be created inside the container."
  fi

  # Root .dockerignore excludes benchmarks/, so stage a small context that
  # still has the path layout the Dockerfile expects (/benchmarks, /build).
  echo "Staging build context for '$IMAGE_NAME'..."
  local stage
  stage="$(mktemp -d "${TMPDIR:-/tmp}/maptology-bench-XXXXXX")"
  cleanup_stage() { rm -rf "$stage"; }
  trap cleanup_stage EXIT

  mkdir -p "$stage/benchmarks" "$stage/build"
  rsync -a \
    --exclude 'runs/' \
    --exclude 'sources/' \
    --exclude 'assets/' \
    --exclude 'inputs/' \
    --exclude '__pycache__/' \
    --exclude '.DS_Store' \
    --exclude '*.pyc' \
    --exclude 'raw/*.tsv.gz' \
    "$PAPER_DIR/" "$stage/benchmarks/"
  cp "$REPO_ROOT/build/build_all_caches.py" "$stage/build/"

  echo "Building image '$IMAGE_NAME'..."
  docker build \
    -f "$stage/benchmarks/Dockerfile" \
    -t "$IMAGE_NAME" \
    "$stage"

  cleanup_stage
  trap - EXIT
}

host_run_container() {
  local entrypoint="$1"
  shift

  mkdir -p \
    "$PAPER_DIR/inputs" \
    "$PAPER_DIR/sources" \
    "$PAPER_DIR/assets" \
    "$PAPER_DIR/runs" \
    "$PAPER_DIR/results" \
    "$PAPER_DIR/raw"

  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "Removing existing container '$CONTAINER_NAME'..."
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi

  echo "Starting container '$CONTAINER_NAME'..."
  echo "Persistent host dirs: inputs sources assets runs results raw"

  # Code and scripts are mounted from the host so a skipped image rebuild
  # still runs the current benchmark files.
  docker run --name "$CONTAINER_NAME" -it --rm \
    --entrypoint "$entrypoint" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONHASHSEED=0 \
    -e PYTHONUTF8=1 \
    -v "$PAPER_DIR/code:/app/benchmarks/code:ro" \
    -v "$PAPER_DIR/scripts:/app/benchmarks/scripts:ro" \
    -v "$PAPER_DIR/inputs:/app/benchmarks/inputs" \
    -v "$PAPER_DIR/sources:/app/benchmarks/sources" \
    -v "$PAPER_DIR/assets:/app/benchmarks/assets" \
    -v "$PAPER_DIR/runs:/app/benchmarks/runs" \
    -v "$PAPER_DIR/results:/app/benchmarks/results" \
    -v "$PAPER_DIR/raw:/app/benchmarks/raw" \
    "$IMAGE_NAME" \
    "$@"
}
