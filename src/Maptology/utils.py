import streamlit as st
import pandas as pd
import re
from dateutil import parser as date_parser

# BioPortal API is no longer used (local TF-IDF search only) / BioPortal API 더 이상 사용 안 함
API_KEY = ""

# 세션 상태 초기화 / Initialize session state
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
    
    # 사용자가 선택한 컬럼별 데이터 타입 저장 / Store user-selected data type per column
    if 'column_data_types' not in st.session_state:
        st.session_state.column_data_types = {}
        
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
    
    # 삭제 카운터 초기화 / Initialize delete counters
    if 'column_checkbox_counter' not in st.session_state:
        st.session_state.column_checkbox_counter = 0
    if 'value_checkbox_counter' not in st.session_state:
        st.session_state.value_checkbox_counter = 0
    
    # 수동 검색 세션 상태 / Manual search session state
    if 'manual_column_search_results' not in st.session_state:
        st.session_state.manual_column_search_results = None
    if 'manual_column_selected_terms' not in st.session_state:
        st.session_state.manual_column_selected_terms = []
    if 'manual_column_checkbox_counter' not in st.session_state:
        st.session_state.manual_column_checkbox_counter = 0
    if 'manual_value_search_results' not in st.session_state:
        st.session_state.manual_value_search_results = None
    if 'manual_value_selected_indices' not in st.session_state:
        st.session_state.manual_value_selected_indices = []
    if 'manual_value_checkbox_counter' not in st.session_state:
        st.session_state.manual_value_checkbox_counter = 0

    # 매핑 파일 가져오기 상태 / Imported-mapping state
    if 'imported_mapping_name' not in st.session_state:
        st.session_state.imported_mapping_name = None
    if 'import_report' not in st.session_state:
        st.session_state.import_report = None
    if 'mapping_uploader_seq' not in st.session_state:
        st.session_state.mapping_uploader_seq = 0

    # 체크박스 단일 진실원천용 버전 카운터 / Bumped on every mapping change so
    # checkbox widgets re-render from the mapping instead of stale widget state
    if 'mapping_version' not in st.session_state:
        st.session_state.mapping_version = 0

    # 온톨로지 체크박스 위젯 버전 / Bumped on every PROGRAMMATIC change to the
    # ontology selection (import auto-select, Select None, file upload/remove) so
    # the ontology checkboxes re-render from selected_ontologies instead of stale
    # widget state. NOT bumped on a manual checkbox toggle.
    if 'ontology_widget_version' not in st.session_state:
        st.session_state.ontology_widget_version = 0

    # 가져온 매핑 파일의 내용 해시 / Content hash of the last-imported mapping file
    # (compared instead of the filename, so a different file with the same name
    # is still re-imported).
    if 'imported_mapping_hash' not in st.session_state:
        st.session_state.imported_mapping_hash = None

# API 키 가져오기 함수 / Get API key function
def get_api_key():
    return st.session_state.get('api_key', None)

