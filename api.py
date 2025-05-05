import streamlit as st
import requests
import urllib.parse
import pandas as pd
from utils import API_KEY

# 수동 검색 함수 - 선택된 온톨로지 내에서만 검색
def manual_search_ontology(search_term):
    if not search_term:
        return False
    
    # 선택된 온톨로지가 없으면 알림
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False
        
    api_key = API_KEY
    
    # 쉼표 주변 공백 제거 - 검색어 전처리
    search_term = search_term.strip()
    
    # 기본 URL 구성
    base_url = f"https://data.bioontology.org/search?q={urllib.parse.quote(search_term)}&apikey={api_key}"
    
    # 선택된 온톨로지로 검색 제한
    ontologies_param = ",".join(st.session_state.selected_ontologies)
    url = f"{base_url}&ontologies={ontologies_param}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json().get("collection", [])
            if results:
                ontology_data = []
                for res in results:
                    # Preferred Label 필수
                    pref_label = res.get("prefLabel")
                    if not pref_label or pref_label == "N/A":
                        continue
                    
                    # 정의 (없으면 '정의 없음'으로 표시)
                    definition = res.get("definition", [None])[0] if res.get("definition") else "No definition available"
                    
                    # 온톨로지 약어 추출
                    ontology_acronym = "Unknown"
                    links = res.get("links", {})
                    
                    # 방법 1: ontology 링크에서 추출
                    if "ontology" in links:
                        ontology_uri = links["ontology"]
                        ontology_acronym = ontology_uri.split("/")[-1]
                    
                    # 방법 2: 소스 확인
                    source = res.get("source", None)
                    if source:
                        ontology_acronym = source
                    
                    # 방법 3: 컨텍스트에서 추출
                    context = res.get("context", {})
                    if context and "acronym" in context:
                        ontology_acronym = context["acronym"]

                    # 선택된 온톨로지 내에 있는지 확인
                    if ontology_acronym in st.session_state.selected_ontologies:
                        ontology_data.append({
                            "Ontology Name": ontology_acronym,
                            "Preferred Label": pref_label,
                            "Definition": definition,
                            "Ontology URI": links.get("ontology", "N/A"),
                            "Ontology Term URI": res.get("@id", "N/A")
                        })

                if ontology_data:
                    df_results = pd.DataFrame(ontology_data)
                    # 정렬: Preferred Label로 1차 정렬, Ontology Name으로 2차 정렬
                    df_results = df_results.sort_values(by=['Preferred Label', 'Ontology Name'])
                    st.session_state.ontology_results = df_results
                    st.session_state.filtered_ontology_results = df_results
                    return True
                else:
                    return False
            else:
                return False
        else:
            st.error(f"Error fetching data from API. Status code: {response.status_code}")
            return False
            
    except Exception as e:
        st.error(f"Error: {str(e)}. Check your API key and internet connection.")
        return False

# 수동 값 검색 함수 - 선택된 온톨로지 내에서만 검색
def manual_search_value(search_term):
    if not search_term:
        return False
    
    # 선택된 온톨로지가 없으면 알림
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False
        
    api_key = API_KEY
    
    # 쉼표 주변 공백 제거 - 검색어 전처리
    search_term = str(search_term).strip()
    
    # 기본 URL 구성
    base_url = f"https://data.bioontology.org/search?q={urllib.parse.quote(search_term)}&apikey={api_key}"
    
    # 선택된 온톨로지로 검색 제한
    ontologies_param = ",".join(st.session_state.selected_ontologies)
    url = f"{base_url}&ontologies={ontologies_param}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json().get("collection", [])
            if results:
                ontology_data = []
                for res in results:
                    # Preferred Label 필수
                    pref_label = res.get("prefLabel")
                    if not pref_label or pref_label == "N/A":
                        continue
                    
                    # 정의 (없으면 '정의 없음'으로 표시)
                    definition = res.get("definition", [None])[0] if res.get("definition") else "No definition available"
                    
                    # 온톨로지 약어 추출
                    ontology_acronym = "Unknown"
                    links = res.get("links", {})
                    
                    # 방법 1: ontology 링크에서 추출
                    if "ontology" in links:
                        ontology_uri = links["ontology"]
                        ontology_acronym = ontology_uri.split("/")[-1]
                    
                    # 방법 2: 소스 확인
                    source = res.get("source", None)
                    if source:
                        ontology_acronym = source
                    
                    # 방법 3: 컨텍스트에서 추출
                    context = res.get("context", {})
                    if context and "acronym" in context:
                        ontology_acronym = context["acronym"]

                    # 선택된 온톨로지 내에 있는지 확인
                    if ontology_acronym in st.session_state.selected_ontologies:
                        ontology_data.append({
                            "Ontology Name": ontology_acronym,
                            "Preferred Label": pref_label,
                            "Definition": definition,
                            "Ontology URI": links.get("ontology", "N/A"),
                            "Ontology Term URI": res.get("@id", "N/A")
                        })

                if ontology_data:
                    df_results = pd.DataFrame(ontology_data)
                    # 정렬: Preferred Label로 1차 정렬, Ontology Name으로 2차 정렬
                    df_results = df_results.sort_values(by=['Preferred Label', 'Ontology Name'])
                    st.session_state.value_ontology_results = df_results
                    return True
                else:
                    return False
            else:
                return False
        else:
            st.error(f"Error fetching data from API. Status code: {response.status_code}")
            return False
            
    except Exception as e:
        st.error(f"Error: {str(e)}. Check your API key and internet connection.")
        return False