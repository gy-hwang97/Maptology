import streamlit as st
from utils import get_friendly_dtype, display_column_info

# 데이터 값 섹션 렌더링 (간소화됨)
def render_data_values_section():
    st.write("### Column Information")
    st.caption("This section shows a summary of the selected column's data.")
    
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df
    
    # 현재 데이터 타입 가져오기
    current_dtype = df[selected_col].dtype
    friendly_dtype = get_friendly_dtype(current_dtype)
    
    st.write(f"**Data type:** {friendly_dtype}")
    
    # 데이터 타입에 따라 다른 정보 표시
    display_column_info(df, selected_col)
