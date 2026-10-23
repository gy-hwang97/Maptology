import streamlit as st
import pandas as pd
import urllib.parse
import yaml
import json
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from mapping import remove_individual_value_mapping, remove_term_mapping
from schema import generate_linkml_schema, generate_sssom_tsv, data_type_term
from utils import get_column_data_type, column_supports_value_mapping, mapping_row_id


def _ontology_term_id(uri):
    """Short id for a term IRI.

    OBO IRIs end in a prefixed local name such as HP_0000001. That id is
    written HP:0000001. Other IRIs use the fragment, or the last path segment.
    """
    uri = str(uri or "").strip()
    if not uri:
        return ""
    if uri.startswith("http://") or uri.startswith("https://"):
        if "#" in uri:
            local = uri.rsplit("#", 1)[-1]
        else:
            local = uri.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    else:
        local = uri
    local = urllib.parse.unquote(local)
    prefix, sep, rest = local.partition("_")
    if (sep and prefix and rest and prefix[0].isalpha()
            and prefix.replace("-", "").isalnum() and not prefix.islower()):
        return prefix + ":" + rest
    return local


def _install_save_as_dialog():
    """Ask where to save a Step 7 file instead of dropping it in Downloads.

    The browser's own download saves immediately, with the name chosen here.
    Chrome and Edge can open the system save dialog from the click. The file
    is still built on the server when the dialog is confirmed. If that dialog
    is not available, the button keeps the browser's normal download.
    """
    st.html(
        """
        <script>
        (function () {
            if (window.__maptologySaveAsV1) return;
            window.__maptologySaveAsV1 = true;

            var FILES = {
                download_column_mappings: ["column_mappings.csv", "CSV", "text/csv", ".csv"],
                download_value_mappings: ["value_mappings.csv", "CSV", "text/csv", ".csv"],
                download_sssom: ["maptology_mappings.sssom.tsv", "TSV", "text/tab-separated-values", ".tsv"],
                download_linkml_yaml: ["ontology_mapping_schema.yaml", "YAML", "text/yaml", ".yaml"],
                download_linkml_json: ["ontology_mapping_schema.json", "JSON", "application/json", ".json"]
            };
            var busy = false;

            function downloadKey(host) {
                var parts = (host.className || "").split(/\\s+/);
                for (var i = 0; i < parts.length; i++) {
                    if (parts[i].indexOf("st-key-download_") === 0)
                        return parts[i].slice("st-key-".length);
                }
                return "";
            }

            function reactOnClick(node) {
                while (node) {
                    var keys = Object.keys(node);
                    for (var i = 0; i < keys.length; i++) {
                        if (keys[i].indexOf("__reactProps") === 0) {
                            var props = node[keys[i]];
                            if (props && typeof props.onClick === "function")
                                return props.onClick;
                        }
                    }
                    node = node.parentElement;
                }
                return null;
            }

            function startButton(button, onClick) {
                if (onClick) {
                    onClick();
                    return;
                }
                window.__maptologySaveBypass = true;
                button.click();
                window.__maptologySaveBypass = false;
            }

            function captureNextDownload(handle) {
                var orig = HTMLAnchorElement.prototype.click;
                var restored = false;
                function restore() {
                    if (restored) return;
                    restored = true;
                    HTMLAnchorElement.prototype.click = orig;
                    busy = false;
                }
                var timer = setTimeout(restore, 20000);
                HTMLAnchorElement.prototype.click = function () {
                    var anchor = this;
                    var url = anchor && anchor.href;
                    if (!url) {
                        clearTimeout(timer);
                        restore();
                        return orig.apply(anchor, arguments);
                    }
                    clearTimeout(timer);
                    restore();
                    fetch(url).then(function (response) {
                        if (!response.ok) throw new Error("download failed");
                        return response.blob();
                    }).then(function (blob) {
                        return handle.createWritable().then(function (writable) {
                            return writable.write(blob).then(function () {
                                return writable.close();
                            });
                        });
                    }).catch(function () {
                        orig.call(anchor);
                    });
                };
            }

            document.addEventListener("click", function (event) {
                if (window.__maptologySaveBypass) return;
                if (typeof window.showSaveFilePicker !== "function") return;
                var button = event.target && event.target.closest
                    ? event.target.closest("button") : null;
                if (!button || button.disabled) return;
                var host = button.closest("[class*='st-key-download_']");
                if (!host) return;
                var spec = FILES[downloadKey(host)];
                if (!spec) return;
                if (busy) {
                    event.preventDefault();
                    event.stopPropagation();
                    event.stopImmediatePropagation();
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                busy = true;
                var onClick = reactOnClick(button);
                var accept = {};
                accept[spec[2]] = [spec[3]];
                window.showSaveFilePicker({
                    suggestedName: spec[0],
                    types: [{ description: spec[1], accept: accept }]
                }).then(function (handle) {
                    captureNextDownload(handle);
                    startButton(button, onClick);
                }, function (err) {
                    busy = false;
                    if (err && err.name === "AbortError") return;
                    startButton(button, onClick);
                });
            }, true);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _render_download_button(label, data, file_name, mime, key, disabled=False):
    """Create downloads on click instead of registering temporary files on render.

    `data` may be bytes or a function. A function runs when the button is
    clicked, so deleting a mapping does not rebuild the export files.

    Streamlit runs that function on a worker thread that has no script
    context, so session state would be empty and every download would fail.
    The context captured while drawing the button is attached before the
    file is built.
    """
    ctx = get_script_run_ctx()

    def _payload(builder=data, ctx=ctx):
        if ctx is not None:
            add_script_run_ctx(ctx=ctx)
        if callable(builder):
            return builder()
        return builder

    st.download_button(
        label,
        data=_payload,
        file_name=file_name,
        mime=mime,
        key=key,
        on_click="ignore",
        disabled=disabled,
    )


_COLUMN_EMPTY = (
    "No column mappings yet. Add a term from the search results "
    "above, and it will be listed here."
)
_VALUE_EMPTY = (
    "No value mappings yet. Add a term for a unique value above, "
    "and it will be listed here."
)


def _mapping_placeholder(message):
    """A short note that holds the mapping section's place before the first row."""
    st.markdown(
        '<p class="maptology-mapping-empty">' + message + "</p>",
        unsafe_allow_html=True,
    )


def _show_added_toast():
    """The Add click refreshes this table only, so the toast is shown here."""
    message = st.session_state.pop("term_added_toast", None)
    if message:
        st.toast(message)


def _has_value_mappings():
    """True when at least one value still has a term.

    An empty column or value left behind must not keep the table headers up.
    """
    vom = st.session_state.get("value_ontology_mapping") or {}
    for values in vom.values():
        if not isinstance(values, dict):
            continue
        for terms in values.values():
            if isinstance(terms, list):
                if terms:
                    return True
            elif terms:
                return True
    return False


# Render the mapped-terms section. A small fragment so the trash icon does
# not redraw the column search above it. The section stays on the page when
# it is empty, so the first and last mapping do not shift the steps below.
@st.fragment(key="mapped_terms_table")
def render_mapped_terms():
    _show_added_toast()
    with st.container(key="mapped_terms_block"):
        st.markdown('<div class="sub-heading">Mapped Ontology Terms</div>', unsafe_allow_html=True)
        # The note stays in the page while rows are showing, hidden by CSS, so
        # the last trash click can reveal it without waiting on a redraw.
        _mapping_placeholder(_COLUMN_EMPTY)
        if not st.session_state.mapped_terms:
            return
        with st.container(key="mapped_terms_rows"):
            _render_mapped_terms_table()


def _render_mapped_terms_table():
    st.markdown("This table shows all the ontology terms you have mapped to your columns. You can view term details or remove mappings.")
    
    header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([2.2, 2.6, 1.8, 2.4, 0.5])
    with header_col1:
        st.markdown("<strong>Column Name</strong>", unsafe_allow_html=True)
    with header_col2:
        st.markdown("<strong>Ontology Term Name</strong>", unsafe_allow_html=True)
    with header_col3:
        st.markdown("<strong>Ontology Term ID</strong>", unsafe_allow_html=True)
    with header_col4:
        st.markdown("<strong>Ontology</strong>", unsafe_allow_html=True)
    with header_col5:
        st.markdown("<strong></strong>", unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
    
    # Display each mapping individually
    for idx, mapping in enumerate(st.session_state.mapped_terms):
        column_name = mapping['Original Label']
        
        col1, col2, col3, col4, col5 = st.columns([2.2, 2.6, 1.8, 2.4, 0.5])
        
        with col1:
            st.write(column_name)

        ontology_abbr = mapping.get("Ontology Abbr", mapping["Ontology Name"].split(" ")[-1] if "(" in mapping["Ontology Name"] else mapping["Ontology Name"])
        with col2:
            preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(mapping['Ontology Term URI'], safe='')}"
            st.markdown(f"""
            <a href="{preferred_label_url}" target="_blank">{mapping['Preferred Label']}</a>
            """, unsafe_allow_html=True)

        with col3:
            st.write(_ontology_term_id(mapping.get("Ontology Term URI", "")))

        with col4:
            ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
            st.markdown(f"""
            <a href="{ontology_url}" target="_blank">{mapping['Ontology Name']}</a>
            """, unsafe_allow_html=True)
        
        with col5:
            term_uri = mapping['Ontology Term URI']
            unique_key = "delete_col_" + mapping_row_id(column_name, term_uri)
            st.button("🗑️", key=unique_key, on_click=remove_term_mapping,
                      args=(column_name, term_uri))
        
        st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)

