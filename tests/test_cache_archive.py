from build.cache_archive import (
    make_deterministic_zip,
    sha256_of,
    build_id_from_sha256,
)


def test_zip_is_byte_identical_regardless_of_member_order(tmp_path):
    m1 = [("A_terms.ormsgpack", b"terms"), ("A_vectorizer.pkl", b"vec")]
    m2 = [("A_vectorizer.pkl", b"vec"), ("A_terms.ormsgpack", b"terms")]
    out1 = str(tmp_path / "one.zip")
    out2 = str(tmp_path / "two.zip")
    make_deterministic_zip(m1, out1)
    make_deterministic_zip(m2, out2)

    assert open(out1, "rb").read() == open(out2, "rb").read()
    assert sha256_of(out1) == sha256_of(out2)


def test_different_content_changes_hash(tmp_path):
    out1 = str(tmp_path / "one.zip")
    out2 = str(tmp_path / "two.zip")
    make_deterministic_zip([("A_terms.ormsgpack", b"one")], out1)
    make_deterministic_zip([("A_terms.ormsgpack", b"two")], out2)

    assert sha256_of(out1) != sha256_of(out2)


def test_build_id_is_first_12_chars(tmp_path):
    out = str(tmp_path / "x.zip")
    make_deterministic_zip([("A_terms.ormsgpack", b"x")], out)
    digest = sha256_of(out)

    assert build_id_from_sha256(digest) == digest[:12]
    assert len(build_id_from_sha256(digest)) == 12
