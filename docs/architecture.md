---
title: Architecture
description: How ingest, ask, and the bibliographic commands move data through paper-rag — hybrid retrieval versus a direct metadata scan — plus the on-disk RAG home layout.
---

# paper-rag

<p class="lede"><b class="accent">ingest</b> writes chunks and citation metadata in; <b class="accent">ask</b> reads chunks back through hybrid retrieval; <b class="accent">cite</b>/<b class="accent">mine</b> read the metadata directly, skipping the vector store entirely.</p>

<section>
  <h2>ingest → chroma + bm25</h2>
  <figure>
    <div class="archify-diagram">
<svg viewBox="0 0 1068 760" role="img" lang="en" aria-labelledby="archify-diagram-title-1 archify-diagram-description-1" data-preset="classic" data-quality-profile="showcase">
  <title id="archify-diagram-title-1">paper-rag ingest pipeline</title>
  <desc id="archify-diagram-description-1">A source (PMID, URL, or local file) is fetched, converted by docling, chunked, and figures extracted, then upserted into a Chroma collection keyed by embedding model, which triggers a full rebuild of the BM25 lexical index for that same collection. In parallel, the same fetch step pulls citation metadata and writes it straight to metadata.json in the home directory, bypassing conversion, chunking, and both indexes entirely.</desc>
  <defs>
    <marker id="arrowhead-1" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-default" />
    </marker>
    <marker id="arrowhead-emphasis-1" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-emphasis" />
    </marker>
    <marker id="arrowhead-dashed-1" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-dashed" />
    </marker>
    <pattern id="grid-1" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" class="c-grid" stroke-width="0.5"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#grid-1)" />
  <rect x="16" y="46" width="168" height="640" rx="10" class="c-lane" stroke-width="1"/>
  <text x="100" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">01 / Source</text>
  <rect x="231" y="46" width="168" height="640" rx="10" class="c-lane" stroke-width="1"/>
  <text x="315" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">02 / Fetch</text>
  <rect x="446" y="46" width="168" height="640" rx="10" class="c-lane" stroke-width="1"/>
  <text x="530" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">03 / Convert + split</text>
  <rect x="661" y="46" width="168" height="640" rx="10" class="c-lane" stroke-width="1"/>
  <text x="745" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">04 / Index</text>
  <rect x="876" y="46" width="168" height="640" rx="10" class="c-lane" stroke-width="1"/>
  <text x="960" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">05 / On disk</text>
  <path d="M 156 271 L 259 271" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-1)"/>
  <path d="M 371 271 L 474 271" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-1)"/>
  <path d="M 586 264 L 637.5 264 L 637.5 157 L 689 157" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-1)"/>
  <path d="M 586 278 L 637.5 278 L 637.5 385 L 689 385" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-1)"/>
  <path d="M 801 157 L 904 157" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-1)"/>
  <path d="M 801 385 L 890 385" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-1)"/>
  <path d="M 960 186 L 916 186 L 916 242 L 960 242" class="a-dashed" stroke-width="1.4" marker-end="url(#arrowhead-dashed-1)"/>
  <path d="M 371 271 L 371 578 L 895 578 L 895 523" class="a-dashed" stroke-width="1.4" marker-end="url(#arrowhead-dashed-1)"/>
  <path d="M 960 494 L 960 414" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-1)"/>
  <g><title>Source · pmid · url · path</title>
    <rect x="44" y="242" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="44" y="242" width="112" height="58" rx="6" class="c-external" stroke-width="1.5"/>
    <text x="100" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">Source</text>
    <text x="100" y="279" class="t-muted" font-size="7" text-anchor="middle">pmid · url · path</text>
  </g>
  <g><title>fetch.py · resolve doc_key</title>
    <rect x="259" y="242" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="259" y="242" width="112" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="315" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">fetch.py</text>
    <text x="315" y="279" class="t-muted" font-size="7" text-anchor="middle">resolve doc_key</text>
  </g>
  <g><title>convert · docling → DoclingDocument</title>
    <rect x="474" y="242" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="474" y="242" width="112" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="530" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">convert</text>
    <text x="530" y="279" class="t-muted" font-size="6.9" text-anchor="middle">docling → DoclingDocument</text>
  </g>
  <g><title>chunk · HybridChunker</title>
    <rect x="689" y="128" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="689" y="128" width="112" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="745" y="149" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">chunk</text>
    <text x="745" y="165" class="t-muted" font-size="7" text-anchor="middle">HybridChunker</text>
  </g>
  <g><title>figures · PDF only · fig_N.png</title>
    <rect x="689" y="356" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="689" y="356" width="112" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="745" y="377" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">figures</text>
    <text x="745" y="393" class="t-muted" font-size="7" text-anchor="middle">PDF only · fig_N.png</text>
  </g>
  <g><title>chroma · papers__{model}</title>
    <rect x="904" y="128" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="904" y="128" width="112" height="58" rx="6" class="c-database" stroke-width="1.5"/>
    <text x="960" y="149" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">chroma</text>
    <text x="960" y="165" class="t-muted" font-size="7" text-anchor="middle">papers__{model}</text>
  </g>
  <g><title>bm25 · {model}.pkl</title>
    <rect x="904" y="242" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="904" y="242" width="112" height="58" rx="6" class="c-database" stroke-width="1.5"/>
    <text x="960" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">bm25</text>
    <text x="960" y="279" class="t-muted" font-size="7" text-anchor="middle">{model}.pkl</text>
  </g>
  <g><title>home dir · papers/&lt;doc_key&gt;/</title>
    <rect x="890" y="356" width="140" height="58" rx="6" class="c-mask"/>
    <rect x="890" y="356" width="140" height="58" rx="6" class="c-external" stroke-width="1.5"/>
    <text x="960" y="377" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">home dir</text>
    <text x="960" y="393" class="t-muted" font-size="7" text-anchor="middle">papers/&lt;doc_key&gt;/</text>
  </g>
  <g><title>metadata.json · authors · year · doi</title>
    <rect x="895" y="494" width="130" height="58" rx="6" class="c-mask"/>
    <rect x="895" y="494" width="130" height="58" rx="6" class="c-database" stroke-width="1.5"/>
    <text x="960" y="515" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">metadata.json</text>
    <text x="960" y="531" class="t-muted" font-size="7" text-anchor="middle">authors · year · doi</text>
  </g>
  <g><rect x="167.2" y="250" width="80.6" height="27" rx="4" class="c-mask"/>
    <text x="207.5" y="261" class="t-backend" font-size="8" text-anchor="middle">resolve</text>
    <text x="207.5" y="272" class="t-dim" font-size="7" text-anchor="middle">pmid or sha256</text>
  </g>
  <g><rect x="384.65" y="250" width="75.7" height="27" rx="4" class="c-mask"/>
    <text x="422.5" y="261" class="t-muted" font-size="8" text-anchor="middle">full text</text>
    <text x="422.5" y="272" class="t-dim" font-size="7" text-anchor="middle">docling input</text>
  </g>
  <g><rect x="611.9" y="189.5" width="51.2" height="16" rx="4" class="c-mask"/>
    <text x="637.5" y="200.5" class="t-muted" font-size="8" text-anchor="middle">sections</text>
  </g>
  <g><rect x="599.65" y="310.5" width="75.7" height="16" rx="4" class="c-mask"/>
    <text x="637.5" y="321.5" class="t-muted" font-size="8" text-anchor="middle">picture items</text>
  </g>
  <g><rect x="807.3" y="136" width="90.4" height="27" rx="4" class="c-mask"/>
    <text x="852.5" y="147" class="t-backend" font-size="8" text-anchor="middle">upsert chunks</text>
    <text x="852.5" y="158" class="t-dim" font-size="7" text-anchor="middle">keyed by doc_key</text>
  </g>
  <g><rect x="817.45" y="364" width="56.1" height="16" rx="4" class="c-mask"/>
    <text x="845.5" y="375" class="t-muted" font-size="8" text-anchor="middle">fig_N.png</text>
  </g>
  <g><rect x="856.1" y="193" width="119.8" height="27" rx="4" class="c-mask"/>
    <text x="916" y="204" class="t-messagebus" font-size="8" text-anchor="middle">full rebuild</text>
    <text x="916" y="215" class="t-dim" font-size="7" text-anchor="middle">IDF needs whole corpus</text>
  </g>
  <g><rect x="529" y="583" width="208" height="27" rx="4" class="c-mask"/>
    <text x="633" y="594" class="t-messagebus" font-size="8" text-anchor="middle">citation fetch</text>
    <text x="633" y="605" class="t-dim" font-size="7" text-anchor="middle">bypasses convert · chunk · chroma · bm25</text>
  </g>
  <g><rect x="905" y="473" width="110" height="16" rx="4" class="c-mask"/>
    <text x="960" y="484" class="t-muted" font-size="8" text-anchor="middle">writes metadata.json</text>
  </g>
  <g>
    <text x="40" y="704" class="t-primary" font-size="12" font-weight="650">Legend</text>
    <path d="M 40 721 L 74 721" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-1)"/>
    <text x="83" y="724" class="t-muted" font-size="10" font-weight="500">primary data</text>
    <path d="M 165 721 L 199 721" class="a-dashed" stroke-width="1.4" marker-end="url(#arrowhead-dashed-1)"/>
    <text x="208" y="724" class="t-muted" font-size="10" font-weight="500">async batch</text>
    <rect x="285" y="716" width="14" height="9" rx="2" class="c-database" stroke-width="1"/>
    <text x="307" y="724" class="t-muted" font-size="10" font-weight="500">data store</text>
    <path d="M 400 721 L 434 721" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-1)"/>
    <text x="443" y="724" class="t-muted" font-size="10" font-weight="500">data flow</text>
  </g>
