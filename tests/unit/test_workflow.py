import pytest

from support_agent_orchestrator.application.planning import PlanningService
from support_agent_orchestrator.application.request_analysis import (
    InvalidRequestAnalysisOutputError,
    RequestAnalyzerProviderError,
)
from support_agent_orchestrator.application.specialists import build_specialist_nodes
from support_agent_orchestrator.application.supervisor import (
    InvalidTrustedContextError,
    SupervisorRoutingError,
)
from support_agent_orchestrator.domain.input import (
    InternalGraphInput,
    create_internal_graph_input,
)
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.graph.workflow import (
    AsyncOnlyGraphError,
    _active_agent_route,
    build_orchestration_graph,
)
from support_agent_orchestrator.ports.agents import GenerationRequest
from support_agent_orchestrator.ports.analysis import RequestAnalysisInput
from support_agent_orchestrator.ports.planning import PlanningInput
from support_agent_orchestrator.ports.routing import RoutingInput


class DeterministicRouter:
    def __init__(self, destination: object) -> None:
        self.destination = destination
        self.calls = 0

    def route(self, routing_input: RoutingInput) -> object:
        self.calls += 1
        return self.destination


class DeterministicAnalyzer:
    def __init__(self, result: object | None = None) -> None:
        self.result = result or RequestAnalysis(
            mode="quick",
            intent="general_support",
            requested_outcomes=("Answer the request",),
        )
        self.calls = 0
        self.received: RequestAnalysisInput | None = None

    async def analyze(self, request: RequestAnalysisInput) -> RequestAnalysis:
        self.calls += 1
        self.received = request
        return self.result  # type: ignore[return-value]


class UnusedPlanner:
    async def plan(self, request: PlanningInput):
        raise AssertionError("Planner must not run for this workflow test")


class UnusedGenerator:
    async def generate(self, request: GenerationRequest) -> object:
        raise AssertionError("A generation path must not run for this workflow test")


def unused_planning_service() -> PlanningService:
    return PlanningService(UnusedPlanner())


def fake_specialists():
    class TerminalGenerator:
        async def generate(self, request: GenerationRequest) -> object:
            return "terminal response"

    generator = TerminalGenerator()
    return build_specialist_nodes(
        triage=generator,
        knowledge=generator,
        billing=generator,
    )


def unused_conversational_generator() -> UnusedGenerator:
    return UnusedGenerator()


@pytest.mark.parametrize("destination", ["triage", "knowledge", "billing"])
@pytest.mark.asyncio
async def test_graph_routes_to_terminal_boundary(
    trusted_context, user_message, destination
) -> None:
    graph = build_orchestration_graph(
        DeterministicRouter(destination),
        analyzer=DeterministicAnalyzer(),
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])

    result = await graph.ainvoke(graph_input)

    assert result.disposition == "quick"
    assert result.plan is None
    assert set(result.state) == {"messages", "user_context", "active_agent", "approval_status"}
    assert result.state["active_agent"] == destination
    assert result.state["approval_status"] == "not_required"
    assert len(result.state["messages"]) == 2
    assert result.state["messages"][0].content == user_message.content
    assert result.state["messages"][0].id != user_message.id
    assert result.state["messages"][-1].content == "terminal response"


@pytest.mark.asyncio
async def test_graph_routes_invalid_provider_output_to_triage(
    trusted_context, user_message
) -> None:
    graph = build_orchestration_graph(
        DeterministicRouter({"route": "billing"}),
        analyzer=DeterministicAnalyzer(),
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])

    assert (await graph.ainvoke(graph_input)).state["active_agent"] == "triage"


