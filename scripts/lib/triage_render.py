"""Render a manual triage dashboard for one PubMed search into a standalone
HTML page: real metadata (title/authors/journal/abstract), all records
selected by default, per-exclusion reason notes, a live before/after PRISMA
record-flow, and a "Save triage.json" step that downloads the decision file
for `scripts/ingest_from_triage.py` to consume. Styled to match
funnel_render.py (forced dark, near-black ground, amber brand accent).

Nothing here touches full text or calls ingest.py — triage is metadata-only,
and ingestion is a separate, deliberate CLI step.
"""
from __future__ import annotations

import html as _html
import json
from pathlib import Path

from . import fetch as fetch_lib


def _esc(text) -> str:
    return _html.escape(str(text), quote=True)


def _authors_str(authors: list[dict]) -> str:
    parts = []
    for a in authors:
        given = (a.get("given") or "").strip()
        initials = "".join(w[0] for w in given.split()) if given else ""
        parts.append(f"{a.get('family', '')} {initials}".strip())
    return ", ".join(parts) if parts else "(no listed authors)"


_CSS = """
:root{
  --bg:#111113; --surface:#18181b; --border:#2a2a2f;
  --fg:#e8e7e3; --muted:#8b8a92; --muted-2:#b9b8bd;
  --accent:#f5a35c; --accent-soft:rgba(245,163,92,.16); --accent-fg:#1a1207; --excl:#e07856;
  --mono:ui-monospace,Menlo,Monaco,'Cascadia Code','Roboto Mono',Consolas,'Courier New',monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);margin:0;font-size:15px;line-height:1.6}
.page{max-width:900px;margin:0 auto;padding-inline:16px;padding-block:36px 60px;display:flex;flex-direction:column;gap:34px}
.kicker{font-family:var(--mono);font-size:10.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}
header h1{font-size:24px;font-weight:600;margin:0 0 8px;letter-spacing:-0.01em}
header p.q{color:var(--muted-2);font-size:14.5px;margin:0 0 14px;max-width:62ch}
.meta-row{display:flex;flex-wrap:wrap;gap:7px 16px;font-family:var(--mono);font-size:12px;color:var(--muted)}
.meta-row b{color:var(--fg);font-weight:600}

.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
.card.scroll{overflow-x:auto}
.card table{border-collapse:collapse;width:100%;min-width:480px}
.card th{text-align:left;font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);padding:0 10px 9px 0;border-bottom:1px solid var(--border)}
.card td{padding:9px 10px 9px 0;border-bottom:1px solid var(--border);font-size:13.5px;vertical-align:top}
.card tr:last-child td{border-bottom:none}
.card td.concept{font-weight:600;white-space:nowrap}
.card td.terms{font-family:var(--mono);font-size:12px;color:var(--muted-2)}
.card.query pre{margin:0;font-family:var(--mono);font-size:12.5px;white-space:pre-wrap;word-break:break-word;
  color:var(--fg);line-height:1.7}

.funnel{display:flex;flex-direction:column}
.step{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:14px 18px;display:flex;justify-content:space-between;align-items:center;gap:16px}
.step .label{display:flex;flex-direction:column;gap:3px;min-width:0}
.step .name{font-weight:600;font-size:13.5px}
.step .desc{font-size:12px;color:var(--muted)}
.step .n{font-family:var(--mono);font-size:20px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--fg)}
.step.final{border-color:var(--accent)}
.step.final .n{color:var(--accent)}
.arrow-row{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;column-gap:14px;padding:6px 0}
.arrow-row .chevron{font-family:var(--mono);font-size:14px;line-height:1;color:var(--accent);grid-column:2}
.arrow-row .excl{grid-column:3;font-family:var(--mono);font-size:11px;color:var(--excl);
  white-space:nowrap;font-variant-numeric:tabular-nums;justify-self:start;margin-left:-2px}

.link-arrow{display:flex;justify-content:center;color:var(--muted);font-family:var(--mono);font-size:13px;padding-block:2px}

.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding-block:4px 12px;display:flex;flex-direction:column;gap:8px}
.bar-row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}
.bar input[type="search"]{flex:1 1 200px;min-width:0;background:var(--surface);color:var(--fg);
  border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-family:var(--sans);font-size:0.9rem}
.bar select{background:var(--surface);color:var(--fg);border:1px solid var(--border);border-radius:8px;
  padding:8px 10px;font-family:var(--sans);font-size:0.85rem}
.check-all{display:flex;align-items:center;gap:6px;font-size:0.85rem;color:var(--muted);white-space:nowrap}
.check-all input{width:16px;height:16px;accent-color:var(--accent)}
.view-toggle{display:flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;flex:none}
.view-toggle button{background:var(--surface);color:var(--muted);border:none;padding:7px 12px;
  font-size:0.78rem;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;font-family:var(--sans)}
.view-toggle button+button{border-left:1px solid var(--border)}
.view-toggle button.active{background:var(--accent-soft);color:var(--accent)}
.view-toggle svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.6}

.count-row{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;
  padding-block:2px 12px;font-size:0.85rem;color:var(--muted)}
.count-row strong{color:var(--fg);font-variant-numeric:tabular-nums}

.list{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;align-items:start}
.list .card{position:relative;display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--border);
  border-radius:10px;padding:14px 40px 14px 16px;transition:background .12s,border-color .12s;height:100%;cursor:pointer}
.list .card.selected{background:var(--accent-soft);border-color:var(--accent)}
.list .card input[type="checkbox"]{position:absolute;top:14px;right:14px;width:19px;height:19px;accent-color:var(--accent);cursor:pointer}
.card-content{min-width:0}
.card-title{font-weight:600;font-size:0.94rem;line-height:1.35;margin:0 0 6px;color:var(--fg);
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.meta{color:var(--muted);font-size:0.76rem;line-height:1.5;margin-bottom:8px}
.meta .authors{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meta .line2{display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px;margin-top:2px}
.meta .pmid{font-family:var(--mono)}
.meta .dot{opacity:.5}
.pill{display:inline-block;font-size:0.6rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  border-radius:4px;padding:1px 5px;border:1px solid var(--border);color:var(--muted)}
.pill.pmc{color:var(--accent);border-color:var(--accent)}
.abstract{font-size:0.82rem;line-height:1.5;color:var(--muted-2);margin:0;
  display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.list .card.expanded .abstract{-webkit-line-clamp:unset}
.toggle-abs{align-self:flex-start;background:none;border:none;color:var(--accent);font-size:0.75rem;
  padding:6px 0 0;cursor:pointer;font-weight:600;font-family:var(--sans)}
.empty{text-align:center;color:var(--muted);padding-block:40px;font-size:0.9rem;grid-column:1/-1}

.reason-wrap{margin-top:8px}
.card.selected .reason-wrap{display:none}
.reason-toggle{background:none;border:none;color:var(--muted);font-size:0.74rem;padding:0;
  cursor:pointer;font-family:var(--sans);text-decoration:underline;text-underline-offset:2px}
.reason-toggle:hover{color:var(--excl)}
.reason-box{width:100%;margin-top:6px;background:var(--bg);color:var(--fg);border:1px solid var(--border);
  border-radius:6px;padding:7px 9px;font-family:var(--sans);font-size:0.78rem;resize:vertical;min-height:44px}
.reason-box:focus{outline:1px solid var(--excl);border-color:var(--excl)}

.list.view-list{display:flex;flex-direction:column;gap:8px}
.list.view-list .card{flex-direction:row;align-items:flex-start;gap:12px;padding:12px 44px 12px 16px;border-radius:8px}
.list.view-list .card input[type="checkbox"]{top:50%;transform:translateY(-50%)}
.list.view-list .card-content{flex:1;display:flex;flex-wrap:wrap;align-items:baseline;column-gap:14px;row-gap:2px}
.list.view-list .card-title{-webkit-line-clamp:1;margin:0;font-size:0.9rem;flex:1 1 240px;min-width:0}
.list.view-list .meta{margin:0;display:flex;flex-wrap:wrap;align-items:center;gap:2px 6px;flex:1 1 260px;min-width:0}
.list.view-list .meta .authors{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px}
.list.view-list .meta .authors::after{content:" ·";opacity:.5;margin-left:4px}
.list.view-list .abstract,.list.view-list .toggle-abs,.list.view-list .reason-wrap{display:none}

.final-empty{background:var(--surface);border:1px dashed var(--border);border-radius:10px;
  padding:22px 18px;text-align:center;color:var(--muted);font-size:0.88rem}
.final-list{display:flex;flex-direction:column;gap:1px;border:1px solid var(--border);border-radius:10px;overflow:hidden}
.final-row{display:flex;justify-content:space-between;align-items:center;gap:14px;background:var(--surface);padding:11px 16px}
.final-row .t{min-width:0}
.final-row .t .ti{font-size:0.86rem;font-weight:600;color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.final-row .t .sub{font-size:0.74rem;color:var(--muted);font-family:var(--mono);margin-top:2px}
.excl-list{display:flex;flex-direction:column;gap:1px;border:1px solid var(--border);border-radius:10px;overflow:hidden}
.excl-row{display:flex;flex-direction:column;gap:2px;background:var(--surface);padding:10px 16px}
.excl-row .ti{font-size:0.82rem;font-weight:600;color:var(--muted-2)}
.excl-row .sub{font-size:0.72rem;color:var(--muted);font-family:var(--mono)}
.excl-row .rs{font-size:0.78rem;color:var(--excl);margin-top:2px}
.excl-row .rs.no-reason{color:var(--muted);font-style:italic}
.note{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:10px}

.save-row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:flex-end;margin-top:12px}
button.save{background:var(--accent);color:var(--accent-fg);border:none;border-radius:8px;
  padding:10px 18px;font-weight:600;font-size:0.85rem;cursor:pointer;font-family:var(--sans)}
button.save:hover{filter:brightness(1.06)}
.saved-hint{font-size:0.8rem;color:var(--accent);opacity:0;transition:opacity .2s}
.saved-hint.show{opacity:1}
.card.json pre{max-height:220px;overflow:auto}
footer{font-family:var(--mono);font-size:11.5px;color:var(--muted);text-align:center;margin-top:8px}
"""


