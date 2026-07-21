"""Deterministic zip packaging + hashing for ontology cache bundles.

A cache bundle is one ontology's three TF-IDF files plus a small metadata.json.
Packing them into a single zip whose bytes depend only on the member *contents*
and names (not timestamps or ordering) lets the zip's sha256 double as a content
fingerprint: rebuild the same bundle and you get the same zip, the same hash, the
same build id. A changed cache, or changed metadata, changes the id.
"""

import hashlib
import os
import zipfile

# Fixed zip timestamp (the zip epoch). A constant date_time -> reproducible bytes.
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)
_CHUNK = 1024 * 1024


def make_deterministic_zip(members, out_path):
    """Write ``members`` into ``out_path`` as a reproducible zip.

    ``members`` is a list of ``(arcname, data_bytes)`` pairs. They are stored
    sorted by arcname with a fixed timestamp, so identical content always
    produces identical archive bytes. The archive is written to a temp file and
    renamed, so a crash cannot leave a half-written zip.
    """
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    ordered = sorted(members, key=lambda m: m[0])
    tmp_path = out_path + ".tmp"
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in ordered:
            info = zipfile.ZipInfo(filename=arcname, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    os.replace(tmp_path, out_path)


def sha256_of(path):
    """Return the lowercase hex sha256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def build_id_from_sha256(sha256):
    """Short content fingerprint: the first 12 hex chars of the zip sha256."""
    return sha256[:12]
