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

# Streamlit 기본 페이지 설정 / Streamlit basic page configuration
st.set_page_config(page_title='Maptology', layout='wide')

# CSS 스타일 추가 / Add CSS styles
add_css()

# 세션 상태 초기화 / Initialize session state
initialize_session()

# 로고와 제목 표시 / Display logo and title
render_header()

# Tagline
st.caption("Map your dataset to standardized ontology terms")

# =============================================================================
# API 키 입력 섹션 / API Key Input Section
# =============================================================================
if not st.session_state.get('api_key'):
    st.markdown("### BioPortal API Key Required")
    st.markdown("Before using Maptology, you need a **free BioPortal API key**:")
    
    with st.expander("How to get your API key", expanded=False):
        st.markdown("""
        1. Visit **https://bioportal.bioontology.org/**
        2. Click **"Login"** or **"Register"** to create a free account
        3. After logging in, go to **"Account" → "API Key"**
        4. Copy your API key and paste it below
        """)
    
    api_key = st.text_input(
        "Enter your BioPortal API Key:", 
        type="password",
        placeholder="Paste your API key here...",
        help="Get your free API key at https://bioportal.bioontology.org/"
    )
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Start Using Maptology", type="primary"):
            if api_key and len(api_key.strip()) > 10:  # 기본적인 validation
                st.session_state.api_key = api_key.strip()
                st.success("✅ API key saved! Loading application...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Please enter a valid API key")
    
    with col2:
        if api_key:
            if len(api_key.strip()) < 10:
                st.warning("API key seems too short. Please check your key.")
    
    if not api_key:
        st.info("**Need an API key?** Register for free at https://bioportal.bioontology.org/")
        st.warning("Please enter your BioPortal API key to continue")
        
    st.stop()  # 앱 실행 중단

# =============================================================================
# 메인 앱 시작 (API 키가 있을 때만) / Main App Start (only when API key exists)
# =============================================================================

# API 키 상태 표시 (작은 표시기)
with st.sidebar:
    st.success("API Key: Active")
    if st.button("Change API Key"):
        st.session_state.api_key = None
        st.rerun()

# CSV 파일 업로드 / CSV file upload
uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
if uploaded_file:
    # 로딩 오버레이와 함께 CSV 파일 처리 / Process CSV file with loading overlay
    loading_container = st.empty()
    
    with loading_container:
        show_loading_overlay("Processing uploaded file...")
    
    try:
        # 인위적인 지연 추가 (로딩 화면을 보기 위해) / Add artificial delay to show loading screen
        time.sleep(1)
        
        # CSV 파일 읽기 및 인덱스를 1부터 시작하도록 설정 / Read CSV file and set index to start from 1
        # 쉼표 주변 공백 처리 - skipinitialspace=True / Handle spaces around commas - skipinitialspace=True
        df = pd.read_csv(uploaded_file, skipinitialspace=True)
        df.index = range(1, len(df) + 1)  # 인덱스를 1부터 시작하도록 재설정 / Reset index to start from 1
        st.session_state.uploaded_df = df
        
        # 로딩 오버레이 제거 / Remove loading overlay
        loading_container.empty()
        
        # 파일 처리 완료 메시지 / File processing completion message
        st.success(f"✅ File uploaded successfully! Found {len(df)} rows and {len(df.columns)} columns.")
        
    except Exception as e:
        loading_container.empty()
        st.error(f"❌ Error processing file: {str(e)}")
        st.stop()
    
    st.write("### Uploaded Data Preview")
    
    # 하이라이트된 컬럼이 있으면 스타일링 적용 / Apply styling if there's a highlighted column
    if 'highlighted_column' in st.session_state and st.session_state.highlighted_column in df.columns:
        highlighted_col = st.session_state.highlighted_column
        
        # Pandas 스타일링을 사용하여 특정 컬럼 하이라이트 / Use Pandas styling to highlight specific column
        def highlight_column(x):
            df_styler = pd.DataFrame('', index=x.index, columns=x.columns)
            df_styler[highlighted_col] = 'background-color: #90EE90;'  # 연한 녹색 배경 / Light green background
            return df_styler
        
        # 하이라이트된 스타일로 데이터프레임 표시 / Display dataframe with highlighted style
        styled_df = df.head(20).style.apply(highlight_column, axis=None)
        st.dataframe(styled_df, use_container_width=True)
        
        # 하이라이트 설명 추가 / Add highlight explanation
        st.caption(f"Column '{highlighted_col}' highlighted due to recent type change")
    else:
        # 일반 미리보기 테이블 / Regular preview table
        st.dataframe(st.session_state.uploaded_df.head(20), use_container_width=True)
    
    # 온톨로지 선택 섹션 / Ontology selection section
    ontology_loading_container = st.empty()
    
    with ontology_loading_container:
        show_loading_overlay("Loading available ontologies...")
    
    # 인위적인 지연 추가 / Add artificial delay
    time.sleep(1)
    
    available_ontologies = get_available_ontologies()
    
    # 로딩 오버레이 제거 / Remove loading overlay
    ontology_loading_container.empty()
        
    if available_ontologies:
        st.success(f"✅ Loaded {len(available_ontologies)} ontologies")
        render_ontology_selection(available_ontologies)
    else:
        st.error("❌ Failed to load ontologies. Please check your internet connection and API key.")
        st.stop()
    
    # 컬럼 선택 및 온톨로지 매핑 섹션 / Column selection and ontology mapping section
    if st.session_state.selected_ontologies:
        render_column_mapping_section()

        # 데이터 타입 감지 및 수정 섹션 / Data type detection and modification section
        if st.session_state.selected_column and st.session_state.uploaded_df is not None:
            render_data_values_section()

        # 값을 온톨로지 용어에 매핑 섹션 / Section for mapping values to ontology terms
        if st.session_state.selected_column and st.session_state.uploaded_df is not None:
            render_value_mapping_section()

# 매핑된 용어 및 삭제 버튼 표시 / Display mapped terms and delete buttons
if st.session_state.mapped_terms:
    render_mapped_terms()

# 값-온톨로지 매핑 정보 표시 / Display value-ontology mapping information
if st.session_state.value_ontology_mapping:
    render_value_mappings()
    
    # 다운로드 버튼 / Download buttons
    render_download_buttons()

# 하단 정보 제거 (교수님 피드백 반영) / Remove bottom warning (professor feedback applied)
st.write("---")
st.caption("Maptology uses the BioPortal API to search and map ontology terms.")

