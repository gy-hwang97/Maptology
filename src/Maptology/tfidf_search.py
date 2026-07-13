"""
Local TF-IDF Search Module
Replaces BioPortal API calls with local precomputed TF-IDF search.
"""

import os
import pickle
import ormsgpack
import pandas as pd
from scipy import sparse
from sklearn.metrics.pairwise import linear_kernel


# Path settings. Resolved against the repo root (this file lives in
# src/Maptology/) rather than the current working directory, so the caches are
# found no matter which directory the app is launched from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(_REPO_ROOT, "tfidf_cache")
TSV_FILE = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_list.tsv")


# ============================================================
# Load ontology list from TSV file (replaces BioPortal API)
# ============================================================

def get_ontology_list_from_tsv():
    """
    Read ontology list from local TSV file.
    Returns a list of dictionaries with acronym, name, description.
    This replaces the BioPortal API call in get_available_ontologies().
    """
    if not os.path.exists(TSV_FILE):
        print("Error: TSV file not found at " + TSV_FILE)
        return []

    df = pd.read_csv(TSV_FILE, sep="\t")

    ontology_list = []
    for i in range(len(df)):
        row = df.iloc[i]
        acronym = str(row["abbreviation"])
        name = str(row["name"])

        # Only include ontologies that have a TF-IDF cache built
        cache_folder = os.path.join(CACHE_DIR, acronym)
        if os.path.exists(cache_folder):
            entry = {}
            entry["acronym"] = acronym
            entry["name"] = name
            entry["description"] = ""
            ontology_list.append(entry)

    # Sort alphabetically by acronym
    ontology_list.sort(key=lambda x: x["acronym"])

    return ontology_list


# ============================================================
# Cache for loaded TF-IDF data (avoid reloading same ontology)
# ============================================================

_loaded_ontologies = {}


def _load_ontology_data(acronym):
    """
    Load precomputed TF-IDF files for one ontology.
    Uses an in-memory cache so we don't reload the same files.
    """
    # Check if already loaded
    if acronym in _loaded_ontologies:
        return _loaded_ontologies[acronym]

    folder = os.path.join(CACHE_DIR, acronym)

    # Check if cache exists
    matrix_path = os.path.join(folder, acronym + "_tfidf_matrix.npz")
    vectorizer_path = os.path.join(folder, acronym + "_vectorizer.pkl")
    terms_path = os.path.join(folder, acronym + "_terms.ormsgpack")

    # If ormsgpack file doesn't exist, try JSON as fallback
    if not os.path.exists(terms_path):
        terms_path_json = os.path.join(folder, acronym + "_terms.json")
        if os.path.exists(terms_path_json):
            terms_path = terms_path_json

    if not os.path.exists(matrix_path):
        return None
    if not os.path.exists(vectorizer_path):
        return None
    if not os.path.exists(terms_path):
        return None

    # Load TF-IDF matrix
    tfidf_matrix = sparse.load_npz(matrix_path)

    # Load vectorizer
    f = open(vectorizer_path, "rb")
    vectorizer = pickle.load(f)
    f.close()

    # Load terms (ormsgpack or JSON)
    if terms_path.endswith(".ormsgpack"):
        f = open(terms_path, "rb")
        terms = ormsgpack.unpackb(f.read())
        f.close()
    else:
        import json
        f = open(terms_path, "r", encoding="utf-8")
        terms = json.load(f)
        f.close()

    # Store in cache
    data = {}
    data["tfidf_matrix"] = tfidf_matrix
    data["vectorizer"] = vectorizer
    data["terms"] = terms

    _loaded_ontologies[acronym] = data

    return data


# ============================================================
# Look up a single term by its IRI (used by mapping re-import)
# ============================================================

def get_term_by_iri(acronym, iri):
    """Return the cached term dict (label, iri, synonyms, definition) for one
    IRI within the given ontology, or None if not found.

    Builds a per-ontology IRI index on first use so repeated lookups are O(1).
    Used on import to refresh a saved mapping's label/definition from the
    current local OWL cache rather than trusting possibly-outdated file values.
    """
    if not acronym or not iri:
        return None
    data = _load_ontology_data(acronym)
    if data is None:
        return None
    index = data.get("iri_index")
    if index is None:
        index = {}
        for term in data["terms"]:
            term_iri = term.get("iri")
            if term_iri and term_iri not in index:
                index[term_iri] = term
        data["iri_index"] = index
    return index.get(iri)


# ============================================================
# Main search function (replaces BioPortal API search)
# ============================================================

def search_local(search_term, selected_ontologies, top_n=10):
    """
    Search for a term across selected ontologies using precomputed TF-IDF.

    Parameters:
        search_term: string to search for (e.g. "gender")
        selected_ontologies: list of ontology acronyms (e.g. ["NCIT", "EFO"])
        top_n: number of results per ontology

    Returns:
        pandas DataFrame with columns:
            Ontology Name, Preferred Label, Definition,
            Ontology URI, Ontology Term URI
        Returns None if no results found.
    """
    if not search_term:
        return None

    if not selected_ontologies:
        return None

    search_term = str(search_term).strip()
    if len(search_term) == 0:
        return None

    all_results = []

    # Search each selected ontology
    for acronym in selected_ontologies:
        # Load precomputed data
        data = _load_ontology_data(acronym)

        if data is None:
            continue

        tfidf_matrix = data["tfidf_matrix"]
        vectorizer = data["vectorizer"]
        terms = data["terms"]

        # Convert search term to vector
        query_vector = vectorizer.transform([search_term])

        # Compute cosine similarity
        scores = linear_kernel(query_vector, tfidf_matrix)
        score_array = scores[0]

        # Get top N indices
        sorted_indices = score_array.argsort()[::-1]
        top_indices = sorted_indices[:top_n]

        # Build results
        for idx in top_indices:
            score = score_array[idx]

            if score <= 0:
                continue

            term = terms[idx]

            label = term.get("label", "")
            if not label:
                continue

            definition = term.get("definition", "No definition available")
            iri = term.get("iri", "N/A")
            synonyms = term.get("synonyms", []) or []

            result = {}
            result["Ontology Name"] = acronym
            result["Preferred Label"] = label
            result["Definition"] = definition
            result["Synonyms"] = synonyms
            result["Ontology URI"] = "https://bioportal.bioontology.org/ontologies/" + acronym
            result["Ontology Term URI"] = iri
            # Keep the RAW similarity as the sort key. Rounding here (e.g. to 3
            # decimals) would create artificial ties that then get ordered by
            # Preferred Label, which can change the Top-10 boundary. The score is
            # never displayed, so there is no reason to round it.
            result["Mapping Score"] = float(score)

            all_results.append(result)

    if len(all_results) == 0:
        return None

    # Create DataFrame
    df_results = pd.DataFrame(all_results)

    # Sort by score (descending), then by Preferred Label
    df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])

    # Remove the score column (not needed for display, matches BioPortal format)
    # Actually keep it - it can be useful
    # df_results = df_results.drop(columns=["Mapping Score"])

    return df_results