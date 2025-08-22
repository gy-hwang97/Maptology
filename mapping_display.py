import streamlit as st
import pandas as pd
import urllib.parse
import yaml
import json
from mapping import remove_mapping, remove_value_mapping
from schema import generate_linkml_schema

# 매핑된 용어 섹션 렌더링 / Render mapped terms section
def render_mapped_terms():
    st.write("### Mapped Ontology Terms")
    st.caption("This table shows all the ontology terms you have mapped to your columns. You can view the full term details by clicking the links or remove mappings using the delete button.")
    
    header_col1, header_col2, header_col3, header_col4 = st.columns([3, 4, 2, 1])
    with header_col1:
        st.markdown("<strong>Original Label</strong>", unsafe_allow_html=True)
    with header_col2:
        st.markdown("<strong>Preferred Label(s)</strong>", unsafe_allow_html=True)
    with header_col3:
        st.markdown("<strong>Ontology Name</strong>", unsafe_allow_html=True)
    with header_col4:
        st.markdown("<strong>Delete</strong>", unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
    
    # 각 매핑을 개별적으로 표시 / Display each mapping individually
    for mapping in st.session_state.mapped_terms:
        column_name = mapping['Original Label']
        data_type = mapping.get('Data Type', 'String')
        
        type_class = "type-string"
        if data_type in ["Float", "Integer"]:
            type_class = "type-numeric"
        elif data_type == "Date":
            type_class = "type-date"
        elif data_type == "Categorical":
            type_class = "type-categorical"
        elif data_type == "Boolean":
            type_class = "type-boolean"
        
        col1, col2, col3, col4 = st.columns([3, 4, 2, 1])
        
        with col1:
            st.markdown(f"""
            <div>
                <span>{column_name}</span>
                <span class="type-badge {type_class}">{data_type}</span>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            ontology_abbr = mapping.get("Ontology Abbr", mapping["Ontology Name"].split(" ")[-1] if "(" in mapping["Ontology Name"] else mapping["Ontology Name"])
            preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(mapping['Ontology Term URI'], safe='')}"
            st.markdown(f"""
            <a href="{preferred_label_url}" target="_blank">{mapping['Preferred Label']}</a>
            """, unsafe_allow_html=True)
        
        with col3:
            ontology_abbr = mapping.get("Ontology Abbr", mapping["Ontology Name"].split(" ")[-1] if "(" in mapping["Ontology Name"] else mapping["Ontology Name"])
            ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
            st.markdown(f"""
            <a href="{ontology_url}" target="_blank">{mapping['Ontology Name']}</a>
            """, unsafe_allow_html=True)
        
        with col4:
            # 각 용어별 삭제 버튼 (고유 키 생성) / Delete button for each term (generate unique key)
            term_uri = mapping['Ontology Term URI']
            unique_key = f"delete_{column_name}_{term_uri.split('/')[-1]}"
            if st.button("🗑️", key=unique_key):
                from mapping import remove_term_mapping
                remove_term_mapping(column_name, term_uri)
        
        st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)

# 값-온톨로지 매핑 정보 표시 / Display value-ontology mapping information
def render_value_mappings():
    st.write("### Unique Values' Ontology Terms")
    st.caption("This table shows the ontology terms mapped to specific data values within your columns. Each row represents a value-to-term mapping that you have created.")
    
    header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([2, 2, 3, 2, 1])
    with header_col1:
        st.markdown("<strong>Column</strong>", unsafe_allow_html=True)
    with header_col2:
        st.markdown("<strong>Original Value</strong>", unsafe_allow_html=True)
    with header_col3:
        st.markdown("<strong>Mapped Term(s)</strong>", unsafe_allow_html=True)
    with header_col4:
        st.markdown("<strong>Ontology</strong>", unsafe_allow_html=True)
    with header_col5:
        st.markdown("<strong>Delete</strong>", unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
    
    for column in st.session_state.value_ontology_mapping:
        for value, val_mappings in st.session_state.value_ontology_mapping[column].items():
            if isinstance(val_mappings, list):
                # 각 매핑을 개별 행으로 표시 / Display each mapping as individual row
                for val_mapping in val_mappings:
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 2, 1])
                    
                    with col1:
                        st.write(f"{column}")
                    
                    with col2:
                        st.write(f"{value}")
                    
                    with col3:
                        ontology_abbr = val_mapping.get("Ontology Abbr", val_mapping["Ontology Name"].split(" ")[-1] if "(" in val_mapping["Ontology Name"] else val_mapping["Ontology Name"])
                        preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(val_mapping['Ontology Term URI'], safe='')}"
                        st.markdown(f"""
                        <a href="{preferred_label_url}" target="_blank">{val_mapping['Preferred Label']}</a>
                        """, unsafe_allow_html=True)
                    
                    with col4:
                        ontology_abbr = val_mapping.get("Ontology Abbr", val_mapping["Ontology Name"].split(" ")[-1] if "(" in val_mapping["Ontology Name"] else val_mapping["Ontology Name"])
                        ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
                        st.markdown(f"""
                        <a href="{ontology_url}" target="_blank">{val_mapping['Ontology Name']}</a>
                        """, unsafe_allow_html=True)
                    
                    with col5:
                        # 각 용어별 삭제 버튼 (고유 키 생성) / Delete button for each term (generate unique key)
                        term_uri = val_mapping['Ontology Term URI']
                        unique_key = f"delete_value_{column}_{value}_{term_uri.split('/')[-1]}"
                        if st.button("🗑️", key=unique_key):
                            from mapping import remove_individual_value_mapping
                            remove_individual_value_mapping(column, value, term_uri)
                    
                    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
            else:
                # 이전 버전 호환성을 위한 단일 매핑 처리 / Single mapping handling for backward compatibility
                col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 2, 1])
                
                with col1:
                    st.write(f"{column}")
                
                with col2:
                    st.write(f"{value}")
                
                with col3:
                    ontology_abbr = val_mappings.get("Ontology Abbr", val_mappings["Ontology Name"].split(" ")[-1] if "(" in val_mappings["Ontology Name"] else val_mappings["Ontology Name"])
                    preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(val_mappings['Ontology Term URI'], safe='')}"
                    st.markdown(f"""
                    <a href="{preferred_label_url}" target="_blank">{val_mappings['Preferred Label']}</a>
                    """, unsafe_allow_html=True)
                
                with col4:
                    ontology_abbr = val_mappings.get("Ontology Abbr", val_mappings["Ontology Name"].split(" ")[-1] if "(" in val_mappings["Ontology Name"] else val_mappings["Ontology Name"])
                    ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
                    st.markdown(f"""
                    <a href="{ontology_url}" target="_blank">{val_mappings['Ontology Name']}</a>
                    """, unsafe_allow_html=True)
                
                with col5:
                    # 각 용어별 삭제 버튼 / Delete button for each term
                    term_uri = val_mappings['Ontology Term URI']
                    unique_key = f"delete_value_{column}_{value}_{term_uri.split('/')[-1]}"
                    if st.button("🗑️", key=unique_key):
                        from mapping import remove_individual_value_mapping
                        remove_individual_value_mapping(column, value, term_uri)
                
                st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)

# 다운로드 버튼 렌더링 / Render download buttons
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
        
        column_csv = pd.DataFrame(column_mappings_list).to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download Column Mappings (CSV)",
            data=column_csv, 
            file_name="column_mappings.csv", 
            mime="text/csv"
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
                        "Definition": val_mappings.get("Definition", "")
                    })
        
        value_csv = pd.DataFrame(value_mappings_list).to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download Value Mappings (CSV)",
            data=value_csv,
            file_name="value_mappings.csv",
            mime="text/csv"
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
