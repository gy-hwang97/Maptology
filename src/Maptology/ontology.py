import streamlit as st
import pandas as pd
from tfidf_search import get_ontology_list_from_tsv, search_local
from ontology_setup import (catalogue_entries, recorded_submissions,
                            install_ontology,
                            _download_all_requested as download_all_requested)


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


MAX_SELECTED_ONTOLOGIES = 10


@st.dialog("Download ontologies", width="large")
def _download_ontologies_dialog():
    """Fetch ontologies from BioPortal, one click each.

    Lists everything the saved catalogue offers that is not on this machine
    yet. Downloading lives here, in its own dialog, so the main page only ever
    deals with ontologies that are actually usable.
    """
    st.caption("These ontologies are on BioPortal but not on this machine yet. "
               "Most download in seconds; the largest take a few minutes. "
               "Downloaded ontologies appear under Available ontologies.")

    query = st.text_input("Search downloadable ontologies",
                          placeholder="Type to filter...",
                          key="download_dialog_filter")
    candidates = [o for o in get_available_ontologies()
                  if not o.get("downloaded", False)]
    if query:
        q = query.lower()
        candidates = [o for o in candidates
                      if q in o["acronym"].lower() or q in o["name"].lower()]

    if not candidates:
        st.info("Nothing matches, or everything is already downloaded.")
    else:
        with st.container(height=380):
            for ont in candidates:
                acronym = ont["acronym"]
                name_col, btn_col = st.columns([5, 1], vertical_alignment="center")
                name_col.write(acronym + " - " + ont["name"])
                if btn_col.button("Download", key="download_" + acronym):
                    with st.spinner("Downloading " + acronym + " from BioPortal..."):
                        ok, message = install_ontology(acronym)
                    if ok:
                        # The catalog on disk changed; drop the caches so this
                        # entry moves to Available, then redraw only the dialog
                        # so several ontologies can be fetched in one visit.
                        _load_ontology_catalog.clear()
                        st.session_state.available_ontologies = []
                        st.rerun(scope="fragment")
                    else:
                        st.error(message)

    if st.button("Done", key="download_dialog_done"):
        st.rerun()  # full rerun closes the dialog and refreshes the lists


# Render ontology selection: a filter box over the Available (downloaded)
# list with an Add button per row, the Selected list underneath with a Remove
# button per row, and a dialog for fetching more from BioPortal.
def render_ontology_selection(available_ontologies):
    st.markdown('<div class="section-header section-purple">Select Ontologies</div>', unsafe_allow_html=True)

    # A download attempted on the previous rerun may have failed; the message
    # has to survive that rerun, so it travels through session state.
    install_error = st.session_state.pop("ontology_install_error", None)
    if install_error:
        st.error(install_error)

    selected = st.session_state.selected_ontologies

    # The filter sits directly above the list it filters.
    filter_query = st.text_input("Filter ontologies",
                                 placeholder="Type to filter available ontologies...")

    header_col, button_col = st.columns([3, 1], vertical_alignment="bottom")
    with header_col:
        st.markdown('<div class="sub-heading">Available ontologies</div>',
                    unsafe_allow_html=True)
    # On a download-everything install the whole catalogue is already local
    # (or on its way), so there is nothing for the button to offer.
    if not download_all_requested():
        with button_col:
            if st.button("Download ontologies", key="open_download_dialog"):
                _download_ontologies_dialog()

    available = [o for o in available_ontologies
                 if o.get("downloaded", False) and o["acronym"] not in selected]
    if filter_query:
        q = filter_query.lower()
        available = [o for o in available
                     if q in o["acronym"].lower() or q in o["name"].lower()]

    at_limit = len(selected) >= MAX_SELECTED_ONTOLOGIES
    if at_limit:
        st.warning("Maximum of " + str(MAX_SELECTED_ONTOLOGIES) + " ontologies "
                   "selected. Remove one to add another.")

    if not available:
        if filter_query:
            st.caption("No available ontology matches '" + filter_query + "'.")
        else:
            st.caption("Nothing downloaded yet - use \"Download ontologies\" "
                       "to fetch some from BioPortal.")
    else:
        with st.container(height=350):
            for ont in available:
                acronym = ont["acronym"]
                label = acronym + " - " + ont["name"]
                if ont.get("update_available"):
                    label += "  (update available)"
                name_col, btn_col = st.columns([5, 1], vertical_alignment="center")
                name_col.write(label)
                if btn_col.button("Add", key="add_" + acronym, disabled=at_limit):
                    # An ontology whose BioPortal submission has moved on is
                    # refreshed at the moment it is chosen for use.
                    if ont.get("update_available"):
                        with st.spinner("Updating " + acronym + " from "
                                        "BioPortal... large ontologies can "
                                        "take a few minutes."):
                            ok, message = install_ontology(acronym)
                        if not ok:
                            st.session_state.ontology_install_error = message
                            st.rerun()
                        _load_ontology_catalog.clear()
                        st.session_state.available_ontologies = []
                    st.session_state.selected_ontologies.append(acronym)
                    st.session_state.ontologies_changed = True
                    st.rerun()

    st.markdown('<div class="sub-heading">Selected ontologies ('
                + str(len(selected)) + '/' + str(MAX_SELECTED_ONTOLOGIES)
                + ')</div>', unsafe_allow_html=True)
    if not selected:
        st.warning("Please select at least one ontology to proceed.")
    else:
        names = {o["acronym"]: o["name"] for o in available_ontologies}
        for acronym in list(selected):
            name_col, btn_col = st.columns([5, 1], vertical_alignment="center")
            name_col.write(acronym + " - " + names.get(acronym, acronym))
            if btn_col.button("Remove", key="remove_" + acronym):
                st.session_state.selected_ontologies.remove(acronym)
                st.session_state.ontologies_changed = True
                st.rerun()

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