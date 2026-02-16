"""TaxPilot Admin Dashboard.

Streamlit app for reviewing and approving algorithm changes.
Run with: streamlit run admin/app.py
"""
import os

import httpx
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="TaxPilot Admin", layout="wide")
st.title("TaxPilot Admin Dashboard")


# --- Sidebar: Navigation ---
page = st.sidebar.radio(
    "Navigation", ["Algorithm Registry", "LLM Configuration", "Crawler Monitor", "System Health"]
)


def fetch_json(path: str):
    with httpx.Client(base_url=API_BASE, timeout=10.0) as client:
        response = client.get(path)
        response.raise_for_status()
        return response.json()


def put_json(path: str, json_data: dict | None = None):
    with httpx.Client(base_url=API_BASE, timeout=10.0) as client:
        response = client.put(path, json=json_data)
        response.raise_for_status()
        return response.json()


def post_json(path: str, json_data: dict | None = None):
    with httpx.Client(base_url=API_BASE, timeout=10.0) as client:
        if json_data:
            response = client.post(path, json=json_data)
        else:
            response = client.post(path)
        response.raise_for_status()
        return response.json()


if page == "System Health":
    st.header("System Health")
    try:
        health = fetch_json("/health")
        col1, col2 = st.columns(2)
        col1.metric("API Status", health.get("status", "unknown"))
        col2.metric("Database", health.get("database", "unknown"))
    except Exception as e:
        st.error(f"Failed to fetch health: {e}")


elif page == "Algorithm Registry":
    st.header("Algorithm Registry")

    try:
        algorithms = fetch_json("/algorithms")

        if not algorithms:
            st.info("No algorithms registered yet.")
        else:
            for status in ["DRAFT", "ACTIVE", "ARCHIVED"]:
                group = [a for a in algorithms if a["status"] == status]
                if group:
                    st.subheader(f"{status} ({len(group)})")
                    for algo in group:
                        with st.expander(f"{algo['function_name']} v{algo['version']}"):
                            st.json(algo)

                            if algo["status"] == "DRAFT":
                                if st.button("Activate", key=f"activate_{algo['id']}"):
                                    try:
                                        result = post_json(f"/algorithms/{algo['id']}/activate")
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
                    result = post_json(
                        "/algorithms",
                        {
                            "function_name": func_name,
                            "version": version,
                            "code_content": code,
                            "source_law_hash": law_hash or None,
                        },
                    )
                    st.success(f"Registered {result['function_name']} v{result['version']} as DRAFT")
                    st.rerun()
                except Exception as e:
                    st.error(f"Registration failed: {e}")
            else:
                st.warning("Please fill in Function Name, Version, and Code.")


