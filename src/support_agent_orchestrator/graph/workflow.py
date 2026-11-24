"""Central LangGraph construction for AGT-1.1."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from support_agent_orchestrator.application.supervisor import (
    InvalidTrustedContextError,
    Supervisor,
)
from support_agent_orchestrator.domain.input import (
    InternalGraphInput,
    InvalidInternalGraphInputError,
)
from support_agent_orchestrator.domain.state import ActiveAgent, AgentState
from support_agent_orchestrator.ports.routing import SupervisorRouter


class OrchestrationGraph:
    """Internal graph facade that accepts only canonical graph input."""

    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    def invoke(self, graph_input: InternalGraphInput) -> dict[str, object]:
        if not isinstance(graph_input, InternalGraphInput):
            raise TypeError("Graph invocation requires internal graph input")
        try:
            state = graph_input.to_state()
        except InvalidInternalGraphInputError:
            raise InvalidTrustedContextError(
                "A validated trusted user context is required"
            ) from None
        return self._graph.invoke(state)


def build_orchestration_graph(router: SupervisorRouter) -> OrchestrationGraph:
    """Build the Supervisor graph with terminal specialist routing boundaries."""

    graph = StateGraph(AgentState)
    graph.add_node("supervisor", Supervisor(router))
    graph.add_node("triage", _routing_boundary)
    graph.add_node("knowledge", _routing_boundary)
    graph.add_node("billing", _routing_boundary)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _active_agent_route,
        {"triage": "triage", "knowledge": "knowledge", "billing": "billing"},
    )
    graph.add_edge("triage", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("billing", END)
    return OrchestrationGraph(graph.compile())


def _active_agent_route(state: AgentState) -> ActiveAgent:
    active_agent = state["active_agent"]
    if active_agent is None:
        raise ValueError("Supervisor did not select an active agent")
    return active_agent


def _routing_boundary(_: AgentState) -> dict[str, object]:
    """Temporary terminal boundary; specialist behavior starts in AGT-1.2."""

    return {}
