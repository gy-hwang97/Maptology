import streamlit as st

# 로고와 제목을 컬럼으로 표시
def render_header():
    col1, col2 = st.columns([1, 10])
    with col1:
        st.image("maptology.png", width=200)  # 경로 슬래시 방향 수정
    with col2:
        st.title('Maptology')
