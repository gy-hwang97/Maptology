"""
Import previously-exported mappings (LinkML YAML or SSSOM TSV) back into the app.

Design notes
------------
The mapping files Maptology exports were originally one-way outputs. To make
them round-trip cleanly we do two things:

  1. LinkML export now embeds a structured, machine-readable block
     (schema-level annotation "maptology_mappings", a JSON payload). Re-import
     reads that block directly - no fragile parsing of free-text descriptions
     or comments. If the block is missing (e.g. a hand-written LinkML file),
     we fall back to the standard fields (title + exact_mappings), best-effort.

  2. SSSOM/TSV already keeps the original column name (subject_label), the
     value (subject_label "Column: value"), the term IRI (object_id) and the
     preferred label (object_label). We reconstruct from those columns.

After parsing, mappings are filtered against the CURRENT data file: a column
mapping is kept only if its column exists in the data; a value mapping is kept
only if its column exists AND the value is present in that column. This is the
"if there is age in the mapping, there has to be age in the data file" rule.
"""

import hashlib
import io
import json

import pandas as pd
import streamlit as st
import yaml

from tfidf_search import get_ontology_list_from_tsv


# SSSOM rows that record a column's basic data type (a schema.org term) use this
# predicate. They are NOT ontology terms the user selected, so re-import must skip
# them rather than treat them as mappings. Kept lowercase for comparison.
_DATA_TYPE_PREDICATES = {
    "rdfs:range",
    "http://www.w3.org/2000/01/rdf-schema#range",
}


# ============================================================
# Ontology catalog helpers (abbreviation -> full name)
# ============================================================

_catalog = None


def _abbr_to_name(abbr):
    global _catalog
    if _catalog is None:
        _catalog = {}
        try:
            for o in get_ontology_list_from_tsv():
                _catalog[o["acronym"]] = o["name"]
        except Exception:
            _catalog = {}
    return _catalog.get(abbr, abbr)


def _display_ontology_name(abbr):
    abbr = abbr or ""
    full = _abbr_to_name(abbr)
    if full and abbr and full != abbr:
        return full + " (" + abbr + ")"
    return abbr or full or ""


def _ontology_uri(abbr):
    return "https://bioportal.bioontology.org/ontologies/" + str(abbr or "")


def _abbr_from_uri(uri):
    """Best-effort ontology abbreviation from a term IRI (used only when the
    file does not already provide one)."""
    uri = str(uri or "")
    if "ncicb.nci.nih.gov" in uri:
        return "NCIT"
    for marker in ("/obo/", "/efo/"):
        if marker in uri:
            tail = uri.split(marker)[-1]
            if "_" in tail:
                return tail.split("_")[0]
    return ""


# ============================================================
# Parsing - LinkML
# ============================================================

def parse_linkml(text):
    """Return (column_records, value_records). Each record is a dict with keys:
    column, value (None for column-level), term_uri, label, ontology_abbr,
    definition, data_type."""
    data = yaml.safe_load(text) or {}
    col_recs = []
    val_recs = []

    # Preferred path: the structured maptology block.
    annotations = data.get("annotations") or {}
    node = annotations.get("maptology_mappings")
    blob = None
    if isinstance(node, dict):
        blob = node.get("value")
    elif isinstance(node, str):
        blob = node

    if blob:
        try:
            payload = json.loads(blob)
            for r in payload.get("column_mappings", []) or []:
                col_recs.append({
                    "column": r.get("column", ""),
                    "value": None,
                    "term_uri": r.get("term_uri", ""),
                    "label": r.get("label", ""),
                    "ontology_abbr": r.get("ontology_abbr", ""),
                    "definition": r.get("definition", ""),
                    "data_type": r.get("data_type", ""),
                })
            for r in payload.get("value_mappings", []) or []:
                val_recs.append({
                    "column": r.get("column", ""),
                    "value": r.get("value", ""),
                    "term_uri": r.get("term_uri", ""),
                    "label": r.get("label", ""),
                    "ontology_abbr": r.get("ontology_abbr", ""),
                    "definition": r.get("definition", ""),
                    "data_type": r.get("data_type", ""),
                })
            return col_recs, val_recs
        except (ValueError, TypeError):
            pass  # fall through to best-effort

    # Fallback: standard LinkML fields only (no value mappings recoverable).
    classes = data.get("classes") or {}
    for cls in classes.values():
        attrs = (cls or {}).get("attributes") or {}
        for key, attr in attrs.items():
            attr = attr or {}
            column = attr.get("title") or str(key).replace("_", " ")
            data_type = ""
            ann = attr.get("annotations") or {}
            dt = ann.get("data_type")
            if isinstance(dt, dict):
                data_type = dt.get("value", "")
            for uri in attr.get("exact_mappings", []) or []:
                col_recs.append({
                    "column": column,
                    "value": None,
                    "term_uri": uri,
                    "label": "",
                    "ontology_abbr": "",
                    "definition": "",
                    "data_type": data_type,
                })
    return col_recs, val_recs


