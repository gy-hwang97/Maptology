"""Run the E12 search on small groups of input strings."""

import copy

import numpy as np
from sklearn.metrics.pairwise import check_pairwise_arrays
from sklearn.utils.extmath import safe_sparse_dot

from common import ref


class OptimizedE12:
    def __init__(self, state, lookup, scope):
        self.state = state
        self.lookup = lookup
        self.scope = str(scope)

        if not state["separate"] or state["matrix"].dtype != np.float64:
            raise ValueError("E12 needs the separate-alias float64 index")

        self.transpose = state["matrix"].T.tocsr()
        self.conversions = 1
        self.transforms = 0
        self.score_calls = 0
        self.computed_inputs = 0

    def score_vectors(self, texts):
        if not texts:
            raise ValueError("The input group is empty")
        for text in texts:
            if not text or not isinstance(text, str):
                raise ValueError("Every input must be a nonempty string")

        queries = self.state["vectorizer"].transform(texts)
        self.transforms += 1
        queries, target = check_pairwise_arrays(queries, self.state["matrix"])
        if target is not self.state["matrix"]:
            raise ValueError("The target matrix changed during scoring")

        self.score_calls += 1
        self.computed_inputs += len(texts)
        scores = safe_sparse_dot(queries, self.transpose, dense_output=True)
        return queries, scores

    def concept_scores(self, alias_scores):
        scores = np.zeros(len(self.state["terms"]), dtype=alias_scores.dtype)
        np.maximum.at(scores, self.state["alias_to_concept"], alias_scores)
        return scores

    def finish(self, text, alias_scores, top_n=5):
        diagnostic = {
            "exact_rows": 0,
            "ambiguous": False,
            "zero_score_added": 0,
            "positive": 0,
        }
        if not text:
            return [], diagnostic

        scores = self.concept_scores(alias_scores)
        diagnostic["positive"] = int((scores > 0).sum())
        terms = self.state["terms"]

        base_rows = []
        ranked = ref.ranked_concepts(self.state, scores, top_n)
        for index in ranked:
            row = ref._row(terms[index], scores[index])
            row["exact_match"] = False
            base_rows.append(row)

        hits = self.lookup.get(text)
        if not hits:
            return base_rows[:top_n], diagnostic

        diagnostic["exact_rows"] = len(hits)
        diagnostic["ambiguous"] = len(hits) > 1

        def exact_order(index):
            return (-float(scores[index]),) + ref._key(terms, index)

        exact = sorted(hits, key=exact_order)
        seen = set()
        front = []
        for index in exact:
            term = terms[index]
            iri = term.get("iri", "N/A")
            if iri in seen:
                continue
            seen.add(iri)
            score = float(scores[index])
            if score <= 0:
                diagnostic["zero_score_added"] += 1
            row = ref._row(term, score)
            row["exact_match"] = True
            front.append(row)

        tail = []
        for row in base_rows:
            if row["Ontology Term URI"] not in seen:
                tail.append(row)
        return (front + tail)[:top_n], diagnostic

    def single(self, text, top_n=5):
        text = str(text).strip()
        if not text:
            return self.finish(text, None, top_n)
        _, scores = self.score_vectors([text])
        return self.finish(text, scores[0], top_n)

    def many(self, texts, batch_size=32, dedup=False, top_n=5):
        cleaned = []
        for text in texts:
            cleaned.append(str(text).strip())

        jobs = []
        seen_texts = set()
        for text in cleaned:
            if not text:
                continue
            if dedup and text in seen_texts:
                continue
            jobs.append(text)
            seen_texts.add(text)

        calculated = []
        cache = {}
        for start in range(0, len(jobs), batch_size):
            chunk = jobs[start:start + batch_size]
            _, scores = self.score_vectors(chunk)
            for text, score_row in zip(chunk, scores):
                result = self.finish(text, score_row, top_n)
                if dedup:
                    key = (self.scope, top_n, text)
                    cache[key] = result
                else:
                    calculated.append(result)

        output = []
        position = 0
        for text in cleaned:
            if not text:
                result = self.finish(text, None, top_n)
            elif dedup:
                key = (self.scope, top_n, text)
                result = cache[key]
            else:
                result = calculated[position]
                position += 1
            output.append(copy.deepcopy(result))

        unique = len(set(cleaned))
        chunks = (len(jobs) + batch_size - 1) // batch_size
        details = {
            "rows": len(cleaned),
            "computed": len(jobs),
            "unique": unique,
            "chunks": chunks,
            "batch_size": batch_size,
            "dedup": dedup,
        }
        return output, details
