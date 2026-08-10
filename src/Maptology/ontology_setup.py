"""Decide, at startup, how ontologies reach this machine.

Two modes, chosen by one environment variable:

  MAPTOLOGY_DOWNLOAD_ALL set (yes/true/1)
      Download and index every ontology BioPortal offers before the UI opens -
      hours of work, meant for a server install where nobody is watching.

  unset (the default)
      Lazy loading. The app opens immediately; an ontology is downloaded and
      indexed the first time someone selects it, which takes seconds for most
      and a couple of minutes for the largest. Most people use five or ten
      ontologies, so downloading a thousand up front helps nobody.

Either way, BioPortal is asked what exists at most once every 30 days; between
checks the saved catalogue answers instead. An environment variable rather
than a config file or a prompt because there is exactly one thing to say, and
a Docker container cannot stop to ask questions.

@st.cache_resource keeps the startup work to once per server process -
Streamlit reruns the whole script on every click.
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


def _setup_module():
    """The build-side updater, or None when it cannot be imported. A broken
    import must never stop the app from opening with what it already has."""
    if _BUILD_DIR not in sys.path:
        sys.path.insert(0, _BUILD_DIR)
    try:
        import setup_ontologies
        return setup_ontologies
    except Exception as e:
        print("Could not load the ontology updater (%s: %s)."
              % (type(e).__name__, e), flush=True)
        return None


def _api_key():
    return os.environ.get("BIOPORTAL_APIKEY", "").strip()


def _download_all_requested():
    return os.environ.get("MAPTOLOGY_DOWNLOAD_ALL", "").strip().lower() \
        in ("1", "true", "yes", "y")


def _print_no_key_notice(have):
    print("BIOPORTAL_APIKEY is not set, so nothing new can be downloaded.")
    print("Maptology will run with the %d ontologies already on this machine." % have)
    if have == 0:
        print("")
        print("There are none yet, so there is nothing to search. Get a free key")
        print("at https://bioportal.bioontology.org/accounts, then set it:")
        print("   Windows PowerShell:  $env:BIOPORTAL_APIKEY = \"your-key\"")
        print("   macOS / Linux:       export BIOPORTAL_APIKEY=your-key")
        print("and start Maptology again.")


@st.cache_resource(show_spinner=False)
def ensure_ontologies():
    """Run the startup mode chosen by MAPTOLOGY_DOWNLOAD_ALL. Returns a short
    status string. Cached for the life of the server process."""
    if os.environ.get("MAPTOLOGY_SKIP_SETUP", "").strip():
        return "skipped (MAPTOLOGY_SKIP_SETUP is set); using %d cached ontologies" \
            % _cache_count()

    if _download_all_requested():
        return _download_everything()
    return _prepare_lazy()


def _download_everything():
    """The server path: fetch and index the whole corpus before opening."""
    api_key = _api_key()
    print("\n" + "=" * 70)
    print("MAPTOLOGY_DOWNLOAD_ALL is set: downloading and indexing every")
    print("ontology before the app opens. This takes a few hours the first")
    print("time; later starts only fetch what changed on BioPortal.")
    print("=" * 70, flush=True)

    if not api_key:
        have = _cache_count()
        _print_no_key_notice(have)
        print("", flush=True)
        return "download-all requested but no API key; using %d cached ontologies" % have

    setup = _setup_module()
    if setup is None:
        return "updater unavailable; using %d cached ontologies" % _cache_count()

    try:
        done, failed = setup.run(api_key)
    except KeyboardInterrupt:
        print("\nSetup interrupted; starting with whatever finished.", flush=True)
        return "interrupted; using %d cached ontologies" % _cache_count()
    except Exception as e:
        print("Ontology update failed (%s: %s); starting with the existing "
              "caches." % (type(e).__name__, e), flush=True)
        return "update failed; using %d cached ontologies" % _cache_count()

    print("Opening Maptology.\n", flush=True)
    if done or failed:
        return "updated %d ontologies (%d failed); %d ready" % (
            done, failed, _cache_count())
    return "already up to date; %d ontologies ready" % _cache_count()


def _prepare_lazy():
    """The default path: open at once, download per selection.

    The only startup cost is refreshing the saved BioPortal catalogue when it
    is more than 30 days old - one request, about a second - so the selection
    list can offer ontologies that are not downloaded yet.
    """
    have = _cache_count()
    print("\n" + "=" * 70)
    print("Maptology downloads an ontology from BioPortal the first time you")
    print("select it in the app - a few seconds for most, a couple of minutes")
    print("for the largest. %d are already on this machine." % have)
    print("")
    print("To download and index everything up front instead (~1,000")
    print("ontologies, 15 GB, roughly 2-3 hours), set an environment variable")
    print("and restart:")
    print("   Windows PowerShell:  $env:MAPTOLOGY_DOWNLOAD_ALL = \"yes\"")
    print("   macOS / Linux:       export MAPTOLOGY_DOWNLOAD_ALL=yes")
    print("")
    print("Ontologies you already have are checked for new versions at most")
    print("once every 30 days.")
    print("=" * 70, flush=True)

    api_key = _api_key()
    if not api_key:
        _print_no_key_notice(have)
        print("", flush=True)
        return "lazy loading; no API key; %d ontologies available" % have

    setup = _setup_module()
    if setup is None:
        return "lazy loading; updater unavailable; %d ontologies available" % have

    try:
        catalogue = setup.get_catalogue(api_key)
        print("BioPortal offers %d ontologies; they appear in the selection "
              "list below.\n" % len(catalogue), flush=True)
    except Exception as e:
        print("Could not reach BioPortal (%s: %s); the selection list shows "
              "only what is already downloaded.\n" % (type(e).__name__, e),
              flush=True)
        return "lazy loading; catalogue unavailable; %d ontologies available" % have

    return "lazy loading; %d downloaded of %d available" % (have, len(catalogue))


# ---------------------------------------------------------------------------
# Helpers for the selection UI (lazy mode).
# ---------------------------------------------------------------------------

def catalogue_entries():
    """The saved BioPortal catalogue, keyed by acronym. Empty when it has
    never been fetched - the selection list then shows only local caches."""
    setup = _setup_module()
    if setup is None:
        return {}
    catalogue = setup.load_saved_catalogue()
    if not catalogue:
        return {}
    return {o["acronym"]: o for o in catalogue}


def recorded_submissions():
    """acronym -> submissionId the local index was built from."""
    setup = _setup_module()
    if setup is None:
        return {}
    try:
        local = setup.versions.load_local_versions()
    except Exception:
        return {}
    return {acr: (info or {}).get("submissionId") for acr, info in local.items()}


def install_ontology(acronym):
    """Download and index one ontology right now. Returns (ok, message).

    Called from the selection list when someone picks an ontology that is not
    on disk yet, or whose BioPortal submission has moved on.
    """
    api_key = _api_key()
    if not api_key:
        return False, ("BIOPORTAL_APIKEY is not set. Get a free key at "
                       "https://bioportal.bioontology.org/accounts, set the "
                       "environment variable, and restart Maptology.")
    setup = _setup_module()
    if setup is None:
        return False, "The ontology updater could not be loaded."
    entry = catalogue_entries().get(acronym)
    if entry is None:
        return False, ("%s is not in the saved BioPortal catalogue; it cannot "
                       "be downloaded." % acronym)
    try:
        n = setup.setup_one(entry, api_key)
    except Exception as e:
        return False, ("%s could not be downloaded and indexed (%s: %s)."
                       % (acronym, type(e).__name__, str(e)[:120]))
    return True, "%s is ready: %d terms indexed." % (acronym, n)
