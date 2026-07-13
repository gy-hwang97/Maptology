import streamlit as st
import yaml
import json
import os
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

# Resolved against the repo root (this file lives in src/Maptology/) rather than
# the current working directory, so the file is found no matter which directory
# the app is launched from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# The basic data type of a column is recorded as an ontology term (not only as a
# plain value), using the schema.org DataType vocabulary. Maptology's data types
# map one-to-one onto schema.org's data types.
SCHEMA_ORG_NS = "http://schema.org/"
DATA_TYPE_TERMS = {
    "String": "Text",
    "Integer": "Integer",
    "Float": "Float",
    "Boolean": "Boolean",
    "Date": "Date",
    "Datetime": "DateTime",
    "Time": "Time",
}


def data_type_term(data_type):
    """Return (label, uri) of the schema.org term for a Maptology data type."""
    label = DATA_TYPE_TERMS.get(data_type, "Text")
    return label, SCHEMA_ORG_NS + label


def data_type_from_term(term):
    """Inverse of data_type_term(): a schema.org term back to a Maptology data
    type. Accepts a full URI ("http://schema.org/Text"), a CURIE ("schema:Text")
    or a bare label ("Text"). Returns "" if it is not a known data type."""
    label = str(term or "").strip().rsplit("/", 1)[-1].split(":")[-1]
    for data_type, term_label in DATA_TYPE_TERMS.items():
        if term_label.lower() == label.lower():
            return data_type
    return ""


# Convert a friendly data type to a LinkML range
def dtype_to_range(data_type):
    """Convert a Data Type string to a LinkML range value."""
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

# Generate a LinkML YAML schema (standard LinkML format)
def generate_linkml_schema():
    # Generate a schema if either mapped_terms or value_ontology_mapping exists
    has_column_mappings = bool(st.session_state.mapped_terms)
    has_value_mappings = bool(st.session_state.value_ontology_mapping)
    
    if not has_column_mappings and not has_value_mappings:
        st.warning("No mappings available to generate schema.")
        return None
    
    # Build the base schema structure
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
    
    # Group by column
    column_mappings = {}
    for mapping in st.session_state.mapped_terms:
        column_name = mapping["Original Label"]
        if column_name not in column_mappings:
            column_mappings[column_name] = []
        column_mappings[column_name].append(mapping)
    
    # Create the main class
    main_class = {
        "name": "DataMapping",
        "description": "A data mapping with multiple ontology terms",
        "attributes": {}
    }
    
    # Add the grouped mappings as attributes
    for column_name, mappings in column_mappings.items():
        safe_column_name = column_name.replace(" ", "_").replace("-", "_").lower()
        
        # Get the current data type from the DataFrame
        data_type = get_column_data_type(column_name)
        range_value = dtype_to_range(data_type)
        
        # Collect the ontology URIs (for exact_mappings)
        exact_mapping_uris = []
        for mapping in mappings:
            uri = mapping.get("Ontology Term URI", "")
            if uri and uri not in exact_mapping_uris:
                exact_mapping_uris.append(uri)
        
        # Attribute definition - only standard LinkML fields
        # title = original column name (case/whitespace preserved). Used for re-import matching
        dt_label, dt_uri = data_type_term(data_type)
        attribute_def = {
            "name": safe_column_name,
            "title": column_name,
            "description": f"Mapping for column: {column_name}",
            "range": range_value,
            "annotations": {
                "data_type": {
                    "tag": "data_type",
                    "value": data_type
                },
                # The same basic data type, as a schema.org ontology term.
                "data_type_term": {
                    "tag": "data_type_term",
                    "value": dt_uri
                }
            }
        }
        
        # Add exact_mappings (list of ontology URIs)
        if exact_mapping_uris:
            attribute_def["exact_mappings"] = exact_mapping_uris
        
        # If there are value mappings, add them to comments (standard LinkML field)
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
    
    # When only value_ontology_mapping exists (no mapped_terms)
    if not has_column_mappings and has_value_mappings:
        for column_name, value_dict in st.session_state.value_ontology_mapping.items():
            safe_column_name = column_name.replace(" ", "_").replace("-", "_").lower()
            
            value_comments = []
            exact_mapping_uris = []
            
            # Get the current data type from the DataFrame
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
            
            # Convert the data type
            range_value = dtype_to_range(data_type)
            
            dt_label, dt_uri = data_type_term(data_type)
            attribute_def = {
                "name": safe_column_name,
                "title": column_name,
                "description": f"Value mapping for column: {column_name}",
                "range": range_value,
                "annotations": {
                    "data_type": {
                        "tag": "data_type",
                        "value": data_type
                    },
                    # The same basic data type, as a schema.org ontology term.
                    "data_type_term": {
                        "tag": "data_type_term",
                        "value": dt_uri
                    }
                }
            }
            
            if exact_mapping_uris:
                attribute_def["exact_mappings"] = exact_mapping_uris
            
            if value_comments:
                attribute_def["comments"] = value_comments
            
            main_class["attributes"][safe_column_name] = attribute_def
    
    # Add the class
    schema["classes"]["DataMapping"] = main_class

    # Structured block for round-trip re-import.
    # The human-readable description/comments are left as-is; the exact,
    # machine-readable mapping data is stored alongside as JSON in a
    # schema-level annotation, so re-import doesn't need to parse free text.
    schema["annotations"] = {
        "maptology_mappings": {
            "tag": "maptology_mappings",
            "value": json.dumps(_build_roundtrip_payload(), ensure_ascii=False)
        },
        # Record WHICH ontology version each mapping was made against, so a file
        # can be interpreted later even after the ontologies are updated.
        "ontology_versions": {
            "tag": "ontology_versions",
            "value": json.dumps(_ontology_versions_used(), ensure_ascii=False)
        }
    }

    return schema


