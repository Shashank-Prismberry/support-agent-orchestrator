import pytest
from pydantic import ValidationError

from support_agent_orchestrator.domain.input import create_internal_graph_input
from support_agent_orchestrator.domain.planning import (
    PlannedTask,
    PlanProposal,
    ValidatedPlan,
    WorkflowResult,
)
from support_agent_orchestrator.domain.state import create_initial_state


def make_task(*, task_id: str = "task-1", depends_on: tuple[str, ...] = ()) -> PlannedTask:
    return PlannedTask(
        task_id=task_id,
        specialist="triage",
        objective="Review the support request",
        expected_outputs=("A concise review",),
        depends_on=depends_on,
    )


def make_state(trusted_context, user_message):
    return create_initial_state(user_context=trusted_context, messages=[user_message])


def test_planned_task_accepts_valid_values_and_defaults_dependencies() -> None:
    task = make_task()

    assert task.task_id == "task-1"
    assert task.specialist == "triage"
    assert task.depends_on == ()


@pytest.mark.parametrize("task_id", [" task-1", "task-1 ", " task-1 "])
def test_planned_task_rejects_task_ids_with_surrounding_whitespace(task_id: str) -> None:
    with pytest.raises(ValidationError):
        make_task(task_id=task_id)


def test_planned_task_accepts_explicit_dependencies() -> None:
    task = make_task(depends_on=("task-0",))

    assert task.depends_on == ("task-0",)


def test_planned_task_rejects_more_dependencies_than_plan_task_bound() -> None:
    dependencies = tuple(f"task-{index}" for index in range(11))

    with pytest.raises(ValidationError):
        make_task(depends_on=dependencies)


@pytest.mark.parametrize(
    "data",
    [
        {
            "task_id": "task-1",
            "specialist": "triage",
            "objective": "Review request",
            "expected_outputs": ("Review",),
            "capability_names": ("invented",),
        },
        {
            "disposition": "unsupported",
            "tasks": (),
            "organization_id": "untrusted",
        },
        {
            "tasks": (make_task(),),
            "user_id": "untrusted",
        },
    ],
)
def test_contracts_reject_unexpected_fields(data) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        if "task_id" in data:
            PlannedTask(**data)
        elif "disposition" in data:
            PlanProposal(**data)
        else:
            WorkflowResult(state={}, disposition="unsupported", **data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", ""),
        ("task_id", "   "),
        ("objective", ""),
        ("objective", "   "),
        ("expected_outputs", ("",)),
        ("expected_outputs", ("   ",)),
        ("clarification_question", ""),
        ("clarification_question", "   "),
    ],
)
def test_contracts_reject_empty_bounded_strings(field, value) -> None:
    task_fields = {
        "task_id": "task-1",
        "specialist": "triage",
        "objective": "Review request",
        "expected_outputs": ("Review",),
    }
    if field in task_fields:
        task_fields[field] = value
        with pytest.raises(ValidationError):
            PlannedTask(**task_fields)
    elif field == "expected_outputs":
        task_fields[field] = value
        with pytest.raises(ValidationError):
            PlannedTask(**task_fields)
    else:
        with pytest.raises(ValidationError):
            PlanProposal(
                disposition="clarification_required",
                clarification_question=value,
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "t" * 65),
        ("objective", "o" * 501),
        ("expected_outputs", ("e" * 301,)),
    ],
)
def test_planned_task_rejects_oversized_strings(field, value) -> None:
    data = {
        "task_id": "task-1",
        "specialist": "triage",
        "objective": "Review request",
        "expected_outputs": ("Review",),
    }
    data[field] = value

    with pytest.raises(ValidationError):
        PlannedTask(**data)


def test_planned_task_rejects_more_than_ten_expected_outputs() -> None:
    with pytest.raises(ValidationError):
        PlannedTask(
            task_id="task-1",
            specialist="triage",
            objective="Review request",
            expected_outputs=tuple(f"Output {index}" for index in range(11)),
        )


def test_clarification_question_rejects_oversized_text() -> None:
    with pytest.raises(ValidationError):
        PlanProposal(
            disposition="clarification_required",
            clarification_question="?" * 501,
        )


def test_plan_proposal_rejects_more_than_ten_tasks() -> None:
    tasks = tuple(make_task(task_id=f"task-{index}") for index in range(11))

    with pytest.raises(ValidationError):
        PlanProposal(disposition="ready", tasks=tasks)


def test_validated_plan_rejects_empty_or_oversized_task_collections() -> None:
    with pytest.raises(ValidationError):
        ValidatedPlan(tasks=())

    tasks = tuple(make_task(task_id=f"task-{index}") for index in range(11))
    with pytest.raises(ValidationError):
        ValidatedPlan(tasks=tasks)


def test_plan_contracts_reject_duplicate_task_ids() -> None:
    duplicate_tasks = (make_task(task_id="duplicate"), make_task(task_id="duplicate"))

    with pytest.raises(ValidationError, match="unique within a plan"):
        PlanProposal(disposition="ready", tasks=duplicate_tasks)

    with pytest.raises(ValidationError, match="unique within a plan"):
        ValidatedPlan(tasks=duplicate_tasks)


