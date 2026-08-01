"""Typed knowledge contracts for the JPS One RAG foundation.

These models are intentionally lightweight. They define the stable shape that
future ingestion, vector search, and MCP tools should build on.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


KnowledgeType = Literal[
    "product_docs",
    "price_rules",
    "email_templates",
    "market_rules",
    "sales_cases",
    "company_docs",
]


class KnowledgeChunk(BaseModel):
    """One retrievable source chunk with citation metadata."""

    doc_id: str
    chunk_id: str
    knowledge_type: KnowledgeType
    title: str = ""
    text: str
    source_file: str = ""
    source_page: str = ""
    language: str = "auto"
    product_category: str = ""
    product_model: str = ""
    country: str = ""
    customer_type: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KnowledgeSearchRequest(BaseModel):
    query: str
    knowledge_types: list[KnowledgeType] = Field(default_factory=list)
    product_category: str = ""
    product_model: str = ""
    country: str = ""
    customer_type: str = ""
    limit: int = Field(default=8, ge=1, le=50)


class KnowledgeSearchResponse(BaseModel):
    query: str
    chunks: list[KnowledgeChunk] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)

