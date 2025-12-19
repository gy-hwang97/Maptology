import streamlit as st
import time
from ontology import get_ontology_details
from utils import get_friendly_dtype
from loading_overlay import show_loading_overlay

# 다중 매핑을 처리하는 콜백 함수
def handle_multiple_mapping(selected_term_uris, search_term=None):
    if st.session_state.filtered_ontology_results is None:
        return
    
    selected_column = st.session_state.selected_column
    df_results = st.session_state.filtered_ontology_results
    
    # 수동 검색 시 search_term을 Original Label로 사용
    original_label = search_term if search_term else selected_column
    
    # 선택된 것이 없으면 해당 라벨의 모든 매핑 삭제
    if not selected_term_uris:
        st.session_state.mapped_terms = [
            mapping for mapping in st.session_state.mapped_terms 
            if mapping["Original Label"] != original_label
        ]
        if original_label in st.session_state.column_mapping:
            del st.session_state.column_mapping[original_label]
        return
    
    # 현재 데이터 타입 가져오기
    if st.session_state.uploaded_df is not None:
        current_dtype = st.session_state.uploaded_df[selected_column].dtype
        data_type = get_friendly_dtype(current_dtype)
    else:
        data_type = "String"
    
    # 해당 라벨에 대한 기존 매핑 확인 및 제거
    st.session_state.mapped_terms = [
        mapping for mapping in st.session_state.mapped_terms 
        if mapping["Original Label"] != original_label
    ]
    
    mappings = []
    for idx, row in df_results.iterrows():
        if row["Ontology Term URI"] in selected_term_uris:
            ontology_abbr = row["Ontology Name"]
            ontology_info = get_ontology_details(ontology_abbr)
            full_ontology_name = ontology_info['full_name']
            display_ontology_name = f"{full_ontology_name} ({ontology_abbr})"
            
            new_mapping = {
                "Original Label": original_label,
                "Preferred Label": row["Preferred Label"],
                "Ontology Name": display_ontology_name,
                "Ontology Abbr": ontology_abbr,
                "Ontology URI": row["Ontology URI"],
                "Ontology Term URI": row["Ontology Term URI"],
                "Data Type": data_type,
                "Definition": row["Definition"]
            }
            
            mappings.append(new_mapping)
    
    st.session_state.mapped_terms.extend(mappings)
    st.session_state.current_mapping_done = True
    
    st.session_state.column_mapping[original_label] = {
        "selected_terms": selected_term_uris.copy(),
        "mapping_info": mappings
    }

# 값-온톨로지 다중 매핑을 처리하는 콜백 함수
def handle_value_multiple_mapping(selected_indices):
    if st.session_state.value_ontology_results is None:
        return
    
    selected_column = st.session_state.selected_column
    selected_value = st.session_state.selected_unique_value
    df_results = st.session_state.value_ontology_results
    
    if not selected_value:
        return
    
    # 선택된 것이 없으면 해당 값의 매핑 삭제
    if not selected_indices:
        if selected_column in st.session_state.value_ontology_mapping:
            if selected_value in st.session_state.value_ontology_mapping[selected_column]:
                del st.session_state.value_ontology_mapping[selected_column][selected_value]
            if not st.session_state.value_ontology_mapping[selected_column]:
                del st.session_state.value_ontology_mapping[selected_column]
        return
    
    if selected_column not in st.session_state.value_ontology_mapping:
        st.session_state.value_ontology_mapping[selected_column] = {}
    
    # 현재 데이터 타입 가져오기
    if st.session_state.uploaded_df is not None:
        current_dtype = st.session_state.uploaded_df[selected_column].dtype
        data_type = get_friendly_dtype(current_dtype)
    else:
        data_type = "String"
    
    mappings = []
    for selected_index in selected_indices:
        if selected_index < len(df_results):
            selected_row = df_results.iloc[selected_index]
            
            ontology_abbr = selected_row["Ontology Name"]
            ontology_info = get_ontology_details(ontology_abbr)
            full_ontology_name = ontology_info['full_name']
            display_ontology_name = f"{full_ontology_name} ({ontology_abbr})"
            
            new_mapping = {
                "Preferred Label": selected_row["Preferred Label"],
                "Ontology Name": display_ontology_name,
                "Ontology Abbr": ontology_abbr,
                "Ontology URI": selected_row["Ontology URI"],
                "Ontology Term URI": selected_row["Ontology Term URI"],
                "Definition": selected_row["Definition"],
                "Data Type": data_type
            }
            
            mappings.append(new_mapping)
    
    st.session_state.value_ontology_mapping[selected_column][selected_value] = mappings

