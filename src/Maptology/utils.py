import inspect

import streamlit as st
import pandas as pd
import re
from dateutil import parser as date_parser

# BioPortal API is no longer used (local TF-IDF search only) / BioPortal API 더 이상 사용 안 함
API_KEY = ""

# 세션 상태 초기화 / Initialize session state
def initialize_session():
    if 'api_key' not in st.session_state:
        if API_KEY:
            st.session_state.api_key = API_KEY
        else:
            st.session_state.api_key = None
        
    if 'ontology_results' not in st.session_state:
        st.session_state.ontology_results = None
    if 'uploaded_df' not in st.session_state:
        st.session_state.uploaded_df = None
    if 'selected_column' not in st.session_state:
        st.session_state.selected_column = None
    if 'mapped_terms' not in st.session_state:
        st.session_state.mapped_terms = []
    if 'current_mapping_done' not in st.session_state:
        st.session_state.current_mapping_done = False
    if 'column_mapping' not in st.session_state:
        st.session_state.column_mapping = {}
    
    if 'selected_terms' not in st.session_state:
        st.session_state.selected_terms = []
    if 'search_term_indices' not in st.session_state:
        st.session_state.search_term_indices = {}
    
    if 'selected_term_index' not in st.session_state:
        st.session_state.selected_term_index = None
        
    if 'first_load' not in st.session_state:
        st.session_state.first_load = True
    if 'value_ontology_mapping' not in st.session_state:
        st.session_state.value_ontology_mapping = {}
    if 'selected_unique_value' not in st.session_state:
        st.session_state.selected_unique_value = None
        
    if 'value_term_indices' not in st.session_state:
        st.session_state.value_term_indices = []
    if 'value_term_indices_by_value' not in st.session_state:
        st.session_state.value_term_indices_by_value = {}
    
    if 'value_term_index' not in st.session_state:
        st.session_state.value_term_index = None
        
    if 'value_ontology_results' not in st.session_state:
        st.session_state.value_ontology_results = None
    if 'auto_searched' not in st.session_state:
        st.session_state.auto_searched = False
    if 'column_states' not in st.session_state:
        st.session_state.column_states = {}
    if 'ontology_details_cache' not in st.session_state:
        st.session_state.ontology_details_cache = {}
    
    # 사용자가 선택한 컬럼별 데이터 타입 저장 / Store user-selected data type per column
    if 'column_data_types' not in st.session_state:
        st.session_state.column_data_types = {}
        
    if 'available_ontologies' not in st.session_state:
        st.session_state.available_ontologies = []
    if 'selected_ontologies' not in st.session_state:
        st.session_state.selected_ontologies = []
    if 'filtered_ontology_results' not in st.session_state:
        st.session_state.filtered_ontology_results = None
    if 'ontologies_changed' not in st.session_state:
        st.session_state.ontologies_changed = False
    if 'search_terms_selections' not in st.session_state:
        st.session_state.search_terms_selections = {}
    
    # 삭제 카운터 초기화 / Initialize delete counters
    if 'column_checkbox_counter' not in st.session_state:
        st.session_state.column_checkbox_counter = 0
    if 'value_checkbox_counter' not in st.session_state:
        st.session_state.value_checkbox_counter = 0
    
    # 수동 검색 세션 상태 / Manual search session state
    if 'manual_column_search_results' not in st.session_state:
        st.session_state.manual_column_search_results = None
    if 'manual_column_selected_terms' not in st.session_state:
        st.session_state.manual_column_selected_terms = []
    if 'manual_column_checkbox_counter' not in st.session_state:
        st.session_state.manual_column_checkbox_counter = 0
    if 'manual_value_search_results' not in st.session_state:
        st.session_state.manual_value_search_results = None
    if 'manual_value_selected_indices' not in st.session_state:
        st.session_state.manual_value_selected_indices = []
    if 'manual_value_checkbox_counter' not in st.session_state:
        st.session_state.manual_value_checkbox_counter = 0

    # 매핑 파일 가져오기 상태 / Imported-mapping state
    if 'imported_mapping_name' not in st.session_state:
        st.session_state.imported_mapping_name = None
    if 'import_report' not in st.session_state:
        st.session_state.import_report = None
    if 'mapping_uploader_seq' not in st.session_state:
        st.session_state.mapping_uploader_seq = 0

    # 체크박스 단일 진실원천용 버전 카운터 / Bumped on every mapping change so
    # checkbox widgets re-render from the mapping instead of stale widget state
    if 'mapping_version' not in st.session_state:
        st.session_state.mapping_version = 0

    # 가져온 매핑 파일의 내용 해시 / Content hash of the last-imported mapping file
    # (compared instead of the filename, so a different file with the same name
    # is still re-imported).
    if 'imported_mapping_hash' not in st.session_state:
        st.session_state.imported_mapping_hash = None

# API 키 가져오기 함수 / Get API key function
def get_api_key():
    return st.session_state.get('api_key', None)

