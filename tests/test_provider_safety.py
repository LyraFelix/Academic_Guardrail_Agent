"""Offline regression tests for identity, evidence and provider failures."""
import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from academic_guardrail.core.exceptions import ProviderError
from academic_guardrail.core.models import Citation
from academic_guardrail.core.ref_resolver import ReferenceResolver
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.crossref import CrossrefProvider
from academic_guardrail.providers.openalex import OpenAlexProvider
from academic_guardrail.providers.http_client import AcademicHttpClient


@pytest.fixture
def provider():
    client = Mock(get_json=AsyncMock(return_value=None), close=AsyncMock())
    result = ChineseAcademicProvider(client=client)
    result.openalex.get_by_doi = AsyncMock(return_value=None)
    result.crossref.get_by_doi = AsyncMock(return_value=None)
    result.openalex.search_by_title = AsyncMock(return_value=[])
    result.crossref.search_by_title = AsyncMock(return_value=[])
    result._search_semantic_scholar_candidates = AsyncMock(return_value=[])
    yield result
    result.retraction_db.close()


@pytest.mark.parametrize("reverse", [False, True])
def test_same_doi_keeps_positive_and_all_sources(reverse):
    candidates = [
        {"title": "A reliable paper title", "doi": "10.1234/example",
         "source": "OpenAlex", "is_retracted": False},
        {"title": "A reliable paper title", "doi": "https://doi.org/10.1234/example",
         "source": "Crossref", "is_retracted": True},
    ]
    merged = ReferenceResolver.deduplicate_candidates(candidates[::-1] if reverse else candidates)[0]
    assert merged["is_retracted"] is True
    assert merged["retraction_status"] == "CONFIRMED"
    assert {s["source"] for s in merged["sources"]} == {"OpenAlex", "Crossref"}


def test_local_candidates_can_skip_deduplication():
    candidates = [{"title": "A reliable paper title"} for _ in range(2)]
    best = ReferenceResolver().select_best_candidate(
        Citation(id="1", raw_text="", title="A reliable paper title"),
        candidates, deduplicate=False)
    assert best["is_uncertain"]


@pytest.mark.asyncio
async def test_title_match_rechecks_offline_database(provider):
    title = "Stimulus-triggered fate conversion of somatic cells into pluripotency"
    provider.openalex.search_by_title.return_value = [
        {"title": title, "doi": "10.1038/nature12968", "is_retracted": False}]
    result = await provider.verify_citation(title)
    assert result["retraction_status"] == "CONFIRMED"
    assert any(s["kind"] == "offline_database" and s["is_retracted"] for s in result["sources"])


@pytest.mark.asyncio
async def test_failure_is_not_not_found(provider):
    for method in (provider.openalex.search_by_title, provider.crossref.search_by_title,
                   provider._search_semantic_scholar_candidates):
        method.side_effect = ProviderError("unavailable")
    result = await provider.verify_citation("A reliable paper title")
    assert result["matched"] is None
    assert result["evidence_status"] == "PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_doi_mismatch_cannot_be_exact_match(provider):
    provider.openalex.get_by_doi.return_value = {
        "title": "Unrelated paper", "doi": "10.1234/other", "is_retracted": True}
    result = await provider.verify_citation("", doi="10.1234/requested")
    assert result["matched"] is not True
    assert result["is_retracted"] is False


@pytest.mark.asyncio
async def test_authors_and_year_reach_resolver(provider):
    provider.openalex.search_by_title.return_value = [{"title": "A reliable paper title"}]
    provider.resolver.select_best_candidate = Mock(return_value=None)
    await provider.verify_citation("A reliable paper title", authors=["Alice"], year=2020)
    citation = provider.resolver.select_best_candidate.call_args.args[0]
    assert citation.authors == ["Alice"] and citation.year == 2020


@pytest.mark.asyncio
async def test_failed_s2_request_is_not_cached(provider):
    provider.client.get_json.side_effect = ProviderError("unavailable")
    for _ in range(2):
        with pytest.raises(ProviderError):
            await ChineseAcademicProvider._search_semantic_scholar_candidates(provider, "same query")
    assert provider.client.get_json.await_count == 2


@pytest.mark.asyncio
async def test_openalex_no_numeric_arxiv_fallback():
    client = Mock(get_json=AsyncMock(side_effect=[
        None, {"results": [{"title": "Other", "doi": "10.9999/other"}]}]))
    assert await OpenAlexProvider(client=client).get_by_doi("10.5555/2020.12345") is None
    assert client.get_json.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type,payload", [
    (OpenAlexProvider, {"title": "Other", "doi": "10.9999/other"}),
    (CrossrefProvider, {"message": {"title": ["Other"], "DOI": "10.9999/other"}}),
])
async def test_direct_provider_rejects_wrong_doi(provider_type, payload):
    client = Mock(get_json=AsyncMock(return_value=payload))
    with pytest.raises(ProviderError):
        await provider_type(client=client).get_by_doi("10.1234/requested")


