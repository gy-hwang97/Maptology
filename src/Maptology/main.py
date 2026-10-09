import csv
import io

import streamlit as st
import pandas as pd

from utils import initialize_session, add_css
from components import render_header, FAVICON_PATH
from ontology_setup import ensure_ontologies
from ontology import render_ontology_selection, get_available_ontologies, search_ontology
from column_mapping import render_column_mapping_section
from value_mapping import render_value_mapping_section
from mapping_display import render_mapped_terms, render_value_mappings, render_download_buttons
from mapping_import import render_import_section

# One page of the preview is sent to the browser. The rest of a large file
# stays on the server until the user moves to it.
PREVIEW_PAGE_ROWS = 20
PREVIEW_PAGE_COLS = 20


def _header_label(name):
    """Column name as a person would compare it. Blank cells share one label."""
    if name is None:
        return ""
    try:
        if pd.isna(name):
            return ""
    except (TypeError, ValueError):
        pass
    return str(name).strip()


def _repeated_column_names(names):
    """Names used more than once, as (label, count) in the order first seen.

    Pandas renames repeats (Age, Age.1) after reading, so this has to use the
    header from the file, not the renamed columns.
    """
    counts = {}
    order = []
    for name in names:
        label = _header_label(name)
        if label not in counts:
            counts[label] = 0
            order.append(label)
        counts[label] += 1
    return [(label, counts[label]) for label in order if counts[label] > 1]


def _read_delimited_header(uploaded_file, delimiter):
    """First row of a CSV or TSV, before pandas renames repeated columns."""
    uploaded_file.seek(0)
    try:
        text_stream = io.TextIOWrapper(uploaded_file, encoding="utf-8-sig", newline="")
        try:
            header = next(csv.reader(
                text_stream, delimiter=delimiter, skipinitialspace=True))
        finally:
            text_stream.detach()
    finally:
        uploaded_file.seek(0)
    return header


def _read_excel_header(uploaded_file):
    """First row of a spreadsheet, before pandas renames repeated columns."""
    uploaded_file.seek(0)
    try:
        raw = pd.read_excel(uploaded_file, header=None, nrows=1)
    finally:
        uploaded_file.seek(0)
    if raw.empty:
        return []
    return raw.iloc[0].tolist()


def _column_name_code(label):
    """Markdown code span so a repeated column name is monospaced, not bold."""
    if label == "":
        label = "(blank)"
    run = 0
    longest = 0
    for ch in label:
        if ch == "`":
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    fence = "`" * (longest + 1)
    # A name that starts or ends with a backtick needs a space inside the fence.
    if label[:1] == "`" or label[-1:] == "`":
        return fence + " " + label + " " + fence
    return fence + label + fence


def _show_repeated_column_message(repeated):
    """Explain which column names clash, without opening the file."""
    lines = ["Rename these columns so each name is used only once, then upload the file again."]
    for label, count in repeated:
        lines.append("- " + _column_name_code(label) + " appears " + str(count) + " times")
    st.error(
        "This file was not opened because some columns have the same name. "
        "Each column needs a name of its own.\n\n" + "\n".join(lines))


def _shift_preview_page(axis, delta):
    """Move the preview one page before the buttons are drawn again."""
    key = "preview_row_page" if axis == "row" else "preview_col_page"
    st.session_state[key] = st.session_state.get(key, 0) + delta