# CSS 스타일 추가 / Add CSS styles
def add_css():
    st.markdown("""
    <style>
    /* 글로벌 폰트 설정 / Global font setting */
    html, body, [class*="css"], .main, .stApp,
    .main .block-container p,
    .main .block-container span,
    .main .block-container label,
    .main .block-container div,
    .main .block-container h1,
    .main .block-container h2,
    .main .block-container h3,
    .main .block-container h4,
    .main .block-container a,
    .main .block-container li,
    .main .block-container td,
    .main .block-container th,
    .main .block-container input,
    .main .block-container button,
    .main .block-container textarea,
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        font-family: 'Calibri', 'Arial', sans-serif !important;
    }
    .main .block-container p,
    .main .block-container span,
    .main .block-container label,
    .main .block-container div {
        font-size: 18px !important;
    }
    [data-testid="stFileUploader"] label p {
        font-size: 18px !important;
        font-weight: 500 !important;
    }
    [data-testid="stFileUploader"] small,
    [data-testid="stFileUploader"] span {
        font-size: 15px !important;
    }
    [data-testid="stCaptionContainer"] p,
    .stCaption p {
        font-size: 20px !important;
    }
    [data-testid="stSelectbox"] label p,
    [data-testid="stTextInput"] label p {
        font-size: 20px !important;
    }
    [data-testid="stExpander"] p {
        font-size: 16px !important;
    }
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
    div[data-testid="stDataFrame"] > div {
        overflow-x: hidden !important;
    }
    div[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {
        overflow-x: auto !important;
    }
    div[data-testid="stDataFrame"] > div::-webkit-scrollbar {
        height: 0px !important;
    }
    div[data-testid="stDataFrame"] > div {
        scrollbar-width: none !important;
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
    .type-string { background-color: #e6f3ff; border-color: #b3d9ff; }
    .type-numeric { background-color: #e6ffe6; border-color: #b3ffb3; }
    .type-date { background-color: #fff0e6; border-color: #ffd1b3; }
    .type-boolean { background-color: #ffe6e6; border-color: #ffb3b3; }
    .conversion-summary {
        padding: 10px;
        border-left: 4px solid #4CAF50;
        background-color: #f8f9fa;
        margin: 10px 0;
    }
    .mapping-table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    .mapping-table th { background-color: #f8f9fa; padding: 8px; text-align: left; border-bottom: 2px solid #ddd; }
    .mapping-table td { padding: 8px; border-bottom: 1px solid #eee; }
    .mapping-table tr:hover { background-color: #f5f5f5; }
    .value-mapping-section { margin-top: 20px; padding-top: 10px; border-top: 1px solid #eee; }
    .section-header {
        background-color: #f0f0f0;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: bold;
        color: #333;
    }
    .section-purple { border-left: 5px solid #9370DB; }
    .section-red { border-left: 5px solid #FF6B6B; }
    .section-blue { border-left: 5px solid #4682B4; }
    .ontology-checkbox-container {
        max-height: 300px; overflow-y: auto;
        border: 1px solid #ddd; padding: 10px; border-radius: 5px; margin-top: 10px;
    }
    .scrollable-container {
        max-height: 300px; overflow-y: auto;
        border: 1px solid #ddd; border-radius: 5px; padding: 10px; margin: 10px 0;
    }
    [data-testid="stExpander"] div:has(>.streamlit-expanderContent) {
        overflow: auto; max-height: 400px;
    }
    .selected-term {
        background-color: #e6f3ff; border-left: 3px solid #4e8cff;
        padding: 8px; margin: 5px 0; border-radius: 4px;
    }
    .multiple-selections-box {
        border: 1px solid #ddd; border-radius: 5px; padding: 10px; margin: 10px 0; background-color: #f9f9f9;
    }
    .selection-summary { font-weight: bold; margin-bottom: 8px; color: #333; }
    .section-green { border-left: 5px solid #4CAF50; }
    .stFileUploader button[kind="icon"] { display: none !important; }
    .stFileUploader button[kind="secondary"] { display: none !important; }
    .unique-values-display {
        background-color: #f8f9fa; padding: 8px 12px; border-radius: 5px;
        border-left: 3px solid #4682B4; margin: 5px 0;
    }
    [data-testid="stForm"] { border: none !important; padding: 0 !important; }
    .sub-heading {
        font-size: 20px !important;
        font-weight: bold !important;
        margin-top: 10px;
        margin-bottom: 5px;
    }
    /* Ontology column values are rendered as DISABLED tertiary buttons (only to
       align them on the same row as the checkbox / ℹ️). Show their text in the
       normal text color instead of the faded 'disabled' grey, so they match the
       Term column values. Only disabled tertiary buttons are affected. */
    button[kind="tertiary"]:disabled,
    button[kind="tertiary"]:disabled *,
    [data-testid="stBaseButton-tertiary"]:disabled,
    [data-testid="stBaseButton-tertiary"]:disabled * {
        color: var(--text-color, rgb(49, 51, 63)) !important;
        -webkit-text-fill-color: var(--text-color, rgb(49, 51, 63)) !important;
        opacity: 1 !important;
        cursor: default !important;
    }
    </style>
    """, unsafe_allow_html=True)

# pandas 데이터 타입을 사용자 친화적으로 변환 / Convert pandas dtype to user-friendly name
def get_friendly_dtype(dtype):
    dtype_name = str(dtype)
    if dtype_name in ['object', 'str']:
        return "String"
    elif dtype_name.startswith('string'):
        return "String"
    elif dtype_name.startswith('float'):
        return "Float"
    elif dtype_name.startswith('int'):
        return "Integer"
    elif dtype_name.startswith('datetime'):
        return "Datetime"
    elif dtype_name.startswith('timedelta'):
        return "Time"
    elif dtype_name == 'bool' or dtype_name == 'boolean':
        return "Boolean"
    elif dtype_name == 'category':
        return "String"
    else:
        return "String"

