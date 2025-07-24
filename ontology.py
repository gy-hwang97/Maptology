import streamlit as st
import requests
import pandas as pd
import urllib.parse
from utils import API_KEY

# 사용 가능한 온톨로지 목록 가져오기 / Get list of available ontologies
def get_available_ontologies():
    if not st.session_state.available_ontologies:
        try:
            url = f"https://data.bioontology.org/ontologies?apikey={API_KEY}"
            response = requests.get(url)
            
            if response.status_code == 200:
                ontologies = response.json()
                # 필요한 정보만 추출 (약어와 전체 이름) / Extract only necessary information (abbreviation and full name)
                st.session_state.available_ontologies = [
                    {
                        'acronym': ont.get('acronym', ''),
                        'name': ont.get('name', ''),
                        'description': ont.get('description', '')[:100] + '...' if ont.get('description') and len(ont.get('description')) > 100 else ont.get('description', '')
                    }
                    for ont in ontologies
                    if ont.get('acronym')  # 약어가 있는 경우만 포함 / Include only if abbreviation exists
                ]
                # 알파벳 순으로 정렬 / Sort alphabetically
                st.session_state.available_ontologies.sort(key=lambda x: x['acronym'])
        except Exception as e:
            st.error(f"Error fetching available ontologies: {str(e)}")
            st.session_state.available_ontologies = []
    
    return st.session_state.available_ontologies

# 온톨로지 정보를 가져오는 함수 (캐싱 적용) / Function to get ontology information (with caching)
def get_ontology_details(ontology_acronym):
    # 세션 캐시에서 먼저 확인 / Check session cache first
    if ontology_acronym in st.session_state.ontology_details_cache:
        return st.session_state.ontology_details_cache[ontology_acronym]
    
    # 캐시에 없으면 API 호출 / Call API if not in cache
    try:
        # BioPortal API를 통해 온톨로지 정보 요청 / Request ontology information through BioPortal API
        url = f"https://data.bioontology.org/ontologies/{ontology_acronym}?apikey={API_KEY}"
        response = requests.get(url)
        
        if response.status_code == 200:
            ontology_data = response.json()
            # 온톨로지 전체 이름 추출 / Extract full ontology name
            full_name = ontology_data.get('name', ontology_acronym)
            # 결과 캐싱 / Cache results
            st.session_state.ontology_details_cache[ontology_acronym] = {
                'full_name': full_name,
                'acronym': ontology_acronym
            }
            return st.session_state.ontology_details_cache[ontology_acronym]
        else:
            # API 오류 시 약어만 반환 / Return only abbreviation on API error
            st.session_state.ontology_details_cache[ontology_acronym] = {
                'full_name': ontology_acronym,
                'acronym': ontology_acronym
            }
            return st.session_state.ontology_details_cache[ontology_acronym]
    except Exception as e:
        # 예외 발생 시 약어만 반환 / Return only abbreviation on exception
        st.session_state.ontology_details_cache[ontology_acronym] = {
            'full_name': ontology_acronym,
            'acronym': ontology_acronym
        }
        return st.session_state.ontology_details_cache[ontology_acronym]

