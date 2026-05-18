import streamlit as st
from utils import get_friendly_dtype, display_column_info, get_column_data_type

# 데이터 값 섹션 렌더링 (간소화됨)
def render_data_values_section():
    st.write("### Column Information")
    st.caption("This section shows a summary of the selected column's data.")
    
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df
    
    dtype_options = ["String", "Categorical", "Float", "Integer", "Boolean", "Date"]
    
    # 현재 데이터 타입 가져오기 (사용자 선택 우선)
    current_type = get_column_data_type(selected_col)
    default_index = dtype_options.index(current_type) if current_type in dtype_options else 0
    
    # 데이터 타입 드롭다운
    new_type = st.selectbox(
        "Data type",
        dtype_options,
        index=default_index,
        key=f"data_type_select_{selected_col}"
    )
    
    # 선택이 변경되면 세션 스테이트에 저장
    if new_type != current_type:
        st.session_state.column_data_types[selected_col] = new_type
        st.rerun()
    else:
        # 처음 선택하는 경우에도 저장
        if selected_col not in st.session_state.get('column_data_types', {}):
            st.session_state.column_data_types[selected_col] = current_type
    
    # 데이터 타입에 따라 다른 정보 표시
    display_column_info(df, selected_col)