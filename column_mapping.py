import streamlit as st
import urllib.parse
from ontology import search_ontology, search_bioportal_all_columns, get_ontology_details
from mapping import on_column_select, on_column_checkbox_change, handle_multiple_mapping

# 컬럼 선택 및 온톨로지 매핑 섹션 렌더링
def render_column_mapping_section():
    st.markdown('<div class="section-header section-red">Select Ontology Term for Column</div>', unsafe_allow_html=True)
    
    if st.session_state.uploaded_df is not None:
        columns = list(st.session_state.uploaded_df.columns)
        
        # 파일 첫 로드 시 자동으로 첫 번째 컬럼 선택 및 검색
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
            
            # 이미 매핑된 컬럼인 경우 해당 정보 불러오기 (이제 고유 식별자를 사용)
            if selected_column in st.session_state.column_mapping:
                st.session_state.selected_terms = st.session_state.column_mapping[selected_column].get("selected_terms", [])
                st.session_state.current_mapping_done = True
        
        # 온톨로지 검색 결과가 있을 때만 선택 UI 표시
        if st.session_state.filtered_ontology_results is not None and len(st.session_state.filtered_ontology_results) > 0:
            st.write("### Select ontology terms")
            
            # 라디오 버튼과 정보를 두 열로 표시
            col1, col2 = st.columns([3, 2])

            with col1:
                # 스크롤 가능한 컨테이너 사용
                with st.container(height=300):
                    st.write("Select one or more terms that match your column:")
                    df = st.session_state.filtered_ontology_results
                    
                    # 체크박스로 다중 선택 지원
                    for i in range(len(df)):
                        # 각 행의 고유 식별자(URI) 추출
                        term_uri = df.iloc[i]['Ontology Term URI']
                        
                        # 현재 검색어 확인 (컬럼 이름 또는 수동 검색어)
                        current_search = st.session_state.get('current_search_term', st.session_state.selected_column)
                        
                        # 이 검색어에 대한 선택 목록이 없으면 초기화
                        if current_search not in st.session_state.search_terms_selections:
                            st.session_state.search_terms_selections[current_search] = []
                        
                        # 현재 검색어의 선택 목록에서 이 용어가 선택되었는지 확인
                        is_checked = term_uri in st.session_state.search_terms_selections[current_search]
                        
                        # 체크박스 고유 키 생성
                        unique_key = f"col_cb_{current_search}_{i}"

                        term_label = f"{df.iloc[i]['Preferred Label']} ({df.iloc[i]['Ontology Name']})"
                        if st.checkbox(
                            term_label,
                            value=is_checked,
                            key=unique_key,
                            on_change=on_column_checkbox_change
                        ):
                            # 이 용어를 현재 검색어의 선택 목록과 전체 선택 목록에 추가
                            if term_uri not in st.session_state.search_terms_selections[current_search]:
                                st.session_state.search_terms_selections[current_search].append(term_uri)
                            if term_uri not in st.session_state.selected_terms:
                                st.session_state.selected_terms.append(term_uri)
                                handle_multiple_mapping(st.session_state.selected_terms, current_search)
                        else:
                            # 이 용어를 현재 검색어의 선택 목록과 전체 선택 목록에서 제거
                            if term_uri in st.session_state.search_terms_selections[current_search]:
                                st.session_state.search_terms_selections[current_search].remove(term_uri)
                            if term_uri in st.session_state.selected_terms:
                                st.session_state.selected_terms.remove(term_uri)
                                handle_multiple_mapping(st.session_state.selected_terms, current_search)
            
            with col2:
                # 선택된 모든 항목 정보 표시 (현재 결과 목록에서 해당 URI에 해당하는 항목 찾기)
                if st.session_state.selected_terms:
                    """st.markdown(f"<div style='font-weight:bold;'>Selected Terms: {len(st.session_state.selected_terms)}</div>", unsafe_allow_html=True)"""
                    
                    for term_uri in st.session_state.selected_terms:
                        # 현재 결과(df)에서 해당 URI를 갖는 행을 검색
                        matching_rows = df[df['Ontology Term URI'] == term_uri]
                        if not matching_rows.empty:
                            selected_row = matching_rows.iloc[0]
                            ontology_abbr = selected_row['Ontology Name']
                            
                            # 온톨로지 전체 이름 가져오기
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
                    # 검색어를 세션 상태에 저장
                    st.session_state.manual_search_term = column_search_term
                    
                    # 이 검색어에 대한 별도의 선택 상태 초기화
                    st.session_state.search_terms_selections[column_search_term] = []
                    
                    # 현재 활성화된 검색어를 세션 상태에 저장
                    st.session_state.current_search_term = column_search_term
                    
                    # 현재 선택된 항목은 새 검색을 위해 초기화
                    st.session_state.selected_terms = []
                    
                    # 선택된 온톨로지에서만 검색
                    search_success = search_bioportal_all_columns(column_search_term)
                    if search_success:
                        st.success(f"BioPortal에서 '{column_search_term}'에 대한 검색 결과를 찾았습니다.")
                        st.rerun()
                    else:
                        st.warning(f"BioPortal에서 '{column_search_term}'에 대한 결과를 찾을 수 없습니다.")
                else:
                    st.warning("검색어를 입력해주세요.")
            st.markdown('</div>', unsafe_allow_html=True)