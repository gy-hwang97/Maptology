import streamlit as st
import yaml
import json

# LinkML YAML 스키마 생성 함수 - LinkML 표준 형식으로 수정
def generate_linkml_schema():
    # mapped_terms 또는 value_ontology_mapping 중 하나라도 있으면 스키마 생성
    has_column_mappings = bool(st.session_state.mapped_terms)
    has_value_mappings = bool(st.session_state.value_ontology_mapping)
    
    if not has_column_mappings and not has_value_mappings:
        st.warning("No mappings available to generate schema.")
        return None
    
    # 스키마 기본 구조 생성
    schema = {
        "id": "https://example.org/ontology_mapping_schema",
        "name": "ontology_mapping_schema",
        "description": "Schema for ontology mappings with support for multiple terms per column/value",
        "imports": ["linkml:types"],
        "prefixes": {
            "linkml": "https://w3id.org/linkml/",
            "schema": "http://schema.org/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "ontology_mapping": "https://example.org/ontology_mapping/"
        },
        "default_prefix": "ontology_mapping",
        "default_range": "string",
        "classes": {},
        "slots": {}
    }
    
    # 컬럼별로 그룹화
    column_mappings = {}
    for mapping in st.session_state.mapped_terms:
        column_name = mapping["Original Label"]
        if column_name not in column_mappings:
            column_mappings[column_name] = []
        column_mappings[column_name].append(mapping)
    
    # 메인 클래스 생성
    main_class = {
        "name": "DataMapping",
        "description": "A data mapping with multiple ontology terms",
        "attributes": {}
    }
    
    # 그룹화된 매핑을 속성으로 추가
    for column_name, mappings in column_mappings.items():
        safe_column_name = column_name.replace(" ", "_").replace("-", "_").lower()
        
        # 첫 번째 매핑에서 데이터 타입 가져오기
        data_type = mappings[0].get("Data Type", "String")
        if data_type == "String" or data_type == "Categorical":
            range_value = "string"
        elif data_type == "Integer":
            range_value = "integer"
        elif data_type == "Float":
            range_value = "float"
        elif data_type == "Boolean":
            range_value = "boolean"
        elif data_type == "Date":
            range_value = "date"
        else:
            range_value = "string"
        
        # 온톨로지 URI 목록 추출 (exact_mappings 용)
        exact_mapping_uris = []
        for mapping in mappings:
            uri = mapping.get("Ontology Term URI", "")
            if uri and uri not in exact_mapping_uris:
                exact_mapping_uris.append(uri)
        
        # 속성 정의 - LinkML 표준 필드만 사용
        attribute_def = {
            "name": safe_column_name,
            "description": f"Mapping for column: {column_name}",
            "range": range_value
        }
        
        # exact_mappings 추가 (온톨로지 URI 목록)
        if exact_mapping_uris:
            attribute_def["exact_mappings"] = exact_mapping_uris
        
        # 값 매핑이 있는 경우 comments에 추가 (LinkML 표준 필드)
        if column_name in st.session_state.value_ontology_mapping:
            value_comments = []
            for value, val_mappings in st.session_state.value_ontology_mapping[column_name].items():
                if isinstance(val_mappings, list):
                    for val_mapping in val_mappings:
                        if isinstance(val_mapping, dict) and "Preferred Label" in val_mapping:
                            comment = f"Value '{value}' maps to: {val_mapping['Preferred Label']} ({val_mapping.get('Ontology Term URI', '')})"
                            value_comments.append(comment)
                elif isinstance(val_mappings, dict) and "Preferred Label" in val_mappings:
                    comment = f"Value '{value}' maps to: {val_mappings['Preferred Label']} ({val_mappings.get('Ontology Term URI', '')})"
                    value_comments.append(comment)
            
            if value_comments:
                attribute_def["comments"] = value_comments
        
        main_class["attributes"][safe_column_name] = attribute_def
    
    # value_ontology_mapping만 있는 경우 (mapped_terms 없음)
    if not has_column_mappings and has_value_mappings:
        for column_name, value_dict in st.session_state.value_ontology_mapping.items():
            safe_column_name = column_name.replace(" ", "_").replace("-", "_").lower()
            
            value_comments = []
            exact_mapping_uris = []
            data_type = "String"
            
            for value, val_mappings in value_dict.items():
                if isinstance(val_mappings, list):
                    for val_mapping in val_mappings:
                        if isinstance(val_mapping, dict) and "Preferred Label" in val_mapping:
                            comment = f"Value '{value}' maps to: {val_mapping['Preferred Label']} ({val_mapping.get('Ontology Term URI', '')})"
                            value_comments.append(comment)
                            uri = val_mapping.get('Ontology Term URI', '')
                            if uri and uri not in exact_mapping_uris:
                                exact_mapping_uris.append(uri)
                            if 'Data Type' in val_mapping:
                                data_type = val_mapping['Data Type']
                elif isinstance(val_mappings, dict) and "Preferred Label" in val_mappings:
                    comment = f"Value '{value}' maps to: {val_mappings['Preferred Label']} ({val_mappings.get('Ontology Term URI', '')})"
                    value_comments.append(comment)
                    uri = val_mappings.get('Ontology Term URI', '')
                    if uri and uri not in exact_mapping_uris:
                        exact_mapping_uris.append(uri)
                    if 'Data Type' in val_mappings:
                        data_type = val_mappings['Data Type']
            
            # 데이터 타입 변환
            if data_type == "String" or data_type == "Categorical":
                range_value = "string"
            elif data_type == "Integer":
                range_value = "integer"
            elif data_type == "Float":
                range_value = "float"
            elif data_type == "Boolean":
                range_value = "boolean"
            elif data_type == "Date":
                range_value = "date"
            else:
                range_value = "string"
            
            attribute_def = {
                "name": safe_column_name,
                "description": f"Value mapping for column: {column_name}",
                "range": range_value
            }
            
            if exact_mapping_uris:
                attribute_def["exact_mappings"] = exact_mapping_uris
            
            if value_comments:
                attribute_def["comments"] = value_comments
            
            main_class["attributes"][safe_column_name] = attribute_def
    
    # 클래스 추가
    schema["classes"]["DataMapping"] = main_class
    
    return schema


