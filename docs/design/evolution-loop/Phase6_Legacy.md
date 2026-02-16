# Phase 6: Evolution Loop & Admin Dashboard
**Goal:** Implement the self-evolving capability: NTA law change monitoring, LLM-assisted code generation, admin review/approval via Streamlit, and hot-reloading of active algorithms.

**Depends on:** Phase 5 (AlgorithmRegistry CRUD and activation must be working)
**Produces:** NTA crawler skeleton, LLM code generation pipeline, Streamlit admin dashboard, algorithm hot-reload

---

## Context

This is the **Evolution Loop** — the slow, safe, admin-gated system that keeps TaxPilot up-to-date with Japanese tax law changes. Unlike the Service Loop (Phases 1-5), this loop is not user-facing; it runs in the background and surfaces changes for human review.

**Flow:**

```
NTA Website ──► Crawler (detect change) ──► LLM (generate code patch)
                                                    │
                                              AlgorithmRegistry (DRAFT)
                                                    │
                                            Admin Dashboard (Streamlit)
                                                    │
                                        ┌───────────┴───────────┐
                                    Approve                  Reject
                                        │                       │
                                  Activate (ACTIVE)       Archive (ARCHIVED)
                                        │
                                  Hot-Reload into Service Loop
```

**Important:** This phase is more experimental than Phases 1-5. The crawler and LLM pipeline are skeletons that will be refined iteratively.

---

## Tasks

### Task 6.1: NTA Law Change Monitor (Crawler Skeleton)

**File:** `backend/src/infrastructure/nta_monitor.py`

This is a skeleton that will be enhanced over time. The initial version:
- Fetches a target NTA page
- Hashes the content
- Compares with previous hash to detect changes
- Logs when a change is detected

```python
"""NTA (National Tax Agency) law change monitor.

Skeleton implementation. Checks a target URL for content changes
by comparing content hashes.
"""
import hashlib

import httpx

from src.logging_config import get_logger

logger = get_logger(__name__)

# Target pages to monitor (expand as needed)
NTA_TARGETS = [
    {
        "name": "income_tax_rates",
        "url": "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        "description": "Income tax rate table",
    },
    {
        "name": "salary_deduction",
        "url": "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm",
        "description": "Salary income deduction table",
    },
]


class NtaMonitor:
    """Monitors NTA website pages for content changes."""

    def __init__(self):
        self._known_hashes: dict[str, str] = {}

    async def check_for_changes(self) -> list[dict]:
        """Check all target pages for changes.

        Returns:
            List of dicts with 'name', 'url', and 'new_hash' for pages that changed.
        """
        changes = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for target in NTA_TARGETS:
                try:
                    response = await client.get(target["url"])
                    response.raise_for_status()
                    content_hash = hashlib.sha256(response.content).hexdigest()

                    previous_hash = self._known_hashes.get(target["name"])
                    if previous_hash is not None and previous_hash != content_hash:
                        logger.warning(
                            f"NTA change detected: {target['name']} ({target['description']})"
                        )
                        changes.append({
                            "name": target["name"],
                            "url": target["url"],
                            "previous_hash": previous_hash,
                            "new_hash": content_hash,
                        })

                    self._known_hashes[target["name"]] = content_hash

                except Exception as e:
                    logger.error(f"Failed to check NTA page '{target['name']}': {e}")

        return changes

    def get_known_hashes(self) -> dict[str, str]:
        """Return current known hashes for all monitored pages."""
        return dict(self._known_hashes)
```

**Future enhancements:**
- Persist hashes in the database (not in-memory)
- Schedule periodic checks via APScheduler or a cron job
- Parse the changed content to identify specific law updates
- Integrate with the LLM pipeline to auto-generate patches

### Task 6.2: LLM Code Generation Pipeline (Skeleton)

**File:** `backend/src/infrastructure/code_generator.py`

This skeleton defines the interface for LLM-assisted code generation. The actual LLM call is stubbed — it will be connected to an LLM API (OpenAI, Anthropic, etc.) in a future iteration.

