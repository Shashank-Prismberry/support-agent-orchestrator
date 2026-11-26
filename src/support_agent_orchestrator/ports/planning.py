"""Provider-independent input and port for Deep request planning."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from support_agent_orchestrator.domain.planning import PlanProposal
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.ports.analysis import RequestAnalysisInput


@dataclass(frozen=True)
class PlanningInput:
    """Validated analysis paired with the existing sanitized, bounded request input."""

    analysis: RequestAnalysis
    request: RequestAnalysisInput

    def __post_init__(self) -> None:
        if not isinstance(self.analysis, RequestAnalysis):
            raise TypeError("Planning input requires validated request analysis")
        if not isinstance(self.request, RequestAnalysisInput):
            raise TypeError("Planning input requires sanitized, bounded request input")


@runtime_checkable
class Planner(Protocol):
    """Propose a structured plan without execution or authorization capabilities."""

    async def plan(self, request: PlanningInput) -> PlanProposal: ...
