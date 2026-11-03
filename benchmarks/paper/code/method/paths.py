"""Asset locations for the search code in this folder.

Set MAPTOLOGY_BENCHMARK_ASSETS to the existing testing folder. The sizes and
SHA-256 hashes of required files are in records/required-assets.tsv.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TESTING = os.environ.get("MAPTOLOGY_BENCHMARK_ASSETS")
if not TESTING:
    TESTING = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
TESTING = os.path.abspath(TESTING)

FROZEN_INDEX = os.path.join(TESTING, "published-benchmark-accuracy", "run-2026-10-16-1159", "cache", "EFO")
FROZEN_TERMS = os.path.join(FROZEN_INDEX, "EFO_terms.ormsgpack")
FROZEN_LOOKUP = os.path.join(os.path.dirname(FROZEN_INDEX), "exact-lookup-EFO.json")

RANKING_RUN = os.path.join(TESTING, "ranking-experiments-20261021-034704")
INDEX = os.path.join(RANKING_RUN, "index")
T2T_CACHE = os.path.join(RANKING_RUN, "cache", "t2t")

ONTOLOGY = "EFO"
TOP_N = 5
BASE_IRIS = ("http://www.ebi.ac.uk/efo/",
             "http://purl.obolibrary.org/obo/MONDO",
             "http://purl.obolibrary.org/obo/HP",
             "http://www.orpha.net/ORDO",
             "http://purl.obolibrary.org/obo/DOID")
INDEX_OF = {
    "A": "word-merged",
    "B2": "word-merged",
    "E1": "word-separate",
    "E2": "char-merged",
    "E12": "char-separate",
}


def index_dir(kind):
    return os.path.join(INDEX, kind)
