# TaxPilot Service — Design Documents Index

This directory contains all technical design documents organized by feature.

---

## Cross-Cutting Architecture

| Document | Description |
|----------|-------------|
| [TechDesign_Master.md](TechDesign_Master.md) | System architecture, data model, API surface, tech stack, and phase dependency graph |

---

## Core Service (Phases 1–5)

The foundational backend: project scaffold, data models, CRUD API, document ingestion, and tax calculation engine.

| Phase | Document | Description |
|-------|----------|-------------|
| 1 | [Phase1_Scaffold.md](core-service/Phase1_Scaffold.md) | Project scaffold, Docker Compose, FastAPI entrypoint, config |
| 2 | [Phase2_DataModels.md](core-service/Phase2_DataModels.md) | SQLAlchemy models, Alembic migrations, JSONB adaptive schema |
| 3 | [Phase3_CrudApi.md](core-service/Phase3_CrudApi.md) | CRUD endpoints for Users, IncomeEntries, TaxProfiles, ProfileDefinition |
| 4 | [Phase4_Ingestion.md](core-service/Phase4_Ingestion.md) | Document ingestion via MarkItDown (PDF, Excel, Images to Markdown) |
| 5 | [Phase5_TaxEngine.md](core-service/Phase5_TaxEngine.md) | Deterministic tax calculation functions, AlgorithmRegistry, calculation endpoint |

---

## Frontend

| Document | Description |
|----------|-------------|
| [Frontend.md](frontend/Frontend.md) | Next.js Reference UI design — i18n, income management, tax profile, file upload |

---

## Evolution Loop (Phase 6)

The self-evolving capability: NTA regulation monitoring, LLM-assisted code generation, admin review and approval, email notifications.

| Phase | Document | Description |
|-------|----------|-------------|
| Overview | [Overview.md](evolution-loop/Overview.md) | Master overview, system diagram, security design, technology choices, example walkthrough |
| 6A | [Phase6A_LlmGateway.md](evolution-loop/Phase6A_LlmGateway.md) | Multi-provider LLM integration via LiteLLM, encrypted token management, cost tracking |
| 6B | [Phase6B_NtaCrawler.md](evolution-loop/Phase6B_NtaCrawler.md) | NTA page crawler via Crawl4AI, persistent markdown storage, admin monitoring dashboard |
| 6C | [Phase6C_RegulationParser.md](evolution-loop/Phase6C_RegulationParser.md) | LLM-based parsing of NTA content into structured law change descriptions |
| 6D | [Phase6D_CodeSchemaGenerator.md](evolution-loop/Phase6D_CodeSchemaGenerator.md) | Algorithm code generation + ProfileDefinition schema generation with RestrictedPython sandboxing |
| 6-Pre | [Phase6-Pre_Bootstrap.md](evolution-loop/Phase6-Pre_Bootstrap.md) | Cold start: seed AlgorithmRegistry, baseline NTA crawl, LLM verification of existing formulas |
| 6E | [Phase6E_PipelineAndReview.md](evolution-loop/Phase6E_PipelineAndReview.md) | End-to-end pipeline orchestration, 4-option admin approval flow, audit trail, rollback |
| 6F | [Phase6F_Notifications.md](evolution-loop/Phase6F_Notifications.md) | Email notification system (SMTP), pluggable interface, notification triggers |
| Legacy | [Phase6_Legacy.md](evolution-loop/Phase6_Legacy.md) | Original Phase 6 skeleton (archived, superseded by the above documents) |

---

## Phase Dependency Graph

```
Phase 1 → Phase 2 → Phase 3 → Phase 4
                         ↓
                    Phase 5
                    ↓    ↓
    Phase 6A (LLM)    Phase 6B (Crawler)
         ↓    ↓              ↓
         ↓    +------+-------+
         ↓           ↓
         ↓    Phase 6-Pre (Bootstrap)    ← depends on 6A + 6B
         ↓           ↓
         +------+----+
                ↓
    Phase 6C (Regulation Parser)         ← depends on 6A
                ↓
    Phase 6D (Code & Schema Generator)   ← depends on 6A + 6C
                ↓
    Phase 6E (Pipeline & Review)         ← depends on 6-Pre + 6B + 6C + 6D
                ↓
    Phase 6F (Email Notifications)       ← depends on 6E
```
