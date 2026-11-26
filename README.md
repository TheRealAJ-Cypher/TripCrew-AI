# TripCrew AI — Multi-Agent Travel Planning System

A multi-agent travel planning assistant built with **FastAPI**, **LangGraph**, **Groq**, **PostgreSQL**, and **Model Context Protocol (MCP)** tools. The project evolved across three progressive milestones:

- **Part 1 (`v1.0-part1-MultiAgent_Workflow_Baseline`):** Core multi-agent travel workflow and FastAPI web interface.
- **Part 2 (`v2.0-part2-MultiAgent_MCP_Integration`):** Integration of MCP and external travel tool helpers (`mcp_client.py` and `custom_weather_mcp_server.py`) for aviation, destination search, and weather/forecast data.
- **Part 3 (`v3.0-part3-Supervisor_Guardrails_Safety_HITL`):** Input guardrail validation, supervisor routing and constraint extraction, PostgreSQL state checkpointing (`PostgresSaver`), and Human-in-the-Loop (`interrupt` / `Command(resume=...)`) approval and feedback revision.

---

## System Architecture Diagram (Part 3: MCP + Supervisor + Guardrails + HITL)

```text
+-----------------------------------------------------------------------------+
|                          Browser UI (127.0.0.1:8000)                        |
|           templates/index.html  +  static/script.js  (Markdown/PDF)         |
+--------------------------------------+--------------------------------------+
                                       |
               POST /api/travel         |         POST /api/travel/resume
         { message, thread_id? }       |       { thread_id, approved, feedback }
                                       v
+-----------------------------------------------------------------------------+
|                        FastAPI Application (app.py)                         |
+--------------------------------------+--------------------------------------+
                                       |
                        run_travel_agent / resume_travel_agent
                                       v
+-----------------------------------------------------------------------------+
|                      LangGraph State Machine (backend.py)                   |
|                                                                             |
|    [START] ---> [supervisor_agent]                                          |
|                     |          |                                            |
|       (blocked)     |          +--(allowed: routes selected_agents)---+    |
|                     v                                               |    |
|            [guardrail_blocked] ---> [END]                           |    |
|                                                                     v    |
|         +-------------------------------------------------------+   |    |
|         |  flight_agent -> hotel_agent -> weather_agent ->        |   |    |
|         |  budget_agent -> itinerary_agent                      |   |    |
|         +---------------------------+---------------------------+   |    |
|                                     |                               |    |
|                                     v                               |    |
|                           [human_approval]                          |    |
|                        (interrupt() pause state)                    |    |
|                                     |                               |    |
|               Command(resume={ approved, feedback })                |    |
|                                     v                               |    |
|                             [final_agent]                           |    |
|                     (7-section polished travel plan)                |    |
|                                     |                               |    |
|                                     v                               |    |
|                                   [END]                             |    |
+------------------+----------------------------------+---------------+----+
                   |                                  |
                   v                                  v
+------------------------------------+  +-------------------------------------+
|   PostgreSQL Checkpointer          |  |   MCP & Tool Layer                  |
|   (PostgresSaver via DATABASE_URL) |  |   - mcp_client.py                   |
|   - Persists thread_id state       |  |   - custom_weather_mcp_server.py    |
|   - Enables HITL pause & resume    |  |   - Aviation / Search / Weather     |
+------------------------------------+  +-------------------------------------+
Component Block DiagramPlaintext+-----------------------------------------------------------------------------------+
|                                  TripCrew AI                                      |
|                                                                                   |
|  +-----------------------+    +------------------------+    +------------------+  |
|  |   Frontend Layer      |    |   API & Service Layer  |    |  LLM Engine      |  |
|  | - index.html          |    | - app.py (FastAPI)     |    | - ChatGroq       |  |
|  | - script.js           |    | - /api/travel          |    | - GROQ_API_KEY   |  |
|  | - HITL Review Panel   |    | - /api/travel/resume   |    |                  |  |
|  +-----------------------+    +------------------------+    +------------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                     Orchestration & Governance (backend.py)                 |  |
|  |                                                                             |  |
|  |  +--------------------+  +--------------------+  +----------------------+  |  |
|  |  | Input Guardrail    |  | Supervisor Router  |  | HITL Review Gate     |  |  |
|  |  | - Travel relevance |  | - Selects agents   |  | - interrupt()        |  |  |
|  |  | - Safety check     |  | - Trip constraints |  | - Approve / Revise   |  |  |
|  |  +--------------------+  +--------------------+  +----------------------+  |  |
|  |                                                                             |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  |  | Specialist Nodes                                                      |  |  |
|  |  | flight_agent | hotel_agent | weather_agent | budget_agent | itinerary |  |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  |                                                                             |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  |  | Synthesis Node: final_agent (1. Trip Summary .. 7. Final Recs)       |  |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  +-----------------------+    +------------------------+    +------------------+  |
|  |   MCP & Tooling       |    |   State Persistence    |    |  Release Tags    |  |
|  | - mcp_client.py       |    | - PostgreSQL           |    | - v1.0-part1-... |  |
|  | - weather MCP server  |    | - PostgresSaver        |    | - v2.0-part2-... |  |
|  | - Graceful fallbacks  |    | - thread_id checkpoints|    | - v3.0-part3-... |  |
|  +-----------------------+    +------------------------+    +------------------+  |
+-----------------------------------------------------------------------------------+
Milestones Across ReleasesMilestoneGit TagFocus & Key CapabilitiesPart 1v1.0-part1-MultiAgent_Workflow_BaselineBaseline multi-agent travel planning graph and FastAPI web interface.Part 2v2.0-part2-MultiAgent_MCP_IntegrationAdded MCP client integration (mcp_client.py) and custom weather MCP server (custom_weather_mcp_server.py).Part 3v3.0-part3-Supervisor_Guardrails_Safety_HITLAdded input guardrails, supervisor agent routing, PostgreSQL checkpointing, and HITL approval/feedback revision.Project StructurePlaintextTripCrew-AI/
├── app.py                        # FastAPI server, web UI routes, and /api/travel endpoints
├── backend.py                    # LangGraph state graph, supervisor, guardrails, HITL & Postgres checkpointer
├── mcp_client.py                 # Client wrappers for MCP and external travel tools
├── custom_weather_mcp_server.py  # Custom MCP weather server
├── requirements.txt              # Python dependencies
├── static/
│   └── script.js                 # Frontend logic, HITL controls, Markdown rendering, copy & PDF export
└── templates/
    └── index.html                # Web UI template
Prerequisites & Setup (Windows)1. PrerequisitesPython 3.10+GitPostgreSQL database connection URL (DATABASE_URL)Groq API Key (GROQ_API_KEY)2. Virtual Environment & InstallationPowerShellpython -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
3. Environment Variables (.env)Create a .env file in the project root (do not commit .env to version control):Code snippetGROQ_API_KEY=your_groq_api_key_here
DATABASE_URL=your_postgresql_connection_string_here
4. Run the ApplicationPowerShellpython app.py
Open your browser to http://127.0.0.1:8000.(Optional) If running the custom weather MCP server separately during tool experimentation:PowerShellpython custom_weather_mcp_server.py
API EndpointsPOST /api/travel — Starts a travel-planning run for a given message (and optional thread_id), runs the guardrail, supervisor, and selected specialist/draft nodes, and pauses at HITL review when required.POST /api/travel/resume — Resumes a paused thread_id with approved (true or false) and optional feedback to produce the final response.
