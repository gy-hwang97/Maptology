# Paper accuracy and single-search speed benchmarks (not the Maptology Streamlit app image).
#
# The repository-root .dockerignore excludes benchmarks/, so prefer:
#   bash benchmarks/run-benchmarks_Nix.sh
# which rebuilds the image from a staged context (benchmarks + build/).
#
# Manual equivalent (from a staged context whose layout matches the COPY paths):
#   docker build -f Dockerfile -t maptology-benchmark-single-search .

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONUTF8=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Compilers help when wheels are unavailable (e.g. sparse-dot-topn).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libxml2 \
    && rm -rf /var/lib/apt/lists/*

COPY benchmarks/requirements-docker.txt /tmp/requirements-docker.txt
RUN pip install --no-cache-dir -r /tmp/requirements-docker.txt \
    && pip install --no-cache-dir --no-deps text2term==4.5.0 \
    && rm /tmp/requirements-docker.txt

# prepare_assets.py imports build/build_all_caches.py via ROOT.parent / "build"
COPY build/ /app/build/
COPY benchmarks/ /app/benchmarks/

WORKDIR /app/benchmarks

RUN chmod +x scripts/container-run-speed.sh scripts/container-run-accuracy.sh \
    && mkdir -p inputs sources assets runs results raw

ENTRYPOINT ["./scripts/container-run-speed.sh"]
CMD []