@pytest.mark.parametrize("specialist", ["planner", "supervisor", "unknown", ""])
def test_planned_task_rejects_invalid_specialist(specialist) -> None:
    with pytest.raises(ValidationError):
        PlannedTask(
            task_id="task-1",
            specialist=specialist,
            objective="Review request",
            expected_outputs=("Review",),
        )


def test_plan_proposal_accepts_each_disposition() -> None:
    ready = PlanProposal(disposition="ready", tasks=(make_task(),))
    clarification = PlanProposal(
        disposition="clarification_required",
        clarification_question="Which ticket should I review?",
    )
    unsupported = PlanProposal(disposition="unsupported")

    assert ready.disposition == "ready"
    assert clarification.disposition == "clarification_required"
    assert unsupported.disposition == "unsupported"


@pytest.mark.parametrize(
    "proposal",
    [
        {"disposition": "ready"},
        {"disposition": "ready", "clarification_question": "Question?", "tasks": (make_task(),)},
        {"disposition": "clarification_required"},
        {
            "disposition": "clarification_required",
            "clarification_question": "Question?",
            "tasks": (make_task(),),
        },
        {"disposition": "unsupported", "tasks": (make_task(),)},
        {"disposition": "unsupported", "clarification_question": "Question?"},
        {"disposition": "unknown"},
    ],
)
def test_plan_proposal_rejects_invalid_disposition_combinations(proposal) -> None:
    with pytest.raises(ValidationError):
        PlanProposal(**proposal)


@pytest.mark.parametrize(
    "result",
    [
        {"disposition": "ready"},
        {
            "disposition": "ready",
            "plan": ValidatedPlan(tasks=(make_task(),)),
            "clarification_question": "Question?",
        },
        {"disposition": "clarification_required"},
        {
            "disposition": "clarification_required",
            "clarification_question": "Question?",
            "plan": ValidatedPlan(tasks=(make_task(),)),
        },
        {"disposition": "unsupported", "plan": ValidatedPlan(tasks=(make_task(),))},
        {"disposition": "unsupported", "clarification_question": "Question?"},
        {"disposition": "invalid"},
    ],
)
def test_workflow_result_rejects_invalid_disposition_combinations(
    trusted_context, user_message, result
) -> None:
    with pytest.raises(ValidationError):
        WorkflowResult(state=make_state(trusted_context, user_message), **result)


def test_workflow_result_accepts_each_consistent_disposition(trusted_context, user_message) -> None:
    state = make_state(trusted_context, user_message)
    plan = ValidatedPlan(tasks=(make_task(),))

    ready = WorkflowResult(state=state, disposition="ready", plan=plan)
    clarification = WorkflowResult(
        state=state,
        disposition="clarification_required",
        clarification_question="Which ticket should I review?",
    )
    unsupported = WorkflowResult(state=state, disposition="unsupported")

    assert ready.plan == plan
    assert clarification.clarification_question == "Which ticket should I review?"
    assert unsupported.plan is None


@pytest.mark.parametrize("disposition", ["conversational", "quick", "context"])
def test_workflow_result_accepts_conversational_and_support_without_plan(
    trusted_context, user_message, disposition
) -> None:
    result = WorkflowResult(
        state=make_state(trusted_context, user_message),
        disposition=disposition,
    )

    assert result.disposition == disposition
    assert result.plan is None
    assert result.clarification_question is None


def test_workflow_result_rejects_agent_state_with_unexpected_fields(
    trusted_context, user_message
) -> None:
    state = make_state(trusted_context, user_message)
    state["plan"] = "not part of AgentState"  # type: ignore[typeddict-unknown-key]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        WorkflowResult(state=state, disposition="unsupported")


@pytest.mark.parametrize(
    "model,instance,field,value",
    [
        (PlannedTask, make_task(), "objective", "Changed"),
        (
            PlanProposal,
            PlanProposal(disposition="unsupported"),
            "disposition",
            "ready",
        ),
        (ValidatedPlan, ValidatedPlan(tasks=(make_task(),)), "tasks", ()),
    ],
)
def test_planning_models_are_immutable(model, instance, field, value) -> None:
    with pytest.raises(ValidationError):
        setattr(instance, field, value)


def test_workflow_result_is_immutable(trusted_context, user_message) -> None:
    result = WorkflowResult(
        state=make_state(trusted_context, user_message), disposition="unsupported"
    )

    with pytest.raises(ValidationError):
        result.disposition = "ready"


def test_workflow_result_uses_exact_four_field_agent_state(trusted_context, user_message) -> None:
    graph_state = create_internal_graph_input(
        user_context=trusted_context,
        messages=[user_message],
    ).to_state()
    result = WorkflowResult(state=graph_state, disposition="unsupported")

    assert set(result.state) == {
        "messages",
        "user_context",
        "active_agent",
        "approval_status",
    }
