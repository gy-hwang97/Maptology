"""Turn the licence audit into a DRAFT distribution policy for review.

This exists so the API can be demonstrated against the real 901 ontologies
instead of a four-row stub. The output is a proposal for the professor to
approve or edit - it is NOT an authoritative licensing decision, and it is
written to a .draft.tsv name so it cannot be mistaken for one.

Mapping applied (conservative; BioPortal support confirmed they cannot grant
redistribution rights, so anything without a positive grant stays off our server):

    PERMISSIVE     -> maptology_server   the licence itself grants redistribution
    COPYLEFT       -> maptology_server   grants it, with share-alike obligations
    NONCOMMERCIAL  -> bioportal_user     redistribution would bind downstream users
    NODERIVS       -> blocked            a TF-IDF cache is itself a derivative
    REVIEW         -> bioportal_user     unresolved, pending human review
    NONE_STATED    -> bioportal_user     no grant found; BioPortal advises asking
                                         the maintainer directly
    (absent)       -> blocked            fail safe

Usage:
    python build/make_draft_policy.py
"""

import csv
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(_REPO_ROOT, "docs", "license-audit", "license_audit_expanded.tsv")
OUT = os.path.join(_REPO_ROOT, "ontology_distribution_policy.draft.tsv")

BUCKET_TO_MODE = {
    "PERMISSIVE":    ("maptology_server", "licence grants redistribution"),
    "COPYLEFT":      ("maptology_server", "grants redistribution; share-alike applies"),
    "NONCOMMERCIAL": ("bioportal_user",   "non-commercial clause; not redistributed"),
    "NODERIVS":      ("blocked",          "no-derivatives; the cache is a derivative"),
    "REVIEW":        ("bioportal_user",   "licence unresolved, pending review"),
    "NONE_STATED":   ("bioportal_user",   "no licence found; ask the maintainer"),
}


def main():
    if not os.path.exists(AUDIT):
        raise SystemExit("audit not found: " + AUDIT)

    rows, counts = [], {}
    with open(AUDIT, "r", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            acronym = (r.get("acronym") or "").strip()
            if not acronym:
                continue
            bucket = (r.get("bucket") or "").strip().upper()
            mode, why = BUCKET_TO_MODE.get(bucket, ("blocked", "unclassified"))
            # viewingRestriction other than public overrides everything.
            vis = (r.get("viewingRestriction") or "").strip().lower()
            if vis and vis != "public":
                mode, why = "blocked", "not public in BioPortal (%s)" % vis
            counts[mode] = counts.get(mode, 0) + 1
            rows.append([acronym, mode, (r.get("license") or "").strip(),
                         (r.get("evidenceUrl") or "").strip(),
                         "%s: %s" % (bucket or "UNKNOWN", why)])

    rows.sort(key=lambda x: x[0])
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("acronym\tdelivery_mode\tlicense\tlicense_url\treason\n")
        for r in rows:
            fh.write("\t".join(x.replace("\t", " ") for x in r) + "\n")

    print("wrote %s  (%d ontologies)" % (OUT, len(rows)))
    for mode in sorted(counts):
        print("   %-18s %4d" % (mode, counts[mode]))
    print("\nDRAFT ONLY - proposal for review, not an authoritative decision.")


if __name__ == "__main__":
    main()
