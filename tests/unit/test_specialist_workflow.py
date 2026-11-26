import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from support_agent_orchestrator.application.planning import (
    UNSUPPORTED_PLANNING_MESSAGE,
    InvalidPlanProposalError,
    PlannerProviderError,
    PlanningService,
    PlanValidationError,
)
from support_agent_orchestrator.application.specialists import (
    MAX_SPECIALIST_CONTEXT_CHARACTERS,
    MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS,
    MAX_SPECIALIST_CONTEXT_MESSAGES,
    SPECIALIST_CONTEXT_TRUNCATION_MARKER,
    build_specialist_nodes,
)
from support_agent_orchestrator.application.supervisor import InvalidTrustedContextError
from support_agent_orchestrator.domain.input import create_internal_graph_input
from support_agent_orchestrator.domain.planning import PlannedTask, PlanProposal, ValidatedPlan
from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.graph.workflow import (
    AsyncOnlyGraphError,
    build_orchestration_graph,
)
from support_agent_orchestrator.ports.agents import GenerationRequest
from support_agent_orchestrator.ports.analysis import RequestAnalysisInput
from support_agent_orchestrator.ports.planning import PlanningInput
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
        self.received: RequestAnalysisInput | None = None

    async def analyze(self, request: RequestAnalysisInput) -> RequestAnalysis:
        self.calls += 1
        self.received = request
        return RequestAnalysis(
            mode=self.mode, intent="general_support", requested_outcomes=("Answer",)
        )


class FakePlanner:
    def __init__(self, result: object | None = None) -> None:
        self.result = result or PlanProposal(disposition="unsupported")
        self.calls = 0
        self.received: PlanningInput | None = None

    async def plan(self, request: PlanningInput) -> PlanProposal:
        self.calls += 1
        self.received = request
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result  # type: ignore[return-value]


class TrackingPlanningService(PlanningService):
    def __init__(self, planner: FakePlanner) -> None:
        super().__init__(planner)
        self.calls = 0

    async def plan(self, planning_input: PlanningInput):
        self.calls += 1
        return await super().plan(planning_input)


class Generator:
    def __init__(self, text):
        self.text = text
        self.calls = 0
        self.received: GenerationRequest | None = None

    async def generate(self, request: GenerationRequest):
        self.calls += 1
        self.received = request
        return self.text


def specialist_set():
    return build_specialist_nodes(
        triage=Generator("t"), knowledge=Generator("k"), billing=Generator("b")
    )


@pytest.mark.asyncio
async def test_specialist_context_filters_roles_preserves_order_and_sanitizes(
    trusted_context,
) -> None:
    generator = Generator("Answer")
    nodes = build_specialist_nodes(
        triage=generator, knowledge=Generator("k"), billing=Generator("b")
    )
    node = nodes["triage"]
    state = create_internal_graph_input(
        user_context=trusted_context,
        messages=[
            SystemMessage(content="System-only"),
            HumanMessage(content="Earlier password=private-value"),
            ToolMessage(content="Tool-only", tool_call_id="tool-1"),
            AIMessage(content="Earlier assistant response"),
            HumanMessage(content="Current request"),
        ],
    ).to_state()
    state["active_agent"] = "triage"

    await node(state)

    assert generator.received is not None
    messages = generator.received.messages
    assert [message.role for message in messages] == ["human", "ai", "human"]
    assert [message.content for message in messages] == [
        "Earlier password=[REDACTED_CREDENTIAL]",
        "Earlier assistant response",
        "Current request",
    ]
    assert sum(message.content == "Current request" for message in messages) == 1
    assert "private-value" not in repr(messages)
    assert "System-only" not in repr(messages)
    assert "Tool-only" not in repr(messages)


@pytest.mark.asyncio
async def test_specialist_context_enforces_count_and_character_bounds(trusted_context) -> None:
    generator = Generator("Answer")
    nodes = build_specialist_nodes(
        triage=generator, knowledge=Generator("k"), billing=Generator("b")
    )
    node = nodes["triage"]
    prior = [
        HumanMessage(content=f"turn-{index}:" + "x" * (2_000 - len(f"turn-{index}:")))
        for index in range(12)
    ]
    current = HumanMessage(content="c" * 4_000)
    state = create_internal_graph_input(
        user_context=trusted_context,
        messages=[*prior, current],
    ).to_state()
    state["active_agent"] = "triage"

    await node(state)

    assert generator.received is not None
    messages = generator.received.messages
    prior_messages = messages[:-1]
    assert len(messages) == 6
    assert len(prior_messages) <= 10
    assert all(len(message.content) <= 2_000 for message in prior_messages)
    assert sum(len(message.content) for message in prior_messages) == 10_000
    assert all(
        message.content.startswith(f"turn-{index}:")
        for message, index in zip(prior_messages, range(7, 12), strict=True)
    )
    assert messages[-1].role == "human"
    assert messages[-1].content == "c" * 4_000
    assert sum(message.content == current.content for message in messages) == 1


