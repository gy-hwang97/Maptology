#!/usr/bin/env bash
# Stop, rebuild, and start the Maptology Streamlit container.
set -euo pipefail

HOST_PORT="${MAPTOLOGY_PORT:-8501}"
BIOPORTAL_APIKEY="${BIOPORTAL_APIKEY:-<YOUR_API_KEY>}"
MAPTOLOGY_DOWNLOAD_ALL="${MAPTOLOGY_DOWNLOAD_ALL:-yes}"

IMAGE_NAME="maptology"
CONTAINER_NAME="maptology"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$BIOPORTAL_APIKEY" == "<YOUR_API_KEY>" ]]; then
  echo "BIOPORTAL_APIKEY is still set to the placeholder <YOUR_API_KEY>."
  echo "Get a free key at https://bioportal.bioontology.org/accounts, then either:"
  echo "  export BIOPORTAL_APIKEY=your-key-here"
  echo "or replace <YOUR_API_KEY> with your key in docker-run.sh, and run this script again."
  exit 1
fi

if [[ "$MAPTOLOGY_DOWNLOAD_ALL" != "yes" && "$MAPTOLOGY_DOWNLOAD_ALL" != "no" ]]; then
  echo "MAPTOLOGY_DOWNLOAD_ALL must be \"yes\" or \"no\" (got: \"$MAPTOLOGY_DOWNLOAD_ALL\")."
  echo "Either:"
  echo "  export MAPTOLOGY_DOWNLOAD_ALL=yes"
  echo "or set MAPTOLOGY_DOWNLOAD_ALL to \"yes\" or \"no\" in docker-run.sh."
  exit 1
fi

cd "$SCRIPT_DIR"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Stopping and removing existing container '$CONTAINER_NAME'..."
  docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
fi

echo "Building image '$IMAGE_NAME'..."
docker build -t "$IMAGE_NAME" .

mkdir -p ontology_cache tfidf_cache

echo "Starting container '$CONTAINER_NAME' on port $HOST_PORT..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -p "${HOST_PORT}:8501" \
  -e "BIOPORTAL_APIKEY=${BIOPORTAL_APIKEY}" \
  -e "MAPTOLOGY_DOWNLOAD_ALL=${MAPTOLOGY_DOWNLOAD_ALL}" \
  -v "${SCRIPT_DIR}/ontology_cache:/app/ontology_cache" \
  -v "${SCRIPT_DIR}/tfidf_cache:/app/tfidf_cache" \
  "$IMAGE_NAME"

echo "Maptology is running at http://localhost:${HOST_PORT}"
