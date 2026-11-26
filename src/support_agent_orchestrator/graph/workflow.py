"""Central LangGraph construction for AGT-1.1."""

from collections.abc import Callable, Mapping
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from support_agent_orchestrator.application.conversational import generate_conversational_response
from support_agent_orchestrator.application.planning import PlanningResult, PlanningService
from support_agent_orchestrator.application.request_analysis import (
    AnalyzedRequest,
    RequestAnalysisService,
)
from support_agent_orchestrator.application.specialists import SpecialistNode
from support_agent_orchestrator.application.supervisor import (
    InvalidTrustedContextError,
    Supervisor,
)
from support_agent_orchestrator.domain.input import (
    InternalGraphInput,
    InvalidInternalGraphInputError,
)
from support_agent_orchestrator.domain.planning import WorkflowResult
from support_agent_orchestrator.domain.state import ActiveAgent, AgentState
from support_agent_orchestrator.ports.agents import AgentResponseGenerator
from support_agent_orchestrator.ports.analysis import RequestAnalyzer
from support_agent_orchestrator.ports.planning import PlanningInput
from support_agent_orchestrator.ports.routing import SupervisorRouter


class _WorkflowState(AgentState):
    """Private graph state for prepared analysis and one planning outcome."""

    analyzed_request: AnalyzedRequest | None
    planning_result: PlanningResult | None


class AsyncOnlyGraphError(RuntimeError):
    """Raised when synchronous invocation is attempted on an async-only graph."""


class OrchestrationGraph:
    """Async graph facade that hides private workflow state from callers."""

    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    def invoke(self, graph_input: InternalGraphInput) -> WorkflowResult:
        raise AsyncOnlyGraphError(
            "This graph contains an asynchronous request analyzer; use ainvoke()."
        )

    async def ainvoke(self, graph_input: InternalGraphInput) -> WorkflowResult:
        """Invoke the workflow and wrap its public state and planning disposition."""

        state = self._prepare_state(graph_input)
        result = await self._graph.ainvoke(state)
        public_state = {key: result[key] for key in AgentState.__annotations__}
        planning_result = result.get("planning_result")
        if isinstance(planning_result, PlanningResult):
            return WorkflowResult(
                state=public_state,
                disposition=planning_result.disposition,
                plan=planning_result.plan,
                clarification_question=planning_result.clarification_question,
            )

        analyzed_request = result.get("analyzed_request")
        if not isinstance(analyzed_request, AnalyzedRequest):
            raise ValueError("Workflow did not produce a validated request analysis")
        if analyzed_request.analysis.mode == "deep":
            raise ValueError("Deep request did not produce a planning result")
        return WorkflowResult(state=public_state, disposition=analyzed_request.analysis.mode)

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
        return {**state, "analyzed_request": None, "planning_result": None}


def build_orchestration_graph(
    router: SupervisorRouter,
    *,
    analyzer: RequestAnalyzer,
    planning_service: PlanningService,
    conversational_generator: AgentResponseGenerator,
    specialists: Mapping[str, SpecialistNode],
) -> OrchestrationGraph:
    """Build the Analyzer-first graph with all response paths explicitly injected."""

    graph = StateGraph(_WorkflowState)
    analysis_service = RequestAnalysisService(analyzer)
    supervisor = Supervisor(router)
    graph.add_node("request_analyzer", _request_analyzer_node(analysis_service))
    graph.add_node("planner", _planning_node(planning_service))
    graph.add_node(
        "conversational_response",
        _conversational_response_node(conversational_generator),
    )
    graph.add_node("supervisor", _async_supervisor(supervisor))
    required = {"triage", "knowledge", "billing"}
    if set(specialists) != required:
        raise ValueError("Specialist mapping must contain exactly triage, knowledge, and billing")
    if any(not isinstance(node, SpecialistNode) for node in specialists.values()):
        raise TypeError("Specialist mapping values must be SpecialistNode instances")
    if any(node.agent_name != name for name, node in specialists.items()):
        raise ValueError("Each SpecialistNode must match its specialist mapping key")
    graph.add_node("triage", _node_callable(specialists["triage"]))
    graph.add_node("knowledge", _node_callable(specialists["knowledge"]))
    graph.add_node("billing", _node_callable(specialists["billing"]))
    graph.add_edge(START, "request_analyzer")
    graph.add_conditional_edges(
        "request_analyzer",
        _request_analysis_route,
        {
            "conversational": "conversational_response",
            "quick": "supervisor",
            "context": "supervisor",
            "deep": "planner",
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
    graph.add_edge("planner", END)
    graph.add_edge("conversational_response", END)
    return OrchestrationGraph(graph.compile())


def _request_analyzer_node(
    service: RequestAnalysisService,
) -> Callable[[_WorkflowState], object]:
    async def analyze(state: _WorkflowState) -> dict[str, AnalyzedRequest]:
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
        analyzed_request = await service.analyze_with_input(current_request.content, context)
        return {"analyzed_request": analyzed_request}

    return analyze


async def _request_analysis_route(
    state: _WorkflowState,
) -> Literal["conversational", "quick", "context", "deep"]:
    analyzed_request = state.get("analyzed_request")
    if not isinstance(analyzed_request, AnalyzedRequest):
        raise ValueError("Request analysis did not produce a validated result")
    return analyzed_request.analysis.mode


def _conversational_response_node(
    generator: AgentResponseGenerator,
) -> Callable[[_WorkflowState], object]:
    async def respond(state: _WorkflowState) -> dict[str, list[AIMessage]]:
        current_request = next(
            (
                message
                for message in reversed(state["messages"])
                if isinstance(message, HumanMessage)
            ),
            None,
        )
        if current_request is None:
            raise ValueError("A current user request is required for a conversational response")
        response = await generate_conversational_response(generator, current_request.content)
        return {"messages": [response]}

    return respond


def _planning_node(service: PlanningService) -> Callable[[_WorkflowState], object]:
    async def plan(state: _WorkflowState) -> dict[str, object]:
        analyzed_request = state.get("analyzed_request")
        if not isinstance(analyzed_request, AnalyzedRequest):
            raise ValueError("A prepared request is required for planning")
        planning_input = PlanningInput(
            analysis=analyzed_request.analysis,
            request=analyzed_request.request,
        )
        planning_result = await service.plan(planning_input)
        updates: dict[str, object] = {"planning_result": planning_result}
        if planning_result.disposition == "unsupported":
            if planning_result.message is None:
                raise ValueError("Unsupported planning result has no safe message")
            updates["messages"] = [AIMessage(content=planning_result.message)]
        return updates

    return plan


def _active_agent_route(state: AgentState) -> ActiveAgent:
    active_agent = state["active_agent"]
    if active_agent is None:
        raise ValueError("Supervisor did not select an active agent")
    return active_agent


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
