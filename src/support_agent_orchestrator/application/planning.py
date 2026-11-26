"""Deterministic structural validation for untrusted plan proposals."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from support_agent_orchestrator.domain.planning import (
    TASK_ID_PATTERN,
    ClarificationQuestion,
    PlannedTask,
    PlanningDisposition,
    PlanProposal,
    ValidatedPlan,
)
from support_agent_orchestrator.ports.planning import Planner, PlanningInput

MAX_DEPENDENCY_DEPTH = 5
UNSUPPORTED_PLANNING_MESSAGE = "This request is not supported by the available planning workflow."


class PlanValidationError(ValueError):
    """Raised when a proposal does not satisfy structural plan constraints."""


class PlannerProviderError(RuntimeError):
    """Raised when the injected Planner fails, without exposing provider details."""


class InvalidPlanProposalError(RuntimeError):
    """Raised when the Planner returns a malformed proposal."""


class PlanningResult(BaseModel):
    """Immutable application outcome for one planning request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    disposition: PlanningDisposition
    plan: ValidatedPlan | None = None
    clarification_question: ClarificationQuestion | None = None
    message: str | None = None

    @model_validator(mode="after")
    def validate_disposition_fields(self) -> "PlanningResult":
        if self.disposition == "ready":
            if (
                self.plan is None
                or self.clarification_question is not None
                or self.message is not None
            ):
                raise ValueError("A ready planning result requires only a plan")
        elif self.disposition == "clarification_required":
            if (
                self.plan is not None
                or self.clarification_question is None
                or self.message is not None
            ):
                raise ValueError("A clarification result requires only a question")
        elif self.disposition == "unsupported":
            if (
                self.plan is not None
                or self.clarification_question is not None
                or self.message != UNSUPPORTED_PLANNING_MESSAGE
            ):
                raise ValueError("An unsupported result requires the fixed safe message")
        return self


class PlanningService:
    """Invoke a Planner once and validate its proposal before returning an outcome."""

    def __init__(self, planner: Planner) -> None:
        self._planner = planner

    async def plan(self, planning_input: PlanningInput) -> PlanningResult:
        """Return a safe disposition or a structurally validated ready plan."""

        if not isinstance(planning_input, PlanningInput):
            raise TypeError("Planning service requires a validated planning input")

        provider_failed = False
        proposal: object = None
        try:
            proposal = await self._planner.plan(planning_input)
        except Exception:
            provider_failed = True
        if provider_failed:
            raise PlannerProviderError("The planning provider failed") from None

        try:
            validated_proposal = revalidate_plan_proposal(proposal)
        except PlanValidationError:
            raise InvalidPlanProposalError("The Planner returned an invalid proposal") from None

        if validated_proposal.disposition == "ready":
            validated_plan = validate_plan_proposal(validated_proposal)
            return PlanningResult(disposition="ready", plan=validated_plan)
        if validated_proposal.disposition == "clarification_required":
            return PlanningResult(
                disposition="clarification_required",
                clarification_question=validated_proposal.clarification_question,
            )
        return PlanningResult(
            disposition="unsupported",
            message=UNSUPPORTED_PLANNING_MESSAGE,
        )


def revalidate_plan_proposal(proposal: object) -> PlanProposal:
    """Strictly rebuild an untrusted proposal, including constructed model instances."""

    try:
        payload = _proposal_payload(proposal)
        return PlanProposal.model_validate(payload, strict=True)
    except (ValidationError, TypeError, ValueError):
        raise PlanValidationError("The plan proposal is structurally invalid") from None


def validate_plan_proposal(proposal: object) -> ValidatedPlan:
    """Revalidate a ready proposal and verify IDs and its dependency DAG.

    This validates structure only. It does not establish that task objectives
    are achievable or authorize capabilities.
    """

    validated_proposal = revalidate_plan_proposal(proposal)

    if validated_proposal.disposition != "ready":
        raise PlanValidationError("Only ready proposals can produce a validated plan")

    tasks = validated_proposal.tasks
    task_ids = {task.task_id for task in tasks}
    for task in tasks:
        if TASK_ID_PATTERN.fullmatch(task.task_id) is None:
            raise PlanValidationError("A task ID does not match the required syntax")
        if len(set(task.depends_on)) != len(task.depends_on):
            raise PlanValidationError("A task contains duplicate dependencies")
        if task.task_id in task.depends_on:
            raise PlanValidationError("A task cannot depend on itself")
        if any(dependency not in task_ids for dependency in task.depends_on):
            raise PlanValidationError("A task references an unknown dependency")

    depth_by_id: dict[str, int] = {}
    visiting: set[str] = set()
    task_by_id = {task.task_id: task for task in tasks}

    def dependency_depth(task_id: str) -> int:
        if task_id in visiting:
            raise PlanValidationError("The plan dependency graph contains a cycle")
        if task_id in depth_by_id:
            return depth_by_id[task_id]

        visiting.add(task_id)
        task = task_by_id[task_id]
        depth = 1 + max(
            (dependency_depth(dependency) for dependency in task.depends_on),
            default=0,
        )
        visiting.remove(task_id)
        if depth > MAX_DEPENDENCY_DEPTH:
            raise PlanValidationError("The plan exceeds the maximum dependency depth")
        depth_by_id[task_id] = depth
        return depth

    for task in tasks:
        dependency_depth(task.task_id)

    try:
        return ValidatedPlan(tasks=tasks)
    except ValidationError:
        raise PlanValidationError("The plan could not be validated") from None


def _proposal_payload(proposal: object) -> object:
    if isinstance(proposal, PlanProposal):
        payload = _model_payload(proposal, PlanProposal)
    elif isinstance(proposal, Mapping):
        payload = dict(proposal)
    else:
        return proposal

    if isinstance(payload, dict) and "tasks" in payload:
        payload["tasks"] = _task_collection_payload(payload["tasks"])
    return payload


def _task_collection_payload(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(_task_payload(task) for task in value)
    if isinstance(value, list):
        return [_task_payload(task) for task in value]
    return value


def _task_payload(task: object) -> object:
    if isinstance(task, PlannedTask):
        return _model_payload(task, PlannedTask)
    if isinstance(task, Mapping):
        return dict(task)
    return task


def _model_payload(model: object, expected_model: type[Any]) -> dict[str, object]:
    """Extract fields without hiding extras or trusting Pydantic instance state."""

    values = vars(model)
    allowed_fields = set(expected_model.model_fields)
    if set(values) - allowed_fields:
        raise ValueError("Unexpected model fields")
    extra = getattr(model, "__pydantic_extra__", None)
    if extra:
        raise ValueError("Unexpected model fields")
    return dict(values)
