import streamlit as st
import pandas as pd
import urllib.parse
import yaml
import json
from mapping import remove_mapping, remove_value_mapping
from schema import generate_linkml_schema

# 매핑된 용어 섹션 렌더링 (각 행마다 타입 변경 가능)
def render_mapped_terms():
    st.write("### Mapped Ontology Terms")
    st.caption("This table shows all the ontology terms you have mapped to your columns. You can change data types, view term details, or remove mappings.")
    
    dtype_options = ["String", "Categorical", "Float", "Integer", "Boolean", "Date"]
    
    header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([2.5, 1.5, 3, 2, 0.5])
    with header_col1:
        st.markdown("<strong>Original Label</strong>", unsafe_allow_html=True)
    with header_col2:
        st.markdown("<strong>Data Type</strong>", unsafe_allow_html=True)
    with header_col3:
        st.markdown("<strong>Preferred Label(s)</strong>", unsafe_allow_html=True)
    with header_col4:
        st.markdown("<strong>Ontology Name</strong>", unsafe_allow_html=True)
    with header_col5:
        st.markdown("<strong></strong>", unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
    
    # 각 매핑을 개별적으로 표시
    for idx, mapping in enumerate(st.session_state.mapped_terms):
        column_name = mapping['Original Label']
        data_type = mapping.get('Data Type', 'String')
        
        col1, col2, col3, col4, col5 = st.columns([2.5, 1.5, 3, 2, 0.5])
        
        with col1:
            st.write(column_name)
        
        with col2:
            # 각 행에 드롭다운 표시 - key를 term_uri 기반으로 (삭제 시 인덱스 변경 문제 해결)
            default_index = dtype_options.index(data_type) if data_type in dtype_options else 0
            term_uri = mapping['Ontology Term URI']
            # URI에서 고유 식별자 추출
            uri_key = term_uri.split('/')[-1].replace('#', '_').replace('.', '_')
            
            new_type = st.selectbox(
                "Type",
                dtype_options,
                index=default_index,
                key=f"type_select_{column_name}_{uri_key}",
                label_visibility="collapsed"
            )
            
            # 타입이 변경되었으면 해당 매핑의 Data Type만 업데이트
            if new_type != data_type:
                st.session_state.mapped_terms[idx]['Data Type'] = new_type
                st.rerun()
        
        with col3:
            ontology_abbr = mapping.get("Ontology Abbr", mapping["Ontology Name"].split(" ")[-1] if "(" in mapping["Ontology Name"] else mapping["Ontology Name"])
            preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(mapping['Ontology Term URI'], safe='')}"
            st.markdown(f"""
            <a href="{preferred_label_url}" target="_blank">{mapping['Preferred Label']}</a>
            """, unsafe_allow_html=True)
        
        with col4:
            ontology_abbr = mapping.get("Ontology Abbr", mapping["Ontology Name"].split(" ")[-1] if "(" in mapping["Ontology Name"] else mapping["Ontology Name"])
            ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
            st.markdown(f"""
            <a href="{ontology_url}" target="_blank">{mapping['Ontology Name']}</a>
            """, unsafe_allow_html=True)
        
        with col5:
            term_uri = mapping['Ontology Term URI']
            unique_key = f"delete_{column_name}_{term_uri.split('/')[-1]}"
            if st.button("🗑️", key=unique_key):
                from mapping import remove_term_mapping
                remove_term_mapping(column_name, term_uri)
        
        st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)