</svg>
    </div>
    <figcaption>
      <b>doc_key</b> (PMID or sha256) is written on every chroma entry and reused for delete-then-reinsert dedup.
      Every ingest that touches chroma also <b>fully rebuilds</b> the BM25 index — since BM25's IDF weights need the whole corpus, not just the new chunks.
      <b>metadata.json</b> (dashed path) is written straight from the citation fetch — it never enters either index, which is what lets <code>cite.py</code>/<code>mine.py</code> answer without touching them (next figure).
    </figcaption>
  </figure>
</section>

<section>
  <h2>ask → hybrid retrieval</h2>
  <figure>
    <div class="archify-diagram">
<svg viewBox="0 0 1068 640" role="img" lang="en" aria-labelledby="archify-diagram-title-2 archify-diagram-description-2" data-preset="classic" data-quality-profile="showcase">
  <title id="archify-diagram-title-2">paper-rag hybrid retrieval</title>
  <desc id="archify-diagram-description-2">A question runs two parallel legs against the same collection, dense vector search through Chroma and lexical BM25 search, each leg producing a ranked candidate list; the two rankings are combined by reciprocal rank fusion into one ranked result set, which the ask command turns into a cited answer.</desc>
  <defs>
    <marker id="arrowhead-2" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-default" />
    </marker>
    <marker id="arrowhead-emphasis-2" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-emphasis" />
    </marker>
  </defs>
  <rect x="16" y="46" width="168" height="520" rx="10" class="c-lane" stroke-width="1"/>
  <text x="100" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">01 / Query</text>
  <rect x="231" y="46" width="168" height="520" rx="10" class="c-lane" stroke-width="1"/>
  <text x="315" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">02 / Two legs</text>
  <rect x="446" y="46" width="168" height="520" rx="10" class="c-lane" stroke-width="1"/>
  <text x="530" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">03 / Fuse</text>
  <rect x="661" y="46" width="168" height="520" rx="10" class="c-lane" stroke-width="1"/>
  <text x="745" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">04 / Result</text>
  <rect x="876" y="46" width="168" height="520" rx="10" class="c-lane" stroke-width="1"/>
  <text x="960" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">05 / Answer</text>
  <path d="M 156 264 L 207.5 264 L 207.5 157 L 259 157" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-2)"/>
  <path d="M 156 278 L 207.5 278 L 207.5 385 L 259 385" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-2)"/>
  <path d="M 371 157 L 418 157 L 418 264 L 465 264" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-2)"/>
  <path d="M 371 385 L 418 385 L 418 278 L 465 278" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-2)"/>
  <path d="M 595 271 L 689 271" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-2)"/>
  <path d="M 801 271 L 904 271" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-2)"/>
  <g><title>question · query.py "..."</title>
    <rect x="44" y="242" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="44" y="242" width="112" height="58" rx="6" class="c-frontend" stroke-width="1.5"/>
    <text x="100" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">question</text>
    <text x="100" y="279" class="t-muted" font-size="7" text-anchor="middle">query.py "..."</text>
  </g>
  <g><title>dense · chroma cosine ANN</title>
    <rect x="259" y="128" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="259" y="128" width="112" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="315" y="149" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">dense</text>
    <text x="315" y="165" class="t-muted" font-size="7" text-anchor="middle">chroma cosine ANN</text>
  </g>
  <g><title>lexical · bm25 over chunk text</title>
    <rect x="259" y="356" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="259" y="356" width="112" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="315" y="377" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">lexical</text>
    <text x="315" y="393" class="t-muted" font-size="7" text-anchor="middle">bm25 over chunk text</text>
  </g>
  <g><title>RRF fuse · Σ 1/(k+rank)</title>
    <rect x="465" y="242" width="130" height="58" rx="6" class="c-mask"/>
    <rect x="465" y="242" width="130" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="530" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">RRF fuse</text>
    <text x="530" y="279" class="t-muted" font-size="7" text-anchor="middle">Σ 1/(k+rank)</text>
  </g>
  <g><title>top k · ranked JSON</title>
    <rect x="689" y="242" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="689" y="242" width="112" height="58" rx="6" class="c-database" stroke-width="1.5"/>
    <text x="745" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">top k</text>
    <text x="745" y="279" class="t-muted" font-size="7" text-anchor="middle">ranked JSON</text>
  </g>
  <g><title>ask · cited answer</title>
    <rect x="904" y="242" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="904" y="242" width="112" height="58" rx="6" class="c-external" stroke-width="1.5"/>
    <text x="960" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">ask</text>
    <text x="960" y="279" class="t-muted" font-size="7" text-anchor="middle">cited answer</text>
  </g>
  <g><rect x="167.2" y="189.5" width="80.6" height="16" rx="4" class="c-mask"/>
    <text x="207.5" y="200.5" class="t-muted" font-size="8" text-anchor="middle">k·4 candidates</text>
  </g>
  <g><rect x="167.2" y="310.5" width="80.6" height="16" rx="4" class="c-mask"/>
    <text x="207.5" y="321.5" class="t-muted" font-size="8" text-anchor="middle">k·4 candidates</text>
  </g>
  <g><rect x="387.5" y="189.5" width="61" height="16" rx="4" class="c-mask"/>
    <text x="418" y="200.5" class="t-backend" font-size="8" text-anchor="middle">dense rank</text>
  </g>
  <g><rect x="382.6" y="310.5" width="70.8" height="16" rx="4" class="c-mask"/>
    <text x="418" y="321.5" class="t-backend" font-size="8" text-anchor="middle">lexical rank</text>
  </g>
  <g><rect x="609.05" y="250" width="65.9" height="16" rx="4" class="c-mask"/>
    <text x="642" y="261" class="t-backend" font-size="8" text-anchor="middle">fused score</text>
  </g>
  <g><rect x="809.75" y="250" width="85.5" height="16" rx="4" class="c-mask"/>
    <text x="852.5" y="261" class="t-muted" font-size="8" text-anchor="middle">context + cites</text>
  </g>
  <g>
    <text x="40" y="584" class="t-primary" font-size="12" font-weight="650">Legend</text>
    <path d="M 40 601 L 74 601" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-2)"/>
    <text x="83" y="604" class="t-muted" font-size="10" font-weight="500">primary data</text>
    <rect x="165" y="596" width="14" height="9" rx="2" class="c-database" stroke-width="1"/>
    <text x="187" y="604" class="t-muted" font-size="10" font-weight="500">data store</text>
    <path d="M 280 601 L 314 601" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-2)"/>
    <text x="323" y="604" class="t-muted" font-size="10" font-weight="500">data flow</text>
  </g>
