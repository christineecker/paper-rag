---
title: Searching PubMed
description: Compile a reproducible Boolean PubMed query from structured concepts and get back a deduplicated PMID set, before you ingest anything.
---

# Searching PubMed

`/paper-rag:pubmed-search` queries **PubMed itself**, not your local library —
`/paper-rag:ask` is for questions about papers you've already ingested. Use
`/paper-rag:pubmed-search` to build a candidate PMID list first, then feed the PMIDs you want
into `/paper-rag:ingest`.

This tutorial builds a search from scratch: a raw query, then a structured concept
search with MeSH heading validation, then a narrower one using sensitivity settings.

## Step 1: A direct query

If you already know PubMed's query syntax, pass it straight through:

```
/paper-rag:pubmed-search --mode direct --query 'metformin[Title/Abstract] AND "Diabetes Mellitus, Type 2"[MeSH Terms]'
```

`direct` mode does no rewriting — only whitespace/line-ending cleanup — so what you
write is exactly what's sent to PubMed's ESearch API. Expected output (trimmed):

```json
{
  "pmids": ["...", "..."],
  "pubmed_query": "metformin[Title/Abstract] AND \"Diabetes Mellitus, Type 2\"[MeSH Terms]",
  "mode": "direct",
  "total_count": 1842,
  "returned_count": 1000,
  "truncated": true,
  "warnings": ["result set truncated to 1000 of 1842 total PubMed hits"],
  "provenance": { "source": "NCBI PubMed ESearch", "query_translation": "...", "...": "..." }
}
```

`truncated: true` plus the warning tells you there were more hits than `--max-results`
(default 1000) returned. Raise it if you need the rest:

```
/paper-rag:pubmed-search --mode direct --query '...' --max-results 3000
```

## Step 2: A structured concept search

Most of the time you don't have hand-written PubMed syntax — you have a population and
a modality/intervention in mind. `concepts` mode builds the Boolean query for you: terms
inside one concept are OR'd together (they're synonyms), and separate concepts are
AND'd (they must all match).

You can hand-draft that concepts JSON yourself:

```
/paper-rag:pubmed-search --mode concepts --concepts '[
  {"name": "population", "terms": ["autism", "autism spectrum disorder"]},
  {"name": "modality", "terms": ["MRI", "structural MRI"]}
]'
```

...or just ask a plain question and let Claude draft the concepts for you:

```
/paper-rag:pubmed-search does structural MRI differ in autism?
```

Claude extracts the concepts (population, intervention, outcome, etc. — using a
PICO/PECO/PCC framework where it fits) and calls `/paper-rag:pubmed-search --mode concepts`
on your behalf, with the same compiled `pubmed_query` output shown below.

<figure class="fw-compare">
  <div class="fw-grid">
    <div class="fw-card">
      <h3>PICO <small>intervention</small></h3>
      <p>Does a treatment or intervention change an outcome? RCTs, drug trials, therapy comparisons.</p>
      <dl>
        <div><dt>P</dt><dd>Population<span>who's studied</span></dd></div>
        <div><dt>I</dt><dd>Intervention<span>what's done to them</span></dd></div>
        <div><dt>C</dt><dd>Comparison<span>vs. what — often dropped</span></dd></div>
        <div><dt>O</dt><dd>Outcome<span>what's measured</span></dd></div>
      </dl>
    </div>
    <div class="fw-card">
      <h3>PECO <small>exposure</small></h3>
      <p>Does an exposure or risk factor associate with an outcome? Observational studies, no active intervention.</p>
      <dl>
        <div><dt>P</dt><dd>Population<span>who's studied</span></dd></div>
        <div><dt>E</dt><dd>Exposure<span>what they're exposed to</span></dd></div>
        <div><dt>C</dt><dd>Comparison<span>vs. unexposed — often dropped</span></dd></div>
        <div><dt>O</dt><dd>Outcome<span>what's measured</span></dd></div>
      </dl>
    </div>
    <div class="fw-card">
      <h3>PCC <small>scoping</small></h3>
      <p>What's the landscape of a topic? No fixed outcome — mapping evidence, not testing an effect.</p>
      <dl>
        <div><dt>P</dt><dd>Population<span>who's studied</span></dd></div>
        <div><dt>C</dt><dd>Concept<span>the phenomenon of interest</span></dd></div>
        <div><dt>C</dt><dd>Context<span>setting, geography, care level</span></dd></div>
      </dl>
    </div>
  </div>
  <figcaption>All three compile to the same thing in <code>/paper-rag:pubmed-search --mode concepts</code>: a list of <code>{name, terms}</code> objects — <code>name</code> is a free-text label, not a fixed vocabulary. <b>PCC has no <code>outcome</code> field</b>, which is the one structural difference from PICO/PECO, not just a naming swap.</figcaption>