# dateutil을 사용하여 컬럼 타입 자동 감지 / Auto-detect column type using dateutil
def detect_column_type(df, column_name):
    dtype = df[column_name].dtype
    dtype_name = str(dtype)
    
    # object(string) 타입이 아니면 pandas dtype 그대로 사용 / Use pandas dtype if not object
    if dtype_name not in ['object', 'str'] and not dtype_name.startswith('string') and dtype_name != 'category':
        return get_friendly_dtype(dtype)
    
    values = df[column_name].dropna()
    if len(values) == 0:
        return "String"
    
    # 샘플로 최대 20개만 검사 / Check up to 20 samples
    sample = values.head(20)
    has_time_component = False
    is_time_only = True
    
    for val in sample:
        val_str = str(val).strip()
        
        # 순수 시간인지 확인 / Check if pure time
        has_date_indicator = False
        for indicator in ['/', '-']:
            if indicator in val_str:
                has_date_indicator = True
                break
        # 마침표는 시간(밀리초)이 아닌 경우만 날짜 구분자로 인식 / Period as date separator only if no colon (not milliseconds)
        if '.' in val_str and ':' not in val_str:
            has_date_indicator = True
        for month in ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']:
            if month in val_str.lower():
                has_date_indicator = True
                break
        # 4자리 연도 패턴 확인 / Check for 4-digit year pattern
        if re.search(r'\b\d{4}\b', val_str):
            has_date_indicator = True
        
        if has_date_indicator:
            is_time_only = False
        
        # dateutil로 파싱 시도 / Try parsing with dateutil
        try:
            parsed = date_parser.parse(val_str)
            if parsed.hour != 0 or parsed.minute != 0 or parsed.second != 0:
                has_time_component = True
        except (ValueError, OverflowError, TypeError):
            return "String"
    
    # 모든 값이 파싱 가능 → 타입 결정 / All values parseable → determine type
    if is_time_only:
        return "Time"
    elif has_time_component:
        return "Datetime"
    else:
        return "Date"

# 사용자가 선택한 데이터 타입을 가져오는 함수 / Get user-selected data type
def get_column_data_type(column_name):
    if column_name in st.session_state.get('column_data_types', {}):
        return st.session_state.column_data_types[column_name]
    if st.session_state.uploaded_df is not None and column_name in st.session_state.uploaded_df.columns:
        return detect_column_type(st.session_state.uploaded_df, column_name)
    return "String"

# 데이터 타입 변경 유효성 검사 함수 / Validate data type change
def validate_type_change(column_name, new_type):
    if st.session_state.uploaded_df is None:
        return True, ""
    
    df = st.session_state.uploaded_df
    actual_dtype = detect_column_type(df, column_name)
    
    if actual_dtype == new_type:
        return True, ""
    if new_type == "String":
        return True, ""
    
    # 자동 감지된 타입이 Date/Datetime/Time이면 세부 검사 / Detailed check for date/time types
    if actual_dtype == "Time":
        if new_type == "Time":
            return True, ""
        else:
            return False, f"This column contains time-only values (no dates). You can only select 'Time' or 'String'."
    
    if actual_dtype == "Date":
        if new_type in ["Date", "Datetime"]:
            return True, ""
        else:
            return False, f"This column contains date values without time. You can select 'Date', 'Datetime', or 'String'."
    
    if actual_dtype == "Datetime":
        if new_type in ["Date", "Datetime", "Time"]:
            return True, ""
        else:
            return False, f"This column contains datetime values. You can select 'Date', 'Datetime', 'Time', or 'String'."
    
    if actual_dtype == "String":
        return False, f"This column contains text (string) values. You can only select 'String' for this column."
    
    if actual_dtype == "Float":
        if new_type == "Integer":
            col_data = df[column_name].dropna()
            has_decimals = False
            for val in col_data:
                if val != int(val):
                    has_decimals = True
                    break
            if has_decimals:
                return False, "This column contains at least one floating-point value and cannot be converted to Integer."
            else:
                return True, ""
        elif new_type == "Float":
            return True, ""
        else:
            return False, f"This column contains float values. You cannot convert it to '{new_type}'."
    
    if actual_dtype == "Integer":
        if new_type in ["Integer", "Float"]:
            return True, ""
        else:
            return False, f"This column contains integer values. You cannot convert it to '{new_type}'."
    
    if actual_dtype == "Boolean":
        if new_type == "Boolean":
            return True, ""
        else:
            return False, f"This column contains boolean values. You cannot convert it to '{new_type}'."
    
    if actual_dtype in ["Date", "Datetime"]:
        if new_type in ["Date", "Datetime", "Time"]:
            return True, ""
        else:
            return False, f"This column contains date/time values. You cannot convert it to '{new_type}'."
    
    if actual_dtype == "Time":
        if new_type in ["Time", "Datetime"]:
            return True, ""
        else:
            return False, f"This column contains time values. You cannot convert it to '{new_type}'."
    
    return True, ""

