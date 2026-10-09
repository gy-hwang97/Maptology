import streamlit as st
import pandas as pd
from tfidf_search import get_ontology_list_from_tsv, search_local
from ontology_setup import (catalogue_entries, recorded_submissions,
                            install_ontology,
                            _download_all_requested as download_all_requested)
from utils import live_query, live_text_input


# Load the ontology catalog once per server process.
# @st.cache_data computes it a single time and shares the result across every
# session, rerun, and user; it is cleared explicitly when a new ontology is
# downloaded, which is the only time it changes.
@st.cache_data(show_spinner=False)
def _load_ontology_catalog():
    """Everything the selection list can offer.

    Two sources, merged: ontologies already downloaded and indexed on this
    machine, and the saved BioPortal catalogue, so an ontology can be chosen
    before it is downloaded - selecting it is what downloads it. Each entry
    carries `downloaded`, and `update_available` when the local index was built
    from an older BioPortal submission than the catalogue now offers.
    """
    built = {o["acronym"]: o for o in get_ontology_list_from_tsv()}
    catalogue = catalogue_entries()
    recorded = recorded_submissions()

    merged = []
    for acronym, entry in catalogue.items():
        downloaded = acronym in built
        merged.append({
            "acronym": acronym,
            "name": entry.get("name") or acronym,
            "description": entry.get("description") or "",
            "version": entry.get("version") or "",
            "released": entry.get("released") or "",
            "downloaded": downloaded,
            "update_available": downloaded
                and recorded.get(acronym) != entry.get("submissionId"),
        })
    # Ontologies built locally that BioPortal no longer lists (this happens:
    # CMEO, CVO and HTO were withdrawn from its catalogue). They keep working;
    # there is just nothing to update them from, and no catalogue description.
    for acronym, entry in built.items():
        if acronym not in catalogue:
            merged.append({
                "acronym": acronym,
                "name": entry.get("name") or acronym,
                "description": "",
                "version": "",
                "released": "",
                "downloaded": True,
                "update_available": False,
            })
    merged.sort(key=lambda x: x["acronym"])
    return merged


# Get list of available ontologies (local caches merged with the saved
# BioPortal catalogue; replaces the old per-request BioPortal API call)
def get_available_ontologies():
    if not st.session_state.available_ontologies:
        ontology_list = _load_ontology_catalog()

        if len(ontology_list) > 0:
            st.session_state.available_ontologies = ontology_list
        else:
            st.error("Error: no ontologies are available yet. Set "
                     "BIOPORTAL_APIKEY and restart Maptology to fetch the "
                     "BioPortal catalogue.")
            st.session_state.available_ontologies = []

    return st.session_state.available_ontologies


# Get ontology details (name, acronym) from local TSV file
# (replaces BioPortal API call)
def get_ontology_details(ontology_acronym):
    # Check session cache first
    if ontology_acronym in st.session_state.ontology_details_cache:
        return st.session_state.ontology_details_cache[ontology_acronym]

    # Look up from available ontologies list
    full_name = ontology_acronym
    for ont in st.session_state.available_ontologies:
        if ont["acronym"] == ontology_acronym:
            full_name = ont["name"]
            break

    # Cache the result
    st.session_state.ontology_details_cache[ontology_acronym] = {
        "full_name": full_name,
        "acronym": ontology_acronym
    }

    return st.session_state.ontology_details_cache[ontology_acronym]


# Search ontology for column mapping - search within selected ontologies
# (replaces BioPortal API search)
def search_ontology(selected_column):
    if not selected_column:
        return

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None
        return

    # Clean up search term
    search_term = selected_column.strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.ontology_results = df_results
        # The auto-suggestion list shows the TOP 10 overall. search_local returns
        # up to 10 PER ontology, so with several ontologies selected the combined
        # set is larger - keep only the 10 best distinct terms.
        st.session_state.filtered_ontology_results = (
            df_results.drop_duplicates(subset=["Ontology Term URI"], keep="first").head(10)
        )

        # Reset selected term index if it's out of range
        if (st.session_state.selected_term_index is not None and
            st.session_state.selected_term_index >= len(df_results)):
            st.session_state.selected_term_index = None
    else:
        # Automatic search: no match is not an error - stay silent so users
        # are not told "no results" for a search they did not run. They can
        # still type keywords in the manual search box.
        st.session_state.ontology_results = None
        st.session_state.filtered_ontology_results = None