# 값-온톨로지 매핑 정보 표시 (Data Type 컬럼 추가)
def render_value_mappings():
    st.write("### Unique Values' Ontology Terms")
    st.caption("This table shows the ontology terms mapped to specific data values within your columns. Each row represents a value-to-term mapping that you have created.")
    
    dtype_options = ["String", "Categorical", "Float", "Integer", "Boolean", "Date"]
    
    header_col1, header_col2, header_col3, header_col4, header_col5, header_col6 = st.columns([1.8, 1.5, 1.3, 2.5, 2, 0.5])
    with header_col1:
        st.markdown("<strong>Column</strong>", unsafe_allow_html=True)
    with header_col2:
        st.markdown("<strong>Original Value</strong>", unsafe_allow_html=True)
    with header_col3:
        st.markdown("<strong>Data Type</strong>", unsafe_allow_html=True)
    with header_col4:
        st.markdown("<strong>Mapped Term(s)</strong>", unsafe_allow_html=True)
    with header_col5:
        st.markdown("<strong>Ontology</strong>", unsafe_allow_html=True)
    with header_col6:
        st.markdown("<strong></strong>", unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
    
    mapping_idx = 0
    for column in st.session_state.value_ontology_mapping:
        for value, val_mappings in st.session_state.value_ontology_mapping[column].items():
            if isinstance(val_mappings, list):
                for val_mapping in val_mappings:
                    col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1.5, 1.3, 2.5, 2, 0.5])
                    
                    with col1:
                        st.write(f"{column}")
                    
                    with col2:
                        st.write(f"{value}")
                    
                    with col3:
                        # Data Type 드롭다운 - key를 term_uri 기반으로
                        data_type = val_mapping.get('Data Type', 'String')
                        default_index = dtype_options.index(data_type) if data_type in dtype_options else 0
                        term_uri = val_mapping['Ontology Term URI']
                        uri_key = term_uri.split('/')[-1].replace('#', '_').replace('.', '_')
                        
                        new_type = st.selectbox(
                            "Type",
                            dtype_options,
                            index=default_index,
                            key=f"val_type_select_{column}_{value}_{uri_key}",
                            label_visibility="collapsed"
                        )
                        
                        # 타입이 변경되었으면 해당 매핑의 Data Type 업데이트
                        if new_type != data_type:
                            val_mapping['Data Type'] = new_type
                            st.rerun()
                    
                    with col4:
                        ontology_abbr = val_mapping.get("Ontology Abbr", val_mapping["Ontology Name"].split(" ")[-1] if "(" in val_mapping["Ontology Name"] else val_mapping["Ontology Name"])
                        preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(val_mapping['Ontology Term URI'], safe='')}"
                        st.markdown(f"""
                        <a href="{preferred_label_url}" target="_blank">{val_mapping['Preferred Label']}</a>
                        """, unsafe_allow_html=True)
                    
                    with col5:
                        ontology_abbr = val_mapping.get("Ontology Abbr", val_mapping["Ontology Name"].split(" ")[-1] if "(" in val_mapping["Ontology Name"] else val_mapping["Ontology Name"])
                        ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
                        st.markdown(f"""
                        <a href="{ontology_url}" target="_blank">{val_mapping['Ontology Name']}</a>
                        """, unsafe_allow_html=True)
                    
                    with col6:
                        term_uri = val_mapping['Ontology Term URI']
                        unique_key = f"delete_value_{column}_{value}_{term_uri.split('/')[-1]}"
                        if st.button("🗑️", key=unique_key):
                            from mapping import remove_individual_value_mapping
                            remove_individual_value_mapping(column, value, term_uri)
                    
                    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
                    mapping_idx += 1
            else:
                col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1.5, 1.3, 2.5, 2, 0.5])
                
                with col1:
                    st.write(f"{column}")
                
                with col2:
                    st.write(f"{value}")
                
                with col3:
                    # Data Type 드롭다운 - key를 term_uri 기반으로
                    data_type = val_mappings.get('Data Type', 'String')
                    default_index = dtype_options.index(data_type) if data_type in dtype_options else 0
                    term_uri = val_mappings['Ontology Term URI']
                    uri_key = term_uri.split('/')[-1].replace('#', '_').replace('.', '_')
                    
                    new_type = st.selectbox(
                        "Type",
                        dtype_options,
                        index=default_index,
                        key=f"val_type_select_{column}_{value}_{uri_key}",
                        label_visibility="collapsed"
                    )
                    
                    # 타입이 변경되었으면 해당 매핑의 Data Type 업데이트
                    if new_type != data_type:
                        val_mappings['Data Type'] = new_type
                        st.rerun()
                
                with col4:
                    ontology_abbr = val_mappings.get("Ontology Abbr", val_mappings["Ontology Name"].split(" ")[-1] if "(" in val_mappings["Ontology Name"] else val_mappings["Ontology Name"])
                    preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(val_mappings['Ontology Term URI'], safe='')}"
                    st.markdown(f"""
                    <a href="{preferred_label_url}" target="_blank">{val_mappings['Preferred Label']}</a>
                    """, unsafe_allow_html=True)
                
                with col5:
                    ontology_abbr = val_mappings.get("Ontology Abbr", val_mappings["Ontology Name"].split(" ")[-1] if "(" in val_mappings["Ontology Name"] else val_mappings["Ontology Name"])
                    ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
                    st.markdown(f"""
                    <a href="{ontology_url}" target="_blank">{val_mappings['Ontology Name']}</a>
                    """, unsafe_allow_html=True)
                
                with col6:
                    term_uri = val_mappings['Ontology Term URI']
                    unique_key = f"delete_value_{column}_{value}_{term_uri.split('/')[-1]}"
                    if st.button("🗑️", key=unique_key):
                        from mapping import remove_individual_value_mapping
                        remove_individual_value_mapping(column, value, term_uri)
                
                st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
                mapping_idx += 1