# 컬럼 정보 표시 함수 / Display column info function
def display_column_info(df, column_name, user_type=None):
    dtype = df[column_name].dtype
    dtype_name = str(dtype)
    
    # 사용자가 String을 선택하면 → 항상 unique values 표시 / If user selected String → always show unique values
    if user_type == "String":
        unique_values = sorted(df[column_name].dropna().unique(), key=str)
        total_count = len(unique_values)
        display_values = unique_values[:5]
        values_str = ", ".join([str(v) for v in display_values])
        
        if total_count > 5:
            remaining = total_count - 5
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str}... <em>(+{remaining} more, {total_count} total)</em></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str} <em>({total_count} total)</em></div>', unsafe_allow_html=True)
        return
    
    if user_type == "Boolean":
        unique_values = sorted(df[column_name].dropna().unique(), key=str)
        total_count = len(unique_values)
        values_str = ", ".join([str(v) for v in unique_values])
        st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str} <em>({total_count} total)</em></div>', unsafe_allow_html=True)
        return
    
    # 숫자 타입 / Numeric types
    if user_type in ["Float", "Integer"] or dtype_name.startswith('float') or dtype_name.startswith('int'):
        try:
            min_val = df[column_name].min()
            max_val = df[column_name].max()
            mean_val = df[column_name].mean()
            st.markdown(f'<div class="unique-values-display"><strong>Range:</strong> {min_val} - {max_val} &nbsp;&nbsp;|&nbsp;&nbsp; <strong>Average:</strong> {mean_val:.2f}</div>', unsafe_allow_html=True)
            return
        except (TypeError, ValueError):
            pass
    
    # 날짜/시간 타입 / Date/time types
    if user_type in ["Date", "Datetime", "Time"] or dtype_name.startswith('datetime'):
        try:
            # pandas datetime이면 바로 사용 / Use directly if pandas datetime
            if dtype_name.startswith('datetime'):
                min_date = df[column_name].min()
                max_date = df[column_name].max()
            else:
                # string인 경우 dateutil로 파싱 / Parse with dateutil if string
                parsed_dates = []
                for val in df[column_name].dropna():
                    try:
                        parsed_dates.append(date_parser.parse(str(val)))
                    except (ValueError, OverflowError, TypeError):
                        pass
                if parsed_dates:
                    min_date = min(parsed_dates)
                    max_date = max(parsed_dates)
                    if user_type == "Time":
                        min_date = min_date.strftime("%H:%M:%S")
                        max_date = max_date.strftime("%H:%M:%S")
                    elif user_type == "Date":
                        min_date = min_date.strftime("%Y-%m-%d")
                        max_date = max_date.strftime("%Y-%m-%d")
                    else:
                        min_date = min_date.strftime("%Y-%m-%d %H:%M:%S")
                        max_date = max_date.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    min_date = "N/A"
                    max_date = "N/A"
            st.markdown(f'<div class="unique-values-display"><strong>Range:</strong> {min_date} - {max_date}</div>', unsafe_allow_html=True)
            return
        except (TypeError, ValueError):
            pass
    
    # 문자열 / String
    if dtype_name in ['object', 'str'] or dtype_name.startswith('string') or dtype_name == 'category':
        unique_values = sorted(df[column_name].dropna().unique(), key=str)
        total_count = len(unique_values)
        display_values = unique_values[:5]
        values_str = ", ".join([str(v) for v in display_values])
        
        if total_count > 5:
            remaining = total_count - 5
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str}... <em>(+{remaining} more, {total_count} total)</em></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str} <em>({total_count} total)</em></div>', unsafe_allow_html=True)
    else:
        sample_values = df[column_name].head(5).tolist()
        values_str = ", ".join([str(v) for v in sample_values])
        st.markdown(f'<div class="unique-values-display"><strong>Sample values:</strong> {values_str}</div>', unsafe_allow_html=True)

# 데이터 타입 변경 함수 / Change column data type function
def change_column_type(column_name, new_type):
    if column_name and st.session_state.uploaded_df is not None:
        df = st.session_state.uploaded_df
        try:
            if new_type == "String":
                df[column_name] = df[column_name].astype('string')
            elif new_type == "Float":
                df[column_name] = df[column_name].astype('float64')
            elif new_type == "Integer":
                df[column_name] = df[column_name].astype('int64')
            elif new_type == "Boolean":
                df[column_name] = df[column_name].astype('bool')
            elif new_type in ["Date", "Datetime"]:
                df[column_name] = pd.to_datetime(df[column_name], errors='coerce')
            elif new_type == "Time":
                df[column_name] = pd.to_datetime(df[column_name], errors='coerce')
            
            st.session_state.uploaded_df = df
            for i, mapping in enumerate(st.session_state.mapped_terms):
                if mapping["Original Label"] == column_name:
                    st.session_state.mapped_terms[i]["Data Type"] = new_type
            return True
        except Exception as e:
            st.error(f"Error changing type: {str(e)}")
            return False
    return False