</svg>
    </div>
    <figcaption>
      Both legs query the <b>same</b> collection; <code>--dense-only</code> / <code>--lexical-only</code> bypass fusion for debugging. <code>--where</code> filters (pmid, type) apply natively to the dense leg, post-hoc to the lexical leg — BM25 has no metadata filter of its own. Result JSON keeps each hit's dense rank and lexical rank alongside the fused score; <code>rrf_k</code> defaults to 60.
    </figcaption>
  </figure>
  <div class="note">
    <b>Falls back to dense-only</b> — with a warning — if a collection exists but its BM25 pickle doesn't (e.g. papers ingested before hybrid search shipped).
  </div>
</section>

<section>
  <h2>cite / mine → metadata.json, no index</h2>
  <figure>
    <div class="archify-diagram">
<svg viewBox="0 0 980 560" role="img" lang="en" aria-labelledby="archify-diagram-title-3 archify-diagram-description-3" data-preset="classic" data-quality-profile="showcase">
  <title id="archify-diagram-title-3">paper-rag cite / mine</title>
  <desc id="archify-diagram-description-3">cite.py and mine.py both glob metadata.json files directly across the home directory's papers folder, filtering in plain Python with no dense or lexical search involved, then produce either a BibTeX file or a filtered JSON list of matching papers.</desc>
  <defs>
    <marker id="arrowhead-3" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-default" />
    </marker>
    <marker id="arrowhead-emphasis-3" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" class="m-emphasis" />
    </marker>
  </defs>
  <rect x="16" y="46" width="168" height="440" rx="10" class="c-lane" stroke-width="1"/>
  <text x="100" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">01 / Metadata</text>
  <rect x="231" y="46" width="168" height="440" rx="10" class="c-lane" stroke-width="1"/>
  <text x="315" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">02 / Filter</text>
  <rect x="446" y="46" width="168" height="440" rx="10" class="c-lane" stroke-width="1"/>
  <text x="530" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">03 / Command</text>
  <rect x="661" y="46" width="168" height="440" rx="10" class="c-lane" stroke-width="1"/>
  <text x="745" y="68" class="t-dim" font-size="9" font-weight="600" text-anchor="middle">04 / Output</text>
  <path d="M 165 271 L 240 271" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-3)"/>
  <path d="M 390 264 L 422.5 264 L 422.5 157 L 455 157" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-3)"/>
  <path d="M 390 278 L 425 278 L 425 385 L 460 385" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-3)"/>
  <path d="M 605 157 L 689 157" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-3)"/>
  <path d="M 600 385 L 689 385" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-3)"/>
  <g><title>metadata.json · papers/*/&lt;key&gt;/</title>
    <rect x="35" y="242" width="130" height="58" rx="6" class="c-mask"/>
    <rect x="35" y="242" width="130" height="58" rx="6" class="c-database" stroke-width="1.5"/>
    <text x="100" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">metadata.json</text>
    <text x="100" y="279" class="t-muted" font-size="7" text-anchor="middle">papers/*/&lt;key&gt;/</text>
  </g>
  <g><title>glob + filter · plain python</title>
    <rect x="240" y="242" width="150" height="58" rx="6" class="c-mask"/>
    <rect x="240" y="242" width="150" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="315" y="263" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">glob + filter</text>
    <text x="315" y="279" class="t-muted" font-size="7" text-anchor="middle">plain python</text>
  </g>
  <g><title>cite.py · doc_key · pmid · --all</title>
    <rect x="455" y="128" width="150" height="58" rx="6" class="c-mask"/>
    <rect x="455" y="128" width="150" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="530" y="149" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">cite.py</text>
    <text x="530" y="165" class="t-muted" font-size="7" text-anchor="middle">doc_key · pmid · --all</text>
  </g>
  <g><title>mine.py · --author · --year</title>
    <rect x="460" y="356" width="140" height="58" rx="6" class="c-mask"/>
    <rect x="460" y="356" width="140" height="58" rx="6" class="c-backend" stroke-width="1.5"/>
    <text x="530" y="377" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">mine.py</text>
    <text x="530" y="393" class="t-muted" font-size="7" text-anchor="middle">--author · --year</text>
  </g>
  <g><title>refs.bib · .bib text → stdout</title>
    <rect x="689" y="128" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="689" y="128" width="112" height="58" rx="6" class="c-external" stroke-width="1.5"/>
    <text x="745" y="149" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">refs.bib</text>
    <text x="745" y="165" class="t-muted" font-size="7" text-anchor="middle">.bib text → stdout</text>
  </g>
  <g><title>matches · JSON → stdout</title>
    <rect x="689" y="356" width="112" height="58" rx="6" class="c-mask"/>
    <rect x="689" y="356" width="112" height="58" rx="6" class="c-external" stroke-width="1.5"/>
    <text x="745" y="377" class="t-primary" font-size="10" font-weight="600" text-anchor="middle">matches</text>
    <text x="745" y="393" class="t-muted" font-size="7" text-anchor="middle">JSON → stdout</text>
  </g>
  <g><rect x="185.5" y="250" width="34" height="16" rx="4" class="c-mask"/>
    <text x="202.5" y="261" class="t-muted" font-size="8" text-anchor="middle">read</text>
  </g>
  <g><rect x="387.1" y="189.5" width="70.8" height="16" rx="4" class="c-mask"/>
    <text x="422.5" y="200.5" class="t-muted" font-size="8" text-anchor="middle">filtered set</text>
  </g>
  <g><rect x="389.6" y="310.5" width="70.8" height="16" rx="4" class="c-mask"/>
    <text x="425" y="321.5" class="t-muted" font-size="8" text-anchor="middle">filtered set</text>
  </g>
  <g><rect x="626.3" y="136" width="41.4" height="16" rx="4" class="c-mask"/>
    <text x="647" y="147" class="t-backend" font-size="8" text-anchor="middle">bibtex</text>
  </g>
  <g><rect x="616.45" y="364" width="56.1" height="16" rx="4" class="c-mask"/>
    <text x="644.5" y="375" class="t-backend" font-size="8" text-anchor="middle">json list</text>
  </g>
  <g>
    <text x="40" y="504" class="t-primary" font-size="12" font-weight="650">Legend</text>
    <path d="M 40 521 L 74 521" class="a-emphasis" stroke-width="1.8" marker-end="url(#arrowhead-emphasis-3)"/>
    <text x="83" y="524" class="t-muted" font-size="10" font-weight="500">primary data</text>
    <rect x="165" y="516" width="14" height="9" rx="2" class="c-database" stroke-width="1"/>
    <text x="187" y="524" class="t-muted" font-size="10" font-weight="500">data store</text>
    <path d="M 280 521 L 314 521" class="a-default" stroke-width="1.4" marker-end="url(#arrowhead-3)"/>
    <text x="323" y="524" class="t-muted" font-size="10" font-weight="500">data flow</text>
  </g>
