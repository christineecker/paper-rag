"""Emit the concept graph as an OKF v0.2 bundle (index.md, log.md, concepts/, references/).

Adapted from ref-manager's okf_emit.py. Output is a pure function of the JSONL rows and the
current claims, with no timestamps of its own, so unchanged input gives byte-identical files.
Frontmatter is written without PyYAML (JSON scalars and flow lists are valid YAML).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from . import graph_store as gs

STALE = "**STALE**"


def bundle_dir(project_path: Path) -> Path:
    """Where the bundle lives: <project>/graph/okf, beside the JSONL it is generated from."""
    return project_path / gs.GRAPH_DIR / "okf"


def ref_slug(doc_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", doc_key)


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _claim_lines(claim_id: str, claims: dict[str, dict], stale: bool, indent: str = "") -> list[str]:
    claim = claims.get(claim_id)
    mark = f" {STALE}" if stale else ""
    if claim is None:
        return [f"{indent}- `{claim_id}`{mark} (claim no longer in the library)"]
    meta = claim["meta"]
    chunks = ", ".join(gs.split_chunk_ids(meta.get("source_chunk_ids")))
    lines = [f"{indent}- `{claim_id}`{mark} {_one_line(claim['text'])}"]
    if meta.get("evidence_span"):
        lines.append(f"{indent}  - evidence: \"{_one_line(meta['evidence_span'])}\"")
    lines.append(f"{indent}  - chunks: {chunks or 'n/a'} · source_level: {meta.get('source_level', 'n/a')}")
    return lines


def _concept_page(c: dict, mappings: list[dict], relations: list[dict], concepts: dict[str, dict],
                  claims: dict[str, dict], current: dict[str, str]) -> str:
    cid = c["concept_id"]
    out = [_frontmatter({"type": "concept", "id": cid, "name": c["name"], "facet": c["facet"],
                         "aliases": c.get("aliases", [])})]
    out.append(f"# {c['name']}\n\nFacet: {c['facet']}\n")
    if c.get("aliases"):
        out.append("## Aliases\n")
        for alias in c["aliases"]:
            prov = c.get("alias_provenance", {}).get(alias)
            note = f" (first seen in `{prov['source']}`)" if prov else ""
            out.append(f"- {alias}{note}")
        out.append("")
    mine = sorted((m for m in mappings if m["concept_id"] == cid), key=lambda m: (m["doc_key"], m["claim_id"]))
    out.append("## Claims\n")
    if not mine:
        out.append("None mapped.")
    for m in mine:
        title = (claims.get(m["claim_id"]) or {}).get("meta", {}).get("title") or m["doc_key"]
        out.append(f"- [{_one_line(title)}](../references/{ref_slug(m['doc_key'])}.md)")
        out.extend(_claim_lines(m["claim_id"], claims, m.get("stale", False), indent="  "))
    out.append("\n## Relations\n")
    rels = sorted((r for r in relations if cid in (r["subject_concept_id"], r["object_concept_id"])),
                  key=lambda r: (r["type"], r["subject_concept_id"], r["object_concept_id"], r["relation_id"]))
    if not rels:
        out.append("None.")
    for r in rels:
        outgoing = r["subject_concept_id"] == cid
        other = concepts[r["object_concept_id"] if outgoing else r["subject_concept_id"]]
        arrow = "→" if outgoing else "←"
        flags = [r["review_state"]] + ([STALE] if r.get("stale") else [])
        out.append(f"- **{r['type']}** {arrow} [{other['name']}]({other['concept_id']}.md) · {' · '.join(flags)} "
                   f"· `{r['relation_id']}` · proposed by {r['proposed_by']}")
        if r.get("rationale"):
            out.append(f"  - rationale: {_one_line(r['rationale'])}")
        for p in r["supporting_claims"]:
            out.extend(_claim_lines(p["claim_id"], claims, gs.pointer_is_stale(p, current), indent="  "))
    return "\n".join(out) + "\n"


def _reference_page(doc_key: str, mappings: list[dict], concepts: dict[str, dict], claims: dict[str, dict]) -> str:
    mine = sorted((m for m in mappings if m["doc_key"] == doc_key), key=lambda m: (m["claim_id"], m["concept_id"]))
    meta = next((claims[m["claim_id"]]["meta"] for m in mine if m["claim_id"] in claims), {})
    fm = {"type": "reference", "id": doc_key, "title": meta.get("title") or doc_key}
    if meta.get("pmid"):
        fm["pmid"] = meta["pmid"]
    out = [_frontmatter(fm), f"# {_one_line(fm['title'])}\n", "## Mapped claims\n"]
    by_claim: dict[str, list[dict]] = {}
    for m in mine:
        by_claim.setdefault(m["claim_id"], []).append(m)
    for claim_id, ms in by_claim.items():
        out.extend(_claim_lines(claim_id, claims, any(m.get("stale") for m in ms)))
        links = ", ".join(f"[{concepts[m['concept_id']]['name']}](../concepts/{m['concept_id']}.md)"
                          for m in ms if m["concept_id"] in concepts)
        out.append(f"  - concepts: {links}")
    return "\n".join(out) + "\n"


def build_bundle(concepts_rows: list[dict], mappings: list[dict], relations: list[dict],
                 claims: dict[str, dict], log_rows: list[dict]) -> dict[str, str]:
    """{bundle-relative path: file content}."""
    concepts = {c["concept_id"]: c for c in concepts_rows}
    current = {cid: cl["hash"] for cid, cl in claims.items()}
    files: dict[str, str] = {}
    for cid in sorted(concepts):
        files[f"concepts/{cid}.md"] = _concept_page(concepts[cid], mappings, relations, concepts, claims, current)
    doc_keys = sorted({m["doc_key"] for m in mappings})
    for dk in doc_keys:
        files[f"references/{ref_slug(dk)}.md"] = _reference_page(dk, mappings, concepts, claims)

    idx = [_frontmatter({"type": "index", "concepts": len(concepts), "references": len(doc_keys),
                         "relations": len(relations),
                         "stale_relations": sum(1 for r in relations if r.get("stale"))}), "# Concept graph\n"]
    by_facet: dict[str, list[dict]] = {}
    for c in concepts.values():
        by_facet.setdefault(c["facet"], []).append(c)
    for facet in sorted(by_facet):
        idx.append(f"## {facet}\n")
        idx.extend(f"- [{c['name']}](concepts/{c['concept_id']}.md)" for c in sorted(by_facet[facet], key=lambda c: c["concept_id"]))
        idx.append("")
    idx.append("## References\n")
    idx.extend(f"- [{dk}](references/{ref_slug(dk)}.md)" for dk in doc_keys)
    files["index.md"] = "\n".join(idx) + "\n"

    log = [_frontmatter({"type": "log"}), "# Log\n"]
    for row in log_rows:
        detail = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in row.items() if k not in ("at", "action"))
        log.append(f"- {row['at']} {row['action']}" + (f" ({detail})" if detail else ""))
    files["log.md"] = "\n".join(log) + "\n"
    return files


def write_bundle(out_dir: Path, files: dict[str, str]) -> dict:
    """Write files (only when content changed) and remove generated pages no longer produced."""
    written = 0
    for rel, content in files.items():
        path = out_dir / rel
        if path.exists() and path.read_text() == content:
            continue
        gs._atomic_write(path, content)
        written += 1
    removed = 0
    for sub in ("concepts", "references"):
        for path in (out_dir / sub).glob("*.md") if (out_dir / sub).is_dir() else []:
            if f"{sub}/{path.name}" not in files:
                path.unlink()
                removed += 1
    return {"files": len(files), "written": written, "removed": removed}


_REL_RE = re.compile(r"^- \*\*(\w+)\*\* (→|←) \[.*?\]\((.+?)\.md\) · (.*?) · `(\w+)` · proposed by (\w+)")
_CLAIM_RE = re.compile(r"^\s*- `([^`]+)`( \*\*STALE\*\*)? (.*)$")
_EVIDENCE_RE = re.compile(r'^\s*- evidence: "(.*)"$')
_CHUNKS_RE = re.compile(r"^\s*- chunks: (.*?) · source_level: (\S+)$")
_RATIONALE_RE = re.compile(r"^\s*- rationale: (.*)$")
_REFLINK_RE = re.compile(r"^- \[(.*)\]\(\.\./references/(.+)\.md\)$")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    _, fm, body = text.split("---\n", 2)
    fields = {}
    for line in fm.splitlines():
        key, value = line.split(": ", 1)
        fields[key] = json.loads(value)
    return fields, body


def parse_bundle(okf_dir: Path) -> Optional[dict]:
    """Read an emitted bundle back into {concepts, relations, claims} for display (the dashboard's
    Graph view). Reads only okf/, so it shows exactly what the bundle says. Returns None if there
    is no bundle. `claims` maps claim_id -> {id, doc_key, text, evidence, chunks, level, stale}."""
    pages = sorted((okf_dir / "concepts").glob("*.md")) if (okf_dir / "concepts").is_dir() else []
    if not pages:
        return None
    claims: dict[str, dict] = {}
    concepts, relations = [], {}
    for page in pages:
        fm, body = _split_frontmatter(page.read_text())
        cid, section, last, rel, mine = fm["id"], None, None, None, []
        for line in body.splitlines():
            if line.startswith("## "):
                section, last = line[3:], None
                continue
            if section == "Relations":
                m = _REL_RE.match(line)
                if m:
                    rel_type, arrow, other, flags, rid, by = m.groups()
                    rel = None
                    if arrow == "→":
                        rel = relations.setdefault(rid, {
                            "relation_id": rid, "type": rel_type, "subject_concept_id": cid,
                            "object_concept_id": other, "review_state": flags.split(" · ")[0],
                            "rationale": None, "stale": STALE in flags, "proposed_by": by, "claims": []})
                    continue
                m = _RATIONALE_RE.match(line)
                if m:
                    if rel:
                        rel["rationale"] = m[1]
                    continue
            m = _CLAIM_RE.match(line)
            if m:
                claim_id = m[1]
                last = claims.setdefault(claim_id, {"id": claim_id, "doc_key": claim_id.split("::")[0],
                                                    "text": m[3], "evidence": "", "chunks": "", "level": "", "stale": False})
                last["stale"] = last["stale"] or bool(m[2])
                if section == "Claims":
                    mine.append(claim_id)
                elif rel is not None:
                    rel["claims"].append(claim_id)
                continue
            m = _EVIDENCE_RE.match(line)
            if m and last:
                last["evidence"] = m[1]
                continue
            m = _CHUNKS_RE.match(line)
            if m and last:
                last["chunks"], last["level"] = m[1], m[2]
        concepts.append({"id": cid, "name": fm["name"], "facet": fm["facet"],
                         "aliases": fm.get("aliases", []), "claims": sorted(set(mine))})
    return {"concepts": concepts, "relations": sorted(relations.values(), key=lambda r: r["relation_id"]),
            "claims": claims}
