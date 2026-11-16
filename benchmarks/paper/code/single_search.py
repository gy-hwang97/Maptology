import sys
import time
from pathlib import Path

import numpy as np
from text2term import t2t
from text2term.term import OntologyTermType
from text2term.tfidf_mapper import TFIDFMapper


sys.path.insert(0, str(Path(__file__).resolve().parent / "method"))
import engines
import paths
from optimized import OptimizedE12


def prepare_method(method, costs=None):
    start = time.perf_counter()
    if method == "E12":
        state, lookup = engines.load_for("E12")
        if len(set(state["iris"])) != 29374:
            raise RuntimeError("E12 does not search the expected 29,374 terms")
        e12 = OptimizedE12(state, lookup, "EFO-3.62.0-common-29374")
        if costs is not None:
            costs["E12_load_and_prepare_seconds"] = time.perf_counter() - start
        return e12
    if method != "T":
        raise ValueError("Unknown search method: " + method)
    terms = t2t._load_ontology(
        paths.ONTOLOGY, paths.BASE_IRIS, True, use_cache=True,
        term_type=OntologyTermType.CLASS, cache_folder=paths.T2T_CACHE,
    )
    maptology_iris = set()
    for term in engines.load_terms():
        maptology_iris.add(str(term["iri"]))
    text2term_iris = set()
    for iri in terms:
        text2term_iris.add(str(iri))
    if len(maptology_iris) != 29374 or maptology_iris != text2term_iris:
        raise RuntimeError("The two tools do not search the same 29,374 terms")
    mapper = TFIDFMapper(terms)
    if costs is not None:
        costs["text2term_load_filter_and_mapper_seconds"] = time.perf_counter() - start
    return mapper


def prepare(costs=None):
    e12 = prepare_method("E12", costs)
    mapper = prepare_method("T", costs)
    return e12, mapper


def search(method, text, row_id, e12, mapper):
    if method == "E12":
        return e12.single(text, top_n=5)
    frame = mapper.map([text], [row_id], max_mappings=5, min_score=0.0)
    if not frame.empty:
        frame["Mapping Score"] = frame["Mapping Score"].astype(float).round(decimals=3)
    return frame


def signature(method, output, text, row_id):
    pairs = []
    if method == "E12":
        for row in output[0]:
            pairs.append((row["Ontology Term URI"], float(row["Mapping Score"])))
    else:
        linked = engines.t2t_relink(output, [row_id], [text])
        if len(linked) != 1 or linked[0][3] == "conflicting_outputs":
            raise RuntimeError("A single search produced an invalid output")
        for iri, score in zip(linked[0][1], linked[0][2]):
            pairs.append((iri, float(score)))
    if len(pairs) > 5:
        raise RuntimeError("A search returned more than five candidates")
    return pairs


def same(first, second):
    if len(first) != len(second):
        return False
    for a, b in zip(first, second):
        if a[0] != b[0]:
            return False
        if not np.isclose(a[1], b[1], rtol=1e-12, atol=1e-12):
            return False
    return True
