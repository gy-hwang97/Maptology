"""
Build TF-IDF caches for every ontology listed in ontology_cache/ontology_list.tsv.

Resumable: skips ontologies whose cache already exists in tfidf_cache/<ACRONYM>/.
Failures are logged to build_failures.log and the script continues.

Strategy:
  - Small/medium files (<= STREAM_THRESHOLD_MB): owlready2 (handles RDF/XML + Turtle).
  - Large files (> STREAM_THRESHOLD_MB) that look like RDF/XML: streaming
    xml.etree.iterparse (low memory). Non-XML large files fall back to owlready2.

Annotation property handling (namespace-agnostic, matched by local name):
  label:       rdfs:label
  definition:  IAO_0000115 (OBO) -> P97 (NCIT DEFINITION) -> P325 (ALT_DEFINITION)
  synonyms:    hasExactSynonym / hasRelatedSynonym / hasBroadSynonym /
               hasNarrowSynonym (OBO) + P90 (NCIT FULL_SYN)
  deprecated:  owl:deprecated="true"

Usage:
    python build_all_caches.py                 # build everything not yet cached
    python build_all_caches.py --limit 5       # build only the first 5 (sample run)
    python build_all_caches.py --only ABC,DEF  # build just these acronyms
    python build_all_caches.py --list-only     # show the plan, don't build
"""

import argparse
import gc
import json
import os
import pickle
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import ormsgpack
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer


# Resolved against the repo root (this script lives in build/) rather than the
# current working directory, so the script works no matter where it is run from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV_FILE = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_list.tsv")
CACHE_DIR = os.path.join(_REPO_ROOT, "tfidf_cache")
FAILURE_LOG = os.path.join(_REPO_ROOT, "build_failures.log")
WORKER_STATUS_FILE = os.path.join(_REPO_ROOT, "_worker_status.json")
STREAM_THRESHOLD_MB = 100  # files larger than this prefer streaming XML parsing
PER_ONTOLOGY_TIMEOUT_SEC = 120  # subprocess hard-kill if a single build exceeds this

CLASS_TAG_OWL = "{http://www.w3.org/2002/07/owl#}Class"
ABOUT_ATTR = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"

# Property local names (namespace-agnostic match)
LABEL_LN = "label"
DEPRECATED_LN = "deprecated"
DEF_PRIMARY_LN = {"IAO_0000115", "P97"}
DEF_FALLBACK_LN = {"P325"}
SYN_LN = {
    "hasExactSynonym", "hasRelatedSynonym",
    "hasBroadSynonym", "hasNarrowSynonym",
    "P90",
}


def is_cache_built(acronym):
    folder = os.path.join(CACHE_DIR, acronym)
    return (
        os.path.exists(os.path.join(folder, acronym + "_tfidf_matrix.npz"))
        and os.path.exists(os.path.join(folder, acronym + "_vectorizer.pkl"))
        and os.path.exists(os.path.join(folder, acronym + "_terms.ormsgpack"))
    )


