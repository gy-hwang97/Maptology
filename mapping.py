import streamlit as st
from ontology import get_ontology_details
from utils import get_friendly_dtype

# 다중 매핑을 처리하는 콜백 함수 (인덱스 대신 선택된 용어의 URI 리스트를 인자로 받음)
def handle_multiple_mapping(selected_term_uris, search_term=None):
    if not selected_term_uris or st.session_state.filtered_ontology_results is None:
        return
    
    selected_column = st.session_state.selected_column
    df_results = st.session_state.filtered_ontology_results
    
    # 현재 데이터 타입 가져오기
    if st.session_state.uploaded_df is not None:
        current_dtype = st.session_state.uploaded_df[selected_column].dtype
        data_type = get_friendly_dtype(current_dtype)
    else:
        data_type = "String"  # 기본값
    
    # 수동 검색 시 search_term을 Original Label로 사용
    original_label = search_term if search_term else selected_column
    
    # 해당 라벨에 대한 기존 매핑 확인 및 제거
    st.session_state.mapped_terms = [
        mapping for mapping in st.session_state.mapped_terms 
        if mapping["Original Label"] != original_label
    ]
    
    mappings = []
    # df_results의 각 행의 URI가 선택된 리스트에 있는지 확인
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
    
    # 모든 매핑을 mapped_terms에 추가
    st.session_state.mapped_terms.extend(mappings)
    st.session_state.current_mapping_done = True
    
    # 컬럼별 매핑 정보 저장
    st.session_state.column_mapping[original_label] = {
        "selected_terms": selected_term_uris,
        "mapping_info": mappings
    }

# 값-온톨로지 다중 매핑을 처리하는 콜백 함수 (수정됨)
def handle_value_multiple_mapping(selected_indices):
    if not selected_indices or st.session_state.value_ontology_results is None:
        return
    
    selected_column = st.session_state.selected_column
    selected_value = st.session_state.selected_unique_value
    df_results = st.session_state.value_ontology_results
    
    if selected_column not in st.session_state.value_ontology_mapping:
        st.session_state.value_ontology_mapping[selected_column] = {}
    
    if not selected_value:
        return
    
    if selected_value in st.session_state.value_ontology_mapping[selected_column]:
        st.session_state.value_ontology_mapping[selected_column][selected_value] = []
    
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
                "Definition": selected_row["Definition"]
            }
            
            mappings.append(new_mapping)
    
    st.session_state.value_ontology_mapping[selected_column][selected_value] = mappings

# 매핑 삭제 함수 (변경 없음)
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

# 값-온톨로지 매핑 삭제 함수 (변경 없음)
def remove_value_mapping(column_name, value):
    if column_name and value and column_name in st.session_state.value_ontology_mapping:
        if value in st.session_state.value_ontology_mapping[column_name]:
            del st.session_state.value_ontology_mapping[column_name][value]
            
            st.success(f"Value mapping for '{value}' in column '{column_name}' has been removed")
            st.rerun()

# 체크박스 선택 시 매핑 처리 콜백 (컬럼) - 빈 함수
def on_column_checkbox_change():
    # 수동 검색어 가져오기
    search_term = st.session_state.get('manual_search_term', None)
    # 수동 검색어가 있으면 original_label로 사용
    handle_multiple_mapping(st.session_state.selected_terms, search_term)

# 체크박스 선택 시 매핑 처리 콜백 (값) - 빈 함수
def on_value_checkbox_change():
    pass

# 컬럼 선택 시 자동으로 온톨로지 검색 실행하는 콜백
def on_column_select():
    selected_column = st.session_state.column_select
    previous_column = st.session_state.selected_column
    
    if previous_column:
        st.session_state.column_states[previous_column] = {
            "selected_terms": st.session_state.selected_terms,
            "selected_unique_value": st.session_state.selected_unique_value,
            "value_ontology_results": st.session_state.value_ontology_results,
            "value_term_indices": st.session_state.value_term_indices,
            "auto_searched": st.session_state.auto_searched
        }
    
    if selected_column != previous_column:
        # 새 컬럼 선택 시 현재 검색어 초기화
        st.session_state.current_search_term = selected_column
        st.session_state.manual_search_term = None
        
        st.session_state.selected_terms = []
        st.session_state.selected_unique_value = None
        st.session_state.value_ontology_results = None
        st.session_state.value_term_indices = []
        st.session_state.auto_searched = False
        
        if selected_column in st.session_state.column_states:
            saved_state = st.session_state.column_states[selected_column]
            st.session_state.selected_terms = saved_state.get("selected_terms", [])
            st.session_state.selected_unique_value = saved_state.get("selected_unique_value")
            st.session_state.value_ontology_results = saved_state.get("value_ontology_results")
            st.session_state.value_term_indices = saved_state.get("value_term_indices", [])
            st.session_state.auto_searched = saved_state.get("auto_searched", False)
    
    st.session_state.selected_column = selected_column
    st.session_state.current_mapping_done = False
    
    if selected_column and st.session_state.selected_ontologies:
        from ontology import search_ontology, search_ontology_for_value
        search_ontology(selected_column)
        
        if st.session_state.uploaded_df is not None and not st.session_state.auto_searched:
            current_dtype = st.session_state.uploaded_df[selected_column].dtype
            dtype_name = str(current_dtype)
            
            if dtype_name == 'object' or dtype_name.startswith('string') or dtype_name == 'category':
                unique_values = st.session_state.uploaded_df[selected_column].dropna().unique()
                unique_values.sort()
                
                if len(unique_values) > 0:
                    default_value = unique_values[0]
                    st.session_state.selected_unique_value = default_value
                    search_ontology_for_value(default_value)
                    st.session_state.auto_searched = True

