# TripCrew-AI — Multi-Agent Travel Planning System

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Groq](https://img.shields.io/badge/Inference-Groq-F55036)](https://groq.com/)
[![MCP](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-000000)](https://modelcontextprotocol.io/)
[![PostgreSQL](https://img.shields.io/badge/Persistence-PostgreSQL%20Checkpointer-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

**TripCrew-AI** is a multi-agent travel planning application built with **FastAPI**, **LangGraph**, **Groq**, **PostgreSQL**, and **Model Context Protocol (MCP)** integrations. Developed across three progressive milestones—**Part 1**, **Part 2**, and **Part 3**—it combines input guardrails, supervisor-driven agent selection and constraint extraction, MCP-backed specialist tools, PostgreSQL state checkpointing, and Human-in-the-Loop (HITL) plan review.

---

## Project Milestones (Parts 1, 2 & 3)

| Part | Release Tag | Summary |
| :--- | :--- | :--- |
| **Part 1** | `v1.0-part1-MultiAgent_Workflow_Baseline` | Foundational multi-agent travel planning workflow and FastAPI web interface. |
| **Part 2** | `v2.0-part2-MultiAgent_MCP_Integration` | Added MCP client integration (`mcp_client.py`) and custom weather MCP server (`custom_weather_mcp_server.py`) for flights, search, and weather. |
| **Part 3** | `v3.0-part3-Supervisor_Guardrails_Safety_HITL` | Added input guardrail validation, `supervisor_agent` routing & trip constraint extraction, PostgreSQL checkpointing (`PostgresSaver`), and HITL `interrupt()` / `Command(resume=...)` review & revision. |

---

## System Architecture Diagram (Part 3)

```mermaid
flowchart TD
    UI[Web UI - templates/index.html & static/script.js] -->|POST /api/travel| API[FastAPI Server - app.py]
    UI -->|POST /api/travel/resume| API

    API --> SUP[supervisor_agent + Input Guardrail]
    SUP -->|Blocked / Non-Travel| BLK[guardrail_blocked] --> END_NODE([END])

    SUP -->|Allowed: selected_agents & trip_constraints| FLT[flight_agent]
    FLT --> HTL[hotel_agent]
    HTL --> WTH[weather_agent]
    WTH --> BDG[budget_agent]
    BDG --> ITN[itinerary_agent]

    ITN --> HITL[human_approval - LangGraph interrupt]
    HITL -->|Command resume approved / feedback| FIN[final_agent - 7-Section Plan]
    FIN --> END_NODE

    FLT <--> MCP[mcp_client.py & custom_weather_mcp_server.py]
    HTL <--> MCP
    WTH <--> MCP

    SUP -.-> PG[(PostgreSQL Checkpointer - PostgresSaver)]
    HITL -.-> PG
    FIN -.-> PG

## Component Block Diagram
+-------------------------------------------------------------------------------+
|                                 TripCrew-AI                                   |
|                                                                               |
|  +-------------------------+   +-----------------------+   +---------------+  |
|  | Frontend UI             |   | FastAPI Layer         |   | LLM & State   |  |
|  | - templates/index.html  |   | - app.py              |   | - ChatGroq    |  |
|  | - static/script.js      |   | - /api/travel         |   | - TravelState |  |
|  | - HITL Review Panel     |   | - /api/travel/resume  |   |               |  |
|  +-------------------------+   +-----------------------+   +---------------+  |
|                                                                               |
|  +-------------------------------------------------------------------------+  |
|  | LangGraph Orchestration (backend.py)                                    |  |
|  |                                                                         |  |
|  |  [Input Guardrail + Supervisor] --> [Selected Specialist Agents]        |  |
|  |         (flight_agent, hotel_agent, weather_agent, budget_agent)        |  |
|  |                |                                                        |  |
|  |                v                                                        |  |
|  |  [itinerary_agent] --> [human_approval interrupt()] --> [final_agent]   |  |
|  +-------------------------------------------------------------------------+  |
|                                                                               |
|  +-------------------------+   +-----------------------+   +---------------+  |
|  | MCP & Tool Layer        |   | Checkpointing         |   | Version Tags  |  |
|  | - mcp_client.py         |   | - PostgreSQL          |   | - v1.0-part1  |  |
|  | - custom_weather_mcp    |   | - PostgresSaver       |   | - v2.0-part2  |  |
|  |   _server.py            |   | - thread_id state     |   | - v3.0-part3  |  |
|  +-------------------------+   +-----------------------+   +---------------+  |
+-------------------------------------------------------------------------------+

Component,Role,Key Responsibilities
app.py,API & Web Server,Serves the web UI and exposes endpoints to start and resume travel planning runs.
supervisor_agent,Guardrail & Router,"Validates travel relevance/safety, extracts trip_constraints, and selects needed specialist agents."
flight_agent,Flight Specialist,"Queries aviation MCP helpers and summarizes airports, airlines, duration/stops, fares, and booking tips."
hotel_agent,Accommodation Specialist,Searches hotel/stay guidance via MCP/search helpers with graceful fallback messaging when live data is unavailable.
weather_agent,Weather & Packing Specialist,Extracts destination and retrieves current weather and forecast data via MCP/weather helpers.
budget_agent,Budget Analyst,"Evaluates cost categories, budget risks, money-saving options, and feasibility against trip constraints."
itinerary_agent,Draft Itinerary Builder,Generates a day-by-day draft plan and prepares the approval prompt for human review.
human_approval,HITL Checkpoint,"Pauses execution with interrupt() and resumes with Command(resume={""approved"": ..., ""feedback"": ...})."
final_agent,Final Synthesizer,Produces the complete 7-section travel plan incorporating approval or revision feedback.
mcp_client.py & custom_weather_mcp_server.py,MCP & Tool Layer,Provides async/sync wrappers and custom MCP weather server functionality.

## Repository Structure

TripCrew-AI/
├── app.py                        # FastAPI web server and API routes
├── backend.py                    # LangGraph graph, supervisor, guardrails, HITL & Postgres checkpointer
├── mcp_client.py                 # MCP and external tool client wrappers
├── custom_weather_mcp_server.py  # Custom MCP weather server
├── requirements.txt              # Python dependencies
├── static/
│   └── script.js                 # Frontend logic, HITL controls, Markdown rendering, copy & PDF export
└── templates/
    └── index.html                # Web UI template

Getting Started (Windows)
1. Prerequisites
Python 3.10+
Git
Groq API Key (GROQ_API_KEY)
PostgreSQL connection URL (DATABASE_URL)

2. Virtual Environment & Dependencies
PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
3. Environment Variables (.env)
Create a .env file in the project root (do not commit .env to Git):

Code snippet
GROQ_API_KEY=your_groq_api_key_here
DATABASE_URL=your_postgresql_connection_string_here
4. Run the Application
PowerShell
python app.py
Open http://127.0.0.1:8000 in your browser. To run the custom weather MCP server separately during experimentation:

PowerShell
python custom_weather_mcp_server.py
API Workflow
POST /api/travel — Starts or continues a thread_id run, applies the input guardrail and supervisor routing, executes specialist and draft itinerary steps, and pauses at human_approval when review is required.

POST /api/travel/resume — Resumes the paused graph thread with approved (true or false) and optional feedback to run final_agent and return the completed plan.
