"""Data models for academic citations, claims, and verification results."""

from enum import Enum
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator


class RiskLevel(str, Enum):
    PASS = "PASS"             # 🟢 正常/通过
    NOTICE = "NOTICE"         # 🔵 提示 (断言略有偏差)
    WARNING = "WARNING"       # 🟡 警告 (未能从数据库检索验证)
    DANGER = "DANGER"         # 🔴 高危 (撤稿或疑似虚构幻觉)


class VerificationStatus(str, Enum):
    VALID = "VALID"                       # 元数据真实匹配且正常
    RETRACTED = "RETRACTED"               # 已被撤稿或有学术警示
    UNVERIFIED = "UNVERIFIED"             # 检索库未能核实或基础设施不可用
    CLAIM_MISMATCH = "CLAIM_MISMATCH"     # 文献真实存在但断言偏差
    HALLUCINATED = "HALLUCINATED"         # 疑似 LLM 虚构论文


class EvidenceStatus(str, Enum):
    PARSE_INCOMPLETE = "PARSE_INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"
    LOCAL_MATCHED = "LOCAL_MATCHED"
    RETRACTED = "RETRACTED"
    OFFLINE_NO_MATCH = "OFFLINE_NO_MATCH"
    ARTICLE_MATCHED = "ARTICLE_MATCHED"
    JOURNAL_MATCHED_ARTICLE_UNVERIFIED = "JOURNAL_MATCHED_ARTICLE_UNVERIFIED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    NO_RETRACTION_FOUND = "NO_RETRACTION_FOUND"
    RETRACTION_SUSPECTED = "RETRACTION_SUSPECTED"


class RetractionStatus(str, Enum):
    """A negative lookup is limited to the consulted sources, never proof of safety."""

    CONFIRMED = "CONFIRMED"
    SUSPECTED = "SUSPECTED"
    NO_RECORD = "NO_RECORD"
    NOT_CHECKED = "NOT_CHECKED"


class EvidenceSource(BaseModel):
    """Where an observation came from; kept separate from the final decision."""

    source: str
    kind: str
    identifier: Optional[str] = None
    detail: Optional[str] = None
    is_retracted: Optional[bool] = None


class SourceLocation(BaseModel):
    """Offsets are zero-based [start, end) in extracted text, never PDF bytes."""

    file_path: str
    page: Optional[int] = None  # One-based physical PDF page, including blank pages.
    line: Optional[int] = None  # One-based line in extracted text.
    char_start: int
    char_end: int


class ParseDiagnostic(BaseModel):
    code: str
    message: str
    location: Optional[SourceLocation] = None


class EvidencePassage(BaseModel):
    text: str
    source_kind: str  # LOCAL_FULLTEXT or ONLINE_ABSTRACT
    location: Optional[SourceLocation] = None


class Citation(BaseModel):
    id: str                               # 唯一识别符 e.g. "cit_1"
    raw_text: str                         # 引用的原始文本
    doi: Optional[str] = None             # 提取到的 DOI (若有)
    title: Optional[str] = None           # 解析出的论文标题
    authors: List[str] = Field(default_factory=list) # 作者列表
    year: Optional[int] = None            # 发表年份
    venue: Optional[str] = None           # 发表期刊/会议名称
    location_info: Optional[str] = None   # 在原文档中的位置 e.g. "Page 3, Paragraph 2"
    location: Optional[SourceLocation] = None
    parse_status: Literal["PARSED", "MISSING", "AMBIGUOUS"] = "PARSED"


class ContextClaim(BaseModel):
    citation_id: str                      # 关联的 Citation ID
    claim_sentence: str                   # 包含引用的正文断言句
    surrounding_context: str              # 上下文背景 (前后 1-2 句)
    occurrence_id: Optional[str] = None
    marker: Optional[str] = None
    location: Optional[SourceLocation] = None


class ParsedDocument(BaseModel):
    citations: List[Citation] = Field(default_factory=list)
    occurrences: List[ContextClaim] = Field(default_factory=list)
    diagnostics: List[ParseDiagnostic] = Field(default_factory=list)


class SemanticFinding(BaseModel):
    """A bounded rule observation, with the exact text that triggered it."""

    code: str
    category: Literal["NUMBER", "NEGATION", "CAUSALITY", "SCOPE", "EVIDENCE"]
    severity: Literal["CONFLICT", "REVIEW"] = "REVIEW"
    message: str
    claim_text: str
    evidence_text: str
    evidence_location: Optional[SourceLocation] = None

    evidence_source: Optional[str] = None


