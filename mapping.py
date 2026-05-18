import streamlit as st
from ontology import get_ontology_details
from utils import get_friendly_dtype, get_column_data_type
from loading_overlay import show_loading_overlay

# =============================================================================
# Column auto search: handle_multiple_mapping
# Only manages URIs from filtered_ontology_results (auto search)
# Does NOT touch manual search mappings
# =============================================================================
def handle_multiple_mapping(selected_term_uris, search_term=None):
    if st.session_state.filtered_ontology_results is None:
        return
    
    selected_column = st.session_state.selected_column
    df_results = st.session_state.filtered_ontology_results
    original_label = selected_column  # Always use column name as label
    
    # Get all URIs from auto search results
    auto_uris = set(df_results['Ontology Term URI'].tolist())
    selected_uris = set(selected_term_uris)
    
    # Get data type (사용자 선택 우선)
    data_type = get_column_data_type(selected_column)
    
    # Remove only auto-search URIs that are no longer selected
    # (preserve manual search mappings and other columns' mappings)
    st.session_state.mapped_terms = [
        m for m in st.session_state.mapped_terms
        if not (m["Original Label"] == original_label
                and m["Ontology Term URI"] in auto_uris
                and m["Ontology Term URI"] not in selected_uris)
    ]
    
    # Add newly selected URIs (avoid duplicates)
    existing_uris = set(
        m["Ontology Term URI"] for m in st.session_state.mapped_terms
        if m["Original Label"] == original_label
    )
    
    for idx, row in df_results.iterrows():
        uri = row["Ontology Term URI"]
        if uri in selected_uris and uri not in existing_uris:
            ontology_abbr = row["Ontology Name"]
            ontology_info = get_ontology_details(ontology_abbr)
            full_ontology_name = ontology_info['full_name']
            display_ontology_name = f"{full_ontology_name} ({ontology_abbr})"
            
            st.session_state.mapped_terms.append({
                "Original Label": original_label,
                "Preferred Label": row["Preferred Label"],
                "Ontology Name": display_ontology_name,
                "Ontology Abbr": ontology_abbr,
                "Ontology URI": row["Ontology URI"],
                "Ontology Term URI": row["Ontology Term URI"],
                "Data Type": data_type,
                "Definition": row["Definition"]
            })
    
    st.session_state.current_mapping_done = True
    
    # Update column_mapping (auto search tracking)
    st.session_state.column_mapping[original_label] = {
        "selected_terms": list(selected_term_uris),
        "mapping_info": [
            m for m in st.session_state.mapped_terms
            if m["Original Label"] == original_label and m["Ontology Term URI"] in auto_uris
        ]
    }

# =============================================================================
# Column manual search: handle_manual_column_mapping
# Only manages URIs from manual_column_search_results
# Does NOT touch auto search mappings
# =============================================================================
def handle_manual_column_mapping(selected_term_uris):
    if st.session_state.get("manual_column_search_results") is None:
        return
    
    selected_column = st.session_state.selected_column
    df_results = st.session_state.manual_column_search_results
    original_label = selected_column
    
    # Get all URIs from manual search results
    manual_uris = set(df_results['Ontology Term URI'].tolist())
    selected_uris = set(selected_term_uris)
    
    # Get data type (사용자 선택 우선)
    data_type = get_column_data_type(selected_column)
    
    # Remove only manual-search URIs that are no longer selected
    st.session_state.mapped_terms = [
        m for m in st.session_state.mapped_terms
        if not (m["Original Label"] == original_label
                and m["Ontology Term URI"] in manual_uris
                and m["Ontology Term URI"] not in selected_uris)
    ]
    
    # Add newly selected URIs
    existing_uris = set(
        m["Ontology Term URI"] for m in st.session_state.mapped_terms
        if m["Original Label"] == original_label
    )
    
    for term_uri in selected_term_uris:
        if term_uri not in existing_uris:
            matching = df_results[df_results['Ontology Term URI'] == term_uri]
            if not matching.empty:
                row = matching.iloc[0]
                ontology_abbr = row["Ontology Name"]
                ontology_info = get_ontology_details(ontology_abbr)
                full_name = ontology_info['full_name']
                
                st.session_state.mapped_terms.append({
                    "Original Label": original_label,
                    "Preferred Label": row["Preferred Label"],
                    "Ontology Name": f"{full_name} ({ontology_abbr})",
                    "Ontology Abbr": ontology_abbr,
                    "Ontology URI": row["Ontology URI"],
                    "Ontology Term URI": row["Ontology Term URI"],
                    "Data Type": data_type,
                    "Definition": row["Definition"]
                })
    
    st.session_state.current_mapping_done = True

