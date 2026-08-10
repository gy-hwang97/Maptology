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
import contextlib
import gc
import gzip
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

import ormsgpack
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer


# Resolved against the repo root (this script lives in build/) rather than the
# current working directory, so the script works no matter where it is run from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV_FILE = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_list.tsv")
# Each ontology is built in its own subprocess, which re-imports this module and
# so cannot see a caller's monkeypatched value. Reading the environment means a
# measurement or a trial run can point somewhere else and actually be isolated.
CACHE_DIR = os.environ.get("MAPTOLOGY_CACHE_DIR") or os.path.join(_REPO_ROOT, "tfidf_cache")
FAILURE_LOG = os.path.join(_REPO_ROOT, "build_failures.log")
WORKER_STATUS_FILE = os.path.join(CACHE_DIR, "_worker_status.json")
STREAM_THRESHOLD_MB = 100  # files larger than this prefer streaming XML parsing
# How long a build may take is set by which parser it falls through to, not by
# how big it is: measured across the whole corpus the cost ranges from 0.13
# seconds per megabyte (NCIT, streamed) to 2,118 (VEMO, a file of almost no size
# that still took 89 seconds). So size alone cannot set the allowance, and the
# floor has to be generous enough for a small file on the slow path.
#
# These are set from the slowest successful builds measured, with roughly three
# times their margin, because a generous limit costs nothing when a build
# succeeds - it returns as soon as it is done - and the point of the timeout is
# to catch a build that has hung rather than one that is merely slow:
#
#   VEMO       0.0 MB   89s      HGNC-NR   91 MB   138s
#   HRA      197.3 MB  215s      NCIT     917 MB   120s
PER_ONTOLOGY_TIMEOUT_SEC = 240  # floor: no build gets less than this
MAX_ONTOLOGY_TIMEOUT_SEC = 900  # ceiling: past this it is hung, not slow
TIMEOUT_SEC_PER_MB = 4.0

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


_XML_ROOT_CLOSERS = (b"</rdf:rdf>", b"</rdf>", b"</ontology>", b"</owl:ontology>")


def truncation_problem(acronym, owl_file):
    """Describe how this file is cut short, or None if it looks whole.

    Worth checking before parsing rather than after: a 1 GiB file that stops
    mid-element costs the whole timeout to discover, and the message that comes
    back - that no parser could read it - points at the parsers when the fault
    is in the file. Only XML serialisations are checked, since Turtle and OBO
    have no closing token to look for.
    """
    try:
        size = os.path.getsize(owl_file)
        with open(owl_file, "rb") as fh:
            head = fh.read(4096)
            fh.seek(max(0, size - 4096))
            tail = fh.read()
    except OSError:
        return None

    stripped = head.lstrip().lower()
    if not (stripped.startswith(b"<?xml") or stripped.startswith(b"<rdf")
            or stripped.startswith(b"<!doctype")):
        return None
    if any(closer in tail.lower() for closer in _XML_ROOT_CLOSERS):
        return None

    ending = tail[-60:].decode("utf-8", "replace").strip().replace("\n", " ")
    return ("file is truncated: %.1f MB of XML with no closing root element, "
            "ending %r. Delete it and download it again."
            % (size / 1e6, ending))


def timeout_for_size(size_mb):
    """How long this ontology is allowed to take before we call it hung."""
    return int(min(MAX_ONTOLOGY_TIMEOUT_SEC,
                   max(PER_ONTOLOGY_TIMEOUT_SEC, size_mb * TIMEOUT_SEC_PER_MB)))


# Suffixes worth trying to parse. Everything else in an archive - Protege project
# files, READMEs, licences - is packaging rather than ontology.
ONTOLOGY_SUFFIXES = (".owl", ".rdf", ".ttl", ".obo", ".omn", ".ofn",
                     ".xml", ".n3", ".nt", ".jsonld")

# How an ontology serialisation starts, for archives whose entries are named
# without a useful suffix.
_ONTOLOGY_PREFIXES = (b"<?xml", b"<rdf", b"<!doctype", b"@prefix", b"@base",
                      b"format-version:", b"prefix(", b"prefix:", b"ontology(")


def _looks_like_ontology(head):
    stripped = head.lstrip().lower()
    return stripped.startswith(_ONTOLOGY_PREFIXES)


def _ontology_entries(zf):
    """Every member of an archive that is worth handing to a parser.

    Packaging - Protege project files, licences, READMEs - is left out; the rest
    is kept, because a multi-file archive is one ontology split across files
    rather than a choice between them.
    """
    entries = [i for i in zf.infolist() if not i.is_dir() and i.file_size > 0]
    named = [i for i in entries
             if os.path.splitext(i.filename)[1].lower() in ONTOLOGY_SUFFIXES]
    if not named:
        # Nothing carries a useful suffix, so look at how each entry starts.
        for info in entries:
            try:
                with zf.open(info) as fh:
                    if _looks_like_ontology(fh.read(200)):
                        named.append(info)
            except Exception:
                continue
    if not named:
        raise RuntimeError(
            "archive contains no ontology file (entries: %s)"
            % ", ".join(i.filename for i in entries[:5]))
    return named


