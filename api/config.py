"""Shared configuration for the Maptology API and its manifest generator.

Paths resolve against the repo root so scripts work from any CWD. The dist
directory (generated manifest + zips) is overridable via ``MAPTOLOGY_DIST_DIR``
so tests and deployments can point it elsewhere.
"""

import os
import re

MANIFEST_VERSION = 1
CACHE_FORMAT_VERSION = 1

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TFIDF_CACHE_DIR = os.path.join(_REPO_ROOT, "tfidf_cache")
ONTOLOGY_LIST_TSV = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_list.tsv")
VERSIONS_JSON = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_versions.json")
POLICY_TSV = os.path.join(_REPO_ROOT, "ontology_distribution_policy.tsv")

CACHE_FILE_SUFFIXES = (
    "_tfidf_matrix.npz",
    "_vectorizer.pkl",
    "_terms.ormsgpack",
)

# Served zip filenames are content-addressed: "<ACRONYM>-<build_id>.zip". This
# pattern is a defence-in-depth guard against path separators; the real
# authorization is manifest membership (see api/main.py).
ZIP_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.zip$")


def dist_dir():
    """Directory holding the generated manifest.json and cache zips."""
    return os.environ.get("MAPTOLOGY_DIST_DIR",
                          os.path.join(_REPO_ROOT, "dist"))


def manifest_path():
    return os.path.join(dist_dir(), "manifest.json")


def cache_zip_dir():
    return os.path.join(dist_dir(), "cache")
