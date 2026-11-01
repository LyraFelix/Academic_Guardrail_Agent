"""Unit tests never use personal caches, external APIs or downloaded models."""
import pytest

from academic_guardrail.core import cache, semantic_matcher
from academic_guardrail.core.proxy_detector import SystemProxyDetector


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_DEFAULT_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache, "_global_cache", None)
    monkeypatch.setenv("RETRACTION_DB_PATH", ":memory:")
    monkeypatch.setenv("ACADEMIC_GUARDRAIL_REVIEW_DIR", str(tmp_path / "claim_reviews"))
    monkeypatch.setattr(semantic_matcher, "_HAS_ST", False)
    monkeypatch.setattr(SystemProxyDetector, "probe_local_proxy_ports", lambda: None)
    attempted = []

    async def block_http(self, request, *args, **kwargs):
        attempted.append(request.url.host)
        raise AssertionError("Unit tests must mock provider HTTP responses")

    monkeypatch.setattr("httpx.AsyncClient.send", block_http)
    yield
    assert not attempted, f"Unmocked HTTP requests in unit test: {attempted}"


@pytest.fixture
def make_text_pdf():
    """Create real, small text-layer PDFs without a new test dependency."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    def write(path, pages):
        writer = PdfWriter()
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        for text in pages:
            page = writer.add_blank_page(width=612, height=792)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            lines = ["BT /F1 12 Tf 40 740 Td 16 TL"]
            for line in text.splitlines():
                escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                lines.append(f"({escaped}) Tj T*")
            stream = DecodedStreamObject()
            stream.set_data(("\n".join(lines) + "\nET").encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(str(path))
        return path

    return write
