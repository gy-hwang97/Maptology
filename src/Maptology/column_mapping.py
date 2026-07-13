import hashlib

import streamlit as st
from ontology import search_ontology, search_bioportal_manual_column, get_ontology_details
from mapping import (
    on_column_select,
    is_column_term_mapped,
    add_column_term,
    remove_column_term,
)
from components import show_term_modal
from utils import get_friendly_dtype, display_column_info, get_column_data_type, validate_type_change


def _render_term_checklist(df, key_prefix, column):
    """Render a checklist of search results. Checked-state is derived from the
    column mapping (single source of truth); toggling adds/removes the term."""
    version = st.session_state.get("mapping_version", 0)
    # The checkbox key is derived from the term URI (its stable identity), NOT the
    # row position. A position-based key gets reused when a new search puts a
    # different term at the same row, so Streamlit keeps showing the old checked
    # state. Drop duplicate URIs first so two rows can never produce the same key
    # (the same IRI can appear in more than one ontology's results -> DuplicateWidgetID).
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
        is_checked = is_column_term_mapped(column, term_uri)
        term_key = hashlib.sha1(str(term_uri).encode("utf-8")).hexdigest()[:16]
        # column MUST be in the key too, so switching columns can't reuse another
        # column's widget state for the same term.
        unique_key = key_prefix + "__" + str(column) + "__" + term_key + "__" + str(version)

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
                add_column_term(column, row)
            else:
                remove_column_term(column, term_uri)
            st.rerun()


# Render column selection and ontology mapping section
def render_column_mapping_section():
    st.write("### Step 5: Map Ontology Terms for Columns")
    st.caption("Now that you have selected one or more ontologies, it is time to search for ontology term(s) for each column and map them to each other. Start by selecting a column name from the dropdown below.")

    if st.session_state.uploaded_df is not None:
        columns = list(st.session_state.uploaded_df.columns)

        # Auto-select and search first column on initial file load
        if st.session_state.first_load and columns:
            first_column = columns[0]
            st.session_state.selected_column = first_column
            st.session_state.column_select = first_column

            search_ontology(first_column)

            st.session_state.first_load = False

        selected_column = st.selectbox(
            "Select a column to map",
            columns,
            key="column_select",
            on_change=on_column_select
        )

        if selected_column:
            st.session_state.selected_column = selected_column

            # ========== Select Data Type section ==========
            st.markdown('<div class="sub-heading">Select Data Type</div>', unsafe_allow_html=True)

            df = st.session_state.uploaded_df

            # Data Type dropdown (LinkML-based)
            dtype_options = ["String", "Float", "Integer", "Boolean", "Date", "Datetime", "Time"]

            # Get user-selected type from column_data_types
            current_display_type = get_column_data_type(selected_column)
            default_index = dtype_options.index(current_display_type) if current_display_type in dtype_options else 0

            new_type = st.selectbox(
                "Data type",
                dtype_options,
                index=default_index,
                key="col_info_dtype_" + selected_column,
                label_visibility="collapsed"
            )

            # Save to session state (export reads this value)
            st.session_state.column_data_types[selected_column] = new_type

            # Data type validation
            is_valid, error_msg = validate_type_change(selected_column, new_type)
            if not is_valid:
                st.error(error_msg)

            # Display column info based on user-selected type
            display_column_info(df, selected_column, new_type)

        # ========== Mapping section ==========
        # The two-column layout (checklist | preview) is shown whenever a
        # column is selected. The automatic-results checklist only appears when
        # there are matches; the manual keyword search is ALWAYS available so a
        # column with no automatic match can still be mapped by hand.
        if selected_column:
            has_auto = (st.session_state.filtered_ontology_results is not None
                        and len(st.session_state.filtered_ontology_results) > 0)

            st.markdown('<div class="sub-heading">Select ontology terms</div>', unsafe_allow_html=True)
            st.caption("Select ontology terms by checking the boxes below, or click the ℹ️ icon to view a term's details. You can also search for more terms.")

            # Full-width list. Term details open in a modal popup (ℹ️) instead of
            # an always-on side panel, so the list can use the whole width.
            if has_auto:
                with st.container(height=300):
                    st.write("Select one or more terms that match your column:")
                    _render_term_checklist(
                        st.session_state.filtered_ontology_results,
                        "col_auto",
                        selected_column,
                    )
            else:
                st.caption("No automatic matches for this column name. Use the keyword search below.")

            # ========== Manual search section (always available) ==========
            with st.container(border=True):
                with st.form(key="column_search_form"):
                    column_search_term = st.text_input("Enter keywords to search for ontology terms", key="manual_column_search")
                    search_submitted = st.form_submit_button("Search Selected Ontologies")

                    if search_submitted:
                        if column_search_term:
                            with st.spinner("Searching for '" + column_search_term + "'..."):
                                search_success = search_bioportal_manual_column(column_search_term)

                            if search_success:
                                st.success("Search results found for '" + column_search_term + "'.")
                                st.rerun()
                            else:
                                st.warning("No results found for '" + column_search_term + "'.")
                        else:
                            st.warning("Please enter a search term.")

                # Manual search results. Hide any term already shown in the auto
                # list above (professor: "only show terms down here that are not
                # already shown up here"), then cap at 10.
                manual_df = st.session_state.manual_column_search_results
                if manual_df is not None and len(manual_df) > 0:
                    if has_auto and st.session_state.filtered_ontology_results is not None:
                        auto_uris = set(st.session_state.filtered_ontology_results['Ontology Term URI'])
                        manual_df = manual_df[~manual_df['Ontology Term URI'].isin(auto_uris)]
                    manual_df = manual_df.drop_duplicates(subset=['Ontology Term URI'], keep='first').head(10)

                    st.markdown('<div class="sub-heading">Search Results</div>', unsafe_allow_html=True)
                    if len(manual_df) > 0:
                        with st.container(height=300):
                            st.write("Select one or more terms from search results:")
                            _render_term_checklist(manual_df, "col_manual", selected_column)
                    else:
                        st.caption("All matching terms are already listed above.")
