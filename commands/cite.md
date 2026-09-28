---
description: Generate BibTeX for one or more papers in the active paper-rag library
argument-hint: [doc_key|pmid ...] [--all]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Generate BibTeX for papers in the active paper-rag library.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/cite.py $ARGUMENTS
```

Print the raw `.bib` text the script outputs to the user verbatim (it's meant to be
pasted/redirected into a `.bib` file as-is — don't reformat or summarize it). If the
script warns on stderr that a target has no `metadata.json` (e.g. a hand-copied local
file that never had a PMID lookup), relay that warning after the BibTeX output.
