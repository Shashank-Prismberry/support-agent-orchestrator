"""Application-owned port for the external RAG knowledge service."""

from typing import Protocol, runtime_checkable

from support_agent_orchestrator.domain.knowledge import (
    KnowledgeAccessScope,
    KnowledgeRetrievalResult,
)


@runtime_checkable
class KnowledgeRetriever(Protocol):
    """Retrieve company knowledge without owning transport or authorization policy."""

    async def retrieve(
        self,
        query: str,
        *,
        limit: int | None = 5,
        scope: KnowledgeAccessScope,
    ) -> KnowledgeRetrievalResult: ...
