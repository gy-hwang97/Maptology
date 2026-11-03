"""Run all six accuracy methods on the fixed paper inputs."""

import argparse
import os
import sys

import benchmark_common as common


sys.path.insert(0, str(common.CODE_DIR / "method"))
import engines
from optimized import OptimizedE12


RAW_COLUMNS = (
    "dataset", "evaluation_row_id", "source_id", "input_text", "gold_iri",
    "method_id", "gold_rank", "top1_hit", "top5_hit", "candidate_iris",
    "candidate_scores", "status",
)
SUMMARY_COLUMNS = (
    "dataset", "method_id", "method_name", "evaluation_rows", "top1_hits",
    "top1_percent", "top5_hits", "top5_percent", "candidate_none", "errors",
)


def search_maptology(method, rows, scope):
    state, lookup = engines.load_for(method)
    results = {}

    if method == "E12":
        searcher = OptimizedE12(state, lookup, scope)
        texts = []
        for row in rows:
            texts.append(row["input_key"])
        found, _ = searcher.many(texts, batch_size=32, dedup=True)
        for index, row in enumerate(rows):
            candidates, _ = found[index]
            results[row["evaluation_row_id"]] = candidates
        return results

    for row in rows:
        text = row["input_key"]
        if text not in results:
            results[text], _ = engines.search(method, state, lookup, text)

    by_id = {}
    for row in rows:
        by_id[row["evaluation_row_id"]] = results[row["input_key"]]
    return by_id


def search_text2term(rows):
    ids = []
    texts = []
    for row in rows:
        ids.append(row["evaluation_row_id"])
        texts.append(row["input_key"])
    frame = engines.t2t_map(texts, ids)
    relinked = engines.t2t_relink(frame, ids, texts)
    found = {}
    for source_id, iris, scores, status, note in relinked:
        found[source_id] = (iris, scores, status, note)
    return found


def old_counts():
    saved = common.read_tsv(common.PACKAGE_DIR / "results" / "accuracy-results.tsv")
    found = {}
    for row in saved:
        key = (row["dataset"], row["method_id"])
        found[key] = row
    return found


def score_dataset(dataset, rows, raw_rows, summary_rows, old, scope):
    print("ACCURACY", dataset, len(rows), "rows", flush=True)
    for method in common.METHODS:
        top1 = 0
        top5 = 0
        candidate_none = 0
        errors = 0

        if method == "T":
            found = search_text2term(rows)
        else:
            found = search_maptology(method, rows, scope)

        for row in rows:
            row_id = row["evaluation_row_id"]
            iris = []
            scores = []
            status = "ok"

            if method == "T":
                iris, scores, status, _ = found[row_id]
                if status == "conflicting_outputs":
                    errors += 1
            else:
                candidates = found[row_id]
                for candidate in candidates:
                    iris.append(candidate["Ontology Term URI"])
                    scores.append(float(candidate["Mapping Score"]))

            if not iris:
                candidate_none += 1
            rank = common.rank_of_gold(iris, row["gold_iri"])
            if rank == 1:
                top1 += 1
            if rank > 0 and rank <= 5:
                top5 += 1

            score_texts = []
            for score in scores:
                score_texts.append(str(score))

            raw_rows.append({
                "dataset": dataset,
                "evaluation_row_id": row_id,
                "source_id": row["source_id"],
                "input_text": row["input_text"],
                "gold_iri": row["gold_iri"],
                "method_id": method,
                "gold_rank": rank,
                "top1_hit": int(rank == 1),
                "top5_hit": int(rank > 0 and rank <= 5),
                "candidate_iris": "|".join(iris),
                "candidate_scores": "|".join(score_texts),
                "status": status,
            })

        summary = {
            "dataset": dataset,
            "method_id": method,
            "method_name": common.NAMES[method],
            "evaluation_rows": len(rows),
            "top1_hits": top1,
            "top1_percent": common.percent(top1, len(rows)),
            "top5_hits": top5,
            "top5_percent": common.percent(top5, len(rows)),
            "candidate_none": candidate_none,
            "errors": errors,
        }
        summary_rows.append(summary)
        previous = old[(dataset, method)]
        old1 = int(previous["top1_hits"])
        old5 = int(previous["top5_hits"])
        print(method, "Top-1", top1, "old", old1, "Top-5", top5, "old", old5, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, help="Use only this many rows per dataset for a code check")
    args = parser.parse_args()

    if os.environ.get("PYTHONHASHSEED") != "0":
        raise RuntimeError("Set PYTHONHASHSEED=0 before starting Python")
    common.check_assets(include_all_indexes=True)

    label = "accuracy"
    if args.sample:
        label = "accuracy-sample"
    folder = common.new_run(label)
    status = {
        "status": "running",
        "sample_rows_per_dataset": args.sample,
        "input_hashes": common.input_hashes(),
        "code_hashes": common.code_hashes(),
        "python": sys.version,
        "assets_folder": common.ASSET_DIR,
        "method_note": "E12 uses the verified 32-row optimized path; all other Maptology methods use the reference search.",
    }
    common.write_json(folder / "status.json", status)

    raw_rows = []
    summary_rows = []
    old = old_counts()
    try:
        scope = "EFO-3.62.0-common-29374"
        for dataset in common.DATASETS:
            rows = common.input_rows(dataset)
            if args.sample:
                rows = rows[:args.sample]
            score_dataset(dataset, rows, raw_rows, summary_rows, old, scope)
        common.write_tsv(folder / "accuracy-per-row.tsv", RAW_COLUMNS, raw_rows)
        common.write_tsv(folder / "accuracy-results.tsv", SUMMARY_COLUMNS, summary_rows)
        status["status"] = "complete"
        status["rows_scored"] = len(raw_rows)
    except Exception as failure:
        status["status"] = "failed"
        status["error"] = repr(failure)
        raise
    finally:
        common.write_json(folder / "status.json", status)
        print("Output:", folder, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