# =============================================================================
# Value auto search: handle_value_multiple_mapping
# Only manages URIs from value_ontology_results (auto search)
# Does NOT touch manual search mappings
# =============================================================================
def handle_value_multiple_mapping(selected_indices):
    if st.session_state.value_ontology_results is None:
        return
    
    selected_column = st.session_state.selected_column
    selected_value = st.session_state.selected_unique_value
    df_results = st.session_state.value_ontology_results
    
    if not selected_value:
        return
    
    # Get data type (사용자 선택 우선)
    data_type = get_column_data_type(selected_column)
    
    # Get all URIs from auto search results
    auto_uris = set(df_results['Ontology Term URI'].tolist())
    
    # Get selected URIs from indices
    selected_uris = set()
    for idx in selected_indices:
        if idx < len(df_results):
            selected_uris.add(df_results.iloc[idx]['Ontology Term URI'])
    
    # Initialize mapping structure
    if selected_column not in st.session_state.value_ontology_mapping:
        st.session_state.value_ontology_mapping[selected_column] = {}
    
    # Get current mappings for this value
    current_mappings = st.session_state.value_ontology_mapping[selected_column].get(selected_value, [])
    if not isinstance(current_mappings, list):
        current_mappings = [current_mappings]
    
    # Remove only auto-search URIs that are no longer selected
    new_mappings = [
        m for m in current_mappings
        if not (m["Ontology Term URI"] in auto_uris and m["Ontology Term URI"] not in selected_uris)
    ]
    
    # Add newly selected auto URIs
    existing_uris = set(m["Ontology Term URI"] for m in new_mappings)
    
    for idx in selected_indices:
        if idx < len(df_results):
            row = df_results.iloc[idx]
            uri = row['Ontology Term URI']
            if uri not in existing_uris:
                ontology_abbr = row["Ontology Name"]
                ontology_info = get_ontology_details(ontology_abbr)
                full_name = ontology_info['full_name']
                
                new_mappings.append({
                    "Preferred Label": row["Preferred Label"],
                    "Ontology Name": f"{full_name} ({ontology_abbr})",
                    "Ontology Abbr": ontology_abbr,
                    "Ontology URI": row["Ontology URI"],
                    "Ontology Term URI": row["Ontology Term URI"],
                    "Definition": row["Definition"],
                    "Data Type": data_type
                })
    
    # Store result
    if new_mappings:
        st.session_state.value_ontology_mapping[selected_column][selected_value] = new_mappings
    else:
        if selected_value in st.session_state.value_ontology_mapping.get(selected_column, {}):
            del st.session_state.value_ontology_mapping[selected_column][selected_value]
        if selected_column in st.session_state.value_ontology_mapping and not st.session_state.value_ontology_mapping[selected_column]:
            del st.session_state.value_ontology_mapping[selected_column]

# =============================================================================
# Value manual search: handle_manual_value_mapping
# Only manages URIs from manual_value_search_results
# Does NOT touch auto search mappings
# =============================================================================
def handle_manual_value_mapping(selected_indices):
    if st.session_state.get("manual_value_search_results") is None:
        return
    
    selected_column = st.session_state.selected_column
    selected_value = st.session_state.selected_unique_value
    df_results = st.session_state.manual_value_search_results
    
    if not selected_value or not selected_column:
        return
    
    # Get data type (사용자 선택 우선)
    data_type = get_column_data_type(selected_column)
    
    # Get all URIs from manual search results
    manual_uris = set(df_results['Ontology Term URI'].tolist())
    
    # Get selected URIs from indices
    selected_uris = set()
    for idx in selected_indices:
        if idx < len(df_results):
            selected_uris.add(df_results.iloc[idx]['Ontology Term URI'])
    
    # Initialize mapping structure
    if selected_column not in st.session_state.value_ontology_mapping:
        st.session_state.value_ontology_mapping[selected_column] = {}
    
    # Get current mappings for this value
    current_mappings = st.session_state.value_ontology_mapping[selected_column].get(selected_value, [])
    if not isinstance(current_mappings, list):
        current_mappings = [current_mappings]
    
    # Remove only manual-search URIs that are no longer selected
    new_mappings = [
        m for m in current_mappings
        if not (m["Ontology Term URI"] in manual_uris and m["Ontology Term URI"] not in selected_uris)
    ]
    
    # Add newly selected manual URIs
    existing_uris = set(m["Ontology Term URI"] for m in new_mappings)
    
    for idx in selected_indices:
        if idx < len(df_results):
            row = df_results.iloc[idx]
            uri = row['Ontology Term URI']
            if uri not in existing_uris:
                ontology_abbr = row["Ontology Name"]
                ontology_info = get_ontology_details(ontology_abbr)
                full_name = ontology_info['full_name']
                
                new_mappings.append({
                    "Preferred Label": row["Preferred Label"],
                    "Ontology Name": f"{full_name} ({ontology_abbr})",
                    "Ontology Abbr": ontology_abbr,
                    "Ontology URI": row["Ontology URI"],
                    "Ontology Term URI": row["Ontology Term URI"],
                    "Definition": row["Definition"],
                    "Data Type": data_type
                })
    
    # Store result
    if new_mappings:
        st.session_state.value_ontology_mapping[selected_column][selected_value] = new_mappings
    elif selected_value in st.session_state.value_ontology_mapping.get(selected_column, {}):
        del st.session_state.value_ontology_mapping[selected_column][selected_value]
        if not st.session_state.value_ontology_mapping[selected_column]:
            del st.session_state.value_ontology_mapping[selected_column]

