import streamlit as st
from utils import get_friendly_dtype, display_column_info, change_column_type
from mapping import on_type_change

# 데이터 값 섹션 렌더링 / Render data values section
def render_data_values_section():
    st.write("### Data Values")
    selected_col = st.session_state.selected_column
    df = st.session_state.uploaded_df
    
    # 현재 데이터 타입 가져오기 / Get current data type
    current_dtype = df[selected_col].dtype
    friendly_dtype = get_friendly_dtype(current_dtype)
    
    # 두 열로 배치 - 데이터 값과 타입 변환 옵션 나란히 표시 / Arrange in two columns - display data values and type conversion options side by side
    col1, col2 = st.columns([3, 2])
    
    with col1:
        # 타입 변환 결과 간단히 표시 / Simply display type conversion results
        if 'type_conversion_result' in st.session_state and st.session_state.type_conversion_result['column'] == selected_col:
            result = st.session_state.type_conversion_result
            st.success(f"Column '{selected_col}' type changed from {result['from_type']} to {result['to_type']}")
        
        st.write(f"Current data type: **{friendly_dtype}** ({current_dtype})")
        
        # 데이터 타입에 따라 다른 정보 표시 / Display different information based on data type
        display_column_info(df, selected_col)
    
    with col2:
        st.write("**Type Conversion Options**")
        
        # 데이터 타입 변경 UI - 현재 타입에 맞게 기본값 설정 / Data type change UI - set default value according to current type
        dtype_options = ["String", "Categorical", "Float", "Integer", "Boolean", "Date"]
        default_index = dtype_options.index(friendly_dtype) if friendly_dtype in dtype_options else 0
        
        # 선택 시 즉시 적용되도록 on_change 추가 / Add on_change to apply immediately upon selection
        new_type = st.selectbox(
            "Change data type to:",
            dtype_options,
            index=default_index,
            key="type_select",
            on_change=on_type_change
        )
        
        # 항상 결측값 처리 옵션 표시 / Always display missing value handling options
        handle_missing = st.checkbox("Handle missing values", value=False)
        missing_values = None
        
        if handle_missing:
            missing_input = st.text_input(
                "Specify values to treat as missing (comma-separated)", 
                placeholder="NA, N/A, missing, ?, -"
            )
            
            if missing_input:
                # 쉼표 주변 공백 제거 / Remove spaces around commas
                missing_values = [v.strip() for v in missing_input.split(',')]
                st.write(f"These values will be converted to NaN: {missing_values}")
                
                # 결측값 처리를 위한 버튼 / Button for missing value handling
                if st.button("Apply Missing Values Handling"):
                    change_column_type(selected_col, st.session_state.type_select, handle_missing, missing_values)