```python
"""LLM-assisted code generation for tax calculation patches.

Skeleton implementation. Generates Python code patches from
law change descriptions using an LLM.
"""
from dataclasses import dataclass

from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CodePatch:
    """A generated code patch for a tax calculation function."""
    function_name: str
    version: str
    code_content: str
    source_law_hash: str
    description: str


class CodeGenerator:
    """Generates Python code patches from law change descriptions."""

    async def generate_patch(
        self,
        function_name: str,
        current_code: str,
        change_description: str,
        source_law_hash: str,
    ) -> CodePatch:
        """Generate a code patch based on a law change description.

        Args:
            function_name: Name of the function to patch.
            current_code: Current Python source code of the function.
            change_description: Natural language description of the law change.
            source_law_hash: Hash of the new law text.

        Returns:
            CodePatch with the generated code.
        """
        # STUB: In production, this calls an LLM API with a structured prompt
        # containing the current code and change description.
        logger.info(f"Generating code patch for '{function_name}' based on: {change_description}")

        # For now, return the current code unchanged with a bumped version
        return CodePatch(
            function_name=function_name,
            version="auto-generated",
            code_content=current_code,  # Placeholder — LLM would modify this
            source_law_hash=source_law_hash,
            description=f"Auto-generated patch: {change_description}",
        )

    def build_prompt(self, function_name: str, current_code: str, change_description: str) -> str:
        """Build the LLM prompt for code generation.

        This is exposed for testing and debugging the prompt template.
        """
        return f"""You are a Japanese tax calculation expert and Python developer.

The following Python function calculates {function_name}:

```python
{current_code}
```

The National Tax Agency has published the following change:
{change_description}

Generate an updated version of this function that incorporates the new rules.
Requirements:
- Keep the function signature identical.
- All amounts in JPY (integers).
- Include comments referencing the specific NTA regulation.
- The function must be pure (no side effects, no external dependencies).

Return ONLY the Python function code, no explanation.
"""
```

### Task 6.3: Algorithm Hot-Reload (Infrastructure Layer)

**File:** `backend/src/infrastructure/algorithm_loader.py`

Loads and executes active algorithms from the registry. This enables the Evolution Loop to update calculations without redeploying the service.

```python
"""Algorithm hot-loader.

Loads active algorithm code from the AlgorithmRegistry and
makes it callable at runtime.
"""
import types
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.models import AlgorithmRegistry
from src.logging_config import get_logger

logger = get_logger(__name__)


class AlgorithmLoader:
    """Loads and caches active algorithms from the registry."""

    def __init__(self):
        self._cache: dict[str, Callable] = {}

    async def load_active_algorithms(self, db: AsyncSession) -> dict[str, Callable]:
        """Load all ACTIVE algorithms from the registry.

        Returns:
            Dict mapping function_name to callable function.
        """
        result = await db.execute(
            select(AlgorithmRegistry).where(AlgorithmRegistry.status == "ACTIVE")
        )
        algorithms = result.scalars().all()

        loaded = {}
        for algo in algorithms:
            try:
                fn = self._compile_function(algo.function_name, algo.code_content)
                loaded[algo.function_name] = fn
                logger.info(f"Loaded algorithm '{algo.function_name}' v{algo.version}")
            except Exception as e:
                logger.error(f"Failed to compile algorithm '{algo.function_name}' v{algo.version}: {e}")

        self._cache = loaded
        return loaded

    def get_function(self, function_name: str) -> Callable | None:
        """Get a loaded function by name from the cache."""
        return self._cache.get(function_name)

    def _compile_function(self, function_name: str, code_content: str) -> Callable:
        """Compile Python source code into a callable function.

        WARNING: This executes arbitrary code. Only use with admin-approved code
        from the AlgorithmRegistry.
        """
        module = types.ModuleType(f"taxpilot_algo_{function_name}")
        exec(code_content, module.__dict__)  # noqa: S102 — intentional dynamic execution

        fn = getattr(module, function_name, None)
        if fn is None or not callable(fn):
            raise ValueError(
                f"Code for '{function_name}' does not define a callable with that name."
            )
        return fn
```

**Security note:** `exec()` is intentionally used here because the Evolution Loop's entire purpose is dynamic code loading. The admin approval gate (Task 6.4) is the security boundary.

### Task 6.4: Streamlit Admin Dashboard

**File:** `admin/app.py`

A separate Streamlit app for admin review of algorithm changes.

