import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build"))

import setup_ontologies as setup


class FakeResponse:
    """Just enough of requests' streaming response for download_one."""

    def __init__(self, body, headers=None, status_code=200, deliver=None):
        self.body = body
        self.headers = headers or {}
        self.status_code = status_code
        # What the server actually sends, when that differs from what it promised.
        self._deliver = body if deliver is None else deliver

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._deliver), chunk_size):
            yield self._deliver[i:i + chunk_size]


def _serve(monkeypatch, tmp_path, response):
    monkeypatch.setattr(setup, "OWL_DIR", str(tmp_path))
    monkeypatch.setattr(setup.requests, "get", lambda *a, **k: response)


ONT = {"acronym": "AAA", "native_format": "OWL"}


def test_complete_download_is_kept(monkeypatch, tmp_path):
    body = b"x" * 5000
    _serve(monkeypatch, tmp_path, FakeResponse(body, {"Content-Length": "5000"}))
    setup.download_one(ONT, "key")
    assert (tmp_path / "AAA.owl").read_bytes() == body


def test_truncated_download_is_rejected(monkeypatch, tmp_path):
    """BioPortal cuts its RDF conversion off at 1 GiB and says nothing.

    PR, GAZ and CHEBI all sit on disk at 1.0007 GiB, each ending mid-element.
    """
    _serve(monkeypatch, tmp_path,
           FakeResponse(b"x" * 5000, {"Content-Length": "5000"}, deliver=b"x" * 4000))
    with pytest.raises(RuntimeError) as excinfo:
        setup.download_one(ONT, "key")
    assert "4000" in str(excinfo.value) and "5000" in str(excinfo.value)


def test_a_rejected_download_leaves_nothing_behind(monkeypatch, tmp_path):
    _serve(monkeypatch, tmp_path,
           FakeResponse(b"x" * 5000, {"Content-Length": "5000"}, deliver=b"x" * 10))
    with pytest.raises(RuntimeError):
        setup.download_one(ONT, "key")
    assert not (tmp_path / "AAA.owl").exists()
    assert not (tmp_path / "AAA.owl.part").exists()


def test_a_rejected_download_does_not_replace_a_good_file(monkeypatch, tmp_path):
    good = tmp_path / "AAA.owl"
    good.write_bytes(b"the copy that already works")
    _serve(monkeypatch, tmp_path,
           FakeResponse(b"x" * 5000, {"Content-Length": "5000"}, deliver=b"x" * 10))
    with pytest.raises(RuntimeError):
        setup.download_one(ONT, "key")
    assert good.read_bytes() == b"the copy that already works"


def test_download_without_a_length_is_accepted(monkeypatch, tmp_path):
    """Chunked responses carry no length; there is nothing to check against."""
    _serve(monkeypatch, tmp_path, FakeResponse(b"y" * 300, {}))
    setup.download_one(ONT, "key")
    assert (tmp_path / "AAA.owl").read_bytes() == b"y" * 300


def test_compressed_response_is_not_measured_against_its_encoded_length(
        monkeypatch, tmp_path):
    """With Content-Encoding the header counts compressed bytes, not the file."""
    _serve(monkeypatch, tmp_path,
           FakeResponse(b"z" * 900, {"Content-Length": "120",
                                     "Content-Encoding": "gzip"}))
    setup.download_one(ONT, "key")
    assert (tmp_path / "AAA.owl").read_bytes() == b"z" * 900


# --- OWL text syntaxes our parsers cannot read (issue #45) -------------------
#
# BioPortal serves a submission as it was uploaded. Nineteen cached ontologies
# arrived in OWL functional syntax (ADHER_INTCARE_EN, IDO, SEPON, ...) or
# Manchester syntax (CHD, FTC, GSSO, ...), which neither owlready2 nor rdflib
# can read. BioPortal also keeps an RDF/XML conversion of every submission it
# parsed, and download_format=rdf fetches that one instead.

FUNCTIONAL = (b"Prefix(:=<http://example.org/x#>)\n"
              b"Ontology(<http://example.org/x>\nDeclaration(Class(:A))\n)\n")
MANCHESTER = b"Prefix: : <http://example.org/x#>\nOntology: <http://example.org/x>\nClass: :A\n"
RDF_XML = (b'<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           b"</rdf:RDF>\n")


def _serve_by_params(monkeypatch, tmp_path, responder):
    """Like _serve, but the response depends on the query parameters and
    every request's parameters are recorded, in order."""
    calls = []

    def get(url, params=None, **kwargs):
        calls.append(dict(params or {}))
        return responder(params or {})

    monkeypatch.setattr(setup, "OWL_DIR", str(tmp_path))
    monkeypatch.setattr(setup.requests, "get", get)
    return calls


def _bioportal(raw):
    """A server whose plain download is `raw` and whose RDF conversion is RDF/XML."""
    return lambda params: FakeResponse(RDF_XML if params.get("download_format") == "rdf" else raw)


def test_functional_syntax_is_replaced_by_bioportals_rdf_conversion(monkeypatch, tmp_path):
    calls = _serve_by_params(monkeypatch, tmp_path, _bioportal(FUNCTIONAL))
    ont = {"acronym": "AAA", "native_format": "OWL", "download_format": "OWL"}
    setup.download_one(ont, "key")
    assert (tmp_path / "AAA.owl").read_bytes() == RDF_XML
    assert [c.get("download_format") for c in calls] == [None, "rdf"]
    assert ont["download_format"] == "RDF/XML"      # the catalogue row says what is on disk


def test_manchester_syntax_is_replaced_by_bioportals_rdf_conversion(monkeypatch, tmp_path):
    calls = _serve_by_params(monkeypatch, tmp_path, _bioportal(MANCHESTER))
    ont = {"acronym": "AAA", "native_format": "OWL", "download_format": "OWL"}
    setup.download_one(ont, "key")
    assert (tmp_path / "AAA.owl").read_bytes() == RDF_XML
    assert [c.get("download_format") for c in calls] == [None, "rdf"]
    assert ont["download_format"] == "RDF/XML"


def test_readable_download_is_fetched_once(monkeypatch, tmp_path):
    calls = _serve_by_params(monkeypatch, tmp_path, _bioportal(RDF_XML))
    ont = {"acronym": "AAA", "native_format": "OWL", "download_format": "OWL"}
    setup.download_one(ont, "key")
    assert (tmp_path / "AAA.owl").read_bytes() == RDF_XML
    assert len(calls) == 1
    assert ont["download_format"] == "OWL"


def test_a_leading_bom_and_blank_lines_do_not_hide_the_syntax(monkeypatch, tmp_path):
    """AURA's file starts with a byte-order mark and 'Prefix(' split across lines."""
    raw = b"\xef\xbb\xbf\r\n\r\nPrefix(\r\n:=<http://www.projecthalo.com/aura#>)\r\n"
    calls = _serve_by_params(monkeypatch, tmp_path, _bioportal(raw))
    ont = {"acronym": "AAA", "native_format": "OWL", "download_format": "OWL"}
    setup.download_one(ont, "key")
    assert (tmp_path / "AAA.owl").read_bytes() == RDF_XML
    assert len(calls) == 2
