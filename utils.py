import streamlit as st
import pandas as pd

# API 키를 빈 문자열로 설정 (더 이상 하드코딩하지 않음)
API_KEY = ""

# 세션 상태 초기화
def initialize_session():
    if 'api_key' not in st.session_state:
        if API_KEY:
            st.session_state.api_key = API_KEY
        else:
            st.session_state.api_key = None
        
    if 'ontology_results' not in st.session_state:
        st.session_state.ontology_results = None
    if 'uploaded_df' not in st.session_state:
        st.session_state.uploaded_df = None
    if 'selected_column' not in st.session_state:
        st.session_state.selected_column = None
    if 'mapped_terms' not in st.session_state:
        st.session_state.mapped_terms = []
    if 'current_mapping_done' not in st.session_state:
        st.session_state.current_mapping_done = False
    if 'column_mapping' not in st.session_state:
        st.session_state.column_mapping = {}
    
    if 'selected_terms' not in st.session_state:
        st.session_state.selected_terms = []
    if 'search_term_indices' not in st.session_state:
        st.session_state.search_term_indices = {}
    
    if 'selected_term_index' not in st.session_state:
        st.session_state.selected_term_index = None
        
    if 'first_load' not in st.session_state:
        st.session_state.first_load = True
    if 'value_ontology_mapping' not in st.session_state:
        st.session_state.value_ontology_mapping = {}
    if 'selected_unique_value' not in st.session_state:
        st.session_state.selected_unique_value = None
        
    if 'value_term_indices' not in st.session_state:
        st.session_state.value_term_indices = []
    if 'value_term_indices_by_value' not in st.session_state:
        st.session_state.value_term_indices_by_value = {}
    
    if 'value_term_index' not in st.session_state:
        st.session_state.value_term_index = None
        
    if 'value_ontology_results' not in st.session_state:
        st.session_state.value_ontology_results = None
    if 'auto_searched' not in st.session_state:
        st.session_state.auto_searched = False
    if 'column_states' not in st.session_state:
        st.session_state.column_states = {}
    if 'ontology_details_cache' not in st.session_state:
        st.session_state.ontology_details_cache = {}
        
    if 'available_ontologies' not in st.session_state:
        st.session_state.available_ontologies = []
    if 'selected_ontologies' not in st.session_state:
        st.session_state.selected_ontologies = []
    if 'filtered_ontology_results' not in st.session_state:
        st.session_state.filtered_ontology_results = None
    if 'ontologies_changed' not in st.session_state:
        st.session_state.ontologies_changed = False
    if 'search_terms_selections' not in st.session_state:
        st.session_state.search_terms_selections = {}
    
    # 삭제 카운터 초기화
    if 'column_checkbox_counter' not in st.session_state:
        st.session_state.column_checkbox_counter = 0
    if 'value_checkbox_counter' not in st.session_state:
        st.session_state.value_checkbox_counter = 0

# API 키 가져오기 함수
def get_api_key():
    """세션 스테이트에서 API 키를 가져오는 함수"""
    return st.session_state.get('api_key', None)

