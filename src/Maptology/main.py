import streamlit as st
import pandas as pd

from utils import initialize_session, add_css
from components import render_header
from ontology import render_ontology_selection, get_available_ontologies, search_ontology
from column_mapping import render_column_mapping_section
from value_mapping import render_value_mapping_section
from mapping_display import render_mapped_terms, render_value_mappings, render_download_buttons
from mapping_import import render_import_section

# Streamlit basic page configuration
st.set_page_config(page_title='Maptology', layout='wide')

# Add CSS styles
add_css()

# Initialize session state
initialize_session()

# Display logo and title
render_header()

# Tagline
st.markdown("### Map your dataset to standardized ontology terms")
st.caption("Maptology helps you search and map ontology terms to your dataset columns and values, then export the results in standardized formats.")

# =============================================================================
# Step 1: File Upload (no API key needed)
# =============================================================================

st.write("### Step 1: Upload Data File")
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
        st.session_state.ontology_widget_version = st.session_state.get('ontology_widget_version', 0) + 1

    try:
        # Read file based on format
        file_name = uploaded_file.name.lower()

        if file_name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, skipinitialspace=True)
        elif file_name.endswith('.tsv'):
            df = pd.read_csv(uploaded_file, sep='\t', skipinitialspace=True)
        elif file_name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("Unsupported file format")
            st.stop()

        df.index = range(1, len(df) + 1)
        st.session_state.uploaded_df = df

        # File processing completion message
        st.success("File uploaded successfully! Found " + str(len(df)) + " rows and " + str(len(df.columns)) + " columns.")

    except Exception as e:
        st.error("Error processing file: " + str(e))
        st.stop()

    st.write("### Step 2: Preview Data")
    st.caption("This table shows the first 20 lines of your data so you can verify that the data were parsed properly.")

    # Apply styling if there's a highlighted column
    if 'highlighted_column' in st.session_state and st.session_state.highlighted_column in df.columns:
        highlighted_col = st.session_state.highlighted_column

        def highlight_column(x):
            df_styler = pd.DataFrame('', index=x.index, columns=x.columns)
            df_styler[highlighted_col] = 'background-color: #90EE90;'
            return df_styler

        styled_df = df.head(20).style.apply(highlight_column, axis=None)
        st.dataframe(styled_df, width='stretch', hide_index=False)

        st.caption("Column '" + highlighted_col + "' highlighted due to recent type change")
    else:
        st.dataframe(st.session_state.uploaded_df.head(20), width='stretch', hide_index=False)

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
    st.success("Loaded " + str(len(available_ontologies)) + " ontologies")
    st.write("### Step 4: Select Ontologies")
    st.caption("Select one or more ontologies that are most relevant to your data. When you map ontology terms to your data, we will limit our search to these ontologies, thus speeding up the process.")
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
        st.session_state.ontology_widget_version = st.session_state.get('ontology_widget_version', 0) + 1
        st.rerun()

st.write("---")
st.caption("Maptology maps ontology terms to your dataset using precomputed TF-IDF vectors for fast search.")