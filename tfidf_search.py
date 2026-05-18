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


# Path settings
CACHE_DIR = "tfidf_cache"
TSV_FILE = "ontology_cache/ontology_list.tsv"


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
            result["Mapping Score"] = round(score, 3)

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