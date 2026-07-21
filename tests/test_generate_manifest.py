import json
import os
import zipfile

from build.cache_archive import sha256_of
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
    lines = ["acronym\tdelivery_mode\tlicense\tlicense_url\treason"]
    for acronym, mode in rows:
        lines.append(acronym + "\t" + mode + "\tLIC-" + acronym
                     + "\thttps://" + acronym + "\treason-" + acronym)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _run(tmp_path, catalog, caches, policy_rows, versions=None):
    tfidf = tmp_path / "tfidf_cache"
    for acronym in caches:
        _make_cache(str(tfidf), acronym)
    if versions is not None:
        vpath = tmp_path / "versions.json"
        vpath.write_text(json.dumps(versions), encoding="utf-8")
        versions_json = str(vpath)
    else:
        versions_json = str(tmp_path / "missing.json")
    out_dir = tmp_path / "dist"
    manifest = gm.generate(
        list_tsv=_catalog_tsv(tmp_path, catalog),
        tfidf_dir=str(tfidf),
        versions_json=versions_json,
        policy_tsv=_policy_tsv(tmp_path, policy_rows),
        out_dir=str(out_dir),
    )
    return manifest, out_dir


def test_all_catalog_entries_appear_with_correct_artifacts(tmp_path):
    manifest, out_dir = _run(
        tmp_path,
        catalog=["ABC", "EFO", "NOP", "XYZ"],
        caches=["ABC", "EFO", "XYZ"],  # NOP is in the catalog but has no cache
        policy_rows=[("EFO", "maptology_server"),
                     ("ABC", "bioportal_user"),
                     ("XYZ", "blocked"),
                     ("NOP", "maptology_server")],
        versions={"EFO": {"version": "3.75.0", "submissionId": 123}},
    )
    by = {o["acronym"]: o for o in manifest["ontologies"]}
    assert set(by) == {"ABC", "EFO", "NOP", "XYZ"}  # every catalog entry appears

    efo = by["EFO"]
    assert efo["delivery_mode"] == "maptology_server"
    assert efo["ontology_version"] == "3.75.0"
    assert efo["submission_id"] == 123
    assert efo["license"] == "LIC-EFO"
    assert efo["download_url"] == "/v1/cache/EFO-" + efo["cache_build_id"] + ".zip"
    zip_path = os.path.join(str(out_dir), "cache", "EFO-" + efo["cache_build_id"] + ".zip")
    assert os.path.isfile(zip_path)
    assert efo["sha256"] == sha256_of(zip_path)
    assert efo["cache_build_id"] == efo["sha256"][:12]
    assert efo["size"] == os.path.getsize(zip_path)

    # yellow: listed, no artifact
    assert by["ABC"]["delivery_mode"] == "bioportal_user"
    assert by["ABC"]["download_url"] is None
    assert by["ABC"]["sha256"] is None

    # blocked: listed, no artifact
    assert by["XYZ"]["delivery_mode"] == "blocked"
    assert by["XYZ"]["download_url"] is None

    # green but no cache: listed, no artifact
    assert by["NOP"]["delivery_mode"] == "maptology_server"
    assert by["NOP"]["download_url"] is None
    assert by["NOP"]["cache_build_id"] is None

    # GC: only EFO's zip exists in the cache dir
    zips = sorted(os.listdir(os.path.join(str(out_dir), "cache")))
    assert zips == ["EFO-" + efo["cache_build_id"] + ".zip"]


def test_metadata_json_included_and_deterministic(tmp_path):
    manifest, out_dir = _run(
        tmp_path,
        catalog=["EFO"],
        caches=["EFO"],
        policy_rows=[("EFO", "maptology_server")],
        versions={"EFO": {"version": "3.75.0", "submissionId": 123}},
    )
    efo = manifest["ontologies"][0]
    zip_path = os.path.join(str(out_dir), "cache", "EFO-" + efo["cache_build_id"] + ".zip")
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "metadata.json" in names
        assert "EFO_tfidf_matrix.npz" in names
        meta = json.loads(zf.read("metadata.json"))
    assert meta["acronym"] == "EFO"
    assert meta["license"] == "LIC-EFO"
    assert meta["ontology_version"] == "3.75.0"
    assert "generated_at" not in meta  # keeps the zip content-deterministic


def test_written_manifest_matches_return_and_missing_versions_is_null(tmp_path):
    manifest, out_dir = _run(
        tmp_path,
        catalog=["EFO"],
        caches=["EFO"],
        policy_rows=[("EFO", "maptology_server")],
        versions=None,
    )
    written = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert written == manifest
    assert written["ontologies"][0]["ontology_version"] is None


def test_reclassify_removes_stale_zip(tmp_path):
    manifest1, out_dir = _run(
        tmp_path,
        catalog=["EFO"],
        caches=["EFO"],
        policy_rows=[("EFO", "maptology_server")],
    )
    old_id = manifest1["ontologies"][0]["cache_build_id"]
    assert os.path.isfile(os.path.join(str(out_dir), "cache", "EFO-" + old_id + ".zip"))

    manifest2 = gm.generate(
        list_tsv=_catalog_tsv(tmp_path, ["EFO"]),
        tfidf_dir=str(tmp_path / "tfidf_cache"),
        versions_json=str(tmp_path / "missing.json"),
        policy_tsv=_policy_tsv(tmp_path, [("EFO", "blocked")]),
        out_dir=str(out_dir),
    )
    assert manifest2["ontologies"][0]["download_url"] is None
    assert os.listdir(os.path.join(str(out_dir), "cache")) == []
