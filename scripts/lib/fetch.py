"""NCBI fetching: PMID -> PMCID, JATS XML, PDF fallback, citation metadata, URL download."""
from __future__ import annotations

import os
import random
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from defusedxml import ElementTree as ET

ID_CONVERTER_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
# The old oa.fcgi OA package/PDF service was retired by NCBI in Aug 2026; article
# files (JATS XML, PDF, media) now live on the PMC Cloud Service (S3), unauthenticated.
PMC_S3_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"
_S3_LIST_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif")

TOOL_NAME = "paper-rag"
CONTACT_EMAIL = "paper-rag@localhost"

# Hard ceiling on PMIDs fetched per esearch_pmids() call, independent of the
# caller-requested max_results, so a bad/broad query can't paginate forever.
ESEARCH_SAFETY_LIMIT = 10_000
DEFAULT_ESEARCH_PAGE_SIZE = 500

_last_request_time = 0.0


class ESearchError(RuntimeError):
    """Raised when ESearch cannot be completed: bad query syntax, rate limiting
    that persists past retries, or PubMed being unavailable."""


def _rate_limit() -> None:
    """Respect NCBI rate limits: <=3 req/s without an API key."""
    global _last_request_time
    has_key = bool(os.environ.get("NCBI_API_KEY"))
    min_interval = 1.0 / 10 if has_key else 1.0 / 3
    elapsed = time.monotonic() - _last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_request_time = time.monotonic()


def _ncbi_params(extra: dict) -> dict:
    params = {"tool": TOOL_NAME, "email": CONTACT_EMAIL}
    params.update(extra)
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def _backoff_sleep(attempt: int) -> None:
    base = min(2**attempt, 30)
    time.sleep(base + random.uniform(0, base * 0.25))


def _get_with_retry(url: str, params: dict, *, timeout: float, max_retries: int) -> httpx.Response:
    """GET with NCBI rate-limiting plus retry/backoff+jitter on timeouts, 429s, and
    5xx responses. Honors a numeric Retry-After header when present."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        _rate_limit()
        try:
            resp = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            _backoff_sleep(attempt)
            continue

        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            last_error = ESearchError(f"NCBI returned HTTP {resp.status_code}")
            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    time.sleep(max(0.0, float(retry_after)))
                    continue
                except ValueError:
                    pass
            _backoff_sleep(attempt)
            continue

        resp.raise_for_status()
        return resp

    raise ESearchError(f"ESearch request failed after {max_retries} attempts") from last_error


def esearch_pmids(
    query: str,
    *,
    max_results: int = 1000,
    page_size: int = DEFAULT_ESEARCH_PAGE_SIZE,
    max_retries: int = 5,
) -> dict:
    """Run PubMed ESearch for a compiled query, paginating with usehistory until
    `max_results`, PubMed's reported total, or ESEARCH_SAFETY_LIMIT is reached.

    Returns a dict: pmids (deduped across pages, first-seen order), total_count,
    returned_count, truncated, query_translation, webenv, querykey.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if max_results <= 0:
        raise ValueError("max_results must be positive")
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    safety_limit = min(max_results, ESEARCH_SAFETY_LIMIT)
    page_size = max(1, min(page_size, safety_limit))

    pmids: list[str] = []
    seen: set[str] = set()
    total_count = 0
    query_translation: Optional[str] = None
    webenv: Optional[str] = None
    querykey: Optional[str] = None
    retstart = 0

    while len(pmids) < safety_limit:
        retmax = min(page_size, safety_limit - len(pmids))
        params = _ncbi_params(
            {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retstart": retstart,
                "retmax": retmax,
                "usehistory": "y",
            }
        )
        resp = _get_with_retry(ESEARCH_URL, params, timeout=30.0, max_retries=max_retries)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ESearchError("ESearch returned non-JSON response") from exc

        result = data.get("esearchresult")
        if result is None:
            raise ESearchError(f"unexpected ESearch response: {data!r}")
        if "ERROR" in result:
            raise ESearchError(f"invalid PubMed query: {result['ERROR']}")

        total_count = int(result.get("count", 0))
        query_translation = result.get("querytranslation", query_translation)
        webenv = result.get("webenv", webenv)
        querykey = result.get("querykey", querykey)

        page_ids = result.get("idlist", [])
        if not page_ids:
            break
        for pmid in page_ids:
            if pmid not in seen:
                seen.add(pmid)
                pmids.append(pmid)

        retstart += len(page_ids)
        if retstart >= total_count:
            break

    return {
        "pmids": pmids,
        "total_count": total_count,
        "returned_count": len(pmids),
        "truncated": total_count > len(pmids),
        "query_translation": query_translation,
        "webenv": webenv,
        "querykey": querykey,
    }


