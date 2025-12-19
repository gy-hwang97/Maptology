import streamlit as st
import urllib.parse
import time
from ontology import search_ontology, search_bioportal_all_columns, get_ontology_details
from mapping import on_column_select, on_column_checkbox_change, handle_multiple_mapping
from loading_overlay import show_loading_overlay

# 컬럼 선택 및 온톨로지 매핑 섹션 렌더링
def render_column_mapping_section():
    st.write("### Map Ontology Terms for Columns")
    st.caption("Now that you have selected one or more ontologies, it is time to search for ontology term(s) for each column and map them to each other. Start by selecting a column name from the dropdown below.")
    
    # 삭제 카운터 초기화
    if "column_checkbox_counter" not in st.session_state:
        st.session_state.column_checkbox_counter = 0
    
    if st.session_state.uploaded_df is not None:
        columns = list(st.session_state.uploaded_df.columns)
        
        # 파일 첫 로드 시 자동으로 첫 번째 컬럼 선택 및 검색
        if st.session_state.first_load and columns:
            first_column = columns[0]
            st.session_state.selected_column = first_column
            st.session_state.column_select = first_column
            
            loading_container = st.empty()
            with loading_container:
                show_loading_overlay(f"Loading ontology terms for column '{first_column}'...")
            
            time.sleep(1)
            search_ontology(first_column)
            loading_container.empty()
            
            st.session_state.first_load = False
        
        selected_column = st.selectbox(
            "Select a column to map", 
            columns, 
            key="column_select",
            on_change=on_column_select
        )
        
        if selected_column:
            st.session_state.selected_column = selected_column
            
            # 이미 매핑된 컬럼인 경우 해당 정보 불러오기
            if selected_column in st.session_state.column_mapping:
                saved_terms = st.session_state.column_mapping[selected_column].get("selected_terms", [])
                st.session_state.selected_terms = saved_terms.copy()
                st.session_state.current_mapping_done = True
        
        # 온톨로지 검색 결과가 있을 때만 선택 UI 표시
        if st.session_state.filtered_ontology_results is not None and len(st.session_state.filtered_ontology_results) > 0:
            st.write("### Select ontology terms")
            
            col1, col2 = st.columns([3, 2])

            with col1:
                with st.container(height=300):
                    st.write("Select one or more terms that match your column:")
                    df = st.session_state.filtered_ontology_results
                    
                    current_search = st.session_state.get('current_search_term', st.session_state.selected_column)
                    
                    if current_search not in st.session_state.search_terms_selections:
                        st.session_state.search_terms_selections[current_search] = []
                    
                    # 현재 selected_terms를 기반으로 체크 상태 결정
                    current_selected_uris = set(st.session_state.selected_terms)
                    
                    for i in range(len(df)):
                        term_uri = df.iloc[i]['Ontology Term URI']
                        
                        # selected_terms 기반으로 체크 상태 결정
                        is_checked = term_uri in current_selected_uris
                        
                        # 체크박스 고유 키 생성 - 카운터 포함
                        counter = st.session_state.column_checkbox_counter
                        unique_key = f"col_cb_{current_search}_{i}_{counter}"

                        term_label = f"{df.iloc[i]['Preferred Label']} ({df.iloc[i]['Ontology Name']})"
                        
                        checkbox_result = st.checkbox(
                            term_label,
                            value=is_checked,
                            key=unique_key,
                            on_change=on_column_checkbox_change
                        )
                        
                        # 체크박스 상태 변경 감지 및 처리
                        if checkbox_result != is_checked:
                            if checkbox_result:
                                # 새로 체크됨
                                if term_uri not in st.session_state.search_terms_selections[current_search]:
                                    st.session_state.search_terms_selections[current_search].append(term_uri)
                                if term_uri not in st.session_state.selected_terms:
                                    st.session_state.selected_terms.append(term_uri)
                                    handle_multiple_mapping(st.session_state.selected_terms, current_search)
                            else:
                                # 체크 해제됨
                                if term_uri in st.session_state.search_terms_selections[current_search]:
                                    st.session_state.search_terms_selections[current_search].remove(term_uri)
                                if term_uri in st.session_state.selected_terms:
                                    st.session_state.selected_terms.remove(term_uri)
                                    handle_multiple_mapping(st.session_state.selected_terms, current_search)
            
            with col2:
                if st.session_state.selected_terms:
                    for term_uri in st.session_state.selected_terms:
                        matching_rows = df[df['Ontology Term URI'] == term_uri]
                        if not matching_rows.empty:
                            selected_row = matching_rows.iloc[0]
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
            
            # 검색 박스
            st.markdown('<div class="section-header section-green">Search BioPortal for term:</div>', unsafe_allow_html=True)
            st.markdown('<div class="search-box">', unsafe_allow_html=True)
            column_search_term = st.text_input("Enter search term for column mapping", key="manual_column_search")
            if st.button("Search All Ontologies", key="btn_column_search"):
                if column_search_term:
                    st.session_state.manual_search_term = column_search_term
                    st.session_state.search_terms_selections[column_search_term] = []
                    st.session_state.current_search_term = column_search_term
                    st.session_state.selected_terms = []
                    
                    loading_container = st.empty()
                    with loading_container:
                        show_loading_overlay(f"Searching BioPortal for '{column_search_term}'...")
                    
                    time.sleep(1.5)
                    
                    search_success = search_bioportal_all_columns(column_search_term)
                    
                    loading_container.empty()
                        
                    if search_success:
                        st.success(f"✅ Search results found for '{column_search_term}' in BioPortal.")
                        st.rerun()
                    else:
                        st.warning(f"⚠️ No results found for '{column_search_term}' in BioPortal.")
                else:
                    st.warning("Please enter a search term.")
            st.markdown('</div>', unsafe_allow_html=True)
