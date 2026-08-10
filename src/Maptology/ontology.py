import streamlit as st
import pandas as pd
from tfidf_search import get_ontology_list_from_tsv, search_local
from ontology_setup import catalogue_entries, recorded_submissions, install_ontology


# Load the ontology catalog once per server process.
# @st.cache_data computes it a single time and shares the result across every
# session, rerun, and user; it is cleared explicitly when a new ontology is
# downloaded, which is the only time it changes.
@st.cache_data(show_spinner=False)
def _load_ontology_catalog():
    """Everything the selection list can offer.

    Two sources, merged: ontologies already downloaded and indexed on this
    machine, and the saved BioPortal catalogue, so an ontology can be chosen
    before it is downloaded - selecting it is what downloads it. Each entry
    carries `downloaded`, and `update_available` when the local index was built
    from an older BioPortal submission than the catalogue now offers.
    """
    built = {o["acronym"]: o for o in get_ontology_list_from_tsv()}
    catalogue = catalogue_entries()
    recorded = recorded_submissions()

    merged = []
    for acronym, entry in catalogue.items():
        downloaded = acronym in built
        merged.append({
            "acronym": acronym,
            "name": entry.get("name") or acronym,
            "description": "",
            "downloaded": downloaded,
            "update_available": downloaded
                and recorded.get(acronym) != entry.get("submissionId"),
        })
    # Ontologies built locally that BioPortal no longer lists (this happens:
    # CMEO, CVO and HTO were withdrawn from its catalogue). They keep working;
    # there is just nothing to update them from.
    for acronym, entry in built.items():
        if acronym not in catalogue:
            merged.append({
                "acronym": acronym,
                "name": entry.get("name") or acronym,
                "description": "",
                "downloaded": True,
                "update_available": False,
            })
    merged.sort(key=lambda x: x["acronym"])
    return merged


# Get list of available ontologies (local caches merged with the saved
# BioPortal catalogue; replaces the old per-request BioPortal API call)
def get_available_ontologies():
    if not st.session_state.available_ontologies:
        ontology_list = _load_ontology_catalog()

        if len(ontology_list) > 0:
            st.session_state.available_ontologies = ontology_list
        else:
            st.error("Error: no ontologies are available yet. Set "
                     "BIOPORTAL_APIKEY and restart Maptology to fetch the "
                     "BioPortal catalogue.")
            st.session_state.available_ontologies = []

    return st.session_state.available_ontologies


# Get ontology details (name, acronym) from local TSV file
# (replaces BioPortal API call)
def get_ontology_details(ontology_acronym):
    # Check session cache first
    if ontology_acronym in st.session_state.ontology_details_cache:
        return st.session_state.ontology_details_cache[ontology_acronym]

    # Look up from available ontologies list
    full_name = ontology_acronym
    for ont in st.session_state.available_ontologies:
        if ont["acronym"] == ontology_acronym:
            full_name = ont["name"]
            break

    # Cache the result
    st.session_state.ontology_details_cache[ontology_acronym] = {
        "full_name": full_name,
        "acronym": ontology_acronym
    }

    return st.session_state.ontology_details_cache[ontology_acronym]


# Search ontology for column mapping - search within selected ontologies
# (replaces BioPortal API search)
def search_ontology(selected_column):
    if not selected_column:
        return

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None
        return

    # Clean up search term
    search_term = selected_column.strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.ontology_results = df_results
        # The auto-suggestion list shows the TOP 10 overall. search_local returns
        # up to 10 PER ontology, so with several ontologies selected the combined
        # set is larger - keep only the 10 best distinct terms.
        st.session_state.filtered_ontology_results = (
            df_results.drop_duplicates(subset=["Ontology Term URI"], keep="first").head(10)
        )

        # Reset selected term index if it's out of range
        if (st.session_state.selected_term_index is not None and
            st.session_state.selected_term_index >= len(df_results)):
            st.session_state.selected_term_index = None
    else:
        # Automatic search: no match is not an error - stay silent so users
        # are not told "no results" for a search they did not run. They can
        # still type keywords in the manual search box.
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None


