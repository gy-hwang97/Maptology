"""Bring the local ontology caches up to date, in one step.

Maptology searches locally, which is what makes it fast, but the local indexes
have to be built from the ontologies first. This script does the whole job:

    ask BioPortal what the current version of each ontology is
        -> download the ones we do not have, or that have changed
        -> build the TF-IDF index for each
        -> record the version that was actually downloaded
        -> refresh ontology_cache/ontology_list.tsv

It is meant to run every time the app starts. The first run is long because
there is nothing cached yet; later runs only touch what changed on BioPortal,
which is usually a handful of ontologies.

Nothing is redistributed by this project. Each user downloads ontologies from
BioPortal under their own API key and their own agreement with BioPortal, and
each ontology's own licence governs what they may then do with it.

Usage:
    python build/setup_ontologies.py                 # update what has changed
    python build/setup_ontologies.py --check-only    # report, download nothing
    python build/setup_ontologies.py --only NCIT,EFO
    python build/setup_ontologies.py --limit 20      # useful for a first trial

The API key is read from BIOPORTAL_APIKEY, or --apikey, or a prompt.
"""

import argparse
import csv
import os
import sys
import time

import requests

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "build"))

import build_all_caches as builder            # noqa: E402
import download_owl_files as downloader       # noqa: E402
import version_check as versions              # noqa: E402

API_BASE = "https://data.bioontology.org"
OWL_DIR = os.path.join(_REPO_ROOT, "ontology_cache")
TSV_FILE = os.path.join(OWL_DIR, "ontology_list.tsv")

# BioPortal documents a limit of 15 requests per second per IP. Stay well under
# it: this script is a background chore, not something anyone is waiting on.
REQUEST_INTERVAL = 0.12


def get_api_key(from_arg=None):
    key = (from_arg or os.environ.get("BIOPORTAL_APIKEY") or "").strip()
    if key:
        return key
    print("Maptology needs a free BioPortal API key to download ontologies.")
    print("Get one at https://bioportal.bioontology.org/accounts")
    print("Set BIOPORTAL_APIKEY to avoid being asked again.\n")
    try:
        return input("BioPortal API key: ").strip()
    except EOFError:
        return ""


def owl_path(acronym):
    return os.path.join(OWL_DIR, acronym + ".owl")


def plan(catalogue, local, only=None):
    """Decide what to do with each ontology.

    Returns a list of (entry, action, why). An ontology is rebuilt when the
    submission we recorded differs from the one BioPortal now offers, or when
    the files it needs are missing.
    """
    out = []
    for ont in catalogue:
        acronym = ont["acronym"]
        if only and acronym not in only:
            continue
        have = local.get(acronym) or {}
        cached = builder.is_cache_built(acronym)
        have_owl = os.path.exists(owl_path(acronym))

        if not cached or not have_owl:
            out.append((ont, "fetch", "not built yet" if not cached else "owl missing"))
        elif have.get("submissionId") != ont.get("submissionId"):
            out.append((ont, "fetch", "new submission %s -> %s"
                        % (have.get("submissionId"), ont.get("submissionId"))))
        else:
            out.append((ont, "skip", "up to date"))
    return out


def fetch_catalogue(api_key, only=None):
    """Ontologies available in a format we can parse, each with its current
    submission id. The id is read now and stored after a successful build, so a
    cache is never labelled with a version it was not built from."""
    print("Asking BioPortal which ontologies are available...")
    ontologies = downloader.get_all_ontologies(api_key)
    usable = downloader.filter_ontologies(ontologies, api_key)

    out = []
    for ont in usable:
        acronym = ont["acronym"]
        if only and acronym not in only:
            continue
        info = versions.get_latest_submission(acronym, api_key)
        time.sleep(REQUEST_INTERVAL)
        ont = dict(ont)
        ont["submissionId"] = (info or {}).get("submissionId")
        ont["version"] = (info or {}).get("version")
        ont["released"] = (info or {}).get("released")
        out.append(ont)
    return out


