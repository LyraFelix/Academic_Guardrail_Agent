"""Reports must remain useful and safe when opened without a network."""

from html.parser import HTMLParser
from types import SimpleNamespace

from academic_guardrail.core.models import (
    Citation, ContextClaim, DocumentAuditReport, RiskLevel,
    VerificationResult, VerificationStatus,
)
from academic_guardrail.core.reporter import ReportGenerator


class Tags(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.tags = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def make_report():
    result = VerificationResult(
        citation=Citation(id="cit_1", raw_text="Original citation", title="Matched paper", doi="10.1/example"),
        status=VerificationStatus.VALID, risk_level=RiskLevel.PASS,
        claim=ContextClaim(citation_id="cit_1", claim_sentence="A claim", surrounding_context="Context"),
        evidence_text="Evidence excerpt", evidence_granularity="SENTENCE", message="Metadata matched",
    )
    return DocumentAuditReport(document_path="paper.docx", total_citations=1,
                               passed_count=1, warning_count=0, danger_count=0, results=[result])


def test_html_has_no_active_external_resources():
    content = ReportGenerator().generate_html(make_report())
    for tag, attrs in Tags(content).tags:
        assert not any(key in attrs for key in ("src", "srcset", "poster", "data", "action"))
        if "href" in attrs:
            assert tag == "a" and attrs["href"].startswith("https://doi.org/")
            assert attrs.get("rel") == "noopener noreferrer"
    for marker in ("@import", "url(", "fetch(", "XMLHttpRequest", "cdn.", "fonts.googleapis"):
        assert marker not in content
    assert "50K" not in content and "KaTeX" not in content


def test_zero_citations_is_not_a_success_claim():
    report = DocumentAuditReport(document_path="empty.docx", total_citations=0,
                                 passed_count=0, warning_count=0, danger_count=0, results=[])
    for content in (ReportGenerator().generate_html(report), ReportGenerator().generate_markdown(report)):
        assert "未提取到引用" in content
        assert "优秀" not in content
        assert "不代表" in content


def test_all_untrusted_html_fields_are_escaped():
    report = make_report()
    payload = '<img src="https://evil.example/pixel" onerror="alert(1)">'
    result = report.results[0]
    report.document_path = payload
    result.citation.id = payload
    result.citation.raw_text = payload
    result.citation.location_info = payload
    result.verified_title = payload
    result.message = payload
    result.evidence_text = payload
    result.evidence_granularity = payload
    result.claim.claim_sentence = payload
    result.resolution_metadata = {"title_score": payload}
    result.ambiguous_candidates = [{"title": payload, "doi": payload, "score": 0.5, "source": payload}]
    content = ReportGenerator().generate_html(report)
    assert payload not in content
    assert "&lt;img" in content
    assert not any(tag == "img" or "onerror" in attrs for tag, attrs in Tags(content).tags)


def test_provenance_and_offline_scope_are_visible():
    report = make_report()
    result = report.results[0]
    # Accept new fields without coupling these tests to the model migration.
    result = SimpleNamespace(**dict(result))
    result.sources = [SimpleNamespace(source="Local <index>", kind="retraction_lookup",
                                     identifier="10.1/source", detail="Checked local snapshot",
                                     is_retracted=False)]
    result.retraction_status = "NO_RECORD"
    report = SimpleNamespace(**dict(report))
    report.results = [result]
    report.offline = True
    content = ReportGenerator().generate_html(report)
    for expected in ("Local &lt;index&gt;", "retraction_lookup", "10.1/source", "Checked local snapshot",
                     "NO_RECORD", "离线", "元数据", "科学正确性"):
        assert expected in content
    assert "不代表" in content


def test_filter_assets_cover_all_risks_and_search():
    content = ReportGenerator().generate_html(make_report())
    tags = Tags(content).tags
    filters = {attrs.get("value") for tag, attrs in tags if tag == "option"}
    assert filters == {"all", "pass", "notice", "warning", "danger"}
    assert any(tag == "input" and attrs.get("type") == "search" for tag, attrs in tags)
    assert any(tag == "article" and attrs.get("data-risk") == "pass" for tag, attrs in tags)
    assert "addEventListener" in content and "textContent" in content
    assert "没有符合筛选条件的引用" in content


def test_markdown_neutral_pass_scope_and_untrusted_text():
    report = make_report()
    report.results[0].message = '<script>alert(1)</script> | [bad](javascript:alert(1))'
    content = ReportGenerator().generate_markdown(report)
    assert "科学正确性" in content
    assert "优秀" not in content
    assert "<script>" not in content
    assert "\\[bad\\]" in content
