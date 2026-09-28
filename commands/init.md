---
description: Initialize (or re-register) a paper-rag home at a path
argument-hint: <path> [--name NAME] [--use]
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Initialize a paper-rag RAG home.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/init.py $ARGUMENTS
```

The script resolves `<path>` to an absolute path, creates `<path>/chroma` and
`<path>/papers`, writes a default `config.json` if absent, and upserts the home into
`~/.config/paper-rag/homes.json` under `--name` (default: the directory basename). If this
is the first home ever registered, or `--use` is passed, it becomes the `current` home.

Report to the user: the resolved path, the registered name, whether this was a fresh or
existing home, and whether it is now the active (`current`) home.
