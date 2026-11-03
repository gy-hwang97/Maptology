"""Search functions for A, B2, E1, E2, E12 and the text2term adapter.

A and B2 use the same candidate selection, positive-score rule, tie-break,
and merge order as the archived accuracy benchmark. They read its frozen
word-merged index.

E1 / E2 / E12 read the indexes built by build_indexes.py. Their candidate rule
is fixed in protocol.md section 2: every concept with score > 0, ordered by
(-score, label, iri), cut at TOP_N, then the same exact-match-first merge as
B2 using the shared frozen lookup (string -> concept row numbers).

For the separate-alias indexes the alias-row scores are aggregated to the
concept by MAXIMUM over all alias rows (no truncation before aggregation).

Counters: CALLS counts transform / linear_kernel / vectorizer fit calls; they
are only switched on by the verification step, never while timing.
"""
import json
import os
import pickle

import numpy as np
import ormsgpack
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

import paths

CALLS = dict(transform=0, linear_kernel=0, fit=0, fit_transform=0)
_COUNTING = False
_ORIG_FIT, _ORIG_FIT_TRANSFORM = TfidfVectorizer.fit, TfidfVectorizer.fit_transform


def instrument(on=True):
    """Count calls (verification only). Also counts any vectorizer fit."""
    global _COUNTING
    _COUNTING = on
    CALLS.update(transform=0, linear_kernel=0, fit=0, fit_transform=0)
    if on:
        def fit(self, *a, **k):
            CALLS["fit"] += 1
            return _ORIG_FIT(self, *a, **k)

        def fit_transform(self, *a, **k):
            CALLS["fit_transform"] += 1
            return _ORIG_FIT_TRANSFORM(self, *a, **k)
        TfidfVectorizer.fit, TfidfVectorizer.fit_transform = fit, fit_transform
    else:
        TfidfVectorizer.fit, TfidfVectorizer.fit_transform = _ORIG_FIT, _ORIG_FIT_TRANSFORM


# ------------------------------------------------------------------- loaders
def load_terms():
    with open(paths.FROZEN_TERMS, "rb") as fh:
        return ormsgpack.unpackb(fh.read())


