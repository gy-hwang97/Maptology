import streamlit as st
import pandas as pd

from utils import initialize_session, add_css
from components import render_header
from ontology import render_ontology_selection, get_available_ontologies, search_ontology
from column_mapping import render_column_mapping_section
from value_mapping import render_value_mapping_section
from mapping_display import render_mapped_terms, render_value_mappings, render_download_buttons
from loading_overlay import show_loading_overlay

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

st.write("### Step 1: Upload File")
uploaded_file = st.file_uploader("Drag and drop or browse files", type=["csv", "tsv", "xlsx", "xls"], label_visibility="collapsed")

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

    # Process file with loading overlay
    loading_container = st.empty()

    with loading_container:
        show_loading_overlay("Loading...")

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

        # Remove loading overlay
        loading_container.empty()

        # File processing completion message
        st.success("File uploaded successfully! Found " + str(len(df)) + " rows and " + str(len(df.columns)) + " columns.")

    except Exception as e:
        loading_container.empty()
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

    # Ontology selection section
    if not st.session_state.available_ontologies:
        ontology_loading_container = st.empty()

        with ontology_loading_container:
            show_loading_overlay("Loading ontologies...")

        available_ontologies = get_available_ontologies()
        st.session_state.available_ontologies = available_ontologies

        ontology_loading_container.empty()
    else:
        available_ontologies = st.session_state.available_ontologies

    if available_ontologies:
        st.success("Loaded " + str(len(available_ontologies)) + " ontologies")

        st.write("### Step 3: Select Ontologies")
        st.caption("Select one or more ontologies that are most relevant to your data. When you map ontology terms to your data, we will limit our search to these ontologies, thus speeding up the process.")

        render_ontology_selection(available_ontologies)
    else:
        st.error("Failed to load ontologies. Please check that the ontology cache has been built.")
        st.stop()

    # Column selection and ontology mapping section
    if st.session_state.selected_ontologies:
        render_column_mapping_section()

        # Mapped Ontology Terms - displayed right after column mapping
        if st.session_state.mapped_terms:
            render_mapped_terms()

        # Section for mapping values to ontology terms
        if st.session_state.selected_column and st.session_state.uploaded_df is not None:
            render_value_mapping_section()

        # Unique Values' Ontology Terms - displayed right after value mapping
        if st.session_state.value_ontology_mapping:
            render_value_mappings()

        # Download buttons
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
        st.rerun()

st.write("---")
st.caption("Maptology maps ontology terms to your dataset using precomputed TF-IDF vectors for fast search.")