# Search ontology for value mapping - search within selected ontologies
# (replaces BioPortal API search)
def search_ontology_for_value(selected_value):
    if not selected_value:
        return

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        st.session_state.value_ontology_results = None
        return

    # Clean up search term
    search_term = str(selected_value).strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        # Auto-suggestion list: keep only the top 10 overall (see search_ontology).
        st.session_state.value_ontology_results = (
            df_results.drop_duplicates(subset=["Ontology Term URI"], keep="first").head(10)
        )
    else:
        # Automatic value search: stay silent on no match (see search_ontology).
        st.session_state.value_ontology_results = None


# Search all selected ontologies for column terms
# (replaces search_bioportal_all_columns)
def search_bioportal_all_columns(search_term):
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
        st.session_state.ontology_results = df_results
        st.session_state.filtered_ontology_results = df_results

        # Reset selection
        st.session_state.selected_terms = []

        return True
    else:
        return False


# Search all selected ontologies for value terms
# (replaces search_bioportal_all)
def search_bioportal_all(search_term):
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

        # Reset selection
        st.session_state.value_term_indices = []

        return True
    else:
        return False


# Manual search for value mapping
# (replaces search_bioportal_manual_value)
def search_bioportal_manual_value(search_term):
    if not search_term:
        return False

    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = str(search_term).strip()

    # Search using local TF-IDF. Fetch more per ontology (top_n=20) so that after
    # we drop terms already shown in the auto list, enough candidates remain to
    # show ~10.
    df_results = search_local(search_term, st.session_state.selected_ontologies, top_n=20)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.manual_value_search_results = df_results
        st.session_state.manual_value_selected_indices = []
        return True
    else:
        st.session_state.manual_value_search_results = None
        return False


# Manual search for column mapping
# (replaces search_bioportal_manual_column)
def search_bioportal_manual_column(search_term):
    if not search_term:
        return False

    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = str(search_term).strip()

    # Search using local TF-IDF. Fetch more per ontology (top_n=20) so that after
    # we drop terms already shown in the auto list, enough candidates remain to
    # show ~10.
    df_results = search_local(search_term, st.session_state.selected_ontologies, top_n=20)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.manual_column_search_results = df_results
        st.session_state.manual_column_selected_terms = []
        return True
    else:
        st.session_state.manual_column_search_results = None
        return False


# Ontology deselection function (for Select None button)
def select_none_ontologies():
    st.session_state.selected_ontologies = []
    st.session_state.ontologies_changed = True
    # Programmatic change -> refresh the ontology checkboxes so they don't keep
    # their stale (checked) widget state.
    st.session_state.ontology_widget_version = st.session_state.get("ontology_widget_version", 0) + 1
    st.rerun()


