"""
Validate that Maptology's LinkML export is a well-formed LinkML schema.

Why this exists
---------------
Maptology exports its mappings as a LinkML *schema* (it defines a DataMapping
class whose attributes are the mapped columns). Every so often we need to confirm
that this export is still valid LinkML - especially after changing schema.py.
This runs that check without needing the Streamlit app: it builds a sample export
straight from schema.generate_linkml_schema(), covering BOTH column mappings and
value mappings, then validates it two ways:

  1. SchemaView load  - the LinkML metamodel loader accepts it (structural).
  2. JsonSchemaGenerator - it compiles to JSON Schema (deeper structural check).

A file that passes both is a valid LinkML schema.

It also reports HOW value mappings are represented, because that is a recurring
question: column mappings use `exact_mappings` (a first-class LinkML slot), while
value mappings are carried as `comments` plus a schema-level `maptology_mappings`
annotation. Both are legal LinkML, but the value mappings are metadata, not
semantically-modelled slots.

Usage:
    python build/validate_linkml_export.py                # validate a sample export
    python build/validate_linkml_export.py path/to.yaml   # validate an existing file
"""

import os
import sys
import tempfile

import yaml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src", "Maptology"))


# ------------------------------------------------------------------
# A synthetic session so schema.py can run outside Streamlit.
# ------------------------------------------------------------------
class _FakeState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


def _sample_export_yaml():
    """Build a LinkML export from the CURRENT schema.py with column + value
    mappings (including a multi-term value, the case most likely to break)."""
    import streamlit as st
    st.session_state = _FakeState()

    ncit = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#"
    st.session_state.uploaded_df = None
    st.session_state.column_data_types = {"sex": "String", "age": "Integer"}
    st.session_state.mapped_terms = [
        {"Original Label": "sex", "Preferred Label": "Sex",
         "Ontology Name": "NCIT (NCIT)", "Ontology Abbr": "NCIT",
         "Ontology URI": "", "Ontology Term URI": ncit + "C28421",
         "Data Type": "String", "Definition": "sex."},
        {"Original Label": "age", "Preferred Label": "Age",
         "Ontology Name": "NCIT (NCIT)", "Ontology Abbr": "NCIT",
         "Ontology URI": "", "Ontology Term URI": ncit + "C25150",
         "Data Type": "Integer", "Definition": "age."},
    ]
    st.session_state.value_ontology_mapping = {
        "sex": {
            "Female": [
                {"Preferred Label": "Female", "Ontology Name": "NCIT (NCIT)",
                 "Ontology Abbr": "NCIT", "Ontology URI": "",
                 "Ontology Term URI": ncit + "C16576", "Definition": "", "Data Type": "String"},
                {"Preferred Label": "Female Gender", "Ontology Name": "NCIT (NCIT)",
                 "Ontology Abbr": "NCIT", "Ontology URI": "",
                 "Ontology Term URI": ncit + "C46110", "Definition": "", "Data Type": "String"},
            ],
            "Male": [
                {"Preferred Label": "Male", "Ontology Name": "NCIT (NCIT)",
                 "Ontology Abbr": "NCIT", "Ontology URI": "",
                 "Ontology Term URI": ncit + "C20197", "Definition": "", "Data Type": "String"},
            ],
        }
    }

    import schema
    doc = schema.generate_linkml_schema()
    if doc is None:
        raise SystemExit("generate_linkml_schema() returned None")
    return yaml.dump(doc, sort_keys=False, default_flow_style=False, allow_unicode=True), doc


def _validate_schema_file(path):
    """Return (ok, messages). Runs two independent LinkML checks."""
    msgs = []
    ok = True

    # 1) The metamodel loader accepts the schema.
    try:
        from linkml_runtime.utils.schemaview import SchemaView
        sv = SchemaView(path)
        n_classes = len(sv.all_classes())
        n_slots = len(sv.all_slots())
        msgs.append("SchemaView load: OK (" + str(n_classes) + " classes, "
                    + str(n_slots) + " slots)")
    except Exception as e:
        ok = False
        msgs.append("SchemaView load: FAILED - " + type(e).__name__ + ": " + str(e))

    # 2) It compiles to JSON Schema.
    try:
        from linkml.generators.jsonschemagen import JsonSchemaGenerator
        out = JsonSchemaGenerator(path).serialize()
        msgs.append("JSON Schema compile: OK (" + str(len(out)) + " chars)")
    except Exception as e:
        ok = False
        msgs.append("JSON Schema compile: FAILED - " + type(e).__name__ + ": " + str(e))

    return ok, msgs


def _describe_value_mappings(doc):
    print("How the export represents mappings:")
    classes = (doc.get("classes") or {})
    for cls_name, cls in classes.items():
        for attr_name, attr in (cls.get("attributes") or {}).items():
            has_exact = bool(attr.get("exact_mappings"))
            n_comments = len(attr.get("comments") or [])
            print("  column '" + attr_name + "': exact_mappings="
                  + ("yes" if has_exact else "no")
                  + ", value-mapping comments=" + str(n_comments))
    ann = list((doc.get("annotations") or {}).keys())
    print("  schema-level annotations: " + (", ".join(ann) if ann else "(none)"))
    print("  -> column mappings use exact_mappings (first-class LinkML);")
    print("     value mappings are comments + the maptology_mappings annotation")
    print("     (valid LinkML, but metadata rather than modelled slots).")


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
        doc = None
        print("Validating existing file: " + path)
    else:
        text, doc = _sample_export_yaml()
        fd, path = tempfile.mkstemp(suffix=".yaml", prefix="maptology_linkml_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        print("Validating a fresh sample export from schema.py")

    ok, msgs = _validate_schema_file(path)
    print("")
    for m in msgs:
        print("  " + m)
    print("")
    if doc is not None:
        _describe_value_mappings(doc)
        print("")

    if ok:
        print("RESULT: valid LinkML schema")
        sys.exit(0)
    else:
        print("RESULT: NOT valid - see failures above")
        sys.exit(1)


if __name__ == "__main__":
    main()
