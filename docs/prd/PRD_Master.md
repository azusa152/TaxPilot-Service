# TaxPilot Service - Core Architecture & Data Specifications
**Version:** 2.1 (Updated with MarkItDown)
**Type:** Master Design Document

## 1. Product Vision
TaxPilot is a **Self-Evolving, Agent-First Backend Service** for Japanese tax calculation.
It serves as a deterministic "Tax Logic Engine" for external AI Agents (like OpenClaw) and human users via a Reference UI.

**Core Pillars:**
1.  **Deterministic Calculation:** Tax logic is implemented in pure Python (not LLM generation) for accuracy.
2.  **Adaptive Schema:** The system handles new tax laws (e.g., "Fixed Tax Cut") by dynamically expanding data requirements via JSON fields.
3.  **Law-Code Traceability:** Every calculation logic is versioned and linked to specific NTA (National Tax Agency) regulations.
4.  **Universal Ingestion:** The system ingests various financial documents (PDF, Excel, Images) and converts them into structured Markdown for Agent processing.

## 2. System Architecture
The system follows a **Service-Oriented Architecture (SOA)** with a **Dual-Loop** design:

### A. Service Loop (Fast & Stable)
* **Ingestion Layer:** Uses **Microsoft MarkItDown** to convert raw files (salary slips, transaction logs) into LLM-friendly Markdown text, preserving table structures.
* **Interface:** FastAPI (REST/OpenAPI). The *only* entry point for Agents and UI.
* **Logic:** Executes active Python algorithms.
* **Data:** PostgreSQL (Async) for relational data + JSONB for dynamic attributes.

### B. Evolution Loop (Slow & Safe)
* **Monitor:** Crawlers check NTA websites for updates.
* **Generate:** LLMs generate Python code patches and Schema definitions.
* **Approve:** Admin reviews changes via a Streamlit Dashboard before hot-reloading.

## 3. Data Dictionary (Entity Relationship)

### User Core
* **User:** The root entity.
    * `id` (UUID): Primary Key.
    * `display_name` (Str).

### Financial Data (Transaction Stream)
* **IncomeEntry:** Monthly financial records.
    * `type`: Salary / Bonus / Other.
    * `amount`: Gross income.
    * `deductions`: Social Insurance, Withholding Tax, Resident Tax.
    * `source_file`: Path to the raw uploaded file.
    * `raw_content`: **Markdown text** extracted by MarkItDown (for audit or re-parsing).

### Tax Configuration (Hybrid Schema)
* **TaxProfile:** Annual tax settings.
    * **Core Fields (SQL Columns):** Stable fields like `has_spouse`, `dependents_count`, `ideco_contribution`.
    * **Dynamic Fields (JSONB):** Adaptive fields like `{"fixed_tax_cut_eligible": true, "gpu_deduction": 30000}`.
* **ProfileDefinition:** Metadata defining *what* fields are required for a specific year.
    * `schema_json`: Defines the structure for the UI/Agent to render inputs.

### System Evolution
* **AlgorithmRegistry:** Stores the logic.
    * `function_name`: e.g., "calc_furusato_limit".
    * `code_content`: The actual Python source code.
    * `source_law_hash`: For change detection.

## 4. Technical Stack Constraints
* **Language:** Python 3.11+.
* **Web Framework:** FastAPI (Async).
* **Ingestion:** **microsoft/markitdown** (Native Markdown conversion for PDF/Images/Office docs).
* **Database:** PostgreSQL (Preferred for JSONB support) or SQLite (for local MVP). Use **SQLAlchemy (Async)**.
* **Validation:** Pydantic v2.
* **Migration:** Alembic.
* **Containerization:** Docker Compose.

## 5. API Design Principles
* **Schema Discovery:** Endpoints like `GET /profile/definition` allow Agents to learn what data to collect.
* **Semantic Errors:** Return actionable error messages (e.g., "Missing field: spouse_income") instead of generic 400s.