# Display value-to-ontology mapping info. Separate from the value search so
# a trash click does not redraw that search. Kept on the page when empty so
# adding or clearing the last value mapping does not move the download step.
@st.fragment(key="value_mappings_table")
def render_value_mappings():
    _show_added_toast()
    # A number, date, or time column has nothing to list here. The note in
    # Step 6 is the whole of that step. Saved value mappings come back when
    # a string column is selected.
    if not column_supports_value_mapping():
        return
    with st.container(key="value_mappings_block"):
        st.markdown('<div class="sub-heading">Unique Values\' Ontology Terms</div>', unsafe_allow_html=True)
        # Same as the column list: the note is already here, hidden while
        # rows exist, and comes back when the last value mapping is removed.
        _mapping_placeholder(_VALUE_EMPTY)
        if not _has_value_mappings():
            return
        with st.container(key="value_mappings_rows"):
            _render_value_mappings_table()


def _render_value_mappings_table():
    st.markdown("This table shows the ontology terms mapped to specific data values within your columns. Each row represents a value-to-term mapping that you have created.")
    
    header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([1.8, 1.5, 3, 2.5, 0.5])
    with header_col1:
        st.markdown("<strong>Column</strong>", unsafe_allow_html=True)
    with header_col2:
        st.markdown("<strong>Original Value</strong>", unsafe_allow_html=True)
    with header_col3:
        st.markdown("<strong>Mapped Term(s)</strong>", unsafe_allow_html=True)
    with header_col4:
        st.markdown("<strong>Ontology</strong>", unsafe_allow_html=True)
    with header_col5:
        st.markdown("<strong></strong>", unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
    
    mapping_idx = 0
    for column in st.session_state.value_ontology_mapping:
        for value, val_mappings in st.session_state.value_ontology_mapping[column].items():
            if isinstance(val_mappings, list):
                for val_mapping in val_mappings:
                    col1, col2, col3, col4, col5 = st.columns([1.8, 1.5, 3, 2.5, 0.5])
                    
                    with col1:
                        st.write(f"{column}")
                    
                    with col2:
                        st.write(f"{value}")
                    
                    with col3:
                        ontology_abbr = val_mapping.get("Ontology Abbr", val_mapping["Ontology Name"].split(" ")[-1] if "(" in val_mapping["Ontology Name"] else val_mapping["Ontology Name"])
                        preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(val_mapping['Ontology Term URI'], safe='')}"
                        st.markdown(f"""
                        <a href="{preferred_label_url}" target="_blank">{val_mapping['Preferred Label']}</a>
                        """, unsafe_allow_html=True)
                    
                    with col4:
                        ontology_abbr = val_mapping.get("Ontology Abbr", val_mapping["Ontology Name"].split(" ")[-1] if "(" in val_mapping["Ontology Name"] else val_mapping["Ontology Name"])
                        ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
                        st.markdown(f"""
                        <a href="{ontology_url}" target="_blank">{val_mapping['Ontology Name']}</a>
                        """, unsafe_allow_html=True)
                    
                    with col5:
                        term_uri = val_mapping['Ontology Term URI']
                        unique_key = "delete_val_" + mapping_row_id(column, value, term_uri)
                        st.button("🗑️", key=unique_key,
                                  on_click=remove_individual_value_mapping,
                                  args=(column, value, term_uri))
                    
                    st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
                    mapping_idx += 1
            else:
                col1, col2, col3, col4, col5 = st.columns([1.8, 1.5, 3, 2.5, 0.5])
                
                with col1:
                    st.write(f"{column}")
                
                with col2:
                    st.write(f"{value}")
                
                with col3:
                    ontology_abbr = val_mappings.get("Ontology Abbr", val_mappings["Ontology Name"].split(" ")[-1] if "(" in val_mappings["Ontology Name"] else val_mappings["Ontology Name"])
                    preferred_label_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}?p=classes&conceptid={urllib.parse.quote(val_mappings['Ontology Term URI'], safe='')}"
                    st.markdown(f"""
                    <a href="{preferred_label_url}" target="_blank">{val_mappings['Preferred Label']}</a>
                    """, unsafe_allow_html=True)
                
                with col4:
                    ontology_abbr = val_mappings.get("Ontology Abbr", val_mappings["Ontology Name"].split(" ")[-1] if "(" in val_mappings["Ontology Name"] else val_mappings["Ontology Name"])
                    ontology_url = f"https://bioportal.bioontology.org/ontologies/{ontology_abbr}"
                    st.markdown(f"""
                    <a href="{ontology_url}" target="_blank">{val_mappings['Ontology Name']}</a>
                    """, unsafe_allow_html=True)
                
                with col5:
                    term_uri = val_mappings['Ontology Term URI']
                    unique_key = "delete_val_" + mapping_row_id(column, value, term_uri)
                    st.button("🗑️", key=unique_key,
                              on_click=remove_individual_value_mapping,
                              args=(column, value, term_uri))
                
                st.markdown("<hr style='margin: 0.5em 0; border-color: #eee;'>", unsafe_allow_html=True)
                mapping_idx += 1