# Search ontology for value mapping - search within selected ontologies
# (replaces BioPortal API search)
def search_ontology_for_value(selected_value):
    if not selected_value:
        return

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        st.session_state.value_ontology_results = None
        return

    # Clean up search term
    search_term = str(selected_value).strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        # Auto-suggestion list: keep only the top 10 overall (see search_ontology).
        st.session_state.value_ontology_results = (
            df_results.drop_duplicates(subset=["Ontology Term URI"], keep="first").head(10)
        )
    else:
        # Automatic value search: stay silent on no match (see search_ontology).
        st.session_state.value_ontology_results = None


# Search all selected ontologies for column terms
# (replaces search_bioportal_all_columns)
def search_bioportal_all_columns(search_term):
    if not search_term:
        return False

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = str(search_term).strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.ontology_results = df_results
        st.session_state.filtered_ontology_results = df_results

        # Reset selection
        st.session_state.selected_terms = []

        return True
    else:
        return False


# Search all selected ontologies for value terms
# (replaces search_bioportal_all)
def search_bioportal_all(search_term):
    if not search_term:
        return False

    # Check if ontologies are selected
    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = str(search_term).strip()

    # Search using local TF-IDF
    df_results = search_local(search_term, st.session_state.selected_ontologies)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.value_ontology_results = df_results

        # Reset selection
        st.session_state.value_term_indices = []

        return True
    else:
        return False


# Manual search for value mapping
# (replaces search_bioportal_manual_value)
def search_bioportal_manual_value(search_term):
    if not search_term:
        return False

    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = str(search_term).strip()

    # Search using local TF-IDF. Fetch more per ontology (top_n=20) so that after
    # we drop terms already shown in the auto list, enough candidates remain to
    # show ~10.
    df_results = search_local(search_term, st.session_state.selected_ontologies, top_n=20)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.manual_value_search_results = df_results
        st.session_state.manual_value_selected_indices = []
        return True
    else:
        st.session_state.manual_value_search_results = None
        return False


# Manual search for column mapping
# (replaces search_bioportal_manual_column)
def search_bioportal_manual_column(search_term):
    if not search_term:
        return False

    if not st.session_state.selected_ontologies:
        st.warning("Please select at least one ontology first.")
        return False

    # Clean up search term
    search_term = str(search_term).strip()

    # Search using local TF-IDF. Fetch more per ontology (top_n=20) so that after
    # we drop terms already shown in the auto list, enough candidates remain to
    # show ~10.
    df_results = search_local(search_term, st.session_state.selected_ontologies, top_n=20)

    if df_results is not None and len(df_results) > 0:
        # Sort by relevance (TF-IDF cosine similarity), highest first
        df_results = df_results.sort_values(by=["Mapping Score", "Preferred Label"], ascending=[False, True])
        st.session_state.manual_column_search_results = df_results
        st.session_state.manual_column_selected_terms = []
        return True
    else:
        st.session_state.manual_column_search_results = None
        return False


MAX_SELECTED_ONTOLOGIES = 10


def _render_ontology_details(ont):
    """One ontology's description, version and release date."""
    st.markdown("**" + ont["acronym"] + " - " + ont["name"] + "**")
    if ont.get("description"):
        st.write(ont["description"])
    else:
        st.write("_No description available._")
    meta = []
    if ont.get("version"):
        meta.append("Version: " + str(ont["version"]))
    if ont.get("released"):
        meta.append("Released: " + str(ont["released"])[:10])
    if meta:
        st.write("  |  ".join(meta))


def _dialog_downloaded():
    """Acronyms fetched in this dialog visit, so they leave the list at once."""
    return st.session_state.setdefault("dialog_downloaded_acronyms", set())


def _pending_downloads():
    """Ontologies queued to fetch, in order, as (acronym, name) pairs."""
    return st.session_state.setdefault("pending_ontology_downloads", [])


def _queue_ontology_download(acronym, name):
    """Queue one ontology. A second click does nothing until this one finishes."""
    pending = _pending_downloads()
    if pending:
        return
    pending.append((acronym, name))


