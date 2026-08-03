import os
import sys
import threading
import time

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


def test_a_changed_ontology_is_downloaded_again(monkeypatch, tmp_path):
    """The whole point of noticing a new submission is to go and get it.

    Reusing the file already on disk would index the old ontology and then
    record the new submission against it, freezing it at that version forever.
    """
    _patch(monkeypatch, tmp_path, built={"BBB"}, owl_present=["BBB"])
    local = {"BBB": {"submissionId": 8}}          # BioPortal now offers 9
    ont = _catalogue()[1]
    assert setup.needs_download(ont, local) is True


def test_an_unchanged_file_on_disk_is_reused(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built={"BBB"}, owl_present=["BBB"])
    local = {"BBB": {"submissionId": 9}}
    assert setup.needs_download(_catalogue()[1], local) is False


def test_a_missing_file_is_downloaded(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, built={"BBB"}, owl_present=[])
    local = {"BBB": {"submissionId": 9}}
    assert setup.needs_download(_catalogue()[1], local) is True


def test_a_current_file_is_not_refetched_to_rebuild_its_index(monkeypatch, tmp_path):
    """An index can be rebuilt from bytes that are already correct."""
    _patch(monkeypatch, tmp_path, built=set(), owl_present=["BBB"])
    local = {"BBB": {"submissionId": 9}}
    assert setup.needs_download(_catalogue()[1], local) is False


def test_an_ontology_we_never_recorded_is_downloaded(monkeypatch, tmp_path):
    """A file with no recorded submission cannot be shown to match the catalogue."""
    _patch(monkeypatch, tmp_path, built={"BBB"}, owl_present=["BBB"])
    assert setup.needs_download(_catalogue()[1], {}) is True


def _run_recording_downloads(monkeypatch, tmp_path, local):
    """Run the real pipeline against stubs, returning what it downloaded."""
    downloaded = []
    saved = {}

    monkeypatch.setattr(setup, "OWL_DIR", str(tmp_path))
    monkeypatch.setattr(setup, "TSV_FILE", str(tmp_path / "ontology_list.tsv"))
    monkeypatch.setattr(setup, "FAILURES_FILE", str(tmp_path / "build_failures.json"))
    monkeypatch.setattr(setup, "fetch_catalogue", lambda key, only=None: _catalogue())
    monkeypatch.setattr(setup.versions, "load_local_versions", lambda: dict(local))
    monkeypatch.setattr(setup.versions, "save_local_versions", saved.update)
    monkeypatch.setattr(setup.builder, "is_cache_built", lambda a: True)
    monkeypatch.setattr(setup, "_index", lambda a: 1)

    def fake_download(ont, api_key):
        downloaded.append(ont["acronym"])
        (tmp_path / (ont["acronym"] + ".owl")).write_bytes(b"fresh")
        return 0.1

    monkeypatch.setattr(setup, "download_one", fake_download)
    setup.run("key")
    return downloaded, saved


def test_run_fetches_a_changed_ontology_rather_than_indexing_stale_bytes(
        monkeypatch, tmp_path):
    """The bug this test exists for.

    plan() classified BBB as "fetch", but the executor only queued a download
    when the OWL file was absent. BBB's old file was indexed and then recorded
    at submission 9, so every later run saw it as up to date.
    """
    for acr in ("AAA", "BBB"):
        (tmp_path / (acr + ".owl")).write_bytes(b"stale")
    local = {"AAA": {"submissionId": 5}, "BBB": {"submissionId": 8}}

    downloaded, saved = _run_recording_downloads(monkeypatch, tmp_path, local)

    assert downloaded == ["BBB"], "the changed ontology has to be fetched again"
    assert (tmp_path / "BBB.owl").read_bytes() == b"fresh"
    assert saved["BBB"]["submissionId"] == 9


def test_run_leaves_up_to_date_ontologies_alone(monkeypatch, tmp_path):
    for acr in ("AAA", "BBB"):
        (tmp_path / (acr + ".owl")).write_bytes(b"current")
    local = {"AAA": {"submissionId": 5}, "BBB": {"submissionId": 9}}

    downloaded, _ = _run_recording_downloads(monkeypatch, tmp_path, local)

    assert downloaded == []


def test_requests_are_spaced_out_across_download_threads(monkeypatch):
    """BioPortal allows 15 requests a second per key; four threads can beat that.

    Several connections each start a request the moment their last file lands,
    so the gap has to be enforced on the requests themselves rather than
    inferred from how many connections are open.
    """
    monkeypatch.setattr(setup, "REQUEST_INTERVAL", 0.05)
    monkeypatch.setattr(setup, "_next_request_at", 0.0)
    stamps, lock = [], threading.Lock()

    def hit():
        setup._rate_limit()
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=hit) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stamps.sort()
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert len(gaps) == 5
    assert min(gaps) >= 0.04, "requests went out closer together than the limit"


def _fake_ok_response(body=b"<rdf/>"):
    class Resp:
        status_code = 200
        headers = {"Content-Length": str(len(body))}

        def iter_content(self, chunk_size=1):
            yield body
    return Resp()


def test_download_one_takes_a_rate_limit_slot(monkeypatch, tmp_path):
    """A limit that nothing calls is documentation, not a limit."""
    monkeypatch.setattr(setup, "OWL_DIR", str(tmp_path))
    taken = []
    monkeypatch.setattr(setup, "_rate_limit", lambda: taken.append(1))
    monkeypatch.setattr(setup.requests, "get",
                        lambda *a, **k: _fake_ok_response())

    setup.download_one({"acronym": "AAA", "native_format": "OWL"}, "key")

    assert taken == [1], "the download went out without waiting for a slot"


def _slot_free(monkeypatch, tmp_path, name, size_bytes):
    """How many heavy slots remain while this ontology is being built."""
    monkeypatch.setattr(setup, "OWL_DIR", str(tmp_path))
    monkeypatch.setattr(setup, "HEAVY_MB", 1)
    monkeypatch.setattr(setup, "_heavy_slots", threading.Semaphore(2))
    (tmp_path / (name + ".owl")).write_bytes(b"x" * size_bytes)
    with setup._build_slot(name):
        inside = setup._heavy_slots._value
    return inside, setup._heavy_slots._value


def test_a_large_ontology_holds_a_heavy_slot(monkeypatch, tmp_path):
    """Memory, not cores, is the limit: one worker was measured at 2.7 GB.

    Six of those at once needs more than the 15.4 GB the machine has, so the
    large ontologies share a small allowance of their own.
    """
    inside, after = _slot_free(monkeypatch, tmp_path, "BIG", 2_000_000)
    assert inside == 1, "a large ontology should occupy one of the two slots"
    assert after == 2, "the slot should be given back when the build ends"


def test_a_small_ontology_does_not_hold_one(monkeypatch, tmp_path):
    inside, after = _slot_free(monkeypatch, tmp_path, "SMALL", 1000)
    assert inside == 2 and after == 2


def test_the_slot_is_released_even_when_the_build_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "OWL_DIR", str(tmp_path))
    monkeypatch.setattr(setup, "HEAVY_MB", 1)
    monkeypatch.setattr(setup, "_heavy_slots", threading.Semaphore(2))
    (tmp_path / "BIG.owl").write_bytes(b"x" * 2_000_000)
    try:
        with setup._build_slot("BIG"):
            raise RuntimeError("build blew up")
    except RuntimeError:
        pass
    assert setup._heavy_slots._value == 2
