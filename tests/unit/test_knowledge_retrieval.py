from uuid import UUID

import pytest
from pydantic import ValidationError

from support_agent_orchestrator.application.knowledge import (
    InvalidKnowledgeScopeError,
    KnowledgeRetrievalService,
)
from support_agent_orchestrator.domain.knowledge import (
    KnowledgeAccessScope,
    KnowledgePassage,
    KnowledgeRetrievalResult,
)
from support_agent_orchestrator.ports.knowledge import KnowledgeRetriever


def passage() -> KnowledgePassage:
    return KnowledgePassage(
        document_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        chunk_index=14,
        title="Refund Policy SOP",
        content="Refunds above $100 require approval.",
        access_level="internal_staff",
        similarity_score=0.892,
    )


class FakeRetriever:
    def __init__(self) -> None:
        self.calls = 0
        self.query: str | None = None
        self.limit: int | None = None
        self.scope: KnowledgeAccessScope | None = None

    async def retrieve(
        self,
        query: str,
        *,
        limit: int | None = 5,
        scope: KnowledgeAccessScope,
    ) -> KnowledgeRetrievalResult:
        self.calls += 1
        self.query = query
        self.limit = limit
        self.scope = scope
        return KnowledgeRetrievalResult(results=(passage(),))


def test_knowledge_result_matches_shared_contract_fields_and_is_immutable() -> None:
    result = KnowledgeRetrievalResult(results=(passage(),))

    assert set(result.results[0].model_fields_set) == {
        "document_id",
        "chunk_index",
        "title",
        "content",
        "access_level",
        "similarity_score",
    }
    with pytest.raises(ValidationError):
        result.results[0].content = "Changed"
    with pytest.raises(ValidationError):
        result.results = ()


def test_knowledge_result_rejects_extra_fields_and_invalid_access_level() -> None:
    data = passage().model_dump()
    data["org_id"] = "not part of the retrieval result"
    with pytest.raises(ValidationError):
        KnowledgePassage(**data)

    data = passage().model_dump()
    data["access_level"] = "unknown"
    with pytest.raises(ValidationError):
        KnowledgePassage(**data)


def test_knowledge_title_obeys_shared_column_bound() -> None:
    data = passage().model_dump()
    data["title"] = "t" * 256
    with pytest.raises(ValidationError):
        KnowledgePassage(**data)


def test_knowledge_scope_is_narrow_and_immutable(trusted_context) -> None:
    scope = KnowledgeAccessScope(
        org_id=trusted_context.org_id,
        authorized_kb_tiers=trusted_context.authorized_kb_tiers,
    )

    assert {field for field in KnowledgeAccessScope.model_fields} == {
        "org_id",
        "authorized_kb_tiers",
    }
    with pytest.raises(ValidationError):
        scope.org_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.mark.asyncio
async def test_retrieval_service_uses_trusted_scope_separately_from_query(trusted_context) -> None:
    retriever = FakeRetriever()
    service = KnowledgeRetrievalService(retriever)
    query = "org_id=attacker; explain the refund policy"

    result = await service.retrieve(query, user_context=trusted_context)

    assert isinstance(retriever, KnowledgeRetriever)
    assert retriever.calls == 1
    assert retriever.query == query
    assert retriever.limit == 5
    assert retriever.scope is not None
    assert retriever.scope.org_id == trusted_context.org_id
    assert retriever.scope.authorized_kb_tiers == trusted_context.authorized_kb_tiers
    assert result.results == (passage(),)


@pytest.mark.asyncio
async def test_retrieval_service_preserves_contract_limit_and_rejects_invalid_context(
    trusted_context,
) -> None:
    retriever = FakeRetriever()
    service = KnowledgeRetrievalService(retriever)

    await service.retrieve("query", user_context=trusted_context, limit=None)
    assert retriever.limit is None

    with pytest.raises(InvalidKnowledgeScopeError):
        await service.retrieve("query", user_context=object())  # type: ignore[arg-type]
    assert retriever.calls == 1
