"""Render a PRISMA-style record-flow diagram for one PubMed search into a
standalone HTML page, styled to match docs/.vitepress/theme/custom.css (forced
dark, near-black ground, amber brand accent, monospace kickers).

Requires the search to have been run with `funnel=True` (concepts mode only),
so `payload["provenance"]["funnel"]` holds the cumulative per-concept counts.
"""
from __future__ import annotations

import html as _html


def _esc(text: str) -> str:
    return _html.escape(str(text), quote=True)


_CSS = """
:root{
  --bg:#111113; --bg-alt:#18181b; --divider:#2a2a2f;
  --text-1:#e8e7e3; --text-2:#b9b8bd; --text-3:#8b8a92;
  --brand:#f5a35c; --brand-soft:rgba(245,163,92,.16); --excl:#e07856;
  --mono:ui-monospace,Menlo,Monaco,'Cascadia Code','Roboto Mono',Consolas,'Courier New',monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg); color:var(--text-1); font-family:var(--sans);
  padding-inline:20px; padding-block:40px 56px; font-size:15px; line-height:1.6;}
.page{max-width:760px; margin:0 auto; display:flex; flex-direction:column; gap:36px}
.kicker{font-family:var(--mono); font-size:10.5px; font-weight:600; letter-spacing:.08em;
  text-transform:uppercase; color:var(--brand); margin:0 0 8px;}
header h1{font-size:26px; font-weight:600; margin:0 0 8px; letter-spacing:-0.01em;}
header p.q{color:var(--text-2); font-size:15px; margin:0 0 14px; max-width:62ch;}
.meta-row{display:flex; flex-wrap:wrap; gap:7px 16px; font-family:var(--mono);
  font-size:12px; color:var(--text-3);}
.meta-row b{color:var(--text-1); font-weight:600}
.card{background:var(--bg-alt); border:1px solid var(--divider); border-radius:10px; padding:18px 20px;}
.card.scroll{overflow-x:auto}
.funnel{display:flex; flex-direction:column}
.step{background:var(--bg-alt); border:1px solid var(--divider); border-radius:10px;
  padding:16px 20px; display:flex; justify-content:space-between; align-items:center; gap:16px;}
.step .label{display:flex; flex-direction:column; gap:3px; min-width:0}
.step .filter{font-weight:600; font-size:14px}
.step .filter code{font-family:var(--mono); font-size:11.5px; background:var(--brand-soft);
  color:var(--brand); padding:1px 6px; border-radius:4px;}
.step .desc{font-size:12.5px; color:var(--text-3)}
.step .n{font-family:var(--mono); font-size:22px; font-weight:600;
  font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--text-1);}
.step.final{border-color:var(--brand)}
.step.final .n{color:var(--brand)}
.arrow-row{display:grid; grid-template-columns:1fr auto 1fr; align-items:center;
  column-gap:14px; padding:8px 0;}
.arrow-row .chevron{font-family:var(--mono); font-size:15px; line-height:1; color:var(--brand);}
.arrow-row .excl{grid-column:3; font-family:var(--mono); font-size:11.5px; color:var(--excl);
  white-space:nowrap; font-variant-numeric:tabular-nums; justify-self:start; margin-left:-2px;}
.query pre{margin:0; font-family:var(--mono); font-size:12.5px; white-space:pre-wrap;
  word-break:break-word; color:var(--text-1); line-height:1.7;}
.params dl{display:grid; grid-template-columns:auto 1fr; gap:9px 18px; margin:0; font-size:13px;}
.params dt{font-family:var(--mono); font-size:11px; color:var(--text-3); white-space:nowrap}
.params dd{margin:0; color:var(--text-1); word-break:break-word}
.params dd code{font-family:var(--mono); font-size:11.5px}
footer{font-family:var(--mono); font-size:11.5px; color:var(--text-3); text-align:center}
"""