# 매핑 삭제 함수
def remove_mapping(column_name):
    if column_name:
        st.session_state.mapped_terms = [
            mapping for mapping in st.session_state.mapped_terms 
            if mapping["Original Label"] != column_name
        ]
        
        if column_name in st.session_state.column_mapping:
            del st.session_state.column_mapping[column_name]
        
        if column_name in st.session_state.value_ontology_mapping:
            del st.session_state.value_ontology_mapping[column_name]
            
        st.success(f"Mapping for '{column_name}' has been removed")
        st.rerun()

# 값-온톨로지 매핑 삭제 함수
def remove_value_mapping(column_name, value):
    if column_name and value and column_name in st.session_state.value_ontology_mapping:
        if value in st.session_state.value_ontology_mapping[column_name]:
            del st.session_state.value_ontology_mapping[column_name][value]
            
            st.success(f"Value mapping for '{value}' in column '{column_name}' has been removed")
            st.rerun()

# 체크박스 선택 시 매핑 처리 콜백 (컬럼)
def on_column_checkbox_change():
    search_term = st.session_state.get('manual_search_term', None)
    handle_multiple_mapping(st.session_state.selected_terms, search_term)

# 체크박스 선택 시 매핑 처리 콜백 (값)
def on_value_checkbox_change():
    pass

# 컬럼 선택 시 자동으로 온톨로지 검색 실행하는 콜백
def on_column_select():
    selected_column = st.session_state.column_select
    previous_column = st.session_state.selected_column
    
    if previous_column:
        st.session_state.column_states[previous_column] = {
            "selected_terms": st.session_state.selected_terms.copy(),
            "selected_unique_value": st.session_state.selected_unique_value,
            "value_ontology_results": st.session_state.value_ontology_results,
            "value_term_indices": st.session_state.value_term_indices.copy() if st.session_state.value_term_indices else [],
            "auto_searched": st.session_state.auto_searched
        }
    
    if selected_column != previous_column:
        st.session_state.current_search_term = selected_column
        st.session_state.manual_search_term = None
        
        st.session_state.selected_terms = []
        st.session_state.selected_unique_value = None
        st.session_state.value_ontology_results = None
        st.session_state.value_term_indices = []
        st.session_state.auto_searched = False
        
        if selected_column in st.session_state.column_states:
            saved_state = st.session_state.column_states[selected_column]
            st.session_state.selected_terms = saved_state.get("selected_terms", []).copy()
            st.session_state.selected_unique_value = saved_state.get("selected_unique_value")
            st.session_state.value_ontology_results = saved_state.get("value_ontology_results")
            st.session_state.value_term_indices = saved_state.get("value_term_indices", []).copy()
            st.session_state.auto_searched = saved_state.get("auto_searched", False)
    
    st.session_state.selected_column = selected_column
    st.session_state.current_mapping_done = False
    
    if selected_column and st.session_state.selected_ontologies and selected_column != previous_column:
        from ontology import search_ontology, search_ontology_for_value
        
        loading_container = st.empty()
        with loading_container:
            show_loading_overlay(f"Loading ontology terms for column '{selected_column}'...")
        
        time.sleep(1)
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
                    
                    time.sleep(1)
                    search_ontology_for_value(default_value)
                    loading_container.empty()
                    
                    st.session_state.auto_searched = True

# 값 선택 콜백 함수
def on_value_select():
    selected_value = st.session_state.value_select
    previous_value = st.session_state.selected_unique_value
    
    if previous_value and st.session_state.value_term_indices:
        column_key = st.session_state.selected_column
        if column_key not in st.session_state.value_term_indices_by_value:
            st.session_state.value_term_indices_by_value[column_key] = {}
        st.session_state.value_term_indices_by_value[column_key][previous_value] = st.session_state.value_term_indices.copy()
    
    st.session_state.selected_unique_value = selected_value
    
    column_key = st.session_state.selected_column
    if (column_key in st.session_state.value_term_indices_by_value and 
        selected_value in st.session_state.value_term_indices_by_value[column_key]):
        st.session_state.value_term_indices = st.session_state.value_term_indices_by_value[column_key][selected_value].copy()
    else:
        st.session_state.value_term_indices = []
    
    if selected_value and selected_value != previous_value:
        from ontology import search_ontology_for_value
        
        loading_container = st.empty()
        with loading_container:
            show_loading_overlay(f"Loading ontology terms for value '{selected_value}'...")
        
        time.sleep(1)
        search_ontology_for_value(selected_value)
        loading_container.empty()

