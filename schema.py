import streamlit as st
import yaml
import json

# LinkML YAML 스키마 생성 함수 - 수정
def generate_linkml_schema():
    if not st.session_state.mapped_terms:
        st.warning("No mappings available to generate schema.")
        return None
    
    # 스키마 기본 구조 생성
    schema = {
        "id": "ontology_mapping_schema",
        "name": "Ontology_Mapping_Schema",
        "description": "Schema for ontology mappings with support for multiple terms per column/value",
        "imports": ["linkml:types"],
        "prefixes": {
            "linkml": "https://w3id.org/linkml/",
            "schema": "http://schema.org/",
            "xsd": "http://www.w3.org/2001/XMLSchema#"
        },
        "default_prefix": "ontology_mapping",
        "classes": {},
        "slots": {},
        "types": {}
    }
    
    # 클래스 생성 - 각 매핑된 컬럼에 대해 하나의 클래스 생성
    main_class = {
        "name": "DataMapping",
        "description": "A data mapping with multiple ontology terms",
        "attributes": {}
    }
    
    # 컬럼별로 그룹화
    column_mappings = {}
    for mapping in st.session_state.mapped_terms:
        column_name = mapping["Original Label"]
        if column_name not in column_mappings:
            column_mappings[column_name] = []
        column_mappings[column_name].append(mapping)
    
    # 그룹화된 매핑을 속성으로 추가
    for column_name, mappings in column_mappings.items():
        safe_column_name = column_name.replace(" ", "_").lower()
        
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
        
        # 속성 정의
        main_class["attributes"][safe_column_name] = {
            "description": f"Mapping for {column_name}",
            "range": range_value,
            "mappings": []
        }
        
        # 각 매핑 추가
        for mapping in mappings:
            main_class["attributes"][safe_column_name]["mappings"].append({
                "ontology": {
                    "label": mapping["Preferred Label"],
                    "ontology": mapping.get("Ontology Abbr", mapping["Ontology Name"]),
                    "uri": mapping["Ontology Term URI"]
                }
            })
        
        # 값 매핑이 있는 경우 추가
        if column_name in st.session_state.value_ontology_mapping:
            value_mappings_by_value = {}
            for value, val_mappings in st.session_state.value_ontology_mapping[column_name].items():
                if value not in value_mappings_by_value:
                    value_mappings_by_value[value] = []
                
                # 여기가 에러 부분: val_mappings가 리스트이므로 각 항목에 대해 반복 처리
                # val_mapping을 사용하기 전에 항상 리스트인지 딕셔너리인지 확인
                if isinstance(val_mappings, list):
                    # 리스트인 경우 각 항목 처리
                    for val_mapping in val_mappings:
                        if isinstance(val_mapping, dict) and "Preferred Label" in val_mapping:
                            value_mappings_by_value[value].append({
                                "mapped_term": {
                                    "label": val_mapping["Preferred Label"],
                                    "ontology": val_mapping.get("Ontology Abbr", val_mapping["Ontology Name"]),
                                    "uri": val_mapping["Ontology Term URI"]
                                }
                            })
                elif isinstance(val_mappings, dict) and "Preferred Label" in val_mappings:
                    # 과거 형식의 딕셔너리인 경우 (하위 호환성)
                    value_mappings_by_value[value].append({
                        "mapped_term": {
                            "label": val_mappings["Preferred Label"],
                            "ontology": val_mappings.get("Ontology Abbr", val_mappings["Ontology Name"]),
                            "uri": val_mappings["Ontology Term URI"]
                        }
                    })
            
            # 값 매핑을 스키마에 추가
            main_class["attributes"][safe_column_name]["value_mappings"] = []
            for value, term_mappings in value_mappings_by_value.items():
                main_class["attributes"][safe_column_name]["value_mappings"].append({
                    "original_value": value,
                    "terms": term_mappings
                })
    
    # 클래스 추가
    schema["classes"]["DataMapping"] = main_class
    
    return schema

# LinkML 스키마 다운로드 함수
def download_linkml_schema():
    schema = generate_linkml_schema()
    if schema:
        # YAML로 변환
        yaml_str = yaml.dump(schema, sort_keys=False, default_flow_style=False)
        
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