```python
"""TaxPilot Admin Dashboard.

Streamlit app for reviewing and approving algorithm changes.
Run with: streamlit run admin/app.py
"""
import asyncio

import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="TaxPilot Admin", layout="wide")
st.title("TaxPilot Admin Dashboard")


# --- Sidebar: Navigation ---
page = st.sidebar.radio("Navigation", ["Algorithm Registry", "System Health"])


async def fetch_json(path: str):
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        response = await client.get(path)
        response.raise_for_status()
        return response.json()


async def post_json(path: str, json_data: dict | None = None):
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        if json_data:
            response = await client.post(path, json=json_data)
        else:
            response = await client.put(path)
        response.raise_for_status()
        return response.json()


if page == "System Health":
    st.header("System Health")
    try:
        health = asyncio.run(fetch_json("/health"))
        col1, col2 = st.columns(2)
        col1.metric("API Status", health.get("status", "unknown"))
        col2.metric("Database", health.get("database", "unknown"))
    except Exception as e:
        st.error(f"Failed to fetch health: {e}")


elif page == "Algorithm Registry":
    st.header("Algorithm Registry")

    try:
        algorithms = asyncio.run(fetch_json("/algorithms"))

        if not algorithms:
            st.info("No algorithms registered yet.")
        else:
            # Group by status
            for status in ["DRAFT", "ACTIVE", "ARCHIVED"]:
                group = [a for a in algorithms if a["status"] == status]
                if group:
                    st.subheader(f"{status} ({len(group)})")
                    for algo in group:
                        with st.expander(f"{algo['function_name']} v{algo['version']}"):
                            st.json(algo)

                            if algo["status"] == "DRAFT":
                                if st.button(f"Activate", key=f"activate_{algo['id']}"):
                                    try:
                                        result = asyncio.run(
                                            post_json(f"/algorithms/{algo['id']}/activate")
                                        )
                                        st.success(
                                            f"Activated {result['function_name']} v{result['version']}"
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Activation failed: {e}")

    except Exception as e:
        st.error(f"Failed to fetch algorithms: {e}")

    # Register new algorithm
    st.divider()
    st.subheader("Register New Algorithm")
    with st.form("register_algorithm"):
        func_name = st.text_input("Function Name", placeholder="calc_furusato_limit")
        version = st.text_input("Version", placeholder="2025.1")
        code = st.text_area("Python Code", height=300, placeholder="def calc_furusato_limit(...):\n    ...")
        law_hash = st.text_input("Source Law Hash (optional)", placeholder="sha256 of NTA page")

        if st.form_submit_button("Register as DRAFT"):
            if func_name and version and code:
                try:
                    result = asyncio.run(post_json("/algorithms", {
                        "function_name": func_name,
                        "version": version,
                        "code_content": code,
                        "source_law_hash": law_hash or None,
                    }))
                    st.success(f"Registered {result['function_name']} v{result['version']} as DRAFT")
                    st.rerun()
                except Exception as e:
                    st.error(f"Registration failed: {e}")
            else:
                st.warning("Please fill in Function Name, Version, and Code.")
```

**File:** `admin/requirements.txt`

```
streamlit>=1.35.0
httpx>=0.27.0
```

### Task 6.5: Docker Compose Update for Admin

Add the Streamlit admin service to `docker-compose.yml`:

```yaml
  admin:
    build:
      context: ./admin
      dockerfile: Dockerfile
    ports:
      - "8501:8501"
    depends_on:
      - api
    environment:
      - API_BASE=http://api:8000
```

**File:** `admin/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Task 6.6: Tests

**File:** `backend/tests/infrastructure/test_nta_monitor.py`

```python
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.nta_monitor import NtaMonitor


@patch("src.infrastructure.nta_monitor.httpx.AsyncClient")
async def test_check_for_changes_first_run_should_return_no_changes(mock_client_class):
    mock_response = AsyncMock()
    mock_response.content = b"<html>tax rates page</html>"
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_class.return_value = mock_client

    monitor = NtaMonitor()
    changes = await monitor.check_for_changes()

    # First run: no previous hash, so no changes detected
    assert changes == []
    assert len(monitor.get_known_hashes()) > 0
```

**File:** `backend/tests/infrastructure/test_algorithm_loader.py`

```python
from src.infrastructure.algorithm_loader import AlgorithmLoader


def test_compile_function_should_return_callable():
    loader = AlgorithmLoader()
    code = "def calc_test(x):\n    return x * 2\n"
    fn = loader._compile_function("calc_test", code)
    assert fn(5) == 10


def test_compile_function_missing_name_should_raise():
    loader = AlgorithmLoader()
    code = "def wrong_name(x):\n    return x\n"
    try:
        loader._compile_function("calc_test", code)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "calc_test" in str(e)
```

---

## Acceptance Criteria

1. `NtaMonitor.check_for_changes()` can detect when a target page's content hash changes.
2. `CodeGenerator.generate_patch()` returns a `CodePatch` (stub implementation is acceptable).
3. `CodeGenerator.build_prompt()` produces a structured LLM prompt with current code and change description.
4. `AlgorithmLoader` can compile and execute Python code from the registry.
5. Streamlit admin dashboard at `http://localhost:8501` shows:
   - System health status
   - Algorithm registry grouped by status (DRAFT / ACTIVE / ARCHIVED)
   - Ability to activate DRAFT algorithms
   - Form to register new algorithms
6. Activating an algorithm via the dashboard archives the previous active version.
7. `make test` passes all Evolution Loop tests.

---

## Security Considerations

- **Code execution:** `AlgorithmLoader._compile_function()` uses `exec()`. This is intentional but must only process admin-approved code from the AlgorithmRegistry.
- **Admin access:** The Streamlit dashboard should be restricted to admin users in production (authentication not in scope for MVP).
- **NTA crawling:** Respect rate limits and `robots.txt` when monitoring NTA pages.
