---
description: Compare chunk, claim and merged retrieval on labelled questions
argument-hint: <questions.json> [--k 5] [--claims-k 3] [--strategies chunks,claims,merged]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Score retrieval strategies on the user's own labelled questions.

`questions.json` is a JSON list of `{"question": "...", "relevant_pmids": ["PMID", ...]}`;
`evals/questions.example.json` shows the shape. The relevant PMIDs must come from the
user: never invent questions or labels.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/eval_retrieval.py $ARGUMENTS
```

It prints per-strategy means of `hit` (any relevant paper returned), `recall` (share of
relevant papers returned) and `mrr` (1 / rank of the first relevant paper), plus
per-question detail. Summarise the `summary` block as a small table and point out
questions where strategies disagree. State the number of questions; with fewer than
about 20, treat differences as indicative only.
