"""Small file and environment helpers for the paper benchmarks."""

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil


sys.dont_write_bytecode = True

CODE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = CODE_DIR.parent
INPUT_DIR = PACKAGE_DIR / "inputs"
RUN_DIR = PACKAGE_DIR / "runs"
ASSET_DIR = os.environ.get("MAPTOLOGY_BENCHMARK_ASSETS", "")
DATASETS = ("UKBB-EFO", "Biomappings", "OLS-EFO")
METHODS = ("A", "B2", "E1", "E2", "E12", "T")
NAMES = {
    "A": "Original Maptology",
    "B2": "Original Maptology + exact-match priority",
    "E1": "Exact-match priority + separate names and synonyms",
    "E2": "Exact-match priority + 3-character search",
    "E12": "Exact-match priority + separate names and synonyms + 3-character search",
    "T": "text2term",
}


def read_tsv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = []
        for row in reader:
            rows.append(row)
    return rows


def write_tsv(path, columns, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE)
        writer.writerow(columns)
        for row in rows:
            values = []
            for column in columns:
                values.append(row.get(column, ""))
            writer.writerow(values)


def write_json(path, data):
    text = json.dumps(data, indent=2, ensure_ascii=False)
    Path(path).write_text(text + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def new_run(label):
    RUN_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = RUN_DIR / (label + "-" + stamp)
    folder.mkdir()
    return folder


def power_state():
    battery = psutil.sensors_battery()
    if battery is None:
        return "unknown"
    if battery.power_plugged:
        return "mains"
    return "battery"


def check_assets(include_all_indexes):
    if not ASSET_DIR:
        raise RuntimeError("Set MAPTOLOGY_BENCHMARK_ASSETS to the existing testing folder")
    folder = Path(ASSET_DIR)
    if not folder.is_dir():
        raise RuntimeError("The asset folder does not exist: " + str(folder))

    records = read_tsv(PACKAGE_DIR / "records" / "required-assets.tsv")
    for record in records:
        if not record["needed_for"].startswith("run"):
            continue
        saved = record["path"]
        relative = saved.removeprefix("testing folder/")
        path = folder / relative
        if not path.is_file():
            raise RuntimeError("Missing benchmark asset: " + str(path))
        actual = sha256(path)
        if actual != record["sha256"]:
            raise RuntimeError("Benchmark asset changed: " + str(path))

    if include_all_indexes:
        for name in ("word-separate", "char-merged"):
            index = folder / "ranking-experiments-20261021-034704" / "index" / name
            if not index.is_dir():
                raise RuntimeError("Missing benchmark index: " + str(index))
    return folder


def input_rows(dataset):
    return read_tsv(INPUT_DIR / ("eval-" + dataset + ".tsv"))


def input_hashes():
    hashes = {}
    for path in sorted(INPUT_DIR.glob("*.tsv")):
        hashes[path.name] = sha256(path)
    return hashes


def code_hashes():
    hashes = {}
    for path in sorted(CODE_DIR.glob("*.py")):
        hashes[path.name] = sha256(path)
    for path in sorted((CODE_DIR / "method").glob("*.py")):
        hashes["method/" + path.name] = sha256(path)
    return hashes


def rank_of_gold(iris, gold):
    for position, iri in enumerate(iris, start=1):
        if iri == gold:
            return position
    return 0


def percent(hits, count):
    if count == 0:
        return ""
    return "%.4f" % (100 * hits / count)