elif page == "LLM Configuration":
    st.header("LLM Configuration")

    # --- Current Config ---
    st.subheader("Current Provider")
    try:
        config = fetch_json("/admin/llm/config")
        if config:
            col1, col2, col3 = st.columns(3)
            col1.metric("Provider", config["provider"])
            col2.metric("Model", config["model_name"])
            col3.metric("Active", "Yes" if config["is_active"] else "No")
            st.text(f"Token: {config['masked_token']}")
            st.text(f"Monthly Budget: ${config['monthly_budget_usd']:.2f}")
        else:
            st.info("No LLM provider configured. Set one below.")
    except Exception as e:
        st.error(f"Failed to fetch config: {e}")

    # --- Update Config ---
    st.divider()
    st.subheader("Update Provider")

    MODEL_SUGGESTIONS = {
        "gemini": ["gemini/gemini-2.0-flash", "gemini/gemini-1.5-pro"],
        "openai": ["openai/gpt-4o", "openai/gpt-4-turbo"],
        "anthropic": ["anthropic/claude-3-5-sonnet-20241022", "anthropic/claude-3-haiku-20240307"],
    }

    with st.form("llm_config"):
        provider = st.selectbox("Provider", ["openai", "gemini", "anthropic"])
        suggestions = MODEL_SUGGESTIONS.get(provider, [])
        model_name = st.selectbox("Model", suggestions) if suggestions else st.text_input("Model String")
        api_token = st.text_input("API Token", type="password")
        budget = st.number_input("Monthly Budget (USD)", min_value=1.0, max_value=10000.0, value=50.0, step=10.0)

        if st.form_submit_button("Save Configuration"):
            if api_token:
                try:
                    result = put_json(
                        "/admin/llm/config",
                        {
                            "provider": provider,
                            "model_name": model_name,
                            "api_token": api_token,
                            "monthly_budget_usd": budget,
                        },
                    )
                    st.success(f"Saved: {result['provider']} / {result['model_name']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save config: {e}")
            else:
                st.warning("Please enter an API token.")

    # --- Test Connection ---
    st.divider()
    st.subheader("Test Connection")
    if st.button("Test LLM Connection"):
        with st.spinner("Testing..."):
            try:
                with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
                    response = client.post("/admin/llm/test")
                    response.raise_for_status()
                    result = response.json()
                st.success(f"Status: {result['status']}")
                col1, col2 = st.columns(2)
                col1.metric("Model", result["model"])
                col2.metric("Latency", f"{result['latency_seconds']}s")
                st.text(f"Response: {result['response']}")
            except Exception as e:
                st.error(f"Connection test failed: {e}")

    # --- Usage Dashboard ---
    st.divider()
    st.subheader("Usage Dashboard")
    try:
        usage = fetch_json("/admin/llm/usage")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Calls", usage["total_calls"])
        col2.metric("Monthly Cost", f"${usage['monthly_total_usd']:.4f}")
        col3.metric("Budget Remaining", f"${usage['budget_remaining_usd']:.2f}")

        st.text(f"Prompt tokens: {usage['total_prompt_tokens']:,}")
        st.text(f"Completion tokens: {usage['total_completion_tokens']:,}")

        if usage["daily_breakdown"]:
            st.bar_chart(
                data={row["date"]: row["cost_usd"] for row in usage["daily_breakdown"]},
            )
    except Exception as e:
        st.error(f"Failed to fetch usage: {e}")


