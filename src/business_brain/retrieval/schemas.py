"""Typed contracts for governed hybrid retrieval and citations."""

from pydantic import BaseModel, ConfigDict, Field


class DocumentCitation(BaseModel):
    document_id: str
    title: str
    page_number: int = Field(ge=1)
    clause_id: str | None = None
    section_heading: str | None = None
    chunk_id: str

    @property
    def label(self) -> str:
        parts = [self.title, f"p. {self.page_number}"]
        if self.clause_id:
            parts.append(self.clause_id)
        return ", ".join(parts)


class RetrievalHit(BaseModel):
    chunk_id: str
    content: str
    sensitivity: str
    fusion_score: float = Field(ge=0)
    rerank_score: float = Field(ge=0)
    citation: DocumentCitation


class HybridSearchResult(BaseModel):
    query: str
    tenant_id: str
    role: str
    candidate_count: int = Field(ge=0)
    hits: list[RetrievalHit]


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=3, max_length=1_000)
    limit: int | None = Field(default=None, ge=1, le=20)
