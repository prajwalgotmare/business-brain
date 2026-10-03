"""Deterministic PDF extraction and clause-aware chunking."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCUMENT_MANIFEST = PROJECT_ROOT / "data" / "documents" / "document_manifest.json"

_SECTION_PATTERN = re.compile(r"(?m)(?=^\d+\.\d+\s+[^\n]+$)")
_CLAUSE_PATTERN = re.compile(r"\bclause_[a-z0-9_]+\b")
_WHITESPACE_PATTERN = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class DocumentChunk:
    point_id: str
    chunk_id: str
    tenant_id: str
    document_id: str
    title: str
    document_kind: str
    document_date: str | None
    page_number: int
    chunk_index: int
    section_heading: str | None
    clause_id: str | None
    content: str
    content_sha256: str
    document_sha256: str
    sensitivity: str
    source_type: str

    def payload(self) -> dict[str, str | int | None]:
        return asdict(self) | {"schema_version": "1.0"}


def load_ingest_documents() -> list[dict[str, object]]:
    """Load only documents explicitly authorized by the manifest for ingestion."""
    manifest = json.loads(DOCUMENT_MANIFEST.read_text(encoding="utf-8"))
    documents = [item for item in manifest["documents"] if item["ingest"] is True]
    if any(not item["tenant_id"] for item in documents):
        raise ValueError("Every ingested document must have a tenant_id")
    return documents


def _normalize_text(text: str) -> str:
    lines = [_WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _split_long_text(text: str, max_chars: int = 850, overlap_chars: int = 120) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        target = min(start + max_chars, len(text))
        end = target
        if target < len(text):
            candidates = [text.rfind("\n", start, target), text.rfind(". ", start, target)]
            boundary = max(candidates)
            if boundary > start + max_chars // 2:
                end = boundary + (1 if text[boundary] == "\n" else 2)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def _page_sections(text: str) -> list[tuple[str | None, str]]:
    normalized = _normalize_text(text)
    pieces = [piece.strip() for piece in _SECTION_PATTERN.split(normalized) if piece.strip()]
    sections: list[tuple[str | None, str]] = []
    for piece in pieces:
        first_line = piece.splitlines()[0]
        heading = first_line if re.match(r"^\d+\.\d+\s+", first_line) else None
        for chunk in _split_long_text(piece):
            sections.append((heading, chunk))
    return sections


def extract_document_chunks(document: dict[str, object]) -> list[DocumentChunk]:
    path = PROJECT_ROOT / str(document["relative_path"])
    content = path.read_bytes()
    document_hash = hashlib.sha256(content).hexdigest()
    if document_hash != document["sha256"]:
        raise ValueError(f"Document hash mismatch: {document['document_id']}")

    allowed_clauses = set(document["clause_ids"])
    chunks: list[DocumentChunk] = []
    for page_number, page in enumerate(PdfReader(path).pages, start=1):
        for section_heading, text in _page_sections(page.extract_text() or ""):
            chunk_index = len(chunks)
            chunk_id = f"chk_{document['document_id']}_{page_number:03d}_{chunk_index:03d}"
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            clauses = sorted(set(_CLAUSE_PATTERN.findall(text)) & allowed_clauses)
            if len(clauses) > 1:
                raise ValueError(f"Chunk contains multiple clauses: {chunk_id}")
            point_id = str(uuid5(NAMESPACE_URL, f"business-brain:{chunk_id}:{content_hash}"))
            chunks.append(
                DocumentChunk(
                    point_id=point_id,
                    chunk_id=chunk_id,
                    tenant_id=str(document["tenant_id"]),
                    document_id=str(document["document_id"]),
                    title=str(document["title"]),
                    document_kind=str(document["document_kind"]),
                    document_date=(
                        str(document["document_date"]) if document["document_date"] else None
                    ),
                    page_number=page_number,
                    chunk_index=chunk_index,
                    section_heading=section_heading,
                    clause_id=clauses[0] if clauses else None,
                    content=text,
                    content_sha256=content_hash,
                    document_sha256=document_hash,
                    sensitivity=str(document["sensitivity"]),
                    source_type=str(document["source_type"]),
                )
            )
    if not chunks:
        raise ValueError(f"No extractable content: {document['document_id']}")
    missing_clauses = allowed_clauses - {chunk.clause_id for chunk in chunks}
    if missing_clauses:
        raise ValueError(f"Missing clauses in {document['document_id']}: {sorted(missing_clauses)}")
    return chunks


def extract_uploaded_pdf_chunks(
    *,
    content: bytes,
    tenant_id: str,
    document_id: str,
    title: str,
    sensitivity: str,
) -> list[DocumentChunk]:
    """Extract already-validated user PDF bytes without writing them to disk."""
    document_hash = hashlib.sha256(content).hexdigest()
    chunks: list[DocumentChunk] = []
    for page_number, page in enumerate(PdfReader(BytesIO(content), strict=True).pages, start=1):
        for section_heading, text in _page_sections(page.extract_text() or ""):
            chunk_index = len(chunks)
            chunk_id = f"chk_{document_id}_{page_number:03d}_{chunk_index:03d}"
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            clauses = sorted(set(_CLAUSE_PATTERN.findall(text)))
            point_id = str(uuid5(NAMESPACE_URL, f"business-brain:{chunk_id}:{content_hash}"))
            chunks.append(
                DocumentChunk(
                    point_id=point_id,
                    chunk_id=chunk_id,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    title=title,
                    document_kind="user_document",
                    document_date=None,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    section_heading=section_heading,
                    clause_id=clauses[0] if len(clauses) == 1 else None,
                    content=text,
                    content_sha256=content_hash,
                    document_sha256=document_hash,
                    sensitivity=sensitivity,
                    source_type="user_upload",
                )
            )
    if not chunks:
        raise ValueError("Uploaded PDF has no extractable content")
    return chunks


def extract_all_chunks() -> list[DocumentChunk]:
    chunks = [
        chunk
        for document in load_ingest_documents()
        for chunk in extract_document_chunks(document)
    ]
    if len({chunk.point_id for chunk in chunks}) != len(chunks):
        raise ValueError("Qdrant point IDs are not unique")
    return chunks
