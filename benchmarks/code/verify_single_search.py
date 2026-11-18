import argparse
import json
import os

import benchmark_common as common
import single_search as searcher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-reference")
    parser.add_argument("--api-queries", type=int, default=10)
    args = parser.parse_args()
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise RuntimeError("Set PYTHONHASHSEED=0 before starting Python")
    common.check_assets(False)
    folder = common.new_run("single-verification")
    e12, mapper = searcher.prepare()
    historical = None
    if args.historical_reference:
        with open(args.historical_reference, encoding="utf-8") as handle:
            historical = json.load(handle)
    checked = set()
    results = []
    for dataset in common.DATASETS:
        rows = common.input_rows(dataset)
        differences = 0
        count = 0
        for row in rows:
            text = row["input_key"]
            if text in checked:
                continue
            checked.add(text)
            count += 1
            current = searcher.search("E12", text, row["evaluation_row_id"], e12, mapper)
            if historical is None:
                previous = searcher.engines.search("E12", e12.state, e12.lookup, text)
            else:
                previous = historical[text]
            actual = searcher.signature("E12", current, text, row["evaluation_row_id"])
            expected = searcher.signature("E12", previous, text, row["evaluation_row_id"])
            matches = searcher.same(actual, expected)
            if len(current[0]) == len(previous[0]):
                for a, b in zip(current[0], previous[0]):
                    if a.get("exact_match") != b.get("exact_match"):
                        matches = False
            if not matches:
                differences += 1
        results.append({"dataset": dataset, "check": "E12 single vs original E12", "inputs": count, "differences": differences})
        print(dataset, "E12 checked", count, "differences", differences, flush=True)
        differences = 0
        count = 0
        seen = set()
        for row in rows:
            text = row["input_key"]
            if not text or text in seen:
                continue
            if count >= args.api_queries:
                break
            seen.add(text)
            row_id = "verify-" + str(count)
            prepared = searcher.search("T", text, row_id, e12, mapper)
            official = searcher.engines.t2t_map([text], [row_id])
            actual = searcher.signature("T", prepared, text, row_id)
            expected = searcher.signature("T", official, text, row_id)
            count += 1
            if not searcher.same(actual, expected):
                differences += 1
        results.append({"dataset": dataset, "check": "Prepared text2term vs official single map_terms", "inputs": count, "differences": differences})
        print(dataset, "text2term checked", count, "differences", differences, flush=True)
    common.write_tsv(folder / "equivalence.tsv", results[0].keys(), results)
    report = {"status": "passed", "input_hashes": common.input_hashes(), "code_hashes": common.code_hashes(),
              "rtol": 1e-12, "atol": 1e-12, "distinct_E12_inputs": len(checked), "checks": results}
    for row in results:
        if row["differences"]:
            report["status"] = "failed"
    common.write_json(folder / "verification.json", report)
    print("Report:", folder, flush=True)
    if report["status"] != "passed":
        raise RuntimeError("Output equivalence failed")


if __name__ == "__main__":
    main()