def _column_mappings_csv():
    """Build the column-mapping file when the user clicks Download."""
    rows = []
    for mapping in st.session_state.mapped_terms:
        column_name = mapping['Original Label']
        column_dtype = get_column_data_type(column_name)
        rows.append({
            "Column Name": column_name,
            "Preferred Label": mapping['Preferred Label'],
            "Ontology Name": mapping['Ontology Name'],
            "Ontology URI": mapping['Ontology URI'],
            "Ontology Term URI": mapping['Ontology Term URI'],
            "Data Type": column_dtype,
            "Data Type Term URI": data_type_term(column_dtype)[1],
            "Definition": mapping.get('Definition', '')
        })
    if not rows:
        return b""
    return pd.DataFrame(rows).to_csv(index=False).encode('utf-8')


def _value_mappings_csv():
    """Build the value-mapping file when the user clicks Download."""
    rows = []
    for column, value_dict in st.session_state.value_ontology_mapping.items():
        current_dtype = get_column_data_type(column)
        current_dtype_uri = data_type_term(current_dtype)[1]
        for value, val_mappings in value_dict.items():
            if isinstance(val_mappings, list):
                entries = val_mappings
            else:
                entries = [val_mappings]
            for val_mapping in entries:
                rows.append({
                    "Column": column,
                    "Value": value,
                    "Preferred Label": val_mapping["Preferred Label"],
                    "Ontology Name": val_mapping["Ontology Name"],
                    "Ontology URI": val_mapping["Ontology URI"],
                    "Ontology Term URI": val_mapping["Ontology Term URI"],
                    "Data Type": current_dtype,
                    "Data Type Term URI": current_dtype_uri,
                    "Definition": val_mapping.get("Definition", "")
                })
    if not rows:
        return b""
    return pd.DataFrame(rows).to_csv(index=False).encode('utf-8')