# 개별 용어 매핑 삭제 함수 (버그 수정됨)
def remove_term_mapping(column_name, term_uri):
    if not (column_name and term_uri):
        return

    # 1) 컬럼 매핑 정보에서 제거
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

    # 2) 전역 selected_terms 에서 제거
    if "selected_terms" in st.session_state and term_uri in st.session_state.selected_terms:
        st.session_state.selected_terms.remove(term_uri)

    # 3) 검색어별 체크박스 상태에서도 제거 (모든 키에서!)
    if "search_terms_selections" in st.session_state:
        for key in list(st.session_state.search_terms_selections.keys()):
            if term_uri in st.session_state.search_terms_selections[key]:
                st.session_state.search_terms_selections[key].remove(term_uri)

    # 4) 전체 mapped_terms 리스트에서 제거
    if "mapped_terms" in st.session_state:
        st.session_state.mapped_terms = [
            m for m in st.session_state.mapped_terms
            if not (
                m.get("Original Label") == column_name
                and m.get("Ontology Term URI") == term_uri
            )
        ]
    
    # 5) column_states에서도 해당 term_uri 제거
    if "column_states" in st.session_state and column_name in st.session_state.column_states:
        saved_terms = st.session_state.column_states[column_name].get("selected_terms", [])
        if term_uri in saved_terms:
            saved_terms.remove(term_uri)

    # 6) 삭제 카운터 증가 (체크박스 키를 새로 생성하게 함)
    if "column_checkbox_counter" not in st.session_state:
        st.session_state.column_checkbox_counter = 0
    st.session_state.column_checkbox_counter += 1

    st.success(f"Term mapping for '{column_name}' has been deleted")
    st.rerun()

# 개별 값 매핑 삭제 함수 (버그 수정됨)
def remove_individual_value_mapping(column_name, value, term_uri):
    if not (column_name and value and term_uri):
        return
    
    if column_name in st.session_state.value_ontology_mapping:
        if value in st.session_state.value_ontology_mapping[column_name]:
            # 삭제할 인덱스 찾기
            deleted_index = None
            if st.session_state.value_ontology_results is not None:
                df_results = st.session_state.value_ontology_results
                for i in range(len(df_results)):
                    if df_results.iloc[i]['Ontology Term URI'] == term_uri:
                        deleted_index = i
                        break
            
            # 매핑 목록에서 해당 URI를 가진 항목만 제거
            if isinstance(st.session_state.value_ontology_mapping[column_name][value], list):
                st.session_state.value_ontology_mapping[column_name][value] = [
                    mapping for mapping in st.session_state.value_ontology_mapping[column_name][value]
                    if mapping["Ontology Term URI"] != term_uri
                ]
                
                if not st.session_state.value_ontology_mapping[column_name][value]:
                    del st.session_state.value_ontology_mapping[column_name][value]
                    
                if not st.session_state.value_ontology_mapping[column_name]:
                    del st.session_state.value_ontology_mapping[column_name]
            
            # value_term_indices에서 삭제된 인덱스 제거
            if deleted_index is not None and deleted_index in st.session_state.value_term_indices:
                st.session_state.value_term_indices.remove(deleted_index)
            
            # value_term_indices_by_value에서도 제거
            if column_name in st.session_state.value_term_indices_by_value:
                if value in st.session_state.value_term_indices_by_value[column_name]:
                    if deleted_index is not None and deleted_index in st.session_state.value_term_indices_by_value[column_name][value]:
                        st.session_state.value_term_indices_by_value[column_name][value].remove(deleted_index)
            
            # column_states에서도 value_term_indices 업데이트
            if "column_states" in st.session_state and column_name in st.session_state.column_states:
                saved_indices = st.session_state.column_states[column_name].get("value_term_indices", [])
                if deleted_index is not None and deleted_index in saved_indices:
                    saved_indices.remove(deleted_index)
            
            # 삭제 카운터 증가 (체크박스 키를 새로 생성하게 함)
            if "value_checkbox_counter" not in st.session_state:
                st.session_state.value_checkbox_counter = 0
            st.session_state.value_checkbox_counter += 1
                
            st.success(f"Value term mapping for '{value}' in column '{column_name}' has been deleted")
            st.rerun()