# CSS 스타일 추가 / Add CSS styles
def add_css():
    st.markdown("""
    <style>
    /* 글로벌 폰트 설정 / Global font setting */
    html, body, [class*="css"], .stMain, .stApp,
    .stMain p,
    .stMain span,
    .stMain label,
    .stMain div,
    .stMain h1,
    .stMain h2,
    .stMain h3,
    .stMain h4,
    .stMain a,
    .stMain li,
    .stMain td,
    .stMain th,
    .stMain input,
    .stMain button,
    .stMain textarea,
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        font-family: 'Calibri', 'Arial', sans-serif !important;
    }
    /* Main headers (28px on the h3, though the span inside shows at 20px),
       subheadings (italic 20px, set on .sub-heading below) and everything
       else (20px). These
       selectors say .stMain, not .main: Streamlit renamed that container, and
       under the old name every rule here silently matched nothing, which left
       body text and buttons at the browser default while the rules keyed to a
       data-testid still applied - the mismatch the sizes were reported for. */
    .stMain h1,
    .stMain h2,
    .stMain h3 {
        font-size: 28px !important;
    }
    .stMain p,
    .stMain span,
    .stMain label,
    .stMain div,
    .stMain li,
    .stMain td,
    .stMain th,
    .stMain button,
    .stMain input,
    .stMain textarea,
    [data-testid="stFileUploader"] label p,
    [data-testid="stFileUploader"] small,
    [data-testid="stFileUploader"] span,
    [data-testid="stCaptionContainer"] p,
    .stCaption p,
    [data-testid="stSelectbox"] label p,
    [data-testid="stTextInput"] label p,
    [data-testid="stTextInput"] input,
    [data-testid="stExpander"] p {
        font-size: 20px !important;
    }
    /* Repeated column names are inline code so they read as monospaced.
       The app font rule would otherwise paint them in Calibri, and Streamlit
       draws code smaller than the alert text around it. */
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Courier New", monospace !important;
        font-size: 20px !important;
        font-weight: 400 !important;
    }
    [data-testid="stFileUploader"] label p {
        font-weight: 500 !important;
    }
    /* The font-family rule above reaches every span, which includes Streamlit's
       material icons - they are ligatures, so overriding their font printed the
       icon's name as text ("add" beside an uploaded file). Give them their font
       back. */
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded' !important;
    }
    /* Only one file is accepted at a time, so the uploader's "add another"
       button has nothing to do; hiding it also stops the file row from
       overflowing into a horizontal scrollbar. */
    [data-testid="stFileUploader"] button[aria-label="Add files"] {
        display: none !important;
    }
    /* Show the uploaded file's full name. Streamlit shortens it in script
       (start...end) before it reaches the page, so widening the chip is not
       enough; the full name is only in the title attribute. The shortened
       text is shrunk away and the title is shown in its place, wrapping
       when it does not fit. */
    .stMain [data-testid="stFileUploader"] [data-testid="stFileChips"],
    .stMain [data-testid="stFileUploader"] [data-testid="stFileChip"],
    .stMain [data-testid="stFileUploader"] [data-testid="stFileChip"] div {
        max-width: 100% !important;
        min-width: 0 !important;
    }
    .stMain [data-testid="stFileUploader"] [data-testid="stFileChip"] {
        width: auto !important;
        flex: 1 1 auto !important;
    }
    .stMain [data-testid="stFileUploader"] [data-testid="stFileChipName"] {
        font-size: 0 !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        width: auto !important;
    }
    .stMain [data-testid="stFileUploader"] [data-testid="stFileChipName"]::before {
        content: attr(title);
        font-size: 20px;
        overflow-wrap: anywhere;
    }
    /* A dialog and a popover body render outside .stMain, so the same three
       sizes and the same black text have to be stated for them as well. */
    [data-testid="stDialog"] p,
    [data-testid="stDialog"] span,
    [data-testid="stDialog"] label,
    [data-testid="stDialog"] div,
    [data-testid="stDialog"] li,
    [data-testid="stDialog"] td,
    [data-testid="stDialog"] th,
    [data-testid="stDialog"] button,
    [data-testid="stDialog"] input,
    [data-testid="stPopoverBody"] p,
    [data-testid="stPopoverBody"] span,
    [data-testid="stPopoverBody"] label,
    [data-testid="stPopoverBody"] div,
    [data-testid="stPopoverBody"] li {
        font-size: 20px !important;
    }
    [data-testid="stDialog"] h1,
    [data-testid="stDialog"] h2,
    [data-testid="stDialog"] h3 {
        font-size: 28px !important;
    }
    [data-testid="stDialog"] p,
    [data-testid="stDialog"] span,
    [data-testid="stDialog"] label,
    [data-testid="stDialog"] li,
    [data-testid="stDialog"] td,
    [data-testid="stDialog"] th,
    [data-testid="stPopoverBody"] p,
    [data-testid="stPopoverBody"] span,
    [data-testid="stPopoverBody"] li {
        color: #000000 !important;
    }
    /* Black text throughout - Streamlit greys out captions and help text -
       leaving only links blue. */
    .stMain p,
    .stMain span,
    .stMain label,
    .stMain li,
    .stMain td,
    .stMain th,
    .stMain h1,
    .stMain h2,
    .stMain h3,
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    .stCaption p {
        color: #000000 !important;
    }
    .stMain a,
    .stMain a *,
    [data-testid="stMarkdownContainer"] a,
    [data-testid="stMarkdownContainer"] a * {
        color: #0068c9 !important;
    }
    /* The download list's info control is a popover; hide the chevron
       Streamlit appends so it reads as the same plain icon button the term
       lists use. The chevron is a material icon in an aria-hidden wrapper,
       not an svg, so target that wrapper (svg kept as a fallback). */
    [data-testid="stPopoverButton"] [aria-hidden="true"],
    [data-testid="stPopoverButton"] svg {
        display: none !important;
    }
    /* An ontology row is a horizontal flex line. The name is sized to one
       full line, so a long name drops onto the next row as a whole. Keep it
       beside the button and wrap the rest of the text. */
    [data-testid="stHorizontalBlock"][class*="st-key-ont_name_"] {
        flex-wrap: nowrap !important;
    }
    [data-testid="stHorizontalBlock"][class*="st-key-ont_name_"] > [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"]) {
        min-width: 0 !important;
        width: auto !important;
        max-width: 100% !important;
        flex: 0 1 auto !important;
    }
    [data-testid="stHorizontalBlock"][class*="st-key-ont_name_"] [data-testid="stMarkdownContainer"] p {
        overflow-wrap: break-word;
    }
    /* The row gap is 1rem. Pull only the info control halfway back toward
       the name, and leave the gap before the name as it is. */
    [data-testid="stHorizontalBlock"][class*="st-key-ont_name_"] > [data-testid="stLayoutWrapper"]:has([data-testid="stPopover"]),
    [data-testid="stHorizontalBlock"][class*="st-key-ont_name_"] > [data-testid="stElementContainer"]:has([data-testid="stPopover"]),
    [class*="st-key-info_"] {
        margin-left: -0.5rem !important;
    }
    /* Anything nested inside a caption stays black too. */
    [data-testid="stCaptionContainer"] * {
        color: #000000 !important;
    }
    /* st.table renders a real HTML table, so the body font and colour reach
       it; let a wide one scroll rather than overflow the page. */
    [data-testid="stTable"] {
        overflow-x: auto;
    }
    [data-testid="stTable"] td,
    [data-testid="stTable"] th {
        font-size: 20px !important;
        color: #000000 !important;
    }
    /* The data preview's hover toolbar (columns, download, search, fullscreen)
       pops up over the table and covers the header. The preview is the only
       dataframe, so this does not affect other widgets. */
    [data-testid="stDataFrame"] [data-testid="stElementToolbar"] {
        display: none !important;
    }
    /* Streamlit leaves a wide gap above the first element; with the toolbar
       hidden there is nothing up there to make room for. */
    [data-testid="stMainBlockContainer"] {
        padding-top: 1rem !important;
    }
    .stMain {
        max-width: 95% !important;
        padding: 1rem;
    }
    .term-box {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 5px 0;
        background-color: #f9f9f9;
    }
    .term-label {
        font-weight: bold;
        color: #000000;
        margin-bottom: 4px;
    }
    .term-definition {
        font-style: italic;
        color: #000000;
        margin-top: 4px;
    }
    div[data-testid="stDataFrame"] > div {
        overflow-x: hidden !important;
    }
    div[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {
        overflow-x: auto !important;
    }
    div[data-testid="stDataFrame"] > div::-webkit-scrollbar {
        height: 0px !important;
    }
    div[data-testid="stDataFrame"] > div {
        scrollbar-width: none !important;
    }
    .delete-button {
        color: red;
        cursor: pointer;
    }
    .type-badge {
        display: inline-block;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 20px;
        margin-left: 8px;
        background-color: #f0f0f0;
        border: 1px solid #ddd;
    }
    .type-string { background-color: #e6f3ff; border-color: #b3d9ff; }
    .type-numeric { background-color: #e6ffe6; border-color: #b3ffb3; }
    .type-date { background-color: #fff0e6; border-color: #ffd1b3; }
    .type-boolean { background-color: #ffe6e6; border-color: #ffb3b3; }
    .conversion-summary {
        padding: 10px;
        border-left: 4px solid #4CAF50;
        background-color: #f8f9fa;
        margin: 10px 0;
    }
    .mapping-table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    .mapping-table th { background-color: #f8f9fa; padding: 8px; text-align: left; border-bottom: 2px solid #ddd; }
    .mapping-table td { padding: 8px; border-bottom: 1px solid #eee; }
    .mapping-table tr:hover { background-color: #f5f5f5; }
    .value-mapping-section { margin-top: 20px; padding-top: 10px; border-top: 1px solid #eee; }
    .section-header {
        background-color: #f0f0f0;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: bold;
        color: #000000;
    }
    .section-purple { border-left: 5px solid #9370DB; }
    .section-red { border-left: 5px solid #FF6B6B; }
    .section-blue { border-left: 5px solid #4682B4; }
    .ontology-checkbox-container {
        max-height: 300px; overflow-y: auto;
        border: 1px solid #ddd; padding: 10px; border-radius: 5px; margin-top: 10px;
    }
    .scrollable-container {
        max-height: 300px; overflow-y: auto;
        border: 1px solid #ddd; border-radius: 5px; padding: 10px; margin: 10px 0;
    }
    [data-testid="stExpander"] div:has(>.streamlit-expanderContent) {
        overflow: auto; max-height: 400px;
    }
    .selected-term {
        background-color: #e6f3ff; border-left: 3px solid #4e8cff;
        padding: 8px; margin: 5px 0; border-radius: 4px;
    }
    .multiple-selections-box {
        border: 1px solid #ddd; border-radius: 5px; padding: 10px; margin: 10px 0; background-color: #f9f9f9;
    }
    .selection-summary { font-weight: bold; margin-bottom: 8px; color: #000000; }
    .section-green { border-left: 5px solid #4CAF50; }
    .stFileUploader button[kind="icon"] { display: none !important; }
    .stFileUploader button[kind="secondary"] { display: none !important; }
    .unique-values-display {
        background-color: #f8f9fa; padding: 8px 12px; border-radius: 5px;
        border-left: 3px solid #4682B4; margin: 5px 0;
    }
    [data-testid="stForm"] { border: none !important; padding: 0 !important; }
    /* Same size as the Step headings as they actually render: the 20px rule
       above reaches the span inside each h3, so those show at 20px, not 28px. */
    .stMain .sub-heading,
    [data-testid="stDialog"] .sub-heading {
        font-size: 20px !important;
        font-weight: normal !important;
        font-style: italic !important;
        margin-top: 10px;
        margin-bottom: 14px;
    }
    /* Button labels live in a markdown container whose text is forced black,
       which hides Streamlit's faded disabled color. Download, Previous, and
       Next should read as unavailable when they cannot be used. The preview
       pagers use the same treatment: Previous is faded on the first page and
       Next is faded on the last page. */
    [class*="st-key-download_"]:not(.st-key-download_dialog_done) button:disabled,
    [class*="st-key-download_"]:not(.st-key-download_dialog_done) button:disabled [data-testid="stMarkdownContainer"],
    [class*="st-key-download_"]:not(.st-key-download_dialog_done) button:disabled [data-testid="stMarkdownContainer"] *,
    [class*="st-key-preview_row_"] button:disabled,
    [class*="st-key-preview_row_"] button:disabled [data-testid="stMarkdownContainer"],
    [class*="st-key-preview_row_"] button:disabled [data-testid="stMarkdownContainer"] *,
    [class*="st-key-preview_col_"] button:disabled,
    [class*="st-key-preview_col_"] button:disabled [data-testid="stMarkdownContainer"],
    [class*="st-key-preview_col_"] button:disabled [data-testid="stMarkdownContainer"] * {
        color: rgba(0, 0, 0, 0.4) !important;
        -webkit-text-fill-color: rgba(0, 0, 0, 0.4) !important;
    }
    /* Done and the dialog's corner close button are redrawn by React as soon
       as a widget is clicked, which strips a disabled flag set from script
       before the browser paints. A class on the page is not part of that
       redraw, so these two gray out on the same click as the Download buttons. */
    body.maptology-download-busy .st-key-download_dialog_done button,
    body.maptology-download-busy .st-key-download_dialog_done button [data-testid="stMarkdownContainer"],
    body.maptology-download-busy .st-key-download_dialog_done button [data-testid="stMarkdownContainer"] * {
        color: rgba(0, 0, 0, 0.4) !important;
        -webkit-text-fill-color: rgba(0, 0, 0, 0.4) !important;
        cursor: not-allowed !important;
    }
    body.maptology-download-busy .st-key-download_dialog_done button,
    body.maptology-download-busy [data-testid="stDialog"] button[aria-label="Close"] {
        pointer-events: none !important;
        cursor: not-allowed !important;
    }
    body.maptology-download-busy [data-testid="stDialog"] button[aria-label="Close"] {
        opacity: 0.4 !important;
    }
    /* Gray the other Download buttons while a fetch runs. Do not set
       pointer-events here: this class is added on mouse-down, and blocking
       the click would stop the download from ever starting. Previous and
       Next are not part of this. */
    body.maptology-download-busy [class*="st-key-download_"]:not([class*="st-key-download_page_"]):not([class*="st-key-download_dialog_"]) button,
    body.maptology-download-busy [class*="st-key-download_"]:not([class*="st-key-download_page_"]):not([class*="st-key-download_dialog_"]) button [data-testid="stMarkdownContainer"],
    body.maptology-download-busy [class*="st-key-download_"]:not([class*="st-key-download_page_"]):not([class*="st-key-download_dialog_"]) button [data-testid="stMarkdownContainer"] * {
        color: rgba(0, 0, 0, 0.4) !important;
        -webkit-text-fill-color: rgba(0, 0, 0, 0.4) !important;
        cursor: not-allowed !important;
    }
    /* Ontology column values are rendered as DISABLED tertiary buttons (only to
       align them on the same row as the checkbox / ℹ️). Show their text in the
       normal text color instead of the faded 'disabled' grey, so they match the
       Term column values. Only disabled tertiary buttons are affected. */
    button[kind="tertiary"]:disabled,
    button[kind="tertiary"]:disabled *,
    [data-testid="stBaseButton-tertiary"]:disabled,
    [data-testid="stBaseButton-tertiary"]:disabled * {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        opacity: 1 !important;
        cursor: default !important;
    }
    /* These boxes apply on their own as the user types, so Streamlit's
       "Press Enter to apply" / "Press Enter to submit form" hint is wrong. */
    [data-testid="stTextInput"]:has(input[placeholder^="Type to filter"]) [data-testid="InputInstructions"],
    [data-testid="stTextInput"]:has(input[aria-label="Enter keywords to search for ontology terms"]) [data-testid="InputInstructions"] {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)
    # Newer Streamlit commits these boxes itself via live=True. The keystroke
    # helper is only for versions that still wait for Enter, and it must not
    # run alongside live mode or it swallows the first characters.
    if not _text_input_supports_live():
        _install_live_text_inputs()
    # The available-ontology list is filtered here, in the browser, so the
    # first character hides rows immediately. A server round trip redraws
    # every row and only catches up after several characters have been typed.
    _install_ontology_browser_filter()
    _install_info_button_no_tooltip()


# A filter or keyword search starts at this many characters. An empty box
# leaves the list unfiltered and clears a search.
LIVE_QUERY_MIN_CHARS = 1


def live_query(text):
    """Text to filter or search on, or "" until it is long enough to act on."""
    text = str(text or "").strip()
    if len(text) < LIVE_QUERY_MIN_CHARS:
        return ""
    return text


def _text_input_supports_live():
    """True when this Streamlit commits a text box while the user is typing."""
    try:
        return "live" in inspect.signature(st.text_input).parameters
    except (TypeError, ValueError):
        return False


def live_text_input(label, **kwargs):
    """Text box that filters or searches as it is typed, from the first character."""
    if _text_input_supports_live():
        kwargs["live"] = True
    return st.text_input(label, **kwargs)


def _install_info_button_no_tooltip():
    """Drop the hover label on ℹ️ buttons.

    A short label in a horizontal row gets the label text as its title, so
    the browser shows "ℹ️" on hover. Term-list buttons used to add a second
    tooltip, "View term details"; that help text is no longer set.
    """
    st.html(
        """
        <style>
        [data-testid="stElementContainer"]:has(.maptology-info-notip) {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        <div class="maptology-info-notip" hidden></div>
        <script>
        (function () {
            if (window.__maptologyInfoNoTipV1) return;
            window.__maptologyInfoNoTipV1 = true;

            function isInfoButton(button) {
                var parts = button.querySelectorAll(
                    '[data-testid="stMarkdownContainer"]');
                var label = "";
                for (var i = 0; i < parts.length; i++) {
                    label += (parts[i].textContent || "").replace(
                        /\\s+/g, " ").trim();
                }
                return label === "ℹ️";
            }

            function clearTitles() {
                var buttons = document.querySelectorAll("button");
                for (var i = 0; i < buttons.length; i++) {
                    if (!isInfoButton(buttons[i])) continue;
                    if (buttons[i].hasAttribute("title"))
                        buttons[i].removeAttribute("title");
                    var titled = buttons[i].querySelectorAll("[title]");
                    for (var j = 0; j < titled.length; j++)
                        titled[j].removeAttribute("title");
                }
            }

            var scheduled = false;
            new MutationObserver(function () {
                if (scheduled) return;
                scheduled = true;
                requestAnimationFrame(function () {
                    scheduled = false;
                    clearTitles();
                });
            }).observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ["title"]
            });
            clearTitles();
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _install_ontology_browser_filter():
    """Hide available-ontology rows as the filter box changes, with no rerun."""
    st.html(
        """
        <style>
        [data-testid="stElementContainer"]:has(.maptology-ont-filter),
        [data-testid="stElementContainer"]:has(.maptology-ont-filter-focus) {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        /* Hidden until a filter matches nothing. Same pale red fill as an
           error alert; the app's text color stays black on those alerts. */
        .maptology-ont-filter-empty,
        [data-testid="stElementContainer"]:has(.maptology-ont-filter-empty):not(:has([class*="st-key-ont_name_av_"])),
        [data-testid="stLayoutWrapper"]:has(.maptology-ont-filter-empty):not(:has([class*="st-key-ont_name_av_"])) {
            display: none;
        }
        .maptology-ont-filter-empty {
            box-sizing: border-box;
            width: 100%;
            margin: 0;
            padding: 20px;
            border-radius: 10px;
            background-color: rgba(255, 43, 43, 0.1);
            line-height: 1.4;
        }
        </style>
        <div class="maptology-ont-filter"></div>
        <script>
        (function () {
            if (window.__maptologyOntFilterV11) return;
            window.__maptologyOntFilterV11 = true;

            var PLACEHOLDER = "Type to filter available ontologies...";

            function filterInput() {
                return document.querySelector(
                    'input[placeholder="' + PLACEHOLDER + '"]');
            }

            // The visible line is "ACRONYM - Name". A query matches when it
            // appears anywhere in the name, or anywhere in the acronym.
            function rowLabel(row) {
                var parts = row.querySelectorAll(
                    '[data-testid="stMarkdownContainer"]');
                for (var j = 0; j < parts.length; j++) {
                    var text = (parts[j].textContent || "").replace(
                        /\\s+/g, " ").trim();
                    if (text.indexOf(" - ") !== -1) return text;
                }
                return "";
            }

            function matches(label, query) {
                if (!query) return true;
                var split = label.indexOf(" - ");
                var acronym = (split === -1 ? label : label.slice(0, split))
                    .trim().toLowerCase();
                var name = (split === -1 ? "" : label.slice(split + 3))
                    .trim().toLowerCase();
                if (name.indexOf(query) !== -1) return true;
                return acronym.indexOf(query) !== -1;
            }

            function apply() {
                var input = filterInput();
                var query = input ? input.value.trim().toLowerCase() : "";
                var rows = document.querySelectorAll(
                    '[data-testid="stHorizontalBlock"][class*="st-key-ont_name_av_"]');
                var shown = 0;
                var scroller = null;
                for (var i = 0; i < rows.length; i++) {
                    var match = matches(rowLabel(rows[i]), query);
                    // Hide the wrapper, not just the inner row. A zero-height
                    // child still keeps the list's gap, which shoves the
                    // match down the scroll box.
                    var wrap = rows[i].parentElement;
                    var box = (wrap && wrap.getAttribute("data-testid")
                               === "stLayoutWrapper") ? wrap : rows[i];
                    box.style.display = match ? "" : "none";
                    if (match) shown++;
                    if (!scroller) {
                        var parent = box.parentElement;
                        if (parent && getComputedStyle(parent).overflowY === "auto")
                            scroller = parent;
                    }
                }
                if (scroller && query) scroller.scrollTop = 0;
                var empty = document.querySelector(".maptology-ont-filter-empty");
                if (!empty) return;
                var show = query && rows.length && shown === 0;
                empty.textContent = show
                    ? "No available ontology matches '" + input.value.trim() + "'."
                    : "";
                // The notice lives inside the list. Hide its wrappers too, or
                // an empty slot stays at the top of the scroll box.
                var hosts = [];
                var node = empty.parentElement;
                while (node && node !== document.body) {
                    var testid = node.getAttribute("data-testid") || "";
                    if (testid === "stVerticalBlock") break;
                    if (testid === "stElementContainer" || testid === "stLayoutWrapper") {
                        if (node.querySelector('[class*="st-key-ont_name_av_"]')) break;
                        hosts.push(node);
                    }
                    node = node.parentElement;
                }
                var visible = show ? "block" : "none";
                empty.style.display = visible;
                for (var h = 0; h < hosts.length; h++) hosts[h].style.display = visible;
            }

            document.addEventListener("input", function (event) {
                var node = event.target;
                if (!node || node.getAttribute("placeholder") !== PLACEHOLDER) return;
                apply();
            }, true);

            // After Select, the rerun leaves a marker. If the filter box
            // already has text, put the cursor back there so typing can
            // continue. An empty box keeps whatever focus the rerun left.
            function focusFilterIfRequested() {
                var marker = document.querySelector(".maptology-ont-filter-focus");
                if (!marker) return;
                // The token changes on each Select. The element itself may be
                // reused, so a flag left on it last time must not hide a new one.
                var token = marker.getAttribute("data-token") || "";
                if (!token || marker.getAttribute("data-done") === token) return;
                if (!filterInput()) return;
                marker.setAttribute("data-done", token);
                var until = Date.now() + 1000;
                function place() {
                    var box = filterInput();
                    if (!box || !box.isConnected) return;
                    if (!box.value.trim()) return;
                    var active = document.activeElement;
                    if (active && active !== box && active.tagName === "INPUT") return;
                    if (active === box) return;
                    box.focus({preventScroll: true});
                    var end = box.value.length;
                    try { box.setSelectionRange(end, end); } catch (err) {}
                }
                function finish() {
                    document.removeEventListener("focusin", onFocusIn, true);
                }
                function onFocusIn(event) {
                    if (Date.now() > until) {
                        finish();
                        return;
                    }
                    var target = event.target;
                    if (target && target.tagName === "INPUT") return;
                    place();
                }
                document.addEventListener("focusin", onFocusIn, true);
                [0, 50, 150, 400, 800].forEach(function (ms) {
                    setTimeout(place, ms);
                });
                setTimeout(finish, 1000);
            }

            // A rerun rebuilds the rows and drops the hidden flags. Put them
            // back from whatever is still in the box.
            var scheduled = false;
            new MutationObserver(function () {
                if (scheduled) return;
                scheduled = true;
                requestAnimationFrame(function () {
                    scheduled = false;
                    var input = filterInput();
                    if (input && input.value) apply();
                    focusFilterIfRequested();
                });
            }).observe(document.body, {childList: true, subtree: true});
            focusFilterIfRequested();
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _install_live_text_inputs():
    """Commit filter and keyword boxes without Enter.

    Streamlit only sends a text box's value when it blurs or Enter is pressed,
    and it prints "Press Enter to apply" while the value is pending. These
    boxes should act on their own: after the user pauses, send Enter for them
    so the script sees the text. The script then ignores anything shorter than
    LIVE_QUERY_MIN_CHARS.
    """
    st.html(
        """
        <style>
        [data-testid="stElementContainer"]:has(.maptology-live-query) {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        <div class="maptology-live-query"></div>
        <script>
        (function () {
            if (window.__maptologyLiveQueryV1) return;
            window.__maptologyLiveQueryV1 = true;

            var MIN_CHARS = 1;
            var DELAY_MS = 400;
            var timers = new WeakMap();

            function isLiveInput(node) {
                if (!node || node.tagName !== "INPUT") return false;
                var placeholder = node.getAttribute("placeholder") || "";
                if (placeholder.indexOf("Type to filter") === 0) return true;
                return (node.getAttribute("aria-label") || "")
                    === "Enter keywords to search for ontology terms";
            }

            function applied(value) {
                var text = (value || "").trim();
                return text.length >= MIN_CHARS ? text : "";
            }

            function commit(input) {
                var next = applied(input.value);
                if (next === (input.dataset.maptologyApplied || "")) return;
                input.dataset.maptologyApplied = next;
                input.dispatchEvent(new KeyboardEvent("keydown", {
                    key: "Enter",
                    code: "Enter",
                    keyCode: 13,
                    which: 13,
                    bubbles: true,
                    cancelable: true
                }));
            }

            function schedule(input) {
                var pending = timers.get(input);
                if (pending) clearTimeout(pending);
                timers.set(input, setTimeout(function () {
                    timers.delete(input);
                    if (!input.isConnected) return;
                    commit(input);
                }, DELAY_MS));
            }

            document.addEventListener("focusin", function (event) {
                var input = event.target;
                if (!isLiveInput(input)) return;
                if (input.dataset.maptologyAppliedSet === "1") return;
                input.dataset.maptologyApplied = applied(input.value);
                input.dataset.maptologyAppliedSet = "1";
            }, true);

            document.addEventListener("input", function (event) {
                var input = event.target;
                if (!isLiveInput(input) || event.isComposing) return;
                schedule(input);
            }, true);

            document.addEventListener("compositionend", function (event) {
                var input = event.target;
                if (!isLiveInput(input)) return;
                schedule(input);
            }, true);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )

# pandas 데이터 타입을 사용자 친화적으로 변환 / Convert pandas dtype to user-friendly name
def get_friendly_dtype(dtype):
    dtype_name = str(dtype)
    if dtype_name in ['object', 'str']:
        return "String"
    elif dtype_name.startswith('string'):
        return "String"
    elif dtype_name.startswith('float'):
        return "Float"
    elif dtype_name.startswith('int'):
        return "Integer"
    elif dtype_name.startswith('datetime'):
        return "Datetime"
    elif dtype_name.startswith('timedelta'):
        return "Time"
    elif dtype_name == 'bool' or dtype_name == 'boolean':
        return "Boolean"
    elif dtype_name == 'category':
        return "String"
    else:
        return "String"

# dateutil을 사용하여 컬럼 타입 자동 감지 / Auto-detect column type using dateutil
def detect_column_type(df, column_name):
    dtype = df[column_name].dtype
    dtype_name = str(dtype)
    
    # object(string) 타입이 아니면 pandas dtype 그대로 사용 / Use pandas dtype if not object
    if dtype_name not in ['object', 'str'] and not dtype_name.startswith('string') and dtype_name != 'category':
        return get_friendly_dtype(dtype)
    
    values = df[column_name].dropna()
    if len(values) == 0:
        return "String"
    
    # 샘플로 최대 20개만 검사 / Check up to 20 samples
    sample = values.head(20)
    has_time_component = False
    is_time_only = True
    
    for val in sample:
        val_str = str(val).strip()
        
        # 순수 시간인지 확인 / Check if pure time
        has_date_indicator = False
        for indicator in ['/', '-']:
            if indicator in val_str:
                has_date_indicator = True
                break
        # 마침표는 시간(밀리초)이 아닌 경우만 날짜 구분자로 인식 / Period as date separator only if no colon (not milliseconds)
        if '.' in val_str and ':' not in val_str:
            has_date_indicator = True
        for month in ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']:
            if month in val_str.lower():
                has_date_indicator = True
                break
        # 4자리 연도 패턴 확인 / Check for 4-digit year pattern
        if re.search(r'\b\d{4}\b', val_str):
            has_date_indicator = True
        
        if has_date_indicator:
            is_time_only = False
        
        # dateutil로 파싱 시도 / Try parsing with dateutil
        try:
            parsed = date_parser.parse(val_str)
            if parsed.hour != 0 or parsed.minute != 0 or parsed.second != 0:
                has_time_component = True
        except (ValueError, OverflowError, TypeError):
            return "String"
    
    # 모든 값이 파싱 가능 → 타입 결정 / All values parseable → determine type
    if is_time_only:
        return "Time"
    elif has_time_component:
        return "Datetime"
    else:
        return "Date"

# 사용자가 선택한 데이터 타입을 가져오는 함수 / Get user-selected data type
def get_column_data_type(column_name):
    if column_name in st.session_state.get('column_data_types', {}):
        return st.session_state.column_data_types[column_name]
    if st.session_state.uploaded_df is not None and column_name in st.session_state.uploaded_df.columns:
        return detect_column_type(st.session_state.uploaded_df, column_name)
    return "String"

# 데이터 타입 변경 유효성 검사 함수 / Validate data type change
def validate_type_change(column_name, new_type):
    if st.session_state.uploaded_df is None:
        return True, ""
    
    df = st.session_state.uploaded_df
    actual_dtype = detect_column_type(df, column_name)
    
    if actual_dtype == new_type:
        return True, ""
    if new_type == "String":
        return True, ""
    
    # 자동 감지된 타입이 Date/Datetime/Time이면 세부 검사 / Detailed check for date/time types
    if actual_dtype == "Time":
        if new_type == "Time":
            return True, ""
        else:
            return False, f"This column contains time-only values (no dates). You can only select 'Time' or 'String'."
    
    if actual_dtype == "Date":
        if new_type in ["Date", "Datetime"]:
            return True, ""
        else:
            return False, f"This column contains date values without time. You can select 'Date', 'Datetime', or 'String'."
    
    if actual_dtype == "Datetime":
        if new_type in ["Date", "Datetime", "Time"]:
            return True, ""
        else:
            return False, f"This column contains datetime values. You can select 'Date', 'Datetime', 'Time', or 'String'."
    
    if actual_dtype == "String":
        return False, f"This column contains text (string) values. You can only select 'String' for this column."
    
    if actual_dtype == "Float":
        if new_type == "Integer":
            col_data = df[column_name].dropna()
            has_decimals = False
            for val in col_data:
                if val != int(val):
                    has_decimals = True
                    break
            if has_decimals:
                return False, "This column contains at least one floating-point value and cannot be converted to Integer."
            else:
                return True, ""
        elif new_type == "Float":
            return True, ""
        else:
            return False, f"This column contains float values. You cannot convert it to '{new_type}'."
    
    if actual_dtype == "Integer":
        if new_type in ["Integer", "Float"]:
            return True, ""
        else:
            return False, f"This column contains integer values. You cannot convert it to '{new_type}'."
    
    if actual_dtype == "Boolean":
        if new_type == "Boolean":
            return True, ""
        else:
            return False, f"This column contains boolean values. You cannot convert it to '{new_type}'."
    
    if actual_dtype in ["Date", "Datetime"]:
        if new_type in ["Date", "Datetime", "Time"]:
            return True, ""
        else:
            return False, f"This column contains date/time values. You cannot convert it to '{new_type}'."
    
    if actual_dtype == "Time":
        if new_type in ["Time", "Datetime"]:
            return True, ""
        else:
            return False, f"This column contains time values. You cannot convert it to '{new_type}'."
    
    return True, ""

# 컬럼 정보 표시 함수 / Display column info function
def display_column_info(df, column_name, user_type=None):
    dtype = df[column_name].dtype
    dtype_name = str(dtype)
    
    # 사용자가 String을 선택하면 → 항상 unique values 표시 / If user selected String → always show unique values
    if user_type == "String":
        unique_values = sorted(df[column_name].dropna().unique(), key=str)
        total_count = len(unique_values)
        display_values = unique_values[:5]
        values_str = ", ".join([str(v) for v in display_values])
        
        if total_count > 5:
            remaining = total_count - 5
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str}... <em>(+{remaining} more, {total_count} total)</em></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str} <em>({total_count} total)</em></div>', unsafe_allow_html=True)
        return
    
    if user_type == "Boolean":
        unique_values = sorted(df[column_name].dropna().unique(), key=str)
        total_count = len(unique_values)
        values_str = ", ".join([str(v) for v in unique_values])
        st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str} <em>({total_count} total)</em></div>', unsafe_allow_html=True)
        return
    
    # 숫자 타입 / Numeric types
    if user_type in ["Float", "Integer"] or dtype_name.startswith('float') or dtype_name.startswith('int'):
        try:
            min_val = df[column_name].min()
            max_val = df[column_name].max()
            mean_val = df[column_name].mean()
            st.markdown(f'<div class="unique-values-display"><strong>Range:</strong> {min_val} - {max_val} &nbsp;&nbsp;|&nbsp;&nbsp; <strong>Average:</strong> {mean_val:.2f}</div>', unsafe_allow_html=True)
            return
        except (TypeError, ValueError):
            pass
    
    # 날짜/시간 타입 / Date/time types
    if user_type in ["Date", "Datetime", "Time"] or dtype_name.startswith('datetime'):
        try:
            # pandas datetime이면 바로 사용 / Use directly if pandas datetime
            if dtype_name.startswith('datetime'):
                min_date = df[column_name].min()
                max_date = df[column_name].max()
            else:
                # string인 경우 dateutil로 파싱 / Parse with dateutil if string
                parsed_dates = []
                for val in df[column_name].dropna():
                    try:
                        parsed_dates.append(date_parser.parse(str(val)))
                    except (ValueError, OverflowError, TypeError):
                        pass
                if parsed_dates:
                    min_date = min(parsed_dates)
                    max_date = max(parsed_dates)
                    if user_type == "Time":
                        min_date = min_date.strftime("%H:%M:%S")
                        max_date = max_date.strftime("%H:%M:%S")
                    elif user_type == "Date":
                        min_date = min_date.strftime("%Y-%m-%d")
                        max_date = max_date.strftime("%Y-%m-%d")
                    else:
                        min_date = min_date.strftime("%Y-%m-%d %H:%M:%S")
                        max_date = max_date.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    min_date = "N/A"
                    max_date = "N/A"
            st.markdown(f'<div class="unique-values-display"><strong>Range:</strong> {min_date} - {max_date}</div>', unsafe_allow_html=True)
            return
        except (TypeError, ValueError):
            pass
    
    # 문자열 / String
    if dtype_name in ['object', 'str'] or dtype_name.startswith('string') or dtype_name == 'category':
        unique_values = sorted(df[column_name].dropna().unique(), key=str)
        total_count = len(unique_values)
        display_values = unique_values[:5]
        values_str = ", ".join([str(v) for v in display_values])
        
        if total_count > 5:
            remaining = total_count - 5
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str}... <em>(+{remaining} more, {total_count} total)</em></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="unique-values-display"><strong>Unique values:</strong> {values_str} <em>({total_count} total)</em></div>', unsafe_allow_html=True)
    else:
        sample_values = df[column_name].head(5).tolist()
        values_str = ", ".join([str(v) for v in sample_values])
        st.markdown(f'<div class="unique-values-display"><strong>Sample values:</strong> {values_str}</div>', unsafe_allow_html=True)

# 데이터 타입 변경 함수 / Change column data type function
def change_column_type(column_name, new_type):
    if column_name and st.session_state.uploaded_df is not None:
        df = st.session_state.uploaded_df
        try:
            if new_type == "String":
                df[column_name] = df[column_name].astype('string')
            elif new_type == "Float":
                df[column_name] = df[column_name].astype('float64')
            elif new_type == "Integer":
                df[column_name] = df[column_name].astype('int64')
            elif new_type == "Boolean":
                df[column_name] = df[column_name].astype('bool')
            elif new_type in ["Date", "Datetime"]:
                df[column_name] = pd.to_datetime(df[column_name], errors='coerce')
            elif new_type == "Time":
                df[column_name] = pd.to_datetime(df[column_name], errors='coerce')
            
            st.session_state.uploaded_df = df
            for i, mapping in enumerate(st.session_state.mapped_terms):
                if mapping["Original Label"] == column_name:
                    st.session_state.mapped_terms[i]["Data Type"] = new_type
            return True
        except Exception as e:
            st.error(f"Error changing type: {str(e)}")
            return False
    return False