</svg>
    </div>
    <figcaption>
      "First author", "which journal", "which year" are facts already sitting in <b>metadata.json</b> — asking the vector store to relevance-rank for them would be answering a lookup with a guess. <code>glob + filter</code> is plain Python; neither chroma nor bm25 is ever touched. <code>/paper-rag:mine</code> defaults <code>--author</code> from <code>config.json</code>'s <code>author_name</code>, set once via <code>/paper-rag:whoami</code>.
    </figcaption>
  </figure>
</section>

<section>
  <h2>RAG home — file &amp; folder layout</h2>
  <figure>
    <pre class="tree"><span class="k">&lt;home&gt;/</span>                              <span class="c"># resolve_home(): --home &gt; $PAPER_RAG_HOME &gt; .paper-rag-home &gt; homes.json "current" &gt; ~/.local/share/paper-rag</span>
├── <span class="k">config.json</span>                       <span class="c"># {"embedding_model": "...", "author_name": "..."}</span>
├── <span class="k">chroma/</span>                            <span class="c"># chromadb.PersistentClient(path=chroma_dir(home))</span>
│   └── <span class="c">... one collection per embedding model: papers__{model_slug}</span>
├── <span class="k">bm25/</span>
│   └── <span class="k">{model_slug}.pkl</span>                <span class="c"># pickled BM25 index, rebuilt whole on every ingest touching that model's collection</span>
└── <span class="k">papers/</span>
    └── <span class="k">&lt;doc_key&gt;/</span>                    <span class="c"># doc_key = resolved PMID, else sha256 of the local file</span>
        ├── <span class="k">metadata.json</span>              <span class="c"># authors, year, journal, doi, doc_key, has_fulltext</span>
        ├── <span class="k">fulltext.md</span>                <span class="c"># docling-converted markdown — only written when has_fulltext</span>
        └── <span class="k">figures/</span>
            └── <span class="k">fig_0.png, fig_1.png, ...</span>  <span class="c"># PictureItem crops, PDF sources only</span>