@pytest.mark.asyncio
async def test_title_keywords_only_suspected(provider):
    title = "Why scientific retraction rates differ across disciplines"
    provider.openalex.get_by_doi.return_value = {
        "title": title, "doi": "10.1234/paper", "is_retracted": False}
    result = await provider.verify_citation(title, doi="10.1234/paper")
    assert result["is_retracted"] is False
    assert result["retraction_status"] == "SUSPECTED"


def test_openalex_title_keyword_only_suspected():
    result = OpenAlexProvider(client=Mock())._process_work(
        {"title": "Retracted articles in science", "doi": "10.1234/paper", "is_retracted": False})
    assert result["is_retracted"] is False
    assert result["retraction_status"] == "SUSPECTED"


@pytest.mark.asyncio
async def test_crossref_title_keyword_only_suspected():
    client = Mock(get_json=AsyncMock(return_value={"message": {
        "DOI": "10.1234/paper", "title": ["Retraction rates in science"]}}))
    result = await CrossrefProvider(client=client).get_by_doi("10.1234/paper")
    assert result["is_retracted"] is False
    assert result["retraction_status"] == "SUSPECTED"


@pytest.mark.asyncio
async def test_http_failure_raises_instead_of_absence():
    client = AcademicHttpClient(max_retries=0)
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
    try:
        with pytest.raises(ProviderError):
            await client.get_json("https://example.invalid/paper")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_close_also_closes_database(provider):
    await provider.close()
    assert provider.retraction_db._conn is None


@pytest.mark.asyncio
async def test_cancellation_waits_for_provider_cleanup(provider):
    cleaned = []
    started = asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            await asyncio.sleep(0)
            cleaned.append(True)

    provider.openalex.search_by_title.side_effect = slow
    task = asyncio.create_task(provider.verify_citation("A reliable paper title"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned == [True]


@pytest.mark.asyncio
async def test_supplementary_metadata_keeps_retraction(provider):
    title = "A reliable paper title"
    provider.crossref.search_by_title.return_value = [
        {"title": title, "doi": "10.1234/paper", "is_retracted": False}]
    provider.openalex.get_by_doi.return_value = {
        "title": title, "doi": "10.1234/paper", "abstract": "Evidence",
        "is_retracted": True}
    result = await provider.verify_citation(title)
    assert result["retraction_status"] == "CONFIRMED"
    assert result["abstract"] == "Evidence"
    assert {s["source"] for s in result["sources"]} >= {"OpenAlex", "Crossref"}


@pytest.mark.asyncio
async def test_partial_failure_keeps_unknown_source(provider):
    provider.openalex.get_by_doi.return_value = {
        "title": "A reliable paper title", "doi": "10.1234/paper", "is_retracted": False}
    provider.crossref.get_by_doi.side_effect = ProviderError("unavailable")
    result = await provider.verify_citation("", doi="10.1234/paper")
    assert result["matched"] is True
    assert any(s["source"] == "Crossref" and s["is_retracted"] is None
               for s in result["sources"])


@pytest.mark.asyncio
async def test_http_404_is_absence():
    client = AcademicHttpClient(max_retries=0)
    client._client.get = AsyncMock(return_value=httpx.Response(404))
    try:
        assert await client.get_json("https://example.invalid/paper") is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_openalex_malformed_work_is_failure():
    provider = OpenAlexProvider(client=Mock(get_json=AsyncMock(return_value={})))
    with pytest.raises(ProviderError):
        await provider.get_by_doi("10.1234/paper")


@pytest.mark.asyncio
async def test_collection_timeout_awaits_cleanup():
    cleaned = []

    async def slow():
        try:
            await asyncio.sleep(60)
        finally:
            await asyncio.sleep(0)
            cleaned.append(True)

    results, failures = await ChineseAcademicProvider._collect_queries(
        [("slow", slow())], timeout=0.01)
    assert results == {} and failures == {"slow": "TIMEOUT"}
    assert cleaned == [True]


def test_configured_database_preserves_existing_retraction_record(tmp_path):
    import sqlite3
    from academic_guardrail.providers.retraction_db import OfflineRetractionDB
    path = tmp_path / "existing.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE retractions (doi TEXT PRIMARY KEY, title TEXT, journal TEXT, retraction_date TEXT, reason TEXT)")
        conn.execute("INSERT INTO retractions VALUES (?, ?, ?, ?, ?)",
                     ("10.1038/nature12968", "Curated title", "Nature", "2014-07-02", "Curated local reason"))
    db = OfflineRetractionDB(str(path))
    try:
        assert db.check_doi("10.1038/nature12968")["reason"] == "Curated local reason"
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT reason FROM retractions WHERE doi=?", ("10.1038/nature12968",)).fetchone()[0] == "Curated local reason"
    finally:
        db.close()