# 값 매핑 정보를 포함한 확장 스키마 생성 (JSON 전용 - 검증 목적 아님)
def generate_extended_schema():
    """값 매핑 정보를 포함한 확장 스키마 (내부 사용/문서화 목적)"""
    has_column_mappings = bool(st.session_state.mapped_terms)
    has_value_mappings = bool(st.session_state.value_ontology_mapping)
    
    if not has_column_mappings and not has_value_mappings:
        return None
    
    schema = {
        "schema_type": "extended_ontology_mapping",
        "description": "Extended schema with value mappings (for documentation purposes, not LinkML compliant)",
        "column_mappings": {},
        "value_mappings": {}
    }
    
    # 컬럼 매핑 정보
    for mapping in st.session_state.mapped_terms:
        column_name = mapping["Original Label"]
        if column_name not in schema["column_mappings"]:
            schema["column_mappings"][column_name] = {
                "data_type": mapping.get("Data Type", "String"),
                "ontology_terms": []
            }
        
        schema["column_mappings"][column_name]["ontology_terms"].append({
            "preferred_label": mapping["Preferred Label"],
            "ontology_name": mapping["Ontology Name"],
            "ontology_abbr": mapping.get("Ontology Abbr", ""),
            "ontology_uri": mapping.get("Ontology URI", ""),
            "term_uri": mapping["Ontology Term URI"],
            "definition": mapping.get("Definition", "")
        })
    
    # 값 매핑 정보
    for column_name, value_dict in st.session_state.value_ontology_mapping.items():
        if column_name not in schema["value_mappings"]:
            schema["value_mappings"][column_name] = {}
        
        for value, val_mappings in value_dict.items():
            schema["value_mappings"][column_name][value] = []
            
            if isinstance(val_mappings, list):
                for val_mapping in val_mappings:
                    if isinstance(val_mapping, dict) and "Preferred Label" in val_mapping:
                        schema["value_mappings"][column_name][value].append({
                            "preferred_label": val_mapping["Preferred Label"],
                            "ontology_name": val_mapping["Ontology Name"],
                            "term_uri": val_mapping["Ontology Term URI"],
                            "definition": val_mapping.get("Definition", "")
                        })
            elif isinstance(val_mappings, dict) and "Preferred Label" in val_mappings:
                schema["value_mappings"][column_name][value].append({
                    "preferred_label": val_mappings["Preferred Label"],
                    "ontology_name": val_mappings["Ontology Name"],
                    "term_uri": val_mappings["Ontology Term URI"],
                    "definition": val_mappings.get("Definition", "")
                })
    
    return schema


# LinkML 스키마 다운로드 함수
def download_linkml_schema():
    schema = generate_linkml_schema()
    if schema:
        # YAML로 변환
        yaml_str = yaml.dump(schema, sort_keys=False, default_flow_style=False, allow_unicode=True)
        
        # 다운로드 버튼 추가
        st.download_button(
            "Download LinkML Schema (YAML)",
            data=yaml_str,
            file_name="ontology_mapping_schema.yaml",
            mime="text/yaml"
        )
        
        # JSON 형식으로도 제공
        json_str = json.dumps(schema, indent=2)
        st.download_button(
            "Download Schema as JSON",
            data=json_str,
            file_name="ontology_mapping_schema.json",
            mime="application/json"
        )
        
        return True
    return False