# =============================================================================
# Mapping removal functions
# =============================================================================

def remove_mapping(column_name):
    """Remove ALL mappings for a column (both auto and manual)"""
    if column_name:
        st.session_state.mapped_terms = [
            mapping for mapping in st.session_state.mapped_terms 
            if mapping["Original Label"] != column_name
        ]
        
        if column_name in st.session_state.column_mapping:
            del st.session_state.column_mapping[column_name]
        
        if column_name in st.session_state.value_ontology_mapping:
            del st.session_state.value_ontology_mapping[column_name]

        st.rerun()

def remove_value_mapping(column_name, value):
    if column_name and value and column_name in st.session_state.value_ontology_mapping:
        if value in st.session_state.value_ontology_mapping[column_name]:
            del st.session_state.value_ontology_mapping[column_name][value]

            st.rerun()

# =============================================================================
# Individual term mapping delete (column) - syncs BOTH auto and manual checkbox state
# =============================================================================
def remove_term_mapping(column_name, term_uri):
    if not (column_name and term_uri):
        return

    # 1) Remove from column_mapping (auto search tracking)
    if "column_mapping" in st.session_state and column_name in st.session_state.column_mapping:
        col_map = st.session_state.column_mapping[column_name]
        if "selected_terms" in col_map and term_uri in col_map["selected_terms"]:
            col_map["selected_terms"].remove(term_uri)
        if "mapping_info" in col_map:
            col_map["mapping_info"] = [
                m for m in col_map["mapping_info"]
                if m.get("Ontology Term URI") != term_uri
            ]
        if not col_map.get("selected_terms"):
            del st.session_state.column_mapping[column_name]

    # 2) Remove from auto search selected_terms
    if "selected_terms" in st.session_state and term_uri in st.session_state.selected_terms:
        st.session_state.selected_terms.remove(term_uri)

    # 3) Remove from search_terms_selections (all keys)
    if "search_terms_selections" in st.session_state:
        for key in list(st.session_state.search_terms_selections.keys()):
            if term_uri in st.session_state.search_terms_selections[key]:
                st.session_state.search_terms_selections[key].remove(term_uri)

    # 4) Remove from mapped_terms list
    if "mapped_terms" in st.session_state:
        st.session_state.mapped_terms = [
            m for m in st.session_state.mapped_terms
            if not (m.get("Original Label") == column_name and m.get("Ontology Term URI") == term_uri)
        ]
    
    # 5) Remove from column_states
    if "column_states" in st.session_state and column_name in st.session_state.column_states:
        saved_terms = st.session_state.column_states[column_name].get("selected_terms", [])
        if term_uri in saved_terms:
            saved_terms.remove(term_uri)
        # Also clean manual state in column_states
        saved_manual = st.session_state.column_states[column_name].get("manual_column_selected_terms", [])
        if term_uri in saved_manual:
            saved_manual.remove(term_uri)

    # 6) Bump auto search checkbox counter (forces new keys)
    if "column_checkbox_counter" not in st.session_state:
        st.session_state.column_checkbox_counter = 0
    st.session_state.column_checkbox_counter += 1

    # 7) Remove from manual_column_selected_terms (manual search state)
    if "manual_column_selected_terms" in st.session_state and term_uri in st.session_state.manual_column_selected_terms:
        st.session_state.manual_column_selected_terms.remove(term_uri)
    
    # 8) Bump manual search checkbox counter
    if "manual_column_checkbox_counter" not in st.session_state:
        st.session_state.manual_column_checkbox_counter = 0
    st.session_state.manual_column_checkbox_counter += 1

    st.rerun()

