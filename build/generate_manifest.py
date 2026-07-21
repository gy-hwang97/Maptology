"""Generate the Maptology distribution manifest + per-ontology cache zips.

Reads the ontology catalog (ontology_list.tsv), the human-reviewed distribution
policy, and BioPortal version data, then writes dist/manifest.json plus one
content-addressed zip per server-deliverable ontology. Run offline on the server
after caches are built.

Key properties (from the reviewed design):
  - Iterates the full catalog, so bioportal_user / blocked ontologies still
    appear (listed with download_url: null) instead of silently vanishing.
  - Each served zip contains the 3 cache files plus a metadata.json (attribution
    travels with the data). The zip is content-deterministic, so its sha256
    fingerprints the content and names the file: <ACRONYM>-<build_id>.zip.
  - Publishes atomically: new zips are written under new names, the manifest is
    swapped in with os.replace, and zips no longer referenced are garbage
    collected. A reclassified ontology's zip stops being referenced immediately.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from api.config import (  # noqa: E402
    MANIFEST_VERSION,
    CACHE_FORMAT_VERSION,
    CACHE_FILE_SUFFIXES,
    TFIDF_CACHE_DIR,
    ONTOLOGY_LIST_TSV,
    VERSIONS_JSON,
    POLICY_TSV,
    manifest_path,
    cache_zip_dir,
)
from build.cache_archive import (  # noqa: E402
    make_deterministic_zip,
    sha256_of,
    build_id_from_sha256,
)
from build.distribution_policy import load_policy, delivery_mode_for  # noqa: E402


# ------------------------------------------------------------------ readers

def load_catalog(list_tsv):
    """Return the ontology catalog as a sorted list of {acronym, name}."""
    out = []
    if not os.path.exists(list_tsv):
        return out
    seen = set()
    with open(list_tsv, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            acronym = (row.get("abbreviation") or "").strip()
            if not acronym or acronym in seen:
                continue
            seen.add(acronym)
            out.append({"acronym": acronym, "name": (row.get("name") or "").strip()})
    out.sort(key=lambda e: e["acronym"])
    return out


def load_versions(json_path):
    """acronym -> {version, submissionId, ...}, from ontology_versions.json."""
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def read_cache_members(tfidf_dir, acronym):
    """Return [(arcname, bytes)] for the 3 cache files, or None if any is missing."""
    members = []
    for suffix in CACHE_FILE_SUFFIXES:
        path = os.path.join(tfidf_dir, acronym, acronym + suffix)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as fh:
            members.append((acronym + suffix, fh.read()))
    return members


# ------------------------------------------------------------------ building

def _metadata_bytes(record, mode):
    """Deterministic metadata.json for inclusion in a served zip.

    Excludes generated_at and any hash so the zip stays content-deterministic.
    """
    meta = {
        "acronym": record["acronym"],
        "name": record["name"],
        "ontology_version": record["ontology_version"],
        "submission_id": record["submission_id"],
        "delivery_mode": mode,
        "license": record["license"],
        "license_url": record["license_url"],
        "reason": record["reason"],
        "cache_format_version": CACHE_FORMAT_VERSION,
    }
    return json.dumps(meta, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def build_manifest(catalog, versions, policy, tfidf_dir, out_zip_dir, generated_at):
    """Build the manifest dict and write a zip for each served ontology.

    Returns (manifest_dict, referenced_zip_filenames_set).
    """
    os.makedirs(out_zip_dir, exist_ok=True)
    ontologies = []
    referenced = set()
    missing_cache = []
    for entry in catalog:
        acronym = entry["acronym"]
        mode = delivery_mode_for(policy, acronym)
        pol = policy.get(acronym) or {}
        vinfo = versions.get(acronym) or {}
        record = {
            "acronym": acronym,
            "name": entry["name"] or acronym,
            "ontology_version": vinfo.get("version"),
            "submission_id": vinfo.get("submissionId"),
            "delivery_mode": mode,
            "license": pol.get("license", ""),
            "license_url": pol.get("license_url", ""),
            "reason": pol.get("reason", ""),
            "cache_build_id": None,
            "download_url": None,
            "sha256": None,
            "size": None,
            "artifact_status": None,
        }

        members = None
        if mode == "maptology_server":
            members = read_cache_members(tfidf_dir, acronym)

        # Record why (or why not) an artifact is attached, so a green ontology
        # whose cache failed to build is visible rather than silently null.
        if mode != "maptology_server":
            record["artifact_status"] = "not_served"
        elif members is None:
            record["artifact_status"] = "missing_cache"
            missing_cache.append(acronym)
        else:
            record["artifact_status"] = "available"

        if members is not None:
            members.append(("metadata.json", _metadata_bytes(record, mode)))
            building = os.path.join(out_zip_dir, acronym + ".building.zip")
            make_deterministic_zip(members, building)
            digest = sha256_of(building)
            build_id = build_id_from_sha256(digest)
            final_name = acronym + "-" + build_id + ".zip"
            final_path = os.path.join(out_zip_dir, final_name)
            os.replace(building, final_path)
            record["cache_build_id"] = build_id
            record["sha256"] = digest
            record["size"] = os.path.getsize(final_path)
            record["download_url"] = "/v1/cache/" + final_name
            referenced.add(final_name)

        ontologies.append(record)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "cache_format_version": CACHE_FORMAT_VERSION,
        "generated_at": generated_at,
        "ontologies": ontologies,
    }
    return manifest, referenced, missing_cache


# ------------------------------------------------------------------ publishing

def _gc_stale_zips(out_zip_dir, referenced):
    """Remove any file in the zip dir not referenced by the new manifest."""
    if not os.path.isdir(out_zip_dir):
        return
    for name in os.listdir(out_zip_dir):
        if name not in referenced:
            try:
                os.remove(os.path.join(out_zip_dir, name))
            except OSError:
                pass


def _write_manifest_atomic(manifest, manifest_file):
    parent = os.path.dirname(manifest_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = manifest_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, manifest_file)


def generate(list_tsv=None, tfidf_dir=None, versions_json=None,
             policy_tsv=None, out_dir=None):
    """Wire the readers together, publish manifest + zips, return the manifest.

    Any argument left as None falls back to the api.config default path. When
    out_dir is None the config dist dir is used.
    """
    list_tsv = list_tsv or ONTOLOGY_LIST_TSV
    tfidf_dir = tfidf_dir or TFIDF_CACHE_DIR
    versions_json = versions_json or VERSIONS_JSON
    policy_tsv = policy_tsv or POLICY_TSV
    if out_dir is None:
        manifest_file = manifest_path()
        out_zip_dir = cache_zip_dir()
    else:
        manifest_file = os.path.join(out_dir, "manifest.json")
        out_zip_dir = os.path.join(out_dir, "cache")

    catalog = load_catalog(list_tsv)
    versions = load_versions(versions_json)
    policy = load_policy(policy_tsv)
    if not policy:
        print("WARNING: no policy at " + policy_tsv
              + " -> every ontology treated as blocked")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest, referenced, missing_cache = build_manifest(
        catalog, versions, policy, tfidf_dir, out_zip_dir, generated_at)

    # Publish: new zips already written; swap the manifest in atomically, then
    # drop zips no longer referenced.
    _write_manifest_atomic(manifest, manifest_file)
    _gc_stale_zips(out_zip_dir, referenced)

    served = sum(1 for o in manifest["ontologies"] if o["download_url"])
    print("Wrote " + manifest_file + " -- " + str(len(manifest["ontologies"]))
          + " ontologies, " + str(served) + " served from server")
    if missing_cache:
        print("WARNING: " + str(len(missing_cache)) + " maptology_server "
              + "ontolog(ies) are missing a complete cache and were NOT "
              + "packaged: " + ", ".join(missing_cache))
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate the Maptology manifest")
    parser.add_argument("--list-tsv", default=None)
    parser.add_argument("--tfidf-dir", default=None)
    parser.add_argument("--versions-json", default=None)
    parser.add_argument("--policy-tsv", default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    generate(args.list_tsv, args.tfidf_dir, args.versions_json,
             args.policy_tsv, args.out_dir)


if __name__ == "__main__":
    main()
