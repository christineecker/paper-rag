---
description: Filter the active paper-rag library by authorship position, year, journal, keyword, or publication type
argument-hint: [--author NAME] [--as first|last|any] [--year Y|Y-Y] [--journal J] [--keyword K] [--pub-type T]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Mine the active paper-rag library's bibliographic metadata (not a vector search).

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/mine.py $ARGUMENTS
```

If `--author` isn't given, the script falls back to `author_name` in `config.json` (set
via `/paper-rag:whoami`); if neither is set, it lists every paper unfiltered.

This returns a JSON array: `{doc_key, pmid, pmcid, title, authors, year, journal,
keywords, pub_types, position}` (`position` omitted if no author filter was applied).

Present the results as a table (title, journal, year, and — when relevant — the author's
position) rather than dumping raw JSON. If the array is empty, say no papers matched.
