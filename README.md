# TripCrew-AI — Production Multi-Agent Travel Orchestration System

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Groq](https://img.shields.io/badge/Inference-Groq-F55036)](https://groq.com/)
[![MCP](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-000000)](https://modelcontextprotocol.io/)
[![PostgreSQL](https://img.shields.io/badge/Persistence-PostgreSQL%20Checkpointer-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**TripCrew-AI** is a stateful multi-agent travel planning application built with **FastAPI**, **LangGraph**, **Groq**, **PostgreSQL**, and **Model Context Protocol (MCP)** integrations. Developed across three progressive milestones—**Part 1 (`v1.0-part1-MultiAgent_Workflow_Baseline`)**, **Part 2 (`v2.0-part2-MultiAgent_MCP_Integration`)**, and **Part 3 (`v3.0-part3-Supervisor_Guardrails_Safety_HITL`)**—it combines input guardrails, supervisor-driven agent routing and trip constraint extraction, MCP-backed specialist tools, durable PostgreSQL state checkpointing, and Human-in-the-Loop (HITL) plan approval and revision workflows.

---

## Table of Contents

- [Release Progression (Parts 1, 2 & 3)](#release-progression-parts-1-2--3)
- [Architectural Overview](#architectural-overview)
- [System Block Diagram](#system-block-diagram)
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
- [License](#license)

---

## Release Progression (Parts 1, 2 & 3)

| Milestone | Git Tag | Architectural Focus |
| :--- | :--- | :--- |
| **Part 1** | `v1.0-part1-MultiAgent_Workflow_Baseline` | Foundational multi-agent travel planning workflow and FastAPI web interface. |
| **Part 2** | `v2.0-part2-MultiAgent_MCP_Integration` | Added MCP client integration (`mcp_client.py`) and custom weather MCP server (`custom_weather_mcp_server.py`) for aviation, search, and weather tools. |
| **Part 3** | `v3.0-part3-Supervisor_Guardrails_Safety_HITL` | Added input guardrail validation, `supervisor_agent` routing & `trip_constraints` extraction, PostgreSQL checkpointing (`PostgresSaver`), and HITL `interrupt()` / `Command(resume=...)` review and feedback revision. |

---

## Architectural Overview

Single-prompt LLM pipelines struggle with multi-constraint travel planning due to context drift, stale reference data, and unverified tool calls. **TripCrew-AI** models travel planning as a checkpointed **LangGraph** state machine:

- **Guardrail & Supervisor Routing (`supervisor_agent`):** Validates travel relevance and safety up front, extracts structured `trip_constraints` (`destination`, `origin`, `duration`, `budget`, `travel_style`, `special_preferences`), and selects only the specialist agents required for the request.
- **Fast Inference with Groq:** Agent routing, budget/itinerary drafting, and final 7-section plan synthesis run on **Groq** (`ChatGroq`) for low-latency execution.
- **MCP & External Tool Integration (`mcp_client.py` & `custom_weather_mcp_server.py`):** Specialist nodes query aviation data, web/hotel search, and current/forecast weather tools with graceful fallback handling when live tool responses are unavailable.
- **Durable State & Thread Continuity (`PostgresSaver`):** Graph checkpoints are persisted in **PostgreSQL** keyed by `thread_id`, enabling paused execution states and multi-turn session tracking.
- **Human-in-the-Loop (HITL) Interrupts:** Execution pauses at `human_approval` via LangGraph `interrupt(...)`, allowing users in the web UI to approve the draft plan or submit revision feedback before `final_agent` generates the complete 7-section response.

---

## System Block Diagram

```mermaid
block-beta
  columns 3

  block:UI_GROUP:1
    columns 1
    UI_MAIN["Web Frontend\ntemplates/index.html & static/script.js"]
    UI_HITL["HITL Review Controls\nApprove / Request Revision"]
  end

  block:API_GROUP:1
    columns 1
    API_SRV["FastAPI Server (app.py)\n/api/travel & /api/travel/resume"]
    LLM_ENG["Groq Inference (ChatGroq)\nGROQ_API_KEY"]
  end

  block:DATA_GROUP:1
    columns 1
    PG_DB["PostgreSQL Checkpointer\nPostgresSaver (DATABASE_URL)"]
    MCP_LAYER["MCP & Tool Helpers\nmcp_client.py & custom_weather_mcp_server.py"]
  end

  block:GRAPH_GROUP:3
    columns 3
    G_SUP["Guardrail & Supervisor\nsupervisor_agent"]
    G_SPEC["Specialist & Draft Nodes\nflight, hotel, weather, budget, itinerary"]
    G_HITL["HITL & Finalizer\nhuman_approval -> final_agent"]
  end
