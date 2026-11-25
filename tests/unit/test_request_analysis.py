import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from support_agent_orchestrator.application.request_analysis import (
    InvalidRequestAnalysisOutputError,
    RequestAnalysisService,
    RequestAnalyzerProviderError,
)
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.ports.analysis import (
    MAX_CONTEXT_CHARACTERS,
    MAX_CONTEXT_MESSAGE_CHARACTERS,
    MAX_CONTEXT_MESSAGES,
    RequestAnalysisInput,
)


@pytest.mark.parametrize("mode", ["quick", "context", "deep"])
@pytest.mark.parametrize("intent", ["general_support", "knowledge", "billing", "mixed"])
def test_request_analysis_accepts_supported_values(mode, intent) -> None:
    analysis = RequestAnalysis(
        mode=mode,
        intent=intent,
        requested_outcomes=("Resolve the customer's question",),
    )

    assert analysis.mode == mode
    assert analysis.intent == intent
    assert analysis.requested_outcomes == ("Resolve the customer's question",)


@pytest.mark.parametrize(
    "field,value",
    [("mode", "fast"), ("intent", "account"), ("mode", 1), ("intent", None)],
)
def test_request_analysis_rejects_invalid_enum_values(field, value) -> None:
    data = {
        "mode": "quick",
        "intent": "knowledge",
        "requested_outcomes": ("Find the relevant answer",),
    }
    data[field] = value

    with pytest.raises(ValidationError):
        RequestAnalysis(**data)


@pytest.mark.parametrize("missing_field", ["mode", "intent", "requested_outcomes"])
def test_request_analysis_requires_all_fields(missing_field) -> None:
    data = {
        "mode": "quick",
        "intent": "general_support",
        "requested_outcomes": ("Answer the question",),
    }
    del data[missing_field]

    with pytest.raises(ValidationError, match="Field required"):
        RequestAnalysis(**data)


def test_request_analysis_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RequestAnalysis(
            mode="quick",
            intent="general_support",
            requested_outcomes=("Answer the question",),
            user_id="untrusted",
        )


@pytest.mark.parametrize("outcomes", [(), ("",), ("   ",)])
def test_request_analysis_rejects_empty_outcomes(outcomes) -> None:
    with pytest.raises(ValidationError):
        RequestAnalysis(mode="quick", intent="general_support", requested_outcomes=outcomes)


def test_request_analysis_rejects_more_than_ten_outcomes() -> None:
    outcomes = tuple(f"Outcome {index}" for index in range(11))

    with pytest.raises(ValidationError):
        RequestAnalysis(mode="deep", intent="mixed", requested_outcomes=outcomes)


def test_request_analysis_rejects_outcome_longer_than_500_characters() -> None:
    with pytest.raises(ValidationError):
        RequestAnalysis(
            mode="quick",
            intent="general_support",
            requested_outcomes=("x" * 501,),
        )


def test_request_analysis_is_immutable() -> None:
    analysis = RequestAnalysis(
        mode="quick",
        intent="general_support",
        requested_outcomes=("Answer the question",),
    )

    with pytest.raises(ValidationError):
        analysis.mode = "deep"


class FakeAnalyzer:
    def __init__(self, result: object) -> None:
        self.result = result
        self.received: RequestAnalysisInput | None = None

    async def analyze(self, request: RequestAnalysisInput) -> RequestAnalysis:
        self.received = request
        if isinstance(self.result, Exception):
            raise self.result
        return self.result  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_service_sanitizes_current_request_and_context_before_invocation() -> None:
    analyzer = FakeAnalyzer(
        RequestAnalysis(
            mode="context",
            intent="general_support",
            requested_outcomes=("Check the request",),
        )
    )
    jwt = "eyJabcdefgh.ijklmnop.qrstuvwxyzABCDEFGH"
    service = RequestAnalysisService(analyzer)

    result = await service.analyze(
        f"Bearer access-secret {jwt}",
        [HumanMessage(content="Order question"), AIMessage(content="Bearer prior-secret")],
    )

    assert result.mode == "context"
    assert analyzer.received is not None
    assert "access-secret" not in analyzer.received.current_request
    assert jwt not in analyzer.received.current_request
    assert "REDACTED_CREDENTIAL" in analyzer.received.current_request
    assert "prior-secret" not in repr(analyzer.received)
    assert "REDACTED_CREDENTIAL" in analyzer.received.conversation_context[-1].content


