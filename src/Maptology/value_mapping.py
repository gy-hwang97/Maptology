import hashlib

import streamlit as st
from ontology import search_ontology_for_value, search_bioportal_manual_value, get_ontology_details
from mapping import (
    on_value_select,
    is_value_term_mapped,
    confirm_added_value_term,
    _search_row_payload,
)
from components import render_term_info_popover
from utils import (
    validate_type_change,
    get_column_data_type,
    column_supports_value_mapping,
    live_query,
    live_text_input,
    mapping_row_id,
)


# Above this many distinct values, the value dropdown also gets a filter box.
VALUE_FILTER_THRESHOLD = 25


def _render_value_checklist(df, key_prefix, column, value):
    """Render value search results as a left-aligned list with an Add button.

    A term already mapped to this value is hidden here - it lives in the value
    mappings table below, where it can be removed. Clicking Add records it in
    value_ontology_mapping (the single source of truth) and confirms with a
    small toast."""
    # The same IRI can appear under more than one ontology; keep one row per URI.
    df = df.drop_duplicates(subset=["Ontology Term URI"], keep="first").reset_index(drop=True)
    if len(df) == 0:
        st.markdown("Every matching term has been added. Remove one from the "
                   "table below to add it again.")
        return

    # Mapped terms stay in the list, hidden. Deleting one shows that row
    # again without redrawing this search.
    shown = 0
    for i in range(len(df)):
        row = df.iloc[i]
        term_uri = row["Ontology Term URI"]
        term_key = hashlib.sha1(str(term_uri).encode("utf-8")).hexdigest()[:16]
        base = key_prefix + "__" + str(column) + "__" + str(value) + "__" + term_key
        mapped = is_value_term_mapped(column, value, term_uri)
        if not mapped:
            shown += 1
        # The id is on every row, mapped or not, so a later trash click can
        # show this row again without redrawing the search.
        row_id = mapping_row_id(column, value, term_uri)
        row_key = ("term_row_mapped_v_" if mapped else "term_row_v_") + row_id
        # Add button and the term on the left. The info icon is pinned to the
        # right edge of the row, same as Select ontologies.
        with st.container(horizontal=True, vertical_alignment="center",
                          key=row_key):
            st.button("Add", key="add_" + base,
                      help="Add " + str(row["Preferred Label"]) + " from " + str(row["Ontology Name"]),
                      on_click=confirm_added_value_term,
                      args=(column, value, _search_row_payload(row)))
            st.markdown(str(row["Preferred Label"]) + "  —  "
                        + str(row["Ontology Name"]))
            ontology_info = get_ontology_details(row["Ontology Name"])
            render_term_info_popover({
                "pref_label": row["Preferred Label"],
                "ontology_abbr": row["Ontology Name"],
                "full_ontology_name": ontology_info["full_name"],
                "definition": row["Definition"],
                "term_uri": row["Ontology Term URI"],
                "synonyms": row.get("Synonyms", []),
            }, "info_" + base)
    st.markdown(
        '<p class="maptology-all-mapped"'
        + ("" if shown == 0 else " hidden")
        + ">Every matching term has been added. "
        "Remove one from the table below to add it again.</p>",
        unsafe_allow_html=True)


# Render value mapping section.
# Mounted with Step 5, and hidden with it until an ontology is selected.
@st.fragment(key="value_mapping")
def render_value_mapping_section():
    with st.container(key="step6_block"):
        _render_step6()


