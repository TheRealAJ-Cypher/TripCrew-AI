
# TripCrew-AI — Production Multi-Agent Travel Orchestration System

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Groq](https://img.shields.io/badge/Inference-Groq%20LPU-F55036)](https://groq.com/)
[![MCP](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-000000)](https://modelcontextprotocol.io/)
[![PostgreSQL](https://img.shields.io/badge/Persistence-PostgreSQL%20Checkpointer-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**TripCrew-AI** is a stateful, production-grade multi-agent travel planning engine built with **LangGraph**, **FastAPI**, **Groq**, and the **Model Context Protocol (MCP)**. It decomposes natural-language travel requests into an orchestrated multi-agent execution graph featuring a **Supervisor Agent**, specialized domain workers (Flight, Hotel, Itinerary, and Synthesis), pre- and post-execution **safety guardrails**, durable **PostgreSQL checkpointing**, and **Human-in-the-Loop (HITL)** approval gates.

---

## Table of Contents

- [Architectural Overview](#architectural-overview)
- [Multi-Agent Topology & Control Flow](#multi-agent-topology--control-flow)
- [Agent & Subsystem Specifications](#agent--subsystem-specifications)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Configuration](#environment-configuration)
  - [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [State Persistence, Guardrails & HITL](#state-persistence-guardrails--hitl)
- [Testing](#testing)
- [License](#license)

---

## Architectural Overview

Single-prompt LLM pipelines struggle with multi-constraint travel planning due to context drift, stale fare data, and unverified tool calls. **TripCrew-AI** solves this by modeling travel synthesis as a deterministic, fault-tolerant state machine:

- **Supervisor-Orchestrated Cyclic Graph:** A central **Supervisor Agent** inspects shared `StateGraph` state, routes bounded subtasks across specialized **Flight**, **Hotel**, **Itinerary**, and **Response** agents, and enforces termination criteria.
- **Low-Latency Inference with Groq:** Agent reasoning, structured routing decisions, and tool-call generation run on **Groq** inference infrastructure for sub-second orchestration turns.
- **Standardized Tooling via MCP:** External domain integrations—including **AviationStack** (real-time flight schedules/routes) and **Tavily** (live web search for accommodations, local attractions, and travel advisories)—are decoupled from agent logic via the **Model Context Protocol (MCP)** inside `tools/`.
- **Durable State & Thread Continuity:** Backed by a **PostgreSQL checkpointer**, every graph super-step is persisted against a session `thread_id`, enabling multi-turn follow-ups, crash recovery, and deterministic replay.
- **Human-in-the-Loop (HITL) Interrupts:** Execution pauses at critical itinerary milestones via LangGraph `interrupt` checkpoints, allowing users to review, approve, or modify proposed flights, hotels, and budget allocations in the web UI before finalization.

---

## Multi-Agent Topology & Control Flow

```mermaid
graph TD
    Client([Web UI / REST Client]) -->|POST /api/travel| FastAPI[FastAPI Gateway - app.py]
    FastAPI --> GuardIn[Ingress Safety Guardrail]
    GuardIn -->|Policy Violation / Injection| Refuse([Safe Refusal Response])
    GuardIn -->|Validated Request| Supervisor{Supervisor Agent}

    Supervisor -->|Route: Flights| FlightAgent[Flight Search Agent]
    Supervisor -->|Route: Hotels| HotelAgent[Hotel Research Agent]
    Supervisor -->|Route: Planning| ItineraryAgent[Itinerary Planning Agent]
    Supervisor -->|Review Checkpoint| HITL[[HITL Interrupt Gate]]
    Supervisor -->|Approved Plan| FinalAgent[Final Synthesis Agent]

    FlightAgent <-->|MCP Tool Call| AviationStack[(AviationStack API)]
    HotelAgent <-->|MCP Tool Call| Tavily[(Tavily Search API)]
    ItineraryAgent <-->|MCP Tool Call| Tavily

    FlightAgent --> Supervisor
    HotelAgent --> Supervisor
    ItineraryAgent --> Supervisor

    HITL -->|User Edits / Re-plan| Supervisor
    HITL -->|User Approved| FinalAgent

    FinalAgent --> GuardOut[Egress Grounding & Budget Guardrail]
    GuardOut --> FastAPI

    Supervisor -.->|State Snapshots| PG[(PostgreSQL Checkpointer)]
    HITL -.->|Checkpoint Resume| PG

```

---

## Agent & Subsystem Specifications

| Component | Architectural Role | External Integrations & Mechanisms |
| --- | --- | --- |
| **Supervisor Agent** | Central planner, task router & state evaluator | Structured output routing, constraint tracking (dates, budget, origin IATA), delegation & convergence control |
| **Flight Search Agent** | Commercial flight discovery & route filtering | **AviationStack API** via MCP tool bindings; normalizes carrier, schedule, and routing options from `DEFAULT_ORIGIN_IATA` |
| **Hotel Research Agent** | Accommodation sourcing & budget matching | **Tavily Search API** via MCP tool bindings; retrieves neighborhood, pricing tier, and property availability context |
| **Itinerary Planning Agent** | Day-by-day schedule & logistics synthesis | Combines flight arrival/departure windows, hotel proximity, and Tavily local attraction intelligence |
| **Final Response Agent** | Structured output formatting & presentation | Compiles verified flight, lodging, and daily schedule blocks into a clean client-ready response |
| **Safety Guardrails** | Ingress & egress policy enforcement | Prompt-injection filtering, off-topic deflection, budget/date sanity checks, and tool-grounding verification |
| **PostgreSQL Checkpointer** | Thread-scoped persistent graph memory | Serializes `StateGraph` checkpoints across turns and preserves paused `interrupt` states |
| **FastAPI + Jinja2 UI (`app.py`)** | Asynchronous REST API & interactive frontend | Serves `templates/` + `static/`, exposes `/health` and `/api/travel`, and manages HITL resume payloads |

---

## Repository Structure

```text
TripCrew-AI/
├── app.py                 # FastAPI server entrypoint, REST endpoints (/health, /api/travel), and UI routes
├── backend.py             # LangGraph StateGraph definition, Supervisor/worker nodes, guardrails & PG checkpointer
├── test.py                # Automated tests for graph execution, tool bindings, and guardrail behavior
├── requirements.txt       # Python runtime and framework dependencies
├── tools/                 # MCP-compliant tool wrappers for AviationStack flight search and Tavily web search
├── templates/             # Jinja2 HTML templates for the interactive web interface
├── static/                # Client-side JavaScript and CSS assets
├── .gitignore             # Git exclusion rules
└── LICENSE                # MIT License

```

---

## Getting Started

### Prerequisites

Before cloning and running the project locally, verify your environment meets the following requirements:

* **Python:** Version 3.10 or higher installed.
* **PostgreSQL:** Running locally or accessible via a remote connection string.
* **API Keys Required:**
* **Groq API Key** (`GROQ_API_KEY`) for ultra-fast agent inference.
* **AviationStack API Key** (`AVIATIONSTACK_API_KEY`) for live flight data and routing schedules.
* **Tavily API Key** (`TAVILY_API_KEY`) for web-grounded hotel and destination research.



### Installation

1. **Clone the repository:**
```bash
git clone [https://github.com/TheRealAJ-Cypher/TripCrew-AI.git](https://github.com/TheRealAJ-Cypher/TripCrew-AI.git)
cd TripCrew-AI

```


2. **Create and activate a virtual environment:**
```bash
python -m venv .venv
# On macOS / Linux:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

```


3. **Install dependencies:**
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt

```



### Environment Configuration

Create a `.env` file in the root directory of your project and configure your environment variables:

```env
# PostgreSQL Database Connection
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/travel_db

# LLM Inference Provider
GROQ_API_KEY=your_groq_api_key_here

# External Tool APIs
AVIATIONSTACK_API_KEY=your_aviationstack_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here

# Default Departure Airport (IATA Code)
DEFAULT_ORIGIN_IATA=MAA

```

### Running the Application

1. **Start your PostgreSQL instance** and ensure the database (`travel_db`) is created.
2. **Start the FastAPI application server:**
```bash
python app.py

```


3. **Access the application:** Open your browser and navigate to `http://127.0.0.1:8000/`.

---

## API Reference

### `GET /health`

Performs a liveness and health check on the FastAPI backend.

```bash
curl [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

```

### `POST /api/travel`

Submits a natural-language user travel request into the LangGraph execution engine.

```bash
curl -X POST [http://127.0.0.1:8000/api/travel](http://127.0.0.1:8000/api/travel) \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan a 3-day trip to Tokyo with a budget of $1200"}'

```

---

## State Persistence, Guardrails & HITL

* **PostgreSQL Checkpointing:** State across every multi-turn conversation is bound to a unique `thread_id` and persisted inside PostgreSQL, ensuring fault tolerance, session recovery, and conversation memory.
* **Safety Guardrails:**
* *Ingress Guardrails* intercept prompt injections, jailbreaks, and off-topic queries before tokens reach the LLM.
* *Egress Guardrails* validate that synthesized travel plans adhere strictly to user budget caps and verified tool outputs.


* **Human-in-the-Loop (HITL) Workflows:** The graph pauses at designated review nodes using LangGraph interrupts. Users can inspect proposed itineraries in the web interface, request adjustments, and approve executions seamlessly.

---

## Testing

Run the automated test suite to verify graph compilation, guardrail logic, and tool bindings:

```bash
python test.py

```

---

## License

This project is licensed under the **MIT License** — see the LICENSE file for details.

```

```