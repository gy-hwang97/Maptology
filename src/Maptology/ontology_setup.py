"""Bring the ontology caches up to date before the app renders.

Maptology searches locally, so the indexes have to exist before anything can be
mapped. This runs the same work as `python build/setup_ontologies.py` when the
app starts: ask BioPortal what changed, download and index only that, then let
the UI open.

Two things make this safe to call from a Streamlit script:

  * @st.cache_resource means it runs ONCE per server process. Streamlit reruns
    the whole script on every click, and a version check costs ~900 API calls,
    so running it per rerun would make the app unusable.
  * It never blocks someone who already has caches. With no API key, or with
    MAPTOLOGY_SKIP_SETUP set, it reports and returns instead of prompting.

Progress goes to the terminal, which is where the professor asked for it; the
browser simply opens once this returns.
"""

import os
import sys

import streamlit as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BUILD_DIR = os.path.join(_REPO_ROOT, "build")


def _cache_count():
    cache_dir = os.path.join(_REPO_ROOT, "tfidf_cache")
    if not os.path.isdir(cache_dir):
        return 0
    return sum(1 for d in os.listdir(cache_dir)
               if not d.endswith(".bak")
               and os.path.isdir(os.path.join(cache_dir, d)))


@st.cache_resource(show_spinner=False)
def ensure_ontologies():
    """Update the local ontology caches. Returns a short status string.

    Cached for the life of the server process, so it happens on startup and not
    on every rerun.
    """
    if os.environ.get("MAPTOLOGY_SKIP_SETUP", "").strip():
        return "skipped (MAPTOLOGY_SKIP_SETUP is set); using %d cached ontologies" \
            % _cache_count()

    api_key = os.environ.get("BIOPORTAL_APIKEY", "").strip()
    if not api_key:
        have = _cache_count()
        print("\n" + "=" * 70)
        print("BIOPORTAL_APIKEY is not set, so ontologies cannot be downloaded or")
        print("updated. Maptology will run with the %d ontologies already cached." % have)
        if have == 0:
            print("")
            print("There are none yet, so there is nothing to search. Get a free key")
            print("at https://bioportal.bioontology.org/accounts, then set it:")
            print("   Windows PowerShell:  $env:BIOPORTAL_APIKEY = \"your-key\"")
            print("   macOS / Linux:       export BIOPORTAL_APIKEY=your-key")
            print("and start Maptology again.")
        print("=" * 70 + "\n", flush=True)
        return "no API key; using %d cached ontologies" % have

    if _BUILD_DIR not in sys.path:
        sys.path.insert(0, _BUILD_DIR)
    try:
        import setup_ontologies
    except Exception as e:                     # a broken import must not stop the app
        print("Could not load the ontology updater (%s: %s); starting with the "
              "existing caches." % (type(e).__name__, e), flush=True)
        return "updater unavailable; using %d cached ontologies" % _cache_count()

    print("\n" + "=" * 70)
    print("Checking BioPortal for ontology updates before Maptology opens.")
    print("The first run downloads a lot and takes a while; later runs only")
    print("fetch what changed. Progress appears below.")
    print("=" * 70, flush=True)
    try:
        done, failed = setup_ontologies.run(api_key)
    except KeyboardInterrupt:
        print("\nSetup interrupted; starting with whatever finished.", flush=True)
        return "interrupted; using %d cached ontologies" % _cache_count()
    except Exception as e:
        # Never let a download problem stop someone from using what they have.
        print("Ontology update failed (%s: %s); starting with the existing "
              "caches." % (type(e).__name__, e), flush=True)
        return "update failed; using %d cached ontologies" % _cache_count()

    print("Opening Maptology.\n", flush=True)
    if done or failed:
        return "updated %d ontologies (%d failed); %d ready" % (
            done, failed, _cache_count())
    return "already up to date; %d ontologies ready" % _cache_count()