# ============================================================
# Parsing - SSSOM
# ============================================================

def _expand_curie(curie, curie_map):
    curie = str(curie or "").strip()
    if ":" in curie:
        prefix, local = curie.split(":", 1)
        if prefix in curie_map:
            return curie_map[prefix] + local
    return curie


def parse_sssom(text):
    """Parse an SSSOM/TSV file (commented YAML metadata header + TSV table)."""
    lines = text.splitlines()
    meta_lines = []
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        meta_lines.append(lines[i][1:])
        i += 1
    tsv_part = "\n".join(lines[i:])

    curie_map = {}
    if meta_lines:
        try:
            meta = yaml.safe_load("\n".join(meta_lines)) or {}
            curie_map = meta.get("curie_map", {}) or {}
        except yaml.YAMLError:
            curie_map = {}

    if not tsv_part.strip():
        return [], []

    df = pd.read_csv(io.StringIO(tsv_part), sep="\t", dtype=str).fillna("")

    col_recs = []
    val_recs = []
    for _, row in df.iterrows():
        subject_id = str(row.get("subject_id", ""))
        subject_label = str(row.get("subject_label", ""))
        object_id = str(row.get("object_id", ""))
        object_label = str(row.get("object_label", ""))
        predicate_id = str(row.get("predicate_id", "")).strip().lower()

        # rdfs:range rows carry the column's basic data type (a schema.org term),
        # not an ontology term the user selected. Skip them, otherwise re-import
        # would turn the data type into a bogus mapping (e.g. sex -> schema:Text).
        if predicate_id in _DATA_TYPE_PREDICATES:
            continue

        term_uri = _expand_curie(object_id, curie_map)
        abbr = object_id.split(":")[0] if ":" in object_id else ""

        is_value = subject_id.startswith("maptology:value__") or (
            "value__" in subject_id
        )

        if is_value:
            # subject_label was exported as "Column: value"
            if ": " in subject_label:
                column, value = subject_label.split(": ", 1)
            else:
                column, value = subject_label, ""
            val_recs.append({
                "column": column,
                "value": value,
                "term_uri": term_uri,
                "label": object_label,
                "ontology_abbr": abbr,
                "definition": "",
                "data_type": "",
            })
        else:
            col_recs.append({
                "column": subject_label,
                "value": None,
                "term_uri": term_uri,
                "label": object_label,
                "ontology_abbr": abbr,
                "definition": "",
                "data_type": "",
            })
    return col_recs, val_recs


# ============================================================
# Filtering against the current data file
# ============================================================

def _norm(s):
    return str(s).strip().lower()


def _match_column(name, actual_cols, norm_map):
    """Match an imported column name to an actual data column.
    Exact match first, then case-insensitive + whitespace-trimmed."""
    if name in actual_cols:
        return name
    return norm_map.get(_norm(name))


def filter_to_data(col_recs, val_recs, df):
    actual_cols = list(df.columns)
    norm_map = {}
    for c in actual_cols:
        norm_map[_norm(c)] = c

    kept_cols = []
    dropped_cols = []
    for r in col_recs:
        actual = _match_column(r["column"], actual_cols, norm_map)
        if actual is not None and r.get("term_uri"):
            r2 = dict(r)
            r2["column"] = actual
            kept_cols.append(r2)
        else:
            dropped_cols.append(r)

    kept_vals = []
    dropped_vals = []
    uniq_cache = {}
    for r in val_recs:
        actual = _match_column(r["column"], actual_cols, norm_map)
        if actual is None or not r.get("term_uri"):
            dropped_vals.append(r)
            continue
        if actual not in uniq_cache:
            uniq_cache[actual] = set(
                str(v).strip() for v in df[actual].dropna().unique()
            )
        if str(r["value"]).strip() in uniq_cache[actual]:
            r2 = dict(r)
            r2["column"] = actual
            kept_vals.append(r2)
        else:
            dropped_vals.append(r)

    return kept_cols, kept_vals, dropped_cols, dropped_vals


