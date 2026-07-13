import streamlit as st
from ontology import get_ontology_details
from utils import get_column_data_type

# =============================================================================
# Single source of truth
# -----------------------------------------------------------------------------
# Column mappings live in st.session_state.mapped_terms.
# Value mappings live in st.session_state.value_ontology_mapping[column][value].
#
# A checkbox is "checked" iff the term's URI is present in that mapping - there
# is no separate selection list to keep in sync. mapping_version is bumped on
# every change so checkbox widgets re-render from the mapping (Streamlit would
# otherwise keep stale widget state after an import or a trash-icon delete).
# =============================================================================


def _bump_version():
    st.session_state.mapping_version = st.session_state.get("mapping_version", 0) + 1


def _column_entry_from_row(column, row):
    """Build a mapped_terms entry from a search-result row (auto or manual)."""
    abbr = row["Ontology Name"]  # the search dataframe stores the acronym here
    info = get_ontology_details(abbr)
    full_name = info["full_name"]
    return {
        "Original Label": column,
        "Preferred Label": row["Preferred Label"],
        "Ontology Name": f"{full_name} ({abbr})",
        "Ontology Abbr": abbr,
        "Ontology URI": row["Ontology URI"],
        "Ontology Term URI": row["Ontology Term URI"],
        "Data Type": get_column_data_type(column),
        "Definition": row.get("Definition", ""),
    }


def _value_entry_from_row(column, row):
    abbr = row["Ontology Name"]
    info = get_ontology_details(abbr)
    full_name = info["full_name"]
    return {
        "Preferred Label": row["Preferred Label"],
        "Ontology Name": f"{full_name} ({abbr})",
        "Ontology Abbr": abbr,
        "Ontology URI": row["Ontology URI"],
        "Ontology Term URI": row["Ontology Term URI"],
        "Definition": row.get("Definition", ""),
        "Data Type": get_column_data_type(column),
    }


# -----------------------------------------------------------------------------
# Column-level term: checked-state + toggle
# -----------------------------------------------------------------------------

def is_column_term_mapped(column, term_uri):
    return any(
        m["Original Label"] == column and m["Ontology Term URI"] == term_uri
        for m in st.session_state.mapped_terms
    )


def add_column_term(column, row):
    if not is_column_term_mapped(column, row["Ontology Term URI"]):
        st.session_state.mapped_terms.append(_column_entry_from_row(column, row))
        _bump_version()


def remove_column_term(column, term_uri):
    st.session_state.mapped_terms = [
        m for m in st.session_state.mapped_terms
        if not (m["Original Label"] == column and m["Ontology Term URI"] == term_uri)
    ]
    _bump_version()


# -----------------------------------------------------------------------------
# Value-level term: checked-state + toggle
# -----------------------------------------------------------------------------

def _value_list(column, value):
    lst = st.session_state.value_ontology_mapping.get(column, {}).get(value, [])
    if not isinstance(lst, list):
        lst = [lst]
    return lst


def is_value_term_mapped(column, value, term_uri):
    return any(m.get("Ontology Term URI") == term_uri for m in _value_list(column, value))


def add_value_term(column, value, row):
    if is_value_term_mapped(column, value, row["Ontology Term URI"]):
        return
    vom = st.session_state.value_ontology_mapping
    if column not in vom:
        vom[column] = {}
    existing = vom[column].get(value, [])
    if not isinstance(existing, list):
        existing = [existing]
    existing.append(_value_entry_from_row(column, row))
    vom[column][value] = existing
    _bump_version()


def remove_value_term(column, value, term_uri):
    vom = st.session_state.value_ontology_mapping
    if column not in vom or value not in vom[column]:
        return
    kept = [m for m in _value_list(column, value) if m.get("Ontology Term URI") != term_uri]
    if kept:
        vom[column][value] = kept
    else:
        del vom[column][value]
        if not vom[column]:
            del vom[column]
    _bump_version()


# =============================================================================
# Whole-mapping / individual deletes (trash icons in the results tables)
# =============================================================================

def remove_mapping(column_name):
    """Remove ALL mappings for a column (column-level and value-level)."""
    if not column_name:
        return
    st.session_state.mapped_terms = [
        m for m in st.session_state.mapped_terms if m["Original Label"] != column_name
    ]
    if column_name in st.session_state.value_ontology_mapping:
        del st.session_state.value_ontology_mapping[column_name]
    _bump_version()
    st.rerun()


def remove_value_mapping(column_name, value):
    """Remove ALL term mappings for one value."""
    vom = st.session_state.value_ontology_mapping
    if column_name in vom and value in vom[column_name]:
        del vom[column_name][value]
        if not vom[column_name]:
            del vom[column_name]
        _bump_version()
        st.rerun()


def remove_term_mapping(column_name, term_uri):
    """Remove one column-level term mapping (trash icon). The matching
    checkbox unchecks automatically because it reads from the mapping."""
    if column_name and term_uri:
        remove_column_term(column_name, term_uri)
        st.rerun()


def remove_individual_value_mapping(column_name, value, term_uri):
    """Remove one value-level term mapping (trash icon)."""
    if column_name and value and term_uri:
        remove_value_term(column_name, value, term_uri)
        st.rerun()


# =============================================================================
# Dropdown callbacks
# =============================================================================

def on_column_select():
    """Column dropdown change: switch column and run its auto-search.
    Mappings are global, so there is no per-column selection to save/restore."""
    selected_column = st.session_state.column_select
    previous_column = st.session_state.selected_column
    if selected_column == previous_column:
        return

    st.session_state.selected_column = selected_column
    st.session_state.current_search_term = selected_column

    # Reset live search caches (NOT the mappings)
    st.session_state.selected_unique_value = None
    st.session_state.value_ontology_results = None
    st.session_state.auto_searched = False
    st.session_state.manual_column_search_results = None
    st.session_state.manual_value_search_results = None

    if selected_column and st.session_state.selected_ontologies:
        from ontology import search_ontology, search_ontology_for_value
        search_ontology(selected_column)

        # Auto-search the first unique value for string-like columns
        if st.session_state.uploaded_df is not None and not st.session_state.auto_searched:
            dtype_name = str(st.session_state.uploaded_df[selected_column].dtype)
            if dtype_name == 'object' or dtype_name.startswith('string') or dtype_name == 'category':
                unique_values = st.session_state.uploaded_df[selected_column].dropna().unique()
                unique_values.sort()
                if len(unique_values) > 0:
                    default_value = str(unique_values[0])
                    st.session_state.selected_unique_value = default_value
                    search_ontology_for_value(default_value)
                    st.session_state.auto_searched = True


def on_value_select():
    """Value dropdown change: switch value and run its auto-search."""
    selected_value = st.session_state.value_select
    previous_value = st.session_state.selected_unique_value
    st.session_state.selected_unique_value = selected_value
    st.session_state.manual_value_search_results = None

    if selected_value and selected_value != previous_value:
        from ontology import search_ontology_for_value
        search_ontology_for_value(selected_value)
