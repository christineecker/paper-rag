---
description: Set your author name for /paper-rag:mine's default author filter
argument-hint: <name>
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Set (or update) the `author_name` used as the default `--author` filter for
`/paper-rag:mine`.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/init.py --whoami "$ARGUMENTS"
```

This patches only the `author_name` key in the active home's `config.json` — nothing else
changes. Confirm to the user what name was saved (matching in `/paper-rag:mine` is a
case-insensitive substring match against each paper's author `family` field, e.g. "Ecker"
matches "Ecker C").
