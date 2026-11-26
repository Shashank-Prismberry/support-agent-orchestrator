import asyncio
from dataclasses import fields

import pytest
from pydantic import ValidationError

from support_agent_orchestrator.application.planning import (
    UNSUPPORTED_PLANNING_MESSAGE,
    InvalidPlanProposalError,
    PlannerProviderError,
    PlanningResult,
    PlanningService,
    PlanValidationError,
)
from support_agent_orchestrator.domain.planning import PlannedTask, PlanProposal, ValidatedPlan
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.ports.analysis import RequestAnalysisInput
from support_agent_orchestrator.ports.planning import Planner, PlanningInput


def make_planning_input() -> PlanningInput:
    return PlanningInput(
        analysis=RequestAnalysis(
            mode="deep",
            intent="mixed",
            requested_outcomes=("Resolve the support request",),
        ),
        request=RequestAnalysisInput(current_request="Please investigate this issue"),
    )


def make_ready_proposal() -> PlanProposal:
    return PlanProposal(
        disposition="ready",
        tasks=(
            PlannedTask(
                task_id="task-1",
                specialist="triage",
                objective="Review the reported issue",
                expected_outputs=("A concise issue summary",),
            ),
        ),
    )


class FakePlanner:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0
        self.received: PlanningInput | None = None

    async def plan(self, request: PlanningInput) -> PlanProposal:
        self.calls += 1
        self.received = request
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_service_returns_validated_ready_plan_and_calls_planner_once() -> None:
    planner = FakePlanner(make_ready_proposal())
    service = PlanningService(planner)

    result = await service.plan(make_planning_input())

    assert isinstance(planner, Planner)
    assert planner.calls == 1
    assert isinstance(result.plan, ValidatedPlan)
    assert result.disposition == "ready"
    assert result.plan.tasks[0].task_id == "task-1"


@pytest.mark.asyncio
async def test_service_returns_clarification_question_without_plan() -> None:
    planner = FakePlanner(
        PlanProposal(
            disposition="clarification_required",
            clarification_question="Which ticket should I review?",
        )
    )

    result = await PlanningService(planner).plan(make_planning_input())

    assert result.disposition == "clarification_required"
    assert result.clarification_question == "Which ticket should I review?"
    assert result.plan is None


@pytest.mark.asyncio
async def test_unsupported_uses_fixed_application_message() -> None:
    planner = FakePlanner(PlanProposal(disposition="unsupported"))

    result = await PlanningService(planner).plan(make_planning_input())

    assert result.disposition == "unsupported"
    assert result.plan is None
    assert result.clarification_question is None
    assert result.message == UNSUPPORTED_PLANNING_MESSAGE


@pytest.mark.asyncio
async def test_planner_unsupported_text_is_rejected_and_not_exposed() -> None:
    private_text = "provider-private unsupported detail"
    planner = FakePlanner({"disposition": "unsupported", "message": private_text})

    with pytest.raises(InvalidPlanProposalError) as error:
        await PlanningService(planner).plan(make_planning_input())

    assert private_text not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.asyncio
async def test_malformed_proposal_is_reported_safely() -> None:
    planner = FakePlanner(
        {
            "disposition": "clarification_required",
            "clarification_question": "Which ticket?",
            "org_id": "sensitive-org-value",
        }
    )

    with pytest.raises(InvalidPlanProposalError) as error:
        await PlanningService(planner).plan(make_planning_input())

    assert "sensitive-org-value" not in str(error.value)
    assert planner.calls == 1


@pytest.mark.asyncio
async def test_invalid_ready_dag_uses_existing_deterministic_validation_error() -> None:
    invalid_dag = PlanProposal(
        disposition="ready",
        tasks=(
            PlannedTask(
                task_id="task-1",
                specialist="triage",
                objective="Review the reported issue",
                expected_outputs=("A concise issue summary",),
                depends_on=("missing-task",),
            ),
        ),
    )

    with pytest.raises(PlanValidationError, match="unknown dependency"):
        await PlanningService(FakePlanner(invalid_dag)).plan(make_planning_input())


@pytest.mark.asyncio
async def test_provider_failure_uses_safe_error_without_details() -> None:
    planner = FakePlanner(RuntimeError("provider credential=private-value"))

    with pytest.raises(PlannerProviderError) as error:
        await PlanningService(planner).plan(make_planning_input())

    assert str(error.value) == "The planning provider failed"
    assert "private-value" not in str(error.value)
    assert error.value.__cause__ is None
    assert planner.calls == 1


@pytest.mark.asyncio
async def test_planner_cancellation_propagates() -> None:
    planner = FakePlanner(asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await PlanningService(planner).plan(make_planning_input())

    assert planner.calls == 1


@pytest.mark.asyncio
async def test_service_has_no_identity_or_execution_context_surface() -> None:
    planning_input = make_planning_input()
    planner = FakePlanner(make_ready_proposal())

    await PlanningService(planner).plan(planning_input)

    assert planner.received is planning_input
    assert {field.name for field in fields(PlanningInput)} == {"analysis", "request"}
    assert {field.name for field in fields(RequestAnalysisInput)} == {
        "current_request",
        "conversation_context",
    }
    assert {field for field in PlanningResult.model_fields} == {
        "disposition",
        "plan",
        "clarification_question",
        "message",
    }


def test_planning_result_is_frozen_and_rejects_inconsistent_outcomes() -> None:
    plan = ValidatedPlan(tasks=make_ready_proposal().tasks)
    result = PlanningResult(disposition="ready", plan=plan)

    with pytest.raises(ValidationError):
        result.disposition = "unsupported"
    with pytest.raises(ValidationError):
        PlanningResult(disposition="ready")
    with pytest.raises(ValidationError):
        PlanningResult(disposition="unsupported", message="Planner generated text")