# 온톨로지 검색 함수 - 선택된 온톨로지 내에서만 검색하도록 수정 / Ontology search function - modified to search only within selected ontologies
def search_ontology(selected_column):
    if not selected_column:
        return
    
    # 선택된 온톨로지가 없으면 알림 / Alert if no ontology selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None
        return
        
    api_key = API_KEY
    
    # 쉼표 주변 공백 제거 - 검색어 전처리 / Remove spaces around commas - search term preprocessing
    search_term = selected_column.strip()
    
    # 기본 URL 구성 / Basic URL configuration
    base_url = f"https://data.bioontology.org/search?q={urllib.parse.quote(search_term)}&apikey={api_key}"
    
    # 선택된 온톨로지로 검색 제한 / Limit search to selected ontologies
    ontologies_param = ",".join(st.session_state.selected_ontologies)
    url = f"{base_url}&ontologies={ontologies_param}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json().get("collection", [])
            if results:
                ontology_data = []
                for res in results:
                    # Preferred Label와 Definition 값이 없는 경우는 결과에서 제외 / Exclude results without Preferred Label and Definition values
                    pref_label = res.get("prefLabel")
                    definition = res.get("definition", [None])[0] if res.get("definition") else None
                    if not pref_label or pref_label == "N/A":
                        continue
                    if not definition or definition == "N/A":
                        continue
                    
                    # 온톨로지 이름 추출 (URL에서 마지막 부분만 가져오기) / Extract ontology name (get only last part from URL)
                    ontology_uri = res.get("links", {}).get("ontology", "N/A")
                    ontology_name = ontology_uri.split("/")[-1] if ontology_uri != "N/A" else "N/A"

                    # 선택된 온톨로지 내에 있는지 확인 / Check if it's within selected ontologies
                    if ontology_name in st.session_state.selected_ontologies:
                        ontology_data.append({
                            "Ontology Name": ontology_name,
                            "Preferred Label": pref_label,
                            "Definition": definition,
                            "Ontology URI": ontology_uri,
                            "Ontology Term URI": res.get("@id", "N/A")
                        })

                if ontology_data:
                    df_results = pd.DataFrame(ontology_data)
                    # 정렬: Preferred Label로 1차 정렬, Ontology Name으로 2차 정렬 / Sort: primary by Preferred Label, secondary by Ontology Name
                    df_results = df_results.sort_values(by=['Preferred Label', 'Ontology Name'])
                    st.session_state.ontology_results = df_results
                    st.session_state.filtered_ontology_results = df_results  # 필터링된 결과 저장 / Save filtered results
                    
                    # 이전에 선택했던 인덱스가 현재 결과에 존재하지 않으면 초기화 / Initialize if previously selected index doesn't exist in current results
                    if (st.session_state.selected_term_index is not None and 
                        st.session_state.selected_term_index >= len(df_results)):
                        st.session_state.selected_term_index = None
                else:
                    st.warning("No valid ontology results found in selected ontologies.")
                    st.session_state.ontology_results = None
                    st.session_state.filtered_ontology_results = None
            else:
                st.warning("No results found. Try a different search term or select different ontologies.")
                st.session_state.ontology_results = None
                st.session_state.filtered_ontology_results = None
        else:
            st.error(f"Error fetching data from API. Status code: {response.status_code}")
            st.session_state.ontology_results = None
            st.session_state.filtered_ontology_results = None
            
    except Exception as e:
        st.error(f"Error: {str(e)}. Check your API key and internet connection.")
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None

