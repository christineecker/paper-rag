import pytest

from lib import fetch as fetch_lib
from lib import mesh as mesh_lib
from lib import pubmed_query as pq


@pytest.fixture(autouse=True)
def no_mesh_index(monkeypatch):
    """Default: no local MeSH index built, so tests are deterministic without
    touching a real cache dir."""
    monkeypatch.setattr(mesh_lib, "latest_available_index", lambda base=None: None)
    monkeypatch.setattr(mesh_lib, "lookup_descriptor", lambda term, index_path=None: None)


@pytest.fixture
def fake_esearch(monkeypatch):
    calls = []

    def fake(query, *, max_results=1000, page_size=500):
        calls.append(query)
        return {
            "pmids": ["111", "222"],
            "total_count": 2,
            "returned_count": 2,
            "truncated": False,
            "query_translation": query,
            "webenv": "WE1",
            "querykey": "1",
        }

    monkeypatch.setattr(fetch_lib, "esearch_pmids", fake)
    return calls


def test_direct_mode_passthrough(fake_esearch):
    result = pq.search_pubmed(mode="direct", query="  autism[Title/Abstract]\r\nAND mri[Title/Abstract]  ")
    assert result.pubmed_query == "(autism[Title/Abstract] AND mri[Title/Abstract]) AND english[Language]"
    assert result.mode == "direct"
    assert result.pmids == ["111", "222"]
    assert result.total_count == 2
    assert result.truncated is False


def test_direct_mode_requires_query():
    with pytest.raises(ValueError):
        pq.search_pubmed(mode="direct")


def test_direct_mode_rejects_wrong_inputs():
    with pytest.raises(ValueError):
        pq.search_pubmed(mode="direct", query="x", concepts=[pq.SearchConcept(name="a", terms=["a"])])


def test_direct_mode_rejects_empty_query():
    with pytest.raises(ValueError):
        pq.compile_direct("   ")


def test_concept_mode_combines_or_and_and(fake_esearch):
    concepts = [
        pq.SearchConcept(name="population", terms=["autism", "autism spectrum disorder"]),
        pq.SearchConcept(name="modality", terms=["MRI", "structural MRI"]),
    ]
    result = pq.search_pubmed(mode="concepts", concepts=concepts)
    query = result.pubmed_query
    assert " AND " in query
    assert query.endswith(" AND english[Language]")
    assert query.count("(") == 3  # two concept groups + outer wrap for the language filter
    assert "autism[Title/Abstract]" in query
    assert '"autism spectrum disorder"[Title/Abstract]' in query
    assert '"structural mri"[Title/Abstract]'.lower() in query.lower() or "mri[Title/Abstract]" in query


def test_concept_mode_requires_nonempty_concepts():
    with pytest.raises(ValueError):
        pq.search_pubmed(mode="concepts", concepts=[])
    with pytest.raises(ValueError):
        pq.search_pubmed(mode="concepts")


def test_concept_mode_rejects_wrong_inputs():
    with pytest.raises(ValueError):
        pq.search_pubmed(mode="concepts", concepts=[pq.SearchConcept(name="a", terms=["a"])], query="x")


def test_concept_requires_nonempty_terms():
    with pytest.raises(ValueError):
        pq.SearchConcept(name="a", terms=["", "   "])


def test_concept_requires_nonempty_name():
    with pytest.raises(ValueError):
        pq.SearchConcept(name="", terms=["a"])


def test_mesh_validated_term_gets_mesh_tag(monkeypatch, fake_esearch):
    monkeypatch.setattr(
        mesh_lib, "lookup_descriptor",
        lambda term, index_path=None: "Autism Spectrum Disorder" if term.lower() == "autism" else None,
    )
    monkeypatch.setattr(mesh_lib, "latest_available_index", lambda base=None: "fake-path")

    concepts = [pq.SearchConcept(name="population", terms=["autism"])]
    query, clauses, warnings = pq.compile_concepts(concepts)
    assert '"Autism Spectrum Disorder"[MeSH Terms]' in query
    assert "autism[Title/Abstract]" in query
    assert not any("no local MeSH index" in w for w in warnings)


def test_no_mesh_index_warns_once(fake_esearch):
    concepts = [pq.SearchConcept(name="population", terms=["autism"])]
    query, clauses, warnings = pq.compile_concepts(concepts)
    assert "[MeSH Terms]" not in query
    assert any("no local MeSH index" in w for w in warnings)


def test_duplicate_terms_deduped_case_insensitively():
    concepts = [pq.SearchConcept(name="a", terms=["Autism", "autism", "AUTISM"])]
    query, clauses, warnings = pq.compile_concepts(concepts)
    assert query.count("[Title/Abstract]") == 1


def test_quote_escaping():
    concepts = [pq.SearchConcept(name="a", terms=['weird "quoted" term'])]
    query, clauses, warnings = pq.compile_concepts(concepts)
    assert query == '(\"weird \'quoted\' term\"[Title/Abstract])'
    assert query.count('"') == 2


def test_stable_ordering_same_input_same_query():
    concepts = [
        pq.SearchConcept(name="a", terms=["zebra", "apple"]),
        pq.SearchConcept(name="b", terms=["banana"]),
    ]
    q1, _, _ = pq.compile_concepts(concepts)
    q2, _, _ = pq.compile_concepts(concepts)
    assert q1 == q2


def test_broad_sensitivity_drops_optional_concepts(fake_esearch):
    concepts = [
        pq.SearchConcept(name="core", terms=["autism"], required=True),
        pq.SearchConcept(name="context", terms=["prevalence"], required=False),
    ]
    query, clauses, warnings = pq.compile_concepts(concepts, sensitivity="broad")
    assert "prevalence" not in query
    assert "autism" in query


def test_balanced_sensitivity_keeps_optional_concepts(fake_esearch):
    concepts = [
        pq.SearchConcept(name="core", terms=["autism"], required=True),
        pq.SearchConcept(name="context", terms=["prevalence"], required=False),
    ]
    query, clauses, warnings = pq.compile_concepts(concepts, sensitivity="balanced")
    assert "prevalence" in query
    assert "autism" in query


def test_precise_sensitivity_warns_and_drops_short_abbreviations():
    concepts = [pq.SearchConcept(name="a", terms=["MRI", "magnetic resonance imaging"])]
    query, clauses, warnings = pq.compile_concepts(concepts, sensitivity="precise")
    assert "magnetic resonance imaging" in query.lower()
    assert any("precise" in w for w in warnings)


def test_question_mode_not_implemented():
    with pytest.raises(NotImplementedError):
        pq.search_pubmed(mode="question", question="does X cause Y?")


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        pq.search_pubmed(mode="bogus")  # type: ignore[arg-type]


def test_truncated_result_adds_warning(monkeypatch):
    def fake(query, *, max_results=1000, page_size=500):
        return {
            "pmids": ["1"],
            "total_count": 500,
            "returned_count": 1,
            "truncated": True,
            "query_translation": query,
            "webenv": None,
            "querykey": None,
        }

    monkeypatch.setattr(fetch_lib, "esearch_pmids", fake)
    result = pq.search_pubmed(mode="direct", query="q")
    assert result.truncated is True
    assert any("truncated" in w for w in result.warnings)


def test_provenance_includes_concept_clauses(fake_esearch):
    concepts = [pq.SearchConcept(name="population", terms=["autism"])]
    result = pq.search_pubmed(mode="concepts", concepts=concepts)
    assert result.provenance["source"] == "NCBI PubMed ESearch"
    assert result.provenance["concept_clauses"][0]["concept"] == "population"