def _render_step6():
    if (not st.session_state.selected_column
            or st.session_state.uploaded_df is None):
        st.html('<div class="maptology-step-idle" hidden></div>')
        return

    st.markdown("### Step 6: Map Ontology Terms for Values", anchors=False)
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df

    # Validate user-selected type
    user_type = get_column_data_type(selected_col)
    is_valid, error_msg = validate_type_change(selected_col, user_type)

    if not is_valid:
        st.error("Value mapping is disabled: " + error_msg)
        return

    if not column_supports_value_mapping(selected_col):
        # Numbers, dates, and times have no individual values to map. One
        # note stands in for the dropdown, the search, and the mappings list.
        st.markdown(
            '<div class="maptology-step-na">This step does not apply to '
            + str(user_type) + " columns.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown("Here you can map ontology term(s) to each data value. Start by selecting a value from the dropdown below.")

    # sorted() rather than .sort(): newer pandas backs string columns with
    # Arrow arrays, and their unique() result has no in-place sort. key=str
    # keeps mixed types comparable, matching how utils.py sorts these.
    unique_values = sorted(df[selected_col].dropna().unique(), key=str)

    if len(unique_values) > 0:
        st.markdown('<h4 class="sub-heading">Select a unique value from column \'' + selected_col + '\' to map to an ontology term</h4>', unsafe_allow_html=True, anchors=False)

        # EVERY unique value has to be reachable: the exported mapping file
        # documents each one, so a value the dropdown never offers can never
        # be mapped. (This list used to be truncated to the first 5, which
        # silently made values 6+ impossible to map at all.)
        all_values = [str(v) for v in unique_values]

        # A long dropdown is hard to work through, so offer a filter once the
        # list is big enough to need one. Short columns render exactly as before.
        value_options = all_values
        if len(all_values) > VALUE_FILTER_THRESHOLD:
            needle = live_query(live_text_input(
                "Filter values",
                key="value_filter__" + str(selected_col),
                placeholder="Type to filter values...",
            ))
            if needle:
                matches = [v for v in all_values if needle.lower() in v.lower()]
                if matches:
                    value_options = matches
                else:
                    st.markdown("No value matches '" + needle + "' - showing all values.")
            st.markdown("Showing " + str(len(value_options)) + " of "
                       + str(len(all_values)) + " unique values")

        if st.session_state.selected_unique_value is None or st.session_state.selected_unique_value not in value_options:
            default_value = value_options[0] if value_options else None
            st.session_state.selected_unique_value = default_value
            if default_value and st.session_state.selected_ontologies:
                search_ontology_for_value(default_value)
                st.session_state.auto_searched = True

        default_index = value_options.index(st.session_state.selected_unique_value) if st.session_state.selected_unique_value in value_options else 0

        selected_value = st.selectbox(
            "Select value to map",
            value_options,
            index=default_index,
            key="value_select",
            on_change=on_value_select,
            label_visibility="collapsed"
        )

        # ========== Auto search results section ==========
        has_auto_results = (st.session_state.value_ontology_results is not None and len(st.session_state.value_ontology_results) > 0)

        if has_auto_results:
            selected_value = st.session_state.selected_unique_value
            st.markdown('<h4 class="sub-heading">Select ontology terms for value: \'' + str(selected_value) + '\'</h4>', unsafe_allow_html=True, anchors=False)

            # Full-width list. Term details open in a popover (ℹ️), same as
            # the ontology lists.
            with st.container(height=300):
                st.write("Click Add next to any term that matches '" + str(selected_value) + "':")
                _render_value_checklist(
                    st.session_state.value_ontology_results,
                    "val_auto",
                    selected_col,
                    selected_value,
                )

        # ========== Manual search section (always visible) ==========
        # The box searches on its own once it has a character. An empty
        # box clears the previous keyword results.
        with st.container(border=True):
            value_search_term = live_text_input(
                "Enter keyword(s) to search for ontology terms",
                key="manual_value_search",
            )
            value_query = live_query(value_search_term)
            if not value_query:
                st.session_state.manual_value_search_query = ""
                st.session_state.manual_value_search_results = None
            elif value_query != st.session_state.get("manual_value_search_query"):
                with st.spinner("Searching for '" + value_query + "'..."):
                    search_success = search_bioportal_manual_value(value_query)
                st.session_state.manual_value_search_query = value_query
                if not search_success:
                    st.warning("No results found for '" + value_query + "'.")

            # Manual search results. Hide any term already shown in the auto
            # list above, then cap at 10.
            manual_df = st.session_state.manual_value_search_results
            if manual_df is not None and len(manual_df) > 0:
                if has_auto_results and st.session_state.value_ontology_results is not None:
                    auto_uris = set(st.session_state.value_ontology_results['Ontology Term URI'])
                    manual_df = manual_df[~manual_df['Ontology Term URI'].isin(auto_uris)]
                manual_df = manual_df.drop_duplicates(subset=['Ontology Term URI'], keep='first').head(10)

                st.markdown('<h4 class="sub-heading">Search Results</h4>', unsafe_allow_html=True, anchors=False)
                if len(manual_df) > 0:
                    with st.container(height=300):
                        _render_value_checklist(
                            manual_df,
                            "val_manual",
                            selected_col,
                            st.session_state.selected_unique_value,
                        )
                else:
                    st.markdown("All matching terms are already listed above.")
    else:
        st.info("No unique values found in this column.")