@pytest.mark.asyncio
async def test_graph_requires_internal_graph_input(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(
        DeterministicRouter("billing"),
        analyzer=DeterministicAnalyzer(),
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )
    raw_state = {
        "messages": [user_message],
        "user_context": trusted_context,
        "active_agent": None,
        "approval_status": "not_required",
    }

    with pytest.raises(TypeError, match="internal graph input"):
        await graph.ainvoke(raw_state)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_graph_validates_input_before_analyzer_invocation(
    trusted_context, user_message
) -> None:
    analyzer = DeterministicAnalyzer()
    graph = build_orchestration_graph(
        DeterministicRouter("triage"),
        analyzer=analyzer,
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )

    with pytest.raises(TypeError, match="internal graph input"):
        await graph.ainvoke({})  # type: ignore[arg-type]

    assert analyzer.calls == 0


def test_internal_graph_input_cannot_be_directly_constructed(trusted_context, user_message) -> None:
    with pytest.raises(TypeError, match="created by create_internal_graph_input"):
        InternalGraphInput(trusted_context, (user_message,))  # type: ignore[call-arg]


def test_internal_graph_input_rejects_invalid_factory_token(trusted_context, user_message) -> None:
    with pytest.raises(TypeError, match="created by create_internal_graph_input"):
        InternalGraphInput._from_factory(
            object(), user_context=trusted_context, messages=(user_message,)
        )


@pytest.mark.asyncio
async def test_graph_revalidates_context_before_invocation(trusted_context, user_message) -> None:
    analyzer = DeterministicAnalyzer()
    graph = build_orchestration_graph(
        DeterministicRouter("billing"),
        analyzer=analyzer,
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    object.__setattr__(graph_input, "user_context", None)

    with pytest.raises(InvalidTrustedContextError, match="validated trusted"):
        await graph.ainvoke(graph_input)
    assert analyzer.calls == 0


@pytest.mark.asyncio
async def test_graph_passes_latest_human_request_and_only_prior_context(
    trusted_context, user_message
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    analyzer = DeterministicAnalyzer()
    graph = build_orchestration_graph(
        DeterministicRouter("knowledge"),
        analyzer=analyzer,
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )
    graph_input = create_internal_graph_input(
        user_context=trusted_context,
        messages=[
            HumanMessage(content="Earlier user message"),
            AIMessage(content="Earlier assistant response"),
            HumanMessage(content="Current request"),
        ],
    )

    await graph.ainvoke(graph_input)

    assert analyzer.received is not None
    assert analyzer.received.current_request == "Current request"
    assert [item.content for item in analyzer.received.conversation_context] == [
        "Earlier user message",
        "Earlier assistant response",
    ]
    assert "org_id" not in repr(analyzer.received)
    assert "permissions" not in repr(analyzer.received)


@pytest.mark.asyncio
async def test_graph_propagates_analyzer_provider_failure_without_routing(
    trusted_context, user_message
) -> None:
    class FailingAnalyzer:
        async def analyze(self, request: RequestAnalysisInput) -> RequestAnalysis:
            raise RuntimeError("credential=private-provider-detail")

    router = DeterministicRouter("triage")
    graph = build_orchestration_graph(
        router,
        analyzer=FailingAnalyzer(),
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])

    with pytest.raises(RequestAnalyzerProviderError) as error:
        await graph.ainvoke(graph_input)

    assert str(error.value) == "The request analyzer failed"
    assert "private-provider-detail" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert router.calls == 0


@pytest.mark.asyncio
async def test_graph_propagates_malformed_analysis_without_routing(
    trusted_context, user_message
) -> None:
    analyzer = DeterministicAnalyzer(
        {
            "mode": "maybe",
            "intent": "general_support",
            "requested_outcomes": ("Answer",),
        }
    )
    router = DeterministicRouter("triage")
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )

    with pytest.raises(InvalidRequestAnalysisOutputError):
        await graph.ainvoke(
            create_internal_graph_input(user_context=trusted_context, messages=[user_message])
        )

    assert router.calls == 0


@pytest.mark.asyncio
async def test_graph_preserves_safe_router_failure(trusted_context, user_message) -> None:
    class FailingRouter:
        def route(self, routing_input: RoutingInput) -> object:
            raise RuntimeError("secret provider detail")

    graph = build_orchestration_graph(
        FailingRouter(),
        analyzer=DeterministicAnalyzer(),
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=fake_specialists(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])

    with pytest.raises(SupervisorRoutingError, match="routing provider failed") as error:
        await graph.ainvoke(graph_input)

    assert error.value.__cause__ is None
    assert "secret provider detail" not in str(error.value)


def test_specialist_graph_rejects_sync_invoke_before_execution(
    trusted_context, user_message
) -> None:
    router = DeterministicRouter("triage")

    class Generator:
        async def generate(self, request):
            raise AssertionError("generator must not be called")

    graph = build_orchestration_graph(
        router,
        analyzer=DeterministicAnalyzer(),
        planning_service=unused_planning_service(),
        conversational_generator=unused_conversational_generator(),
        specialists=build_specialist_nodes(
            triage=Generator(), knowledge=Generator(), billing=Generator()
        ),
    )

    with pytest.raises(AsyncOnlyGraphError, match="use ainvoke"):
        graph.invoke(
            create_internal_graph_input(user_context=trusted_context, messages=[user_message])
        )

    assert router.destination == "triage"


def test_conditional_route_rejects_missing_active_agent(trusted_context, user_message) -> None:
    state = create_internal_graph_input(
        user_context=trusted_context, messages=[user_message]
    ).to_state()

    with pytest.raises(ValueError, match="did not select"):
        _active_agent_route(state)