# =============================================================================
# Individual value mapping delete - syncs BOTH auto and manual checkbox state
# =============================================================================
def remove_individual_value_mapping(column_name, value, term_uri):
    if not (column_name and value and term_uri):
        return
    
    if column_name not in st.session_state.value_ontology_mapping:
        return
    if value not in st.session_state.value_ontology_mapping[column_name]:
        return
    
    # 1) Remove from value_ontology_mapping
    if isinstance(st.session_state.value_ontology_mapping[column_name][value], list):
        st.session_state.value_ontology_mapping[column_name][value] = [
            mapping for mapping in st.session_state.value_ontology_mapping[column_name][value]
            if mapping["Ontology Term URI"] != term_uri
        ]
        if not st.session_state.value_ontology_mapping[column_name][value]:
            del st.session_state.value_ontology_mapping[column_name][value]
        if not st.session_state.value_ontology_mapping.get(column_name):
            del st.session_state.value_ontology_mapping[column_name]
    
    # 2) Remove from auto search value_term_indices
    deleted_auto_index = None
    if st.session_state.value_ontology_results is not None:
        df_results = st.session_state.value_ontology_results
        for i in range(len(df_results)):
            if df_results.iloc[i]['Ontology Term URI'] == term_uri:
                deleted_auto_index = i
                break
    
    if deleted_auto_index is not None:
        if deleted_auto_index in st.session_state.value_term_indices:
            st.session_state.value_term_indices.remove(deleted_auto_index)
        
        # Also from value_term_indices_by_value
        if column_name in st.session_state.value_term_indices_by_value:
            if value in st.session_state.value_term_indices_by_value[column_name]:
                if deleted_auto_index in st.session_state.value_term_indices_by_value[column_name][value]:
                    st.session_state.value_term_indices_by_value[column_name][value].remove(deleted_auto_index)
        
        # Also from column_states
        if "column_states" in st.session_state and column_name in st.session_state.column_states:
            saved_indices = st.session_state.column_states[column_name].get("value_term_indices", [])
            if deleted_auto_index in saved_indices:
                saved_indices.remove(deleted_auto_index)
    
    # 3) Bump auto search checkbox counter
    if "value_checkbox_counter" not in st.session_state:
        st.session_state.value_checkbox_counter = 0
    st.session_state.value_checkbox_counter += 1
    
    # 4) Remove from manual search manual_value_selected_indices
    deleted_manual_index = None
    if st.session_state.get('manual_value_search_results') is not None:
        manual_df = st.session_state.manual_value_search_results
        for i in range(len(manual_df)):
            if manual_df.iloc[i]['Ontology Term URI'] == term_uri:
                deleted_manual_index = i
                break
    
    if deleted_manual_index is not None:
        if "manual_value_selected_indices" in st.session_state:
            if deleted_manual_index in st.session_state.manual_value_selected_indices:
                st.session_state.manual_value_selected_indices.remove(deleted_manual_index)
    
    # 5) Bump manual search checkbox counter
    if "manual_value_checkbox_counter" not in st.session_state:
        st.session_state.manual_value_checkbox_counter = 0
    st.session_state.manual_value_checkbox_counter += 1
    
    st.rerun()

# =============================================================================
# Callback functions
# =============================================================================

def on_column_checkbox_change():
    """Auto search checkbox callback"""
    handle_multiple_mapping(st.session_state.selected_terms)

def on_value_checkbox_change():
    """Auto value search checkbox callback"""
    pass