def download_one(ont, api_key):
    """Download a single ontology's OWL file. Written to a temp name and moved
    into place, so an interrupted download cannot be mistaken for a good file."""
    acronym = ont["acronym"]
    dest = owl_path(acronym)
    tmp = dest + ".part"
    url = API_BASE + "/ontologies/" + acronym + "/download"
    params = {} if ont.get("native_format") == "OWL" else {"download_format": "rdf"}
    headers = {"Authorization": "apikey token=" + api_key}

    resp = requests.get(url, headers=headers, params=params, timeout=300, stream=True)
    if resp.status_code != 200:
        raise RuntimeError("HTTP %d" % resp.status_code)
    os.makedirs(OWL_DIR, exist_ok=True)
    with open(tmp, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            fh.write(chunk)
    os.replace(tmp, dest)
    return os.path.getsize(dest) / 1e6


def write_catalogue_tsv(entries):
    """Rewrite ontology_list.tsv from whatever is actually on disk, so the app
    never lists an ontology it cannot open."""
    rows = []
    for ont in entries:
        acronym = ont["acronym"]
        if not os.path.exists(owl_path(acronym)):
            continue
        rows.append([ont.get("name") or acronym, owl_path(acronym), acronym,
                     ont.get("native_format", "OWL"),
                     ont.get("download_format", "OWL")])
    rows.sort(key=lambda r: r[2])
    os.makedirs(OWL_DIR, exist_ok=True)
    with open(TSV_FILE, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["name", "file_path", "abbreviation", "native_format", "download_format"])
        w.writerows(rows)
    return len(rows)


def run(api_key, only=None, limit=0, check_only=False):
    catalogue = fetch_catalogue(api_key, only)
    local = versions.load_local_versions()
    todo = plan(catalogue, local, only)

    work = [(o, why) for o, act, why in todo if act == "fetch"]
    skip = len(todo) - len(work)
    print("\n%d ontologies available, %d already up to date, %d to process"
          % (len(todo), skip, len(work)))
    if check_only:
        for ont, why in work[:40]:
            print("   %-14s %s" % (ont["acronym"], why))
        if len(work) > 40:
            print("   ... and %d more" % (len(work) - 40))
        return 0, 0

    if limit:
        work = work[:limit]
        print("(--limit: processing only the first %d)" % len(work))
    if work:
        print("This can take a while the first time. Ctrl+C is safe - progress "
              "is kept and the next run continues.\n")

    done = failed = 0
    for i, (ont, why) in enumerate(work, start=1):
        acronym = ont["acronym"]
        head = "[%d/%d] %-14s" % (i, len(work), acronym)
        try:
            if not os.path.exists(owl_path(acronym)):
                print(head + " downloading...", end="", flush=True)
                mb = download_one(ont, api_key)
                print(" %.1f MB" % mb, end="", flush=True)
                time.sleep(REQUEST_INTERVAL)
            else:
                print(head + " have file", end="", flush=True)

            size_mb = os.path.getsize(owl_path(acronym)) / 1e6
            print(", indexing...", end="", flush=True)
            t0 = time.time()
            builder.cleanup_partial_cache(acronym)
            method, n, dep, n_def, n_syn, shape = builder.build_one_with_timeout(
                acronym, owl_path(acronym), size_mb)
            print(" %d terms (%.0fs)" % (n, time.time() - t0))

            # Record the submission only once the build actually succeeded, so a
            # failed attempt is retried next run rather than looking current.
            local[acronym] = {"submissionId": ont.get("submissionId"),
                              "version": ont.get("version"),
                              "released": ont.get("released")}
            versions.save_local_versions(local)
            done += 1
        except KeyboardInterrupt:
            print("\n\nStopped. %d finished; run again to continue." % done)
            break
        except Exception as e:
            print(" FAILED: %s: %s" % (type(e).__name__, str(e)[:70]))
            failed += 1

    listed = write_catalogue_tsv(catalogue)
    print("\n%d ontologies ready for searching." % listed)
    if failed:
        print("%d could not be processed; Maptology will run without them." % failed)
    return done, failed


def main():
    ap = argparse.ArgumentParser(description="Download and index ontologies for Maptology")
    ap.add_argument("--apikey")
    ap.add_argument("--only", help="comma-separated acronyms")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--check-only", action="store_true",
                    help="report what would be done, download nothing")
    args = ap.parse_args()

    api_key = get_api_key(args.apikey)
    if not api_key:
        raise SystemExit("No API key given. Set BIOPORTAL_APIKEY or pass --apikey.")

    only = None
    if args.only:
        only = {a.strip() for a in args.only.split(",") if a.strip()}

    run(api_key, only, args.limit, args.check_only)


if __name__ == "__main__":
    main()
