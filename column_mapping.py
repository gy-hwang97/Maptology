import streamlit as st
from ontology import search_ontology, search_bioportal_manual_column, get_ontology_details
from mapping import on_column_select, on_column_checkbox_change, handle_multiple_mapping, handle_manual_column_mapping
from components import set_term_preview, render_preview_panel
from utils import get_friendly_dtype, display_column_info, get_column_data_type, validate_type_change

# Render column selection and ontology mapping section
def render_column_mapping_section():
    st.write("### Step 4: Map Ontology Terms for Columns")
    st.caption("Now that you have selected one or more ontologies, it is time to search for ontology term(s) for each column and map them to each other. Start by selecting a column name from the dropdown below.")
    
    # Initialize delete counters
    if "column_checkbox_counter" not in st.session_state:
        st.session_state.column_checkbox_counter = 0
    if "manual_column_checkbox_counter" not in st.session_state:
        st.session_state.manual_column_checkbox_counter = 0
    
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
            
            # Load saved info if column is already mapped
            if selected_column in st.session_state.column_mapping:
                saved_terms = st.session_state.column_mapping[selected_column].get("selected_terms", [])
                st.session_state.selected_terms = saved_terms.copy()
                st.session_state.current_mapping_done = True
            
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
        
        # ========== Auto search results section ==========
        if st.session_state.filtered_ontology_results is not None and len(st.session_state.filtered_ontology_results) > 0:
            st.markdown('<div class="sub-heading">Select ontology terms</div>', unsafe_allow_html=True)
            st.caption("Select ontology terms by checking the boxes below or searching for additional ontology terms.")
            
            # Left: checklist / Right: preview panel
            list_col, preview_col = st.columns(2)
            
            with list_col:
              with st.container(height=300):
                st.write("Select one or more terms that match your column:")
                df = st.session_state.filtered_ontology_results
                
                current_search = st.session_state.get('current_search_term', st.session_state.selected_column)
                
                if current_search not in st.session_state.search_terms_selections:
                    st.session_state.search_terms_selections[current_search] = []
                
                # Determine check state based on current selected_terms
                current_selected_uris = set(st.session_state.selected_terms)
                
                for i in range(len(df)):
                    term_uri = df.iloc[i]['Ontology Term URI']
                    
                    is_checked = term_uri in current_selected_uris
                    
                    counter = st.session_state.column_checkbox_counter
                    unique_key = "col_cb_" + str(current_search) + "_" + str(i) + "_" + str(counter)
                    term_label = df.iloc[i]['Preferred Label'] + " (" + df.iloc[i]['Ontology Name'] + ")"
                    
                    cb_col, info_btn_col = st.columns([5, 1])
                    with cb_col:
                        checkbox_result = st.checkbox(
                            term_label,
                            value=is_checked,
                            key=unique_key,
                            on_change=on_column_checkbox_change
                        )
                    with info_btn_col:
                        if st.button("\u2139\ufe0f", key="preview_col_" + str(current_search) + "_" + str(i) + "_" + str(counter), help="View term details", type="tertiary"):
                            ontology_info = get_ontology_details(df.iloc[i]['Ontology Name'])
                            set_term_preview(
                                df.iloc[i]['Preferred Label'],
                                df.iloc[i]['Ontology Name'],
                                ontology_info['full_name'],
                                df.iloc[i]['Definition'],
                                df.iloc[i]['Ontology Term URI'],
                                "column_term_preview",
                                synonyms=df.iloc[i].get('Synonyms', [])
                            )
                    
                    # Detect and handle checkbox state changes
                    if checkbox_result != is_checked:
                        if checkbox_result:
                            if term_uri not in st.session_state.search_terms_selections[current_search]:
                                st.session_state.search_terms_selections[current_search].append(term_uri)
                            if term_uri not in st.session_state.selected_terms:
                                st.session_state.selected_terms.append(term_uri)
                                handle_multiple_mapping(st.session_state.selected_terms, current_search)
                        else:
                            if term_uri in st.session_state.search_terms_selections[current_search]:
                                st.session_state.search_terms_selections[current_search].remove(term_uri)
                            if term_uri in st.session_state.selected_terms:
                                st.session_state.selected_terms.remove(term_uri)
                                handle_multiple_mapping(st.session_state.selected_terms, current_search)
              
              # ========== Manual search section ==========
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
                
                # Manual search results
                if st.session_state.manual_column_search_results is not None and len(st.session_state.manual_column_search_results) > 0:
                    st.markdown('<div class="sub-heading">Search Results</div>', unsafe_allow_html=True)
                    
                    with st.container(height=300):
                        st.write("Select one or more terms from search results:")
                        manual_df = st.session_state.manual_column_search_results
                        
                        current_manual_selected = set(st.session_state.manual_column_selected_terms)
                        
                        for i in range(len(manual_df)):
                            term_uri = manual_df.iloc[i]['Ontology Term URI']
                            is_checked = term_uri in current_manual_selected
                            
                            counter = st.session_state.manual_column_checkbox_counter
                            unique_key = "manual_col_cb_" + str(i) + "_" + str(counter)
                            term_label = manual_df.iloc[i]['Preferred Label'] + " (" + manual_df.iloc[i]['Ontology Name'] + ")"
                            
                            cb_col, info_btn_col = st.columns([5, 1])
                            with cb_col:
                                checkbox_result = st.checkbox(
                                    term_label,
                                    value=is_checked,
                                    key=unique_key
                                )
                            with info_btn_col:
                                if st.button("\u2139\ufe0f", key="preview_mcol_" + str(i) + "_" + str(counter), help="View term details", type="tertiary"):
                                    ontology_info = get_ontology_details(manual_df.iloc[i]['Ontology Name'])
                                    set_term_preview(
                                        manual_df.iloc[i]['Preferred Label'],
                                        manual_df.iloc[i]['Ontology Name'],
                                        ontology_info['full_name'],
                                        manual_df.iloc[i]['Definition'],
                                        manual_df.iloc[i]['Ontology Term URI'],
                                        "column_term_preview",
                                        synonyms=manual_df.iloc[i].get('Synonyms', [])
                                    )
                            
                            if checkbox_result != is_checked:
                                if checkbox_result:
                                    if term_uri not in st.session_state.manual_column_selected_terms:
                                        st.session_state.manual_column_selected_terms.append(term_uri)
                                        handle_manual_column_mapping(st.session_state.manual_column_selected_terms)
                                else:
                                    if term_uri in st.session_state.manual_column_selected_terms:
                                        st.session_state.manual_column_selected_terms.remove(term_uri)
                                        handle_manual_column_mapping(st.session_state.manual_column_selected_terms)
            
            # Right panel: Term Preview
            with preview_col:
                render_preview_panel("column_term_preview")