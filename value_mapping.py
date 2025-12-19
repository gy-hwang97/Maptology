import streamlit as st
import urllib.parse
import time
from ontology import search_ontology_for_value, search_bioportal_all, get_ontology_details
from mapping import on_value_select, on_value_checkbox_change, handle_value_multiple_mapping
from loading_overlay import show_loading_overlay

# 값 매핑 섹션 렌더링
def render_value_mapping_section():
    st.write("### Map Ontology Terms for Values")
    st.caption("Now you can map ontology term(s) to each data value. Start by selecting a value from the dropdown below.")
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df
    
    # 삭제 카운터 초기화
    if "value_checkbox_counter" not in st.session_state:
        st.session_state.value_checkbox_counter = 0
    
    # 현재 데이터 타입 확인
    current_dtype = df[selected_col].dtype
    dtype_name = str(current_dtype)
    
    # 문자열 또는 카테고리 타입인 경우에만 값-온톨로지 매핑 UI 표시
    if dtype_name == 'object' or dtype_name.startswith('string') or dtype_name == 'category':
        unique_values = df[selected_col].dropna().unique()
        unique_values.sort()
        
        if len(unique_values) > 0:
            st.write(f"Select a unique value from column '{selected_col}' to map to an ontology term:")
            
            value_options = unique_values[:5].tolist()
            
            if st.session_state.selected_unique_value is None or st.session_state.selected_unique_value not in value_options:
                default_value = value_options[0] if value_options else None
                st.session_state.selected_unique_value = default_value
                if default_value and st.session_state.selected_ontologies:
                    loading_container = st.empty()
                    with loading_container:
                        show_loading_overlay(f"Loading ontology terms for value '{default_value}'...")
                    
                    time.sleep(1)
                    search_ontology_for_value(default_value)
                    loading_container.empty()
                    
                    st.session_state.auto_searched = True
            
            default_index = value_options.index(st.session_state.selected_unique_value) if st.session_state.selected_unique_value in value_options else 0
            
            selected_value = st.selectbox(
                "Select value to map:",
                value_options,
                index=default_index,
                key="value_select",
                on_change=on_value_select
            )
            
            if st.session_state.value_ontology_results is not None:
                selected_value = st.session_state.selected_unique_value
                st.write(f"### Select ontology terms for value: '{selected_value}'")
                
                col1, col2 = st.columns([3, 2])
                
                with col1:
                    with st.container(height=300):
                        st.write(f"Select one or more terms that match '{selected_value}':")
                        df_results = st.session_state.value_ontology_results
                        
                        # 현재 선택된 인덱스 집합
                        current_selected_indices = set(st.session_state.value_term_indices)
                        
                        for i in range(len(df_results)):
                            is_checked = i in current_selected_indices
                            
                            term_label = f"{df_results.iloc[i]['Preferred Label']} ({df_results.iloc[i]['Ontology Name']})"
                            
                            # 체크박스 고유 키 생성 - 카운터 포함
                            counter = st.session_state.value_checkbox_counter
                            checkbox_key = f"val_cb_{selected_value}_{i}_{counter}"
                            
                            checkbox_result = st.checkbox(
                                term_label,
                                value=is_checked,
                                key=checkbox_key,
                                on_change=on_value_checkbox_change
                            )
                            
                            # 체크박스 상태 변경 감지 및 처리
                            if checkbox_result != is_checked:
                                if checkbox_result:
                                    # 새로 체크됨
                                    if i not in st.session_state.value_term_indices:
                                        st.session_state.value_term_indices.append(i)
                                        column_key = st.session_state.selected_column
                                        if column_key not in st.session_state.value_term_indices_by_value:
                                            st.session_state.value_term_indices_by_value[column_key] = {}
                                        st.session_state.value_term_indices_by_value[column_key][selected_value] = st.session_state.value_term_indices.copy()
                                        handle_value_multiple_mapping(st.session_state.value_term_indices)
                                else:
                                    # 체크 해제됨
                                    if i in st.session_state.value_term_indices:
                                        st.session_state.value_term_indices.remove(i)
                                        column_key = st.session_state.selected_column
                                        if column_key not in st.session_state.value_term_indices_by_value:
                                            st.session_state.value_term_indices_by_value[column_key] = {}
                                        st.session_state.value_term_indices_by_value[column_key][selected_value] = st.session_state.value_term_indices.copy()
                                        handle_value_multiple_mapping(st.session_state.value_term_indices)
                
                with col2:
                    if st.session_state.value_term_indices:
                        for idx in st.session_state.value_term_indices:
                            if idx < len(df_results):
                                selected_row = df_results.iloc[idx]
                                ontology_abbr = selected_row['Ontology Name']
                                
                                ontology_info = get_ontology_details(ontology_abbr)
                                full_ontology_name = ontology_info['full_name']
                                display_ontology_name = f"{full_ontology_name} ({ontology_abbr})"
                                
                                st.markdown(f"""
                                <div class="term-box">
                                    <div class="term-label">Term: {selected_row['Preferred Label']}</div>
                                    <div class="term-label">Ontology: <a href="https://bioportal.bioontology.org/ontologies/{ontology_abbr}" target="_blank">{display_ontology_name}</a></div>
                                    <div class="term-definition">Definition: {selected_row['Definition']}</div>
                                    <div style="margin-top:8px; font-size:0.8em;">
                                        <a href="https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(selected_row['Ontology Term URI'], safe='')}" target="_blank">View term details</a>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                    else:
                        st.info("No terms selected yet. Check one or more terms from the left panel.")
                
                # 값 검색 박스
                st.markdown('<div class="section-header section-green">Search BioPortal for term:</div>', unsafe_allow_html=True)
                st.markdown('<div class="search-box">', unsafe_allow_html=True)
                value_search_term = st.text_input("Enter search term for value mapping", key="manual_value_search")
                if st.button("Search All Ontologies", key="btn_value_search"):
                    if value_search_term:
                        if st.session_state.selected_unique_value and st.session_state.value_term_indices:
                            column_key = st.session_state.selected_column
                            if column_key not in st.session_state.value_term_indices_by_value:
                                st.session_state.value_term_indices_by_value[column_key] = {}
                            st.session_state.value_term_indices_by_value[column_key][st.session_state.selected_unique_value] = st.session_state.value_term_indices.copy()
                        
                        st.session_state.value_term_indices = []
                        
                        loading_container = st.empty()
                        with loading_container:
                            show_loading_overlay(f"Searching BioPortal for '{value_search_term}'...")
                        
                        time.sleep(1.5)
                        search_success = search_bioportal_all(value_search_term)
                        loading_container.empty()
                            
                        if search_success:
                            st.success(f"✅ Search results found for '{value_search_term}' in BioPortal.")
                            st.rerun()
                        else:
                            st.warning(f"⚠️ No results found for '{value_search_term}' in BioPortal.")
                    else:
                        st.warning("Please enter a search term.")
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("No unique values found in this column.")
    else:
        st.info("Only string values just for now!")