# CSS 스타일 추가
def add_css():
    st.markdown("""
    <style>
    .main .block-container {
        max-width: 95% !important;
        padding: 1rem;
    }
    .term-box {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 5px 0;
        background-color: #f9f9f9;
    }
    .term-label {
        font-weight: bold;
        color: #333;
        margin-bottom: 4px;
    }
    .term-definition {
        font-style: italic;
        color: #555;
        margin-top: 4px;
    }
    
    /* OUTER wrapper: horizontal scroll 제거 */
    div[data-testid="stDataFrame"] > div {
    overflow-x: hidden !important;
    }

    /* INNER resizable area: horizontal scroll 유지 */
    div[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {
    overflow-x: auto !important;
    }

    /* 바깥쪽 스크롤바가 "보이기만" 하는 경우 완전 숨김 */
    div[data-testid="stDataFrame"] > div::-webkit-scrollbar {
    height: 0px !important;
    }
    div[data-testid="stDataFrame"] > div {
    scrollbar-width: none !important; /* Firefox */
    }
    
    .delete-button {
        color: red;
        cursor: pointer;
    }
    .type-badge {
        display: inline-block;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 0.8em;
        margin-left: 8px;
        background-color: #f0f0f0;
        border: 1px solid #ddd;
    }
    .type-string {
        background-color: #e6f3ff;
        border-color: #b3d9ff;
    }
    .type-numeric {
        background-color: #e6ffe6;
        border-color: #b3ffb3;
    }
    .type-date {
        background-color: #fff0e6;
        border-color: #ffd1b3;
    }
    .type-categorical {
        background-color: #f2e6ff;
        border-color: #d9b3ff;
    }
    .type-boolean {
        background-color: #ffe6e6;
        border-color: #ffb3b3;
    }
    .conversion-summary {
        padding: 10px;
        border-left: 4px solid #4CAF50;
        background-color: #f8f9fa;
        margin: 10px 0;
    }
    .mapping-table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    .mapping-table th {
        background-color: #f8f9fa;
        padding: 8px;
        text-align: left;
        border-bottom: 2px solid #ddd;
    }
    .mapping-table td {
        padding: 8px;
        border-bottom: 1px solid #eee;
    }
    .mapping-table tr:hover {
        background-color: #f5f5f5;
    }
    .value-mapping-section {
        margin-top: 20px;
        padding-top: 10px;
        border-top: 1px solid #eee;
    }
    .section-header {
        background-color: #f0f0f0;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: bold;
        color: #333;
    }
    .section-purple {
        border-left: 5px solid #9370DB;
    }
    .section-red {
        border-left: 5px solid #FF6B6B;
    }
    .section-blue {
        border-left: 5px solid #4682B4;
    }
    .ontology-checkbox-container {
        max-height: 300px;
        overflow-y: auto;
        border: 1px solid #ddd;
        padding: 10px;
        border-radius: 5px;
        margin-top: 10px;
    }
    .scrollable-container {
        max-height: 300px;
        overflow-y: auto;
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 10px 0;
    }
    [data-testid="stExpander"] div:has(>.streamlit-expanderContent) {
        overflow: auto;
        max-height: 400px;
    }
    .selected-term {
        background-color: #e6f3ff;
        border-left: 3px solid #4e8cff;
        padding: 8px;
        margin: 5px 0;
        border-radius: 4px;
    }
    .multiple-selections-box {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 10px 0;
        background-color: #f9f9f9;
    }
    .selection-summary {
        font-weight: bold;
        margin-bottom: 8px;
        color: #333;
    }
    .section-green {
        border-left: 5px solid #4CAF50;
    }
    
    /* 파일 업로더의 X 버튼 숨기기 */
    .stFileUploader button[kind="icon"] {
        display: none !important;
    }
    
    /* 파일 업로더의 Browse files 버튼 숨기기 */
    .stFileUploader button[kind="secondary"] {
        display: none !important;
    }
    
    /* Unique values 스타일 */
    .unique-values-display {
        background-color: #f8f9fa;
        padding: 8px 12px;
        border-radius: 5px;
        border-left: 3px solid #4682B4;
        margin: 5px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# pandas 데이터 타입을 사용자 친화적으로 변환하는 함수
def get_friendly_dtype(dtype):
    dtype_name = str(dtype)
    
    if dtype_name == 'object':
        return "String"
    elif dtype_name.startswith('string'):
        return "String"
    elif dtype_name.startswith('float'):
        return "Float"
    elif dtype_name.startswith('int'):
        return "Integer"
    elif dtype_name == 'category':
        return "Categorical"
    elif dtype_name.startswith('datetime'):
        return "Date"
    elif dtype_name == 'bool':
        return "Boolean"
    else:
        return "String"

# 값 정보 표시 함수 (깔끔한 형식으로 변경)
def display_column_info(df, column_name):
    dtype = df[column_name].dtype
    dtype_name = str(dtype)
    
    if dtype_name == 'object' or dtype_name.startswith('string') or dtype_name == 'category':
        unique_values = df[column_name].dropna().unique()
        total_count = len(unique_values)
        
        # 최대 5개까지만 표시
        display_values = unique_values[:5].tolist()
        values_str = ", ".join([str(v) for v in display_values])
        
        # 5개 초과면 "+N more" 추가
        if total_count > 5:
            remaining = total_count - 5
            st.markdown(f"""
            <div class="unique-values-display">
                <strong>Unique values:</strong> {values_str}... <em>(+{remaining} more, {total_count} total)</em>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="unique-values-display">
                <strong>Unique values:</strong> {values_str} <em>({total_count} total)</em>
            </div>
            """, unsafe_allow_html=True)
            
    elif dtype_name.startswith('float') or dtype_name.startswith('int'):
        min_val = df[column_name].min()
        max_val = df[column_name].max()
        mean_val = df[column_name].mean()
        st.markdown(f"""
        <div class="unique-values-display">
            <strong>Range:</strong> {min_val} ~ {max_val} &nbsp;&nbsp;|&nbsp;&nbsp; <strong>Average:</strong> {mean_val:.2f}
        </div>
        """, unsafe_allow_html=True)
        
    elif dtype_name.startswith('datetime'):
        min_date = df[column_name].min()
        max_date = df[column_name].max()
        st.markdown(f"""
        <div class="unique-values-display">
            <strong>Date range:</strong> {min_date} ~ {max_date}
        </div>
        """, unsafe_allow_html=True)
    else:
        sample_values = df[column_name].head(5).tolist()
        values_str = ", ".join([str(v) for v in sample_values])
        st.markdown(f"""
        <div class="unique-values-display">
            <strong>Sample values:</strong> {values_str}
        </div>
        """, unsafe_allow_html=True)

# 데이터 타입 변경 함수
def change_column_type(column_name, new_type):
    if column_name and st.session_state.uploaded_df is not None:
        df = st.session_state.uploaded_df
        
        try:
            if new_type == "String":
                df[column_name] = df[column_name].astype('string')
            elif new_type == "Categorical":
                df[column_name] = df[column_name].astype('category')
            elif new_type == "Float":
                df[column_name] = df[column_name].astype('float64')
            elif new_type == "Integer":
                df[column_name] = df[column_name].astype('int64')
            elif new_type == "Boolean":
                df[column_name] = df[column_name].astype('bool')
            elif new_type == "Date":
                df[column_name] = pd.to_datetime(df[column_name], errors='coerce')
            
            st.session_state.uploaded_df = df
            
            # mapped_terms에서 해당 컬럼의 타입 업데이트
            for i, mapping in enumerate(st.session_state.mapped_terms):
                if mapping["Original Label"] == column_name:
                    st.session_state.mapped_terms[i]["Data Type"] = new_type
            
            return True
            
        except Exception as e:
            st.error(f"Error changing type: {str(e)}")
            return False
    return False
