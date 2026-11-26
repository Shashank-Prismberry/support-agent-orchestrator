"""Strict domain contracts for proposing and validating Deep request plans."""

import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from support_agent_orchestrator.domain.state import AgentState

PlanningDisposition = Literal["ready", "clarification_required", "unsupported"]
WorkflowDisposition = Literal[
    "conversational", "quick", "context", "ready", "clarification_required", "unsupported"
]
SpecialistName = Literal["triage", "knowledge", "billing"]

TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _validate_task_id(value: str) -> str:
    if TASK_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("Task ID does not match the required syntax")
    return value


TaskId = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=64),
    AfterValidator(_validate_task_id),
]
TaskObjective = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
]
ExpectedOutput = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300),
]
ClarificationQuestion = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
]


class _PlanningModel(BaseModel):
    """Common strict and immutable configuration for planning contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlannedTask(_PlanningModel):
    """A bounded objective assigned to one known specialist."""

    task_id: TaskId
    specialist: SpecialistName
    objective: TaskObjective
    expected_outputs: tuple[ExpectedOutput, ...] = Field(min_length=1, max_length=10)
    depends_on: tuple[TaskId, ...] = Field(default=(), max_length=10)


class PlanProposal(_PlanningModel):
    """Untrusted structured proposal returned by a future Planner implementation."""

    disposition: PlanningDisposition
    tasks: tuple[PlannedTask, ...] = Field(default=(), max_length=10)
    clarification_question: ClarificationQuestion | None = None

    @model_validator(mode="after")
    def validate_disposition_fields(self) -> "PlanProposal":
        _require_unique_task_ids(self.tasks)
        if self.disposition == "ready":
            if not self.tasks:
                raise ValueError("A ready proposal must contain tasks")
            if self.clarification_question is not None:
                raise ValueError("A ready proposal cannot contain a clarification question")
        elif self.disposition == "clarification_required":
            if self.tasks:
                raise ValueError("A clarification proposal cannot contain tasks")
            if self.clarification_question is None:
                raise ValueError("A clarification proposal requires a question")
        elif self.disposition == "unsupported":
            if self.tasks:
                raise ValueError("An unsupported proposal cannot contain tasks")
            if self.clarification_question is not None:
                raise ValueError("An unsupported proposal cannot contain a question")
        return self


class ValidatedPlan(_PlanningModel):
    """A structurally bounded plan accepted by later deterministic validation."""

    tasks: tuple[PlannedTask, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_unique_task_ids(self) -> "ValidatedPlan":
        _require_unique_task_ids(self.tasks)
        return self


class WorkflowResult(_PlanningModel):
    """Public workflow outcome without extending the conversation AgentState."""

    state: AgentState
    disposition: WorkflowDisposition
    plan: ValidatedPlan | None = None
    clarification_question: ClarificationQuestion | None = None

    @model_validator(mode="after")
    def validate_disposition_fields(self) -> "WorkflowResult":
        if self.disposition in {"conversational", "quick", "context"}:
            if self.plan is not None or self.clarification_question is not None:
                raise ValueError("A conversational/support result cannot contain planning data")
        elif self.disposition == "ready":
            if self.plan is None:
                raise ValueError("A ready workflow result requires a plan")
            if self.clarification_question is not None:
                raise ValueError("A ready workflow result cannot contain a question")
        elif self.disposition == "clarification_required":
            if self.plan is not None:
                raise ValueError("A clarification workflow result cannot contain a plan")
            if self.clarification_question is None:
                raise ValueError("A clarification workflow result requires a question")
        elif self.disposition == "unsupported":
            if self.plan is not None:
                raise ValueError("An unsupported workflow result cannot contain a plan")
            if self.clarification_question is not None:
                raise ValueError("An unsupported workflow result cannot contain a question")
        return self


def _require_unique_task_ids(tasks: tuple[PlannedTask, ...]) -> None:
    task_ids = tuple(task.task_id for task in tasks)
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("Task IDs must be unique within a plan")
