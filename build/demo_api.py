"""Readable walk-through of the running Maptology API, for showing to someone.

The manifest is a thousand-entry JSON blob; nobody can read that off a screen.
This prints the same information as a summary, downloads one cache, checks its
checksum, and shows that a restricted one is refused.

    python -m uvicorn api.main:app --port 8000      # in one terminal
    python build/demo_api.py                        # in another
"""

import argparse
import collections
import hashlib
import io
import json
import sys
import urllib.request
import zipfile

DEFAULT = "http://127.0.0.1:8000"


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.status, r.read()


def rule(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    rule("1. Is the server up?   GET /v1/health")
    try:
        _, body = get(base + "/v1/health")
    except Exception as e:
        sys.exit("cannot reach %s (%s)\nStart it with:\n"
                 "  python -m uvicorn api.main:app --port 8000" % (base, e))
    print("   " + body.decode())

    rule("2. What does the server have?   GET /v1/manifest")
    _, body = get(base + "/v1/manifest")
    m = json.loads(body)
    onts = m["ontologies"]
    modes = collections.Counter(o["delivery_mode"] for o in onts)
    print("   generated at   %s" % m["generated_at"])
    print("   ontologies     %d" % len(onts))
    print()
    print("   %-18s %5d  we may redistribute; licence grants it"
          % ("maptology_server", modes["maptology_server"]))
    print("   %-18s %5d  user fetches it from BioPortal themselves"
          % ("bioportal_user", modes["bioportal_user"]))
    print("   %-18s %5d  not offered at all"
          % ("blocked", modes["blocked"]))

    served = [o for o in onts if o["delivery_mode"] == "maptology_server"
              and o["download_url"]]
    if not served:
        sys.exit("nothing is served - regenerate the manifest first")
    total = sum(o["size"] or 0 for o in served)
    print("\n   downloadable payload: %.0f MB across %d ontologies"
          % (total / 1e6, len(served)))

    rule("3. Why is each one in that bucket?  (the policy file decides, not code)")
    for mode in ("maptology_server", "bioportal_user", "blocked"):
        ex = next((o for o in onts if o["delivery_mode"] == mode), None)
        if ex:
            print("   %-18s %-12s %s" % (mode, ex["acronym"], ex["reason"][:44]))

    pick = next((o for o in served if o["acronym"] == "EFO"), served[0])
    rule("4. Download one cache   GET %s" % pick["download_url"])
    print("   %s  %s  %.1f MB" % (pick["acronym"], pick["ontology_version"] or "-",
                                  (pick["size"] or 0) / 1e6))
    status, blob = get(base + pick["download_url"])
    got = hashlib.sha256(blob).hexdigest()
    print("   HTTP %d, %d bytes" % (status, len(blob)))
    print("   checksum in manifest : %s" % pick["sha256"])
    print("   checksum of download : %s" % got)
    print("   -> %s" % ("MATCH, the file is intact" if got == pick["sha256"]
                        else "MISMATCH"))

    zf = zipfile.ZipFile(io.BytesIO(blob))
    print("\n   inside the zip: %s" % ", ".join(zf.namelist()))
    meta = json.loads(zf.read("metadata.json"))
    print("   attribution travels with the data:")
    for k in ("acronym", "name", "ontology_version", "license", "license_url"):
        if meta.get(k):
            print("      %-17s %s" % (k, str(meta[k])[:52]))

    rule("5. What is NOT served, and why that is more than a naming accident")
    # The honest evidence is the manifest itself: a restricted ontology is never
    # given a download address, so there is nothing for a client to ask for.
    restricted = [o for o in onts if o["delivery_mode"] != "maptology_server"]
    with_url = [o for o in restricted if o["download_url"]]
    print("   restricted ontologies            %d" % len(restricted))
    print("   ...of those, given a download URL %d   <- must be zero" % len(with_url))
    ex = restricted[0]
    print("   e.g. %-14s download_url=%s" % (ex["acronym"], ex["download_url"]))

    print("\n   Requests that are refused:")
    tries = [("an address that is not offered",
              "/v1/cache/%s-000000000000.zip" % ex["acronym"]),
             ("a made-up file", "/v1/cache/NOPE-000000000000.zip"),
             ("a path-traversal attempt", "/v1/cache/..%2f..%2fetc%2fpasswd.zip")]
    for label, path in tries:
        try:
            status, _ = get(base + path)
        except urllib.error.HTTPError as e:
            status = e.code
        print("      %-32s -> HTTP %d" % (label, status))

    print("\n   Note: the first line uses a made-up filename, so on its own it")
    print("   only shows an unknown address is refused. The licence gate proper")
    print("   is that the server serves a file ONLY while the current manifest")
    print("   lists it - move an ontology to blocked, regenerate, and its old")
    print("   URL stops working without restarting anything. tests/test_api.py")
    print("   covers exactly that (test_existing_but_unreferenced_zip_is_not_served,")
    print("   test_reclassified_ontology_stops_serving).")

    print("\n" + "=" * 68)
    print("The split above comes from ontology_distribution_policy.tsv.")
    print("Changing a row and regenerating changes what is served - no code edit.")
    print("=" * 68)


if __name__ == "__main__":
    main()