# 매핑에 사용된 온톨로지들의 버전 정보 / Versions of the ontologies used here.
# Reads ontology_cache/ontology_versions.json (populated by version_check.py).
# Returns {abbr: {version, released, submissionId}}; "unknown" if not recorded.
def _ontology_versions_used():
    used = set()
    for m in st.session_state.mapped_terms:
        abbr = m.get("Ontology Abbr")
        if abbr:
            used.add(abbr)
    for value_dict in st.session_state.value_ontology_mapping.values():
        for val_mappings in value_dict.values():
            iterable = val_mappings if isinstance(val_mappings, list) else [val_mappings]
            for vm in iterable:
                if isinstance(vm, dict) and vm.get("Ontology Abbr"):
                    used.add(vm["Ontology Abbr"])

    versions_path = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_versions.json")
    recorded = {}
    if os.path.exists(versions_path):
        try:
            with open(versions_path, "r", encoding="utf-8") as f:
                recorded = json.load(f)
        except (ValueError, OSError):
            recorded = {}

    result = {}
    for abbr in sorted(used):
        info = recorded.get(abbr) or {}
        result[abbr] = {
            "version": info.get("version", "unknown"),
            "released": info.get("released", "unknown"),
            "submissionId": info.get("submissionId"),
        }
    return result


# 재가져오기용 구조화 페이로드 생성 / Build the machine-readable round-trip payload
def _build_roundtrip_payload():
    column_mappings = []
    for m in st.session_state.mapped_terms:
        column_mappings.append({
            "column": m.get("Original Label", ""),
            "term_uri": m.get("Ontology Term URI", ""),
            "label": m.get("Preferred Label", ""),
            "ontology_abbr": m.get("Ontology Abbr", ""),
            "definition": m.get("Definition", ""),
            "data_type": get_column_data_type(m.get("Original Label", "")),
        })

    value_mappings = []
    for column_name, value_dict in st.session_state.value_ontology_mapping.items():
        for value, val_mappings in value_dict.items():
            iterable = val_mappings if isinstance(val_mappings, list) else [val_mappings]
            for vm in iterable:
                if isinstance(vm, dict) and vm.get("Ontology Term URI"):
                    value_mappings.append({
                        "column": column_name,
                        "value": value,
                        "term_uri": vm.get("Ontology Term URI", ""),
                        "label": vm.get("Preferred Label", ""),
                        "ontology_abbr": vm.get("Ontology Abbr", ""),
                        "definition": vm.get("Definition", ""),
                        "data_type": get_column_data_type(column_name),
                    })

    return {"column_mappings": column_mappings, "value_mappings": value_mappings}


