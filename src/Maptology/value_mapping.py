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


def _render_value_checklist(df, key_prefix, column, value):
    """Render a checklist of value search results. Checked-state is derived
    from value_ontology_mapping (single source of truth)."""
    version = st.session_state.get("mapping_version", 0)
    # Key is derived from the term URI (stable identity), not the row position, so
    # a new search can't inherit the previous result's checked state. Drop duplicate
    # URIs first to avoid DuplicateWidgetID (same IRI across ontologies).
    df = df.drop_duplicates(subset=["Ontology Term URI"], keep="first").reset_index(drop=True)

    # Three aligned columns with thin light-gray dividers between them:
    # Term (checkbox) | Ontology | Details (ℹ️).
    COLS = [4, 0.1, 1.5, 0.1, 1, 5.3]
    DIVIDER = "<div style='border-left:1px solid #d9d9d9; height:2.2em;'></div>"
    h_term, _hs1, h_ont, _hs2, h_icon, _h_sp = st.columns(COLS)
    # Indent the Term header so it lines up with the value text, which sits to the
    # right of the checkbox box below it.
    h_term.markdown("<div style='padding-left:1.8rem;'><strong>Term</strong></div>", unsafe_allow_html=True)
    h_ont.markdown("<strong>Ontology</strong>", unsafe_allow_html=True)
    h_icon.markdown("<strong>Details</strong>", unsafe_allow_html=True)

    for i in range(len(df)):
        row = df.iloc[i]
        term_uri = row['Ontology Term URI']
        is_checked = is_value_term_mapped(column, value, term_uri)
        term_key = hashlib.sha1(str(term_uri).encode("utf-8")).hexdigest()[:16]
        # column AND value MUST be in the key so switching value/column can't
        # reuse another value's widget state for the same term.
        unique_key = key_prefix + "__" + str(column) + "__" + str(value) + "__" + term_key + "__" + str(version)

        term_col, sep1, ont_col, sep2, info_btn_col, _spacer = st.columns(COLS, vertical_alignment="center")
        with term_col:
            result = st.checkbox(row['Preferred Label'], value=is_checked, key=unique_key)
        sep1.markdown(DIVIDER, unsafe_allow_html=True)
        with ont_col:
            # Render the ontology as a DISABLED tertiary button (not markdown): it
            # is the same widget family as the ℹ️ button, which already lines up
            # with the checkbox, so it sits on the same line. Plain markdown text
            # centers within its block and drifts slightly lower than the widgets.
            st.button(str(row['Ontology Name']), key="ont_" + unique_key, disabled=True, type="tertiary")
        sep2.markdown(DIVIDER, unsafe_allow_html=True)
        with info_btn_col:
            if st.button("ℹ️", key="prev_" + unique_key, help="View term details", type="tertiary"):
                ontology_info = get_ontology_details(row['Ontology Name'])
                show_term_modal({
                    "pref_label": row['Preferred Label'],
                    "ontology_abbr": row['Ontology Name'],
                    "full_ontology_name": ontology_info['full_name'],
                    "definition": row['Definition'],
                    "term_uri": row['Ontology Term URI'],
                    "synonyms": row.get('Synonyms', []),
                })

        if result != is_checked:
            if result:
                add_value_term(column, value, row)
            else:
                remove_value_term(column, value, term_uri)
            st.rerun()


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
    elif dtype_name in ['object', 'str'] or dtype_name.startswith('string') or dtype_name == 'category':
        show_value_mapping = True
    else:
        show_value_mapping = False

    if show_value_mapping:
        unique_values = df[selected_col].dropna().unique()
        unique_values.sort()

        if len(unique_values) > 0:
            st.markdown('<div class="sub-heading">Select a unique value from column \'' + selected_col + '\' to map to an ontology term</div>', unsafe_allow_html=True)

            # Convert to string for display
            value_options = [str(v) for v in unique_values[:5].tolist()]

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
                    st.write("Select one or more terms that match '" + str(selected_value) + "':")
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
                            st.write("Select one or more terms from search results:")
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