def uncompressed_size_mb(owl_file):
    """Size the parsers will actually face, without unpacking anything.

    An archive's stored size says nothing about the work ahead - BIOMODELS is
    12.6 MB on disk and 253 MB once opened - and both the timeout and the choice
    of parser depend on the real figure. ZIP keeps it in the central directory
    and gzip in the last four bytes, so neither costs a read of the whole file.
    """
    try:
        size = os.path.getsize(owl_file)
        with open(owl_file, "rb") as fh:
            magic = fh.read(4)
        if magic[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(owl_file) as zf:
                largest = max((i.file_size for i in zf.infolist()), default=0)
            return largest / 1e6 if largest else size / 1e6
        if magic[:2] == b"\x1f\x8b":
            with open(owl_file, "rb") as fh:
                fh.seek(-4, os.SEEK_END)
                # gzip records the size modulo 4 GiB; ontologies here are smaller.
                return int.from_bytes(fh.read(4), "little") / 1e6
        return size / 1e6
    except (OSError, zipfile.BadZipFile, ValueError):
        try:
            return os.path.getsize(owl_file) / 1e6
        except OSError:
            return 0.0


@contextlib.contextmanager
def readable_sources(acronym, owl_file):
    """Yield the files the parsers should read, unwrapping any container first.

    BioPortal serves each ontology in whatever container its author uploaded, and
    the downloader stores the response bytes under a .owl name without looking
    inside. Eight ontologies are therefore ZIP or GZIP archives that no parser
    here can read. Unwrapping at parse time rather than at download time also
    repairs the copies already sitting in existing installations.

    Unwrapped copies live in a temporary directory that is removed on the way
    out, so a 250 MB archive does not silently become 250 MB of extra cache.
    """
    try:
        with open(owl_file, "rb") as fh:
            magic = fh.read(4)
    except OSError:
        yield [owl_file]
        return

    if magic[:2] != b"\x1f\x8b" and magic[:4] != b"PK\x03\x04":
        yield [owl_file]
        return

    tmpdir = tempfile.mkdtemp(prefix="maptology_unpack_")
    try:
        if magic[:2] == b"\x1f\x8b":
            target = os.path.join(tmpdir, acronym + ".owl")
            with gzip.open(owl_file, "rb") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            yield [target]
        else:
            out = []
            with zipfile.ZipFile(owl_file) as zf:
                for n, info in enumerate(_ontology_entries(zf)):
                    # Entries can share a basename across subdirectories, so the
                    # index keeps them from overwriting one another.
                    base = os.path.basename(info.filename) or (acronym + ".owl")
                    target = os.path.join(tmpdir, "%03d_%s" % (n, base))
                    with zf.open(info) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    out.append(target)
            yield out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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

    # Everything is written beside its final name and moved into place only once
    # all three files are complete. is_cache_built asks whether the three files
    # exist, and writing them directly made that question unsafe to answer: the
    # terms file is opened before the data to fill it has been produced, so a
    # build interrupted at that moment - which the timeout does deliberately -
    # left an empty file that counted as a finished cache and loaded as nothing.
    folder = os.path.join(CACHE_DIR, acronym)
    os.makedirs(folder, exist_ok=True)
    finals = [os.path.join(folder, acronym + suffix) for suffix in
              ("_tfidf_matrix.npz", "_vectorizer.pkl", "_terms.ormsgpack")]
    temps = [f + ".tmp" for f in finals]

    try:
        # save_npz appends .npz to a path that lacks it, so it gets a handle.
        with open(temps[0], "wb") as fh:
            sparse.save_npz(fh, tfidf_matrix)
        with open(temps[1], "wb") as fh:
            pickle.dump(vectorizer, fh)
        packed = ormsgpack.packb(terms)
        with open(temps[2], "wb") as fh:
            fh.write(packed)
        for tmp, final in zip(temps, finals):
            os.replace(tmp, final)
    except BaseException:
        for tmp in temps:
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise

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
    """Index one ontology, unwrapping its container first if it has one."""
    with readable_sources(acronym, owl_file) as sources:
        for path in sources:
            problem = truncation_problem(acronym, path)
            if problem:
                raise RuntimeError(problem)
        return _build_from_sources(acronym, sources)


def _extract_terms(owl_file, size_mb):
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
        # Reporting last_err alone is misleading: the rdflib fallback tries
        # several serialisations and the final one is json-ld, so every
        # unparseable file was reported as a JSON error regardless of what it
        # actually contained. Say what was tried and how the file starts.
        try:
            with open(owl_file, "rb") as fh:
                head = fh.read(60).decode("utf-8", "replace").strip().replace("\n", " ")
        except OSError:
            head = "?"
        raise RuntimeError(
            "no parser could read this file (tried %s); starts with %r; last "
            "error was %s: %s"
            % (", ".join(label for label, _ in attempts), head,
               type(last_err).__name__ if last_err else "none", last_err))

    return method, terms, dep


def _build_from_sources(acronym, sources):
    """Index one ontology, which may arrive as several files.

    ICPS is twenty-five OWL files in one archive and OCRE is six; in both the
    ontology is the whole set rather than any one member. Parsing only the
    largest gave ICPS eleven terms and called it done, which is worse than
    failing - it claims coverage that is not there. Terms are merged on IRI, so
    a concept repeated across members is stored once.
    """
    merged = {}
    methods = []
    dep = 0
    errors = []
    for path in sources:
        size_mb = os.path.getsize(path) / 1e6
        try:
            method, terms, d = _extract_terms(path, size_mb)
        except Exception as e:
            errors.append("%s: %s" % (os.path.basename(path), e))
            continue
        methods.append(method)
        dep += d
        for t in terms:
            merged.setdefault(t["iri"], t)

    if not merged:
        raise RuntimeError(errors[0] if len(errors) == 1
                           else "no parser could read any of the %d files in this "
                                "archive; %s" % (len(sources), " | ".join(errors[:3])))

    terms = list(merged.values())
    method = methods[0] if len(set(methods)) == 1 else "+".join(sorted(set(methods)))
    if len(sources) > 1:
        method = "%s x%d" % (method, len(sources))

    shape = build_and_save(acronym, terms)
    n_def = sum(1 for t in terms if t["definition"] != "No definition available")
    n_syn = sum(1 for t in terms if t["synonyms"])
    return method, len(terms), dep, n_def, n_syn, shape


def _tail_text(path, limit=300):
    """Last few hundred characters of a worker's stderr, on one line."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            raw = fh.read()
    except OSError:
        return ""
    text = raw.decode("utf-8", "replace").strip().replace("\n", " | ")
    return text[-limit:]


def _discard(path):
    try:
        os.remove(path)
    except OSError:
        pass


def build_one_with_timeout(acronym, owl_file, size_mb, timeout_seconds=None):
    """Run build_one in a child subprocess with a hard timeout.

    Some ontologies cause owlready2 to enter pathological cyclic-resolution
    loops (e.g. MGBD spamming "ignoring cyclic type of" warnings for hours).
    Running each build in its own process means we can kill it cleanly.

    The allowance is derived from the size the parsers will meet rather than the
    size on disk, so a compressed ontology is not cut off part way through for
    having looked small.
    """
    if timeout_seconds is None:
        timeout_seconds = timeout_for_size(uncompressed_size_mb(owl_file))
    # One status file per ontology. A single shared path was fine while builds
    # ran one at a time, but it makes concurrent builds read each other's
    # results, and building several at once is the main way to use more than one
    # of the machine's cores.
    status_file = os.path.join(CACHE_DIR, "_worker_status_%s.json" % acronym)
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(status_file):
        try:
            os.remove(status_file)
        except OSError:
            pass

    cmd = [sys.executable, "-u", __file__, "--worker-build",
           acronym, owl_file, str(size_mb), status_file]
    # The child's output goes to a file rather than a pipe. Capturing it through
    # a pipe means that after the timeout fires we still have to drain whatever
    # the child buffered before it can be reaped, and a build that spins inside
    # owlready2 emits warnings without limit: CHEBI took 1,274 seconds to stop
    # under a 600 second timeout, all of it draining. Writing to a file makes the
    # kill immediate and still leaves the tail for the error message.
    err_file = os.path.join(CACHE_DIR, "_worker_stderr_%s.log" % acronym)
    returncode = None
    try:
        with open(err_file, "wb") as errfh:
            proc = subprocess.run(
                cmd,
                timeout=timeout_seconds,
                stdout=subprocess.DEVNULL,
                stderr=errfh,
            )
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        cleanup_partial_cache(acronym)
        _discard(err_file)
        raise RuntimeError("build timed out after " + str(timeout_seconds) + "s")

    stderr_tail = _tail_text(err_file)
    _discard(err_file)

    if not os.path.exists(status_file):
        cleanup_partial_cache(acronym)
        raise RuntimeError("worker died (exit " + str(returncode) +
                           ") without status; stderr: " + stderr_tail)

    with open(status_file, "r", encoding="utf-8") as fh:
        status = json.load(fh)

    try:
        os.remove(status_file)
    except OSError:
        pass

    if returncode != 0 or "error" in status:
        cleanup_partial_cache(acronym)
        raise RuntimeError(status.get("error", "worker failed (exit " + str(returncode) + ")"))

    return (status["method"], status["n"], status["dep"],
            status["n_def"], status["n_syn"], tuple(status["shape"]))


def worker_main():
    """Subprocess entry: build one ontology, write status to JSON, exit."""
    acronym = sys.argv[2]
    owl_file = sys.argv[3]
    size_mb = float(sys.argv[4])
    status_file = sys.argv[5] if len(sys.argv) > 5 else WORKER_STATUS_FILE
    try:
        method, n, dep, n_def, n_syn, shape = build_one(acronym, owl_file, size_mb)
        with open(status_file, "w", encoding="utf-8") as fh:
            json.dump({"method": method, "n": n, "dep": dep,
                       "n_def": n_def, "n_syn": n_syn,
                       "shape": list(shape)}, fh)
        sys.exit(0)
    except Exception as e:
        cleanup_partial_cache(acronym)
        with open(status_file, "w", encoding="utf-8") as fh:
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