elif page == "Crawler Monitor":
    st.header("NTA Crawler Monitor")

    # --- 1. Health Overview ---
    st.subheader("Health Overview")
    try:
        health = fetch_json("/admin/nta/health")
        status = health["status"]
        status_color = {"healthy": "green", "degraded": "orange", "error": "red"}.get(status, "gray")
        status_emoji = {"healthy": "OK", "degraded": "WARN", "error": "ERR"}.get(status, "?")

        col1, col2, col3 = st.columns(3)
        col1.metric("Status", status_emoji)
        col2.metric("Active Pages", f"{health['active_target_pages']} / {health['total_target_pages']}")

        if health["last_run"]:
            last = health["last_run"]
            col3.metric(
                "Last Run",
                f"{last['pages_checked']} checked, {last['pages_changed']} changed",
            )
            st.text(f"Last run: {last['started_at']} ({last['trigger']})")
            if last["pages_failed"] > 0:
                st.warning(f"{last['pages_failed']} page(s) failed in last run")
        else:
            col3.metric("Last Run", "Never")
            st.info("No crawl runs yet. Click 'Run Now' to start.")

    except Exception as e:
        st.error(f"Failed to fetch crawler health: {e}")

    # Run Now button
    if st.button("Run Now"):
        with st.spinner("Crawling NTA pages..."):
            try:
                changes = post_json("/admin/nta/check-now")
                if changes:
                    st.success(f"Crawl complete: {len(changes)} change(s) detected!")
                    for change in changes:
                        st.write(f"- **{change['page_name']}**: hash changed to `{change['new_hash'][:12]}...`")
                else:
                    st.success("Crawl complete: no changes detected.")
                st.rerun()
            except Exception as e:
                st.error(f"Crawl failed: {e}")

    # --- 2. Target Pages Management ---
    st.divider()
    st.subheader("Target Pages")

    try:
        targets = fetch_json("/admin/nta/targets")
        if targets:
            for target in targets:
                status_label = "Active" if target["is_active"] else "Disabled"
                with st.expander(f"{target['name']} ({status_label})"):
                    st.text(f"URL: {target['url']}")
                    st.text(f"Description: {target.get('description', 'N/A')}")
                    st.text(f"Check interval: {target['check_interval_hours']}h")
        else:
            st.info("No target pages configured. Add one below.")
    except Exception as e:
        st.error(f"Failed to fetch targets: {e}")

    # Add new target page
    st.divider()
    st.subheader("Add / Update Target Page")
    with st.form("add_target"):
        name = st.text_input("Page Name", placeholder="income_tax_rates")
        url = st.text_input("URL", placeholder="https://www.nta.go.jp/...")
        description = st.text_input("Description", placeholder="Income tax rate table")
        check_interval = st.number_input("Check Interval (hours)", min_value=1, max_value=720, value=24)
        is_active = st.checkbox("Active", value=True)

        if st.form_submit_button("Save Target Page"):
            if name and url:
                try:
                    result = put_json(
                        "/admin/nta/targets",
                        {
                            "name": name,
                            "url": url,
                            "description": description or None,
                            "check_interval_hours": check_interval,
                            "is_active": is_active,
                        },
                    )
                    st.success(f"Saved target page: {result['name']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save target: {e}")
            else:
                st.warning("Please fill in Page Name and URL.")

    # --- 3. Snapshot History ---
    st.divider()
    st.subheader("Snapshot History")

    col1, col2 = st.columns(2)
    filter_page = col1.text_input("Filter by page name", placeholder="(all pages)")
    changes_only = col2.checkbox("Changes only")

    try:
        params = "?"
        if filter_page:
            params += f"page_name={filter_page}&"
        if changes_only:
            params += "changes_only=true&"
        params += "limit=50"

        snapshots = fetch_json(f"/admin/nta/snapshots{params}")

        if snapshots:
            for snap in snapshots:
                status_icon = {"SUCCESS": "OK", "FAILED": "FAIL", "TIMEOUT": "TIMEOUT"}.get(
                    snap["status"], "?"
                )
                label = f"{snap['target_page_name']} | {snap['fetched_at']} | {status_icon}"
                if snap["response_time_ms"]:
                    label += f" | {snap['response_time_ms']}ms"

                with st.expander(label):
                    st.text(f"Hash: {snap['content_hash']}")
                    st.text(f"URL: {snap['target_page_url']}")

                    if snap.get("error_message"):
                        st.error(f"Error: {snap['error_message']}")

                    if snap.get("fit_markdown"):
                        tab1, tab2 = st.tabs(["Rendered Markdown", "Raw (copyable)"])
                        with tab1:
                            st.markdown(snap["fit_markdown"][:5000])
                        with tab2:
                            st.code(snap["fit_markdown"], language="markdown")

                    if snap.get("extracted_tables"):
                        st.subheader("Extracted Tables")
                        st.json(snap["extracted_tables"])
        else:
            st.info("No snapshots yet.")
    except Exception as e:
        st.error(f"Failed to fetch snapshots: {e}")

    # --- 4. Crawl Run Log ---
    st.divider()
    st.subheader("Crawl Run Log")

    try:
        runs = fetch_json("/admin/nta/runs")
        if runs:
            for run in runs:
                duration = ""
                if run.get("completed_at") and run.get("started_at"):
                    duration = f" | completed: {run['completed_at']}"

                label = (
                    f"{run['trigger']} | {run['started_at']}{duration} | "
                    f"checked={run['pages_checked']}, changed={run['pages_changed']}, "
                    f"failed={run['pages_failed']}"
                )
                st.text(label)
        else:
            st.info("No crawl runs yet.")
    except Exception as e:
        st.error(f"Failed to fetch runs: {e}")

    # --- 5. Error Log ---
    st.divider()
    st.subheader("Error Log")

    try:
        # Fetch all snapshots and filter to failed/timed out
        error_snapshots = fetch_json("/admin/nta/snapshots?limit=100")
        errors = [s for s in error_snapshots if s["status"] in ("FAILED", "TIMEOUT")]

        if errors:
            for err in errors:
                st.error(
                    f"**{err['target_page_name']}** ({err['status']}) - {err['fetched_at']}\n\n"
                    f"URL: {err['target_page_url']}\n\n"
                    f"Error: {err.get('error_message', 'N/A')}"
                )
        else:
            st.success("No errors in recent snapshots.")
    except Exception as e:
        st.error(f"Failed to fetch error log: {e}")
