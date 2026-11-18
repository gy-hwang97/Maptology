import os

HERE = os.path.dirname(os.path.abspath(__file__))
TESTING = os.environ.get("MAPTOLOGY_BENCHMARK_ASSETS")
if not TESTING:
    TESTING = os.path.join(os.path.dirname(os.path.dirname(HERE)), "assets")
TESTING = os.path.abspath(TESTING)

FROZEN_INDEX = os.path.join(TESTING, "published-benchmark-accuracy", "run-2026-10-16-1159", "cache", "EFO")
FROZEN_TERMS = os.path.join(FROZEN_INDEX, "EFO_terms.ormsgpack")
FROZEN_LOOKUP = os.path.join(os.path.dirname(FROZEN_INDEX), "exact-lookup-EFO.json")

RANKING_RUN = os.path.join(TESTING, "ranking-experiments-20261021-034704")
INDEX = os.path.join(RANKING_RUN, "index")
T2T_CACHE = os.path.join(RANKING_RUN, "cache", "t2t")

if os.path.isfile(os.path.join(TESTING, "asset-manifest.json")):
    FROZEN_INDEX = os.path.join(TESTING, "EFO")
    FROZEN_TERMS = os.path.join(FROZEN_INDEX, "EFO_terms.ormsgpack")
    FROZEN_LOOKUP = os.path.join(TESTING, "exact-lookup-EFO.json")
    INDEX = os.path.join(TESTING, "index")
    T2T_CACHE = os.path.join(TESTING, "t2t")

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