# ============================================================
# Apply to session state
# ============================================================

def _latest_label_def(abbr, term_uri, fallback_label, fallback_def):
    """Return the CURRENT label/definition for a term from the local OWL cache,
    matched by URI (the stable identifier). Falls back to the values stored in
    the imported file if the term is not in the cache.

    This is intentional: an exported mapping may be old, and the ontology's
    label/definition may have changed since. We trust only the URI from the
    file and re-read the up-to-date label/definition locally."""
    try:
        from tfidf_search import get_term_by_iri
        term = get_term_by_iri(abbr, term_uri) if abbr else None
    except Exception:
        term = None
    if term:
        label = term.get("label") or fallback_label
        definition = term.get("definition") or fallback_def
        return label, definition
    return fallback_label, fallback_def


def apply_mappings(kept_cols, kept_vals):
    from utils import get_column_data_type

    added = False
    existing = set(
        (m["Original Label"], m["Ontology Term URI"])
        for m in st.session_state.mapped_terms
    )
    for r in kept_cols:
        key = (r["column"], r["term_uri"])
        if key in existing:
            continue
        abbr = r.get("ontology_abbr") or _abbr_from_uri(r["term_uri"])
        label, definition = _latest_label_def(abbr, r["term_uri"], r.get("label", ""), r.get("definition", ""))
        st.session_state.mapped_terms.append({
            "Original Label": r["column"],
            "Preferred Label": label,
            "Ontology Name": _display_ontology_name(abbr),
            "Ontology Abbr": abbr,
            "Ontology URI": _ontology_uri(abbr),
            "Ontology Term URI": r["term_uri"],
            "Data Type": get_column_data_type(r["column"]),
            "Definition": definition,
        })
        existing.add(key)
        added = True

    vom = st.session_state.value_ontology_mapping
    for r in kept_vals:
        col = r["column"]
        val = str(r["value"])
        if col not in vom:
            vom[col] = {}
        if val not in vom[col]:
            vom[col][val] = []
        if any(m.get("Ontology Term URI") == r["term_uri"] for m in vom[col][val]):
            continue
        abbr = r.get("ontology_abbr") or _abbr_from_uri(r["term_uri"])
        label, definition = _latest_label_def(abbr, r["term_uri"], r.get("label", ""), r.get("definition", ""))
        vom[col][val].append({
            "Preferred Label": label,
            "Ontology Name": _display_ontology_name(abbr),
            "Ontology Abbr": abbr,
            "Ontology URI": _ontology_uri(abbr),
            "Ontology Term URI": r["term_uri"],
            "Definition": definition,
            "Data Type": get_column_data_type(col),
        })
        added = True

    # Bump mapping_version so checkbox widgets pick up the imported mappings
    # (otherwise Streamlit keeps stale unchecked widget state).
    if added:
        st.session_state.mapping_version = st.session_state.get("mapping_version", 0) + 1


# ============================================================
# Auto-select the ontologies used by an imported file
# ============================================================

def _auto_select_ontologies(kept_cols, kept_vals):
    """Auto-select the ontologies used by the imported mappings so the user does
    not have to re-check them in the ontology step.

      - case-insensitive match against the loaded catalog (so "ncit" -> "NCIT")
      - only ontologies that exist in the local catalog are selected
      - existing selections are kept (union), capped at 10
      - returns (unknown, overflow): abbreviations that could NOT be selected
        because they are not in the catalog / would exceed the 10 cap.

    Bumps ontology_widget_version so the ontology checkboxes re-render checked
    (otherwise Streamlit keeps their stale unchecked widget state)."""
    available = st.session_state.get("available_ontologies", []) or []
    canon = {}
    for o in available:
        canon[str(o.get("acronym", "")).lower()] = o.get("acronym", "")

    wanted = []
    for r in list(kept_cols) + list(kept_vals):
        abbr = r.get("ontology_abbr") or _abbr_from_uri(r.get("term_uri", ""))
        if abbr and abbr not in wanted:
            wanted.append(abbr)

    selected = st.session_state.selected_ontologies
    unknown = []
    overflow = []
    changed = False
    for abbr in wanted:
        canonical = canon.get(str(abbr).lower())
        if not canonical:
            unknown.append(abbr)
            continue
        if canonical in selected:
            continue
        if len(selected) >= 10:
            overflow.append(canonical)
            continue
        selected.append(canonical)
        changed = True

    if changed:
        st.session_state.ontologies_changed = True
        st.session_state.ontology_widget_version = (
            st.session_state.get("ontology_widget_version", 0) + 1
        )
    return unknown, overflow


