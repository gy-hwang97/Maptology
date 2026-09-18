#!/usr/bin/env bash
# Start Streamlit at the web-server root, or under MAPTOLOGY_BASE_PATH.
set -euo pipefail

BASE_PATH="${MAPTOLOGY_BASE_PATH:-}"
BASE_PATH="${BASE_PATH#/}"
BASE_PATH="${BASE_PATH%/}"

exec streamlit run src/Maptology/main.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.baseUrlPath="${BASE_PATH}"
