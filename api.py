import streamlit as st
import pandas as pd
from tfidf_search import search_local


# Manual search function for columns - search within selected ontologies
def manual_search_ontology(search_term):
    if not search_term:
        return False

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = search_term.strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.ontology_results = df_results
        st.session_state.filtered_ontology_results = df_results
        return True
    else:
        return False


# Manual search function for values - search within selected ontologies
def manual_search_value(search_term):
    if not search_term:
        return False

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = str(search_term).strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.value_ontology_results = df_results
        return True
    else:
        return False