# Generate an extended schema that includes value mappings (JSON only - not for validation)
def generate_extended_schema():
    """Extended schema including value mappings (for internal use/documentation)."""
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
    
    # Column mapping info
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
    
    # Value mapping info
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


# LinkML schema download function
def download_linkml_schema():
    schema = generate_linkml_schema()
    if schema:
        # Convert to YAML
        yaml_str = yaml.dump(schema, sort_keys=False, default_flow_style=False, allow_unicode=True)
        
        # Add the download button
        st.download_button(
            "Download LinkML Schema (YAML)",
            data=yaml_str,
            file_name="ontology_mapping_schema.yaml",
            mime="text/yaml"
        )
        
        # Also provide it in JSON format
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
            "schema": "http://schema.org/",
        }

    def add_prefix_from_uri(uri, prefix_map):
        uri = str(uri).strip()

        # OBO pattern (http): http://purl.obolibrary.org/obo/HP_0000008
        if uri.startswith("http://purl.obolibrary.org/obo/"):
            tail = uri.replace("http://purl.obolibrary.org/obo/", "", 1)
            if "_" in tail:
                prefix = tail.split("_", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://purl.obolibrary.org/obo/{prefix}_"

        # OBO pattern (https): https://purl.obolibrary.org/obo/HP_0000008
        elif uri.startswith("https://purl.obolibrary.org/obo/"):
            tail = uri.replace("https://purl.obolibrary.org/obo/", "", 1)
            if "_" in tail:
                prefix = tail.split("_", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"https://purl.obolibrary.org/obo/{prefix}_"

        # BioPortal pattern: http://purl.bioontology.org/ontology/SNOMEDCT/410607006
        elif uri.startswith("http://purl.bioontology.org/ontology/"):
            tail = uri.replace("http://purl.bioontology.org/ontology/", "", 1)
            if "/" in tail:
                prefix = tail.split("/", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://purl.bioontology.org/ontology/{prefix}/"

        # BioPortal data pattern: https://data.bioontology.org/ontologies/...
        elif uri.startswith("https://data.bioontology.org/ontologies/"):
            tail = uri.replace("https://data.bioontology.org/ontologies/", "", 1)
            if "/" in tail:
                prefix = tail.split("/", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://purl.bioontology.org/ontology/{prefix}/"

        # NCIT pattern: http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#C93501
        elif uri.startswith("http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#"):
            if "ncit" not in prefix_map:
                prefix_map["ncit"] = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#"

        # EBI/EFO pattern: http://www.ebi.ac.uk/efo/EFO_0020103
        elif uri.startswith("http://www.ebi.ac.uk/efo/"):
            tail = uri.replace("http://www.ebi.ac.uk/efo/", "", 1)
            if "_" in tail:
                prefix = tail.split("_", 1)[0]
                if prefix and prefix not in prefix_map:
                    prefix_map[prefix] = f"http://www.ebi.ac.uk/efo/{prefix}_"

        # Identifiers.org pattern: http://identifiers.org/xxx/12345
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

        # Basic data type of each column, recorded as a schema.org ontology term.
        # rdfs:range states "values of this column are of this type", which is the
        # honest relationship: the column is modelled as a slot in the LinkML
        # export, and its range is the data type. Only standard SSSOM slots are
        # used, so no non-standard columns are introduced.
        seen_columns = []
        for mapping in st.session_state.mapped_terms:
            col_name = mapping["Original Label"]
            if col_name not in seen_columns:
                seen_columns.append(col_name)
        for column_name in st.session_state.value_ontology_mapping:
            if column_name not in seen_columns:
                seen_columns.append(column_name)

        for col_name in seen_columns:
            dt_label, dt_uri = data_type_term(get_column_data_type(col_name))
            rows.append({
                "subject_id": f"maptology:column__{safe_text(col_name)}",
                "subject_label": col_name,
                "predicate_id": "rdfs:range",
                "object_id": uri_to_curie(dt_uri, converter),
                "object_label": dt_label,
                "mapping_justification": "semapv:ManualMappingCuration",
                "comment": "basic data type (schema.org)",
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