</figure>

Look at `pubmed_query` in the output — this is the compiled, reproducible query, saved
alongside the PMIDs so you (or anyone else) can re-run the exact same search later:

```json
"pubmed_query": "(\"Autism Spectrum Disorder\"[MeSH Terms] OR \"Autistic Disorder\"[MeSH Terms] OR autism[Title/Abstract] OR \"autism spectrum disorder\"[Title/Abstract]) AND (MRI[Title/Abstract] OR \"structural MRI\"[Title/Abstract])"
```

Notice two things happened automatically:

- **MeSH validation**: `autism` matched a real MeSH descriptor (`Autistic Disorder`),
  so it was tagged `[MeSH Terms]` *in addition to* the raw term as `[Title/Abstract]` —
  never instead of it, and never for a term that didn't validate. `MRI` had no MeSH
  match, so it stayed `[Title/Abstract]`-only.
- **Deduplication**: if two terms in a concept normalize to the same thing
  case-insensitively, only one clause is kept.

If a search returns a warning like:

```
"no local MeSH index found; all terms compiled as [Title/Abstract] only. Run `python scripts/mesh_update.py` to enable MeSH heading validation."
```

...run `/paper-rag:mesh-update` once (see [below](#one-time-setup-the-mesh-index)),
then re-run the search — no other change needed.

### Marking a concept optional

Set `"required": false` on a concept you only want included some of the time —
`sensitivity: broad` drops it, `balanced`/`precise` keep it:

```
/paper-rag:pubmed-search --mode concepts --concepts '[
  {"name": "population", "terms": ["autism"]},
  {"name": "context", "terms": ["prevalence"], "required": false}
]'
```

## Step 3: Tune recall vs. precision with sensitivity

`--sensitivity` controls how much the concept compiler narrows the query:

| Sensitivity | Behavior |
|---|---|
| `broad` (widest) | Only `required: true` concepts are included; generous synonyms. |
| `balanced` (default) | All concepts included, MeSH + free-text terms as given. |
| `precise` (narrowest) | All concepts included, but short/ambiguous single-word terms (e.g. bare abbreviations like `MRI`) are dropped in favor of full phrases. Always adds a warning that this can reduce recall. |

```
/paper-rag:pubmed-search --mode concepts --concepts '[{"name": "modality", "terms": ["MRI", "magnetic resonance imaging"]}]' --sensitivity precise
```

Here `precise` keeps `magnetic resonance imaging` (a phrase) and drops the bare `MRI`
abbreviation, since it's short enough to collide with unrelated meanings.

## Step 4: Ingest what you found

`/paper-rag:pubmed-search` only returns PMIDs — it never ingests anything. Feed the ones you
want into your library:

```
/paper-rag:ingest 31978945
```

See [Ingesting Papers](/guide/ingest) for what happens next (full-text resolution,
chunking, embedding).

## One-time setup: the MeSH index

MeSH heading validation needs a local index built from NLM's own descriptor data — this
is a deliberate, explicit step, not something that happens silently on first search,
because the source file is 300MB+ and takes a few minutes to download and parse:

```
/paper-rag:mesh-update
```

This downloads `desc<year>.xml` (NLM's public-domain MeSH descriptor set) to
`~/.cache/paper-rag/mesh` and builds a SQLite lookup alongside it — independent of any
paper-rag home, shared across all your libraries. Without it, `/paper-rag:pubmed-search` still
works; every term just stays `[Title/Abstract]`-only (no `[MeSH Terms]` tag), which is
weaker recall but never wrong.

Re-run with `--force` to rebuild against a fresh MeSH release; `--year YYYY` targets a
specific year instead of the current one.

## What a natural-language question doesn't get you (yet)

There's no `question` mode that takes "does metformin reduce cardiovascular risk in
type 2 diabetes?" and turns it into concepts automatically — that needs an LLM, and
paper-rag has none built in. If you ask Claude a question like that, it extracts the
concepts itself (population, intervention, outcome, etc. — using a PICO/PECO/PCC
framework where it fits) and calls `/paper-rag:pubmed-search --mode concepts` on your behalf,
rather than guessing at raw PubMed syntax.

<figure>
  <div class="fd-wrap">
    <svg class="fd-diagram" viewBox="0 0 800 396" role="img" aria-labelledby="fd-t fd-d">
      <title id="fd-t">Three questions to PMIDs via PICO, PECO, and PCC</title>
      <desc id="fd-d">A PICO-shaped intervention question, a PECO-shaped exposure question, and a PCC-shaped scoping question are each extracted into a concepts JSON, submitted to paper-rag search mode concepts, and returned as a distinct PMID set.</desc>
      <defs>
        <marker id="fd-arrow" markerWidth="8" markerHeight="7" refX="7" refY="3.5" orient="auto">
          <polygon points="0 0, 8 3.5, 0 7" class="fd-arrowhead"/>
        </marker>
      </defs>
      <text x="91" y="14" class="fd-lane" text-anchor="middle">Question</text>
      <text x="235" y="14" class="fd-lane" text-anchor="middle">01 / Framework</text>
      <text x="385" y="14" class="fd-lane" text-anchor="middle">02 / Concepts JSON</text>
      <text x="575" y="14" class="fd-lane" text-anchor="middle">03 / search --mode concepts</text>
      <text x="730" y="14" class="fd-lane" text-anchor="middle">04 / PMIDs</text>
      <!-- PICO row (center y=73) -->
      <rect x="16" y="28" width="150" height="90" rx="8" class="fd-box"/>
      <text x="91" y="50" class="fd-sub" text-anchor="middle">"Does metformin vs</text>
      <text x="91" y="62" class="fd-sub" text-anchor="middle">placebo reduce</text>
      <text x="91" y="74" class="fd-sub" text-anchor="middle">cardiovascular events</text>
      <text x="91" y="86" class="fd-sub" text-anchor="middle">in adults with T2D?"</text>
      <path d="M 166 73 L 190 73" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="190" y="37" width="90" height="72" rx="8" class="fd-box fd-box-accent"/>
      <text x="235" y="68" class="fd-title" text-anchor="middle">PICO</text>
      <text x="235" y="82" class="fd-sub" text-anchor="middle">P · I · C · O</text>
      <path d="M 280 73 L 300 73" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="300" y="28" width="170" height="90" rx="8" class="fd-box"/>
      <text x="313" y="50" class="fd-sub" font-size="9">population:</text>
      <text x="313" y="61" class="fd-title" font-size="9.5">type 2 diabetes</text>
      <text x="313" y="76" class="fd-sub" font-size="9">intervention: metformin</text>
      <text x="313" y="91" class="fd-sub" font-size="9">outcome: CV events</text>
      <text x="313" y="105" class="fd-sub" font-size="8" opacity=".65">(comparison usually dropped)</text>
      <path d="M 470 73 L 490 73" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="490" y="37" width="170" height="72" rx="8" class="fd-box"/>
      <text x="575" y="58" class="fd-title" text-anchor="middle" font-size="9.5">ESearch:</text>
      <text x="575" y="72" class="fd-sub" text-anchor="middle">(MeSH ∨ text)</text>
      <text x="575" y="84" class="fd-sub" text-anchor="middle">∧ (text) ∧ (text)</text>
      <path d="M 660 73 L 680 73" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="680" y="37" width="104" height="72" rx="8" class="fd-box"/>
      <text x="732" y="68" class="fd-title" text-anchor="middle" font-size="15">412</text>
      <text x="732" y="83" class="fd-sub" text-anchor="middle">pmids</text>
      <!-- PECO row (center y=205) -->
      <rect x="16" y="160" width="150" height="90" rx="8" class="fd-box"/>
      <text x="91" y="182" class="fd-sub" text-anchor="middle">"Is prenatal valproate</text>
      <text x="91" y="194" class="fd-sub" text-anchor="middle">exposure, vs. none,</text>
      <text x="91" y="206" class="fd-sub" text-anchor="middle">associated with autism</text>
      <text x="91" y="218" class="fd-sub" text-anchor="middle">in children?"</text>
      <path d="M 166 205 L 190 205" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="190" y="169" width="90" height="72" rx="8" class="fd-box fd-box-accent"/>
      <text x="235" y="200" class="fd-title" text-anchor="middle">PECO</text>
      <text x="235" y="214" class="fd-sub" text-anchor="middle">P · E · C · O</text>
      <path d="M 280 205 L 300 205" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="300" y="160" width="170" height="90" rx="8" class="fd-box"/>
      <text x="313" y="182" class="fd-sub" font-size="9">population: children</text>
      <text x="313" y="197" class="fd-sub" font-size="9">exposure:</text>
      <text x="313" y="208" class="fd-title" font-size="9.5">prenatal valproate</text>
      <text x="313" y="223" class="fd-sub" font-size="9">outcome: autism</text>
      <path d="M 470 205 L 490 205" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="490" y="169" width="170" height="72" rx="8" class="fd-box"/>
      <text x="575" y="190" class="fd-title" text-anchor="middle" font-size="9.5">ESearch:</text>
      <text x="575" y="204" class="fd-sub" text-anchor="middle">(MeSH ∨ text)</text>
      <text x="575" y="216" class="fd-sub" text-anchor="middle">∧ (text) ∧ (text)</text>
      <path d="M 660 205 L 680 205" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="680" y="169" width="104" height="72" rx="8" class="fd-box"/>
      <text x="732" y="200" class="fd-title" text-anchor="middle" font-size="15">88</text>
      <text x="732" y="215" class="fd-sub" text-anchor="middle">pmids</text>
      <!-- PCC row (center y=337) -->
      <rect x="16" y="292" width="150" height="90" rx="8" class="fd-box"/>
      <text x="91" y="314" class="fd-sub" text-anchor="middle">"What does the literature</text>
      <text x="91" y="326" class="fd-sub" text-anchor="middle">say about structural MRI</text>
      <text x="91" y="338" class="fd-sub" text-anchor="middle">findings in autistic adults,</text>
      <text x="91" y="350" class="fd-sub" text-anchor="middle">in clinical settings?"</text>
      <path d="M 166 337 L 190 337" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="190" y="301" width="90" height="72" rx="8" class="fd-box fd-box-accent"/>
      <text x="235" y="332" class="fd-title" text-anchor="middle">PCC</text>
      <text x="235" y="346" class="fd-sub" text-anchor="middle" font-size="7.5">P · Concept · Context</text>
      <path d="M 280 337 L 300 337" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="300" y="292" width="170" height="90" rx="8" class="fd-box"/>
      <text x="313" y="314" class="fd-sub" font-size="9">population: autistic adults</text>
      <text x="313" y="329" class="fd-sub" font-size="9">concept:</text>
      <text x="313" y="340" class="fd-title" font-size="9.5">structural MRI</text>
      <text x="313" y="355" class="fd-sub" font-size="9">context: clinical settings</text>
      <path d="M 470 337 L 490 337" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="490" y="301" width="170" height="72" rx="8" class="fd-box"/>
      <text x="575" y="322" class="fd-title" text-anchor="middle" font-size="9.5">ESearch:</text>
      <text x="575" y="336" class="fd-sub" text-anchor="middle">(MeSH ∨ text)</text>
      <text x="575" y="348" class="fd-sub" text-anchor="middle">∧ (text) ∧ (text)</text>
      <path d="M 660 337 L 680 337" class="fd-line" marker-end="url(#fd-arrow)"/>
      <rect x="680" y="301" width="104" height="72" rx="8" class="fd-box"/>
      <text x="732" y="332" class="fd-title" text-anchor="middle" font-size="15">156</text>
      <text x="732" y="347" class="fd-sub" text-anchor="middle">pmids</text>
    </svg>
  </div>
  <figcaption>The same pipeline run three ways from three differently-shaped questions — each framework's concepts JSON compiles to its own query, and each query returns its own PMID set.</figcaption>
</figure>

## What's next

- [Ingesting Papers](/guide/ingest) — turn a PMID into a searchable, cited paper.
- [Concepts](/concepts) — how doc_key identity and metadata work once ingested.
- [CLI Reference](/reference/cli) — every flag for `search_pubmed.py` and `mesh_update.py`.

<style scoped>
figure {
  margin: 24px 0;
  background: var(--vp-c-bg-alt);
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  padding: 20px 16px 16px;
  overflow-x: auto;
}
figcaption {
  font-family: ui-monospace, Menlo, Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
  font-size: 12.5px;
  color: var(--vp-c-text-2);
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--vp-c-divider);
  line-height: 1.5;
}
figcaption b { color: var(--vp-c-text-1); font-weight: 600; }
figcaption code { font-size: 0.95em; }

.fw-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
@media (max-width: 720px) { .fw-grid { grid-template-columns: 1fr; } }
.fw-card {
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  padding: 14px 16px;
}
.fw-card h3 { margin: 0 0 8px; font-size: 15px; border: none; padding: 0; display: flex; align-items: baseline; gap: 8px; }
.fw-card h3 small { font-weight: 400; font-size: 11px; color: var(--vp-c-text-3); text-transform: uppercase; letter-spacing: 0.04em; }
.fw-card p { margin: 0 0 12px; font-size: 13px; color: var(--vp-c-text-2); line-height: 1.5; }
.fw-card dl { margin: 0; display: flex; flex-direction: column; gap: 6px; }
.fw-card dl div { display: grid; grid-template-columns: 18px 1fr; gap: 8px; align-items: baseline; }
.fw-card dt { color: var(--vp-c-brand-1); font-family: ui-monospace, Menlo, Monaco, monospace; font-size: 13px; font-weight: 600; }
.fw-card dd { margin: 0; font-size: 13px; color: var(--vp-c-text-1); }
.fw-card dd span { display: block; font-size: 11.5px; color: var(--vp-c-text-3); font-weight: 400; }

.fd-wrap { overflow-x: auto; }
.fd-diagram { display: block; min-width: 640px; }
.fd-diagram text { font-family: ui-monospace, Menlo, Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace; }
.fd-lane { fill: var(--vp-c-text-3); font-size: 9px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
.fd-box { fill: var(--vp-c-bg); stroke: var(--vp-c-divider); stroke-width: 1.4; }
.fd-box-accent { stroke: var(--vp-c-brand-1); }
.fd-title { fill: var(--vp-c-text-1); font-size: 11px; font-weight: 600; }
.fd-sub { fill: var(--vp-c-text-3); font-size: 8.5px; }
.fd-line { stroke: var(--vp-c-divider); stroke-width: 1.4; fill: none; }
.fd-arrowhead { fill: var(--vp-c-divider); }
</style>