def localname(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def label_from_iri(iri):
    if "#" in iri:
        frag = iri.split("#")[-1]
    else:
        frag = iri.rstrip("/").split("/")[-1]
    return frag.replace("_", " ")


def looks_like_rdf_xml(owl_file):
    """True only for RDF/XML (the streaming parser's supported format).
    OWL/XML files (root <Ontology>, uses <Declaration>/<AnnotationAssertion>)
    are NOT supported by streaming and must go through owlready2."""
    try:
        with open(owl_file, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    head_lower = head.lower()
    # RDF/XML marker: the <rdf:RDF root element appears near the top.
    return b"<rdf:rdf" in head_lower


def extract_terms_streaming(owl_file):
    terms_by_iri = {}
    deprecated_count = 0
    n_classes = 0

    context = ET.iterparse(owl_file, events=("start", "end"))
    _, root = next(context)

    for event, elem in context:
        if event != "end" or elem.tag != CLASS_TAG_OWL:
            continue

        about = elem.get(ABOUT_ATTR)
        if about is None:
            elem.clear()
            continue

        n_classes += 1

        label = None
        def_primary = None
        def_alt = None
        synonyms = []
        is_dep = False

        for child in elem:
            ln = localname(child.tag)
            text = (child.text or "").strip()
            if not text:
                continue
            if ln == LABEL_LN and label is None:
                label = text
            elif ln in DEF_PRIMARY_LN and def_primary is None:
                def_primary = text
            elif ln in DEF_FALLBACK_LN and def_alt is None:
                def_alt = text
            elif ln in SYN_LN:
                if text not in synonyms:
                    synonyms.append(text)
            elif ln == DEPRECATED_LN and text.lower() == "true":
                is_dep = True

        elem.clear()

        if is_dep:
            deprecated_count += 1
            continue

        if label is None:
            label = label_from_iri(about)

        definition = def_primary or def_alt or "No definition available"
        terms_by_iri[about] = {
            "label": str(label),
            "iri": str(about),
            "synonyms": synonyms,
            "definition": definition,
        }

        if n_classes % 5000 == 0:
            root.clear()

    return list(terms_by_iri.values()), deprecated_count


def extract_terms_rdflib(owl_file):
    """Last-resort fallback: parse with rdflib (handles Turtle, N3, RDF/XML,
    NTriples, JSON-LD). Useful for .owl files whose content is actually
    Turtle (very common in OBO-style ontologies)."""
    from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal

    g = Graph()
    try:
        g.parse(owl_file)
    except Exception:
        # rdflib auto-detect failed; try common serializations explicitly.
        last_err = None
        for fmt in ("turtle", "xml", "nt", "n3", "json-ld"):
            try:
                g = Graph()
                g.parse(owl_file, format=fmt)
                last_err = None
                break
            except Exception as e:
                last_err = e
        if last_err is not None:
            raise last_err

    DEF_PRIMARY_LN = {"IAO_0000115", "P97"}
    DEF_FALLBACK_LN = {"P325"}
    SYN_LN_LOCAL = {
        "hasExactSynonym", "hasRelatedSynonym",
        "hasBroadSynonym", "hasNarrowSynonym",
        "P90",
    }

    def local(uri):
        s = str(uri)
        if "#" in s:
            return s.rsplit("#", 1)[-1]
        return s.rsplit("/", 1)[-1]

    # Named classes only (skip blank nodes / restrictions)
    class_iris = []
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef):
            class_iris.append(s)

    terms = []
    deprecated_count = 0
    seen = set()

    for cls in class_iris:
        iri = str(cls)
        if iri in seen:
            continue
        seen.add(iri)

        label = None
        def_primary = None
        def_alt = None
        synonyms = []
        is_dep = False

        for p, o in g.predicate_objects(cls):
            pn = local(p)
            if pn == "deprecated":
                if isinstance(o, Literal) and str(o).lower() == "true":
                    is_dep = True
                continue
            if not isinstance(o, Literal):
                continue
            v = str(o).strip()
            if not v:
                continue
            if pn == "label" and label is None:
                label = v
            elif pn in DEF_PRIMARY_LN and def_primary is None:
                def_primary = v
            elif pn in DEF_FALLBACK_LN and def_alt is None:
                def_alt = v
            elif pn in SYN_LN_LOCAL:
                if v not in synonyms:
                    synonyms.append(v)

        if is_dep:
            deprecated_count += 1
            continue
        if label is None:
            label = label_from_iri(iri)
        definition = def_primary or def_alt or "No definition available"
        terms.append({
            "label": str(label),
            "iri": iri,
            "synonyms": synonyms,
            "definition": definition,
        })

    return terms, deprecated_count


def extract_terms_owlready(owl_file):
    # Lazy import so streaming-only path doesn't require owlready2.
    from owlready2 import World

    world = World()
    try:
        onto = world.get_ontology(owl_file).load()
    except Exception:
        try:
            world.close()
        except Exception:
            pass
        raise

    terms = []
    deprecated_count = 0
    try:
        for cls in onto.classes():
            is_dep = False
            try:
                dep_vals = list(getattr(cls, "deprecated", []) or [])
                if True in dep_vals:
                    is_dep = True
            except Exception:
                pass
            if is_dep:
                deprecated_count += 1
                continue

            label = None
            try:
                if cls.label:
                    label = cls.label.first()
            except Exception:
                pass
            if label is None:
                label = label_from_iri(cls.iri)

            synonyms = []
            for prop in ("hasExactSynonym", "hasRelatedSynonym",
                         "hasBroadSynonym", "hasNarrowSynonym", "P90"):
                try:
                    vals = getattr(cls, prop, None)
                except Exception:
                    vals = None
                if vals:
                    for v in vals:
                        if isinstance(v, str) and v and v not in synonyms:
                            synonyms.append(v)

            definition = "No definition available"
            for prop in ("IAO_0000115", "P97", "P325"):
                try:
                    vals = getattr(cls, prop, None)
                except Exception:
                    vals = None
                if vals:
                    first = vals[0]
                    if isinstance(first, str) and first.strip():
                        definition = first
                        break

            terms.append({
                "label": str(label),
                "iri": str(cls.iri),
                "synonyms": synonyms,
                "definition": definition,
            })
    finally:
        try:
            world.close()
        except Exception:
            pass

    return terms, deprecated_count


def build_and_save(acronym, terms):
    if not terms:
        raise RuntimeError("0 terms extracted")

    documents = []
    for t in terms:
        text = t["label"]
        if t["synonyms"]:
            text = text + " " + " ".join(t["synonyms"])
        documents.append(text)

    vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        lowercase=True,
        stop_words="english",
    )
    tfidf_matrix = vectorizer.fit_transform(documents)

    folder = os.path.join(CACHE_DIR, acronym)
    os.makedirs(folder, exist_ok=True)
    sparse.save_npz(os.path.join(folder, acronym + "_tfidf_matrix.npz"), tfidf_matrix)
    with open(os.path.join(folder, acronym + "_vectorizer.pkl"), "wb") as f:
        pickle.dump(vectorizer, f)
    with open(os.path.join(folder, acronym + "_terms.ormsgpack"), "wb") as f:
        f.write(ormsgpack.packb(terms))

    return tfidf_matrix.shape


