import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build"))

import setup_ontologies as setup


def _catalogue():
    return [
        {"acronym": "AAA", "name": "A", "native_format": "OWL", "submissionId": 5},
        {"acronym": "BBB", "name": "B", "native_format": "OWL", "submissionId": 9},
    ]


def _patch(monkeypatch, tmp_path, built, owl_present):
    monkeypatch.setattr(setup, "OWL_DIR", str(tmp_path))
    monkeypatch.setattr(setup.builder, "is_cache_built", lambda a: a in built)
    for acr in owl_present:
        (tmp_path / (acr + ".owl")).write_bytes(b"x")


def _actions(plan):
    return {ont["acronym"]: (action, why) for ont, action, why in plan}


def test_never_built_is_fetched(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built=set(), owl_present=[])
    got = _actions(setup.plan(_catalogue(), {}))
    assert got["AAA"][0] == "fetch"
    assert got["BBB"][0] == "fetch"


def test_up_to_date_is_skipped(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built={"AAA", "BBB"}, owl_present=["AAA", "BBB"])
    local = {"AAA": {"submissionId": 5}, "BBB": {"submissionId": 9}}
    got = _actions(setup.plan(_catalogue(), local))
    assert got["AAA"][0] == "skip"
    assert got["BBB"][0] == "skip"


def test_new_submission_is_refetched(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built={"AAA", "BBB"}, owl_present=["AAA", "BBB"])
    # BBB moved on from submission 8 to 9
    local = {"AAA": {"submissionId": 5}, "BBB": {"submissionId": 8}}
    got = _actions(setup.plan(_catalogue(), local))
    assert got["AAA"][0] == "skip"
    assert got["BBB"][0] == "fetch"
    assert "8" in got["BBB"][1] and "9" in got["BBB"][1]


def test_missing_owl_is_refetched(monkeypatch, tmp_path):
    # The index exists but the source file was deleted; rebuilding needs it back.
    _patch(monkeypatch, tmp_path, built={"AAA", "BBB"}, owl_present=["AAA"])
    local = {"AAA": {"submissionId": 5}, "BBB": {"submissionId": 9}}
    got = _actions(setup.plan(_catalogue(), local))
    assert got["AAA"][0] == "skip"
    assert got["BBB"][0] == "fetch"
    assert "owl missing" in got["BBB"][1]


def test_unrecorded_version_is_refetched(monkeypatch, tmp_path):
    # A cache with no recorded submission cannot be shown to be current.
    _patch(monkeypatch, tmp_path, built={"AAA"}, owl_present=["AAA"])
    got = _actions(setup.plan(_catalogue(), {}))
    assert got["AAA"][0] == "fetch"


def test_only_filter_limits_the_plan(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built=set(), owl_present=[])
    got = _actions(setup.plan(_catalogue(), {}, only={"BBB"}))
    assert set(got) == {"BBB"}


def test_catalogue_tsv_lists_only_files_on_disk(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built=set(), owl_present=["AAA"])
    monkeypatch.setattr(setup, "TSV_FILE", str(tmp_path / "ontology_list.tsv"))
    n = setup.write_catalogue_tsv(_catalogue())
    assert n == 1
    body = open(str(tmp_path / "ontology_list.tsv"), encoding="utf-8").read()
    assert "AAA" in body
    # BBB has no OWL file, so listing it would offer the app something it
    # cannot open.
    assert "BBB" not in body


def test_ontology_withdrawn_from_bioportal_is_kept(monkeypatch, tmp_path):
    # CMEO, CVO and HTO are downloaded, built and usable, but BioPortal no
    # longer lists them. Dropping them would take working ontologies away from
    # the user for no benefit.
    _patch(monkeypatch, tmp_path, built=set(), owl_present=["AAA", "GONE"])
    tsv = tmp_path / "ontology_list.tsv"
    tsv.write_text(
        "name\tfile_path\tabbreviation\tnative_format\tdownload_format\n"
        "Withdrawn Ontology\told/path.owl\tGONE\tOWL\tOWL\n",
        encoding="utf-8")
    monkeypatch.setattr(setup, "TSV_FILE", str(tsv))

    n = setup.write_catalogue_tsv(_catalogue())   # catalogue has AAA and BBB only

    body = tsv.read_text(encoding="utf-8")
    assert n == 2
    assert "GONE" in body and "Withdrawn Ontology" in body
    assert "AAA" in body


def test_withdrawn_entry_without_its_file_is_dropped(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built=set(), owl_present=["AAA"])
    tsv = tmp_path / "ontology_list.tsv"
    tsv.write_text(
        "name\tfile_path\tabbreviation\tnative_format\tdownload_format\n"
        "Deleted Ontology\told/path.owl\tGONE\tOWL\tOWL\n",
        encoding="utf-8")
    monkeypatch.setattr(setup, "TSV_FILE", str(tsv))

    n = setup.write_catalogue_tsv(_catalogue())

    assert n == 1
    assert "GONE" not in tsv.read_text(encoding="utf-8")
