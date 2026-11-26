import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import operator
import os
import time
import uuid
from typing import Annotated, Any, TypedDict

import certifi
from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
import psycopg
from psycopg.rows import dict_row

from mcp_client import (
    aviation_mcp_call,
    extract_destination,
    forecast_mcp_search,
    tavily_mcp_search,
    weather_mcp_search,
)

load_dotenv()
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# Optional pacing (seconds between LLM calls) to avoid bursting past 8,000 TPM.
GROQ_MIN_INTERVAL_SEC = float(os.getenv("GROQ_MIN_INTERVAL_SEC", "0"))
_LAST_LLM_CALL_TS = 0.0

# Character budgets to keep single-request prompt sizes well below 8,000 TPM (~4 chars/token).
MAX_RAW_TOOL_CHARS = 2400
MAX_SECTION_CHARS = 1800
MAX_ITINERARY_CHARS = 2200


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. "
            "Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")

# =========================
# LLM - original model kept
# =========================
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY,
    temperature=0.3,
)


# =========================
# State - original fields kept, new control fields added
# =========================
class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str

    # Supervisor + guardrail state
    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]
    supervisor_reasoning: str

    # Original specialist results
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str

    # New budget + HITL state
    budget_results: str
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    llm_calls: int


# =========================
# Shared helpers
# =========================
KNOWN_AGENTS = {
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
}

AGENT_ORDER = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
]


def _run_async(coro):
    """Run an async coroutine safely even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _pace_llm_call() -> None:
    global _LAST_LLM_CALL_TS
    if GROQ_MIN_INTERVAL_SEC > 0:
        elapsed = time.monotonic() - _LAST_LLM_CALL_TS
        if elapsed < GROQ_MIN_INTERVAL_SEC:
            time.sleep(GROQ_MIN_INTERVAL_SEC - elapsed)
    _LAST_LLM_CALL_TS = time.monotonic()


def _trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated for token budget]"


def _compact_tool_payload(payload: Any, max_chars: int = MAX_RAW_TOOL_CHARS) -> str:
    """Reduce verbose MCP/search JSON or long text while retaining key facts."""
    if isinstance(payload, (dict, list)):
        try:
            dumped = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            dumped = str(payload)
        return _trim_text(dumped, max_chars)

    raw = str(payload or "").strip()
    if raw.startswith("{") or raw.startswith("["):
        try:
            parsed = json.loads(raw)
            dumped = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
            return _trim_text(dumped, max_chars)
        except Exception:
            pass

    return _trim_text(raw, max_chars)


def _compact_constraints(constraints: dict[str, Any] | None) -> str:
    if not isinstance(constraints, dict):
        return "{}"
    cleaned = {
        k: v
        for k, v in constraints.items()
        if v not in ("", [], None, {})
    }
    return _trim_text(json.dumps(cleaned, ensure_ascii=False), 400)


def _llm_text(system_prompt: str, user_prompt: str) -> str:
    _pace_llm_call()
    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return str(response.content)


def _json_from_llm(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object returned by the model."""
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("The model did not return a JSON object.")

    return json.loads(text[start : end + 1])


def _empty_constraints() -> dict[str, Any]:
    return {
        "destination": "",
        "origin": "",
        "duration": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": [],
    }