@pytest.mark.asyncio
async def test_service_bounds_context_to_recent_messages_and_input_limits() -> None:
    analyzer = FakeAnalyzer(
        RequestAnalysis(
            mode="context",
            intent="general_support",
            requested_outcomes=("Review recent context",),
        )
    )
    context = [HumanMessage(content=f"turn-{index}") for index in range(MAX_CONTEXT_MESSAGES + 3)]
    context.extend(
        [
            AIMessage(content="a" * (MAX_CONTEXT_MESSAGE_CHARACTERS + 500)),
            HumanMessage(content="b" * (MAX_CONTEXT_CHARACTERS + 500)),
        ]
    )

    await RequestAnalysisService(analyzer).analyze("Current request", context)

    assert analyzer.received is not None
    bounded = analyzer.received.conversation_context
    assert len(bounded) <= MAX_CONTEXT_MESSAGES
    assert sum(len(message.content) for message in bounded) <= MAX_CONTEXT_CHARACTERS
    assert all(len(message.content) <= MAX_CONTEXT_MESSAGE_CHARACTERS for message in bounded)
    assert bounded[-1].content.endswith("b" * MAX_CONTEXT_MESSAGE_CHARACTERS)


@pytest.mark.asyncio
async def test_service_filters_context_roles_and_order_without_current_request() -> None:
    analyzer = FakeAnalyzer(
        RequestAnalysis(
            mode="context",
            intent="general_support",
            requested_outcomes=("Use prior conversation",),
        )
    )
    history = [
        SystemMessage(content="system-only context"),
        HumanMessage(content="first human turn"),
        AIMessage(content="first assistant turn"),
        ToolMessage(content="tool-only result", tool_call_id="tool-call"),
        HumanMessage(content="latest human request"),
    ]

    await RequestAnalysisService(analyzer).analyze("latest human request", history[:-1])

    assert analyzer.received is not None
    assert analyzer.received.current_request == "latest human request"
    assert [turn.role for turn in analyzer.received.conversation_context] == ["human", "ai"]
    assert [turn.content for turn in analyzer.received.conversation_context] == [
        "first human turn",
        "first assistant turn",
    ]
    assert all(
        turn.content != analyzer.received.current_request
        for turn in analyzer.received.conversation_context
    )


@pytest.mark.asyncio
async def test_service_context_count_bound_applies_to_recent_human_and_ai_turns() -> None:
    analyzer = FakeAnalyzer(
        RequestAnalysis(
            mode="context",
            intent="general_support",
            requested_outcomes=("Use recent turns",),
        )
    )
    context = [SystemMessage(content="excluded system message")]
    for index in range(MAX_CONTEXT_MESSAGES + 2):
        context.extend(
            [
                HumanMessage(content=f"human-{index}"),
                ToolMessage(content=f"excluded-tool-{index}", tool_call_id=f"tool-{index}"),
                AIMessage(content=f"assistant-{index}"),
            ]
        )

    await RequestAnalysisService(analyzer).analyze("current", context)

    assert analyzer.received is not None
    bounded = analyzer.received.conversation_context
    assert len(bounded) == MAX_CONTEXT_MESSAGES
    assert all(turn.role in {"human", "ai"} for turn in bounded)
    assert [turn.content for turn in bounded] == [
        f"{role}-{index}"
        for index in range(2, MAX_CONTEXT_MESSAGES + 2)
        for role in ("human", "assistant")
    ][-MAX_CONTEXT_MESSAGES:]


@pytest.mark.asyncio
async def test_service_returns_validated_analysis() -> None:
    expected = RequestAnalysis(
        mode="deep",
        intent="mixed",
        requested_outcomes=("Resolve issue", "Explain next steps"),
    )
    analyzer = FakeAnalyzer(expected)

    result = await RequestAnalysisService(analyzer).analyze("Help me resolve this and explain it")

    assert result == expected
    assert result is not expected


@pytest.mark.asyncio
async def test_service_rejects_malformed_analyzer_output_without_details() -> None:
    analyzer = FakeAnalyzer(
        {
            "mode": "quick",
            "intent": "general_support",
            "requested_outcomes": ("Answer",),
            "org_id": "private-org",
        }
    )

    with pytest.raises(InvalidRequestAnalysisOutputError) as error:
        await RequestAnalysisService(analyzer).analyze("What is the status?")

    assert "private-org" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.asyncio
async def test_service_revalidates_constructed_analysis() -> None:
    malformed = RequestAnalysis.model_construct(
        mode="unknown",
        intent="general_support",
        requested_outcomes=("Answer",),
    )

    with pytest.raises(InvalidRequestAnalysisOutputError):
        await RequestAnalysisService(FakeAnalyzer(malformed)).analyze("Question")


@pytest.mark.asyncio
async def test_service_maps_provider_failure_without_exposing_details() -> None:
    analyzer = FakeAnalyzer(RuntimeError("credential=provider-secret"))

    with pytest.raises(RequestAnalyzerProviderError) as error:
        await RequestAnalysisService(analyzer).analyze("Question")

    assert str(error.value) == "The request analyzer failed"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "provider-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_service_rejects_oversized_current_request_safely() -> None:
    analyzer = FakeAnalyzer(
        RequestAnalysis(
            mode="quick",
            intent="general_support",
            requested_outcomes=("Answer",),
        )
    )

    with pytest.raises(ValueError, match="Current request exceeds"):
        await RequestAnalysisService(analyzer).analyze("x" * 4_001)

    assert analyzer.received is None