# 값에 대한 온톨로지 검색 함수 - 선택된 온톨로지 내에서만 검색 / Ontology search function for values - search only within selected ontologies
def search_ontology_for_value(selected_value):
    if not selected_value:
        return
    
    # 선택된 온톨로지가 없으면 알림 / Alert if no ontology selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        st.session_state.value_ontology_results = None
        return
        
    api_key = API_KEY
    
    # 쉼표 주변 공백 제거 - 검색어 전처리 / Remove spaces around commas - search term preprocessing
    search_term = str(selected_value).strip()
    
    # 기본 URL 구성 / Basic URL configuration
    base_url = f"https://data.bioontology.org/search?q={urllib.parse.quote(search_term)}&apikey={api_key}"
    
    # 선택된 온톨로지로 검색 제한 / Limit search to selected ontologies
    ontologies_param = ",".join(st.session_state.selected_ontologies)
    url = f"{base_url}&ontologies={ontologies_param}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json().get("collection", [])
            if results:
                ontology_data = []
                for res in results:
                    # Preferred Label와 Definition 값이 없는 경우는 결과에서 제외 / Exclude results without Preferred Label and Definition values
                    pref_label = res.get("prefLabel")
                    definition = res.get("definition", [None])[0] if res.get("definition") else None
                    if not pref_label or pref_label == "N/A":
                        continue
                    if not definition or definition == "N/A":
                        continue
                    
                    # 온톨로지 이름 추출 (URL에서 마지막 부분만 가져오기) / Extract ontology name (get only last part from URL)
                    ontology_uri = res.get("links", {}).get("ontology", "N/A")
                    ontology_name = ontology_uri.split("/")[-1] if ontology_uri != "N/A" else "N/A"

                    # 선택된 온톨로지 내에 있는지 확인 / Check if it's within selected ontologies
                    if ontology_name in st.session_state.selected_ontologies:
                        ontology_data.append({
                            "Ontology Name": ontology_name,
                            "Preferred Label": pref_label,
                            "Definition": definition,
                            "Ontology URI": ontology_uri,
                            "Ontology Term URI": res.get("@id", "N/A")
                        })

                if ontology_data:
                    df_results = pd.DataFrame(ontology_data)
                    # 정렬: Preferred Label로 1차 정렬, Ontology Name으로 2차 정렬 / Sort: primary by Preferred Label, secondary by Ontology Name
                    df_results = df_results.sort_values(by=['Preferred Label', 'Ontology Name'])
                    st.session_state.value_ontology_results = df_results
                else:
                    st.warning(f"No valid ontology results found for value '{selected_value}' in selected ontologies.")
                    st.session_state.value_ontology_results = None
            else:
                st.warning(f"No results found for value '{selected_value}'. Try a different search term or select different ontologies.")
                st.session_state.value_ontology_results = None
        else:
            st.error(f"Error fetching data from API. Status code: {response.status_code}")
            st.session_state.value_ontology_results = None
            
    except Exception as e:
        st.error(f"Error: {str(e)}. Check your API key and internet connection.")
        st.session_state.value_ontology_results = None

# BioPortal 전체에서 컬럼 용어 검색 함수 (온톨로지 제한 없음) / Function to search column terms across all BioPortal (no ontology restrictions)
def search_bioportal_all_columns(search_term):
    if not search_term:
        return False
    
    # 선택된 온톨로지가 없으면 알림 / Alert if no ontology selected
    if not st.session_state.selected_ontologies:
        st.warning("온톨로지를 하나 이상 선택해주세요.")  # Please select at least one ontology
        return False
        
    api_key = API_KEY
    
    # 쉼표 주변 공백 제거 - 검색어 전처리 / Remove spaces around commas - search term preprocessing
    search_term = str(search_term).strip()
    
    # 기본 URL 구성 - 선택된 온톨로지로만 제한 / Basic URL configuration - limited to selected ontologies only
    base_url = f"https://data.bioontology.org/search?q={urllib.parse.quote(search_term)}&apikey={api_key}&pagesize=100"
    
    # 선택된 온톨로지로 검색 제한 / Limit search to selected ontologies
    ontologies_param = ",".join(st.session_state.selected_ontologies)
    url = f"{base_url}&ontologies={ontologies_param}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json().get("collection", [])
            total_count = response.json().get("totalCount", 0)
            
            if results:
                ontology_data = []
                for res in results:
                    # Preferred Label 필수 / Preferred Label required
                    pref_label = res.get("prefLabel")
                    if not pref_label or pref_label == "N/A":
                        continue
                    
                    # 정의 (없으면 '정의 없음'으로 표시) / Definition (display as 'no definition' if none)
                    definition = res.get("definition", [None])[0] if res.get("definition") else "정의 없음"  # No definition available
                    
                    # 온톨로지 약어 추출 / Extract ontology abbreviation
                    ontology_acronym = "Unknown"
                    links = res.get("links", {})
                    
                    # 방법 1: ontology 링크에서 추출 / Method 1: extract from ontology link
                    if "ontology" in links:
                        ontology_uri = links["ontology"]
                        ontology_acronym = ontology_uri.split("/")[-1]
                    
                    # 방법 2: 소스 확인 / Method 2: check source
                    source = res.get("source", None)
                    if source:
                        ontology_acronym = source
                    
                    # 방법 3: 컨텍스트에서 추출 / Method 3: extract from context
                    context = res.get("context", {})
                    if context and "acronym" in context:
                        ontology_acronym = context["acronym"]
                    
                    # 선택된 온톨로지에 있는지 확인 / Check if it's in selected ontologies
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
                    # 정렬: Preferred Label로 1차 정렬, Ontology Name으로 2차 정렬 / Sort: primary by Preferred Label, secondary by Ontology Name
                    df_results = df_results.sort_values(by=['Preferred Label', 'Ontology Name'])
                    st.session_state.ontology_results = df_results
                    st.session_state.filtered_ontology_results = df_results
                    
                    # 선택 초기화 / Initialize selection
                    st.session_state.selected_terms = []
                    
                    return True
                else:
                    st.warning(f"선택된 온톨로지에서 '{search_term}'에 대한 유효한 결과를 찾을 수 없습니다.")  # Cannot find valid results for '{search_term}' in selected ontologies
                    return False
            else:
                st.warning(f"선택된 온톨로지에서 '{search_term}'에 대한 결과를 찾을 수 없습니다.")  # Cannot find results for '{search_term}' in selected ontologies
                return False
        else:
            st.error(f"API에서 데이터 가져오기 오류. 상태 코드: {response.status_code}")  # Error fetching data from API. Status code: {response.status_code}
            return False
            
    except Exception as e:
        st.error(f"오류: {str(e)}. API 키와 인터넷 연결을 확인하세요.")  # Error: {str(e)}. Check your API key and internet connection
        return False