def cleanup_partial_cache(acronym):
    folder = os.path.join(CACHE_DIR, acronym)
    if not os.path.isdir(folder):
        return
    for fname in os.listdir(folder):
        try:
            os.remove(os.path.join(folder, fname))
        except OSError:
            pass
    try:
        os.rmdir(folder)
    except OSError:
        pass


def build_one(acronym, owl_file, size_mb):
    """Try several extractors in order until one returns a non-empty term list.

    Order:
      1. Primary: streaming (for big RDF/XML) OR owlready2 (everything else).
      2. Streaming fallback if file looks like RDF/XML and wasn't already tried.
      3. rdflib fallback (handles Turtle / N3 / JSON-LD / RDF/XML).
    """
    is_xml = looks_like_rdf_xml(owl_file)
    use_streaming_primary = size_mb > STREAM_THRESHOLD_MB and is_xml

    attempts = []
    if use_streaming_primary:
        attempts.append(("stream", lambda: extract_terms_streaming(owl_file)))
    else:
        attempts.append(("owlready", lambda: extract_terms_owlready(owl_file)))
    if not use_streaming_primary and is_xml:
        attempts.append(("stream(fb)", lambda: extract_terms_streaming(owl_file)))
    attempts.append(("rdflib(fb)", lambda: extract_terms_rdflib(owl_file)))

    method = None
    terms = None
    dep = 0
    last_err = None
    for label, fn in attempts:
        try:
            t, d = fn()
        except Exception as e:
            last_err = e
            continue
        if t:
            method = label
            terms = t
            dep = d
            break
        last_err = RuntimeError("0 terms extracted via " + label)

    if not terms:
        raise last_err if last_err is not None else RuntimeError("all extractors failed")

    shape = build_and_save(acronym, terms)
    n_def = sum(1 for t in terms if t["definition"] != "No definition available")
    n_syn = sum(1 for t in terms if t["synonyms"])
    return method, len(terms), dep, n_def, n_syn, shape


def build_one_with_timeout(acronym, owl_file, size_mb, timeout_seconds=PER_ONTOLOGY_TIMEOUT_SEC):
    """Run build_one in a child subprocess with a hard timeout.

    Some ontologies cause owlready2 to enter pathological cyclic-resolution
    loops (e.g. MGBD spamming "ignoring cyclic type of" warnings for hours).
    Running each build in its own process means we can kill it cleanly.
    """
    if os.path.exists(WORKER_STATUS_FILE):
        try:
            os.remove(WORKER_STATUS_FILE)
        except OSError:
            pass

    cmd = [sys.executable, "-u", __file__, "--worker-build",
           acronym, owl_file, str(size_mb)]
    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        cleanup_partial_cache(acronym)
        raise RuntimeError("build timed out after " + str(timeout_seconds) + "s")

    if not os.path.exists(WORKER_STATUS_FILE):
        cleanup_partial_cache(acronym)
        tail = (proc.stderr or "")[-300:].strip().replace("\n", " | ")
        raise RuntimeError("worker died (exit " + str(proc.returncode) +
                           ") without status; stderr: " + tail)

    with open(WORKER_STATUS_FILE, "r", encoding="utf-8") as fh:
        status = json.load(fh)

    if proc.returncode != 0 or "error" in status:
        cleanup_partial_cache(acronym)
        raise RuntimeError(status.get("error", "worker failed (exit " + str(proc.returncode) + ")"))

    return (status["method"], status["n"], status["dep"],
            status["n_def"], status["n_syn"], tuple(status["shape"]))


