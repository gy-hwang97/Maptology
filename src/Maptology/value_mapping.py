import hashlib

import streamlit as st
from ontology import search_ontology_for_value, search_bioportal_manual_value, get_ontology_details
from mapping import (
    on_value_select,
    is_value_term_mapped,
    add_value_term,
    remove_value_term,
)
from components import show_term_modal
from utils import validate_type_change, get_column_data_type


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
    # Hide terms already added to this value.
    keep = [not is_value_term_mapped(column, value, u) for u in df["Ontology Term URI"]]
    df = df[keep].reset_index(drop=True)
    if len(df) == 0:
        st.caption("Every matching term has been added. Remove one from the "
                   "table below to add it again.")
        return

    for i in range(len(df)):
        row = df.iloc[i]
        term_uri = row["Ontology Term URI"]
        term_key = hashlib.sha1(str(term_uri).encode("utf-8")).hexdigest()[:16]
        base = key_prefix + "__" + str(column) + "__" + str(value) + "__" + term_key
        # Add button beside the term and its ontology, packed left; details last.
        with st.container(horizontal=True, vertical_alignment="center"):
            add_clicked = st.button("Add", key="add_" + base)
            st.markdown(str(row["Preferred Label"]) + "  —  "
                        + str(row["Ontology Name"]))
            info_clicked = st.button("ℹ️", key="info_" + base,
                                     help="View term details", type="tertiary")
        if add_clicked:
            add_value_term(column, value, row)
            st.session_state.term_added_toast = "Added: " + str(row["Preferred Label"])
            st.rerun()
        if info_clicked:
            ontology_info = get_ontology_details(row["Ontology Name"])
            show_term_modal({
                "pref_label": row["Preferred Label"],
                "ontology_abbr": row["Ontology Name"],
                "full_ontology_name": ontology_info["full_name"],
                "definition": row["Definition"],
                "term_uri": row["Ontology Term URI"],
                "synonyms": row.get("Synonyms", []),
            })


# Render value mapping section
def render_value_mapping_section():
    st.write("### Step 6: Map Ontology Terms for Values")
    st.caption("Now you can map ontology term(s) to each data value. Start by selecting a value from the dropdown below.")
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df

    # Validate user-selected type
    user_type = get_column_data_type(selected_col)
    is_valid, error_msg = validate_type_change(selected_col, user_type)

    if not is_valid:
        st.error("Value mapping is disabled: " + error_msg)
        st.info("Please change the data type to a valid option in the Column Information section above.")
        return

    # Check current data type
    current_dtype = df[selected_col].dtype
    dtype_name = str(current_dtype)

    # If user selected String, allow value mapping even for numeric data
    if user_type == "String":
        show_value_mapping = True
    elif user_type in ("Date", "Datetime", "Time"):
        # Date/time columns often read as object (unparsed date strings), which
        # would otherwise fall through to the object branch below and wrongly
        # offer value mapping. The user's chosen type wins: no value mapping.
        show_value_mapping = False
    elif dtype_name in ['object', 'str'] or dtype_name.startswith('string') or dtype_name == 'category':
        show_value_mapping = True
    else:
        show_value_mapping = False

    if show_value_mapping:
        # sorted() rather than .sort(): newer pandas backs string columns with
        # Arrow arrays, and their unique() result has no in-place sort. key=str
        # keeps mixed types comparable, matching how utils.py sorts these.
        unique_values = sorted(df[selected_col].dropna().unique(), key=str)

        if len(unique_values) > 0:
            st.markdown('<div class="sub-heading">Select a unique value from column \'' + selected_col + '\' to map to an ontology term</div>', unsafe_allow_html=True)

            # EVERY unique value has to be reachable: the exported mapping file
            # documents each one, so a value the dropdown never offers can never
            # be mapped. (This list used to be truncated to the first 5, which
            # silently made values 6+ impossible to map at all.)
            all_values = [str(v) for v in unique_values]

            # A long dropdown is hard to work through, so offer a filter once the
            # list is big enough to need one. Short columns render exactly as before.
            value_options = all_values
            if len(all_values) > VALUE_FILTER_THRESHOLD:
                needle = st.text_input(
                    "Filter values",
                    key="value_filter__" + str(selected_col),
                    placeholder="Type to filter values...",
                )
                if needle:
                    matches = [v for v in all_values if needle.lower() in v.lower()]
                    if matches:
                        value_options = matches
                    else:
                        st.caption("No value matches '" + needle + "' - showing all values.")
                st.caption("Showing " + str(len(value_options)) + " of "
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
                st.markdown('<div class="sub-heading">Select ontology terms for value: \'' + str(selected_value) + '\'</div>', unsafe_allow_html=True)

                # Full-width list. Term details open in a modal popup (ℹ️).
                with st.container(height=300):
                    st.write("Click Add next to any term that matches '" + str(selected_value) + "':")
                    _render_value_checklist(
                        st.session_state.value_ontology_results,
                        "val_auto",
                        selected_col,
                        selected_value,
                    )

            # ========== Manual search section (always visible) ==========
            with st.container(border=True):
                with st.form(key="value_search_form"):
                    value_search_term = st.text_input("Enter keywords to search for ontology terms", key="manual_value_search")
                    search_submitted = st.form_submit_button("Search Selected Ontologies")

                    if search_submitted:
                        if value_search_term:
                            with st.spinner("Searching for '" + value_search_term + "'..."):
                                search_success = search_bioportal_manual_value(value_search_term)

                            if search_success:
                                st.success("Search results found for '" + value_search_term + "'.")
                                st.rerun()
                            else:
                                st.warning("No results found for '" + value_search_term + "'.")
                        else:
                            st.warning("Please enter a search term.")

                # Manual search results. Hide any term already shown in the auto
                # list above, then cap at 10.
                manual_df = st.session_state.manual_value_search_results
                if manual_df is not None and len(manual_df) > 0:
                    if has_auto_results and st.session_state.value_ontology_results is not None:
                        auto_uris = set(st.session_state.value_ontology_results['Ontology Term URI'])
                        manual_df = manual_df[~manual_df['Ontology Term URI'].isin(auto_uris)]
                    manual_df = manual_df.drop_duplicates(subset=['Ontology Term URI'], keep='first').head(10)

                    st.markdown('<div class="sub-heading">Search Results</div>', unsafe_allow_html=True)
                    if len(manual_df) > 0:
                        with st.container(height=300):
                            st.write("Click Add next to any term from the search results:")
                            _render_value_checklist(
                                manual_df,
                                "val_manual",
                                selected_col,
                                st.session_state.selected_unique_value,
                            )
                    else:
                        st.caption("All matching terms are already listed above.")
        else:
            st.info("No unique values found in this column.")
    else:
        # Non-string column (e.g. Float / Integer): value mapping does not apply.
        # Show the step but hide the value dropdown and the keyword search.
        st.info("Value mapping is only available for string columns. Change the data type to 'String' above if you want to map individual values for this column.")