# BioPortal 전체에서 값 검색 함수 (온톨로지 제한 없음) / Function to search values across all BioPortal (no ontology restrictions)
def search_bioportal_all(search_term):
    if not search_term:
        return False
    
    # 선택된 온톨로지가 없으면 알림 / Alert if no ontology selected
    if not st.session_state.selected_ontologies:
        st.warning("온톨로지를 하나 이상 선택해주세요.")  # Please select at least one ontology
        return False
        
    api_key = API_KEY
    
    # 쉼표 주변 공백 제거 - 검색어 전처리 / Remove spaces around commas - search term preprocessing
    search_term = str(search_term).strip()
    
    # 기본 URL 구성 - 선택된 온톨로지로만 제한 / Basic URL configuration - limited to selected ontologies only
    base_url = f"https://data.bioontology.org/search?q={urllib.parse.quote(search_term)}&apikey={api_key}&pagesize=100"
    
    # 선택된 온톨로지로 검색 제한 / Limit search to selected ontologies
    ontologies_param = ",".join(st.session_state.selected_ontologies)
    url = f"{base_url}&ontologies={ontologies_param}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json().get("collection", [])
            total_count = response.json().get("totalCount", 0)
            
            if results:
                ontology_data = []
                for res in results:
                    # Preferred Label 필수 / Preferred Label required
                    pref_label = res.get("prefLabel")
                    if not pref_label or pref_label == "N/A":
                        continue
                    
                    # 정의 (없으면 '정의 없음'으로 표시) / Definition (display as 'no definition' if none)
                    definition = res.get("definition", [None])[0] if res.get("definition") else "정의 없음"  # No definition available
                    
                    # 온톨로지 약어 추출 / Extract ontology abbreviation
                    ontology_acronym = "Unknown"
                    links = res.get("links", {})
                    
                    # 방법 1: ontology 링크에서 추출 / Method 1: extract from ontology link
                    if "ontology" in links:
                        ontology_uri = links["ontology"]
                        ontology_acronym = ontology_uri.split("/")[-1]
                    
                    # 방법 2: 소스 확인 / Method 2: check source
                    source = res.get("source", None)
                    if source:
                        ontology_acronym = source
                    
                    # 방법 3: 컨텍스트에서 추출 / Method 3: extract from context
                    context = res.get("context", {})
                    if context and "acronym" in context:
                        ontology_acronym = context["acronym"]
                    
                    # 선택된 온톨로지에 있는지 확인 / Check if it's in selected ontologies
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
                    # 정렬: Preferred Label로 1차 정렬, Ontology Name으로 2차 정렬 / Sort: primary by Preferred Label, secondary by Ontology Name
                    df_results = df_results.sort_values(by=['Preferred Label', 'Ontology Name'])
                    st.session_state.ontology_results = df_results
                    st.session_state.filtered_ontology_results = df_results
                    
                    # 선택 초기화 / Initialize selection
                    st.session_state.selected_terms = []
                    
                    return True
                else:
                    st.warning(f"선택된 온톨로지에서 '{search_term}'에 대한 유효한 결과를 찾을 수 없습니다.")  # Cannot find valid results for '{search_term}' in selected ontologies
                    return False
            else:
                st.warning(f"선택된 온톨로지에서 '{search_term}'에 대한 결과를 찾을 수 없습니다.")  # Cannot find results for '{search_term}' in selected ontologies
                return False
        else:
            st.error(f"API에서 데이터 가져오기 오류. 상태 코드: {response.status_code}")  # Error fetching data from API. Status code: {response.status_code}
            return False
            
    except Exception as e:
        st.error(f"오류: {str(e)}. API 키와 인터넷 연결을 확인하세요.")  # Error: {str(e)}. Check your API key and internet connection
        return False

