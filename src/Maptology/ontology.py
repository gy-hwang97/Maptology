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
            "description": entry.get("description") or "",
            "version": entry.get("version") or "",
            "released": entry.get("released") or "",
            "downloaded": downloaded,
            "update_available": downloaded
                and recorded.get(acronym) != entry.get("submissionId"),
        })
    # Ontologies built locally that BioPortal no longer lists (this happens:
    # CMEO, CVO and HTO were withdrawn from its catalogue). They keep working;
    # there is just nothing to update them from, and no catalogue description.
    for acronym, entry in built.items():
        if acronym not in catalogue:
            merged.append({
                "acronym": acronym,
                "name": entry.get("name") or acronym,
                "description": "",
                "version": "",
                "released": "",
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


def _ontology_info_popover(ont):
    """An info button that opens a small panel with the ontology's description,
    version and release date. A popover rather than a dialog, so it also works
    inside the download dialog (dialogs cannot be nested)."""
    with st.popover("ℹ️", help="View description"):
        st.markdown("**" + ont["acronym"] + " - " + ont["name"] + "**")
        if ont.get("description"):
            st.write(ont["description"])
        else:
            st.caption("No description available.")
        meta = []
        if ont.get("version"):
            meta.append("Version: " + str(ont["version"]))
        if ont.get("released"):
            meta.append("Released: " + str(ont["released"])[:10])
        if meta:
            st.caption("  |  ".join(meta))


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

    # A download on the previous fragment rerun left a confirmation to show.
    success = st.session_state.pop("download_success_msg", None)
    if success:
        st.success(success)

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
        # After a download the confirmation above already explains the empty
        # list, so the "nothing matches" note would only confuse. Otherwise say
        # which case it is: an unmatched search, or everything downloaded.
        if success:
            pass
        elif query:
            st.info("No downloadable ontology matches '" + query + "'.")
        else:
            st.info("Every available ontology has already been downloaded.")
    else:
        with st.container(height=380):
            for ont in candidates:
                acronym = ont["acronym"]
                # Button next to the name, packed left (see the Available list).
                with st.container(horizontal=True, vertical_alignment="center"):
                    clicked = st.button("Download", key="download_" + acronym)
                    st.markdown(acronym + " - " + ont["name"])
                    _ontology_info_popover(ont)
                if clicked:
                    with st.spinner("Downloading " + acronym + " from BioPortal..."):
                        ok, message = install_ontology(acronym)
                    if ok:
                        # The catalog on disk changed; drop the caches so this
                        # entry moves to Available, then redraw only the dialog
                        # so several ontologies can be fetched in one visit.
                        st.session_state.download_success_msg = (
                            ont["name"] + " was downloaded successfully.")
                        _load_ontology_catalog.clear()
                        st.session_state.available_ontologies = []
                        st.rerun(scope="fragment")
                    else:
                        st.error(message)

    if st.button("Done", key="download_dialog_done"):
        st.rerun()  # full rerun closes the dialog and refreshes the lists


# Render ontology selection. A statement explains what to do; while nothing is
# downloaded, the Available section is hidden and only the Download dialog is
# offered. Once ontologies are on disk they appear under Available, each with a
# Select button; chosen ones move to Selected, each with a Remove button.
def render_ontology_selection(available_ontologies):
    # st.markdown('<div class="section-header section-purple">Select Ontologies</div>', unsafe_allow_html=True)

    # A download attempted on the previous rerun may have failed; the message
    # has to survive that rerun, so it travels through session state.
    install_error = st.session_state.pop("ontology_install_error", None)
    if install_error:
        st.error(install_error)

    selected = st.session_state.selected_ontologies

    # What is on disk decides both the wording below and which sections show.
    n_downloaded = sum(1 for o in available_ontologies if o.get("downloaded", False))
    total = len(available_ontologies)
    # "Everything is here" when the whole catalogue is downloaded, or on a
    # download-everything install where it is already on its way.
    all_downloaded = download_all_requested() or (total > 0 and n_downloaded >= total)

    statement = ("Before you can annotate your data, you must specify one or "
                 "more ontologies to use.")
    if all_downloaded:
        pass  # nothing left to download, so no extra guidance
    elif n_downloaded == 0:
        statement += (" Hundreds of ontologies are available on BioPortal. "
                      "However, to use these, you must first download them. To "
                      "do so, click on the \"Download ontologies\" button below.")
    else:
        statement += (" Hundreds of ontologies are available on BioPortal. The "
                      "ontologies you have downloaded are shown below. If you "
                      "would like to download more, click on the \"Download "
                      "ontologies\" button below.")
    st.caption(statement)

    # The Download button is offered until everything is downloaded. Rendered on
    # its own so it sits left-aligned at the start of the line.
    if not all_downloaded:
        if st.button("Download ontologies", key="open_download_dialog"):
            _download_ontologies_dialog()

    # Available ontologies stay hidden until at least one has been downloaded.
    if n_downloaded > 0:
        st.markdown('<div class="sub-heading">Available ontologies</div>',
                    unsafe_allow_html=True)
        st.caption("The following ontologies have been downloaded. Select any "
                   "that you wish to use when annotating your data.")

        # The filter sits directly under the heading and shows only while the
        # list does. Its label is hidden - the placeholder already says what it
        # is for. The key is versioned so Select can hand back an empty box: the
        # chosen ontology was usually the query's only match, and a stale query
        # would otherwise greet the user with an empty list.
        filter_seq = st.session_state.get("ontology_filter_seq", 0)
        filter_query = st.text_input(
            "Filter ontologies",
            placeholder="Type to filter available ontologies...",
            label_visibility="collapsed",
            key="ontology_filter_" + str(filter_seq))

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
                # An empty result usually has a reason the user can act on: the
                # match is already selected, or it exists but is not downloaded.
                q = filter_query.lower()
                already = [o["acronym"] for o in available_ontologies
                           if o["acronym"] in selected
                           and (q in o["acronym"].lower() or q in o["name"].lower())]
                downloadable = [o["acronym"] for o in available_ontologies
                                if not o.get("downloaded", False)
                                and o["acronym"] not in selected
                                and (q in o["acronym"].lower() or q in o["name"].lower())]
                if already:
                    st.caption(", ".join(already)
                               + (" is" if len(already) == 1 else " are")
                               + " already selected - see Selected ontologies below.")
                if downloadable:
                    shown = ", ".join(downloadable[:5])
                    if len(downloadable) > 5:
                        shown += " and %d more" % (len(downloadable) - 5)
                    st.caption(shown
                               + (" is" if len(downloadable) == 1 else " are")
                               + " not on this machine yet - use \"Download "
                                 "ontologies\" to fetch "
                               + ("it." if len(downloadable) == 1 else "them."))
                if not already and not downloadable:
                    st.caption("No available ontology matches '" + filter_query + "'.")
            else:
                st.caption("Every downloaded ontology is already selected.")
        else:
            with st.container(height=350):
                for ont in available:
                    acronym = ont["acronym"]
                    label = acronym + " - " + ont["name"]
                    if ont.get("update_available"):
                        label += "  (update available)"
                    # Button next to the name, packed left, so a wide screen
                    # leaves the empty space on the right, not between them.
                    with st.container(horizontal=True, vertical_alignment="center"):
                        clicked = st.button("Select", key="add_" + acronym,
                                            disabled=at_limit)
                        st.markdown(label)
                        _ontology_info_popover(ont)
                    if clicked:
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
                        st.session_state.ontology_filter_seq = filter_seq + 1
                        st.session_state.selected_ontologies.append(acronym)
                        st.session_state.ontologies_changed = True
                        st.rerun()

    # Selected ontologies appear only once at least one has been chosen.
    if selected:
        st.markdown('<div class="sub-heading">Selected ontologies ('
                    + str(len(selected)) + '/' + str(MAX_SELECTED_ONTOLOGIES)
                    + ')</div>', unsafe_allow_html=True)
        names = {o["acronym"]: o["name"] for o in available_ontologies}
        for acronym in list(selected):
            # Remove on the left, next to the name, matching the Available list.
            with st.container(horizontal=True, vertical_alignment="center"):
                clicked = st.button("Remove", key="remove_" + acronym)
                st.markdown(acronym + " - " + names.get(acronym, acronym))
            if clicked:
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