def _sssom_download():
    """Build the SSSOM file when the user clicks Download."""
    data = generate_sssom_tsv()
    return data or b""


def _linkml_yaml_download():
    """Build the LinkML YAML file when the user clicks Download."""
    schema = generate_linkml_schema()
    if not schema:
        return b""
    return yaml.dump(schema, sort_keys=False, default_flow_style=False).encode("utf-8")


def _linkml_json_download():
    """Build the LinkML JSON file when the user clicks Download."""
    schema = generate_linkml_schema()
    if not schema:
        return b""
    return json.dumps(schema, indent=2).encode("utf-8")


# Render the download buttons. Its own fragment so a trash-icon delete can
# refresh which buttons are available without rebuilding the files or the
# ontology list. Each file is built when its button is clicked.
@st.fragment(key="download_results")
def render_download_buttons():
    _install_save_as_dialog()
    has_columns = bool(st.session_state.mapped_terms)
    has_values = bool(st.session_state.value_ontology_mapping)
    if not (has_columns or has_values):
        return
    st.markdown("### Step 7: Download Results", anchors=False)
    st.markdown(
        "Here you can export your annotations in various formats for use in "
        "other applications or for record keeping. Each download opens a save "
        "dialog so you can choose the folder and the file name."
    )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        _render_download_button(
            "Download Column Mappings (CSV)",
            data=_column_mappings_csv,
            file_name="column_mappings.csv",
            mime="text/csv",
            key="download_column_mappings",
            disabled=not has_columns,
        )

    with col2:
        _render_download_button(
            "Download Value Mappings (CSV)",
            data=_value_mappings_csv,
            file_name="value_mappings.csv",
            mime="text/csv",
            key="download_value_mappings",
            disabled=not has_values,
        )

    with col3:
        _render_download_button(
            "Download SSSOM (TSV)",
            data=_sssom_download,
            file_name="maptology_mappings.sssom.tsv",
            mime="text/tab-separated-values",
            key="download_sssom",
        )
    
    col4, col5, _ = st.columns(3)
    
    with col4:
        _render_download_button(
            "Download LinkML Schema (YAML)",
            data=_linkml_yaml_download,
            file_name="ontology_mapping_schema.yaml",
            mime="text/yaml",
            key="download_linkml_yaml",
        )
    
    with col5:
        _render_download_button(
            "Download Schema as JSON",
            data=_linkml_json_download,
            file_name="ontology_mapping_schema.json",
            mime="application/json",
            key="download_linkml_json",
        )

    # SSSOM / LinkML 홈페이지 링크 / SSSOM and LinkML homepage links
    st.markdown(
        "Learn more about the standards used: "
        "[LinkML](https://linkml.io/) · "
        "[SSSOM](https://mapping-commons.github.io/sssom/)"
    )