@pytest.mark.asyncio
async def test_specialist_context_marks_per_message_truncation_and_preserves_boundary(
    trusted_context,
) -> None:
    generator = Generator("Answer")
    node = build_specialist_nodes(
        triage=generator, knowledge=Generator("k"), billing=Generator("b")
    )["triage"]
    exact_boundary = "e" * MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS
    oversized = "prefix-" + "x" * MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS
    state = create_internal_graph_input(
        user_context=trusted_context,
        messages=[
            HumanMessage(content=exact_boundary),
            AIMessage(content=oversized),
            HumanMessage(content="Current"),
        ],
    ).to_state()
    state["active_agent"] = "triage"

    await node(state)

    assert generator.received is not None
    prior = generator.received.messages[:-1]
    assert len(prior[0].content) == MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS
    assert not prior[0].content.startswith(SPECIALIST_CONTEXT_TRUNCATION_MARKER)
    assert prior[1].content.startswith(SPECIALIST_CONTEXT_TRUNCATION_MARKER)
    assert len(prior[1].content) == MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS
    assert prior[1].content.endswith("x" * 100)
    assert generator.received.messages[-1].content == "Current"


@pytest.mark.asyncio
async def test_specialist_context_marks_total_budget_truncation_and_preserves_all_limits(
    trusted_context,
) -> None:
    generator = Generator("Answer")
    node = build_specialist_nodes(
        triage=generator, knowledge=Generator("k"), billing=Generator("b")
    )["triage"]
    messages = [HumanMessage(content="o" * 1_800)]
    messages.extend(AIMessage(content="r" * 1_500) for _ in range(6))
    messages.append(HumanMessage(content="Current request"))
    state = create_internal_graph_input(user_context=trusted_context, messages=messages).to_state()
    state["active_agent"] = "triage"

    await node(state)

    assert generator.received is not None
    prepared = generator.received.messages
    prior = prepared[:-1]
    assert len(prior) <= MAX_SPECIALIST_CONTEXT_MESSAGES
    assert sum(len(message.content) for message in prior) == MAX_SPECIALIST_CONTEXT_CHARACTERS
    assert all(
        len(message.content) <= MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS for message in prior
    )
    assert prior[0].content.startswith(SPECIALIST_CONTEXT_TRUNCATION_MARKER)
    assert len(prior[0].content) == 1_000
    assert prepared[-1].content == "Current request"
    assert sum(message.content == "Current request" for message in prepared) == 1


@pytest.mark.asyncio
async def test_specialist_context_keeps_latest_message_count_in_chronological_order(
    trusted_context,
) -> None:
    generator = Generator("Answer")
    node = build_specialist_nodes(
        triage=generator, knowledge=Generator("k"), billing=Generator("b")
    )["triage"]
    state = create_internal_graph_input(
        user_context=trusted_context,
        messages=[
            *(
                HumanMessage(content=f"prior-{index}")
                for index in range(MAX_SPECIALIST_CONTEXT_MESSAGES + 2)
            ),
            HumanMessage(content="Current"),
        ],
    ).to_state()
    state["active_agent"] = "triage"

    await node(state)

    assert generator.received is not None
    prepared = generator.received.messages
    assert [message.content for message in prepared] == [
        *(f"prior-{index}" for index in range(2, MAX_SPECIALIST_CONTEXT_MESSAGES + 2)),
        "Current",
    ]
    assert len(prepared) == MAX_SPECIALIST_CONTEXT_MESSAGES + 1


def unused_planning_service() -> PlanningService:
    return PlanningService(FakePlanner())


