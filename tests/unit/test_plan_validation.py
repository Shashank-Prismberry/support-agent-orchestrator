import pytest

from support_agent_orchestrator.application.planning import (
    MAX_DEPENDENCY_DEPTH,
    PlanValidationError,
    validate_plan_proposal,
)
from support_agent_orchestrator.domain.planning import PlannedTask, PlanProposal, ValidatedPlan


def task(
    task_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    **overrides: object,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "specialist": "triage",
        "objective": f"Review request for {task_id}",
        "expected_outputs": (f"Summary for {task_id}",),
        "depends_on": depends_on,
        **overrides,
    }


def proposal(*tasks: dict[str, object], **overrides: object) -> dict[str, object]:
    return {"disposition": "ready", "tasks": tasks, **overrides}


def test_validates_single_task_without_dependencies() -> None:
    result = validate_plan_proposal(proposal(task("task-1")))

    assert isinstance(result, ValidatedPlan)
    assert [item.task_id for item in result.tasks] == ["task-1"]
    assert result.tasks[0].depends_on == ()


@pytest.mark.parametrize("task_id", [" task-1", "task-1 ", " task-1 "])
def test_rejects_task_ids_with_surrounding_whitespace(task_id: str) -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task(task_id)))


def test_validates_multiple_independent_tasks_and_preserves_order() -> None:
    result = validate_plan_proposal(proposal(task("third"), task("first"), task("second")))

    assert [item.task_id for item in result.tasks] == ["third", "first", "second"]


def test_validates_dependency_chain_at_maximum_depth() -> None:
    task_list = tuple(
        task(f"task-{index}", depends_on=(f"task-{index - 1}",) if index else ())
        for index in range(MAX_DEPENDENCY_DEPTH)
    )

    result = validate_plan_proposal(proposal(*task_list))

    assert len(result.tasks) == MAX_DEPENDENCY_DEPTH


def test_validates_branching_dependency_graph() -> None:
    result = validate_plan_proposal(
        proposal(
            task("root"),
            task("left", depends_on=("root",)),
            task("right", depends_on=("root",)),
            task("join", depends_on=("left", "right")),
        )
    )

    assert [item.task_id for item in result.tasks] == ["root", "left", "right", "join"]


def test_rejects_ready_proposal_without_tasks() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal({"disposition": "ready", "tasks": ()})


def test_rejects_more_than_ten_tasks() -> None:
    tasks = tuple(task(f"task-{index}") for index in range(11))

    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(*tasks))


def test_rejects_duplicate_task_ids() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("same"), task("same")))


def test_rejects_task_id_outside_bounded_syntax() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("not a valid id")))


def test_rejects_unsupported_specialist() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("task-1", specialist="planner")))


def test_rejects_missing_dependency() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("task-1", depends_on=("missing",))))


def test_rejects_self_dependency() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("task-1", depends_on=("task-1",))))


def test_rejects_duplicate_dependency_reference() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("root"), task("child", depends_on=("root", "root"))))


def test_rejects_direct_cycle() -> None:
    with pytest.raises(PlanValidationError, match="cycle"):
        validate_plan_proposal(
            proposal(task("first", depends_on=("second",)), task("second", depends_on=("first",)))
        )


def test_rejects_indirect_cycle() -> None:
    with pytest.raises(PlanValidationError, match="cycle"):
        validate_plan_proposal(
            proposal(
                task("first", depends_on=("third",)),
                task("second", depends_on=("first",)),
                task("third", depends_on=("second",)),
            )
        )


def test_rejects_dependency_chain_over_maximum_depth() -> None:
    tasks = tuple(
        task(f"task-{index}", depends_on=(f"task-{index - 1}",) if index else ())
        for index in range(MAX_DEPENDENCY_DEPTH + 1)
    )

    with pytest.raises(PlanValidationError, match="maximum dependency depth"):
        validate_plan_proposal(proposal(*tasks))


def test_rejects_oversized_objective() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("task-1", objective="x" * 501)))


def test_rejects_oversized_expected_output() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("task-1", expected_outputs=("x" * 301,))))


def test_rejects_too_many_expected_outputs() -> None:
    outputs = tuple(f"output-{index}" for index in range(11))

    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("task-1", expected_outputs=outputs)))


def test_rejects_unexpected_fields() -> None:
    with pytest.raises(PlanValidationError):
        validate_plan_proposal(proposal(task("task-1", capability_names=("invented",))))


def test_revalidates_already_constructed_proposal() -> None:
    valid_proposal = PlanProposal(
        disposition="ready",
        tasks=(
            PlannedTask(
                task_id="valid-1",
                specialist="knowledge",
                objective="Find the relevant policy",
                expected_outputs=("Matching policy",),
            ),
        ),
    )

    result = validate_plan_proposal(valid_proposal)

    assert result.tasks[0].specialist == "knowledge"


def test_revalidates_constructed_model_that_skipped_field_validation() -> None:
    malformed_task = PlannedTask.model_construct(
        task_id="bad id",
        specialist="unknown",
        objective="",
        expected_outputs=(),
        depends_on=(),
    )
    malformed_proposal = PlanProposal.model_construct(
        disposition="ready",
        tasks=(malformed_task,),
        clarification_question=None,
    )

    with pytest.raises(PlanValidationError):
        validate_plan_proposal(malformed_proposal)


def test_rejects_unexpected_field_added_to_constructed_model() -> None:
    constructed = PlanProposal.model_construct(
        disposition="ready",
        tasks=(
            PlannedTask(
                task_id="task-1",
                specialist="triage",
                objective="Review the request",
                expected_outputs=("Summary",),
            ),
        ),
        clarification_question=None,
    )
    object.__setattr__(constructed, "organization_id", "untrusted")

    with pytest.raises(PlanValidationError):
        validate_plan_proposal(constructed)


@pytest.mark.parametrize("disposition", ["clarification_required", "unsupported"])
def test_non_ready_dispositions_do_not_produce_validated_plans(disposition) -> None:
    non_ready = (
        {"disposition": disposition, "clarification_question": "Which request?"}
        if disposition == "clarification_required"
        else {"disposition": disposition}
    )

    with pytest.raises(PlanValidationError, match="Only ready"):
        validate_plan_proposal(non_ready)