class ClaimAssessment(BaseModel):
    state: Literal["TEXT_ALIGNED", "POTENTIAL_CONFLICT", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"]
    similarity_score: float = 0.0  # Retrieval score, never a truth probability.
    message: str
    evidence_text: str = ""
    evidence_location: Optional[SourceLocation] = None
    text_source: Optional[str] = None
    alignment_engine: str = "rule_lexical_fallback"
    findings: List[SemanticFinding] = Field(default_factory=list)


class VerificationResult(BaseModel):
    citation: Citation
    claim: Optional[ContextClaim] = None
    status: VerificationStatus
    risk_level: RiskLevel
    sources: List[EvidenceSource] = Field(default_factory=list)
    retraction_status: RetractionStatus = RetractionStatus.NOT_CHECKED
    verification_scope: str = "REFERENCE_METADATA"
    evidence_status: Optional[EvidenceStatus] = None  # 细粒度证据/基础设施状态
    failure_reason: Optional[str] = None               # TIMEOUT / RATE_LIMITED / PROXY_ERROR
    verified_title: Optional[str] = None
    verified_doi: Optional[str] = None
    retraction_info: Optional[str] = None
    abstract_tldr: Optional[str] = None
    evidence_text: Optional[str] = None                # 精准提炼的证据片段
    evidence_granularity: Optional[str] = None         # "SENTENCE" | "CLAUSE" | "EXPANDED_WINDOW"
    evidence_location: Optional[SourceLocation] = None
    text_source: Optional[str] = None
    retrieval_status: Literal["NOT_REQUESTED", "AVAILABLE", "NO_TEXT", "NO_RELEVANT_PASSAGE", "AMBIGUOUS"] = "NOT_REQUESTED"
    semantic_mode: Optional[str] = None                # "CORE" | "FULL" | "CORE_FALLBACK"
    reference_confidence: Optional[float] = None  # 0.0 ~ 1.0 文献元数据匹配置信度
    claim_alignment_score: Optional[float] = None  # Retrieval similarity, not a truth probability.
    alignment_state: Optional[str] = None  # ClaimAssessment.state; old serialized labels remain readable.
    semantic_findings: List[SemanticFinding] = Field(default_factory=list)
    alignment_engine: Optional[str] = None  # "vector_embedding" | "rule_lexical_fallback"
    resolution_metadata: Optional[Dict[str, Any]] = None  # 详细匹配打分分解 (title_score, author_score, etc.)
    ambiguous_candidates: Optional[List[Dict[str, Any]]] = None  # 歧义文献候选对比列表
    message: str                          # 详细说明/修复指引

    @property
    def nli_state(self) -> Optional[str]:
        """Backward compatibility alias for alignment_state."""
        return self.alignment_state


class DocumentAuditReport(BaseModel):
    document_path: str
    offline: bool = False
    total_citations: int  # Compatibility: result rows, not unique references.
    total_references: Optional[int] = None
    total_occurrences: Optional[int] = None
    parse_diagnostics: List[ParseDiagnostic] = Field(default_factory=list)
    passed_count: int
    notice_count: int = 0
    warning_count: int
    danger_count: int
    results: List[VerificationResult]

    @model_validator(mode="after")
    def infer_legacy_counts(self):
        """Old callers can omit the new counts; do not display invented zeros."""
        if self.total_references is None:
            self.total_references = len({r.citation.id for r in self.results if r.citation.parse_status != "MISSING"})
        if self.total_occurrences is None:
            self.total_occurrences = sum(r.claim is not None for r in self.results)
        return self


class PaperRecord(BaseModel):
    filename: str                         # 文件名 e.g. "2023_v2_final.pdf"
    filepath: str                         # 完整绝对路径
    title: str                            # 从正文截取抽取的实际标题
    authors: List[str] = Field(default_factory=list) # 作者列表
    year: Optional[int] = None            # 发表年份
    abstract: str = ""                    # 自动提取到的 Abstract / 摘要
    fulltext: str = ""                    # 提取到的原文全文本
    doi: Optional[str] = None
    doi_candidates: List[str] = Field(default_factory=list)
    abstract_location: Optional[SourceLocation] = None
    passages: List[EvidencePassage] = Field(default_factory=list)