def render_funnel_html(payload: dict, label: str | None, question: str | None = None) -> str:
    """payload is the JSON dict search_pubmed.py prints (asdict(PubMedSearchResult)
    plus retrieved_at/search_dir); provenance.funnel must be present."""
    provenance = payload["provenance"]
    funnel = provenance.get("funnel")
    if not funnel:
        raise ValueError("payload has no provenance.funnel — rerun the search with --funnel")

    rows = []
    for c in provenance["concept_clauses"]:
        rows.append(
            f'<tr><td class="concept">{_esc(c["concept"])}</td>'
            f'<td>{"required" if c["required"] else "optional"}</td>'
            f'<td class="terms">{_esc(c["clause"])}</td></tr>'
        )
    table_rows = "\n".join(rows)

    steps_html = []
    prev_total = None
    for i, step in enumerate(funnel):
        is_final = i == len(funnel) - 1
        step_class = "step final" if is_final else "step"
        desc = "Included — final PubMed hit count" if is_final else f"AND {_esc(step['concept'])}"
        steps_html.append(
            f'<div class="{step_class}">'
            f'<div class="label"><div class="filter">{_esc(step["concept"])} '
            f'<code>{_esc(step["clause"])}</code></div>'
            f'<div class="desc">{desc}</div></div>'
            f'<div class="n">{step["total_count"]:,}</div></div>'
        )
        if not is_final:
            excluded = step["total_count"] - funnel[i + 1]["total_count"]
            steps_html.append(
                '<div class="arrow-row"><div></div><div class="chevron">▾</div>'
                f'<div class="excl">&minus;{excluded:,} removed by {_esc(funnel[i + 1]["concept"])}</div></div>'
            )
        prev_total = step["total_count"]

    title = _esc(label or "PubMed Search Funnel")
    q_html = f'<p class="q">{_esc(question)}</p>' if question else ""

    return f"""<title>PubMed Search Funnel</title>
<style>{_CSS}</style>
<div class="page">
  <header>
    <p class="kicker">paper-rag &middot; /paper-rag:pubmed-search</p>
    <h1>{title}</h1>
    {q_html}
    <div class="meta-row">
      <span><b>Run</b> {_esc(payload["retrieved_at"])}</span>
      <span><b>Mode</b> {_esc(payload["mode"])}</span>
      <span><b>Sensitivity</b> {_esc(payload["sensitivity"])}</span>
    </div>
  </header>

  <section>
    <p class="kicker">Search framework &mdash; concept groups</p>
    <div class="card scroll">
      <table style="border-collapse:collapse;width:100%;min-width:480px">
        <thead><tr style="text-align:left">
          <th style="font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-3);padding:0 10px 9px 0;border-bottom:1px solid var(--divider)">Concept</th>
          <th style="font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-3);padding:0 10px 9px 0;border-bottom:1px solid var(--divider)">Role</th>
          <th style="font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-3);padding:0 10px 9px 0;border-bottom:1px solid var(--divider)">Compiled clause</th>
        </tr></thead>
        <tbody style="font-size:13.5px">
          {table_rows}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <p class="kicker">Record flow</p>
    <div class="funnel">
      {"".join(steps_html)}
    </div>
  </section>

  <section>
    <p class="kicker">Compiled PubMed query</p>
    <div class="card query"><pre>{_esc(payload["pubmed_query"])}</pre></div>
  </section>

  <section>
    <p class="kicker">Run parameters</p>
    <div class="card params">
      <dl>
        <dt>total_count</dt><dd><code>{payload["total_count"]:,}</code></dd>
        <dt>returned_count</dt><dd><code>{payload["returned_count"]:,}</code></dd>
        <dt>truncated</dt><dd><code>{str(payload["truncated"]).lower()}</code></dd>
        <dt>search_dir</dt><dd><code>{_esc(payload.get("search_dir", ""))}</code></dd>
      </dl>
    </div>
  </section>

  <footer>generated from search_pubmed.py provenance</footer>
</div>
"""
