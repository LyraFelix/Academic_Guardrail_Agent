"""Data models for academic citations, claims, and verification results."""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    PASS = "PASS"             # 🟢 正常/通过
    NOTICE = "NOTICE"         # 🔵 提示 (断言略有偏差)
    WARNING = "WARNING"       # 🟡 警告 (未能从数据库检索验证)
    DANGER = "DANGER"         # 🔴 高危 (撤稿或疑似虚构幻觉)


class VerificationStatus(str, Enum):
    VALID = "VALID"                       # 元数据真实匹配且正常
    RETRACTED = "RETRACTED"               # 已被撤稿或有学术警示
    UNVERIFIED = "UNVERIFIED"             # 检索库未能核实
    CLAIM_MISMATCH = "CLAIM_MISMATCH"     # 文献真实存在但断言偏差
    HALLUCINATED = "HALLUCINATED"         # 疑似 LLM 虚构论文


class Citation(BaseModel):
    id: str                               # 唯一识别符 e.g. "cit_1"
    raw_text: str                         # 引用的原始文本
    doi: Optional[str] = None             # 提取到的 DOI (若有)
    title: Optional[str] = None           # 解析出的论文标题
    authors: List[str] = Field(default_factory=list) # 作者列表
    year: Optional[int] = None            # 发表年份
    venue: Optional[str] = None           # 发表期刊/会议名称
    location_info: Optional[str] = None   # 在原文档中的位置 e.g. "Page 3, Paragraph 2"


class ContextClaim(BaseModel):
    citation_id: str                      # 关联的 Citation ID
    claim_sentence: str                   # 包含引用的正文断言句
    surrounding_context: str              # 上下文背景 (前后 1-2 句)


class VerificationResult(BaseModel):
    citation: Citation
    claim: Optional[ContextClaim] = None
    status: VerificationStatus
    risk_level: RiskLevel
    verified_title: Optional[str] = None
    verified_doi: Optional[str] = None
    retraction_info: Optional[str] = None
    abstract_tldr: Optional[str] = None
    reference_confidence: Optional[float] = None  # 0.0 ~ 1.0 文献元数据匹配置信度
    claim_alignment_score: Optional[float] = None  # 0.0 ~ 1.0 语义对齐得分
    nli_state: Optional[str] = None  # "ENTAILED" | "CONTRADICTED" | "NEUTRAL" | "UNVERIFIED"
    message: str                          # 详细说明/修复指引


class DocumentAuditReport(BaseModel):
    document_path: str
    total_citations: int
    passed_count: int
    warning_count: int
    danger_count: int
    results: List[VerificationResult]


class PaperRecord(BaseModel):
    filename: str                         # 文件名 e.g. "2023_v2_final.pdf"
    filepath: str                         # 完整绝对路径
    title: str                            # 从正文截取抽取的实际标题
    authors: List[str] = Field(default_factory=list) # 作者列表
    year: Optional[int] = None            # 发表年份
    abstract: str = ""                    # 自动提取到的 Abstract / 摘要
    fulltext: str = ""                    # 提取到的原文全文本