# =========================
# Supervisor Agent + Input Guardrail
# =========================
def supervisor_agent(state: TravelState):
    query = _trim_text(state["user_query"], 1000)
    llm_calls = state.get("llm_calls", 0)

    guardrail_prompt = f"""
Determine whether the following request belongs to travel planning or travel
information. Valid requests can include destinations, flights, hotels, weather,
budgets, visas, transportation, sightseeing, food, packing, or itineraries.

Block clearly unrelated requests and requests asking for harmful or illegal
instructions. Do not block a valid travel request merely because some details
are missing.

Return strict JSON only:
{{
  "allowed": true,
  "reason": ""
}}

User request:
{query}
"""

    try:
        guardrail_raw = _llm_text(
            "You are the input guardrail for a travel-planning application. "
            "Return strict JSON only.",
            guardrail_prompt,
        )
        guardrail_result = _json_from_llm(guardrail_raw)
        allowed = bool(guardrail_result.get("allowed", True))
        guardrail_reason = str(guardrail_result.get("reason", "")).strip()
        llm_calls += 1
    except Exception as exc:
        print(f"Guardrail fallback used: {exc}")
        allowed = True
        guardrail_reason = "Guardrail validation fallback allowed the request."

    if not allowed:
        reason = guardrail_reason or (
            "TripMate AI can only help with travel-planning requests. "
            "Please ask about a destination, flight, hotel, weather, budget, "
            "or itinerary."
        )
        return {
            "guardrail_allowed": False,
            "guardrail_reason": reason,
            "selected_agents": [],
            "trip_constraints": _empty_constraints(),
            "supervisor_reasoning": reason,
            "final_response": reason,
            "messages": [AIMessage(content="Guardrail blocked request.")],
            "llm_calls": llm_calls,
        }

    supervisor_prompt = f"""
You are the supervisor of a multi-agent travel-planning system.
Choose only the specialist agents needed for the request.

Available agents:
- flight_agent: flights, airports, airlines, routes, airfare, or booking advice
- hotel_agent: hotels, accommodation, neighborhoods, or places to stay
- weather_agent: weather, climate, season, forecast, or packing advice
- budget_agent: cost, affordability, price limits, or budget feasibility
- itinerary_agent: creates the integrated travel plan and must always be included

Return strict JSON only using this schema:
{{
  "selected_agents": ["flight_agent", "hotel_agent", "weather_agent", "budget_agent", "itinerary_agent"],
  "trip_constraints": {{
    "destination": "",
    "origin": "",
    "duration": "",
    "budget": "",
    "travel_style": "",
    "special_preferences": []
  }},
  "reasoning": ""
}}

User request:
{query}
"""

    try:
        supervisor_raw = _llm_text(
            "You route work to travel specialist agents. Return strict JSON only.",
            supervisor_prompt,
        )
        parsed = _json_from_llm(supervisor_raw)
        requested_agents = parsed.get("selected_agents", [])
        selected_agents = [
            name for name in AGENT_ORDER
            if name in requested_agents and name in KNOWN_AGENTS
        ]

        if "itinerary_agent" not in selected_agents:
            selected_agents.append("itinerary_agent")

        constraints = _empty_constraints()
        parsed_constraints = parsed.get("trip_constraints", {})
        if isinstance(parsed_constraints, dict):
            constraints.update(parsed_constraints)

        reasoning = _trim_text(parsed.get("reasoning", ""), 300)
        llm_calls += 1
    except Exception as exc:
        print(f"Supervisor fallback used: {exc}")
        selected_agents = AGENT_ORDER.copy()
        constraints = _empty_constraints()
        reasoning = (
            "Supervisor parsing failed, so the original full travel workflow "
            "was selected as a safe fallback."
        )

    return {
        "guardrail_allowed": True,
        "guardrail_reason": guardrail_reason,
        "selected_agents": selected_agents,
        "trip_constraints": constraints,
        "supervisor_reasoning": reasoning,
        "messages": [AIMessage(content="Supervisor created the agent plan.")],
        "llm_calls": llm_calls,
    }


# =========================
# Guardrail blocked response
# =========================
def guardrail_blocked_agent(state: TravelState):
    reason = state.get("final_response") or state.get("guardrail_reason") or (
        "This request was blocked by the travel input guardrail."
    )
    return {
        "final_response": reason,
        "messages": [AIMessage(content=reason)],
    }


# =========================
# Flight Agent
# =========================
FLIGHT_AGENT_PROMPT = """
You are a travel flight expert. Keep points brief and specific.

User Query:
{query}

Airport Data:
{airport_data}

Airline Data:
{airline_data}

Provide concise bullet points for:
1. Likely departure & arrival airports
2. Airlines serving this route
3. Typical flight duration & airfare range
4. Peak season pricing warning & booking advice
"""


