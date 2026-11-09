import argparse
import csv
import hashlib
import importlib.metadata
import json
import random
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import bioregistry
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
COMMIT = "b999dbb670fa13c9ceb1ba631a7abc7557f3293b"
BASE_URL = "https://raw.githubusercontent.com/rsgoncalves/text2term-evaluation/" + COMMIT + "/data/"
SOURCES = {
    "UKBB-EFO": ("UK_Biobank_master_file.tsv", "6a111561366f01c5b5ed8bc81b958341896393febb9edbe5b9c195f1dcf1bed6"),
    "Biomappings": ("biomappings.tsv", "8eca8ddcd235197ac20eff43c6775ab7c9bf486d020603b734e76c396c2890e0"),
    "OLS-EFO": ("efo.ols.sssom.tsv", "a5be5b487c0003713cda5c704a4d8a321229eafbb42c7966cffd004d4049c643"),
}
COLUMNS = ("evaluation_row_id", "source_id", "input_text", "gold_raw", "gold_iri", "input_key")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def download(url, path, expected):
    if path.exists():
        if sha256(path) != expected:
            raise RuntimeError("Existing source file has a different hash: " + str(path))
        return "verified_local_download"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "Maptology-benchmark"})
    with urllib.request.urlopen(request, timeout=120) as response:
        with temporary.open("wb") as handle:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                handle.write(block)
    actual = sha256(temporary)
    if actual != expected:
        raise RuntimeError("Downloaded source hash mismatch: " + path.name + " " + actual)
    temporary.replace(path)
    return "downloaded_and_verified"


def select_rows(dataset, path):
    skipped = 0
    if dataset == "OLS-EFO":
        skipped = 112
    table = pd.read_csv(path, sep="\t", skiprows=skipped)
    original = len(table)
    excluded = {}
    if dataset == "UKBB-EFO":
        mask = table["MAPPED_TERM_URI"].astype(str).str.contains(",")
        excluded["mapping_contains_comma"] = int(mask.sum())
        table = table[~mask]
        mask = table["MAPPED_TERM_URI"].astype(str).str.contains(r"\|\|")
        excluded["mapping_contains_double_pipe"] = int(mask.sum())
        table = table[~mask]
        mask = table["MAPPING_TYPE"] != "Exact"
        excluded["mapping_type_not_exact"] = int(mask.sum())
        table = table[~mask]
    elif dataset == "Biomappings":
        mask = table["target prefix"] != "efo"
        excluded["target_not_efo"] = int(mask.sum())
        table = table[~mask]
        mask = table["relation"] != "skos:exactMatch"
        excluded["relation_not_exact_match"] = int(mask.sum())
        table = table[~mask]
    else:
        mask = table["object_label"].isna()
        excluded["missing_object_label"] = int(mask.sum())
        table = table[~mask]
    return table, original, excluded


def make_rows(dataset, table):
    result = []
    unresolved = 0
    for position, (_, row) in enumerate(table.iterrows()):
        if dataset == "UKBB-EFO":
            source_id = "UKBB-" + str(position).zfill(4)
            text = str(row["ZOOMA QUERY"])
            gold = str(row["MAPPED_TERM_URI"]).replace("_", ":").replace("Orphanet", "ORDO")
        elif dataset == "Biomappings":
            source_id = str(row["source identifier"])
            text = str(row["source name"])
            gold = "efo:" + str(row["target identifier"])
        else:
            source_id = str(row["object_id"])
            text = str(row["object_label"])
            gold = str(row["subject_id"])
        value = gold.strip()
        if value.startswith("http://") or value.startswith("https://"):
            iri = value
        else:
            iri = bioregistry.get_iri(value, priority=["obofoundry", "default"])
        if iri is None:
            iri = ""
            unresolved += 1
        result.append({
            "evaluation_row_id": dataset + "#" + str(position).zfill(5),
            "source_id": source_id,
            "input_text": text,
            "gold_raw": gold,
            "gold_iri": iri,
            "input_key": text.strip(),
        })
    return result, unresolved


def write_table(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE)
        writer.writerow(columns)
        for row in rows:
            values = []
            for column in columns:
                values.append(row[column])
            writer.writerow(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "inputs")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "sources")
    parser.add_argument("--compare-dir", type=Path)
    args = parser.parse_args()
    with (ROOT / "records" / "environment-20261102.json").open(encoding="utf-8") as handle:
        expected = json.load(handle)["input_hashes"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run = ROOT / "runs" / ("inputs-" + stamp)
    run.mkdir(parents=True)
    report = {
        "status": "running",
        "source_commit": COMMIT,
        "sample_seed": 20261021,
        "python": sys.version,
        "pandas": importlib.metadata.version("pandas"),
        "bioregistry": importlib.metadata.version("bioregistry"),
        "datasets": {},
        "outputs": {},
    }
    try:
        for dataset in SOURCES:
            filename, source_hash = SOURCES[dataset]
            source = args.source_dir / filename
            url = BASE_URL + filename
            outcome = download(url, source, source_hash)
            table, original, excluded = select_rows(dataset, source)
            rows, unresolved = make_rows(dataset, table)
            distinct = set()
            for row in rows:
                distinct.add(row["input_key"])
            sample = random.Random(20261021).sample(sorted(distinct), 100)
            sample_rows = []
            for position, text in enumerate(sample, start=1):
                sample_rows.append({"position": position, "input_key": text})
            files = (("eval-" + dataset + ".tsv", COLUMNS, rows),
                     ("speed-sample-" + dataset + ".tsv", ("position", "input_key"), sample_rows))
            for name, columns, output in files:
                temporary = run / name
                write_table(temporary, columns, output)
                digest = sha256(temporary)
                if digest != expected[name]:
                    raise RuntimeError("Recreated input differs from the benchmark: " + name + " " + digest)
                if args.compare_dir:
                    if sha256(args.compare_dir / name) != digest:
                        raise RuntimeError("Local comparison failed: " + name)
                destination = args.output_dir / name
                if destination.exists():
                    if sha256(destination) != digest:
                        raise RuntimeError("Output file differs; it was not overwritten: " + str(destination))
                report["outputs"][name] = {"sha256": digest, "rows": len(output), "matches_existing_benchmark": True}
            report["datasets"][dataset] = {
                "url": url, "source_sha256": source_hash, "download": outcome,
                "original_rows": original, "excluded": excluded, "selected_rows": len(rows),
                "distinct_strings": len(distinct), "unresolved_reference_ids": unresolved,
            }
            print(dataset, "source", original, "selected", len(rows), "sample", len(sample), flush=True)
        for name in report["outputs"]:
            destination = args.output_dir / name
            if not destination.exists():
                destination.write_bytes((run / name).read_bytes())
        report["status"] = "complete"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        (run / "input-verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Report:", run, flush=True)


if __name__ == "__main__":
    main()