def _success_download_message(name, acronym):
    shown = name.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")
    return ("*" + shown + "* (" + acronym + ") was downloaded successfully. "
            "It has been added to the list of available ontologies on the main page.")


def _render_download_row(ont, queued=False, show_info=True, locked=False):
    """One row in the download list: Download, name, and usually details.

    Details are skipped while a download is in progress. A popover body is
    built for every row, and that work was delaying the Downloading note.
    `locked` disables this button while some other ontology is downloading.
    """
    acronym = ont["acronym"]
    with st.container(horizontal=True, vertical_alignment="center",
                      key="ont_name_dl_" + acronym):
        st.button("Download", key="download_" + acronym,
                  disabled=queued or locked,
                  on_click=_queue_ontology_download,
                  args=(acronym, ont["name"]))
        st.markdown(acronym + " - " + ont["name"])
        # A dialog cannot be opened from inside this one, so the details pop
        # up over the row. Nothing reruns, so it opens at once; the chevron
        # Streamlit adds to a popover is hidden in CSS.
        if show_info:
            with st.popover("ℹ️", type="tertiary"):
                _render_ontology_details(ont)


def _shift_download_page(delta):
    """Move one page before Previous and Next are drawn.

    A button's disabled flag is fixed when the button is created. Updating
    the page after that click changes the list, but leaves the buttons grayed
    for the page just left until something else redraws them.
    """
    st.session_state.download_list_page = (
        st.session_state.get("download_list_page", 0) + delta)


def _clear_download_dialog_state():
    """Drop dialog-only state. The main page reads the catalog on its own."""
    st.session_state.show_download_dialog = False
    st.session_state.pop("pending_ontology_downloads", None)
    st.session_state.pop("dialog_downloaded_acronyms", None)
    st.session_state.pop("download_row_errors", None)
    st.session_state.pop("download_list_page", None)
    st.session_state.pop("download_list_filter", None)


def _close_download_dialog():
    """Close the download dialog without first redrawing its list.

    A click inside a dialog reruns the dialog before the button's result is
    visible, and that list is one row per ontology still to fetch. A callback
    runs before the body, and st.rerun() stops there, so Done does not build
    the list only to discard it. The full rerun is what closes the dialog and
    shows anything just downloaded under Available ontologies.
    """
    _clear_download_dialog_state()
    st.rerun()


def _dismiss_download_dialog():
    """The corner close button dismisses the dialog; refresh the main page."""
    _clear_download_dialog_state()


