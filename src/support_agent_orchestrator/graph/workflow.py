"""Central LangGraph construction for AGT-1.1."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from support_agent_orchestrator.application.specialists import SpecialistNode
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

    async def ainvoke(self, graph_input: InternalGraphInput) -> dict[str, object]:
        """Invoke workflows containing async specialist nodes."""

        if not isinstance(graph_input, InternalGraphInput):
            raise TypeError("Graph invocation requires internal graph input")
        try:
            state = graph_input.to_state()
        except InvalidInternalGraphInputError:
            raise InvalidTrustedContextError(
                "A validated trusted user context is required"
            ) from None
        return await self._graph.ainvoke(state)


def build_orchestration_graph(
    router: SupervisorRouter,
    *,
    specialists: dict[str, SpecialistNode] | None = None,
) -> OrchestrationGraph:
    """Build the Supervisor graph with terminal specialist routing boundaries."""

    graph = StateGraph(AgentState)
    supervisor = Supervisor(router)
    graph.add_node("supervisor", _async_supervisor(supervisor) if specialists else supervisor)
    if specialists is None:
        specialist_nodes: dict[str, object] = {
            "triage": _routing_boundary,
            "knowledge": _routing_boundary,
            "billing": _routing_boundary,
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
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _active_agent_route_async if specialists else _active_agent_route,
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


def _node_callable(node: object):
    if isinstance(node, SpecialistNode):

        async def invoke(state: AgentState) -> dict[str, object]:
            return await node(state)

        return invoke
    return node


def _async_supervisor(supervisor: Supervisor):
    async def invoke(state: AgentState) -> dict[str, object]:
        return supervisor(state)

    return invoke


async def _active_agent_route_async(state: AgentState) -> ActiveAgent:
    return _active_agent_route(state)
