"""paper-rag retrieval eval: compare chunk, claim and merged search on labelled questions.

python scripts/eval_retrieval.py <questions.json> [--k 5] [--claims-k 3]
    [--strategies chunks,claims,merged] [--embedding-model M]

questions.json: [{"question": "...", "relevant_pmids": ["123", "456"]}, ...]

For each question and strategy, the distinct PMIDs of the returned hits are ranked in
result order and scored against `relevant_pmids`:
  hit    1 if any relevant PMID is returned
  recall fraction of relevant PMIDs returned
  mrr    1 / rank of the first relevant PMID (0 if none)
Prints a JSON summary (means per strategy) plus per-question detail.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import query as query_lib  # noqa: E402

app = typer.Typer(add_completion=False)

STRATEGIES = ("chunks", "claims", "merged", "mixed")


def ranked_pmids(results: list[dict]) -> list[str]:
    seen: list[str] = []
    for r in results:
        pmid = r.get("pmid")
        if pmid and pmid not in seen:
            seen.append(pmid)
    return seen


def score(returned: list[str], relevant: list[str]) -> dict:
    rel = set(relevant)
    found = [p for p in returned if p in rel]
    first = next((i for i, p in enumerate(returned, start=1) if p in rel), None)
    return {
        "hit": 1.0 if found else 0.0,
        "recall": len(set(found)) / len(rel) if rel else 0.0,
        "mrr": 1.0 / first if first else 0.0,
    }


def evaluate(questions: list[dict], strategies: list[str], k: int, claims_k: int, embedding_model: Optional[str]) -> dict:
    per_question = []
    totals = {s: {"hit": 0.0, "recall": 0.0, "mrr": 0.0} for s in strategies}
    for item in questions:
        row = {"question": item["question"], "relevant_pmids": item["relevant_pmids"], "strategies": {}}
        for strategy in strategies:
            results, _ = query_lib.run_query(
                item["question"], k=k, claims_k=claims_k, strategy=strategy, embedding_model=embedding_model
            )
            returned = ranked_pmids(results)
            metrics = score(returned, item["relevant_pmids"])
            row["strategies"][strategy] = {"returned_pmids": returned, **metrics}
            for name, value in metrics.items():
                totals[strategy][name] += value
        per_question.append(row)
    n = len(questions) or 1
    summary = {s: {name: round(v / n, 3) for name, v in t.items()} for s, t in totals.items()}
    return {"n_questions": len(questions), "k": k, "claims_k": claims_k, "summary": summary, "questions": per_question}


@app.command()
def main(
    questions_file: Path = typer.Argument(..., help="JSON list of {question, relevant_pmids}"),
    k: int = typer.Option(5, "--k"),
    claims_k: int = typer.Option(3, "--claims-k"),
    strategies: str = typer.Option("chunks,claims,merged", "--strategies"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
):
    chosen = [s.strip() for s in strategies.split(",") if s.strip()]
    bad = [s for s in chosen if s not in STRATEGIES]
    if bad:
        print(f"error: unknown strategies {bad}; choose from {list(STRATEGIES)}", file=sys.stderr)
        raise typer.Exit(code=2)
    questions = json.loads(questions_file.read_text())
    print(json.dumps(evaluate(questions, chosen, k, claims_k, embedding_model), indent=2))


if __name__ == "__main__":
    app()