# ============================================================
# UI
# ============================================================

def render_import_section():
    """Optional importer - its own step. Only shown once a data file is loaded."""
    if st.session_state.uploaded_df is None:
        return

    st.write("### Step 3: Import Existing Mappings (Optional)")
    st.caption(
        "If you previously exported a mapping file from Maptology (LinkML .yaml "
        "or SSSOM .tsv), you can re-load it here. Only mappings whose column - "
        "and, for value mappings, whose value - exist in the current data file "
        "are kept. You can skip this step and map terms from scratch below."
    )

    seq = st.session_state.get("mapping_uploader_seq", 0)
    uploaded = st.file_uploader(
        "Mapping file (LinkML .yaml / SSSOM .tsv)",
        type=["yaml", "yml", "tsv", "json"],
        key="mapping_import_uploader_" + str(seq),
    )

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        # Compare the file CONTENT (hash), not the name: a different file that
        # happens to have the same name must still be re-imported.
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        if st.session_state.get("imported_mapping_hash") != file_hash:
            text = file_bytes.decode("utf-8", errors="replace")
            name = uploaded.name.lower()
            try:
                if name.endswith(".tsv"):
                    col_recs, val_recs = parse_sssom(text)
                    fmt = "SSSOM"
                else:
                    col_recs, val_recs = parse_linkml(text)
                    fmt = "LinkML"
            except Exception as e:
                st.error("Could not parse mapping file: " + str(e))
                return

            df = st.session_state.uploaded_df
            kept_cols, kept_vals, dropped_cols, dropped_vals = filter_to_data(
                col_recs, val_recs, df
            )
            apply_mappings(kept_cols, kept_vals)
            unknown_onts, overflow_onts = _auto_select_ontologies(kept_cols, kept_vals)

            st.session_state.imported_mapping_hash = file_hash
            st.session_state.imported_mapping_name = uploaded.name
            st.session_state.import_report = {
                "fmt": fmt,
                "kept_cols": len(kept_cols),
                "kept_vals": len(kept_vals),
                "dropped_cols": [r["column"] for r in dropped_cols],
                "dropped_vals": [str(r["column"]) + " = " + str(r["value"]) for r in dropped_vals],
                "unknown_onts": unknown_onts,
                "overflow_onts": overflow_onts,
            }

    report = st.session_state.get("import_report")
    if report:
        st.success(
            "Imported from " + report["fmt"] + ": "
            + str(report["kept_cols"]) + " column mapping(s), "
            + str(report["kept_vals"]) + " value mapping(s) kept."
        )
        dc = report.get("dropped_cols") or []
        dv = report.get("dropped_vals") or []
        if dc or dv:
            details = []
            if dc:
                details.append(str(len(dc)) + " column mapping(s) [" + ", ".join(dc[:8]) + ("..." if len(dc) > 8 else "") + "]")
            if dv:
                details.append(str(len(dv)) + " value mapping(s)")
            st.warning(
                "The imported file contains mappings to columns/values that are not "
                "present in this data file, so they were ignored: "
                + "; ".join(details)
                + ". The mappings that matched your data were loaded."
            )

        unknown = report.get("unknown_onts") or []
        overflow = report.get("overflow_onts") or []
        if unknown or overflow:
            parts = []
            if unknown:
                parts.append("not in the local ontology catalog: " + ", ".join(unknown))
            if overflow:
                parts.append("over the 10-ontology limit: " + ", ".join(overflow))
            st.warning(
                "Some ontologies used by the file were not auto-selected ("
                + "; ".join(parts)
                + "). Select them manually in Step 4 if you need them."
            )
