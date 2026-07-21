import importlib
import os


def test_versions_are_one():
    from api import config
    assert config.MANIFEST_VERSION == 1
    assert config.CACHE_FORMAT_VERSION == 1


def test_cache_suffixes_are_the_three_files():
    from api import config
    assert config.CACHE_FILE_SUFFIXES == (
        "_tfidf_matrix.npz", "_vectorizer.pkl", "_terms.ormsgpack",
    )


def test_zip_filename_regex_blocks_separators():
    from api import config
    assert config.ZIP_FILENAME_RE.match("EFO-a1b2c3d4e5f6.zip")
    assert config.ZIP_FILENAME_RE.match("NCIT-000000000000.zip")
    assert not config.ZIP_FILENAME_RE.match("../etc/passwd.zip")
    assert not config.ZIP_FILENAME_RE.match("a/b.zip")
    assert not config.ZIP_FILENAME_RE.match(".hidden.zip")
    assert not config.ZIP_FILENAME_RE.match("EFO-a1b2c3d4e5f6.txt")


def test_dist_dir_honors_env_override(monkeypatch):
    monkeypatch.setenv("MAPTOLOGY_DIST_DIR", os.path.join("tmp", "mydist"))
    from api import config
    importlib.reload(config)
    expected = os.path.join("tmp", "mydist")
    assert config.dist_dir() == expected
    assert config.manifest_path() == os.path.join(expected, "manifest.json")
    assert config.cache_zip_dir() == os.path.join(expected, "cache")
    monkeypatch.delenv("MAPTOLOGY_DIST_DIR")
    importlib.reload(config)
