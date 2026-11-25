import pytest

from support_agent_orchestrator.application.specialists import build_specialist_nodes
from support_agent_orchestrator.application.supervisor import InvalidTrustedContextError
from support_agent_orchestrator.domain.input import create_internal_graph_input
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.graph.workflow import (
    AsyncOnlyGraphError,
    build_orchestration_graph,
)
from support_agent_orchestrator.ports.agents import GenerationRequest
from support_agent_orchestrator.ports.analysis import RequestAnalysisInput
from support_agent_orchestrator.ports.routing import RoutingInput


class Router:
    def __init__(self, destination):
        self.destination = destination
        self.calls = 0

    def route(self, request: RoutingInput):
        self.calls += 1
        return self.destination


class Analyzer:
    def __init__(self, mode: str = "quick") -> None:
        self.mode = mode
        self.calls = 0

    async def analyze(self, request: RequestAnalysisInput) -> RequestAnalysis:
        self.calls += 1
        return RequestAnalysis(
            mode=self.mode, intent="general_support", requested_outcomes=("Answer",)
        )


class Generator:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    async def generate(self, request: GenerationRequest):
        self.calls += 1
        return self.text


def specialist_set():
    return build_specialist_nodes(
        triage=Generator("t"), knowledge=Generator("k"), billing=Generator("b")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,destination,text",
    [
        ("quick", "triage", "t"),
        ("quick", "knowledge", "k"),
        ("quick", "billing", "b"),
        ("context", "triage", "t"),
        ("context", "knowledge", "k"),
        ("context", "billing", "b"),
    ],
)
async def test_graph_routes_one_specialist_to_end(
    trusted_context, user_message, mode, destination, text
) -> None:
    analyzer = Analyzer(mode)
    router = Router(destination)
    specialists = specialist_set()
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        specialists=specialists,
    )
    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )

    assert result["active_agent"] == destination
    assert result["messages"][-1].content == text
    assert len(result["messages"]) == 2
    assert analyzer.calls == 1
    assert router.calls == 1
    assert sum(node._generator.calls for node in specialists.values()) == 1
    assert set(result) == {"messages", "user_context", "active_agent", "approval_status"}


@pytest.mark.asyncio
async def test_deep_request_ends_without_supervisor_or_specialist(
    trusted_context, user_message
) -> None:
    router = Router("triage")
    analyzer = Analyzer("deep")
    specialists = specialist_set()
    graph = build_orchestration_graph(router, analyzer=analyzer, specialists=specialists)

    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )

    assert result["messages"][-1].content == (
        "This request requires multiple steps, and multi-step orchestration is not available yet."
    )
    assert result["active_agent"] is None
    assert analyzer.calls == 1
    assert router.calls == 0
    assert sum(node._generator.calls for node in specialists.values()) == 0
    assert set(result) == {"messages", "user_context", "active_agent", "approval_status"}


@pytest.mark.asyncio
async def test_async_graph_rejects_plain_input(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(
        Router("triage"),
        analyzer=Analyzer(),
        specialists=specialist_set(),
    )

    with pytest.raises(TypeError, match="internal graph input"):
        await graph.ainvoke({})  # type: ignore[arg-type]


def test_specialist_graph_sync_error_is_application_level(trusted_context, user_message) -> None:
    router = Router("triage")
    analyzer = Analyzer()
    graph = build_orchestration_graph(router, analyzer=analyzer, specialists=specialist_set())

    with pytest.raises(AsyncOnlyGraphError, match="use ainvoke"):
        graph.invoke(
            create_internal_graph_input(user_context=trusted_context, messages=[user_message])
        )
    assert router.calls == 0
    assert analyzer.calls == 0


@pytest.mark.asyncio
async def test_graph_maps_invalid_context_to_safe_error(trusted_context, user_message) -> None:
    analyzer = Analyzer()
    graph = build_orchestration_graph(
        Router("triage"),
        analyzer=analyzer,
        specialists=specialist_set(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    object.__setattr__(graph_input, "user_context", None)

    with pytest.raises(InvalidTrustedContextError, match="validated trusted"):
        await graph.ainvoke(graph_input)
    assert analyzer.calls == 0


@pytest.mark.asyncio
async def test_none_specialists_preserves_placeholder_graph(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(Router("triage"), analyzer=Analyzer())
    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )
    assert result["active_agent"] == "triage"


@pytest.mark.parametrize("mapping", [{}, {"triage": object(), "knowledge": object()}])
def test_graph_rejects_empty_or_incomplete_specialist_mapping(mapping) -> None:
    with pytest.raises(ValueError, match="Specialist mapping"):
        build_orchestration_graph(Router("triage"), analyzer=Analyzer(), specialists=mapping)


def test_graph_rejects_non_callable_specialist_mapping_value() -> None:
    with pytest.raises(TypeError, match="callable"):
        build_orchestration_graph(
            Router("triage"),
            analyzer=Analyzer(),
            specialists={"triage": object(), "knowledge": object(), "billing": object()},
        )
