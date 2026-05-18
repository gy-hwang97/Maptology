import streamlit as st
import yaml
import json
import pandas as pd
import io
from utils import get_column_data_type

try:
    from sssom.util import MappingSetDataFrame
    from sssom.writers import write_tsv as sssom_write_tsv
    from curies import Converter
    SSSOM_AVAILABLE = True
except ImportError:
    SSSOM_AVAILABLE = False

# friendly data type을 LinkML range로 변환
def dtype_to_range(data_type):
    """Data Type 문자열을 LinkML range 값으로 변환"""
    if data_type == "String":
        return "string"
    elif data_type == "Integer":
        return "integer"
    elif data_type == "Float":
        return "float"
    elif data_type == "Boolean":
        return "boolean"
    elif data_type == "Date":
        return "date"
    elif data_type == "Datetime":
        return "datetime"
    elif data_type == "Time":
        return "time"
    else:
        return "string"

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
        
        # DataFrame에서 현재 데이터 타입 가져오기
        data_type = get_column_data_type(column_name)
        range_value = dtype_to_range(data_type)
        
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
            "range": range_value,
            "annotations": {
                "data_type": {
                    "tag": "data_type",
                    "value": data_type
                }
            }
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
            
            # DataFrame에서 현재 데이터 타입 가져오기
            data_type = get_column_data_type(column_name)
            
            for value, val_mappings in value_dict.items():
                if isinstance(val_mappings, list):
                    for val_mapping in val_mappings:
                        if isinstance(val_mapping, dict) and "Preferred Label" in val_mapping:
                            comment = f"Value '{value}' maps to: {val_mapping['Preferred Label']} ({val_mapping.get('Ontology Term URI', '')})"
                            value_comments.append(comment)
                            uri = val_mapping.get('Ontology Term URI', '')
                            if uri and uri not in exact_mapping_uris:
                                exact_mapping_uris.append(uri)
                elif isinstance(val_mappings, dict) and "Preferred Label" in val_mappings:
                    comment = f"Value '{value}' maps to: {val_mappings['Preferred Label']} ({val_mappings.get('Ontology Term URI', '')})"
                    value_comments.append(comment)
                    uri = val_mappings.get('Ontology Term URI', '')
                    if uri and uri not in exact_mapping_uris:
                        exact_mapping_uris.append(uri)
            
            # 데이터 타입 변환
            range_value = dtype_to_range(data_type)
            
            attribute_def = {
                "name": safe_column_name,
                "description": f"Value mapping for column: {column_name}",
                "range": range_value,
                "annotations": {
                    "data_type": {
                        "tag": "data_type",
                        "value": data_type
                    }
                }
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
                "data_type": get_column_data_type(column_name),
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


# SSSOM TSV 생성 함수 / Generate SSSOM TSV
def generate_sssom_tsv():
    if not SSSOM_AVAILABLE:
        st.warning("SSSOM package is not installed. Run: pip install sssom curies")
        return None

    has_column_mappings = bool(st.session_state.mapped_terms)
    has_value_mappings = bool(st.session_state.value_ontology_mapping)

    if not has_column_mappings and not has_value_mappings:
        return None

    def safe_text(x):
        return str(x).strip().replace(" ", "_").replace("-", "_").replace("/", "_").lower()

    def build_prefix_map():
        return {
            "maptology": "https://example.org/maptology/",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "semapv": "https://w3id.org/semapv/vocab/",
            "sssom": "https://w3id.org/sssom/",
            "owl": "http://www.w3.org/2002/07/owl#",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        }

    def add_prefix_from_uri(uri, prefix_map):
        uri = str(uri).strip()

        # OBO 패턴 (http): http://purl.obolibrary.org/obo/HP_0000008
        if uri.startswith("http://purl.obolibrary.org/obo/"):
            tail = uri.replace("http://purl.obolibrary.org/obo/", "", 1)
            if "_" in tail:
                prefix = tail.split("_", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://purl.obolibrary.org/obo/{prefix}_"

        # OBO 패턴 (https): https://purl.obolibrary.org/obo/HP_0000008
        elif uri.startswith("https://purl.obolibrary.org/obo/"):
            tail = uri.replace("https://purl.obolibrary.org/obo/", "", 1)
            if "_" in tail:
                prefix = tail.split("_", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"https://purl.obolibrary.org/obo/{prefix}_"

        # BioPortal 패턴: http://purl.bioontology.org/ontology/SNOMEDCT/410607006
        elif uri.startswith("http://purl.bioontology.org/ontology/"):
            tail = uri.replace("http://purl.bioontology.org/ontology/", "", 1)
            if "/" in tail:
                prefix = tail.split("/", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://purl.bioontology.org/ontology/{prefix}/"

        # BioPortal data 패턴: https://data.bioontology.org/ontologies/...
        elif uri.startswith("https://data.bioontology.org/ontologies/"):
            tail = uri.replace("https://data.bioontology.org/ontologies/", "", 1)
            if "/" in tail:
                prefix = tail.split("/", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://purl.bioontology.org/ontology/{prefix}/"

        # NCIT 패턴: http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#C93501
        elif uri.startswith("http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#"):
            if "ncit" not in prefix_map:
                prefix_map["ncit"] = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#"

        # EBI/EFO 패턴: http://www.ebi.ac.uk/efo/EFO_0020103
        elif uri.startswith("http://www.ebi.ac.uk/efo/"):
            tail = uri.replace("http://www.ebi.ac.uk/efo/", "", 1)
            if "_" in tail:
                prefix = tail.split("_", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://www.ebi.ac.uk/efo/{prefix}_"

        # Identifiers.org 패턴: http://identifiers.org/xxx/12345
        elif uri.startswith("http://identifiers.org/"):
            tail = uri.replace("http://identifiers.org/", "", 1)
            if "/" in tail:
                prefix = tail.split("/", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://identifiers.org/{prefix}/"

    def uri_to_curie(uri, converter):
        uri = str(uri).strip()
        if not uri:
            return uri
        try:
            curie = converter.compress(uri)
            if curie:
                return curie
        except Exception:
            pass
        return uri

    try:
        prefix_map = build_prefix_map()

        all_object_uris = []

        for mapping in st.session_state.mapped_terms:
            uri = mapping.get("Ontology Term URI", "")
            if uri:
                all_object_uris.append(uri)

        for column_name, value_dict in st.session_state.value_ontology_mapping.items():
            for value, val_mappings in value_dict.items():
                if isinstance(val_mappings, list):
                    for val_mapping in val_mappings:
                        if isinstance(val_mapping, dict):
                            uri = val_mapping.get("Ontology Term URI", "")
                            if uri:
                                all_object_uris.append(uri)
                elif isinstance(val_mappings, dict):
                    uri = val_mappings.get("Ontology Term URI", "")
                    if uri:
                        all_object_uris.append(uri)

        for uri in all_object_uris:
            add_prefix_from_uri(uri, prefix_map)

        converter = Converter.from_prefix_map(prefix_map)

        rows = []

        for mapping in st.session_state.mapped_terms:
            col_name = mapping["Original Label"]
            safe_col = safe_text(col_name)
            object_uri = mapping.get("Ontology Term URI", "")
            object_id = uri_to_curie(object_uri, converter)

            rows.append({
                "subject_id": f"maptology:column__{safe_col}",
                "subject_label": col_name,
                "predicate_id": "skos:exactMatch",
                "object_id": object_id,
                "object_label": mapping.get("Preferred Label", ""),
                "mapping_justification": "semapv:ManualMappingCuration",
                "comment": "column-level mapping",
            })

        for column_name, value_dict in st.session_state.value_ontology_mapping.items():
            safe_col = safe_text(column_name)

            for value, val_mappings in value_dict.items():
                safe_val = safe_text(value)
                subject_id = f"maptology:value__{safe_col}__{safe_val}"
                subject_label = f"{column_name}: {value}"

                if isinstance(val_mappings, list):
                    iterable = val_mappings
                else:
                    iterable = [val_mappings]

                for val_mapping in iterable:
                    if isinstance(val_mapping, dict) and "Preferred Label" in val_mapping:
                        object_uri = val_mapping.get("Ontology Term URI", "")
                        object_id = uri_to_curie(object_uri, converter)

                        rows.append({
                            "subject_id": subject_id,
                            "subject_label": subject_label,
                            "predicate_id": "skos:exactMatch",
                            "object_id": object_id,
                            "object_label": val_mapping.get("Preferred Label", ""),
                            "mapping_justification": "semapv:ManualMappingCuration",
                            "comment": f"value-level mapping (column: {column_name})",
                        })

        if not rows:
            return None

        df = pd.DataFrame(rows)

        metadata = {
            "mapping_set_id": "https://example.org/maptology/mappings",
            "mapping_set_description": "Ontology mappings generated by Maptology",
            "license": "https://creativecommons.org/licenses/by/4.0/",
        }

        msdf = MappingSetDataFrame(df=df, converter=converter, metadata=metadata)
        msdf.standardize_references()
        
        # 안 쓰는 prefix 제거 / Remove unused prefixes
        msdf.clean_prefix_map()

        output = io.StringIO()
        sssom_write_tsv(msdf, output)
        return output.getvalue()

    except Exception as e:
        st.error(f"SSSOM generation error: {str(e)}")
        return None