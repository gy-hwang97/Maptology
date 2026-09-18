#!/usr/bin/env bash
# Stop the Maptology Streamlit container if it is running.
set -euo pipefail

CONTAINER_NAME="maptology"

if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Container '$CONTAINER_NAME' is not present."
  exit 0
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Stopping container '$CONTAINER_NAME'..."
  docker stop "$CONTAINER_NAME"
  echo "Container '$CONTAINER_NAME' stopped."
else
  echo "Container '$CONTAINER_NAME' is already stopped."
fi
