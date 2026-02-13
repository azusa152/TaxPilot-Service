"""TaxPilot Dashboard — Streamlit entry point."""

import os

import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

st.set_page_config(page_title="TaxPilot Dashboard", page_icon="📊", layout="wide")

st.title("TaxPilot Dashboard")


def check_backend_health() -> dict | None:
    """Call the backend health endpoint.

    Returns:
        Health response dict, or None if the backend is unreachable.
    """
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=5.0)
        response.raise_for_status()
        return response.json()
    except (httpx.RequestError, httpx.HTTPStatusError):
        return None


st.subheader("System Status")

health = check_backend_health()

if health and health.get("status") == "healthy":
    st.success(f"Backend: {health['status']} | Database: {health['database']}")
else:
    st.error("Backend is unreachable. Ensure the API service is running.")
