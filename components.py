import streamlit as st
import urllib.parse

# 로고와 제목을 컬럼으로 표시 / Display logo and title in columns
def render_header():
    col1, col2 = st.columns([3, 10])
    with col1:
        st.image("maptology.png", width=1000)

def set_term_preview(pref_label, ontology_abbr, full_ontology_name, definition, term_uri, preview_key, synonyms=None):
    """프리뷰 패널에 표시할 정보를 세션에 저장 / Store term info in session state for preview panel.

    All values come from the local TF-IDF cache (no network calls)."""
    st.session_state[preview_key] = {
        "pref_label": pref_label,
        "ontology_abbr": ontology_abbr,
        "full_ontology_name": full_ontology_name,
        "definition": definition,
        "term_uri": term_uri,
        "synonyms": list(synonyms) if synonyms else []
    }

def _render_term_details(info):
    """Render one term's details (shared by the modal and the side panel).
    All values come from the local cache - no network calls."""
    st.markdown(f"**Term:** {info['pref_label']}")
    ontology_url = f"https://bioportal.bioontology.org/ontologies/{info['ontology_abbr']}"
    st.markdown(f"**Ontology:** [{info['full_ontology_name']} ({info['ontology_abbr']})]({ontology_url})")
    definition = info.get('definition')
    if definition and definition != "No definition available":
        st.markdown(f"**Definition:** {definition}")
    else:
        st.markdown("**Definition:** _No definition available in the local ontology cache._")
    synonyms = info.get('synonyms') or []
    if synonyms:
        st.markdown(f"**Synonyms:** {', '.join(str(s) for s in synonyms)}")
    encoded_uri = urllib.parse.quote(info['term_uri'], safe='')
    detail_url = f"https://bioportal.bioontology.org/ontologies/{info['ontology_abbr']}?p=classes&conceptid={encoded_uri}"
    st.caption(f"[Open this term on BioPortal ↗]({detail_url})")


@st.dialog("Term Preview")
def show_term_modal(info):
    """Show one term's details in a modal popup. Dismissed with the built-in X
    in the corner or the Close button. Replaces the always-on side panel so the
    term list can use the full page width."""
    _render_term_details(info)
    if st.button("Close", key="close_term_modal"):
        st.rerun()


def render_preview_panel(preview_key):
    """오른쪽 패널에 Term Preview 표시 / Render Term Preview in right panel.
    (Kept for the panel-vs-modal comparison; the app now uses show_term_modal.)"""
    with st.container(border=True):
        st.markdown("#### Term Preview")
        if preview_key in st.session_state and st.session_state[preview_key]:
            _render_term_details(st.session_state[preview_key])
        else:
            st.caption("Click ℹ️ next to a term to view its details.")