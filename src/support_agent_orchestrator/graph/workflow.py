"""Central LangGraph construction for AGT-1.1."""

from collections.abc import Callable
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from support_agent_orchestrator.application.request_analysis import RequestAnalysisService
from support_agent_orchestrator.application.specialists import SpecialistNode
from support_agent_orchestrator.application.supervisor import (
    InvalidTrustedContextError,
    Supervisor,
)
from support_agent_orchestrator.domain.input import (
    InternalGraphInput,
    InvalidInternalGraphInputError,
)
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.domain.state import ActiveAgent, AgentState
from support_agent_orchestrator.ports.analysis import RequestAnalyzer
from support_agent_orchestrator.ports.routing import SupervisorRouter

_DEEP_UNSUPPORTED_RESPONSE = (
    "This request requires multiple steps, and multi-step orchestration is not available yet."
)


class _WorkflowState(AgentState):
    """Private graph state that carries one run's analysis alongside conversation state."""

    request_analysis: RequestAnalysis | None


class AsyncOnlyGraphError(RuntimeError):
    """Raised when synchronous invocation is attempted on an async-only graph."""


class OrchestrationGraph:
    """Async graph facade that hides private workflow state from callers."""

    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    def invoke(self, graph_input: InternalGraphInput) -> dict[str, object]:
        raise AsyncOnlyGraphError(
            "This graph contains an asynchronous request analyzer; use ainvoke()."
        )

    async def ainvoke(self, graph_input: InternalGraphInput) -> dict[str, object]:
        """Invoke the workflow and return only the public four-field AgentState."""

        state = self._prepare_state(graph_input)
        result = await self._graph.ainvoke(state)
        return {key: result[key] for key in AgentState.__annotations__}

    @staticmethod
    def _prepare_state(graph_input: InternalGraphInput) -> _WorkflowState:
        if not isinstance(graph_input, InternalGraphInput):
            raise TypeError("Graph invocation requires internal graph input")
        try:
            state = graph_input.to_state()
        except InvalidInternalGraphInputError:
            raise InvalidTrustedContextError(
                "A validated trusted user context is required"
            ) from None
        return {**state, "request_analysis": None}


def build_orchestration_graph(
    router: SupervisorRouter,
    *,
    analyzer: RequestAnalyzer,
    specialists: dict[str, SpecialistNode] | None = None,
) -> OrchestrationGraph:
    """Build the Analyzer-first graph with terminal specialist routing boundaries."""

    graph = StateGraph(_WorkflowState)
    analysis_service = RequestAnalysisService(analyzer)
    supervisor = Supervisor(router)
    graph.add_node("request_analyzer", _request_analyzer_node(analysis_service))
    graph.add_node("supervisor", _async_supervisor(supervisor))
    if specialists is None:
        specialist_nodes: dict[str, object] = {
            "triage": _async_routing_boundary,
            "knowledge": _async_routing_boundary,
            "billing": _async_routing_boundary,
        }
    else:
        required = {"triage", "knowledge", "billing"}
        if set(specialists) != required:
            raise ValueError(
                "Specialist mapping must contain exactly triage, knowledge, and billing"
            )
        if any(not callable(node) for node in specialists.values()):
            raise TypeError("Specialist mapping values must be callable nodes")
        specialist_nodes = specialists
    graph.add_node("triage", _node_callable(specialist_nodes["triage"]))
    graph.add_node("knowledge", _node_callable(specialist_nodes["knowledge"]))
    graph.add_node("billing", _node_callable(specialist_nodes["billing"]))
    graph.add_edge(START, "request_analyzer")
    graph.add_conditional_edges(
        "request_analyzer",
        _request_analysis_route,
        {
            "quick": "supervisor",
            "context": "supervisor",
            "deep": "deep_unsupported",
        },
    )
    graph.add_conditional_edges(
        "supervisor",
        _active_agent_route_async,
        {"triage": "triage", "knowledge": "knowledge", "billing": "billing"},
    )
    graph.add_edge("triage", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("billing", END)
    graph.add_node("deep_unsupported", _deep_unsupported)
    graph.add_edge("deep_unsupported", END)
    return OrchestrationGraph(graph.compile())


def _request_analyzer_node(
    service: RequestAnalysisService,
) -> Callable[[_WorkflowState], object]:
    async def analyze(state: _WorkflowState) -> dict[str, RequestAnalysis]:
        current_index = next(
            (
                index
                for index in range(len(state["messages"]) - 1, -1, -1)
                if isinstance(state["messages"][index], HumanMessage)
            ),
            None,
        )
        if current_index is None:
            raise ValueError("A current user request is required for analysis")

        current_request = state["messages"][current_index]
        context = state["messages"][:current_index]
        analysis = await service.analyze(current_request.content, context)
        return {"request_analysis": analysis}

    return analyze


async def _request_analysis_route(
    state: _WorkflowState,
) -> Literal["quick", "context", "deep"]:
    analysis = state.get("request_analysis")
    if not isinstance(analysis, RequestAnalysis):
        raise ValueError("Request analysis did not produce a validated result")
    return analysis.mode


async def _deep_unsupported(_: _WorkflowState) -> dict[str, list[AIMessage]]:
    return {"messages": [AIMessage(content=_DEEP_UNSUPPORTED_RESPONSE)]}


def _active_agent_route(state: AgentState) -> ActiveAgent:
    active_agent = state["active_agent"]
    if active_agent is None:
        raise ValueError("Supervisor did not select an active agent")
    return active_agent


async def _async_routing_boundary(_: AgentState) -> dict[str, object]:
    """Temporary terminal boundary; specialist behavior starts in AGT-1.2."""

    return {}


def _node_callable(node: object) -> object:
    if isinstance(node, SpecialistNode):

        async def invoke(state: AgentState) -> dict[str, object]:
            return await node(state)

        return invoke
    return node


def _async_supervisor(supervisor: Supervisor) -> Callable[..., object]:
    async def invoke(state: AgentState) -> dict[str, object]:
        return supervisor(state)

    return invoke


async def _active_agent_route_async(state: _WorkflowState) -> ActiveAgent:
    return _active_agent_route(state)
