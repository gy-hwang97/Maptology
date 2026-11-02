"""Precomputed character-trigram search over individual ontology aliases.

An index is built from the terms saved by the ontology installer the first
time that ontology is searched. It is stored separately from the word index.
The source terms file determines the index generation, so an ontology update
cannot silently reuse an older index.
"""

import copy
import hashlib
import json
import os
import pickle
import shutil
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import ormsgpack
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import check_pairwise_arrays
from sklearn.utils.extmath import safe_sparse_dot


_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _ROOT / "tfidf_cache"
_INDEX_ROOT = Path(os.environ.get("MAPTOLOGY_E12_CACHE_DIR", _SOURCE_ROOT / ".e12"))
_loaded = {}
_locks = {}
_locks_guard = threading.Lock()
_PARTITION = 200


def clear_loaded():
    """Discard indexes held in memory after ontology files are updated."""
    _loaded.clear()


def unload(acronym):
    """Release an ontology's in-memory index when it is deselected."""
    with _lock_for(acronym):
        _loaded.pop(acronym, None)


def _lock_for(acronym):
    with _locks_guard:
        if acronym not in _locks:
            _locks[acronym] = threading.Lock()
        return _locks[acronym]


def _source_path(acronym):
    return _SOURCE_ROOT / acronym / (acronym + "_terms.ormsgpack")


def _index_files(folder):
    return (folder / "matrix.npz", folder / "vectorizer.pkl",
            folder / "alias_to_concept.npy", folder / "lookup.ormsgpack",
            folder / "meta.json")


def _complete(folder, digest):
    files = _index_files(folder)
    for path in files:
        if not path.is_file():
            return False
    with files[-1].open(encoding="utf-8") as handle:
        meta = json.load(handle)
    return meta.get("terms_sha256") == digest and meta.get("method") == "e12-v1"


def _build_index(folder, terms, digest):
    aliases = []
    concept_rows = []
    lookup = {}
    for concept_index, term in enumerate(terms):
        seen_aliases = set()
        seen_lookup = set()
        names = [term.get("label") or ""]
        for synonym in term.get("synonyms") or []:
            names.append(synonym)

        for name in names:
            alias = str(name)
            if not alias.strip():
                continue
            if alias not in seen_aliases:
                seen_aliases.add(alias)
                aliases.append(alias)
                concept_rows.append(concept_index)
            key = alias.strip()
            if key not in seen_lookup:
                seen_lookup.add(key)
                if key not in lookup:
                    lookup[key] = []
                lookup[key].append(concept_index)

    if not aliases:
        raise ValueError("The ontology has no searchable names or synonyms")

    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 3), lowercase=True)
    matrix = vectorizer.fit_transform(aliases)
    parent = folder.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".building-", dir=parent))
    try:
        matrix_file, vectorizer_file, concept_file, lookup_file, meta_file = _index_files(temp)
        sparse.save_npz(matrix_file, matrix)
        with vectorizer_file.open("wb") as handle:
            pickle.dump(vectorizer, handle)
        np.save(concept_file, np.asarray(concept_rows, dtype=np.int32))
        lookup_file.write_bytes(ormsgpack.packb(lookup))
        meta_file.write_text(json.dumps({
            "method": "e12-v1", "terms_sha256": digest,
            "concepts": len(terms), "aliases": len(aliases),
            "analyzer": "char_wb", "ngram_range": [3, 3],
            "lowercase": True, "exact_match_normalization": "strip",
        }, indent=2), encoding="utf-8")
        for attempt in range(10):
            try:
                os.replace(temp, folder)
                break
            except FileExistsError:
                if not _complete(folder, digest):
                    raise
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.5)
    finally:
        if temp.exists():
            if not temp.resolve().is_relative_to(parent.resolve()):
                raise RuntimeError("Temporary E12 index is outside its cache directory")
            shutil.rmtree(temp)


def load_index(acronym):
    """Load or build an E12 index for the installed version of an ontology."""
    source = _source_path(acronym)
    if not source.is_file():
        return None
    with _lock_for(acronym):
        stat = source.stat()
        stamp = (stat.st_dev, stat.st_ino, stat.st_size,
                 stat.st_mtime_ns, stat.st_ctime_ns)
        cached = _loaded.get(acronym)
        if cached is not None and cached[0] == stamp:
            return cached[1]

        packed = source.read_bytes()
        digest = hashlib.sha256(packed).hexdigest()
        terms = ormsgpack.unpackb(packed)
        folder = _INDEX_ROOT / acronym / digest
        if folder.exists() and not _complete(folder, digest):
            raise RuntimeError("Incomplete E12 index: " + str(folder))
        if not folder.exists():
            _build_index(folder, terms, digest)

        matrix_file, vectorizer_file, concept_file, lookup_file, _ = _index_files(folder)
        matrix = sparse.load_npz(matrix_file).tocsr()
        with vectorizer_file.open("rb") as handle:
            vectorizer = pickle.load(handle)
        alias_to_concept = np.load(concept_file, allow_pickle=False)
        lookup = ormsgpack.unpackb(lookup_file.read_bytes())
        if (matrix.shape[0] != len(alias_to_concept)
                or alias_to_concept.min() < 0
                or alias_to_concept.max() >= len(terms)):
            raise ValueError("E12 index and ontology terms do not match")
        labels = []
        iris = []
        for term in terms:
            labels.append(str(term.get("label") or ""))
            iris.append(str(term.get("iri") or ""))
        state = {
            "matrix": matrix,
            "transpose": matrix.T.tocsr(),
            "vectorizer": vectorizer,
            "alias_to_concept": alias_to_concept,
            "lookup": lookup,
            "terms": terms,
            "labels": labels,
            "iris": iris,
        }
        _loaded[acronym] = (stamp, state)
        return state


