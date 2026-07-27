"""Maptology serving API (read-only).

Serves the pre-generated manifest and per-ontology cache zips produced by
build/generate_manifest.py. Needs no BioPortal key — the key lives only in the
upstream build pipeline.

The /v1/cache endpoint authorizes a download by **manifest membership**, not by
file existence: a zip is served only if the current manifest references it. So
the moment an ontology is reclassified away from maptology_server, the next
manifest stops referencing its zip and the download 404s — even if a stale zip
file is still on disk.
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from api.config import (
    MANIFEST_VERSION,
    CACHE_FORMAT_VERSION,
    ZIP_FILENAME_RE,
    manifest_path,
    cache_zip_dir,
)

app = FastAPI(title="Maptology API", version="1")


def _load_manifest():
    path = manifest_path()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _served_filenames(manifest):
    """Basenames the manifest both references AND marks maptology_server.

    Requiring delivery_mode explicitly (not just the presence of a download_url)
    is defence in depth: a corrupted or hand-edited manifest that put a url on a
    non-green ontology still cannot be served.
    """
    names = set()
    for ontology in manifest.get("ontologies", []):
        if ontology.get("delivery_mode") != "maptology_server":
            continue
        url = ontology.get("download_url")
        if url:
            names.add(url.rsplit("/", 1)[-1])
    return names


@app.get("/")
def index():
    """Anyone opening the bare address should be told where to go, rather than
    getting a bare 404 that looks like the server is broken."""
    return {
        "service": "Maptology API",
        "manifest_version": MANIFEST_VERSION,
        "cache_format_version": CACHE_FORMAT_VERSION,
        "endpoints": {
            "interactive docs": "/docs",
            "health": "/v1/health",
            "catalogue": "/v1/manifest",
            "one cache": "/v1/cache/{acronym}-{cache_build_id}.zip",
        },
        "note": "download URLs come from /v1/manifest; only ontologies whose "
                "licence permits redistribution are served here",
    }


@app.get("/v1/health")
def health():
    return {
        "status": "ok",
        "manifest_version": MANIFEST_VERSION,
        "cache_format_version": CACHE_FORMAT_VERSION,
    }


@app.get("/v1/manifest")
def manifest():
    data = _load_manifest()
    if data is None:
        raise HTTPException(status_code=503, detail="manifest not generated yet")
    return JSONResponse(content=data)


@app.get("/v1/cache/{filename}")
def cache_zip(filename: str):
    # Defence in depth: reject anything that isn't a bare zip filename.
    if not ZIP_FILENAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="not found")
    # Authorization: only serve files the current manifest references.
    data = _load_manifest()
    if data is None or filename not in _served_filenames(data):
        raise HTTPException(status_code=404, detail="not available for download")
    zip_path = os.path.join(cache_zip_dir(), filename)
    if not os.path.isfile(zip_path):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(zip_path, media_type="application/zip", filename=filename)