def pmid_to_pmcid(pmid: str) -> Optional[str]:
    """Look up the PMCID for a PMID via the NCBI ID converter API. None if not in PMC."""
    _rate_limit()
    resp = httpx.get(
        ID_CONVERTER_URL,
        params=_ncbi_params({"tool": "paper-rag", "email": "paper-rag@localhost", "ids": pmid, "format": "json"}),
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    records = data.get("records", [])
    if not records:
        return None
    record = records[0]
    if "pmcid" not in record or "errmsg" in record:
        return None
    return record["pmcid"]


def find_pmid_by_doi(doi: str) -> Optional[str]:
    """Look up the PMID for a DOI via the NCBI ESearch API. None if not found."""
    _rate_limit()
    resp = httpx.get(
        ESEARCH_URL,
        params=_ncbi_params({"db": "pubmed", "term": f"{doi}[AID]", "retmode": "json"}),
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    ids = resp.json().get("esearchresult", {}).get("idlist", [])
    return ids[0] if ids else None


_JATS_DOCTYPE = (
    b'<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD v1.2 20190208//EN" '
    b'"JATS-journalpublishing1.dtd">'
)


def _unwrap_jats_articleset(content: bytes) -> bytes:
    """Unwrap NCBI's efetch (db=pmc) ``<pmc-articleset>`` envelope to a bare
    ``<article>`` with a JATS DOCTYPE.

    efetch always wraps the article in a ``pmc-articleset`` element carrying an NLM
    "ARTICLE SET" DOCTYPE, not a JATS one. docling's format sniffer only recognizes
    JATS XML when the DOCTYPE names JATS-journalpublishing/-archive, so the wrapped
    document is otherwise left undetected and conversion fails.

    Also strips any ``<processing-meta>`` element (NLM archiving-tagset metadata,
    not article content). Some PMC exports carry a `table-model="xhtml"` attribute
    on it near the top of the document; docling's mime sniffer does a naive
    substring search for "xhtml" in the first 1000 characters, so that attribute
    alone gets the whole document mis-sniffed as XHTML -- which excludes JATS from
    the candidate formats entirely and skips the DOCTYPE check that would
    otherwise have identified it correctly.
    """
    match = re.search(rb"<article\b.*</article>", content, re.DOTALL)
    if not match:
        return content
    article = re.sub(rb"<processing-meta\b.*?(?:/>|</processing-meta>)", b"", match.group(0), flags=re.DOTALL)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + _JATS_DOCTYPE + article


def fetch_jats(pmcid: str, dest_dir: Path) -> Path:
    """Fetch full-text JATS XML for a PMCID via efetch (db=pmc). Writes dest_dir/source.xml."""
    _rate_limit()
    numeric_id = pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid
    resp = httpx.get(
        EFETCH_URL,
        params=_ncbi_params({"db": "pmc", "id": numeric_id, "rettype": "full", "retmode": "xml"}),
        timeout=60.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "source.xml"
    dest_path.write_bytes(_unwrap_jats_articleset(resp.content))
    return dest_path


def _list_pmc_s3_keys(pmcid: str) -> list[str]:
    """List every object key on the PMC Cloud Service (S3) under a PMCID's prefix,
    across all versions. Empty if the article isn't in the OA subset there."""
    numeric_id = pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid
    resp = httpx.get(
        PMC_S3_BASE,
        params={"list-type": "2", "prefix": f"PMC{numeric_id}."},
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    return [el.text for el in root.findall(".//s3:Contents/s3:Key", _S3_LIST_NS) if el.text]


def _latest_pmc_s3_version_prefix(keys: list[str]) -> Optional[str]:
    """Highest-versioned ``PMCxxxxx.N`` key prefix present in a listing."""
    versions = {k.split("/", 1)[0] for k in keys if "/" in k}
    if not versions:
        return None
    return max(versions, key=lambda v: int(v.rsplit(".", 1)[1]))


def fetch_pmc_package(pmcid: str, dest_dir: Path) -> Optional[Path]:
    """Fetch full-text JATS XML plus its figure images from the PMC Cloud Service
    (S3). Writes dest_dir/source.xml and the referenced raster images alongside it
    (same filenames as their JATS xlink:href) so docling's JATS backend can resolve
    and embed them -- tables come along for free since JATS table-wrap markup is
    parsed directly from the XML, no image needed. Returns None if the PMCID has no
    package there (not in the OA subset)."""
    keys = _list_pmc_s3_keys(pmcid)
    version_prefix = _latest_pmc_s3_version_prefix(keys)
    if version_prefix is None:
        return None
    version_keys = [k for k in keys if k.startswith(version_prefix + "/")]
    xml_key = next((k for k in version_keys if k.endswith(".xml")), None)
    if xml_key is None:
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    xml_resp = httpx.get(f"{PMC_S3_BASE}/{xml_key}", timeout=60.0, follow_redirects=True)
    xml_resp.raise_for_status()
    dest_path = dest_dir / "source.xml"
    dest_path.write_bytes(xml_resp.content)

    for key in version_keys:
        if key == xml_key:
            continue
        filename = key.rsplit("/", 1)[-1]
        if Path(filename).suffix.lower() not in IMAGE_EXTS:
            continue
        media_resp = httpx.get(f"{PMC_S3_BASE}/{key}", timeout=60.0, follow_redirects=True)
        media_resp.raise_for_status()
        (dest_dir / filename).write_bytes(media_resp.content)

    return dest_path


def fetch_oa_pdf(pmcid: str, dest_dir: Path) -> Optional[Path]:
    """Fetch the publisher PDF from the PMC Cloud Service (S3), if the article is
    in the OA subset there."""
    keys = _list_pmc_s3_keys(pmcid)
    version_prefix = _latest_pmc_s3_version_prefix(keys)
    if version_prefix is None:
        return None
    pdf_key = next(
        (
            k
            for k in keys
            if k.startswith(version_prefix + "/") and k.endswith(".pdf") and "MOESM" not in k
        ),
        None,
    )
    if pdf_key is None:
        return None
    return fetch_url(f"{PMC_S3_BASE}/{pdf_key}", dest_dir, filename="source.pdf")


def fetch_url(url: str, dest_dir: Path, filename: Optional[str] = None) -> Path:
    """Download a direct file URL (PDF/XML/etc). Avoids scraping HTML article pages."""
    if url.startswith("ftp://"):
        import urllib.request

        dest_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = _filename_from_url(url)
        dest_path = dest_dir / filename
        urllib.request.urlretrieve(url, dest_path)
        return dest_path

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = _filename_from_url(url, content_type=resp.headers.get("content-type", ""))
        dest_path = dest_dir / filename
        dest_path.write_bytes(resp.content)
        return dest_path


def _filename_from_url(url: str, content_type: str = "") -> str:
    tail = url.rstrip("/").split("/")[-1]
    ext = Path(tail).suffix.lower()
    if ext in (".pdf", ".xml", ".html", ".htm"):
        return f"source{ext}"
    if "pdf" in content_type:
        return "source.pdf"
    if "xml" in content_type:
        return "source.xml"
    if "html" in content_type:
        return "source.html"
    return "source.bin"


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or el.text is None:
        return None
    return "".join(el.itertext()).strip() or None


def fetch_citation_metadata(pmid: str) -> dict:
    """Fetch structured citation metadata for a PMID via efetch (db=pubmed)."""
    _rate_limit()
    resp = httpx.get(
        EFETCH_URL,
        params=_ncbi_params({"db": "pubmed", "id": pmid, "rettype": "xml", "retmode": "xml"}),
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    article = root.find(".//PubmedArticle")
    if article is None:
        raise ValueError(f"No PubMed record found for PMID {pmid}")

    article_el = article.find(".//Article")
    title = _text(article_el.find("ArticleTitle")) if article_el is not None else None

    authors = []
    for author_el in article.findall(".//AuthorList/Author"):
        family = _text(author_el.find("LastName"))
        given = _text(author_el.find("ForeName")) or _text(author_el.find("Initials"))
        if family:
            authors.append({"family": family, "given": given or ""})

    journal_el = article.find(".//Journal")
    journal = None
    year = None
    volume = None
    issue = None
    if journal_el is not None:
        journal = _text(journal_el.find("Title")) or _text(journal_el.find("ISOAbbreviation"))
        volume = _text(journal_el.find("JournalIssue/Volume"))
        issue = _text(journal_el.find("JournalIssue/Issue"))
        year = (
            _text(journal_el.find("JournalIssue/PubDate/Year"))
            or _text(journal_el.find("JournalIssue/PubDate/MedlineDate"))
        )
        if year:
            match = re.match(r"(\d{4})", year)
            year = match.group(1) if match else year

    pages = _text(article.find(".//Pagination/MedlinePgn"))
    elocation_id = None
    for eloc in article.findall(".//ELocationID"):
        elocation_id = _text(eloc)
        if elocation_id:
            break

    doi = None
    for eloc in article.findall(".//ELocationID"):
        if eloc.get("EIdType") == "doi":
            doi = _text(eloc)
            break
    if doi is None:
        for aid in article.findall(".//ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
                break

    abstract_parts = [
        _text(el) for el in article.findall(".//Abstract/AbstractText") if _text(el)
    ]
    abstract = " ".join(abstract_parts) if abstract_parts else None

    keywords = []
    for mesh in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName"):
        text = _text(mesh)
        if text:
            keywords.append(text)
    for kw in article.findall(".//KeywordList/Keyword"):
        text = _text(kw)
        if text:
            keywords.append(text)
    seen = set()
    deduped_keywords = []
    for kw in keywords:
        key = kw.lower()
        if key not in seen:
            seen.add(key)
            deduped_keywords.append(kw)

    pub_types = []
    for pt in article.findall(".//PublicationTypeList/PublicationType"):
        text = _text(pt)
        if text:
            pub_types.append(text)

    pmcid = None
    for aid in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "pmc":
            pmcid = _text(aid)
            break
    if pmcid is None:
        try:
            pmcid = pmid_to_pmcid(pmid)
        except Exception:
            pmcid = None

    return {
        "pmid": pmid,
        "pmcid": pmcid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": doi,
        "abstract": abstract,
        "keywords": deduped_keywords,
        "pub_types": pub_types,
        "elocation_id": elocation_id,
    }


def fetch_citation_metadata_from_jats(jats_path: Path) -> dict:
    """Fallback: parse citation metadata from JATS front matter (no PMID available)."""
    root = ET.parse(jats_path).getroot()
    front = root.find(".//front")
    if front is None:
        front = root

    title = _text(front.find(".//article-title"))

    authors = []
    for contrib in front.findall('.//contrib-group/contrib[@contrib-type="author"]'):
        name_el = contrib.find("name")
        if name_el is None:
            continue
        family = _text(name_el.find("surname"))
        given = _text(name_el.find("given-names"))
        if family:
            authors.append({"family": family, "given": given or ""})

    journal = _text(front.find('.//journal-title')) or _text(front.find(".//journal-title-group/journal-title"))
    year = _text(front.find('.//pub-date/year'))
    volume = _text(front.find(".//volume"))
    issue = _text(front.find(".//issue"))
    pages = _text(front.find(".//fpage"))
    lpage = _text(front.find(".//lpage"))
    if pages and lpage:
        pages = f"{pages}-{lpage}"

    doi = None
    for aid in front.findall(".//article-id"):
        if aid.get("pub-id-type") == "doi":
            doi = _text(aid)
            break

    pmcid = None
    for aid in front.findall(".//article-id"):
        if aid.get("pub-id-type") == "pmc":
            pmcid = _text(aid)
            break

    elocation_id = _text(front.find(".//elocation-id"))

    abstract_el = front.find(".//abstract")
    abstract = _text(abstract_el) if abstract_el is not None else None

    keywords = []
    for kwd in front.findall(".//kwd-group/kwd"):
        text = _text(kwd)
        if text:
            keywords.append(text)

    return {
        "pmid": None,
        "pmcid": pmcid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": doi,
        "abstract": abstract,
        "keywords": keywords,
        "pub_types": None,
        "elocation_id": elocation_id,
    }