def worker_main():
    """Subprocess entry: build one ontology, write status to JSON, exit."""
    acronym = sys.argv[2]
    owl_file = sys.argv[3]
    size_mb = float(sys.argv[4])
    try:
        method, n, dep, n_def, n_syn, shape = build_one(acronym, owl_file, size_mb)
        with open(WORKER_STATUS_FILE, "w", encoding="utf-8") as fh:
            json.dump({"method": method, "n": n, "dep": dep,
                       "n_def": n_def, "n_syn": n_syn,
                       "shape": list(shape)}, fh)
        sys.exit(0)
    except Exception as e:
        cleanup_partial_cache(acronym)
        with open(WORKER_STATUS_FILE, "w", encoding="utf-8") as fh:
            json.dump({"error": type(e).__name__ + ": " + str(e)}, fh)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Build only these acronyms (comma-separated)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after building this many (sample run)")
    parser.add_argument("--list-only", action="store_true",
                        help="Print the plan, don't build")
    args = parser.parse_args()

    df = pd.read_csv(TSV_FILE, sep="\t")
    only = None
    if args.only:
        only = {a.strip() for a in args.only.split(",")}

    plan = []
    for _, row in df.iterrows():
        acronym = str(row["abbreviation"])
        owl_file = str(row["file_path"])
        if only and acronym not in only:
            continue
        plan.append((acronym, owl_file))

    total = len(plan)
    failures = []
    skipped = 0
    built = 0
    t0 = time.time()

    print("Plan: " + str(total) + " ontologies considered "
          "(already-built ones will be skipped)", flush=True)
    if args.list_only:
        for acronym, owl_file in plan:
            print(" ", acronym, owl_file)
        return

    for i, (acronym, owl_file) in enumerate(plan, start=1):
        if is_cache_built(acronym):
            skipped += 1
            continue

        if not os.path.exists(owl_file):
            msg = "OWL file missing: " + owl_file
            failures.append((acronym, msg))
            print("[" + str(i) + "/" + str(total) + "] FAIL " + acronym + " -- " + msg, flush=True)
            continue

        size_mb = os.path.getsize(owl_file) / 1024.0 / 1024.0
        tstart = time.time()
        try:
            method, n, dep, n_def, n_syn, shape = build_one_with_timeout(acronym, owl_file, size_mb)
            elapsed = time.time() - tstart
            built += 1
            print("[" + str(i) + "/" + str(total) + "] OK   "
                  + acronym.ljust(15)
                  + (str(round(size_mb, 1)) + "MB").rjust(10) + "  "
                  + method.ljust(8) + "  "
                  + str(n).rjust(7) + " terms  "
                  + "def=" + str(n_def) + " syn=" + str(n_syn)
                  + "  shape=" + str(shape)
                  + "  (" + str(round(elapsed, 1)) + "s)", flush=True)
        except Exception as e:
            cleanup_partial_cache(acronym)
            err = type(e).__name__ + ": " + str(e)
            failures.append((acronym, err))
            print("[" + str(i) + "/" + str(total) + "] FAIL "
                  + acronym.ljust(15)
                  + (str(round(size_mb, 1)) + "MB").rjust(10) + "  "
                  + "-> " + err, flush=True)

        gc.collect()

        if args.limit and built >= args.limit:
            print("--limit reached, stopping early", flush=True)
            break

    total_min = (time.time() - t0) / 60.0
    print("", flush=True)
    print("=" * 70, flush=True)
    print("Done in " + str(round(total_min, 1)) + " min.  "
          + "built=" + str(built) + "  "
          + "skipped(already cached)=" + str(skipped) + "  "
          + "failed=" + str(len(failures)), flush=True)

    if failures:
        with open(FAILURE_LOG, "w", encoding="utf-8") as fh:
            for a, e in failures:
                fh.write(a + "\t" + e + "\n")
        print("Failure log written to " + FAILURE_LOG, flush=True)


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "--worker-build":
        worker_main()
    else:
        main()