@pytest.mark.asyncio
async def test_conversational_route_uses_only_current_request_and_skips_support_nodes(
    trusted_context,
) -> None:
    analyzer = Analyzer("conversational")
    router = Router("triage")
    specialists = specialist_set()
    planner = FakePlanner()
    planning_service = TrackingPlanningService(planner)
    conversational_generator = Generator("Hello! I can help with support questions.")
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=planning_service,
        conversational_generator=conversational_generator,
        specialists=specialists,
    )

    result = await graph.ainvoke(
        create_internal_graph_input(
            user_context=trusted_context,
            messages=[
                HumanMessage(content="Earlier private conversation"),
                AIMessage(content="Earlier response"),
                HumanMessage(content="Hi api_key=private-value"),
            ],
        )
    )

    assert result.disposition == "conversational"
    assert result.plan is None
    assert result.clarification_question is None
    assert result.state["active_agent"] is None
    assert result.state["messages"][-1].content == "Hello! I can help with support questions."
    assert analyzer.calls == 1
    assert conversational_generator.calls == 1
    assert conversational_generator.received is not None
    assert len(conversational_generator.received.messages) == 1
    assert conversational_generator.received.messages[0].content.startswith("Hi ")
    assert "Earlier" not in repr(conversational_generator.received)
    assert "private-value" not in repr(conversational_generator.received)
    assert router.calls == planner.calls == planning_service.calls == 0
    assert sum(node._generator.calls for node in specialists.values()) == 0
    assert set(result.state) == {"messages", "user_context", "active_agent", "approval_status"}


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
    planner = FakePlanner()
    planning_service = TrackingPlanningService(planner)
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=planning_service,
        conversational_generator=Generator("conversation"),
        specialists=specialists,
    )
    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )

    assert result.disposition == mode
    assert result.plan is None
    assert result.clarification_question is None
    assert result.state["active_agent"] == destination
    assert result.state["messages"][-1].content == text
    assert len(result.state["messages"]) == 2
    assert analyzer.calls == 1
    assert planning_service.calls == 0
    assert planner.calls == 0
    assert router.calls == 1
    assert sum(node._generator.calls for node in specialists.values()) == 1
    assert set(result.state) == {"messages", "user_context", "active_agent", "approval_status"}


@pytest.mark.asyncio
async def test_deep_request_ends_without_supervisor_or_specialist(
    trusted_context, user_message
) -> None:
    router = Router("triage")
    analyzer = Analyzer("deep")
    specialists = specialist_set()
    planner = FakePlanner()
    planning_service = TrackingPlanningService(planner)
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=planning_service,
        conversational_generator=Generator("conversation"),
        specialists=specialists,
    )

    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )

    assert result.disposition == "unsupported"
    assert result.plan is None
    assert result.clarification_question is None
    assert result.state["messages"][-1].content == UNSUPPORTED_PLANNING_MESSAGE
    assert result.state["active_agent"] is None
    assert analyzer.calls == 1
    assert planning_service.calls == 1
    assert planner.calls == 1
    assert router.calls == 0
    assert sum(node._generator.calls for node in specialists.values()) == 0
    assert set(result.state) == {"messages", "user_context", "active_agent", "approval_status"}
    assert planner.received is not None
    assert planner.received.request is analyzer.received


@pytest.mark.asyncio
async def test_deep_ready_returns_validated_plan_only(trusted_context, user_message) -> None:
    proposal = PlanProposal(
        disposition="ready",
        tasks=(
            PlannedTask(
                task_id="task-1",
                specialist="knowledge",
                objective="Find the applicable support policy",
                expected_outputs=("Policy summary",),
            ),
        ),
    )
    analyzer = Analyzer("deep")
    router = Router("triage")
    specialists = specialist_set()
    planner = FakePlanner(proposal)
    planning_service = TrackingPlanningService(planner)
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=planning_service,
        conversational_generator=Generator("conversation"),
        specialists=specialists,
    )

    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )

    assert result.disposition == "ready"
    assert isinstance(result.plan, ValidatedPlan)
    assert result.plan.tasks[0].task_id == "task-1"
    assert result.state["messages"][-1].content == user_message.content
    assert len(result.state["messages"]) == 1
    assert set(result.state) == {"messages", "user_context", "active_agent", "approval_status"}
    assert analyzer.calls == planner.calls == planning_service.calls == 1
    assert router.calls == 0
    assert sum(node._generator.calls for node in specialists.values()) == 0


@pytest.mark.asyncio
async def test_deep_clarification_returns_question_without_plan_or_execution(
    trusted_context, user_message
) -> None:
    question = "Which ticket should I investigate?"
    analyzer = Analyzer("deep")
    router = Router("triage")
    specialists = specialist_set()
    planner = FakePlanner(
        PlanProposal(disposition="clarification_required", clarification_question=question)
    )
    planning_service = TrackingPlanningService(planner)
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=planning_service,
        conversational_generator=Generator("conversation"),
        specialists=specialists,
    )

    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )

    assert result.disposition == "clarification_required"
    assert result.clarification_question == question
    assert result.plan is None
    assert len(result.state["messages"]) == 1
    assert analyzer.calls == planner.calls == planning_service.calls == 1
    assert router.calls == 0
    assert sum(node._generator.calls for node in specialists.values()) == 0


