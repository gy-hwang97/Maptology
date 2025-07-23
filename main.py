import streamlit as st
import pandas as pd
import time

from utils import initialize_session, add_css
from components import render_header
from ontology import render_ontology_selection, get_available_ontologies, search_ontology
from column_mapping import render_column_mapping_section
from data_values import render_data_values_section
from value_mapping import render_value_mapping_section
from mapping_display import render_mapped_terms, render_value_mappings, render_download_buttons
from loading_overlay import show_loading_overlay

# Streamlit 기본 페이지 설정
st.set_page_config(page_title='Maptology', layout='wide')

# CSS 스타일 추가
add_css()

# 세션 상태 초기화
initialize_session()

# 로고와 제목 표시
render_header()

# 🔹 1. CSV 파일 업로드
uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
if uploaded_file:
    # 로딩 오버레이와 함께 CSV 파일 처리
    loading_container = st.empty()
    
    with loading_container:
        show_loading_overlay("Processing uploaded file...")
    
    try:
        # 인위적인 지연 추가 (로딩 화면을 보기 위해)
        time.sleep(1)
        
        # CSV 파일 읽기 및 인덱스를 1부터 시작하도록 설정
        # 쉼표 주변 공백 처리 - skipinitialspace=True
        df = pd.read_csv(uploaded_file, skipinitialspace=True)
        df.index = range(1, len(df) + 1)  # 인덱스를 1부터 시작하도록 재설정
        st.session_state.uploaded_df = df
        
        # 로딩 오버레이 제거
        loading_container.empty()
        
        # 파일 처리 완료 메시지
        st.success(f"✅ File uploaded successfully! Found {len(df)} rows and {len(df.columns)} columns.")
        
    except Exception as e:
        loading_container.empty()
        st.error(f"❌ Error processing file: {str(e)}")
        st.stop()
    
    st.write("### Uploaded Data Preview")
    
    # 하이라이트된 컬럼이 있으면 스타일링 적용
    if 'highlighted_column' in st.session_state and st.session_state.highlighted_column in df.columns:
        highlighted_col = st.session_state.highlighted_column
        
        # Pandas 스타일링을 사용하여 특정 컬럼 하이라이트
        def highlight_column(x):
            df_styler = pd.DataFrame('', index=x.index, columns=x.columns)
            df_styler[highlighted_col] = 'background-color: #90EE90;'  # 연한 녹색 배경
            return df_styler
        
        # 하이라이트된 스타일로 데이터프레임 표시
        styled_df = df.head(20).style.apply(highlight_column, axis=None)
        st.dataframe(styled_df, use_container_width=True)
        
        # 하이라이트 설명 추가
        st.caption(f"Column '{highlighted_col}' highlighted due to recent type change")
    else:
        # 일반 미리보기 테이블
        st.dataframe(st.session_state.uploaded_df.head(20), use_container_width=True)
    
    # 🔹 온톨로지 선택 섹션
    ontology_loading_container = st.empty()
    
    with ontology_loading_container:
        show_loading_overlay("Loading available ontologies...")
    
    # 인위적인 지연 추가
    time.sleep(1)
    
    available_ontologies = get_available_ontologies()
    
    # 로딩 오버레이 제거
    ontology_loading_container.empty()
        
    if available_ontologies:
        st.success(f"✅ Loaded {len(available_ontologies)} ontologies")
        render_ontology_selection(available_ontologies)
    else:
        st.error("❌ Failed to load ontologies. Please check your internet connection and try again.")
        st.stop()
    
    # 🔹 컬럼 선택 및 온톨로지 매핑 섹션
    if st.session_state.selected_ontologies:
        render_column_mapping_section()

        # 🔹 데이터 타입 감지 및 수정 섹션
        if st.session_state.selected_column and st.session_state.uploaded_df is not None:
            render_data_values_section()

        # 🔹 값을 온톨로지 용어에 매핑 섹션
        if st.session_state.selected_column and st.session_state.uploaded_df is not None:
            render_value_mapping_section()

# 🔹 매핑된 용어 및 삭제 버튼 표시
if st.session_state.mapped_terms:
    render_mapped_terms()

# 🔹 값-온톨로지 매핑 정보 표시
if st.session_state.value_ontology_mapping:
    render_value_mappings()
    
    # 다운로드 버튼
    render_download_buttons()

# API 라이센스 관련 경고
st.write("---")
st.warning("Please ensure you have proper licensing for using the BioPortal API. [Learn more about BioPortal licensing](https://bioportal.bioontology.org/license)")
