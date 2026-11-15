# TripCrew-AI — Production Multi-Agent Travel Orchestration System

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
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


