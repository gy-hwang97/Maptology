import streamlit as st
from ontology import search_ontology_for_value, search_bioportal_manual_value, get_ontology_details
from mapping import on_value_select, on_value_checkbox_change, handle_value_multiple_mapping, handle_manual_value_mapping
from loading_overlay import show_loading_overlay
from components import set_term_preview, render_preview_panel
from utils import validate_type_change, get_column_data_type

# Render value mapping section
def render_value_mapping_section():
    st.write("### Step 5: Map Ontology Terms for Values")
    st.caption("Now you can map ontology term(s) to each data value. Start by selecting a value from the dropdown below.")
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df
    
    # Initialize delete counters
    if "value_checkbox_counter" not in st.session_state:
        st.session_state.value_checkbox_counter = 0
    if "manual_value_checkbox_counter" not in st.session_state:
        st.session_state.manual_value_checkbox_counter = 0
    
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
                    loading_container = st.empty()
                    with loading_container:
                        show_loading_overlay("Loading ontology terms for value '" + default_value + "'...")

                    search_ontology_for_value(default_value)
                    loading_container.empty()
                    
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
                
                # Left: checklist / Right: preview panel
                list_col, preview_col = st.columns(2)
                
                with list_col:
                  with st.container(height=300):
                    st.write("Select one or more terms that match '" + str(selected_value) + "':")
                    df_results = st.session_state.value_ontology_results
                    
                    # Set of currently selected indices
                    current_selected_indices = set(st.session_state.value_term_indices)
                    
                    for i in range(len(df_results)):
                        is_checked = i in current_selected_indices
                        term_label = df_results.iloc[i]['Preferred Label'] + " (" + df_results.iloc[i]['Ontology Name'] + ")"
                        
                        # Generate unique checkbox key - includes counter
                        counter = st.session_state.value_checkbox_counter
                        checkbox_key = "val_cb_" + str(selected_value) + "_" + str(i) + "_" + str(counter)
                        
                        cb_col, info_btn_col = st.columns([5, 1])
                        with cb_col:
                            checkbox_result = st.checkbox(
                                term_label,
                                value=is_checked,
                                key=checkbox_key,
                                on_change=on_value_checkbox_change
                            )
                        with info_btn_col:
                            if st.button("\u2139\ufe0f", key="preview_val_" + str(selected_value) + "_" + str(i) + "_" + str(counter), help="View term details", type="tertiary"):
                                ontology_info = get_ontology_details(df_results.iloc[i]['Ontology Name'])
                                set_term_preview(
                                    df_results.iloc[i]['Preferred Label'],
                                    df_results.iloc[i]['Ontology Name'],
                                    ontology_info['full_name'],
                                    df_results.iloc[i]['Definition'],
                                    df_results.iloc[i]['Ontology Term URI'],
                                    "value_term_preview",
                                    synonyms=df_results.iloc[i].get('Synonyms', [])
                                )
                        
                        # Detect and handle checkbox state changes
                        if checkbox_result != is_checked:
                            if checkbox_result:
                                if i not in st.session_state.value_term_indices:
                                    st.session_state.value_term_indices.append(i)
                                    column_key = st.session_state.selected_column
                                    if column_key not in st.session_state.value_term_indices_by_value:
                                        st.session_state.value_term_indices_by_value[column_key] = {}
                                    st.session_state.value_term_indices_by_value[column_key][selected_value] = st.session_state.value_term_indices.copy()
                                    handle_value_multiple_mapping(st.session_state.value_term_indices)
                            else:
                                if i in st.session_state.value_term_indices:
                                    st.session_state.value_term_indices.remove(i)
                                    column_key = st.session_state.selected_column
                                    if column_key not in st.session_state.value_term_indices_by_value:
                                        st.session_state.value_term_indices_by_value[column_key] = {}
                                    st.session_state.value_term_indices_by_value[column_key][selected_value] = st.session_state.value_term_indices.copy()
                                    handle_value_multiple_mapping(st.session_state.value_term_indices)
                
                # Right panel: Term Preview
                with preview_col:
                    render_preview_panel("value_term_preview")
            
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
                
                # Manual search results
                if st.session_state.manual_value_search_results is not None and len(st.session_state.manual_value_search_results) > 0:
                    st.markdown('<div class="sub-heading">Search Results</div>', unsafe_allow_html=True)
                    
                    with st.container(height=300):
                        st.write("Select one or more terms from search results:")
                        manual_df = st.session_state.manual_value_search_results
                        
                        current_manual_selected = set(st.session_state.manual_value_selected_indices)
                        
                        for i in range(len(manual_df)):
                            is_checked = i in current_manual_selected
                            
                            counter = st.session_state.manual_value_checkbox_counter
                            unique_key = "manual_val_cb_" + str(i) + "_" + str(counter)
                            term_label = manual_df.iloc[i]['Preferred Label'] + " (" + manual_df.iloc[i]['Ontology Name'] + ")"
                            
                            cb_col, info_btn_col = st.columns([5, 1])
                            with cb_col:
                                checkbox_result = st.checkbox(
                                    term_label,
                                    value=is_checked,
                                    key=unique_key
                                )
                            with info_btn_col:
                                if st.button("\u2139\ufe0f", key="preview_mval_" + str(i) + "_" + str(counter), help="View term details", type="tertiary"):
                                    ontology_info = get_ontology_details(manual_df.iloc[i]['Ontology Name'])
                                    set_term_preview(
                                        manual_df.iloc[i]['Preferred Label'],
                                        manual_df.iloc[i]['Ontology Name'],
                                        ontology_info['full_name'],
                                        manual_df.iloc[i]['Definition'],
                                        manual_df.iloc[i]['Ontology Term URI'],
                                        "value_term_preview",
                                        synonyms=manual_df.iloc[i].get('Synonyms', [])
                                    )
                            
                            if checkbox_result != is_checked:
                                if checkbox_result:
                                    if i not in st.session_state.manual_value_selected_indices:
                                        st.session_state.manual_value_selected_indices.append(i)
                                        handle_manual_value_mapping(st.session_state.manual_value_selected_indices)
                                else:
                                    if i in st.session_state.manual_value_selected_indices:
                                        st.session_state.manual_value_selected_indices.remove(i)
                                        handle_manual_value_mapping(st.session_state.manual_value_selected_indices)
        else:
            st.info("No unique values found in this column.")
    else:
        st.info("Value mapping is only available for string data types. Change the data type to 'String' if you want to map values for this column.")
        
        # Show manual search even for non-string types
        with st.container(border=True):
            with st.form(key="value_search_form_nonstring"):
                value_search_term = st.text_input("Enter keywords to search for ontology terms", key="manual_value_search_nonstring")
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
            
            # Manual search results
            if st.session_state.manual_value_search_results is not None and len(st.session_state.manual_value_search_results) > 0:
                st.markdown('<div class="sub-heading">Search Results</div>', unsafe_allow_html=True)
                
                with st.container(height=300):
                    st.write("Select one or more terms from search results:")
                    manual_df = st.session_state.manual_value_search_results
                    
                    current_manual_selected = set(st.session_state.manual_value_selected_indices)
                    
                    for i in range(len(manual_df)):
                        is_checked = i in current_manual_selected
                        
                        counter = st.session_state.manual_value_checkbox_counter
                        unique_key = "manual_val_ns_cb_" + str(i) + "_" + str(counter)
                        term_label = manual_df.iloc[i]['Preferred Label'] + " (" + manual_df.iloc[i]['Ontology Name'] + ")"
                        
                        cb_col, info_btn_col = st.columns([5, 1])
                        with cb_col:
                            checkbox_result = st.checkbox(
                                term_label,
                                value=is_checked,
                                key=unique_key
                            )
                        with info_btn_col:
                            if st.button("\u2139\ufe0f", key="preview_mval_ns_" + str(i) + "_" + str(counter), help="View term details", type="tertiary"):
                                ontology_info = get_ontology_details(manual_df.iloc[i]['Ontology Name'])
                                set_term_preview(
                                    manual_df.iloc[i]['Preferred Label'],
                                    manual_df.iloc[i]['Ontology Name'],
                                    ontology_info['full_name'],
                                    manual_df.iloc[i]['Definition'],
                                    manual_df.iloc[i]['Ontology Term URI'],
                                    "value_term_preview",
                                    synonyms=manual_df.iloc[i].get('Synonyms', [])
                                )
                        
                        if checkbox_result != is_checked:
                            if checkbox_result:
                                if i not in st.session_state.manual_value_selected_indices:
                                    st.session_state.manual_value_selected_indices.append(i)
                                    handle_manual_value_mapping(st.session_state.manual_value_selected_indices)
                            else:
                                if i in st.session_state.manual_value_selected_indices:
                                    st.session_state.manual_value_selected_indices.remove(i)
                                    handle_manual_value_mapping(st.session_state.manual_value_selected_indices)