def load_lookup():
    """B2 / E1 / E2 / E12 only: string (strip only) -> concept row numbers."""
    with open(paths.FROZEN_LOOKUP, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_index(kind):
    """kind in word-merged | word-separate | char-merged | char-separate.

    word-merged is the frozen accuracy-run index (A and B2). The others come
    from this run's index/ folder. Every state carries the concept terms in
    the frozen order, plus label/iri arrays for the explicit tie rule."""
    folder = paths.index_dir(kind)
    prefix = kind
    if kind == "word-merged":
        folder = paths.FROZEN_INDEX
        prefix = "EFO"
    matrix = sparse.load_npz(os.path.join(folder, "%s_tfidf_matrix.npz" % prefix))
    with open(os.path.join(folder, "%s_vectorizer.pkl" % prefix), "rb") as fh:
        vectorizer = pickle.load(fh)
    terms = load_terms()
    state = dict(kind=kind, matrix=matrix, vectorizer=vectorizer, terms=terms,
                 separate=kind.endswith("separate"))
    if state["separate"]:
        state["alias_to_concept"] = np.load(os.path.join(folder, "%s_alias_to_concept.npy" % prefix))
        assert state["alias_to_concept"].shape[0] == matrix.shape[0]
    else:
        assert matrix.shape[0] == len(terms)
    labels = []
    iris = []
    for term in terms:
        labels.append(str(term.get("label") or ""))
        iris.append(str(term.get("iri") or ""))
    state["labels"] = labels
    state["iris"] = iris
    return state


# ---------------------------------------------------------------- A and B2
def _row(term, score):
    return {"Preferred Label": term.get("label", ""),
            "Ontology Term URI": term.get("iri", "N/A"),
            "Mapping Score": float(score)}


def _key(terms, index):
    t = terms[index]
    return (str(t.get("label") or ""), str(t.get("iri") or ""))


def search_A(state, text, top_n=paths.TOP_N):
    """Verbatim app path: transform, linear_kernel, argsort, score>0, final sort."""
    text = str(text).strip()
    if not text:
        return [], None
    query_vector = state["vectorizer"].transform([text])
    if _COUNTING:
        CALLS["transform"] += 1
    scores = linear_kernel(query_vector, state["matrix"])
    if _COUNTING:
        CALLS["linear_kernel"] += 1
    score_array = scores[0]

    rows = []
    for idx in score_array.argsort()[::-1][:top_n]:
        score = score_array[idx]
        if score <= 0:
            continue
        term = state["terms"][idx]
        if not term.get("label", ""):
            continue
        rows.append(_row(term, score))
    if rows:
        rows = pd.DataFrame(rows).sort_values(
            by=["Mapping Score", "Preferred Label"], ascending=[False, True]).to_dict("records")
    return rows, score_array


def search_B2(state, lookup, text, top_n=paths.TOP_N):
    text = str(text).strip()
    diag = dict(exact_rows=0, ambiguous=False, zero_score_added=0)
    if not text:
        return [], diag
    base_rows, score_array = search_A(state, text, top_n)

    hits = lookup.get(text) or []
    diag["exact_rows"] = len(hits)
    diag["ambiguous"] = len(hits) > 1
    if not hits:
        return base_rows[:top_n], diag

    terms = state["terms"]
    def exact_order(index):
        return (-float(score_array[index]),) + _key(terms, index)

    exact = sorted(hits, key=exact_order)
    seen, front = set(), []
    for index in exact:
        term = terms[index]
        iri = term.get("iri", "N/A")
        if iri in seen:
            continue
        seen.add(iri)
        score = float(score_array[index])
        if score <= 0:
            diag["zero_score_added"] += 1
        row = _row(term, score)
        row["exact_match"] = True
        front.append(row)

    tail = []
    for row in base_rows:
        if row["Ontology Term URI"] in seen:
            continue
        row = dict(row)
        row["exact_match"] = False
        tail.append(row)
    return (front + tail)[:top_n], diag


# ------------------------------------------------------------ E1 / E2 / E12
PARTITION = 200


def concept_scores_for(state, text):
    """Query -> score per concept (max over alias rows for separate indexes)."""
    query_vector = state["vectorizer"].transform([text])
    if _COUNTING:
        CALLS["transform"] += 1
    scores = linear_kernel(query_vector, state["matrix"])[0]
    if _COUNTING:
        CALLS["linear_kernel"] += 1
    if not state["separate"]:
        return scores
    concept = np.zeros(len(state["terms"]), dtype=scores.dtype)
    np.maximum.at(concept, state["alias_to_concept"], scores)
    return concept


def ranked_concepts(state, concept_scores, top_n=paths.TOP_N):
    """Concepts with score > 0 ordered by (-score, label, iri); first top_n.

    Exact: a partition of the top PARTITION scores is sorted with the full
    key; if the top_n-th score ties with the smallest partitioned score the
    full sort is used instead, so no tie can be cut off by the partition."""
    positive = np.flatnonzero(concept_scores > 0)
    if positive.size == 0:
        return []
    labels, iris = state["labels"], state["iris"]

    def key(i):
        return (-float(concept_scores[i]), labels[i], iris[i])

    if positive.size > PARTITION:
        part = positive[np.argpartition(-concept_scores[positive], PARTITION - 1)[:PARTITION]]
        ordered = sorted(part.tolist(), key=key)
        cut = min(top_n, len(ordered))
        floor = float(concept_scores[part].min())
        if float(concept_scores[ordered[cut - 1]]) > floor:
            return ordered[:top_n]
    ordered = sorted(positive.tolist(), key=key)
    return ordered[:top_n]


def search_E(state, lookup, text, top_n=paths.TOP_N):
    """E1 / E2 / E12: ranked concepts + B2-style exact-match-first merge."""
    text = str(text).strip()
    diag = dict(exact_rows=0, ambiguous=False, zero_score_added=0, positive=0)
    if not text:
        return [], diag
    concept_scores = concept_scores_for(state, text)
    diag["positive"] = int((concept_scores > 0).sum())
    terms = state["terms"]
    ranked = ranked_concepts(state, concept_scores, top_n)
    base_rows = []
    for i in ranked:
        row = _row(terms[i], concept_scores[i])
        row["exact_match"] = False
        base_rows.append(row)

    hits = lookup.get(text) or []
    diag["exact_rows"] = len(hits)
    diag["ambiguous"] = len(hits) > 1
    if not hits:
        return base_rows[:top_n], diag
    def exact_order(index):
        return (-float(concept_scores[index]),) + _key(terms, index)

    exact = sorted(hits, key=exact_order)
    seen, front = set(), []
    for index in exact:
        term = terms[index]
        iri = term.get("iri", "N/A")
        if iri in seen:
            continue
        seen.add(iri)
        score = float(concept_scores[index])
        if score <= 0:
            diag["zero_score_added"] += 1
        row = _row(term, score)
        row["exact_match"] = True
        front.append(row)
    tail = []
    for row in base_rows:
        if row["Ontology Term URI"] not in seen:
            tail.append(row)
    return (front + tail)[:top_n], diag


# -------------------------------------------------------- unified interface
def search(condition, state, lookup, text):
    if condition == "A":
        rows, _ = search_A(state, text)
        result = []
        for row in rows:
            result.append(dict(row, exact_match=False))
        return result, dict(exact_rows=0, ambiguous=False)
    if condition == "B2":
        return search_B2(state, lookup, text)
    if condition in ("E1", "E2", "E12"):
        return search_E(state, lookup, text)
    raise ValueError(condition)


def load_for(condition):
    """(state, lookup) for a Maptology-side condition. A never loads the lookup."""
    state = load_index(paths.INDEX_OF[condition])
    lookup = None
    if condition != "A":
        lookup = load_lookup()
    return state, lookup


# ----------------------------------------------------------------- text2term
def t2t_map(strings, ids, cache_folder=None):
    """One official map_terms call against the cache built in this run."""
    import text2term
    from text2term import Mapper
    folder = paths.T2T_CACHE
    if cache_folder:
        folder = cache_folder
    return text2term.map_terms(
        source_terms=list(strings), source_terms_ids=list(ids),
        target_ontology=paths.ONTOLOGY, use_cache=True, cache_folder=folder,
        base_iris=paths.BASE_IRIS, excl_deprecated=True,
        max_mappings=paths.TOP_N, min_score=0.0, mapper=Mapper.TFIDF,
        save_mappings=False, save_graphs=False)


def t2t_relink(frame, ids, strings):
    """Attach candidates to every requested row by exact input string.

    text2term 4.5.0 groups on the source STRING, so a repeated string's later
    id can come back empty while its candidates sit on an earlier id. Repair
    by exact string equality (strip only), keep first order, drop duplicate
    IRIs, cap at TOP_N. Disagreeing outputs for one string are a conflict,
    never resolved by picking one. Returns (id, iris, scores, status, note)."""
    col = "Mapped Term CURIE"
    if "Mapped Term IRI" in frame.columns:
        col = "Mapped Term IRI"
    by_key_id = {}
    if len(frame):
        keys = frame["Source Term"].astype(str).str.strip()
        sids = frame["Source Term ID"].astype(str)
        for key, sid, iri, score in zip(keys, sids, frame[col].astype(str), frame["Mapping Score"]):
            by_key_id.setdefault(key, {}).setdefault(sid, []).append((iri, float(score)))

    def dedupe(pairs):
        seen, out = set(), []
        for iri, score in pairs:
            if iri in seen:
                continue
            seen.add(iri)
            out.append((iri, score))
            if len(out) == paths.TOP_N:
                break
        return out

    results = []
    for rid, text in zip(ids, strings):
        key = str(text).strip()
        variants = by_key_id.get(key, {})
        own = variants.get(str(rid))
        if own:
            cands = dedupe(own)
            iris = []
            scores = []
            for iri, score in cands:
                iris.append(iri)
                scores.append(score)
            results.append((str(rid), iris, scores, "own_id", ""))
        elif variants:
            lists = {}
            for key_id, values in variants.items():
                lists[key_id] = dedupe(values)
            distinct = set()
            for values in lists.values():
                iris = []
                for iri, _ in values:
                    iris.append(iri)
                distinct.add(tuple(iris))
            if len(distinct) == 1:
                donor = sorted(lists)[0]
                cands = lists[donor]
                iris = []
                scores = []
                for iri, score in cands:
                    iris.append(iri)
                    scores.append(score)
                results.append((str(rid), iris, scores, "recovered_same_string", donor))
            else:
                messages = []
                for key_id, values in sorted(lists.items()):
                    iris = []
                    for iri, _ in values:
                        iris.append(iri)
                    messages.append("%s:%s" % (key_id, ",".join(iris)))
                results.append((str(rid), [], [], "conflicting_outputs", " || ".join(messages)))
        else:
            results.append((str(rid), [], [], "absent_from_output", ""))
    return results
