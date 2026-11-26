from dataclasses import fields

import pytest

from support_agent_orchestrator.domain.planning import PlanProposal
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.ports.analysis import (
    MAX_CONTEXT_CHARACTERS,
    MAX_CONTEXT_MESSAGE_CHARACTERS,
    MAX_CONTEXT_MESSAGES,
    MAX_CURRENT_REQUEST_CHARACTERS,
    RequestAnalysisInput,
)
from support_agent_orchestrator.ports.planning import Planner, PlanningInput
from support_agent_orchestrator.ports.routing import RoutingMessage


def make_analysis() -> RequestAnalysis:
    return RequestAnalysis(
        mode="deep",
        intent="mixed",
        requested_outcomes=("Review the request",),
    )


def make_request_input(
    current_request: str = "Review my support request",
    conversation_context: tuple[RoutingMessage, ...] = (),
) -> RequestAnalysisInput:
    return RequestAnalysisInput(
        current_request=current_request,
        conversation_context=conversation_context,
    )


def test_planning_input_accepts_valid_analysis_and_bounded_request() -> None:
    request = make_request_input(
        conversation_context=(
            RoutingMessage(role="human", content="Earlier question"),
            RoutingMessage(role="ai", content="Earlier answer"),
        )
    )
    planning_input = PlanningInput(analysis=make_analysis(), request=request)

    assert planning_input.analysis.mode == "deep"
    assert planning_input.request.current_request == "Review my support request"
    assert planning_input.request.conversation_context == request.conversation_context


@pytest.mark.parametrize("current_request", ["", "   "])
def test_planning_input_reuses_empty_request_validation(current_request) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        make_request_input(current_request=current_request)


def test_planning_input_reuses_current_request_size_limit() -> None:
    with pytest.raises(ValueError, match="size limit"):
        make_request_input(current_request="x" * (MAX_CURRENT_REQUEST_CHARACTERS + 1))


def test_planning_input_reuses_context_message_count_and_size_limits() -> None:
    too_many_messages = tuple(
        RoutingMessage(role="human", content="context") for _ in range(MAX_CONTEXT_MESSAGES + 1)
    )
    with pytest.raises(ValueError, match="message limit"):
        make_request_input(conversation_context=too_many_messages)

    oversized_message = (
        RoutingMessage(role="human", content="x" * (MAX_CONTEXT_MESSAGE_CHARACTERS + 1)),
    )
    with pytest.raises(ValueError, match="message exceeds"):
        make_request_input(conversation_context=oversized_message)

    total_context_over_limit = tuple(
        RoutingMessage(role="human", content="x" * 2_000) for _ in range(6)
    )
    assert (
        sum(len(message.content) for message in total_context_over_limit) > MAX_CONTEXT_CHARACTERS
    )
    with pytest.raises(ValueError, match="total size limit"):
        make_request_input(conversation_context=total_context_over_limit)


def test_planning_input_requires_existing_routing_message_values() -> None:
    with pytest.raises(TypeError, match="routing messages"):
        make_request_input(conversation_context=(object(),))  # type: ignore[arg-type]


def test_planning_input_rejects_unexpected_fields() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        PlanningInput(
            analysis=make_analysis(),
            request=make_request_input(),
            user_id="untrusted",  # type: ignore[call-arg]
        )


def test_planning_input_rejects_invalid_contract_types() -> None:
    with pytest.raises(TypeError, match="validated request analysis"):
        PlanningInput(analysis=object(), request=make_request_input())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="sanitized, bounded request input"):
        PlanningInput(analysis=make_analysis(), request=object())  # type: ignore[arg-type]


def test_planning_input_is_immutable_and_contains_no_trusted_fields() -> None:
    planning_input = PlanningInput(analysis=make_analysis(), request=make_request_input())

    with pytest.raises(AttributeError):
        planning_input.analysis = make_analysis()

    assert {field.name for field in fields(PlanningInput)} == {"analysis", "request"}
    assert {field.name for field in fields(RequestAnalysisInput)} == {
        "current_request",
        "conversation_context",
    }


@pytest.mark.asyncio
async def test_planner_protocol_accepts_async_fake_returning_plan_proposal() -> None:
    expected = PlanProposal(disposition="unsupported")

    class FakePlanner:
        async def plan(self, request: PlanningInput) -> PlanProposal:
            assert request.analysis.mode == "deep"
            assert request.request.current_request == "Review my support request"
            return expected

    planner: Planner = FakePlanner()
    planning_input = PlanningInput(analysis=make_analysis(), request=make_request_input())

    assert isinstance(planner, Planner)
    assert await planner.plan(planning_input) is expected