# Render ontology selection section (UI - mostly unchanged)
def render_ontology_selection(available_ontologies):
    st.markdown('<div class="section-header section-purple">Select Ontologies</div>', unsafe_allow_html=True)

    # Select None button and Selected ontologies on same row
    btn_col, info_col = st.columns([1, 4])

    with btn_col:
        if st.button("Select None", key="btn_select_none"):
            select_none_ontologies()

    with info_col:
        current_count = len(st.session_state.selected_ontologies)
        max_count = 10
        if st.session_state.selected_ontologies:
            selected_text = ", ".join(st.session_state.selected_ontologies)
            st.markdown("**Selected ontologies (" + str(current_count) + "/" + str(max_count) + "):** " + selected_text)
        else:
            st.warning("Please select at least one ontology to proceed.")

    # A download attempted on the previous rerun may have failed; the message
    # has to survive that rerun, so it travels through session state.
    install_error = st.session_state.pop("ontology_install_error", None)
    if install_error:
        st.error(install_error)

    st.caption("Ontologies not yet on this machine are downloaded from "
               "BioPortal the first time you select them - a few seconds for "
               "most, a couple of minutes for the largest.")

    # Search filtering
    filter_query = st.text_input("Filter ontologies", placeholder="Type to filter...")

    # Filtered ontology list
    filtered_ontologies = available_ontologies
    if filter_query:
        filtered_ontologies = []
        for ont in available_ontologies:
            acronym_match = filter_query.lower() in ont["acronym"].lower()
            name_match = filter_query.lower() in ont["name"].lower()
            if acronym_match or name_match:
                filtered_ontologies.append(ont)

    # Create expandable container
    with st.expander("Ontology List", expanded=True):
        # Create scrollable area
        with st.container(height=400):
            # Create checkboxes
            for idx in range(len(filtered_ontologies)):
                ont = filtered_ontologies[idx]
                acronym = ont["acronym"]
                name = ont["name"]
                tooltip = ont.get("description", "")

                # Check checkbox state
                is_checked = acronym in st.session_state.selected_ontologies

                # Calculate currently selected count
                current_count = len(st.session_state.selected_ontologies)
                max_count = 10

                # Check maximum selection limit
                is_disabled = (current_count >= max_count and not is_checked)

                # Say up front which selections will cost a download, so the
                # wait that follows is never a surprise.
                label = acronym + " - " + name
                if not ont.get("downloaded", True):
                    label += "  (not downloaded yet)"
                elif ont.get("update_available"):
                    label += "  (update available)"

                checkbox = st.checkbox(
                    label,
                    value=is_checked,
                    key="ont_" + acronym + "_" + str(st.session_state.get("ontology_widget_version", 0)),
                    help=tooltip,
                    disabled=is_disabled
                )

                # Update checkbox state
                if checkbox and acronym not in st.session_state.selected_ontologies:
                    if len(st.session_state.selected_ontologies) < max_count:
                        # Lazy loading: selecting an ontology is what fetches
                        # it. Also refreshes one whose BioPortal submission has
                        # moved on since it was built.
                        if not ont.get("downloaded", True) or ont.get("update_available"):
                            verb = ("Updating" if ont.get("downloaded", True)
                                    else "Downloading")
                            with st.spinner(verb + " " + acronym + " from "
                                            "BioPortal... large ontologies can "
                                            "take a few minutes."):
                                ok, message = install_ontology(acronym)
                            if not ok:
                                # Reset the checkbox (a version bump rebuilds
                                # every widget) and surface the reason after
                                # the rerun.
                                st.session_state.ontology_install_error = message
                                st.session_state.ontology_widget_version = \
                                    st.session_state.get("ontology_widget_version", 0) + 1
                                st.rerun()
                            # The catalog changed on disk; drop both caches so
                            # the entry shows up as downloaded from now on.
                            _load_ontology_catalog.clear()
                            st.session_state.available_ontologies = []
                        st.session_state.selected_ontologies.append(acronym)
                        st.session_state.ontologies_changed = True
                        st.rerun()
                    else:
                        st.error("Cannot select more than " + str(max_count) + " ontologies")
                elif not checkbox and acronym in st.session_state.selected_ontologies:
                    st.session_state.selected_ontologies.remove(acronym)
                    st.session_state.ontologies_changed = True
                    st.rerun()

                # Description for disabled checkboxes
                if is_disabled:
                    st.caption("Remove other selections to enable this option")

    # When the selected ontologies change, previous manual search results may be
    # from ontologies that are no longer selected - clear them so stale results
    # don't linger (e.g. NCIT results still showing after NCIT was deselected).
    if st.session_state.ontologies_changed:
        st.session_state.manual_column_search_results = None
        st.session_state.manual_value_search_results = None

    # Automatically execute search if ontology changed and column is selected
    if st.session_state.ontologies_changed and st.session_state.selected_column and st.session_state.selected_ontologies:
        search_ontology(st.session_state.selected_column)

        # Also perform automatic search for value mapping
        if st.session_state.selected_unique_value:
            search_ontology_for_value(st.session_state.selected_unique_value)

        # Reset flag
        st.session_state.ontologies_changed = False