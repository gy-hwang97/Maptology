"""
Check BioPortal for newer ontology versions and record the version of each
locally-built ontology.

Why this exists
---------------
Maptology serves search/definitions from local OWL caches. Those OWL files go
stale as ontologies are updated on BioPortal. This module lets the maintenance
process (run periodically, e.g. monthly on the server):

  1. Look up the LATEST submission of an ontology via the BioPortal API.
  2. Compare it to the version we built locally.
  3. Report which ontologies are out of date (so they can be re-downloaded).

It also records the version of each ontology we currently have, into
  ontology_cache/ontology_versions.json
which the LinkML export reads so every exported mapping records WHICH version
of each ontology it was made against.

BioPortal API (confirmed against https://data.bioontology.org/documentation):
  GET /ontologies/{ACRONYM}/latest_submission?apikey=KEY
      -> JSON with: submissionId, version, released, creationDate,
                    submissionStatus, ...
  GET /ontologies?apikey=KEY
      -> list of ontologies, each with links.latest_submission

The API key is NOT hardcoded. Pass --apikey or set BIOPORTAL_APIKEY.

Usage:
    python version_check.py --record               # store versions for all
                                                   # ontologies in tfidf_cache/
    python version_check.py --record --only NCIT,EFO
    python version_check.py --check                # list ontologies that are
                                                   # newer on BioPortal
"""

import argparse
import json
import os

import requests

API_BASE = "https://data.bioontology.org"
# Resolved against the repo root (this script lives in build/) rather than the
# current working directory, so the script works no matter where it is run from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_REPO_ROOT, "tfidf_cache")
VERSIONS_FILE = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_versions.json")
TIMEOUT = 30


# ============================================================
# BioPortal API
# ============================================================

def get_latest_submission(acronym, api_key):
    """Return version info for the latest submission of one ontology, or None.

    Keys returned: submissionId, version, released, creationDate,
    submissionStatus (whatever BioPortal provides)."""
    url = API_BASE + "/ontologies/" + acronym + "/latest_submission"
    try:
        resp = requests.get(url, params={"apikey": api_key}, timeout=TIMEOUT)
    except requests.RequestException as e:
        print("  [" + acronym + "] request failed: " + str(e))
        return None
    if resp.status_code != 200:
        print("  [" + acronym + "] HTTP " + str(resp.status_code))
        return None
    try:
        data = resp.json()
    except ValueError:
        print("  [" + acronym + "] invalid JSON")
        return None
    return {
        "submissionId": data.get("submissionId"),
        "version": data.get("version"),
        "released": data.get("released"),
        "creationDate": data.get("creationDate"),
        "submissionStatus": data.get("submissionStatus"),
    }


def list_ontologies(api_key):
    """Return the full list of ontologies (acronym + latest_submission link)."""
    url = API_BASE + "/ontologies"
    resp = requests.get(url, params={"apikey": api_key}, timeout=TIMEOUT)
    resp.raise_for_status()
    out = []
    for ont in resp.json():
        out.append({
            "acronym": ont.get("acronym"),
            "name": ont.get("name"),
            "latest_submission": (ont.get("links") or {}).get("latest_submission"),
        })
    return out


# ============================================================
# Local version store (ontology_cache/ontology_versions.json)
# ============================================================

def load_local_versions():
    if not os.path.exists(VERSIONS_FILE):
        return {}
    try:
        with open(VERSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def save_local_versions(versions):
    os.makedirs(os.path.dirname(VERSIONS_FILE), exist_ok=True)
    with open(VERSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(versions, f, indent=2, ensure_ascii=False)


def _cached_acronyms():
    if not os.path.isdir(CACHE_DIR):
        return []
    out = []
    for name in os.listdir(CACHE_DIR):
        if name.endswith(".bak"):
            continue
        if os.path.isdir(os.path.join(CACHE_DIR, name)):
            out.append(name)
    return sorted(out)


# ============================================================
# Operations
# ============================================================

def record_versions(api_key, acronyms=None):
    """Fetch the current BioPortal version of each cached ontology and store it
    locally. This is the version the exported LinkML files will reference."""
    if acronyms is None:
        acronyms = _cached_acronyms()
    versions = load_local_versions()
    print("Recording versions for " + str(len(acronyms)) + " ontologies...")
    for acronym in acronyms:
        info = get_latest_submission(acronym, api_key)
        if info is None:
            continue
        versions[acronym] = info
        print("  " + acronym.ljust(12) + " version=" + str(info.get("version"))
              + " released=" + str(info.get("released"))
              + " submissionId=" + str(info.get("submissionId")))
    save_local_versions(versions)
    print("Saved to " + VERSIONS_FILE)
    return versions


def check_for_updates(api_key, acronyms=None):
    """Compare locally-stored versions to the latest on BioPortal. Returns the
    list of acronyms that are out of date (or never recorded)."""
    if acronyms is None:
        acronyms = _cached_acronyms()
    local = load_local_versions()
    outdated = []
    for acronym in acronyms:
        remote = get_latest_submission(acronym, api_key)
        if remote is None:
            continue
        mine = local.get(acronym)
        if mine is None:
            outdated.append((acronym, "not recorded locally", remote))
            continue
        # A different submissionId (or a newer release date) means an update.
        if remote.get("submissionId") != mine.get("submissionId") or \
           str(remote.get("released")) != str(mine.get("released")):
            outdated.append((acronym, "local=" + str(mine.get("released"))
                             + " remote=" + str(remote.get("released")), remote))
    print("")
    print("=" * 60)
    if outdated:
        print(str(len(outdated)) + " ontology(ies) out of date:")
        for acronym, why, _remote in outdated:
            print("  " + acronym.ljust(12) + " " + why)
    else:
        print("All recorded ontologies are up to date.")
    return outdated


def _get_api_key(arg_key):
    return arg_key or os.environ.get("BIOPORTAL_APIKEY", "").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Record current versions of cached ontologies")
    parser.add_argument("--check", action="store_true", help="List ontologies that are newer on BioPortal")
    parser.add_argument("--only", help="Comma-separated acronyms (default: all cached)")
    parser.add_argument("--apikey", help="BioPortal API key (or set BIOPORTAL_APIKEY)")
    args = parser.parse_args()

    api_key = _get_api_key(args.apikey)
    if not api_key:
        raise SystemExit("No API key. Pass --apikey or set BIOPORTAL_APIKEY.")

    only = None
    if args.only:
        only = [a.strip() for a in args.only.split(",") if a.strip()]

    if args.record:
        record_versions(api_key, only)
    elif args.check:
        check_for_updates(api_key, only)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
