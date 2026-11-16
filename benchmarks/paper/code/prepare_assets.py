import argparse
import importlib.metadata
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import ormsgpack
import text2term
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from text2term import t2t
from text2term.term import OntologyTermType

from build_inputs import download, sha256


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent.parent / "build"))
import build_all_caches

URL = "https://github.com/EBISPOT/efo/releases/download/v3.62.0/efo.owl"
OWL_HASH = "f87fc3cdbae7fac68c5b2a470ae81da59bec3fa98ada908c5262dc89edcdb0bc"
TERM_HASH = "61af9c87dd79a954b00d680ac8bb838a50719e685325b7a9ef719d09ef03188c"
BASE_IRIS = ("http://www.ebi.ac.uk/efo/", "http://purl.obolibrary.org/obo/MONDO",
             "http://purl.obolibrary.org/obo/HP", "http://www.orpha.net/ORDO",
             "http://purl.obolibrary.org/obo/DOID")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets")
    parser.add_argument("--owl", type=Path)
    args = parser.parse_args()
    folder = args.output_dir.resolve()
    manifest = folder / "asset-manifest.json"
    if manifest.exists():
        report = json.loads(manifest.read_text(encoding="utf-8"))
        for name, digest in report["files"].items():
            if sha256(folder / name) != digest:
                raise RuntimeError("Asset hash mismatch: " + name)
        print("Existing assets verified:", folder)
        return
    folder.mkdir(parents=True, exist_ok=True)
    owl = args.owl
    if owl is None:
        owl = ROOT / "sources" / "efo-v3.62.0.owl"
        download(URL, owl, OWL_HASH)
    if sha256(owl) != OWL_HASH:
        raise RuntimeError("The OWL file is not the pinned EFO 3.62.0 file")
    report = {"ontology": "EFO 3.62.0", "owl_url": URL, "owl_sha256": OWL_HASH,
              "base_iris": list(BASE_IRIS), "packages": {}, "build_seconds": {}, "files": {}}
    for name in ("text2term", "scikit-learn", "numpy", "scipy", "ormsgpack"):
        report["packages"][name] = importlib.metadata.version(name)
    start = time.perf_counter()
    cache = folder / "t2t"
    text2term.cache_ontology(str(owl), "EFO", base_iris=BASE_IRIS, cache_folder=str(cache))
    t_terms = t2t._load_ontology("EFO", BASE_IRIS, True, use_cache=True,
                               term_type=OntologyTermType.CLASS, cache_folder=str(cache))
    report["build_seconds"]["text2term_cache"] = time.perf_counter() - start
    target = set()
    for iri in t_terms:
        target.add(str(iri))
    start = time.perf_counter()
    extracted, deprecated = build_all_caches.extract_terms_streaming(str(owl))
    terms = []
    for term in extracted:
        if term["iri"] in target:
            terms.append(term)
    if len(terms) != 29374 or len(target) != 29374:
        raise RuntimeError("The expected common target contains 29,374 terms")
    terms_path = folder / "EFO" / "EFO_terms.ormsgpack"
    terms_path.parent.mkdir(parents=True, exist_ok=True)
    terms_path.write_bytes(ormsgpack.packb(terms))
    if sha256(terms_path) != TERM_HASH:
        raise RuntimeError("The rebuilt term list differs from the original benchmark")
    lookup = {}
    aliases = []
    alias_to_term = []
    documents = []
    for index, term in enumerate(terms):
        names = [term["label"]]
        names.extend(term["synonyms"])
        document = term["label"]
        if term["synonyms"]:
            document += " " + " ".join(term["synonyms"])
        documents.append(document)
        seen = set()
        for name in names:
            key = str(name).strip()
            if not key:
                continue
            if key not in lookup:
                lookup[key] = []
            if index not in lookup[key]:
                lookup[key].append(index)
            if name in seen:
                continue
            seen.add(name)
            aliases.append(str(name))
            alias_to_term.append(index)
    lookup_path = folder / "exact-lookup-EFO.json"
    lookup_path.write_text(json.dumps(lookup, ensure_ascii=False), encoding="utf-8")
    report["build_seconds"]["extract_terms_and_lookup"] = time.perf_counter() - start
    for kind in ("word-merged", "word-separate", "char-merged", "char-separate"):
        start = time.perf_counter()
        if kind.startswith("word"):
            vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), lowercase=True, stop_words="english")
        else:
            vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 3), lowercase=True)
        texts = documents
        if kind.endswith("separate"):
            texts = aliases
        matrix = vectorizer.fit_transform(texts)
        prefix = kind
        destination = folder / "index" / kind
        if kind == "word-merged":
            prefix = "EFO"
            destination = folder / "EFO"
        destination.mkdir(parents=True, exist_ok=True)
        sparse.save_npz(destination / (prefix + "_tfidf_matrix.npz"), matrix)
        with (destination / (prefix + "_vectorizer.pkl")).open("wb") as handle:
            pickle.dump(vectorizer, handle)
        if kind.endswith("separate"):
            np.save(destination / (prefix + "_alias_to_concept.npy"), np.array(alias_to_term, dtype=np.int32))
            (destination / (prefix + "_aliases.ormsgpack")).write_bytes(ormsgpack.packb(aliases))
        report["build_seconds"][kind] = time.perf_counter() - start
        print(kind, matrix.shape, flush=True)
    report["target_terms"] = len(terms)
    report["alias_rows"] = len(aliases)
    report["deprecated_excluded_by_maptology"] = deprecated
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            report["files"][path.relative_to(folder).as_posix()] = sha256(path)
    manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Prepared:", folder, flush=True)


if __name__ == "__main__":
    main()
