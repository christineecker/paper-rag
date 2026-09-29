# paper-rag

## Graphify knowledge graph

A knowledge graph of this project lives in `graphify-out/`.

- Before answering any question about the codebase (architecture, file relationships, "how does X work", "what calls Y"), query the graph first: `graphify query "<question>"`.
- For specific relationships use `graphify path "<A>" "<B>"` or `graphify explain "<node>"`.
- Read `graphify-out/GRAPH_REPORT.md` for god nodes, communities, and surprising connections when you need a broad overview.
- Fall back to reading or grepping source files only if the graph result is empty or insufficient, and cite `source_location` from graph output when available.
- After changing code, refresh the graph with `graphify update .` (code-only, no LLM needed).