# 다운로드 버튼 렌더링
def render_download_buttons():
    st.write("### Download Results")
    st.caption("Export your mapping results in various formats for use in other applications or for record keeping.")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        column_mappings_list = []
        for mapping in st.session_state.mapped_terms:
            column_name = mapping['Original Label']
            column_mappings_list.append({
                "Column Name": column_name,
                "Preferred Label": mapping['Preferred Label'],
                "Ontology Name": mapping['Ontology Name'],
                "Ontology URI": mapping['Ontology URI'],
                "Ontology Term URI": mapping['Ontology Term URI'],
                "Data Type": mapping.get('Data Type', 'String'),
                "Definition": mapping.get('Definition', '')
            })
        
        if column_mappings_list:
            column_csv = pd.DataFrame(column_mappings_list).to_csv(index=False).encode('utf-8')
            st.download_button(
                "Download Column Mappings (CSV)",
                data=column_csv, 
                file_name="column_mappings.csv", 
                mime="text/csv"
            )
        else:
            st.download_button(
                "Download Column Mappings (CSV)",
                data="No column mappings",
                file_name="column_mappings.csv",
                mime="text/csv",
                disabled=True
            )

    with col2:
        value_mappings_list = []
        for column, value_dict in st.session_state.value_ontology_mapping.items():
            for value, val_mappings in value_dict.items():
                if isinstance(val_mappings, list):
                    for val_mapping in val_mappings:
                        value_mappings_list.append({
                            "Column": column,
                            "Value": value,
                            "Preferred Label": val_mapping["Preferred Label"],
                            "Ontology Name": val_mapping["Ontology Name"],
                            "Ontology URI": val_mapping["Ontology URI"],
                            "Ontology Term URI": val_mapping["Ontology Term URI"],
                            "Data Type": val_mapping.get("Data Type", "String"),
                            "Definition": val_mapping.get("Definition", "")
                        })
                else:
                    value_mappings_list.append({
                        "Column": column,
                        "Value": value,
                        "Preferred Label": val_mappings["Preferred Label"],
                        "Ontology Name": val_mappings["Ontology Name"],
                        "Ontology URI": val_mappings["Ontology URI"],
                        "Ontology Term URI": val_mappings["Ontology Term URI"],
                        "Data Type": val_mappings.get("Data Type", "String"),
                        "Definition": val_mappings.get("Definition", "")
                    })
        
        if value_mappings_list:
            value_csv = pd.DataFrame(value_mappings_list).to_csv(index=False).encode('utf-8')
            st.download_button(
                "Download Value Mappings (CSV)",
                data=value_csv,
                file_name="value_mappings.csv",
                mime="text/csv"
            )
        else:
            st.download_button(
                "Download Value Mappings (CSV)",
                data="No value mappings",
                file_name="value_mappings.csv",
                mime="text/csv",
                disabled=True
            )

    schema = generate_linkml_schema()
    if schema:
        with col3:
            yaml_str = yaml.dump(schema, sort_keys=False, default_flow_style=False)
            st.download_button(
                "Download LinkML Schema (YAML)",
                data=yaml_str,
                file_name="ontology_mapping_schema.yaml",
                mime="text/yaml"
            )
        
        with col4:
            json_str = json.dumps(schema, indent=2)
            st.download_button(
                "Download Schema as JSON",
                data=json_str,
                file_name="ontology_mapping_schema.json",
                mime="application/json"
            )
