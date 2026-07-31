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
import json
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
FAILURES_FILE = os.path.join(OWL_DIR, "build_failures.json")

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


def load_failures():
    """Submissions that could not be parsed, so they are not retried forever.

    A few ontologies are published in formats none of our parsers read. Without
    this, every start would re-download and re-fail them. Keyed by submission,
    so a new release from the publisher is tried afresh.
    """
    if not os.path.exists(FAILURES_FILE):
        return {}
    try:
        with open(FAILURES_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def save_failures(failures):
    os.makedirs(OWL_DIR, exist_ok=True)
    tmp = FAILURES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(failures, fh, indent=2, sort_keys=True)
    os.replace(tmp, FAILURES_FILE)


def owl_path(acronym):
    return os.path.join(OWL_DIR, acronym + ".owl")


def plan(catalogue, local, only=None, failures=None):
    """Decide what to do with each ontology.

    Returns a list of (entry, action, why). An ontology is rebuilt when the
    submission we recorded differs from the one BioPortal now offers, or when
    the files it needs are missing.
    """
    failures = failures or {}
    out = []
    for ont in catalogue:
        acronym = ont["acronym"]
        if only and acronym not in only:
            continue
        # Already proven unreadable at this exact submission; a new one is
        # worth another try, this one is not.
        if failures.get(acronym) == ont.get("submissionId") and not only:
            out.append((ont, "skip", "no parser could read submission %s"
                        % ont.get("submissionId")))
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
    """Ontologies we can parse, each with the submission BioPortal now offers.

    One request to /submissions returns the latest submission of every ontology
    with its id, version, release date and source language. Asking per ontology
    instead costs about 2,200 requests and takes over half an hour, which is far
    too slow to sit in front of app startup.

    The id is read here and stored only after a build succeeds, so a cache is
    never labelled with a version it was not built from.
    """
    print("Asking BioPortal which ontologies are available...", end="", flush=True)
    t0 = time.time()
    resp = requests.get(
        API_BASE + "/submissions",
        params={"apikey": api_key,
                "include": "submissionId,version,released,hasOntologyLanguage,ontology",
                "display_links": "false", "display_context": "false"},
        timeout=600)
    resp.raise_for_status()
    submissions = resp.json()
    print(" %d in %.0fs" % (len(submissions), time.time() - t0))

    out = []
    skipped = {}
    for sub in submissions:
        ont = sub.get("ontology") or {}
        acronym = (ont.get("acronym") if isinstance(ont, dict) else None) or ""
        if not acronym or (only and acronym not in only):
            continue
        language = str(sub.get("hasOntologyLanguage") or "").upper()
        # OWL downloads natively; OBO is converted by BioPortal to RDF/XML.
        # Anything else (SKOS, UMLS) our parsers cannot read.
        if "OWL" in language:
            native, fmt = "OWL", "OWL"
        elif "OBO" in language:
            native, fmt = "OBO", "RDF/XML"
        else:
            skipped[language or "UNKNOWN"] = skipped.get(language or "UNKNOWN", 0) + 1
            continue
        out.append({
            "acronym": acronym,
            "name": (ont.get("name") if isinstance(ont, dict) else "") or acronym,
            "native_format": native,
            "download_format": fmt,
            "submissionId": sub.get("submissionId"),
            "version": sub.get("version"),
            "released": sub.get("released"),
        })
    if skipped:
        worst = sorted(skipped.items(), key=lambda kv: -kv[1])[:3]
        print("   skipping %d in formats Maptology cannot parse (%s)"
              % (sum(skipped.values()),
                 ", ".join("%s %d" % (k, v) for k, v in worst)))
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


def _existing_rows():
    """Rows already in ontology_list.tsv, keyed by acronym."""
    if not os.path.exists(TSV_FILE):
        return {}
    out = {}
    try:
        with open(TSV_FILE, "r", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                acr = (r.get("abbreviation") or "").strip()
                if acr:
                    out[acr] = r
    except OSError:
        return {}
    return out


def _index(acronym):
    """Build the TF-IDF index for one ontology. Returns the term count."""
    path = owl_path(acronym)
    builder.cleanup_partial_cache(acronym)
    method, n, dep, n_def, n_syn, shape = builder.build_one_with_timeout(
        acronym, path, os.path.getsize(path) / 1e6)
    return n


def write_catalogue_tsv(entries):
    """Rewrite ontology_list.tsv from whatever is actually on disk.

    Listing only what BioPortal currently offers would quietly drop ontologies
    that were withdrawn from its catalogue but are still downloaded, built and
    perfectly usable here (CMEO, CVO and HTO are in that position today).
    Anything with an OWL file on disk stays; anything without one goes, so the
    app never offers a file it cannot open.
    """
    rows, seen = [], set()
    for ont in entries:
        acronym = ont["acronym"]
        if not os.path.exists(owl_path(acronym)):
            continue
        seen.add(acronym)
        rows.append([ont.get("name") or acronym, owl_path(acronym), acronym,
                     ont.get("native_format", "OWL"),
                     ont.get("download_format", "OWL")])

    for acr, old in _existing_rows().items():
        if acr in seen or not os.path.exists(owl_path(acr)):
            continue
        rows.append([old.get("name") or acr, owl_path(acr), acr,
                     old.get("native_format", "OWL"),
                     old.get("download_format", "OWL")])

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
    failures = load_failures()
    todo = plan(catalogue, local, only, failures)

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
            reused = os.path.exists(owl_path(acronym))
            if not reused:
                print(head + " downloading...", end="", flush=True)
                mb = download_one(ont, api_key)
                print(" %.1f MB" % mb, end="", flush=True)
                time.sleep(REQUEST_INTERVAL)
            else:
                print(head + " have file", end="", flush=True)

            print(", indexing...", end="", flush=True)
            t0 = time.time()
            try:
                n = _index(acronym)
            except Exception:
                # A file left over from an earlier run can be truncated, or in a
                # format we asked BioPortal not to send. Retrying the same bytes
                # forever would keep this ontology broken, so fetch it once more
                # before giving up.
                if not reused:
                    raise
                print(" stale file, re-downloading...", end="", flush=True)
                os.remove(owl_path(acronym))
                mb = download_one(ont, api_key)
                print(" %.1f MB, indexing..." % mb, end="", flush=True)
                time.sleep(REQUEST_INTERVAL)
                n = _index(acronym)
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
            failures[acronym] = ont.get("submissionId")
            save_failures(failures)
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
