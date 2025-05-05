import streamlit as st
import urllib.parse
from ontology import search_ontology_for_value, search_bioportal_all, get_ontology_details
from mapping import on_value_select, on_value_checkbox_change, handle_value_multiple_mapping

# 값 매핑 섹션 렌더링
def render_value_mapping_section():
    st.markdown('<div class="section-header section-blue">Select Ontology Term for Value</div>', unsafe_allow_html=True)
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df
    
    # 현재 데이터 타입 확인
    current_dtype = df[selected_col].dtype
    dtype_name = str(current_dtype)
    
    # 문자열 또는 카테고리 타입인 경우에만 값-온톨로지 매핑 UI 표시
    if dtype_name == 'object' or dtype_name.startswith('string') or dtype_name == 'category':
        # 고유 값 가져오기 (최대 5개로 제한)
        unique_values = df[selected_col].dropna().unique()
        
        # 알파벳 순으로 정렬
        unique_values.sort()
        
        # 고유 값이 있는 경우에만 UI 표시
        if len(unique_values) > 0:
            st.write(f"Select a unique value from column '{selected_col}' to map to an ontology term:")
            
            # 값 옵션 (최대 5개로 제한)
            value_options = unique_values[:5].tolist()
            
            # 기본값 설정 및 자동 검색
            if st.session_state.selected_unique_value is None or st.session_state.selected_unique_value not in value_options:
                default_value = value_options[0] if value_options else None
                st.session_state.selected_unique_value = default_value
                if default_value and st.session_state.selected_ontologies:
                    search_ontology_for_value(default_value)
                    st.session_state.auto_searched = True
            
            # 현재 선택된 값 인덱스 계산
            default_index = value_options.index(st.session_state.selected_unique_value) if st.session_state.selected_unique_value in value_options else 0
            
            # 드롭다운으로 고유 값 선택
            selected_value = st.selectbox(
                "Select value to map:",
                value_options,
                index=default_index,
                key="value_select",
                on_change=on_value_select
            )
            
            # 검색 결과가 있는 경우 표시
            if st.session_state.value_ontology_results is not None:
                # 현재 선택된 값 사용 (기본값 포함)
                selected_value = st.session_state.selected_unique_value
                st.write(f"### Select ontology terms for value: '{selected_value}'")
                
                # 체크박스와 정보를 두 열로 표시
                col1, col2 = st.columns([3, 2])
                
                with col1:
                    # 스크롤 가능한 컨테이너 사용
                    with st.container(height=300):
                        st.write(f"Select one or more terms that match '{selected_value}':")
                        df_results = st.session_state.value_ontology_results
                        
                        # 체크박스로 다중 선택 지원
                        for i in range(len(df_results)):
                            # 이전에 선택되었는지 확인 (기본값은 False)
                            is_checked = i in st.session_state.value_term_indices
                            
                            # 체크박스 생성
                            term_label = f"{df_results.iloc[i]['Preferred Label']} ({df_results.iloc[i]['Ontology Name']})"
                            if st.checkbox(
                                term_label,
                                value=is_checked,
                                key=f"val_cb_{i}",
                                on_change=on_value_checkbox_change
                            ):
                                # 체크박스가 변경되면 자동으로 인덱스 업데이트
                                if i not in st.session_state.value_term_indices:
                                    st.session_state.value_term_indices.append(i)
                                    # 자동 매핑 적용
                                    handle_value_multiple_mapping(st.session_state.value_term_indices)
                            else:
                                # 체크 해제되면 인덱스에서 제거
                                if i in st.session_state.value_term_indices:
                                    st.session_state.value_term_indices.remove(i)
                                    # 자동 매핑 적용
                                    handle_value_multiple_mapping(st.session_state.value_term_indices)
                
                with col2:
                    # 선택된 모든 항목 정보 표시 (모든 항목을 각각 상세히 표시)
                    if st.session_state.value_term_indices:
                        """st.markdown(f"<div style='font-weight:bold;'>Selected Terms: {len(st.session_state.value_term_indices)}</div>", unsafe_allow_html=True)"""
                        
                        # 각 선택된 항목에 대한 상세 정보 표시
                        for idx in st.session_state.value_term_indices:
                            if idx < len(df_results):
                                selected_row = df_results.iloc[idx]
                                ontology_abbr = selected_row['Ontology Name']
                                
                                # 온톨로지 전체 이름 가져오기
                                ontology_info = get_ontology_details(ontology_abbr)
                                full_ontology_name = ontology_info['full_name']
                                display_ontology_name = f"{full_ontology_name} ({ontology_abbr})"
                                
                                # 각 항목의 상세 정보 표시
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
                        # 버튼 클릭시 먼저 선택 인덱스 초기화
                        st.session_state.value_term_indices = []
                        
                        # 모든 온톨로지에서 검색
                        search_success = search_bioportal_all(value_search_term)
                        if search_success:
                            st.success(f"Search results for '{value_search_term}' found in BioPortal.")
                            st.rerun()  # 결과를 표시하기 위해 페이지 새로고침
                        else:
                            st.warning(f"No results found for '{value_search_term}' in BioPortal.")
                    else:
                        st.warning("Please enter a search term.")
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("No unique values found in this column.")
    else:
        # 문자열 타입이 아닌 경우 메시지 표시
        st.info("Only string values just for now!")