def _ranked_concepts(state, scores, top_n):
    positive = np.flatnonzero(scores > 0)
    if positive.size == 0:
        return []
    labels, iris = state["labels"], state["iris"]

    def sort_key(index):
        return (-float(scores[index]), labels[index], iris[index])

    if positive.size > _PARTITION and top_n <= _PARTITION:
        positive_scores = scores[positive]
        partition = np.argpartition(-positive_scores, _PARTITION - 1)
        selected = partition[:_PARTITION]
        part = positive[selected]
        ordered = sorted(part.tolist(), key=sort_key)
        cut = min(top_n, len(ordered))
        # Fall back to a full sort when a tied score may cross the cutoff.
        if float(scores[ordered[cut - 1]]) > float(scores[part].min()):
            return ordered[:top_n]
    return sorted(positive.tolist(), key=sort_key)[:top_n]


def _result(term, score, acronym, exact):
    return {
        "Ontology Name": acronym,
        "Preferred Label": term.get("label", ""),
        "Definition": term.get("definition", "No definition available"),
        "Synonyms": list(term.get("synonyms") or []),
        "Ontology URI": "https://bioportal.bioontology.org/ontologies/" + acronym,
        "Ontology Term URI": term.get("iri", "N/A"),
        "Mapping Score": float(score),
        "_exact_match": exact,
    }


def _finish(state, acronym, text, alias_scores, top_n):
    if not text:
        return []
    scores = np.zeros(len(state["terms"]), dtype=alias_scores.dtype)
    np.maximum.at(scores, state["alias_to_concept"], alias_scores)
    terms = state["terms"]
    base = []
    ranked = _ranked_concepts(state, scores, top_n)
    for index in ranked:
        base.append(_result(terms[index], scores[index], acronym, False))

    hits = state["lookup"].get(text) or []
    if not hits:
        return base[:top_n]
    def exact_sort_key(index):
        return (-float(scores[index]), state["labels"][index], state["iris"][index])

    exact = sorted(hits, key=exact_sort_key)
    seen = set()
    front = []
    for index in exact:
        term = terms[index]
        iri = term.get("iri", "N/A")
        if iri not in seen:
            seen.add(iri)
            front.append(_result(term, scores[index], acronym, True))
    tail = []
    for row in base:
        if row["Ontology Term URI"] not in seen:
            tail.append(row)
    return (front + tail)[:top_n]


def _empty_results(count):
    output = []
    for _ in range(count):
        output.append([])
    return output


def search_many(acronym, texts, top_n=10, batch_size=32):
    """Search one ontology, scoring distinct inputs in bounded batches."""
    if top_n < 1 or batch_size < 1:
        raise ValueError("top_n and batch_size must be positive")
    prepared = []
    for text in texts:
        if text is None:
            prepared.append("")
        else:
            prepared.append(str(text).strip())
    if not prepared:
        return []
    if not any(prepared):
        return _empty_results(len(prepared))
    state = load_index(acronym)
    if state is None:
        return _empty_results(len(prepared))

    distinct = []
    seen = set()
    for text in prepared:
        if text and text not in seen:
            distinct.append(text)
            seen.add(text)
    results = {}
    for start in range(0, len(distinct), batch_size):
        chunk = distinct[start:start + batch_size]
        queries = state["vectorizer"].transform(chunk)
        queries, target = check_pairwise_arrays(queries, state["matrix"])
        if target is not state["matrix"]:
            raise RuntimeError("The E12 matrix changed during scoring")
        block = safe_sparse_dot(queries, state["transpose"], dense_output=True)
        for text, alias_scores in zip(chunk, block):
            results[text] = _finish(state, acronym, text, alias_scores, top_n)

    output = []
    for text in prepared:
        if text:
            output.append(copy.deepcopy(results[text]))
        else:
            output.append([])
    return output


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Prepare E12 indexes from installed ontology terms")
    parser.add_argument("acronyms", nargs="+", help="Only these installed ontologies are prepared")
    args = parser.parse_args()
    for acronym in args.acronyms:
        state = load_index(acronym)
        if state is None:
            parser.error("No installed terms for " + acronym)
        print("%s: %d concepts, %d aliases" % (
            acronym, len(state["terms"]), state["matrix"].shape[0]))


if __name__ == "__main__":
    main()
