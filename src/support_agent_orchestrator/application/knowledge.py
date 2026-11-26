"""Shared application boundary for scoped company-knowledge retrieval."""

from pydantic import ValidationError

from support_agent_orchestrator.domain.context import TrustedUserContext
from support_agent_orchestrator.domain.input import (
    InvalidInternalGraphInputError,
    validate_internal_user_context,
)
from support_agent_orchestrator.domain.knowledge import (
    KnowledgeAccessScope,
    KnowledgeRetrievalResult,
)
from support_agent_orchestrator.ports.knowledge import KnowledgeRetriever


class InvalidKnowledgeScopeError(ValueError):
    """Raised when trusted context cannot provide a contract-valid RAG scope."""


class KnowledgeRetrievalService:
    """Map validated runtime context to RAG scope and delegate to one retriever port."""

    def __init__(self, retriever: KnowledgeRetriever) -> None:
        self._retriever = retriever

    async def retrieve(
        self,
        query: str,
        *,
        user_context: TrustedUserContext,
        limit: int | None = 5,
    ) -> KnowledgeRetrievalResult:
        """Retrieve with tenant and tiers from runtime context, separate from query text."""

        try:
            context = validate_internal_user_context(user_context)
        except InvalidInternalGraphInputError:
            raise InvalidKnowledgeScopeError(
                "A validated trusted user context is required for knowledge retrieval"
            ) from None

        try:
            scope = KnowledgeAccessScope(
                org_id=context.org_id,
                authorized_kb_tiers=context.authorized_kb_tiers,
            )
        except ValidationError:
            raise InvalidKnowledgeScopeError("Trusted knowledge scope is invalid") from None

        return await self._retriever.retrieve(query, limit=limit, scope=scope)