def _arm_single_download_lock():
    """Lock the dialog's other actions in the browser as soon as Download is clicked.

    The fetch runs in this dialog until BioPortal responds, so the page cannot
    close it until then. Streamlit only disables Done once that run has
    started, and the corner close button is not one of those widgets. This
    turns both off at the click, and turns them back on when the Downloading
    note leaves.
    """
    st.html(
        """
        <style>
        [data-testid="stElementContainer"]:has(.maptology-download-lock) {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        <div class="maptology-download-lock"></div>
        <script>
        (function () {
            if (window.__maptologySingleDownloadV7) return;
            window.__maptologySingleDownloadV7 = true;

            function downloadLabel(button) {
                return (button.textContent || "").replace(/\\s+/g, " ").trim();
            }

            function dialogOf(node) {
                return node.closest('[data-testid="stDialog"]');
            }

            function lockOthers(clicked) {
                var dialog = dialogOf(clicked);
                if (!dialog) return;
                var buttons = dialog.querySelectorAll("button");
                for (var i = 0; i < buttons.length; i++) {
                    var other = buttons[i];
                    if (other === clicked) continue;
                    if (downloadLabel(other) !== "Download") continue;
                    other.disabled = true;
                }
            }

            function stillDownloading(dialog, acr) {
                var text = dialog.innerText || "";
                if (!acr) return text.indexOf("Downloading ") !== -1;
                return text.indexOf("Downloading " + acr + " from BioPortal") !== -1;
            }

            function successShown(dialog, acr) {
                var alerts = dialog.querySelectorAll('[data-testid="stAlert"]');
                for (var i = 0; i < alerts.length; i++) {
                    var found = successAcronym(alerts[i].textContent || "");
                    if (found && (!acr || found === acr)) return true;
                }
                return false;
            }

            function exceptionText() {
                var nodes = document.querySelectorAll('[data-testid="stException"]');
                var parts = [];
                for (var i = 0; i < nodes.length; i++) parts.push(nodes[i].innerText || "");
                return parts.join("\\n");
            }

            // The note under one row: "" if there is none, null if the row is
            // not on screen. Any note other than Downloading or a success note
            // is an error; the messages vary (missing API key, not in the
            // catalogue, failed fetch), so the wording is not matched.
            function rowNoteAlert(dialog, acr) {
                if (!acr) return null;
                var rows = dialog.querySelectorAll(ROW_SELECTOR);
                for (var i = 0; i < rows.length; i++) {
                    if (rowAcronym(rows[i]) !== acr) continue;
                    var slot = ownWrapper(rows[i], dialog).nextElementSibling;
                    return {alert: slot ? slot.querySelector('[data-testid="stAlert"]') : null};
                }
                return null;
            }

            function rowNote(dialog, acr) {
                var found = rowNoteAlert(dialog, acr);
                if (!found) return null;
                return found.alert ? (found.alert.textContent || "").trim() : "";
            }

            function beginDownload(button) {
                var dialog = dialogOf(button);
                if (!dialog) return;
                window.__maptologyDownloadBusy = true;
                window.__maptologyDownloadSaw = false;
                window.__maptologyDownloadScrolled = false;
                var row = button.closest(ROW_SELECTOR);
                window.__maptologyDownloadAcronym = row ? rowAcronym(row) : null;
                window.__maptologySuccessGen = (window.__maptologySuccessGen || 0) + 1;
                window.__maptologyExceptionAtStart = exceptionText();
                window.__maptologyNoteAtStart = rowNote(dialog, window.__maptologyDownloadAcronym);
                document.body.classList.add("maptology-download-busy");
                lockOthers(button);
            }

            function enableDownloadButtons() {
                if (window.__maptologyDownloadBusy) return;
                var dialog = document.querySelector('[data-testid="stDialog"]');
                if (!dialog) return;
                var buttons = dialog.querySelectorAll("button");
                for (var i = 0; i < buttons.length; i++) {
                    if (downloadLabel(buttons[i]) !== "Download") continue;
                    buttons[i].disabled = false;
                }
            }

            function endDownload() {
                window.__maptologyDownloadBusy = false;
                window.__maptologyDownloadSaw = false;
                document.body.classList.remove("maptology-download-busy");
                enableDownloadButtons();
                // The page may apply its own disabled flag as this run ends.
                // Put the buttons back once that has settled.
                setTimeout(enableDownloadButtons, 0);
                setTimeout(enableDownloadButtons, 300);
            }

            // Acronyms whose success note has had its three seconds. The page
            // reuses the same nodes for other rows when the list is redrawn,
            // so what is hidden is decided by content, not by node.
            window.__maptologyHiddenAcronyms = window.__maptologyHiddenAcronyms || {};

            var SUCCESS_SUFFIX = ") was downloaded successfully";

            function successAcronym(text) {
                var end = text.indexOf(SUCCESS_SUFFIX);
                if (end === -1) return null;
                var start = text.lastIndexOf("(", end);
                if (start === -1) return null;
                return text.slice(start + 1, end);
            }

            var ROW_SELECTOR = '[data-testid="stHorizontalBlock"][class*="st-key-ont_name_dl_"]';

            function rowAcronym(row) {
                var texts = row.querySelectorAll('[data-testid="stMarkdownContainer"] p');
                for (var i = 0; i < texts.length; i++) {
                    var t = (texts[i].textContent || "").trim();
                    var dash = t.indexOf(" - ");
                    if (dash > 0) return t.slice(0, dash);
                }
                return null;
            }

            // The outermost wrapper that holds only this row or note, so its
            // spacing goes too. Stops before any node that also holds others.
            function ownWrapper(node, dialog) {
                var n = node;
                while (n.parentElement && n.parentElement !== dialog
                        && n.parentElement.children.length === 1) {
                    n = n.parentElement;
                }
                return n;
            }

            // Every row and success note in the dialog, with its acronym.
            function hideTargets(dialog) {
                var out = [];
                var rows = dialog.querySelectorAll(ROW_SELECTOR);
                for (var i = 0; i < rows.length; i++) {
                    var acr = rowAcronym(rows[i]);
                    if (acr) out.push([acr, ownWrapper(rows[i], dialog)]);
                }
                var alerts = dialog.querySelectorAll('[data-testid="stAlert"]');
                for (var j = 0; j < alerts.length; j++) {
                    var a = successAcronym(alerts[j].textContent || "");
                    if (a) out.push([a, ownWrapper(alerts[j], dialog)]);
                }
                return out;
            }

            function applyHidden(dialog) {
                var hidden = window.__maptologyHiddenAcronyms;
                var keep = [];
                var targets = hideTargets(dialog);
                for (var i = 0; i < targets.length; i++) {
                    if (hidden[targets[i][0]]) keep.push(targets[i][1]);
                }
                // A hidden node now showing a different row comes back.
                var marked = dialog.querySelectorAll("[data-maptology-hidden]");
                for (var j = 0; j < marked.length; j++) {
                    if (keep.indexOf(marked[j]) !== -1) continue;
                    marked[j].style.display = "";
                    marked[j].removeAttribute("data-maptology-hidden");
                }
                for (var k = 0; k < keep.length; k++) {
                    if (keep[k].hasAttribute("data-maptology-hidden")) continue;
                    keep[k].style.display = "none";
                    keep[k].setAttribute("data-maptology-hidden", "1");
                }
            }

            function scheduleHideSuccess() {
                var gen = ++window.__maptologySuccessGen;
                setTimeout(function () {
                    if (gen !== window.__maptologySuccessGen) return;
                    var dialog = document.querySelector('[data-testid="stDialog"]');
                    if (!dialog) return;
                    var alerts = dialog.querySelectorAll('[data-testid="stAlert"]');
                    for (var i = 0; i < alerts.length; i++) {
                        var acr = successAcronym(alerts[i].textContent || "");
                        if (acr) window.__maptologyHiddenAcronyms[acr] = true;
                    }
                    applyHidden(dialog);
                }, 3000);
            }

            document.addEventListener("pointerdown", function (event) {
                var el = event.target;
                if (!el || !el.closest) return;
                var button = el.closest("button");
                if (!button || downloadLabel(button) !== "Download") return;
                if (!dialogOf(button)) return;
                beginDownload(button);
            }, true);

            document.addEventListener("click", function (event) {
                var el = event.target;
                if (!el || !el.closest) return;
                var button = el.closest("button");
                if (!button || downloadLabel(button) !== "Download") return;
                if (!dialogOf(button)) return;
                beginDownload(button);
                setTimeout(function () { button.disabled = true; }, 0);
            }, true);

            document.addEventListener("keydown", function (event) {
                if (!window.__maptologyDownloadBusy) return;
                if (event.key !== "Escape") return;
                event.preventDefault();
                event.stopPropagation();
            }, true);

            new MutationObserver(function () {
                var dialog = document.querySelector('[data-testid="stDialog"]');
                if (!dialog) {
                    window.__maptologyHiddenAcronyms = {};
                    if (window.__maptologyDownloadBusy) endDownload();
                    return;
                }
                applyHidden(dialog);
                if (!window.__maptologyDownloadBusy) return;
                var acr = window.__maptologyDownloadAcronym;
                // An exception keeps the Downloading line on screen, because
                // the traceback quotes that line. The error itself is what
                // ends the lock. An error already visible before this click
                // does not.
                var failed = exceptionText() !== (window.__maptologyExceptionAtStart || "")
                    && exceptionText() !== "";
                if (failed) {
                    endDownload();
                    return;
                }
                // Read only the note under the clicked row. Errors under other
                // rows come and go as the list is redrawn.
                var note = rowNote(dialog, acr);
                if (note !== null) {
                    if (note.indexOf("Downloading ") === 0) {
                        window.__maptologyDownloadSaw = true;
                        // Once per download, so the list does not keep
                        // jumping back if the user scrolls away from it.
                        if (!window.__maptologyDownloadScrolled) {
                            window.__maptologyDownloadScrolled = true;
                            rowNoteAlert(dialog, acr).alert.scrollIntoView(
                                {block: "nearest", behavior: "smooth"});
                        }
                        return;
                    }
                    if (successAcronym(note) === acr) {
                        endDownload();
                        scheduleHideSuccess();
                        return;
                    }
                    // Any other note is an error. A retry of a row that already
                    // showed an error must wait for the new run, not the old note.
                    if (note && (window.__maptologyDownloadSaw
                                 || note !== window.__maptologyNoteAtStart)) {
                        endDownload();
                    }
                    return;
                }
                if (stillDownloading(dialog, acr)) {
                    window.__maptologyDownloadSaw = true;
                    return;
                }
                // The note can replace "Downloading" in one update, so this
                // ontology's own success note is enough to release the
                // buttons. An earlier ontology's note does not count.
                var finished = successShown(dialog, acr);
                if (finished || window.__maptologyDownloadSaw) {
                    endDownload();
                    if (finished) scheduleHideSuccess();
                }
            }).observe(document.body, {
                childList: true,
                subtree: true,
                // The page can turn the Downloading note into the error or
                // success note by changing only its text.
                characterData: true,
            });
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


@st.dialog("Download ontologies", width="large",
           on_dismiss=_dismiss_download_dialog)
def _download_ontologies_dialog():
    """Fetch ontologies from BioPortal, one at a time.

    Lists everything the saved catalogue offers that is not on this machine
    yet. Downloading lives here, in its own dialog, so the main page only
    ever deals with ontologies that are actually usable.
    """
    _arm_single_download_lock()
    st.markdown("These ontologies are on BioPortal but have not been downloaded to this machine yet. "
               "Most download in seconds; the largest may take a few minutes.")

    query = live_query(live_text_input("Search downloadable ontologies",
                                       placeholder="Type to filter...",
                                       key="download_dialog_filter"))
    already = _dialog_downloaded()
    candidates = [o for o in get_available_ontologies()
                  if not o.get("downloaded", False)
                  and o["acronym"] not in already]
    if query:
        q = query.lower()
        candidates = [o for o in candidates
                      if q in o["acronym"].lower() or q in o["name"].lower()]

    pending = _pending_downloads()
    pending_acronyms = {item[0] for item in pending}
    # A failed fetch is shown under that row on the redraw, with the rest of
    # the list still there.
    row_errors = st.session_state.setdefault("download_row_errors", {})

    # The full catalogue is hundreds of rows. Drawing every one makes each
    # Download or Done click wait on that whole list, so only one page is built.
    page_size = 25
    prev_filter = st.session_state.get("download_list_filter", "")
    if query != prev_filter:
        st.session_state.download_list_filter = query
        st.session_state.download_list_page = 0
    page = st.session_state.get("download_list_page", 0)
    page_count = max(1, (len(candidates) + page_size - 1) // page_size)
    page = min(max(page, 0), page_count - 1)
    st.session_state.download_list_page = page

    if not candidates and not row_errors:
        if query:
            st.info("No downloadable ontology matches '" + query + "'.")
        else:
            st.info("Every available ontology has already been downloaded.")
    else:
        if len(candidates) > page_size:
            prev_col, label_col, next_col = st.columns([1, 3, 1])
            with prev_col:
                st.button("Previous", key="download_page_prev",
                          disabled=page == 0,
                          on_click=_shift_download_page, args=(-1,))
            with next_col:
                # The list below is full width. Keep Next against that box's
                # right edge instead of the left side of this column.
                with st.container(horizontal=True, horizontal_alignment="right"):
                    st.button("Next", key="download_page_next",
                              disabled=page >= page_count - 1,
                              on_click=_shift_download_page, args=(1,))
            start = page * page_size
            window = candidates[start:start + page_size]
            with label_col:
                st.markdown("%d–%d of %d" % (start + 1, start + len(window),
                                            len(candidates)),
                            text_alignment="center")
        else:
            window = candidates

        placeholders = {}
        with st.container(height=380):
            for ont in window:
                acronym = ont["acronym"]
                queued = acronym in pending_acronyms
                # Keep every visible row in place. Skip descriptions during a
                # fetch so the Downloading note is not stuck behind them.
                # The button stays enabled in the page data. Graying it is
                # done in the browser, and that has to be reversible when the
                # fetch fails without rebuilding this list.
                _render_download_row(ont, show_info=not pending)
                slot = st.empty()
                placeholders[acronym] = slot
                if queued:
                    slot.info("Downloading " + acronym + " from BioPortal. This may take a few minutes...")
                elif acronym in row_errors:
                    slot.error(row_errors.pop(acronym))

        if pending:
            for acronym, name in list(pending):
                slot = placeholders.get(acronym)
                try:
                    ok, message = install_ontology(acronym)
                except Exception as e:
                    ok = False
                    message = ("%s could not be downloaded (%s)."
                               % (acronym, type(e).__name__))
                pending[:] = [item for item in pending if item[0] != acronym]
                if ok:
                    already.add(acronym)
                    _load_ontology_catalog.clear()
                    st.session_state.available_ontologies = []
                    # Same spot as the Downloading note. The browser removes
                    # this note, and the row with it, after three seconds.
                    # Rebuilding the list from the server is what was flashing
                    # the dialog twice.
                    if slot is not None:
                        slot.success(_success_download_message(name, acronym))
                else:
                    row_errors[acronym] = message
                    # Same spot as the Downloading note. Replacing it releases
                    # Download, Done, and the corner close button. A rerun
                    # here would rebuild the list and leave those locked.
                    if slot is not None:
                        slot.error(message)

    st.button("Done", key="download_dialog_done",
              on_click=_close_download_dialog)


@st.fragment
def _render_available_ontologies(available_ontologies):
    """List downloaded ontologies, filtered in the browser as the user types.

    The box does not submit on each character. Sending the query back to the
    server redraws every row, and that redraw was slow enough that the list
    only appeared to change after a few characters.
    """
    selected = st.session_state.selected_ontologies
    st.text_input(
        "Filter ontologies",
        placeholder="Type to filter available ontologies...",
        label_visibility="collapsed",
        key="ontology_filter")
    # The browser filter watches for this marker after a successful Select.
    # It focuses the box above only when that box already has text.
    token = st.session_state.pop("focus_ontology_filter", None)
    if token:
        st.html(
            '<div class="maptology-ont-filter-focus" data-token="%d" hidden></div>'
            % int(token),
            unsafe_allow_javascript=True)

    available = [o for o in available_ontologies
                 if o.get("downloaded", False) and o["acronym"] not in selected]

    at_limit = len(selected) >= MAX_SELECTED_ONTOLOGIES
    if at_limit:
        st.warning("Maximum of " + str(MAX_SELECTED_ONTOLOGIES) + " ontologies "
                   "selected. Remove one to add another.")

    if not available:
        st.markdown("Every downloaded ontology is already selected.")
    else:
        with st.container(height=350):
            # Inside the list, so a filter that matches nothing is noticed
            # there instead of under the box. The browser shows it.
            st.markdown(
                '<p class="maptology-ont-filter-empty"></p>',
                unsafe_allow_html=True)
            for ont in available:
                acronym = ont["acronym"]
                label = acronym + " - " + ont["name"]
                if ont.get("update_available"):
                    label += "  (update available)"
                # Button next to the name, packed left, so a wide screen
                # leaves the empty space on the right, not between them.
                with st.container(horizontal=True, vertical_alignment="center",
                                  key="ont_name_av_" + acronym):
                    clicked = st.button("Select", key="add_" + acronym,
                                        disabled=at_limit)
                    st.markdown(label)
                    # A button that opens a dialog reruns the whole script,
                    # and with a long list that rerun is slow. A popover
                    # opens without a rerun. CSS hides its chevron so it
                    # still reads as the same icon button.
                    with st.popover("ℹ️", type="tertiary"):
                        _render_ontology_details(ont)
                if clicked:
                    # An ontology whose BioPortal submission has moved on is
                    # refreshed at the moment it is chosen for use.
                    if ont.get("update_available"):
                        with st.spinner("Updating " + acronym + " from "
                                        "BioPortal... large ontologies can "
                                        "take a few minutes."):
                            ok, message = install_ontology(acronym)
                        if not ok:
                            st.session_state.ontology_install_error = message
                            st.rerun()
                        _load_ontology_catalog.clear()
                        st.session_state.available_ontologies = []
                    st.session_state.selected_ontologies.append(acronym)
                    st.session_state.ontologies_changed = True
                    seq = st.session_state.get("ontology_filter_focus_seq", 0) + 1
                    st.session_state.ontology_filter_focus_seq = seq
                    st.session_state.focus_ontology_filter = seq
                    st.rerun()


# Render ontology selection. A statement explains what to do; while nothing is
# downloaded, the Available section is hidden and only the Download dialog is
# offered. Once ontologies are on disk they appear under Available, each with a
# Select button; chosen ones move to Selected, each with a Remove button.
def render_ontology_selection(available_ontologies):
    # st.markdown('<div class="section-header section-purple">Select Ontologies</div>', unsafe_allow_html=True)

    # A download attempted on the previous rerun may have failed; the message
    # has to survive that rerun, so it travels through session state.
    install_error = st.session_state.pop("ontology_install_error", None)
    if install_error:
        st.error(install_error)

    selected = st.session_state.selected_ontologies

    # What is on disk decides both the wording below and which sections show.
    n_downloaded = sum(1 for o in available_ontologies if o.get("downloaded", False))
    total = len(available_ontologies)
    # "Everything is here" when the whole catalogue is downloaded, or on a
    # download-everything install where it is already on its way.
    all_downloaded = download_all_requested() or (total > 0 and n_downloaded >= total)

    statement = ("Before you can annotate your data, you must specify one or "
                 "more ontologies to use.")
    if all_downloaded:
        pass  # nothing left to download, so no extra guidance
    elif n_downloaded == 0:
        statement += (" Hundreds of ontologies are available on BioPortal. "
                      "However, to use these, you must first download them. To "
                      "do so, click on the \"Download ontologies\" button below.")
    else:
        statement += (" Hundreds of ontologies are available on BioPortal. The "
                      "ontologies you have downloaded are shown below. If you "
                      "would like to download more, click on the \"Download "
                      "ontologies\" button below.")
    st.markdown(statement)

    # The Download button is offered until everything is downloaded. Rendered on
    # its own so it sits left-aligned at the start of the line.
    if not all_downloaded:
        if st.button("Download ontologies", key="open_download_dialog"):
            st.session_state.show_download_dialog = True
        # Reopened after a download finishes, so the list behind the dialog
        # already includes the ontology that was just fetched.
        if st.session_state.get("show_download_dialog"):
            _download_ontologies_dialog()

    # Available ontologies stay hidden until at least one has been downloaded.
    if n_downloaded > 0:
        # st.markdown('<div class="sub-heading">Available ontologies</div>',
        #             unsafe_allow_html=True)
        st.markdown("The following ontologies have been downloaded. Select any "
                   "that you wish to use when annotating your data.")
        _render_available_ontologies(available_ontologies)

    # Selected ontologies appear only once at least one has been chosen.
    if selected:
        st.markdown('<div class="sub-heading">Selected ontologies ('
                    + str(len(selected)) + '/' + str(MAX_SELECTED_ONTOLOGIES)
                    + ')</div>', unsafe_allow_html=True)
        names = {o["acronym"]: o["name"] for o in available_ontologies}
        for acronym in list(selected):
            # Remove on the left, next to the name, matching the Available list.
            with st.container(horizontal=True, vertical_alignment="center",
                              key="ont_name_sel_" + acronym):
                clicked = st.button("Remove", key="remove_" + acronym)
                st.markdown(acronym + " - " + names.get(acronym, acronym))
            if clicked:
                st.session_state.selected_ontologies.remove(acronym)
                st.session_state.ontologies_changed = True
                st.rerun()

    # When the selected ontologies change, previous manual search results may be
    # from ontologies that are no longer selected - clear them so stale results
    # don't linger (e.g. NCIT results still showing after NCIT was deselected).
    if st.session_state.ontologies_changed:
        st.session_state.manual_column_search_results = None
        st.session_state.manual_value_search_results = None
        st.session_state.manual_column_search_query = ""
        st.session_state.manual_value_search_query = ""

    # Automatically execute search if ontology changed and column is selected
    if st.session_state.ontologies_changed and st.session_state.selected_column and st.session_state.selected_ontologies:
        search_ontology(st.session_state.selected_column)

        # Also perform automatic search for value mapping
        if st.session_state.selected_unique_value:
            search_ontology_for_value(st.session_state.selected_unique_value)

        # Reset flag
        st.session_state.ontologies_changed = False