@pytest.mark.asyncio
async def test_planning_failures_do_not_fall_back_to_supervisor(
    trusted_context, user_message
) -> None:
    analyzer = Analyzer("deep")
    router = Router("triage")
    specialists = specialist_set()
    planner = FakePlanner(RuntimeError("provider-secret"))
    planning_service = TrackingPlanningService(planner)
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=planning_service,
        conversational_generator=Generator("conversation"),
        specialists=specialists,
    )

    with pytest.raises(PlannerProviderError) as error:
        await graph.ainvoke(
            create_internal_graph_input(user_context=trusted_context, messages=[user_message])
        )

    assert str(error.value) == "The planning provider failed"
    assert "provider-secret" not in str(error.value)
    assert analyzer.calls == planner.calls == planning_service.calls == 1
    assert router.calls == 0
    assert sum(node._generator.calls for node in specialists.values()) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "planner_result,expected_error",
    [
        ({"disposition": "unsupported", "planner_message": "private"}, InvalidPlanProposalError),
        (
            PlanProposal(
                disposition="ready",
                tasks=(
                    PlannedTask(
                        task_id="task-1",
                        specialist="triage",
                        objective="Review the support request",
                        expected_outputs=("Summary",),
                        depends_on=("missing-task",),
                    ),
                ),
            ),
            PlanValidationError,
        ),
    ],
)
async def test_invalid_planning_output_never_reaches_supervisor(
    trusted_context, user_message, planner_result, expected_error
) -> None:
    analyzer = Analyzer("deep")
    router = Router("triage")
    specialists = specialist_set()
    planner = FakePlanner(planner_result)
    planning_service = TrackingPlanningService(planner)
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=planning_service,
        conversational_generator=Generator("conversation"),
        specialists=specialists,
    )

    with pytest.raises(expected_error):
        await graph.ainvoke(
            create_internal_graph_input(user_context=trusted_context, messages=[user_message])
        )

    assert analyzer.calls == planner.calls == planning_service.calls == 1
    assert router.calls == 0
    assert sum(node._generator.calls for node in specialists.values()) == 0


@pytest.mark.asyncio
async def test_async_graph_rejects_plain_input(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(
        Router("triage"),
        analyzer=Analyzer(),
        planning_service=unused_planning_service(),
        conversational_generator=Generator("conversation"),
        specialists=specialist_set(),
    )

    with pytest.raises(TypeError, match="internal graph input"):
        await graph.ainvoke({})  # type: ignore[arg-type]


def test_specialist_graph_sync_error_is_application_level(trusted_context, user_message) -> None:
    router = Router("triage")
    analyzer = Analyzer()
    graph = build_orchestration_graph(
        router,
        analyzer=analyzer,
        planning_service=unused_planning_service(),
        conversational_generator=Generator("conversation"),
        specialists=specialist_set(),
    )

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
        planning_service=unused_planning_service(),
        conversational_generator=Generator("conversation"),
        specialists=specialist_set(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    object.__setattr__(graph_input, "user_context", None)

    with pytest.raises(InvalidTrustedContextError, match="validated trusted"):
        await graph.ainvoke(graph_input)
    assert analyzer.calls == 0


def test_graph_requires_specialist_nodes() -> None:
    with pytest.raises(TypeError, match="specialists"):
        build_orchestration_graph(
            Router("triage"),
            analyzer=Analyzer(),
            planning_service=unused_planning_service(),
            conversational_generator=Generator("unused"),
        )  # type: ignore[call-arg]


@pytest.mark.parametrize("mapping", [{}, {"triage": object(), "knowledge": object()}])
def test_graph_rejects_empty_or_incomplete_specialist_mapping(mapping) -> None:
    with pytest.raises(ValueError, match="Specialist mapping"):
        build_orchestration_graph(
            Router("triage"),
            analyzer=Analyzer(),
            planning_service=unused_planning_service(),
            conversational_generator=Generator("unused"),
            specialists=mapping,
        )


def test_graph_rejects_non_specialist_mapping_value() -> None:
    with pytest.raises(TypeError, match="SpecialistNode"):
        build_orchestration_graph(
            Router("triage"),
            analyzer=Analyzer(),
            planning_service=unused_planning_service(),
            conversational_generator=Generator("unused"),
            specialists={"triage": object(), "knowledge": object(), "billing": object()},
        )


def test_graph_rejects_specialist_nodes_under_the_wrong_identity() -> None:
    specialists = specialist_set()
    specialists["triage"], specialists["knowledge"] = (
        specialists["knowledge"],
        specialists["triage"],
    )

    with pytest.raises(ValueError, match="match its specialist mapping key"):
        build_orchestration_graph(
            Router("triage"),
            analyzer=Analyzer(),
            planning_service=unused_planning_service(),
            conversational_generator=Generator("unused"),
            specialists=specialists,
        )


def test_graph_requires_explicit_planning_service() -> None:
    with pytest.raises(TypeError, match="planning_service"):
        build_orchestration_graph(
            Router("triage"),
            analyzer=Analyzer(),
            conversational_generator=Generator("unused"),
            specialists=specialist_set(),
        )  # type: ignore[call-arg]
