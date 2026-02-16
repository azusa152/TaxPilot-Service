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
page = st.sidebar.radio("Navigation", ["Algorithm Registry", "LLM Configuration", "System Health"])


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
            response = client.put(path)
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
