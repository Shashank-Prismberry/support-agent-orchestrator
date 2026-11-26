"""Provider-independent contracts for organization-scoped company knowledge."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

KnowledgeAccessLevel = Literal["public", "internal_staff", "admin_only"]
KnowledgeTitle = Annotated[str, StringConstraints(strict=True, max_length=255)]


class _KnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class KnowledgeAccessScope(_KnowledgeModel):
    """Narrow tenant and tier scope copied from authenticated runtime context."""

    org_id: UUID
    authorized_kb_tiers: tuple[KnowledgeAccessLevel, ...]


class KnowledgePassage(_KnowledgeModel):
    """One result row from the shared `retrieve_kb` contract."""

    document_id: UUID
    chunk_index: int
    title: KnowledgeTitle
    content: str
    access_level: KnowledgeAccessLevel
    similarity_score: float


class KnowledgeRetrievalResult(_KnowledgeModel):
    """Immutable retrieval results; passage content remains untrusted evidence."""

    results: tuple[KnowledgePassage, ...]
