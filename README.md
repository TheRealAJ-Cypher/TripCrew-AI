# TripCrew-AI
A Multi-Agent Travel Planner - Production-ready multi-agent AI system built with LangGraph and Model Context Protocol (MCP), featuring a Supervisor Agent, safety guardrails, PostgreSQL persistence, and Human-in-the-Loop (HITL) workflows.

# TripCrew-AI: Production Multi-Agent Travel Orchestration System

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![MCP](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-000000)](https://modelcontextprotocol.io/)
[![PostgreSQL](https://img.shields.io/badge/Persistence-PostgreSQL%20Checkpointer-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**TripCrew-AI** is a stateful, production-grade multi-agent travel planning engine built on **LangGraph** and the **Model Context Protocol (MCP)**. Designed around a deterministic **Supervisor-Worker topology**, it coordinates specialized domain agents, enforces pre- and post-execution **safety guardrails**, persists graph state via **PostgreSQL checkpointing**, and exposes native **Human-in-the-Loop (HITL)** approval interrupts before high-stakes itinerary commitments.

---

## Table of Contents

- [Architectural Overview](#architectural-overview)
- [Core Agentic Capabilities](#core-agentic-capabilities)
- [System Topology & Control Flow](#system-topology--control-flow)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Configuration](#environment-configuration)
  - [Running the Application](#running-the-application)
- [State Persistence & HITL Workflows](#state-persistence--hitl-workflows)
- [Safety & Guardrail Architecture](#safety--guardrail-architecture)
- [Testing & Evaluation](#testing--evaluation)
- [License](#license)

---

## Architectural Overview

Modern travel planning requires synthesizing real-time search, flight logistics, budget constraints, and user preferences across multi-turn sessions. Rather than relying on a monolithic prompt, **TripCrew-AI** decomposes reasoning across an orchestrated cyclic graph:

- **Supervisor-Driven Routing:** A central Supervisor node evaluates shared `StateGraph` memory, decomposes complex user intents into bounded subtasks, delegates execution to specialized workers, and synthesizes validated outputs.
- **Standardized Tooling via MCP:** External capabilities (flight search, Tavily real-time web intelligence, and custom domain utilities under `tools/`) are decoupled from agent logic using the **Model Context Protocol (MCP)**, enabling modular tool discovery, schema enforcement, and transport-agnostic execution.
- **Durable Execution & Time-Travel:** Backed by a **PostgreSQL checkpointer**, every graph super-step is serialized against a `thread_id`, supporting fault-tolerant session recovery, multi-turn conversational continuity, and deterministic state inspection.
- **Human-in-the-Loop (HITL) Gates:** Critical state transitions pause execution via LangGraph `interrupt` primitives, surfacing proposed itineraries, flight selections, or budget allocations to the web UI for explicit human approval, modification, or rejection before resuming graph execution.

---

## Core Agentic Capabilities

| Component | Architectural Role | Key Mechanisms |
| :--- | :--- | :--- |
| **Supervisor Agent** | Central planner & router | Structured output routing, task decomposition, termination condition verification, context synthesis |
| **Flight & Transit Agent** | Logistics & fare retrieval | MCP-bound flight search tool integration, route filtering, schedule & pricing normalization |
| **Destination & Research Agent** | Real-time local intelligence | Tavily search tool integration, venue/attraction grounding, seasonal & advisory synthesis |
| **Guardrail Layer** | Input/output policy enforcement | Prompt-injection screening, off-topic/unsafe request deflection, schema & hallucination validation |
| **PostgreSQL Checkpointer** | Durable state & thread memory | Thread-scoped state snapshots, interrupt state serialization, cross-session resume |
| **Web Application (`app.py`)** | Interactive HITL & streaming UI | Server-rendered templates (`templates/`), static assets (`static/`), session thread management |

---

## System Topology & Control Flow

```mermaid
graph TD
    User([User Query / Web UI]) --> GuardIn[Input Safety Guardrail]
    GuardIn -->|Blocked / Policy Violation| Reject([Safe Refusal Response])
    GuardIn -->|Validated| Supervisor{Supervisor Agent}

    Supervisor -->|Delegate: Flights| FlightAgent[Flight & Transit Worker]
    Supervisor -->|Delegate: Research| ResearchAgent[Destination & Tavily Worker]
    Supervisor -->|Ready for Review| HITL[[HITL Interrupt Gate]]

    FlightAgent <-->|MCP Tool Calls| MCPTools[(MCP Tool Servers & tools/)]
    ResearchAgent <-->|MCP Tool Calls| MCPTools

    FlightAgent --> Supervisor
    ResearchAgent --> Supervisor

    HITL -->|User Feedback / Edits| Supervisor
    HITL -->|Approved| GuardOut[Output Safety & Grounding Guardrail]
    GuardOut --> Final([Final Verified Itinerary])

    Supervisor -.->|State Snapshots| PG[(PostgreSQL Checkpointer)]
    HITL -.->|Checkpoint Resume| PG
