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
page = st.sidebar.radio("Navigation", ["Algorithm Registry", "System Health"])


def fetch_json(path: str):
    with httpx.Client(base_url=API_BASE, timeout=10.0) as client:
        response = client.get(path)
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
