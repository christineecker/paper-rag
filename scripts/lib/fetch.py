"""NCBI fetching: PMID -> PMCID, JATS XML, PDF fallback, citation metadata, URL download."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from defusedxml import ElementTree as ET

ID_CONVERTER_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
OA_SERVICE_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"

_last_request_time = 0.0


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
    params = dict(extra)
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def pmid_to_pmcid(pmid: str) -> Optional[str]:
    """Look up the PMCID for a PMID via the NCBI ID converter API. None if not in PMC."""
    _rate_limit()
    resp = httpx.get(
        ID_CONVERTER_URL,
        params=_ncbi_params({"tool": "paper-rag", "email": "paper-rag@localhost", "ids": pmid, "format": "json"}),
        timeout=30.0,
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
    """
    match = re.search(rb"<article\b.*</article>", content, re.DOTALL)
    if not match:
        return content
    return b'<?xml version="1.0" encoding="UTF-8"?>' + _JATS_DOCTYPE + match.group(0)


def fetch_jats(pmcid: str, dest_dir: Path) -> Path:
    """Fetch full-text JATS XML for a PMCID via efetch (db=pmc). Writes dest_dir/source.xml."""
    _rate_limit()
    numeric_id = pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid
    resp = httpx.get(
        EFETCH_URL,
        params=_ncbi_params({"db": "pmc", "id": numeric_id, "rettype": "full", "retmode": "xml"}),
        timeout=60.0,
    )
    resp.raise_for_status()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "source.xml"
    dest_path.write_bytes(_unwrap_jats_articleset(resp.content))
    return dest_path


def fetch_oa_pdf(pmcid: str, dest_dir: Path) -> Optional[Path]:
    """Fetch a PDF via the PMC OA service, if the article is in the OA subset."""
    _rate_limit()
    resp = httpx.get(OA_SERVICE_URL, params=_ncbi_params({"id": pmcid}), timeout=30.0)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    for link in root.iter("link"):
        if link.get("format") == "pdf":
            href = link.get("href")
            if href:
                return fetch_url(href, dest_dir, filename="source.pdf")
    return None


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
