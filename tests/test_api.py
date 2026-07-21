import hashlib
import importlib
import os

import pytest
from fastapi.testclient import TestClient

from build import generate_manifest as gm


def _make_cache(tfidf_dir, acronym, payload=b"data"):
    folder = os.path.join(tfidf_dir, acronym)
    os.makedirs(folder, exist_ok=True)
    for suffix in ("_tfidf_matrix.npz", "_vectorizer.pkl", "_terms.ormsgpack"):
        with open(os.path.join(folder, acronym + suffix), "wb") as fh:
            fh.write(acronym.encode() + suffix.encode() + payload)


def _catalog_tsv(tmp_path, acronyms):
    p = tmp_path / "ontology_list.tsv"
    lines = ["name\tfile_path\tabbreviation\tnative_format\tdownload_format"]
    for a in acronyms:
        lines.append(a + " Name\tx.owl\t" + a + "\tOWL\tOWL")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _policy_tsv(tmp_path, rows):
    p = tmp_path / "policy.tsv"
    lines = ["acronym\tdelivery_mode"]
    for acronym, mode in rows:
        lines.append(acronym + "\t" + mode)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _client_for(tmp_path, monkeypatch, policy_rows):
    tfidf = tmp_path / "tfidf_cache"
    for acronym in ("EFO", "ABC"):
        _make_cache(str(tfidf), acronym)
    dist = tmp_path / "dist"
    gm.generate(
        list_tsv=_catalog_tsv(tmp_path, ["EFO", "ABC"]),
        tfidf_dir=str(tfidf),
        versions_json=str(tmp_path / "missing.json"),
        policy_tsv=_policy_tsv(tmp_path, policy_rows),
        out_dir=str(dist),
    )
    monkeypatch.setenv("MAPTOLOGY_DIST_DIR", str(dist))
    from api import config, main
    importlib.reload(config)
    importlib.reload(main)
    return TestClient(main.app), str(dist)


@pytest.fixture
def client(tmp_path, monkeypatch):
    c, _ = _client_for(
        tmp_path, monkeypatch,
        [("EFO", "maptology_server"), ("ABC", "bioportal_user")],
    )
    return c


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "ok"
    assert b["manifest_version"] == 1
    assert b["cache_format_version"] == 1


def test_manifest_lists_ontologies(client):
    r = client.get("/v1/manifest")
    assert r.status_code == 200
    by = {o["acronym"]: o for o in r.json()["ontologies"]}
    assert by["EFO"]["delivery_mode"] == "maptology_server"
    assert by["ABC"]["delivery_mode"] == "bioportal_user"


def test_cache_zip_served_bytes_match_manifest(client):
    manifest = client.get("/v1/manifest").json()
    efo = next(o for o in manifest["ontologies"] if o["acronym"] == "EFO")
    filename = efo["download_url"].rsplit("/", 1)[-1]
    r = client.get("/v1/cache/" + filename)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert hashlib.sha256(r.content).hexdigest() == efo["sha256"]


def test_cache_zip_404_for_non_served(client):
    # ABC is bioportal_user -> no zip is referenced by the manifest
    assert client.get("/v1/cache/ABC-000000000000.zip").status_code == 404


def test_cache_zip_404_for_unknown(client):
    assert client.get("/v1/cache/NOPE-000000000000.zip").status_code == 404


def test_cache_zip_rejects_path_traversal(client):
    assert client.get("/v1/cache/..%2F..%2Fetc%2Fpasswd.zip").status_code == 404


def test_existing_but_unreferenced_zip_is_not_served(client):
    # A zip that exists on disk but is NOT in the manifest must not be served.
    # This is the stale-zip guard: existence != permission to serve.
    from api import config
    rogue = os.path.join(config.cache_zip_dir(), "ROGUE-deadbeef0000.zip")
    with open(rogue, "wb") as fh:
        fh.write(b"PK\x03\x04 not a real cache")
    assert client.get("/v1/cache/ROGUE-deadbeef0000.zip").status_code == 404


def test_reclassified_ontology_stops_serving(tmp_path, monkeypatch):
    c, dist = _client_for(
        tmp_path, monkeypatch,
        [("EFO", "maptology_server"), ("ABC", "bioportal_user")],
    )
    efo = next(o for o in c.get("/v1/manifest").json()["ontologies"]
               if o["acronym"] == "EFO")
    filename = efo["download_url"].rsplit("/", 1)[-1]
    assert c.get("/v1/cache/" + filename).status_code == 200

    # Regenerate into the same dist with EFO now blocked.
    gm.generate(
        list_tsv=_catalog_tsv(tmp_path, ["EFO", "ABC"]),
        tfidf_dir=str(tmp_path / "tfidf_cache"),
        versions_json=str(tmp_path / "missing.json"),
        policy_tsv=_policy_tsv(tmp_path, [("EFO", "blocked"), ("ABC", "bioportal_user")]),
        out_dir=dist,
    )
    # Same running app, same dist dir: the old download no longer serves.
    assert c.get("/v1/cache/" + filename).status_code == 404