<span class="c">~/.config/paper-rag/</span>
└── <span class="k">homes.json</span>                        <span class="c"># {"homes": {name: path}, "current": name} — multiple libraries, switched by name</span>
<span class="c">&lt;project&gt;/.paper-rag-home</span>                <span class="c"># optional per-project override: a raw path, or "name:&lt;name&gt;" into homes.json</span></pre>
    <figcaption>
      Every paper gets its own <b>doc_key</b> directory under <code>papers/</code> — the same key that tags each chroma chunk and bm25 entry, so <code>--force</code> re-ingest deletes-then-reinserts by directory, not by search. <b>chroma/</b> and <b>bm25/</b> are keyed by <code>embedding_model</code>, not doc_key — switching models gets you a fresh collection and index, not a mixed one.
    </figcaption>
  </figure>
</section>


<style scoped>
.lede {
  color: var(--vp-c-text-2);
  font-size: 16px;
  max-width: 60ch;
  margin: 0 0 40px;
}
.accent { color: var(--vp-c-brand-1); }

h2 {
  font-family: ui-monospace, Menlo, Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-brand-1);
  margin: 0 0 16px;
  display: flex;
  align-items: baseline;
  gap: 10px;
  border: none;
  padding: 0;
}
h2::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--vp-c-divider);
}

