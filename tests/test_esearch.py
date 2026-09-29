import httpx
import pytest

from lib import fetch as fetch_lib


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


def _esearch_payload(idlist, count, translation="q", webenv="WE1", querykey="1"):
    return {
        "esearchresult": {
            "count": str(count),
            "idlist": idlist,
            "querytranslation": translation,
            "webenv": webenv,
            "querykey": querykey,
        }
    }


def test_single_page(monkeypatch):
    calls = []

    def fake_get(url, params, timeout, follow_redirects):
        calls.append(params)
        return _FakeResponse(json_data=_esearch_payload(["1", "2", "3"], 3))

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_lib.esearch_pmids("cancer[Title/Abstract]", max_results=100, page_size=500)
    assert result["pmids"] == ["1", "2", "3"]
    assert result["total_count"] == 3
    assert result["returned_count"] == 3
    assert result["truncated"] is False
    assert result["query_translation"] == "q"
    assert result["webenv"] == "WE1"
    assert result["querykey"] == "1"
    assert len(calls) == 1
    assert calls[0]["tool"] == "paper-rag"
    assert calls[0]["email"]


def test_multiple_pages_dedupe_and_preserve_order(monkeypatch):
    pages = [
        _esearch_payload(["1", "2"], 5),
        _esearch_payload(["2", "3"], 5),  # overlapping id across pages
        _esearch_payload(["4", "5"], 5),
    ]

    def fake_get(url, params, timeout, follow_redirects):
        return _FakeResponse(json_data=pages.pop(0))

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_lib.esearch_pmids("q", max_results=100, page_size=2)
    assert result["pmids"] == ["1", "2", "3", "4", "5"]
    assert result["returned_count"] == 5
    assert result["truncated"] is False


def test_max_results_truncates(monkeypatch):
    def fake_get(url, params, timeout, follow_redirects):
        return _FakeResponse(json_data=_esearch_payload(["1", "2"], 1000))

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_lib.esearch_pmids("q", max_results=2, page_size=2)
    assert result["returned_count"] == 2
    assert result["total_count"] == 1000
    assert result["truncated"] is True


def test_zero_results(monkeypatch):
    def fake_get(url, params, timeout, follow_redirects):
        return _FakeResponse(json_data=_esearch_payload([], 0))

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_lib.esearch_pmids("q", max_results=100)
    assert result["pmids"] == []
    assert result["total_count"] == 0
    assert result["truncated"] is False


def test_retries_on_429_then_succeeds(monkeypatch):
    responses = [
        _FakeResponse(status_code=429),
        _FakeResponse(json_data=_esearch_payload(["1"], 1)),
    ]
    sleeps = []

    def fake_get(url, params, timeout, follow_redirects):
        return responses.pop(0)

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(fetch_lib.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_lib.esearch_pmids("q", max_results=100)
    assert result["pmids"] == ["1"]
    assert sleeps  # backed off at least once


def test_retries_on_timeout(monkeypatch):
    attempts = {"n": 0}

    def fake_get(url, params, timeout, follow_redirects):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.TimeoutException("boom")
        return _FakeResponse(json_data=_esearch_payload(["1"], 1))

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(fetch_lib, "_backoff_sleep", lambda attempt: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_lib.esearch_pmids("q", max_results=100)
    assert result["pmids"] == ["1"]
    assert attempts["n"] == 2


def test_exhausted_retries_raises(monkeypatch):
    def fake_get(url, params, timeout, follow_redirects):
        return _FakeResponse(status_code=500)

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(fetch_lib, "_backoff_sleep", lambda attempt: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(fetch_lib.ESearchError):
        fetch_lib.esearch_pmids("q", max_results=100, max_retries=2)


def test_honors_retry_after_header(monkeypatch):
    responses = [
        _FakeResponse(status_code=429, headers={"Retry-After": "0"}),
        _FakeResponse(json_data=_esearch_payload(["1"], 1)),
    ]
    slept = []

    def fake_get(url, params, timeout, follow_redirects):
        return responses.pop(0)

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(fetch_lib.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_lib.esearch_pmids("q", max_results=100)
    assert result["pmids"] == ["1"]
    assert 0.0 in slept


def test_invalid_query_syntax_raises(monkeypatch):
    def fake_get(url, params, timeout, follow_redirects):
        return _FakeResponse(json_data={"esearchresult": {"ERROR": "Invalid search term"}})

    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(fetch_lib.ESearchError):
        fetch_lib.esearch_pmids("bad[[query", max_results=100)


def test_empty_query_rejected():
    with pytest.raises(ValueError):
        fetch_lib.esearch_pmids("   ", max_results=100)


def test_api_key_included_when_env_set(monkeypatch):
    captured = {}

    def fake_get(url, params, timeout, follow_redirects):
        captured.update(params)
        return _FakeResponse(json_data=_esearch_payload(["1"], 1))

    monkeypatch.setenv("NCBI_API_KEY", "secret-key-123")
    monkeypatch.setattr(fetch_lib, "_rate_limit", lambda: None)
    monkeypatch.setattr(httpx, "get", fake_get)

    fetch_lib.esearch_pmids("q", max_results=100)
    assert captured["api_key"] == "secret-key-123"
