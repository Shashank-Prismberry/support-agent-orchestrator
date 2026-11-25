from dataclasses import fields

import pytest

from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.ports.analysis import (
    MAX_CONTEXT_CHARACTERS,
    MAX_CONTEXT_MESSAGE_CHARACTERS,
    MAX_CONTEXT_MESSAGES,
    MAX_CURRENT_REQUEST_CHARACTERS,
    MAX_ROUTING_ROLE_CHARACTERS,
    RequestAnalysisInput,
    RequestAnalyzer,
)
from support_agent_orchestrator.ports.routing import RoutingMessage


def test_request_analysis_input_accepts_current_request_and_bounded_context() -> None:
    request = RequestAnalysisInput(
        current_request="Can you follow up on this?",
        conversation_context=(
            RoutingMessage(role="human", content="My package is late."),
            RoutingMessage(role="ai", content="I can look into that."),
        ),
    )

    assert request.current_request == "Can you follow up on this?"
    assert len(request.conversation_context) == 2


def test_request_analysis_input_exposes_only_conversation_fields() -> None:
    assert {field.name for field in fields(RequestAnalysisInput)} == {
        "current_request",
        "conversation_context",
    }


def test_request_analysis_input_is_immutable() -> None:
    request = RequestAnalysisInput(current_request="Find the status")

    with pytest.raises(AttributeError):
        request.current_request = "Override"  # type: ignore[misc]


@pytest.mark.parametrize("current_request", ["", "   "])
def test_request_analysis_input_rejects_empty_current_request(current_request) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        RequestAnalysisInput(current_request=current_request)


def test_request_analysis_input_rejects_oversized_current_request() -> None:
    with pytest.raises(ValueError, match="size limit"):
        RequestAnalysisInput(current_request="x" * (MAX_CURRENT_REQUEST_CHARACTERS + 1))


def test_request_analysis_input_accepts_role_at_maximum_length() -> None:
    request = RequestAnalysisInput(
        current_request="Current",
        conversation_context=(
            RoutingMessage(role="r" * MAX_ROUTING_ROLE_CHARACTERS, content="Context"),
        ),
    )

    assert len(request.conversation_context[0].role) == MAX_ROUTING_ROLE_CHARACTERS


def test_request_analysis_input_rejects_role_over_maximum_length() -> None:
    with pytest.raises(ValueError, match="role exceeds the size limit"):
        RequestAnalysisInput(
            current_request="Current",
            conversation_context=(
                RoutingMessage(role="r" * (MAX_ROUTING_ROLE_CHARACTERS + 1), content="Context"),
            ),
        )


def test_request_analysis_input_rejects_too_many_context_messages() -> None:
    messages = tuple(
        RoutingMessage(role="human", content="context") for _ in range(MAX_CONTEXT_MESSAGES + 1)
    )

    with pytest.raises(ValueError, match="message limit"):
        RequestAnalysisInput(current_request="Current", conversation_context=messages)


def test_request_analysis_input_rejects_oversized_context_message() -> None:
    with pytest.raises(ValueError, match="message exceeds"):
        RequestAnalysisInput(
            current_request="Current",
            conversation_context=(
                RoutingMessage(
                    role="human",
                    content="x" * (MAX_CONTEXT_MESSAGE_CHARACTERS + 1),
                ),
            ),
        )


def test_request_analysis_input_rejects_oversized_total_context() -> None:
    content = "x" * (MAX_CONTEXT_CHARACTERS // 5)
    messages = tuple(RoutingMessage(role="human", content=content) for _ in range(6))

    with pytest.raises(ValueError, match="total size limit"):
        RequestAnalysisInput(
            current_request="Current",
            conversation_context=messages,
        )


@pytest.mark.asyncio
async def test_request_analyzer_protocol_accepts_provider_independent_fake() -> None:
    expected = RequestAnalysis(
        mode="context",
        intent="general_support",
        requested_outcomes=("Explain the delivery status",),
    )

    class FakeAnalyzer:
        async def analyze(self, request: RequestAnalysisInput) -> RequestAnalysis:
            assert request.current_request == "Where is my order?"
            return expected

    analyzer: RequestAnalyzer = FakeAnalyzer()
    request = RequestAnalysisInput(current_request="Where is my order?")

    assert isinstance(analyzer, RequestAnalyzer)
    assert await analyzer.analyze(request) is expected
