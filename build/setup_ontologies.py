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
import contextlib
import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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

# BioPortal documents a limit of 15 requests per second per API key. Stay well
# under it: this script is a background chore, not something anyone is waiting
# on. Small files finish in a fraction of a second, so several connections can
# start requests far faster than the average rate suggests; the limit has to be
# enforced on the request rate itself, not inferred from the connection count.
REQUEST_INTERVAL = 0.12

# Downloads run several at a time. BioPortal gives about 4.7 MB/s down a single
# connection whatever the file size, but serves several happily: measured here at
# 12.4 MB/s over four connections and 15.4 MB/s over eight. Four is close to the
# available gain while staying below what a browser opens to one host, which
# matters for a free academic service. Override with MAPTOLOGY_DOWNLOAD_WORKERS.
DOWNLOAD_WORKERS = int(os.environ.get("MAPTOLOGY_DOWNLOAD_WORKERS", "4"))

# Indexing runs several ontologies at once. Each one is a separate subprocess
# that has to import scikit-learn, scipy and pandas before it can do anything,
# which costs about 2.3 seconds - roughly 38 minutes across a thousand
# ontologies, spent entirely on start-up. Running them concurrently divides that
# down. Capped rather than using every core because each worker holds a parsed
# ontology in memory and the largest need a few GB.
def _default_build_workers():
    try:
        cores = os.cpu_count() or 2
    except NotImplementedError:
        cores = 2
    return max(1, min(6, cores - 1))


BUILD_WORKERS = int(os.environ.get("MAPTOLOGY_BUILD_WORKERS", "0")) or _default_build_workers()

# Cores are not the limit here, memory is. A worker holds the whole parsed
# ontology: one was measured at 2.7 GB on a 91 MB file, and the largest are ten
# times that size on disk. Six of those at once needs more memory than an
# ordinary machine has - 16 GB against the 15.4 GB of the machine this was
# measured on - and the run would start swapping instead of indexing.
#
# So the big ones get a small allowance of their own while the remaining workers
# carry on with small files, which is what the whole corpus was measured under.
# The threshold is on the size after decompression, since an archive says
# nothing useful about what it holds.
HEAVY_MB = 50
HEAVY_WORKERS = int(os.environ.get("MAPTOLOGY_HEAVY_WORKERS", "0")) or 2
_heavy_slots = threading.Semaphore(HEAVY_WORKERS)


@contextlib.contextmanager
def _build_slot(acronym):
    """Hold a heavy-build slot for as long as this ontology needs one."""
    path = owl_path(acronym)
    heavy = False
    try:
        heavy = os.path.exists(path) and builder.uncompressed_size_mb(path) > HEAVY_MB
    except OSError:
        heavy = False
    if heavy:
        _heavy_slots.acquire()
    try:
        yield
    finally:
        if heavy:
            _heavy_slots.release()


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
    """Download a single ontology's OWL file.

    Written to a temp name and moved into place only once the response has been
    checked against the length the server promised. Writing to a temp name was
    never enough on its own: a response that stops early ends iter_content
    without raising, so the short file was renamed over the good one and looked
    finished. That is how PR, GAZ and CHEBI came to sit on disk at 1.0007 GiB
    each, ending in the middle of an XML element - BioPortal cuts its RDF
    conversion off there, and nothing here noticed.
    """
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
    written = 0
    try:
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
                written += len(chunk)

        # Content-Length describes the bytes on the wire. When the response is
        # compressed those are not the bytes we just wrote, so there is nothing
        # to compare; the same goes for chunked responses, which send no length.
        promised = resp.headers.get("Content-Length")
        if promised is not None and not resp.headers.get("Content-Encoding"):
            try:
                promised = int(promised)
            except (TypeError, ValueError):
                promised = None
            if promised is not None and written != promised:
                raise RuntimeError(
                    "incomplete download: got %d bytes, server said %d"
                    % (written, promised))
    except BaseException:
        # Leave no half-written file behind, and leave any working copy alone.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

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
    with _build_slot(acronym):
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
    lock = threading.Lock()

    # Downloads run on their own connections; indexing runs on its own workers.
    # A single connection tops out near 4.7 MB/s whatever the file size, and a
    # single indexing worker leaves most of a multi-core machine idle while it
    # pays a ~2.3 second import cost per ontology. Both phases overlap, so the
    # run takes about as long as the slower of the two rather than their sum.
    dl_pool = ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS)
    pending = {}
    for _ont, _why in work:
        _acr = _ont["acronym"]
        if not os.path.exists(owl_path(_acr)):
            pending[_acr] = dl_pool.submit(download_one, _ont, api_key)

    counter = {"n": 0}

    def process(ont):
        acronym = ont["acronym"]
        try:
            future = pending.get(acronym)
            reused = future is None
            if not reused:
                future.result()
            try:
                n = _index(acronym)
            except Exception:
                # A file left over from an earlier run can be truncated, or in a
                # format we asked BioPortal not to send. Retrying the same bytes
                # forever would keep this ontology broken, so fetch it once more
                # before giving up.
                if not reused:
                    raise
                os.remove(owl_path(acronym))
                download_one(ont, api_key)
                n = _index(acronym)
            with lock:
                counter["n"] += 1
                local[acronym] = {"submissionId": ont.get("submissionId"),
                                  "version": ont.get("version"),
                                  "released": ont.get("released")}
                versions.save_local_versions(local)
                print("[%d/%d] %-14s %d terms"
                      % (counter["n"], len(work), acronym, n), flush=True)
            return True
        except Exception as e:
            with lock:
                counter["n"] += 1
                failures[acronym] = ont.get("submissionId")
                save_failures(failures)
                print("[%d/%d] %-14s FAILED: %s: %s"
                      % (counter["n"], len(work), acronym,
                         type(e).__name__, str(e)[:60]), flush=True)
            return False

    build_pool = ThreadPoolExecutor(max_workers=BUILD_WORKERS)
    print("indexing %d at a time on %d cores\n" % (BUILD_WORKERS, os.cpu_count() or 1))
    try:
        for succeeded in build_pool.map(process, [o for o, _ in work]):
            if succeeded:
                done += 1
            else:
                failed += 1
    except KeyboardInterrupt:
        print("\n\nStopped. %d finished; run again to continue." % done)
    finally:
        # Drop queued work rather than making the user wait it out.
        dl_pool.shutdown(wait=False, cancel_futures=True)
        build_pool.shutdown(wait=False, cancel_futures=True)

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
