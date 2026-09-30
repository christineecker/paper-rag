"""Relation validation and deterministic conflict proposal for the concept graph.

Adapted from ref-manager's weave (relation.py / lib_schema.validate_relation). `contradicts`
is never proposed: it needs review_state "reviewed" and a rationale. Claims carry no
timepoint field, so comparability checks population, comparator and effect_measure.
"""
from __future__ import annotations

import hashlib
import itertools
from typing import Optional

from . import graph_store as gs

CLAIM_TYPES = ("supports", "potential_conflict", "contradicts", "extends", "replicates")
TYPES = CLAIM_TYPES + ("is_a",)
REVIEW_STATES = ("unreviewed", "reviewed")
COMPARABLE_FIELDS = ("population", "comparator", "effect_measure")
OPPOSITE = {"increase": "decrease", "decrease": "increase"}
# Facets that make the subject/object of a proposed edge (intervention -> outcome).
_FACET_RANK = {"intervention": 0, "exposure": 0, "intervention/exposure": 0, "outcome": 1}


def relation_id(rel_type: str, subject: str, obj: str) -> str:
    return hashlib.sha1(f"{rel_type}|{subject}|{obj}".encode()).hexdigest()[:12]


def new_relation(rel_type: str, subject: str, obj: str, claims: list[dict], proposed_by: str,
                 review_state: str = "unreviewed", rationale: Optional[str] = None) -> dict:
    ts = gs.now()
    return {
        "relation_id": relation_id(rel_type, subject, obj),
        "type": rel_type,
        "subject_concept_id": subject,
        "object_concept_id": obj,
        "supporting_claims": sorted(claims, key=lambda p: p["claim_id"]),
        "review_state": review_state,
        "rationale": rationale,
        "stale": False,
        "proposed_by": proposed_by,
        "created_at": ts,
        "updated_at": ts,
    }


def validate_relation(rel: dict, concept_ids: set[str]) -> Optional[tuple[str, dict]]:
    """None if the relation is valid, else (error_code, details)."""
    rel_type = rel.get("type")
    if rel_type not in TYPES:
        return "invalid_relation_type", {"type": rel_type, "allowed": list(TYPES)}
    for end in ("subject_concept_id", "object_concept_id"):
        if rel.get(end) not in concept_ids:
            return "unknown_concept", {"concept_id": rel.get(end)}
    if rel["subject_concept_id"] == rel["object_concept_id"]:
        return "self_relation", {"concept_id": rel["subject_concept_id"]}
    if rel.get("review_state") not in REVIEW_STATES:
        return "invalid_review_state", {"review_state": rel.get("review_state"), "allowed": list(REVIEW_STATES)}
    claims = rel.get("supporting_claims") or []
    if rel_type == "is_a":
        if claims:
            return "is_a_takes_no_claims", {}
        if rel.get("proposed_by") != "claude":
            return "is_a_must_be_proposed_by_claude", {}
        return None
    if len(claims) < 2:
        return "needs_two_claims", {"type": rel_type, "given": len(claims)}
    if rel_type in ("potential_conflict", "contradicts") and len({c["doc_key"] for c in claims}) < 2:
        return "needs_two_papers", {"type": rel_type}
    if rel_type == "contradicts" and (rel["review_state"] != "reviewed" or not (rel.get("rationale") or "").strip()):
        return "contradicts_needs_review_and_rationale", {
            "hint": "use: relation review <id> contradicts --rationale '...'"
        }
    return None


def _context(claim: dict) -> Optional[tuple]:
    meta = claim["meta"]
    values = tuple(gs.normalize(meta.get(f, "")) for f in COMPARABLE_FIELDS)
    return values if all(values) else None


def comparable_conflict(a: dict, b: dict) -> bool:
    """True if two claims from different papers have opposite directions in the same context.
    Missing context never makes a conflict."""
    if a["doc_key"] == b["doc_key"]:
        return False
    da, db = a["meta"].get("direction"), b["meta"].get("direction")
    if OPPOSITE.get(da) != db:
        return False
    ctx_a = _context(a)
    return ctx_a is not None and ctx_a == _context(b)


def _endpoints(concept_ids: frozenset[str], concepts: dict[str, dict]) -> tuple[str, str]:
    ranked = sorted(concept_ids, key=lambda c: (_FACET_RANK.get(concepts[c]["facet"], 2), c))
    return ranked[0], ranked[1]


def propose_conflicts(mappings: list[dict], claims: dict[str, dict], concepts: dict[str, dict],
                      relations: list[dict]) -> tuple[list[dict], dict]:
    """Deterministic `potential_conflict` edges: claim pairs from different papers that map to
    the same concept set (>= 2 concepts), with opposite directions and matching context.
    Merges supporting claims into an existing unreviewed edge for the same concept pair.
    Returns (relations, {"created": n, "updated": n})."""
    by_claim: dict[str, set[str]] = {}
    for m in mappings:
        if not m.get("stale") and m["claim_id"] in claims and m["concept_id"] in concepts:
            by_claim.setdefault(m["claim_id"], set()).add(m["concept_id"])
    groups: dict[frozenset, list[str]] = {}
    for cid, cs in by_claim.items():
        if len(cs) >= 2:
            groups.setdefault(frozenset(cs), []).append(cid)

    found: dict[tuple[str, str], dict[str, dict]] = {}
    for concept_set, cids in groups.items():
        for a, b in itertools.combinations(sorted(cids), 2):
            if comparable_conflict(claims[a], claims[b]):
                pair = _endpoints(concept_set, concepts)
                bucket = found.setdefault(pair, {})
                bucket[a], bucket[b] = gs.pointer(claims[a]), gs.pointer(claims[b])

    out = [dict(r) for r in relations]
    created = updated = 0
    for (subj, obj), ptrs in sorted(found.items()):
        existing = next(
            (r for r in out if r["type"] in ("potential_conflict", "contradicts")
             and {r["subject_concept_id"], r["object_concept_id"]} == {subj, obj}),
            None,
        )
        if existing is None:
            out.append(new_relation("potential_conflict", subj, obj, list(ptrs.values()), "deterministic"))
            created += 1
        elif existing["review_state"] == "unreviewed":
            merged = {p["claim_id"]: p for p in existing["supporting_claims"]}
            merged.update(ptrs)
            merged_list = sorted(merged.values(), key=lambda p: p["claim_id"])
            if merged_list != existing["supporting_claims"]:
                existing["supporting_claims"] = merged_list
                existing["updated_at"] = gs.now()
                updated += 1
    return out, {"created": created, "updated": updated}