# 값 선택 콜백 함수 (수정됨 - 버그 수정)
def on_value_select():
    selected_value = st.session_state.value_select
    previous_value = st.session_state.selected_unique_value
    
    # 이전 값의 선택사항을 저장
    if previous_value and st.session_state.value_term_indices:
        column_key = st.session_state.selected_column
        if column_key not in st.session_state.value_term_indices_by_value:
            st.session_state.value_term_indices_by_value[column_key] = {}
        st.session_state.value_term_indices_by_value[column_key][previous_value] = st.session_state.value_term_indices.copy()
    
    # 새 값으로 업데이트
    st.session_state.selected_unique_value = selected_value
    
    # 새 값의 이전 선택사항 복원
    column_key = st.session_state.selected_column
    if (column_key in st.session_state.value_term_indices_by_value and 
        selected_value in st.session_state.value_term_indices_by_value[column_key]):
        st.session_state.value_term_indices = st.session_state.value_term_indices_by_value[column_key][selected_value].copy()
    else:
        st.session_state.value_term_indices = []
    
    # 새 값에 대한 검색 실행
    if selected_value:
        from ontology import search_ontology_for_value
        search_ontology_for_value(selected_value)

# 타입 변경시 호출되는 콜백 함수 (변경 없음)
def on_type_change():
    new_type = st.session_state.type_select
    selected_col = st.session_state.selected_column
    from utils import change_column_type
    change_column_type(selected_col, new_type, False, None)

# 개별 용어 매핑 삭제 함수
def remove_term_mapping(column_name, term_uri):
    if column_name and term_uri:
        # 컬럼에 매핑된 용어 목록에서 해당 URI를 가진 항목 제거
        if column_name in st.session_state.column_mapping:
            # 선택된 용어 목록에서 제거
            if term_uri in st.session_state.column_mapping[column_name].get("selected_terms", []):
                st.session_state.column_mapping[column_name]["selected_terms"].remove(term_uri)
            
            # 매핑 정보에서 제거
            st.session_state.column_mapping[column_name]["mapping_info"] = [
                mapping for mapping in st.session_state.column_mapping[column_name].get("mapping_info", [])
                if mapping["Ontology Term URI"] != term_uri
            ]
            
            # 전체 매핑 목록에서도 제거
            st.session_state.mapped_terms = [
                mapping for mapping in st.session_state.mapped_terms 
                if not (mapping["Original Label"] == column_name and mapping["Ontology Term URI"] == term_uri)
            ]
            
            # 매핑이 모두 삭제된 경우 컬럼 매핑 자체 삭제
            if not st.session_state.column_mapping[column_name]["mapping_info"]:
                del st.session_state.column_mapping[column_name]
                
            st.success(f"'{column_name}'의 용어 매핑이 삭제되었습니다")
            st.rerun()
            
def remove_individual_value_mapping(column_name, value, term_uri):
    if column_name and value and term_uri:
        # 해당 컬럼에 대한 값 매핑이 있는지 확인
        if column_name in st.session_state.value_ontology_mapping:
            # 해당 값에 대한 매핑이 있는지 확인
            if value in st.session_state.value_ontology_mapping[column_name]:
                # 매핑 목록에서 해당 URI를 가진 항목만 제거
                if isinstance(st.session_state.value_ontology_mapping[column_name][value], list):
                    st.session_state.value_ontology_mapping[column_name][value] = [
                        mapping for mapping in st.session_state.value_ontology_mapping[column_name][value]
                        if mapping["Ontology Term URI"] != term_uri
                    ]
                    
                    # 만약 매핑이 모두 제거되었다면 해당 값 엔트리 삭제
                    if not st.session_state.value_ontology_mapping[column_name][value]:
                        del st.session_state.value_ontology_mapping[column_name][value]
                        
                    # 만약 컬럼에 대한 매핑이 모두 제거되었다면 해당 컬럼 엔트리 삭제
                    if not st.session_state.value_ontology_mapping[column_name]:
                        del st.session_state.value_ontology_mapping[column_name]
                        
                    st.success(f"'{column_name}' 컬럼의 '{value}' 값에 대한 용어 매핑이 삭제되었습니다")
                    st.rerun()