def on_column_select():
    """Column dropdown change callback"""
    selected_column = st.session_state.column_select
    previous_column = st.session_state.selected_column
    
    # Save previous column state
    if previous_column:
        st.session_state.column_states[previous_column] = {
            "selected_terms": st.session_state.selected_terms.copy(),
            "selected_unique_value": st.session_state.selected_unique_value,
            "value_ontology_results": st.session_state.value_ontology_results,
            "value_term_indices": st.session_state.value_term_indices.copy() if st.session_state.value_term_indices else [],
            "auto_searched": st.session_state.auto_searched,
            # Save manual search state too
            "manual_column_search_results": st.session_state.get("manual_column_search_results"),
            "manual_column_selected_terms": list(st.session_state.get("manual_column_selected_terms", [])),
            "manual_value_search_results": st.session_state.get("manual_value_search_results"),
            "manual_value_selected_indices": list(st.session_state.get("manual_value_selected_indices", [])),
        }
    
    if selected_column != previous_column:
        st.session_state.current_search_term = selected_column
        st.session_state.manual_search_term = None
        
        # Reset auto search state
        st.session_state.selected_terms = []
        st.session_state.selected_unique_value = None
        st.session_state.value_ontology_results = None
        st.session_state.value_term_indices = []
        st.session_state.auto_searched = False
        
        # Reset manual search state
        st.session_state.manual_column_search_results = None
        st.session_state.manual_column_selected_terms = []
        st.session_state.manual_value_search_results = None
        st.session_state.manual_value_selected_indices = []
        
        # Restore saved state
        if selected_column in st.session_state.column_states:
            saved_state = st.session_state.column_states[selected_column]
            st.session_state.selected_terms = saved_state.get("selected_terms", []).copy()
            st.session_state.selected_unique_value = saved_state.get("selected_unique_value")
            st.session_state.value_ontology_results = saved_state.get("value_ontology_results")
            st.session_state.value_term_indices = saved_state.get("value_term_indices", []).copy()
            st.session_state.auto_searched = saved_state.get("auto_searched", False)
            # Restore manual search state
            st.session_state.manual_column_search_results = saved_state.get("manual_column_search_results")
            st.session_state.manual_column_selected_terms = list(saved_state.get("manual_column_selected_terms", []))
            st.session_state.manual_value_search_results = saved_state.get("manual_value_search_results")
            st.session_state.manual_value_selected_indices = list(saved_state.get("manual_value_selected_indices", []))
    
    st.session_state.selected_column = selected_column
    st.session_state.current_mapping_done = False
    
    if selected_column and st.session_state.selected_ontologies and selected_column != previous_column:
        from ontology import search_ontology, search_ontology_for_value
        
        loading_container = st.empty()
        with loading_container:
            show_loading_overlay(f"Loading ontology terms for column '{selected_column}'...")
        
        search_ontology(selected_column)
        loading_container.empty()
        
        if st.session_state.uploaded_df is not None and not st.session_state.auto_searched:
            current_dtype = st.session_state.uploaded_df[selected_column].dtype
            dtype_name = str(current_dtype)
            
            if dtype_name == 'object' or dtype_name.startswith('string') or dtype_name == 'category':
                unique_values = st.session_state.uploaded_df[selected_column].dropna().unique()
                unique_values.sort()
                
                if len(unique_values) > 0:
                    default_value = unique_values[0]
                    st.session_state.selected_unique_value = default_value
                    
                    loading_container = st.empty()
                    with loading_container:
                        show_loading_overlay(f"Loading ontology terms for value '{default_value}'...")
                    
                    search_ontology_for_value(default_value)
                    loading_container.empty()
                    
                    st.session_state.auto_searched = True

def on_value_select():
    """Value dropdown change callback"""
    selected_value = st.session_state.value_select
    previous_value = st.session_state.selected_unique_value
    
    # Save previous value's indices
    if previous_value and st.session_state.value_term_indices:
        column_key = st.session_state.selected_column
        if column_key not in st.session_state.value_term_indices_by_value:
            st.session_state.value_term_indices_by_value[column_key] = {}
        st.session_state.value_term_indices_by_value[column_key][previous_value] = st.session_state.value_term_indices.copy()
    
    st.session_state.selected_unique_value = selected_value
    
    # Restore saved indices
    column_key = st.session_state.selected_column
    if (column_key in st.session_state.value_term_indices_by_value and 
        selected_value in st.session_state.value_term_indices_by_value[column_key]):
        st.session_state.value_term_indices = st.session_state.value_term_indices_by_value[column_key][selected_value].copy()
    else:
        st.session_state.value_term_indices = []
    
    # Reset manual value search when switching values
    st.session_state.manual_value_search_results = None
    st.session_state.manual_value_selected_indices = []
    
    if selected_value and selected_value != previous_value:
        from ontology import search_ontology_for_value
        
        loading_container = st.empty()
        with loading_container:
            show_loading_overlay(f"Loading ontology terms for value '{selected_value}'...")
        
        search_ontology_for_value(selected_value)
        loading_container.empty()