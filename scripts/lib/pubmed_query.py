"""Turn a search request (raw query string, or structured concepts) into a
deterministic Boolean PubMed query and run it through ESearch (lib/fetch.py) to
get a deduplicated PMID set.

Two modes are implemented: `direct` (pass a query straight through) and
`concepts` (compile a Boolean query from structured SearchConcept groups,
validating MeSH headings against the local index in lib/mesh.py). A third,
`question` (natural-language question -> LLM-extracted concepts), is not
implemented here: this project has no LLM client. Ask Claude — which already
has the pubmed-cyanheads MCP tool — to turn a question into SearchConcept
objects, then call search_pubmed(mode="concepts", concepts=...).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from . import fetch as fetch_lib
from . import mesh as mesh_lib

Mode = Literal["direct", "concepts", "question"]
Sensitivity = Literal["broad", "balanced", "precise"]

_VALID_MODES = {"direct", "concepts", "question"}
_VALID_SENSITIVITIES = {"broad", "balanced", "precise"}


@dataclass
class SearchConcept:
    """One scientific concept: a group of interchangeable terms (synonyms),
    combined with OR, then ANDed against other concepts."""

    name: str
    terms: list[str]
    required: bool = True
    expand: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("concept name must not be empty")
        cleaned = [t.strip() for t in self.terms if t and t.strip()]
        if not cleaned:
            raise ValueError(f"concept {self.name!r} must have at least one non-empty term")
        self.terms = cleaned


@dataclass
class QueryClause:
    """One compiled Boolean OR-group, tagged with the concept that produced it."""

    concept_name: str
    text: str
    required: bool


@dataclass
class PubMedSearchResult:
    pmids: list[str]
    pubmed_query: str
    mode: str
    framework: Optional[str]
    sensitivity: str
    total_count: int
    returned_count: int
    truncated: bool
    warnings: list[str]
    retrieved_at: datetime
    provenance: dict[str, Any]


def _escape_term(term: str) -> str:
    """Normalize whitespace and neutralize double quotes (PubMed has no quote-
    escaping syntax; a literal `"` inside a phrase would prematurely close it)."""
    collapsed = " ".join(term.split())
    return collapsed.replace('"', "'")


def _field_tag(term: str, tag: str) -> str:
    escaped = _escape_term(term)
    if " " in escaped:
        return f'"{escaped}"[{tag}]'
    return f"{escaped}[{tag}]"


def _looks_like_ambiguous_abbreviation(term: str) -> bool:
    """Heuristic for `precise` mode: short, all-caps-or-mixed single tokens
    (e.g. "MRI", "ASD") are more likely to collide with unrelated meanings than
    a full phrase."""
    return " " not in term and len(term) <= 4


def compile_direct(query: str) -> str:
    """Direct mode: pass the query straight to ESearch, normalizing only
    surrounding whitespace and line endings — no semantic rewriting."""
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    normalized = query.strip().replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(normalized.split("\n"))


def _select_concepts(concepts: list[SearchConcept], sensitivity: str) -> tuple[list[SearchConcept], list[str]]:
    warnings: list[str] = []
    if sensitivity == "broad":
        required_only = [c for c in concepts if c.required]
        selected = required_only or list(concepts)
    else:
        selected = list(concepts)
    if sensitivity == "precise":
        warnings.append(
            "sensitivity='precise' prefers exact phrases and drops short/ambiguous "
            "abbreviations, which can reduce recall."
        )
    return selected, warnings


def _compile_concept_terms(concept: SearchConcept, sensitivity: str) -> list[str]:
    mesh_headings: set[str] = set()
    freetext_seen: set[str] = set()
    freetext: list[str] = []

    for term in concept.terms:
        if concept.expand:
            descriptor = mesh_lib.lookup_descriptor(term)
            if descriptor:
                mesh_headings.add(descriptor)
        key = term.lower()
        if key not in freetext_seen:
            freetext_seen.add(key)
            freetext.append(term)

    if sensitivity == "precise":
        filtered = [t for t in freetext if not _looks_like_ambiguous_abbreviation(t)]
        freetext = filtered or freetext  # never drop down to zero terms

    clauses = [_field_tag(h, "MeSH Terms") for h in sorted(mesh_headings)]
    clauses += [_field_tag(t, "Title/Abstract") for t in sorted(freetext, key=str.lower)]
    return clauses


def compile_concepts(concepts: list[SearchConcept], sensitivity: Sensitivity = "balanced") -> tuple[str, list[QueryClause], list[str]]:
    """Compile a list of SearchConcept groups into one Boolean query: OR within
    a concept, AND across concepts. Returns (query, clauses, warnings)."""
    if not concepts:
        raise ValueError("concepts must be a non-empty list")
    if sensitivity not in _VALID_SENSITIVITIES:
        raise ValueError(f"unknown sensitivity {sensitivity!r}")

    selected, warnings = _select_concepts(concepts, sensitivity)
    if mesh_lib.latest_available_index() is None:
        warnings.append(
            "no local MeSH index found; all terms compiled as [Title/Abstract] only. "
            "Run `python scripts/mesh_update.py` to enable MeSH heading validation."
        )

    clauses: list[QueryClause] = []
    group_texts: list[str] = []
    for concept in selected:
        terms = _compile_concept_terms(concept, sensitivity)
        if not terms:
            continue
        group_text = "(" + " OR ".join(terms) + ")"
        clauses.append(QueryClause(concept_name=concept.name, text=group_text, required=concept.required))
        group_texts.append(group_text)

    if not group_texts:
        raise ValueError("no usable terms after MeSH/synonym expansion and sensitivity filtering")

    return " AND ".join(group_texts), clauses, warnings


def search_pubmed(
    *,
    mode: Mode,
    query: Optional[str] = None,
    concepts: Optional[list[SearchConcept]] = None,
    question: Optional[str] = None,
    framework: str = "auto",
    sensitivity: Sensitivity = "balanced",
    max_results: int = 1000,
    page_size: int = 500,
) -> PubMedSearchResult:
    if mode not in _VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if max_results <= 0:
        raise ValueError("max_results must be positive")
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    clauses: list[QueryClause] = []
    compile_warnings: list[str] = []
    framework_used: Optional[str] = None

    if mode == "direct":
        if concepts is not None or question is not None:
            raise ValueError("mode='direct' accepts only 'query'")
        if query is None:
            raise ValueError("mode='direct' requires 'query'")
        compiled_query = compile_direct(query)

    elif mode == "concepts":
        if query is not None or question is not None:
            raise ValueError("mode='concepts' accepts only 'concepts'")
        if not concepts:
            raise ValueError("mode='concepts' requires a non-empty 'concepts' list")
        compiled_query, clauses, compile_warnings = compile_concepts(concepts, sensitivity)

    else:  # mode == "question"
        raise NotImplementedError(
            "mode='question' is not implemented (no LLM client in this project). "
            "Ask Claude to turn the question into SearchConcept objects (it has the "
            "pubmed-cyanheads MCP tool for MeSH/terminology help), then call "
            "search_pubmed(mode='concepts', concepts=...)."
        )

    esearch_result = fetch_lib.esearch_pmids(compiled_query, max_results=max_results, page_size=page_size)

    warnings = list(compile_warnings)
    if esearch_result["truncated"]:
        warnings.append(
            f"result set truncated to {esearch_result['returned_count']} of "
            f"{esearch_result['total_count']} total PubMed hits"
        )

    provenance = {
        "source": "NCBI PubMed ESearch",
        "query_translation": esearch_result["query_translation"],
        "webenv": esearch_result["webenv"],
        "querykey": esearch_result["querykey"],
        "concept_clauses": [
            {"concept": c.concept_name, "clause": c.text, "required": c.required} for c in clauses
        ],
    }

    return PubMedSearchResult(
        pmids=esearch_result["pmids"],
        pubmed_query=compiled_query,
        mode=mode,
        framework=framework_used,
        sensitivity=sensitivity,
        total_count=esearch_result["total_count"],
        returned_count=esearch_result["returned_count"],
        truncated=esearch_result["truncated"],
        warnings=warnings,
        retrieved_at=datetime.now(timezone.utc),
        provenance=provenance,
    )