def flight_agent(state: TravelState):
    print("\nINSIDE FLIGHT AGENT\n")
    query = _trim_text(state["user_query"], 600)

    try:
        airports = _run_async(aviation_mcp_call("list_airports"))
        airlines = _run_async(aviation_mcp_call("list_airlines"))

        prompt = FLIGHT_AGENT_PROMPT.format(
            query=query,
            airport_data=_compact_tool_payload(airports, 1400),
            airline_data=_compact_tool_payload(airlines, 1400),
        )

        flight_data = _trim_text(
            _llm_text("You are an expert travel flight planner.", prompt),
            MAX_SECTION_CHARS,
        )
    except Exception as exc:
        flight_data = f"Flight information unavailable: {exc}"

    return {
        "flight_results": flight_data,
        "messages": [AIMessage(content="Flight recommendations generated.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Hotel Agent
# =========================
HOTEL_AGENT_PROMPT = """
Summarize hotel options concisely from the search data below.

User Query:
{query}

Search Results:
{search_data}

Include top hotel/area picks, approximate price tiers, and brief booking tips.
"""


def hotel_agent(state: TravelState):
    query = _trim_text(state["user_query"], 600)
    search_query = f"Best hotels and areas for {query}"

    try:
        raw_search = _run_async(tavily_mcp_search(search_query))
        compacted_search = _compact_tool_payload(raw_search, MAX_RAW_TOOL_CHARS)
        hotel_results = _trim_text(
            _llm_text(
                "You are a concise hotel research specialist.",
                HOTEL_AGENT_PROMPT.format(
                    query=query,
                    search_data=compacted_search,
                ),
            ),
            MAX_SECTION_CHARS,
        )
        llm_calls = state.get("llm_calls", 0) + 1
    except Exception as exc:
        print(
            f"HOTEL AGENT MCP ERROR: {type(exc).__name__}: {exc}",
            flush=True,
        )
        hotel_results = (
            "Live hotel search is temporarily unavailable. "
            "Provide general accommodation and neighborhood guidance based on "
            "the destination and label it as non-live advice."
        )
        llm_calls = state.get("llm_calls", 0)

    return {
        "hotel_results": hotel_results,
        "messages": [AIMessage(content="Hotel information processed.")],
        "llm_calls": llm_calls,
    }


# =========================
# Weather Agent
# =========================
def weather_agent(state: TravelState):
    city = extract_destination(_trim_text(state["user_query"], 600))

    try:
        weather_data = _run_async(weather_mcp_search(city))
        forecast_data = _run_async(forecast_mcp_search(city))

        weather_results = _trim_text(
            f"Current Weather:\n{_compact_tool_payload(weather_data, 1000)}\n\n"
            f"Forecast:\n{_compact_tool_payload(forecast_data, 1200)}",
            MAX_SECTION_CHARS,
        )
    except Exception as exc:
        print(
            f"WEATHER AGENT MCP ERROR: {type(exc).__name__}: {exc}",
            flush=True,
        )
        weather_results = (
            f"Live weather information for {city} is temporarily unavailable. "
            "Give general seasonal guidance and advise the traveler to verify "
            "the forecast before departure."
        )

    return {
        "weather_results": weather_results,
        "messages": [AIMessage(content="Weather information processed.")],
    }


# =========================
# Budget Agent
# =========================
def budget_agent(state: TravelState):
    prompt = f"""
Analyze trip budget feasibility concisely.

User Query:
{_trim_text(state['user_query'], 500)}

Trip Constraints:
{_compact_constraints(state.get('trip_constraints'))}

Flights Summary:
{_trim_text(state.get('flight_results', ''), 900)}

Hotels Summary:
{_trim_text(state.get('hotel_results', ''), 900)}

Weather Summary:
{_trim_text(state.get('weather_results', ''), 700)}

Return concise bullets for:
1. Estimated cost categories
2. Budget risk areas
3. Money-saving suggestions
4. Overall feasibility (label approximate estimates clearly)
"""

    budget_text = _trim_text(
        _llm_text("You are a practical travel budget analyst.", prompt),
        MAX_SECTION_CHARS,
    )

    return {
        "budget_results": budget_text,
        "messages": [AIMessage(content="Budget assessment generated.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Itinerary Agent
# =========================
def itinerary_agent(state: TravelState):
    prompt = f"""
Create a clear, practical, budget-aware draft travel itinerary.

User Query:
{_trim_text(state['user_query'], 500)}

Trip Constraints:
{_compact_constraints(state.get('trip_constraints'))}

Flights:
{_trim_text(state.get('flight_results', ''), 800)}

Hotels:
{_trim_text(state.get('hotel_results', ''), 800)}

Weather:
{_trim_text(state.get('weather_results', ''), 650)}

Budget:
{_trim_text(state.get('budget_results', ''), 800)}

Keep the draft focused and easy to review for human approval.
"""

    itinerary_text = _trim_text(
        _llm_text("You are an expert travel planner.", prompt),
        MAX_ITINERARY_CHARS,
    )

    approval_request = (
        "Please review the generated draft itinerary. Approve it to create the "
        "final polished plan, or provide feedback for revision."
    )

    return {
        "itinerary": itinerary_text,
        "approval_request": approval_request,
        "messages": [AIMessage(content="Draft itinerary created for human review.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Human-in-the-Loop approval
# =========================
def human_approval_agent(state: TravelState):
    # Do not wrap interrupt() in try/except. LangGraph uses it to pause execution.
    review = interrupt(
        {
            "question": "Do you approve this itinerary?",
            "draft_itinerary": state.get("itinerary", ""),
            "approval_request": state.get("approval_request", ""),
            "selected_agents": state.get("selected_agents", []),
            "supervisor_reasoning": state.get("supervisor_reasoning", ""),
            "expected_response": {
                "approved": True,
                "feedback": "Optional revision feedback",
            },
        }
    )

    approved = bool(review.get("approved", False))
    human_feedback = str(review.get("feedback", "")).strip()

    return {
        "approved": approved,
        "human_feedback": human_feedback,
        "messages": [AIMessage(content="Human approval step completed.")],
    }


# =========================
# Final Response Agent
# =========================
def final_agent(state: TravelState):
    if state.get("approved", False):
        review_instruction = (
            "The user approved the draft. Preserve its decisions while polishing it."
        )
    else:
        feedback_clean = _trim_text(state.get("human_feedback", ""), 500)
        review_instruction = (
            "The user requested a revision. Apply this feedback carefully:\n"
            f"{feedback_clean or 'Improve the draft before finalizing it.'}"
        )

    final_prompt = f"""
Generate the final travel response concisely and clearly.

Human Review:
{review_instruction}

User Request:
{_trim_text(state['user_query'], 500)}

Trip Constraints:
{_compact_constraints(state.get('trip_constraints'))}

Flights:
{_trim_text(state.get('flight_results', ''), 750)}

Hotels:
{_trim_text(state.get('hotel_results', ''), 750)}

Weather:
{_trim_text(state.get('weather_results', ''), 600)}

Budget:
{_trim_text(state.get('budget_results', ''), 750)}

Draft Itinerary:
{_trim_text(state.get('itinerary', ''), 1200)}

Format using these exact sections:
1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations

Rules:
- Keep wording concise and practical.
- Note that live flight APIs may omit ticket prices when unavailable.
- Include weather-based advice and apply any human feedback.
"""

    final_text = _llm_text(
        "You are a professional AI travel booking assistant.",
        final_prompt,
    )

    return {
        "final_response": final_text,
        "messages": [AIMessage(content=final_text)],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# =========================
# Dynamic Supervisor Routing
# =========================
ROUTE_MAP = {
    "guardrail_blocked": "guardrail_blocked",
    "flight_agent": "flight_agent",
    "hotel_agent": "hotel_agent",
    "weather_agent": "weather_agent",
    "budget_agent": "budget_agent",
    "itinerary_agent": "itinerary_agent",
}


def _selected_agents(state: TravelState) -> list[str]:
    selected = state.get("selected_agents", [])
    return [agent for agent in AGENT_ORDER if agent in selected]


def route_from_supervisor(state: TravelState) -> str:
    if not state.get("guardrail_allowed", True):
        return "guardrail_blocked"

    selected = _selected_agents(state)
    return selected[0] if selected else "itinerary_agent"


def route_after_agent(current_agent: str):
    def route(state: TravelState) -> str:
        selected = _selected_agents(state)
        current_index = AGENT_ORDER.index(current_agent)

        for next_agent in AGENT_ORDER[current_index + 1 :]:
            if next_agent in selected:
                return next_agent

        return "itinerary_agent"

    return route


# =========================
# Build Graph
# =========================
graph = StateGraph(TravelState)

graph.add_node("supervisor", supervisor_agent)
graph.add_node("guardrail_blocked", guardrail_blocked_agent)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("budget_agent", budget_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("human_approval", human_approval_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)

graph.add_conditional_edges(
    "flight_agent", route_after_agent("flight_agent"), ROUTE_MAP
)
graph.add_conditional_edges(
    "hotel_agent", route_after_agent("hotel_agent"), ROUTE_MAP
)
graph.add_conditional_edges(
    "weather_agent", route_after_agent("weather_agent"), ROUTE_MAP
)
graph.add_conditional_edges(
    "budget_agent", route_after_agent("budget_agent"), ROUTE_MAP
)

graph.add_edge("itinerary_agent", "human_approval")
graph.add_edge("human_approval", "final_agent")
graph.add_edge("final_agent", END)
graph.add_edge("guardrail_blocked", END)

# =========================
# PostgreSQL Checkpointer - original persistence kept
# =========================
DATABASE_URL = get_database_url()
_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row,
)
checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)


# =========================
# FastAPI-facing helpers
# =========================
def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None

    first_interrupt = interrupts[0]
    payload = getattr(first_interrupt, "value", first_interrupt)
    return payload if isinstance(payload, dict) else {"value": payload}


def _serialize_result(
    result: dict[str, Any],
    thread_id: str,
) -> dict[str, Any]:
    messages = result.get("messages", [])
    last_message = messages[-1].content if messages else ""
    answer = result.get("final_response") or last_message
    interrupt_payload = _interrupt_payload(result)

    if interrupt_payload:
        answer = interrupt_payload.get("draft_itinerary") or result.get(
            "itinerary", ""
        )

    return {
        "thread_id": thread_id,
        "answer": answer,
        "requires_approval": interrupt_payload is not None,
        "approval_request": (
            interrupt_payload.get("approval_request", "")
            if interrupt_payload
            else result.get("approval_request", "")
        ),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "itinerary": (
            interrupt_payload.get("draft_itinerary", "")
            if interrupt_payload
            else result.get("itinerary", "")
        ),
        "selected_agents": result.get("selected_agents", []),
        "trip_constraints": result.get("trip_constraints", {}),
        "supervisor_reasoning": result.get("supervisor_reasoning", ""),
        "guardrail_allowed": result.get("guardrail_allowed", True),
        "guardrail_reason": result.get("guardrail_reason", ""),
        "approved": result.get("approved"),
        "human_feedback": result.get("human_feedback", ""),
        "llm_calls": result.get("llm_calls", 0),
    }


def run_travel_agent(user_input: str, thread_id: str | None = None):
    """Start a new travel-planning run and pause at human approval."""
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {"configurable": {"thread_id": thread_id}}

    result = travel_graph.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "guardrail_allowed": True,
            "guardrail_reason": "",
            "selected_agents": [],
            "trip_constraints": _empty_constraints(),
            "supervisor_reasoning": "",
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "budget_results": "",
            "itinerary": "",
            "approval_request": "",
            "approved": False,
            "human_feedback": "",
            "final_response": "",
            "llm_calls": 0,
        },
        config=config,
    )

    return _serialize_result(result, thread_id)


def resume_travel_agent(
    thread_id: str,
    approved: bool,
    feedback: str = "",
):
    """Resume the paused LangGraph thread after human review."""
    if not thread_id:
        raise ValueError("thread_id is required to resume a travel plan.")

    config = {"configurable": {"thread_id": thread_id}}
    result = travel_graph.invoke(
        Command(
            resume={
                "approved": approved,
                "feedback": feedback.strip(),
            }
        ),
        config=config,
    )

    return _serialize_result(result, thread_id)