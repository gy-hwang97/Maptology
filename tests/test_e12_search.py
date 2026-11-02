"""Checks for the app's E12 cache lifecycle and public search interface."""

import os
import sys
from pathlib import Path

import ormsgpack
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "Maptology"))

import e12_search  # noqa: E402
import tfidf_search  # noqa: E402


@pytest.fixture
def installed_terms(tmp_path, monkeypatch):
    source_root = tmp_path / "tfidf_cache"
    monkeypatch.setattr(e12_search, "_SOURCE_ROOT", source_root)
    monkeypatch.setattr(e12_search, "_INDEX_ROOT", tmp_path / "tfidf_cache_e12")
    e12_search.clear_loaded()

    def write(acronym, terms):
        folder = source_root / acronym
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (acronym + "_terms.ormsgpack")
        path.write_bytes(ormsgpack.packb(terms))
        return path

    yield write
    e12_search.clear_loaded()


def test_exact_synonym_and_batch_duplicates(installed_terms):
    installed_terms("SAMPLE", [
        {"label": "Fatigue Severity Scale", "iri": "urn:fss",
         "synonyms": ["FSS"], "definition": "A scale"},
        {"label": "Fentanyl Sublingual Spray", "iri": "urn:spray",
         "synonyms": ["FSS"], "definition": "A medication"},
        {"label": "FSS questionnaire item", "iri": "urn:item",
         "synonyms": [], "definition": "An item"},
    ])

    results = tfidf_search.search_many(["FSS", "FSS", "  "], ["SAMPLE"], top_n=3)
    assert results[2] is None
    assert results[0]["Ontology Term URI"].tolist()[:2] == ["urn:fss", "urn:spray"]
    assert tfidf_search.get_term_by_iri("SAMPLE", "urn:fss")["label"] == "Fatigue Severity Scale"
    assert results[0]["Ontology Term URI"].tolist() == results[1]["Ontology Term URI"].tolist()
    results[0].at[0, "Preferred Label"] = "edited"
    assert results[1].at[0, "Preferred Label"] == "Fatigue Severity Scale"


def test_ontology_update_builds_a_new_index(installed_terms):
    path = installed_terms("CHANGING", [
        {"label": "old label", "iri": "urn:old", "synonyms": []},
    ])
    first = e12_search.load_index("CHANGING")
    assert first["terms"][0]["iri"] == "urn:old"

    path.write_bytes(ormsgpack.packb([
        {"label": "new label", "iri": "urn:new", "synonyms": []},
    ]))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    second = e12_search.load_index("CHANGING")
    assert second["terms"][0]["iri"] == "urn:new"
    assert second is not first
    assert len(list((e12_search._INDEX_ROOT / "CHANGING").iterdir())) == 2
    e12_search.unload("CHANGING")
    assert "CHANGING" not in e12_search._loaded


def test_unknown_ontology_and_invalid_limits(installed_terms):
    assert tfidf_search.search_local("asthma", ["NOT_INSTALLED"]) is None
    with pytest.raises(ValueError):
        e12_search.search_many("NOT_INSTALLED", ["asthma"], top_n=0)
