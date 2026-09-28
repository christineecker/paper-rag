---
description: Switch the active paper-rag home
argument-hint: <name>
allowed-tools: Bash(uv run --project ${CLAUDE_PLUGIN_ROOT}:*)
---

Switch the active paper-rag home to a previously registered name.

Run:

```
uv run --project ${CLAUDE_PLUGIN_ROOT} python ${CLAUDE_PLUGIN_ROOT}/scripts/init.py --use-only $ARGUMENTS
```

This only updates the `current` key in `~/.config/paper-rag/homes.json` — no filesystem
changes. If `<name>` isn't registered, the script exits with an error listing known homes;
relay that to the user (suggest `/paper-rag:init` to register it).

Note: a project-local `.paper-rag-home` file (if present in the cwd) overrides this choice
for that project — mention this if the user seems confused about which home is active.