# 온톨로지 선택 처리 함수 (Select All 버튼용) / Ontology selection handling function (for Select All button)
def select_all_ontologies():
    # 최대 10개 제한 적용 / Apply maximum 10 limit
    all_ontologies = [ont['acronym'] for ont in st.session_state.available_ontologies]
    if len(all_ontologies) <= 10:
        st.session_state.selected_ontologies = all_ontologies
        st.session_state.ontologies_changed = True
        st.success(f"Selected all {len(all_ontologies)} ontologies")
    else:
        st.session_state.selected_ontologies = all_ontologies[:10]
        st.session_state.ontologies_changed = True
        st.warning(f"Selected first 10 ontologies out of {len(all_ontologies)} available (maximum 10 allowed)")

# 온톨로지 선택 해제 함수 (Select None 버튼용) / Ontology deselection function (for Select None button)
def select_none_ontologies():
    st.session_state.selected_ontologies = []
    st.session_state.ontologies_changed = True

# 온톨로지 선택 섹션 렌더링 / Render ontology selection section
def render_ontology_selection(available_ontologies):
    st.markdown('<div class="section-header section-purple">Select Ontologies</div>', unsafe_allow_html=True)
    
    # 실시간 업데이트 카운터용 컨테이너 생성 / Create container for real-time update counter
    counter_container = st.empty()
    
    # 버튼 행 / Button row
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Select All", key="btn_select_all"):
            select_all_ontologies()
    with col2:
        if st.button("Select None", key="btn_select_none"):
            select_none_ontologies()
    
    # 검색 필터링 추가 / Add search filtering
    filter_query = st.text_input("Filter ontologies", placeholder="Type to filter...")
    
    # 필터링된 온톨로지 목록 / Filtered ontology list
    filtered_ontologies = available_ontologies
    if filter_query:
        filtered_ontologies = [
            ont for ont in available_ontologies 
            if filter_query.lower() in ont['acronym'].lower() or filter_query.lower() in ont['name'].lower()
        ]
    
    # 확장 가능한 컨테이너 생성 / Create expandable container
    with st.expander("Ontology List", expanded=True):
        # st.container를 사용하여 스크롤이 가능한 영역 생성 / Create scrollable area using st.container
        with st.container(height=400):
            # 체크박스 생성 / Create checkboxes
            for idx, ont in enumerate(filtered_ontologies):
                acronym = ont['acronym']
                name = ont['name']
                tooltip = ont.get('description', '')
                
                # 체크박스 상태 확인 및 생성 / Check checkbox state and create
                is_checked = acronym in st.session_state.selected_ontologies
                
                # 현재 선택된 개수 계산 (실시간) / Calculate currently selected count (real-time)
                current_count = len(st.session_state.selected_ontologies)
                max_count = 10
                
                # 최대 선택 제한 확인 (이미 선택된 것은 체크 해제 가능) / Check maximum selection limit (already selected ones can be unchecked)
                is_disabled = (current_count >= max_count and not is_checked)
                
                checkbox = st.checkbox(
                    f"{acronym} - {name}",
                    value=is_checked,
                    key=f"ont_{acronym}",
                    help=tooltip,
                    disabled=is_disabled
                )
                
                # 체크박스 상태 업데이트 / Update checkbox state
                if checkbox and acronym not in st.session_state.selected_ontologies:
                    if len(st.session_state.selected_ontologies) < max_count:
                        st.session_state.selected_ontologies.append(acronym)
                        st.session_state.ontologies_changed = True
                        # 카운터 즉시 업데이트 / Immediately update counter
                        current_count = len(st.session_state.selected_ontologies)
                    else:
                        st.error(f"Cannot select more than {max_count} ontologies")
                elif not checkbox and acronym in st.session_state.selected_ontologies:
                    st.session_state.selected_ontologies.remove(acronym)
                    st.session_state.ontologies_changed = True
                    # 카운터 즉시 업데이트 / Immediately update counter
                    current_count = len(st.session_state.selected_ontologies)
                
                # 비활성화된 체크박스에 대한 설명 / Description for disabled checkboxes
                if is_disabled:
                    st.caption("🚫 Remove other selections to enable this option")
    
    # 실시간 카운터 및 상태 메시지 업데이트 / Real-time counter and status message updates
    current_count = len(st.session_state.selected_ontologies)
    max_count = 10
    
    # 카운터 컨테이너에 실시간 업데이트 / Real-time update in counter container
    with counter_container:
        col1, col2 = st.columns([1, 1])
        with col1:
            # 선택 개수 표시 (색상 코딩) / Display selection count (color coding)
            if current_count >= max_count:
                st.error(f"🚫 {current_count}/{max_count} - Maximum reached")
            elif current_count >= max_count * 0.8:  # 80% 이상일 때 경고 / Warning when 80% or more
                st.warning(f"⚠️ {current_count}/{max_count} - Nearly full")
            else:
                st.success(f"✅ {current_count}/{max_count} - Available")
        
        with col2:
            # 추가 상태 메시지 / Additional status messages
            if current_count >= max_count:
                st.info("🚫 Remove some to select others")
            elif current_count >= max_count * 0.8:
                remaining = max_count - current_count
                st.info(f"💡 {remaining} more available")
            else:
                st.info(f"🎯 Select up to {max_count - current_count} more")
    
    # 선택된 온톨로지 표시 / Display selected ontologies
    if st.session_state.selected_ontologies:
        st.write(f"**Selected ontologies ({current_count}/{max_count}):** {', '.join(st.session_state.selected_ontologies)}")
    else:
        st.warning("Please select at least one ontology to proceed.")
    
    # 온톨로지가 변경되었고 컬럼이 선택되어 있다면, 자동으로 검색 실행 / Automatically execute search if ontology changed and column is selected
    if st.session_state.ontologies_changed and st.session_state.selected_column and st.session_state.selected_ontologies:
        search_ontology(st.session_state.selected_column)
        
        # 값 매핑을 위한 자동 검색도 수행 / Also perform automatic search for value mapping
        if st.session_state.selected_unique_value:
            search_ontology_for_value(st.session_state.selected_unique_value)
        
        # 플래그 리셋 / Reset flag
        st.session_state.ontologies_changed = False
