import streamlit as st

def show_loading_overlay(message="Loading..."):
    st.markdown(
        f"""
        <style>
        .overlay {{
            position: fixed; 
            top: 0; 
            left: 0; 
            width: 100%; 
            height: 100%; 
            background-color: rgba(255, 255, 255, 0.8);
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 3em;
            font-weight: bold;
            color: #333;
        }}
        </style>
        <div class="overlay">{message}</div>
        """, unsafe_allow_html=True)