def render_triage_html(payload: dict, papers: list[dict], label: str | None) -> str:
    """payload is the JSON dict search_pubmed.py's result.json holds (plus
    search_dir). papers is a list of {pmid, title, authors (list of
    {family,given}), journal, year, doi, pmcid, abstract} dicts, one per PMID
    in payload["pmids"], in that order."""
    provenance = payload.get("provenance") or {}
    funnel = provenance.get("funnel")

    before_html = ""
    if funnel:
        rows = []
        for c in provenance.get("concept_clauses", []):
            rows.append(
                f'<tr><td class="concept">{_esc(c["concept"])}</td>'
                f'<td>{"required" if c["required"] else "optional"}</td>'
                f'<td class="terms">{_esc(c["clause"])}</td></tr>'
            )
        steps_html = []
        for i, step in enumerate(funnel):
            is_final = i == len(funnel) - 1
            step_class = "step final" if is_final else "step"
            desc = "included — final PubMed hit count, advanced to manual triage" if is_final else f"AND {_esc(step['concept'])}"
            steps_html.append(
                f'<div class="{step_class}"><div class="label">'
                f'<div class="name">{_esc(step["concept"])}</div><div class="desc">{desc}</div></div>'
                f'<div class="n">{step["total_count"]:,}</div></div>'
            )
            if not is_final:
                excluded = step["total_count"] - funnel[i + 1]["total_count"]
                steps_html.append(
                    '<div class="arrow-row"><div></div><div class="chevron">&#9662;</div>'
                    f'<div class="excl">&minus;{excluded:,} removed by AND {_esc(funnel[i + 1]["concept"])}</div></div>'
                )
        before_html = f"""
  <section>
    <p class="kicker">Search framework &mdash; concept groups</p>
    <div class="card scroll"><table>
      <thead><tr><th>Concept</th><th>Role</th><th>Compiled clause</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table></div>
  </section>

  <section>
    <p class="kicker">Record flow &mdash; before triage</p>
    <div class="funnel">{"".join(steps_html)}</div>
  </section>
"""
    else:
        before_html = f"""
  <section>
    <p class="kicker">Record flow &mdash; before triage</p>
    <div class="funnel">
      <div class="step final"><div class="label"><div class="name">{_esc(payload.get("mode", "search"))}</div>
      <div class="desc">included — advanced to manual triage</div></div>
      <div class="n">{len(papers):,}</div></div>
    </div>
  </section>
"""

    query_html = f"""
  <section>
    <p class="kicker">Compiled PubMed query</p>
    <div class="card query"><pre>{_esc(payload.get("pubmed_query", ""))}</pre></div>
  </section>
"""

    papers_json = json.dumps(
        [
            {
                "pmid": p["pmid"],
                "title": p.get("title") or "(no title)",
                "authors": _authors_str(p.get("authors") or []),
                "authors_list": p.get("authors") or [],
                "journal": p.get("journal") or "(no journal)",
                "year": p.get("year") or "",
                "volume": p.get("volume"),
                "issue": p.get("issue"),
                "pages": p.get("pages"),
                "doi": p.get("doi"),
                "pmcid": p.get("pmcid"),
                "elocation_id": p.get("elocation_id"),
                "pub_types": p.get("pub_types") or [],
                "keywords": p.get("keywords") or [],
                "abstract": p.get("abstract") or "(no abstract)",
            }
            for p in papers
        ]
    ).replace("</", "<\\/")

    search_meta_json = json.dumps(
        {
            "pubmed_query": payload.get("pubmed_query"),
            "mode": payload.get("mode"),
            "sensitivity": payload.get("sensitivity"),
            "retrieved_at": payload.get("retrieved_at"),
            "total_count": payload.get("total_count"),
            "returned_count": payload.get("returned_count"),
            "truncated": payload.get("truncated"),
            "concept_clauses": provenance.get("concept_clauses") or [],
            "funnel": funnel or [],
            "esearch_query_translation": provenance.get("query_translation"),
        }
    ).replace("</", "<\\/")

    title = _esc(label or "Search Triage")
    search_dir = _esc(payload.get("search_dir", ""))
    search_dir_json = json.dumps(payload.get("search_dir", "")).replace("</", "<\\/")
    retrieved_at = _esc(payload.get("retrieved_at", ""))

    return f"""<title>{title} &mdash; triage</title>
<style>{_CSS}</style>
<div class="page">
  <header>
    <p class="kicker">paper-rag &middot; /paper-rag:pubmed-search &rarr; triage &rarr; ingest</p>
    <h1>{title}</h1>
    <p class="q">Metadata-only review of {len(papers)} record{"s" if len(papers) != 1 else ""}. Nothing here touches full text, and nothing gets ingested until you run <code>ingest_from_triage.py</code> against the saved decisions.</p>
    <div class="meta-row">
      <span><b>Run</b> {retrieved_at}</span>
      <span><b>Mode</b> {_esc(payload.get("mode", ""))}</span>
      <span><b>Sensitivity</b> {_esc(payload.get("sensitivity", ""))}</span>
      <span><b>search_dir</b> {search_dir}</span>
    </div>
  </header>
{before_html}{query_html}
  <div class="link-arrow">&#9662; screen each record &#9662;</div>

  <section>
    <p class="kicker">Manual triage &mdash; metadata only</p>
    <div class="bar">
      <div class="bar-row">
        <input type="search" id="q" placeholder="Filter by title, author, keyword…">
        <select id="journalFilter"><option value="">All journals</option></select>
        <select id="yearFilter"><option value="">All years</option></select>
      </div>
      <div class="bar-row">
        <label class="check-all"><input type="checkbox" id="selectAll"> select all shown</label>
        <div class="view-toggle">
          <button type="button" id="gridViewBtn" class="active" aria-pressed="true">
            <svg viewBox="0 0 16 16"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>
            Grid
          </button>
          <button type="button" id="listViewBtn" aria-pressed="false">
            <svg viewBox="0 0 16 16"><line x1="1" y1="3" x2="15" y2="3"/><line x1="1" y1="8" x2="15" y2="8"/><line x1="1" y1="13" x2="15" y2="13"/></svg>
            List
          </button>
        </div>
      </div>
    </div>
    <div class="count-row">
      <span><strong id="selCount">0</strong> of <strong id="totalCount">0</strong> selected for inclusion</span>
    </div>
    <div class="list" id="list"></div>
    <div class="empty" id="emptyMsg" hidden>No papers match this filter.</div>
  </section>

  <div class="link-arrow">&#9662; update prisma from selection &#9662;</div>

  <section>
    <p class="kicker">Record flow &mdash; after triage</p>
    <div class="funnel">
      <div class="step">
        <div class="label"><div class="name">manual triage</div><div class="desc">advanced to manual triage</div></div>
        <div class="n">{len(papers)}</div>
      </div>
      <div class="arrow-row"><div></div><div class="chevron">&#9662;</div><div class="excl" id="finalExcl">&minus;0 excluded at manual triage</div></div>
      <div class="step final">
        <div class="label"><div class="name">Manual triage</div><div class="desc">included &mdash; ready for ingest</div></div>
        <div class="n" id="finalN">{len(papers)}</div>
      </div>
    </div>
  </section>

  <section id="exclSection" hidden>
    <p class="kicker">Excluded at triage</p>
    <div id="exclList" class="excl-list"></div>
  </section>

  <section>
    <p class="kicker">Final selection</p>
    <div id="finalEmpty" class="final-empty" hidden>Nothing selected — check papers above to build the final list.</div>
    <div id="finalList" class="final-list"></div>
    <p class="note">Not ingested. Run <code>python scripts/ingest_from_triage.py {search_dir}/triage.json</code> once this list is final.</p>
  </section>

  <section>
    <p class="kicker">Save decisions</p>
    <div class="card json"><pre id="jsonPreview"></pre></div>
    <div class="save-row">
      <button class="save" id="saveBtn">Save triage.json</button>
      <span class="saved-hint" id="savedHint">saved</span>
    </div>
  </section>

  <footer>generated from search_pubmed.py provenance + manual triage</footer>
</div>

<script>
const PAPERS = {papers_json};
const SEARCH_DIR = {search_dir_json};
const SEARCH_META = {search_meta_json};
const RETRIEVED = new Date().toISOString();

const state = {{ selected: new Set(PAPERS.map(p=>p.pmid)), view: "grid", reasons: {{}} }};
try{{
  const saved = localStorage.getItem("triage-view");
  if (saved === "list" || saved === "grid") state.view = saved;
}}catch(e){{}}

function escapeHtml(s){{
  return String(s).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
}}
function uniqueSorted(field){{
  return [...new Set(PAPERS.map(p=>p[field]))].filter(v=>v!=="").sort((a,b)=> typeof a==="number" ? b-a : String(a).localeCompare(String(b)));
}}
function populateFilters(){{
  const jf = document.getElementById("journalFilter");
  uniqueSorted("journal").forEach(j=>{{ const o=document.createElement("option"); o.value=j; o.textContent=j; jf.appendChild(o); }});
  const yf = document.getElementById("yearFilter");
  uniqueSorted("year").forEach(y=>{{ const o=document.createElement("option"); o.value=y; o.textContent=y; yf.appendChild(o); }});
}}
function matches(p, q, journal, year){{
  if (journal && p.journal !== journal) return false;
  if (year && String(p.year) !== year) return false;
  if (!q) return true;
  const hay = (p.title + " " + p.authors + " " + p.abstract).toLowerCase();
  return hay.includes(q.toLowerCase());
}}

function render(){{
  const q = document.getElementById("q").value.trim();
  const journal = document.getElementById("journalFilter").value;
  const year = document.getElementById("yearFilter").value;
  const list = document.getElementById("list");
  const shown = PAPERS.filter(p => matches(p, q, journal, year));

  list.innerHTML = "";
  document.getElementById("emptyMsg").hidden = shown.length !== 0;

  shown.forEach(p=>{{
    const card = document.createElement("div");
    card.className = "card" + (state.selected.has(p.pmid) ? " selected" : "");
    const pmcPill = p.pmcid ? '<span class="pill pmc">PMC available</span>' : '<span class="pill">no PMC record</span>';
    card.innerHTML = `
      <input type="checkbox" data-pmid="${{escapeHtml(p.pmid)}}" ${{state.selected.has(p.pmid) ? "checked" : ""}}>
      <div class="card-content">
        <p class="card-title">${{escapeHtml(p.title)}}</p>
        <div class="meta">
          <span class="authors">${{escapeHtml(p.authors)}}</span>
          <span class="line2">
            <span>${{escapeHtml(p.journal)}}${{p.year ? ", " + escapeHtml(String(p.year)) : ""}}</span>
            <span class="dot">·</span>
            <span class="pmid">PMID ${{escapeHtml(p.pmid)}}</span>
            ${{pmcPill}}
          </span>
        </div>
        <p class="abstract">${{escapeHtml(p.abstract)}}</p>
        <button class="toggle-abs" type="button">Show more</button>
        <div class="reason-wrap">
          <button class="reason-toggle" type="button">${{state.reasons[p.pmid] ? "edit reason" : "+ reason"}}</button>
          <textarea class="reason-box" placeholder="e.g. wrong population, animal study, duplicate…"
            hidden>${{escapeHtml(state.reasons[p.pmid] || "")}}</textarea>
        </div>
      </div>`;
    const cb = card.querySelector("input[type=checkbox]");
    function setSelected(on){{
      if (on) state.selected.add(p.pmid); else state.selected.delete(p.pmid);
      cb.checked = on; card.classList.toggle("selected", on);
      updateCounts(); syncSelectAll(shown); renderFinal();
    }}
    cb.addEventListener("click", e => e.stopPropagation());
    cb.addEventListener("change", ()=> setSelected(cb.checked));
    card.addEventListener("click", ()=> setSelected(!cb.checked));
    const toggleBtn = card.querySelector(".toggle-abs");
    toggleBtn.addEventListener("click", (e)=>{{
      e.stopPropagation();
      const exp = card.classList.toggle("expanded");
      toggleBtn.textContent = exp ? "Show less" : "Show more";
    }});
    const reasonToggle = card.querySelector(".reason-toggle");
    const reasonBox = card.querySelector(".reason-box");
    reasonToggle.addEventListener("click", (e)=>{{
      e.stopPropagation();
      reasonBox.hidden = !reasonBox.hidden;
      if (!reasonBox.hidden) reasonBox.focus();
    }});
    reasonBox.addEventListener("click", e => e.stopPropagation());
    reasonBox.addEventListener("input", ()=>{{
      const v = reasonBox.value.trim();
      if (v) state.reasons[p.pmid] = reasonBox.value; else delete state.reasons[p.pmid];
      reasonToggle.textContent = v ? "edit reason" : "+ reason";
      renderFinal();
    }});
    if (state.reasons[p.pmid]) reasonBox.hidden = false;
    list.appendChild(card);
  }});

  document.getElementById("totalCount").textContent = PAPERS.length;
  syncSelectAll(shown);
  updateCounts();
}}

function syncSelectAll(shown){{
  const box = document.getElementById("selectAll");
  if (shown.length === 0){{ box.checked = false; box.indeterminate = false; return; }}
  const selectedShown = shown.filter(p=>state.selected.has(p.pmid)).length;
  box.checked = selectedShown === shown.length;
  box.indeterminate = selectedShown > 0 && selectedShown < shown.length;
}}
function updateCounts(){{
  document.getElementById("selCount").textContent = state.selected.size;
}}

function renderFinal(){{
  const n = state.selected.size;
  const excludedCount = PAPERS.length - n;
  document.getElementById("finalN").textContent = n;
  document.getElementById("finalExcl").textContent = `\\u2212${{excludedCount}} excluded at manual triage`;

  const emptyEl = document.getElementById("finalEmpty");
  const listEl = document.getElementById("finalList");
  const chosen = PAPERS.filter(p => state.selected.has(p.pmid));
  emptyEl.hidden = chosen.length !== 0;
  listEl.innerHTML = chosen.map(p => `
    <div class="final-row"><div class="t">
      <div class="ti">${{escapeHtml(p.title)}}</div>
      <div class="sub">PMID ${{escapeHtml(p.pmid)}} &middot; ${{escapeHtml(p.journal)}}${{p.year ? ", " + escapeHtml(String(p.year)) : ""}}</div>
    </div></div>`).join("");

  const excluded = PAPERS.filter(p => !state.selected.has(p.pmid));
  const exclSection = document.getElementById("exclSection");
  const exclList = document.getElementById("exclList");
  exclSection.hidden = excluded.length === 0;
  exclList.innerHTML = excluded.map(p => `
    <div class="excl-row">
      <div class="ti">${{escapeHtml(p.title)}}</div>
      <div class="sub">PMID ${{escapeHtml(p.pmid)}} &middot; ${{escapeHtml(p.journal)}}${{p.year ? ", " + escapeHtml(String(p.year)) : ""}}</div>
      <div class="rs${{state.reasons[p.pmid] ? "" : " no-reason"}}">${{
        state.reasons[p.pmid] ? escapeHtml(state.reasons[p.pmid]) : "no reason given"
      }}</div>
    </div>`).join("");

  updateJsonPreview();
}}

function buildTriageJson(){{
  const decisions = PAPERS.map(p => ({{
    pmid: p.pmid,
    doi: p.doi,
    pmcid: p.pmcid,
    title: p.title,
    authors: p.authors_list,
    journal: p.journal,
    year: p.year || null,
    volume: p.volume,
    issue: p.issue,
    pages: p.pages,
    elocation_id: p.elocation_id,
    publication_types: p.pub_types,
    mesh_and_keywords: p.keywords,
    abstract: p.abstract,
    included: state.selected.has(p.pmid),
    reason: state.selected.has(p.pmid) ? null : (state.reasons[p.pmid] || null),
  }}));
  return {{
    schema: "paper-rag.triage/1",
    generated_by: "scripts/lib/triage_render.py",
    search_dir: SEARCH_DIR,
    triaged_at: new Date().toISOString(),
    search: SEARCH_META,
    decisions,
    summary: {{
      total: PAPERS.length,
      included: decisions.filter(d=>d.included).length,
      excluded: decisions.filter(d=>!d.included).length,
      excluded_with_reason: decisions.filter(d=>!d.included && d.reason).length,
    }},
  }};
}}
function updateJsonPreview(){{
  document.getElementById("jsonPreview").textContent = JSON.stringify(buildTriageJson(), null, 2);
}}

function flashHint(text){{
  const hint = document.getElementById("savedHint");
  hint.textContent = text;
  hint.classList.add("show");
  setTimeout(()=>hint.classList.remove("show"), 3000);
}}

async function saveTriageJson(){{
  const json = JSON.stringify(buildTriageJson(), null, 2);

  // Served by `python scripts/triage.py <search_dir> --serve`: POST writes
  // triage.json straight into search_dir on the server side, no dialog at
  // all. This is the only path that's truly automatic; both fallbacks below
  // need the user to interact with a picker or a downloads folder.
  if (location.protocol === "http:" || location.protocol === "https:"){{
    try{{
      const res = await fetch("/save", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: json,
      }});
      const data = await res.json();
      if (res.ok && data.ok){{
        flashHint("saved to " + data.path);
        return;
      }}
      // fall through to the fallbacks below (e.g. page opened via a plain
      // static file server with no /save route wired up)
    }}catch(err){{
      // fall through
    }}
  }}

  // File System Access API: writes straight into a folder you pick once
  // (no Downloads detour). Chromium-only, and only available on a secure
  // context — file:// pages fail the check, so this silently falls through
  // to the download fallback below there.
  if (window.showSaveFilePicker){{
    try{{
      const handle = await window.showSaveFilePicker({{
        suggestedName: "triage.json",
        types: [{{description: "Triage decisions", accept: {{"application/json": [".json"]}}}}],
      }});
      const writable = await handle.createWritable();
      await writable.write(json);
      await writable.close();
      flashHint("saved");
      return;
    }}catch(err){{
      if (err && err.name === "AbortError") return; // user cancelled the picker
      // fall through to the download fallback below
    }}
  }}

  const blob = new Blob([json], {{type: "application/json"}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "triage.json";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
  flashHint("downloaded — move it into " + SEARCH_DIR + "/");
}}
document.getElementById("saveBtn").addEventListener("click", saveTriageJson);

document.getElementById("selectAll").addEventListener("change", (e)=>{{
  const q = document.getElementById("q").value.trim();
  const journal = document.getElementById("journalFilter").value;
  const year = document.getElementById("yearFilter").value;
  const shown = PAPERS.filter(p => matches(p, q, journal, year));
  shown.forEach(p => e.target.checked ? state.selected.add(p.pmid) : state.selected.delete(p.pmid));
  render(); renderFinal();
}});
["q","journalFilter","yearFilter"].forEach(id=>{{
  document.getElementById(id).addEventListener("input", render);
  document.getElementById(id).addEventListener("change", render);
}});

function applyView(){{
  const isList = state.view === "list";
  document.getElementById("list").classList.toggle("view-list", isList);
  document.getElementById("gridViewBtn").classList.toggle("active", !isList);
  document.getElementById("gridViewBtn").setAttribute("aria-pressed", String(!isList));
  document.getElementById("listViewBtn").classList.toggle("active", isList);
  document.getElementById("listViewBtn").setAttribute("aria-pressed", String(isList));
}}
function setView(v){{
  state.view = v;
  try{{ localStorage.setItem("triage-view", v); }}catch(e){{}}
  applyView();
}}
document.getElementById("gridViewBtn").addEventListener("click", ()=> setView("grid"));
document.getElementById("listViewBtn").addEventListener("click", ()=> setView("list"));

populateFilters();
applyView();
render();
renderFinal();
</script>
"""


def build_triage_for_search_dir(sdir: Path, payload: dict, pmids: list[str], label: str | None) -> dict:
    """Fetch real citation metadata for every PMID and write sdir/triage.html.
    Records whose metadata fetch fails or whose title is missing are excluded.
    Returns a JSON-able summary (n_papers, n_metadata_errors, n_missing_title,
    missing_title_pmids, errors, triage_html)."""
    papers = []
    errors = []
    missing_title = []
    for pmid in pmids:
        try:
            meta = fetch_lib.fetch_citation_metadata(pmid)
        except Exception as exc:
            errors.append({"pmid": pmid, "error": str(exc)})
            continue
        # Records without a title are excluded from triage entirely.
        if not (meta.get("title") or "").strip():
            missing_title.append(pmid)
            continue
        papers.append(meta)

    html = render_triage_html(dict(payload, search_dir=str(sdir)), papers, label=label)
    out_path = sdir / "triage.html"
    out_path.write_text(html)

    return {
        "triage_html": str(out_path),
        "n_papers": len(papers),
        "n_metadata_errors": len(errors),
        "n_missing_title": len(missing_title),
        "missing_title_pmids": missing_title,
        "errors": errors,
    }
