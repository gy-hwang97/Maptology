import os
import sys

import pandas as pd
import streamlit as st
import yaml

st.fragment = lambda *args, **kwargs: (lambda fn: fn)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "Maptology"))

import mapping_display
import mapping_import
import schema
import utils


class State(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value


def _state():
    df = pd.DataFrame({
        "age": [40, 41],
        "sex": ["female", "male"],
        "city": ["Provo", "Orem"],
    })
    state = State({
        "uploaded_df": df,
        "mapped_terms": [{
            "Original Label": "sex",
            "Preferred Label": "Female",
            "Ontology Name": "Gender (GSSO)",
            "Ontology Abbr": "GSSO",
            "Ontology URI": "http://example.org/gsso",
            "Ontology Term URI": "http://example.org/gsso/female",
            "Definition": "",
        }],
        "value_ontology_mapping": {},
        "column_data_types": {
            "age": "Integer",
            "sex": "String",
            "city": "Date",
        },
    })
    for module in (schema, utils, mapping_display, mapping_import):
        module.st.session_state = state
    return state


def test_linkml_and_json_record_every_columns_schema_org_type():
    _state()
    linkml = schema.generate_linkml_schema()
    attributes = linkml["classes"]["DataMapping"]["attributes"]
    assert set(attributes) == {"age", "sex", "city"}
    assert "exact_mappings" not in attributes["age"]
    assert attributes["age"]["annotations"]["data_type_term"]["value"] == "http://schema.org/Integer"
    assert attributes["city"]["annotations"]["data_type_term"]["value"] == "http://schema.org/Date"
    assert attributes["sex"]["exact_mappings"] == ["http://example.org/gsso/female"]

    payload = yaml.safe_load(yaml.dump(linkml))
    saved = payload["annotations"]["maptology_mappings"]["value"]
    import json
    types = {row["column"]: row["data_type"] for row in json.loads(saved)["column_data_types"]}
    assert types == {"age": "Integer", "sex": "String", "city": "Date"}


def test_column_mapping_csv_includes_unmapped_columns():
    _state()
    text = mapping_display._column_mappings_csv().decode("utf-8")
    table = pd.read_csv(pd.io.common.StringIO(text), dtype=str).fillna("")
    by_name = {row["Column Name"]: row for _, row in table.iterrows()}
    assert set(by_name) == {"age", "sex", "city"}
    assert by_name["age"]["Ontology Term URI"] == ""
    assert by_name["age"]["Data Type Term URI"] == "http://schema.org/Integer"
    assert by_name["city"]["Data Type Term URI"] == "http://schema.org/Date"
    assert by_name["sex"]["Ontology Term URI"] == "http://example.org/gsso/female"
    assert by_name["sex"]["Data Type Term URI"] == "http://schema.org/Text"


def test_sssom_records_a_range_for_every_column():
    _state()
    text = schema.generate_sssom_tsv()
    assert text
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    table = pd.read_csv(pd.io.common.StringIO(body), sep="\t", dtype=str).fillna("")
    ranges = table[table["predicate_id"].str.lower() == "rdfs:range"]
    found = {
        row["subject_label"]: row["object_id"]
        for _, row in ranges.iterrows()
    }
    assert found["age"].endswith("Integer")
    assert found["sex"].endswith("Text")
    assert found["city"].endswith("Date")


def test_a_manual_data_type_overrides_the_inferred_type():
    state = _state()
    # The table says age is a whole number, and a stale save still says Integer.
    # The dropdown is what the export must follow.
    state[utils.column_dtype_widget_key("age")] = "Date"
    state["column_data_types"]["age"] = "Integer"
    linkml = schema.generate_linkml_schema()
    age = linkml["classes"]["DataMapping"]["attributes"]["age"]
    assert age["annotations"]["data_type"]["value"] == "Date"
    assert age["annotations"]["data_type_term"]["value"] == "http://schema.org/Date"
    assert age["range"] == "date"


def test_reimport_restores_a_type_for_a_column_with_no_term():
    state = _state()
    linkml = schema.generate_linkml_schema()
    text = yaml.dump(linkml, sort_keys=False)
    state["column_data_types"] = {}
    col_recs, val_recs = mapping_import.parse_linkml(text)
    kept_cols, kept_vals, dropped_cols, _dropped_vals, type_recs = mapping_import.filter_to_data(
        col_recs, val_recs, state["uploaded_df"]
    )
    applied, rejected = mapping_import._restore_data_types(kept_cols + kept_vals + type_recs)
    assert "age" in applied
    assert state["column_data_types"]["age"] == "Integer"
    assert any(item.startswith("city") for item in rejected)
    assert dropped_cols == []
    assert [row["column"] for row in kept_cols] == ["sex"]