section { margin-bottom: 48px; }

figure {
  margin: 0;
  background: var(--vp-c-bg-alt);
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  padding: 20px 16px 16px;
  overflow-x: auto;
}
figure svg { display: block; margin: 0 auto; max-width: 100%; height: auto; }
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

figure text { fill: currentColor; font-family: ui-monospace, Menlo, Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace; }

.note {
  font-family: ui-monospace, Menlo, Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
  font-size: 12.5px;
  color: var(--vp-c-text-2);
  background: var(--vp-c-brand-soft);
  border-radius: 8px;
  padding: 10px 14px;
  margin-top: 14px;
  line-height: 1.6;
}
.note b { color: var(--vp-c-text-1); }

/* archify-generated diagrams, remapped onto the site's ink/amber theme */
.archify-diagram .c-grid { stroke: transparent; fill: none; }
.archify-diagram .c-mask { fill: var(--vp-c-bg-alt); stroke: none; }
.archify-diagram .c-lane { fill: rgba(245, 163, 92, 0.05); stroke: var(--vp-c-divider); stroke-dasharray: 6,6; }
.archify-diagram .c-frontend, .archify-diagram .c-backend, .archify-diagram .c-cloud,
.archify-diagram .c-security, .archify-diagram .c-messagebus { fill: transparent; stroke: var(--vp-c-text-1); }
.archify-diagram .c-database { fill: var(--vp-c-brand-soft); stroke: var(--vp-c-brand-1); }
.archify-diagram .c-external { fill: transparent; stroke: var(--vp-c-text-2); }
.archify-diagram .t-primary { fill: var(--vp-c-text-1); }
.archify-diagram .t-muted, .archify-diagram .t-dim { fill: var(--vp-c-text-2); }
.archify-diagram .t-frontend, .archify-diagram .t-backend, .archify-diagram .t-cloud,
.archify-diagram .t-security, .archify-diagram .t-messagebus { fill: var(--vp-c-text-1); }
.archify-diagram .t-database { fill: var(--vp-c-brand-1); }
.archify-diagram .t-external { fill: var(--vp-c-text-2); }
.archify-diagram .a-default { stroke: var(--vp-c-text-2); fill: none; }
.archify-diagram .a-emphasis { stroke: var(--vp-c-brand-1); fill: none; }
.archify-diagram .a-security { stroke: var(--vp-c-text-2); fill: none; stroke-dasharray: 5,5; }
.archify-diagram .a-dashed { stroke: var(--vp-c-text-2); fill: none; stroke-dasharray: 4,4; }
.archify-diagram .m-default { fill: var(--vp-c-text-2); }
.archify-diagram .m-emphasis { fill: var(--vp-c-brand-1); }
.archify-diagram .m-security { fill: var(--vp-c-text-2); }
.archify-diagram .m-dashed { fill: var(--vp-c-text-2); }
.archify-diagram [data-node-id] { cursor: pointer; transition: opacity 0.18s ease, filter 0.18s ease; }
.archify-diagram [data-node-id]:hover, .archify-diagram [data-node-id]:focus-visible { filter: drop-shadow(0 0 7px var(--vp-c-brand-1)); outline: none; }

.tree {
  margin: 0;
  font-family: ui-monospace, Menlo, Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre;
  overflow-x: auto;
}
.tree .c { color: var(--vp-c-text-2); }
.tree .k { color: var(--vp-c-brand-1); font-weight: 600; }
</style>