def _preview_bounds(n_items, page, page_size):
    """Clamp a page index and return that page's slice and page count."""
    page_count = max(1, (n_items + page_size - 1) // page_size) if n_items else 1
    page = min(max(page, 0), page_count - 1)
    start = page * page_size
    stop = min(start + page_size, n_items)
    return page, start, stop, page_count


def _render_preview_pager(axis, page, page_count, start, stop, total):
    """Previous / Next for one axis. Hidden when everything fits on one page."""
    if page_count <= 1:
        return
    noun = "rows" if axis == "row" else "columns"
    prev_col, label_col, next_col = st.columns([1, 3, 1])
    with prev_col:
        st.button("Previous " + noun, key="preview_" + axis + "_prev",
                  disabled=page == 0,
                  on_click=_shift_preview_page, args=(axis, -1))
    with next_col:
        with st.container(horizontal=True, horizontal_alignment="right"):
            st.button("Next " + noun, key="preview_" + axis + "_next",
                      disabled=page >= page_count - 1,
                      on_click=_shift_preview_page, args=(axis, 1))
    with label_col:
        st.markdown("%d–%d of %d %s" % (start + 1, stop, total, noun),
                    text_alignment="center")


def _render_data_preview(df):
    """Show one page of rows and columns. A wide or long file is not sent whole."""
    highlight = st.session_state.get("highlighted_column")
    if highlight in df.columns and st.session_state.get("preview_highlight_followed") != highlight:
        col_index = next(i for i, name in enumerate(df.columns) if name == highlight)
        st.session_state.preview_col_page = col_index // PREVIEW_PAGE_COLS
        st.session_state.preview_highlight_followed = highlight

    row_page, row_start, row_stop, row_pages = _preview_bounds(
        len(df), st.session_state.get("preview_row_page", 0), PREVIEW_PAGE_ROWS)
    col_page, col_start, col_stop, col_pages = _preview_bounds(
        len(df.columns), st.session_state.get("preview_col_page", 0), PREVIEW_PAGE_COLS)
    st.session_state.preview_row_page = row_page
    st.session_state.preview_col_page = col_page

    _render_preview_pager("col", col_page, col_pages, col_start, col_stop, len(df.columns))

    view = df.iloc[row_start:row_stop, col_start:col_stop]
    if highlight in view.columns:
        def highlight_column(x):
            df_styler = pd.DataFrame('', index=x.index, columns=x.columns)
            df_styler[highlight] = 'background-color: #90EE90;'
            return df_styler

        st.dataframe(view.style.apply(highlight_column, axis=None),
                     width='stretch', hide_index=False)
    else:
        st.dataframe(view, width='stretch', hide_index=False)

    _render_preview_pager("row", row_page, row_pages, row_start, row_stop, len(df))
    if highlight in view.columns:
        st.markdown("Column '" + highlight + "' highlighted due to recent type change")


# Streamlit basic page configuration
st.set_page_config(page_title='Maptology', page_icon=FAVICON_PATH, layout='wide')

# Download and index any ontologies that are new or updated on BioPortal, before
# the UI renders. Cached per server process, so this is startup work rather than
# something that repeats on every rerun. Progress is printed to the terminal.
ensure_ontologies()

# Add CSS styles
add_css()

# Initialize session state
initialize_session()

# A one-shot confirmation left by an Add click on the previous run. Toasts do
# not survive the st.rerun() that clears the added term from the results list,
# so the message is carried across in session state and shown here.
_added_toast = st.session_state.pop("term_added_toast", None)
if _added_toast:
    st.toast(_added_toast)

# Display logo and title
render_header()

# Tagline
# st.markdown("### Map your tabular dataset to ontology terms")
st.markdown("Maptology helps researchers semantically annotate tabular data with ontology terms. After uploading a data file (CSV, TSV, or Excel formats), a researcher selects from the hundreds of ontologies available in [BioPortal](https://bioportal.bioontology.org/). Then, for each column, they can assign ontology term(s) describing the data in that column. Similarly, for each value in a columns with categorical data, they can assign ontology term(s) describing the meaning of that value. The resulting annotations can be downloaded as a [LinkML](https://linkml.io/) or [SSSOM](https://github.com/mapping-commons/sssom) file, which can be shared with others alongside the data file, thus providing a rich description of the data. Upload a file below to get started!")

# =============================================================================
# Step 1: File Upload (no API key needed)
# =============================================================================

st.write("### Step 1: Upload Data File")
st.markdown("Please click on the gray box below and then select a file to upload. The file must be in CSV, TSV, or Excel format. All of the column names should be unique.")
# A stable key keeps the uploaded file across reruns. Without it, adding other
# widgets/sections can shift this keyless widget's identity and Streamlit resets
# its value to None on a rerun (which would wipe the whole session).
uploaded_file = st.file_uploader(
    "Drag and drop or browse files",
    type=["csv", "tsv", "xlsx", "xls"],
    label_visibility="collapsed",
    key="main_file_uploader",
)

# Check if file changed and reset session state
if 'current_file_name' not in st.session_state:
    st.session_state.current_file_name = None

if uploaded_file:
    # Reset all mapping info when a new file is uploaded
    if st.session_state.current_file_name != uploaded_file.name:
        st.session_state.current_file_name = uploaded_file.name
        # Reset all mapping info
        st.session_state.mapped_terms = []
        st.session_state.value_ontology_mapping = {}
        st.session_state.column_mapping = {}
        st.session_state.selected_terms = []
        st.session_state.value_term_indices = []
        st.session_state.value_term_indices_by_value = {}
        st.session_state.selected_column = None
        st.session_state.selected_unique_value = None
        st.session_state.first_load = True
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None
        st.session_state.value_ontology_results = None
        st.session_state.search_terms_selections = {}
        st.session_state.column_states = {}
        st.session_state.selected_ontologies = []
        st.session_state.column_data_types = {}
        # Clear imported-mapping state and reset the import uploader widget
        st.session_state.imported_mapping_name = None
        st.session_state.imported_mapping_hash = None
        st.session_state.import_report = None
        st.session_state.mapping_uploader_seq = st.session_state.get('mapping_uploader_seq', 0) + 1
        # Force checkbox widgets to re-render fresh (mappings were cleared)
        st.session_state.mapping_version = st.session_state.get('mapping_version', 0) + 1
        st.session_state.preview_row_page = 0
        st.session_state.preview_col_page = 0
        st.session_state.preview_highlight_followed = None

    try:
        # Read file based on format
        file_name = uploaded_file.name.lower()

        if file_name.endswith('.csv'):
            header = _read_delimited_header(uploaded_file, ",")
            df = pd.read_csv(uploaded_file, skipinitialspace=True)
        elif file_name.endswith('.tsv'):
            header = _read_delimited_header(uploaded_file, "\t")
            df = pd.read_csv(uploaded_file, sep='\t', skipinitialspace=True)
        elif file_name.endswith(('.xlsx', '.xls')):
            header = _read_excel_header(uploaded_file)
            df = pd.read_excel(uploaded_file)
        else:
            st.error("Unsupported file format")
            st.stop()

        repeated = _repeated_column_names(header)
        if repeated:
            # A file with repeated names is not usable. Leave it out of the
            # session so the preview and the mapping steps do not run.
            st.session_state.uploaded_df = None
            _show_repeated_column_message(repeated)
            st.stop()

        df.index = range(1, len(df) + 1)
        st.session_state.uploaded_df = df

        # File processing completion message
        st.success("File uploaded successfully! Found " + str(len(df)) + " rows and " + str(len(df.columns)) + " columns.")

    except Exception as e:
        st.error("Error processing file: " + str(e))
        st.stop()

    st.write("### Step 2: Preview Data")
    st.markdown("This table shows your data so you can check that it was read correctly. "
                "A large file is shown one page at a time.")
    _render_data_preview(df)

    # Load the ontology catalog up front (silently). It must be available BEFORE
    # the import step so an imported file can auto-select the ontologies it uses.
    if not st.session_state.available_ontologies:
        available_ontologies = get_available_ontologies()
        st.session_state.available_ontologies = available_ontologies
    else:
        available_ontologies = st.session_state.available_ontologies

    if not available_ontologies:
        st.error("Failed to load ontologies. Please check that the ontology cache has been built.")
        st.stop()

    # Step 3: import previously-exported mappings (LinkML / SSSOM). Only available
    # once a data file is loaded; kept mappings are filtered to the current data
    # file's columns/values, and the ontologies they use are auto-selected below.
    render_import_section()

    # Step 4: select / add the ontologies to search. Any ontology auto-selected by
    # the import above is already checked here.
    st.write("### Step 4: Select Ontologies")

    # st.success("Loaded " + str(len(available_ontologies)) + " ontologies")
    render_ontology_selection(available_ontologies)

    # Column selection and ontology mapping section (requires ontologies)
    if st.session_state.selected_ontologies:
        render_column_mapping_section()

        # Section for mapping values to ontology terms
        if st.session_state.selected_column and st.session_state.uploaded_df is not None:
            render_value_mapping_section()

    # Results tables and downloads - shown whenever mappings exist, whether
    # they came from a search or from an imported file.
    if st.session_state.mapped_terms:
        render_mapped_terms()

    if st.session_state.value_ontology_mapping:
        render_value_mappings()

    if st.session_state.mapped_terms or st.session_state.value_ontology_mapping:
        render_download_buttons()

else:
    # Reset when file is removed
    if st.session_state.current_file_name is not None:
        st.session_state.current_file_name = None
        st.session_state.mapped_terms = []
        st.session_state.value_ontology_mapping = {}
        st.session_state.column_mapping = {}
        st.session_state.selected_terms = []
        st.session_state.value_term_indices = []
        st.session_state.value_term_indices_by_value = {}
        st.session_state.selected_column = None
        st.session_state.selected_unique_value = None
        st.session_state.first_load = True
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None
        st.session_state.value_ontology_results = None
        st.session_state.uploaded_df = None
        st.session_state.search_terms_selections = {}
        st.session_state.column_states = {}
        st.session_state.selected_ontologies = []
        st.session_state.column_data_types = {}
        # Clear imported-mapping state and reset the import uploader widget
        st.session_state.imported_mapping_name = None
        st.session_state.imported_mapping_hash = None
        st.session_state.import_report = None
        st.session_state.mapping_uploader_seq = st.session_state.get('mapping_uploader_seq', 0) + 1
        # Force checkbox widgets to re-render fresh (mappings were cleared)
        st.session_state.mapping_version = st.session_state.get('mapping_version', 0) + 1
        st.rerun()

st.write("---")
st.markdown(
    "This application was developed by the "
    "[Piccolo Lab](https://piccolo.byu.edu) at "
    "[Brigham Young University](https://www.byu.edu). "
    "To report a bug or request a feature, "
    "[contact us](https://github.com/gy-hwang97/Maptology/issues)."
)