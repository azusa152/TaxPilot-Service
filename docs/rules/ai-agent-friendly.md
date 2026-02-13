# AI Agent Interaction Standards

## Core Philosophy
We are building a backend *for Agents*, not humans.
The API must be self-documenting and error-tolerant for LLMs.

## Rules
1.  **Semantic Error Messages:**
    -   ❌ `400 Bad Request`
    -   ✅ `400: Missing 'spouse_income' field. Required when 'has_spouse' is true.`
2.  **Schema Discovery:**
    -   Always expose `GET /.../definition` or `OPTIONS` endpoints so Agents can learn input requirements dynamically.
3.  **Atomic Tools:**
    -   Each API endpoint should do *one* thing well. Avoid complex multi-step workflows in a single endpoint.
4.  **Statelessness:**
    -   Do not assume the Agent remembers previous requests. Every request should contain necessary context (or ID).
5.  **Pydantic v2:**
    -   Use `Field(description="...")` extensively. This description is what the Agent reads to understand the parameter.