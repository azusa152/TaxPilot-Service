"""TaxPilot Admin Dashboard.

Streamlit app for reviewing and approving algorithm changes.
Run with: streamlit run admin/app.py
"""
import os
import time

import httpx
import streamlit as st

from i18n import load_translations, t, SUPPORTED_LOCALES

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="TaxPilot Admin", layout="wide")

# Language selector in sidebar
if "locale" not in st.session_state:
    st.session_state["locale"] = "en"

locale = st.sidebar.selectbox(
    "🌐 Language",
    SUPPORTED_LOCALES,
    index=SUPPORTED_LOCALES.index(st.session_state["locale"]),
    key="locale_selector",
)
st.session_state["locale"] = locale
tr = load_translations(locale)

st.title(t(tr, "app.title"))


# --- Sidebar: Navigation ---
page = st.sidebar.radio(
    t(tr, "app.nav"),
    [
        t(tr, "pages.systemHealth"),
        t(tr, "pages.algorithmRegistry"),
        t(tr, "pages.llmConfiguration"),
        t(tr, "pages.crawlerMonitor"),
    ],
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


if page == t(tr, "pages.systemHealth"):
    st.header(t(tr, "health.title"))
    try:
        health = fetch_json("/health")
        col1, col2 = st.columns(2)
        col1.metric(t(tr, "health.apiStatus"), health.get("status", "unknown"))
        col2.metric(t(tr, "health.database"), health.get("database", "unknown"))
    except Exception as e:
        st.error(t(tr, "health.fetchError", error=str(e)))


elif page == t(tr, "pages.algorithmRegistry"):
    st.header(t(tr, "algorithm.title"))

    try:
        algorithms = fetch_json("/algorithms")

        if not algorithms:
            st.info(t(tr, "algorithm.noAlgorithms"))
        else:
            for status in ["DRAFT", "ACTIVE", "ARCHIVED"]:
                group = [a for a in algorithms if a["status"] == status]
                if group:
                    st.subheader(f"{status} ({len(group)})")
                    for algo in group:
                        with st.expander(f"{algo['function_name']} v{algo['version']}"):
                            st.json(algo)

                            if algo["status"] == "DRAFT":
                                if st.button(t(tr, "algorithm.activateButton"), key=f"activate_{algo['id']}"):
                                    try:
                                        result = post_json(f"/algorithms/{algo['id']}/activate")
                                        st.success(
                                            t(tr, "algorithm.activated", name=result['function_name'], version=result['version'])
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(t(tr, "algorithm.activationFailed", error=str(e)))

    except Exception as e:
        st.error(t(tr, "algorithm.fetchError", error=str(e)))

    # Register new algorithm
    st.divider()
    st.subheader(t(tr, "algorithm.register.title"))
    with st.form("register_algorithm"):
        func_name = st.text_input(t(tr, "algorithm.register.functionName"), placeholder=t(tr, "algorithm.register.functionNamePlaceholder"))
        version = st.text_input(t(tr, "algorithm.register.version"), placeholder=t(tr, "algorithm.register.versionPlaceholder"))
        code = st.text_area(t(tr, "algorithm.register.code"), height=300, placeholder=t(tr, "algorithm.register.codePlaceholder"))
        law_hash = st.text_input(t(tr, "algorithm.register.lawHash"), placeholder=t(tr, "algorithm.register.lawHashPlaceholder"))

        if st.form_submit_button(t(tr, "algorithm.register.submitButton")):
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
                    st.success(t(tr, "algorithm.register.success", name=result['function_name'], version=result['version']))
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "algorithm.register.failed", error=str(e)))
            else:
                st.warning(t(tr, "algorithm.register.fillRequired"))


elif page == t(tr, "pages.llmConfiguration"):
    st.header(t(tr, "llm.title"))

    # --- Current Config ---
    st.subheader(t(tr, "llm.currentProvider"))
    try:
        config = fetch_json("/admin/llm/config")
        if config:
            col1, col2, col3 = st.columns(3)
            col1.metric(t(tr, "llm.provider"), config["provider"])
            col2.metric(t(tr, "llm.model"), config["model_name"])
            col3.metric(t(tr, "llm.active"), t(tr, "llm.yes") if config["is_active"] else t(tr, "llm.no"))
            st.text(t(tr, "llm.token") + ": " + config['masked_token'])
            st.text(t(tr, "llm.monthlyBudget") + f": ${config['monthly_budget_usd']:.2f}")
        else:
            st.info(t(tr, "llm.noProvider"))
    except Exception as e:
        st.error(t(tr, "llm.fetchError", error=str(e)))

    # --- Update Config ---
    st.divider()
    st.subheader(t(tr, "llm.updateProvider"))

    MODEL_SUGGESTIONS = {
        "gemini": ["gemini/gemini-2.0-flash", "gemini/gemini-1.5-pro"],
        "openai": ["openai/gpt-4o", "openai/gpt-4o-mini"],
        "anthropic": ["anthropic/claude-sonnet-4-20250514", "anthropic/claude-3-7-sonnet-20250219"],
    }

    # Provider selectbox outside form to trigger reactive reruns
    provider = st.selectbox(t(tr, "llm.provider"), ["openai", "gemini", "anthropic"])
    suggestions = MODEL_SUGGESTIONS.get(provider, [])

    with st.form("llm_config"):
        model_name = st.selectbox(t(tr, "llm.model"), suggestions) if suggestions else st.text_input(t(tr, "llm.modelString"))
        api_token = st.text_input(t(tr, "llm.apiToken"), type="password")
        budget = st.number_input(t(tr, "llm.monthlyBudgetUsd"), min_value=1.0, max_value=10000.0, value=50.0, step=10.0)

        if st.form_submit_button(t(tr, "llm.saveButton")):
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
                    st.success(t(tr, "llm.saved", provider=result['provider'], model=result['model_name']))
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "llm.saveFailed", error=str(e)))
            else:
                st.warning(t(tr, "llm.enterToken"))

    # --- Test Connection ---
    st.divider()
    st.subheader(t(tr, "llm.testConnection"))
    if st.button(t(tr, "llm.testButton")):
        with st.spinner(t(tr, "llm.testing")):
            try:
                with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
                    response = client.post("/admin/llm/test")
                    if response.status_code >= 400:
                        error_body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                        detail = error_body.get("detail", response.text)
                        st.error(t(tr, "llm.testFailed", error=detail))
                    else:
                        result = response.json()
                        st.success(t(tr, "llm.status") + f": {result['status']}")
                        col1, col2 = st.columns(2)
                        col1.metric(t(tr, "llm.model"), result["model"])
                        col2.metric(t(tr, "llm.latency"), t(tr, "llm.latencySeconds", seconds=result['latency_seconds']))
                        st.text(t(tr, "llm.response") + f": {result['response']}")
            except Exception as e:
                st.error(t(tr, "llm.testFailed", error=str(e)))

    # --- Usage Dashboard ---
    st.divider()
    st.subheader(t(tr, "llm.usage.title"))
    try:
        usage = fetch_json("/admin/llm/usage")
        col1, col2, col3 = st.columns(3)
        col1.metric(t(tr, "llm.usage.totalCalls"), usage["total_calls"])
        col2.metric(t(tr, "llm.usage.monthlyCost"), f"${usage['monthly_total_usd']:.4f}")
        col3.metric(t(tr, "llm.usage.budgetRemaining"), f"${usage['budget_remaining_usd']:.2f}")

        st.text(t(tr, "llm.usage.promptTokens", count=f"{usage['total_prompt_tokens']:,}"))
        st.text(t(tr, "llm.usage.completionTokens", count=f"{usage['total_completion_tokens']:,}"))

        if usage["daily_breakdown"]:
            st.bar_chart(
                data={row["date"]: row["cost_usd"] for row in usage["daily_breakdown"]},
            )
    except Exception as e:
        st.error(t(tr, "llm.usage.fetchError", error=str(e)))


elif page == t(tr, "pages.crawlerMonitor"):
    st.header(t(tr, "crawler.title"))

    # --- A. Unified Status Dashboard ---
    st.subheader(t(tr, "crawler.dashboard.title"))
    
    any_running = False
    layers = []
    
    try:
        progress = fetch_json("/admin/nta/progress")
        layers = progress.get("layers", [])
        any_running = progress.get("any_running", False)
        
        # Three-column layout for layer status
        col1, col2, col3 = st.columns(3)
        
        for idx, layer in enumerate(layers):
            col = [col1, col2, col3][idx]
            with col:
                status = layer["status"]
                status_emoji = {
                    "IDLE": "⚪",
                    "RUNNING": "🟢",
                    "COMPLETED": "✅",
                    "FAILED": "❌"
                }.get(status, "?")
                
                st.markdown(f"### {status_emoji} {layer['layer_label']}")
                st.metric(t(tr, "crawler.dashboard.status"), status)
                
                if status == "RUNNING":
                    st.metric(t(tr, "crawler.dashboard.progress"), f"{layer['progress_percent']:.1f}%")
                    st.metric(t(tr, "crawler.dashboard.elapsed"), f"{layer['elapsed_seconds']:.0f}s")
                elif status in ("COMPLETED", "FAILED"):
                    st.metric(t(tr, "crawler.dashboard.completed"), f"{layer['completed_pages']}/{layer['total_pages']}")
                    if layer['failed_pages'] > 0:
                        st.metric(t(tr, "crawler.dashboard.failed"), layer['failed_pages'])
                    if layer['changed_pages'] > 0:
                        st.metric(t(tr, "crawler.dashboard.changed"), layer['changed_pages'])
        
        # Run All button
        if not any_running:
            if st.button(t(tr, "crawler.dashboard.runAllButton"), use_container_width=True):
                try:
                    result = post_json("/admin/nta/start-crawl?layer=all")
                    st.success(result.get("message", "Started"))
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "crawler.dashboard.startFailed", error=str(e)))
        
    except Exception as e:
        st.error(t(tr, "crawler.dashboard.fetchError", error=str(e)))

    # --- B. Live Progress Panel (shown when any crawl is running) ---
    if any_running:
        st.divider()
        st.subheader(t(tr, "crawler.progress.title"))
        
        # Create a placeholder for auto-refresh
        progress_placeholder = st.empty()
        
        # Auto-refresh every 2 seconds while running
        for layer in layers:
            if layer["status"] == "RUNNING":
                with progress_placeholder.container():
                    st.markdown(f"**{layer['layer_label']}**")
                    st.progress(layer["progress_percent"] / 100.0)
                    
                    # Page-by-page status
                    if layer.get("pages"):
                        page_data = []
                        for page_info in layer["pages"]:
                            status_icon = {
                                "PENDING": "⏳",
                                "CRAWLING": "🔄",
                                "SUCCESS": "✅",
                                "FAILED": "❌"
                            }.get(page_info["status"], "?")
                            
                            page_data.append({
                                "Status": status_icon,
                                "Page": page_info["page_name"],
                                "Time (ms)": page_info.get("response_time_ms", ""),
                                "Error": page_info.get("error_message", "")[:50] if page_info.get("error_message") else ""
                            })
                        
                        if page_data:
                            st.dataframe(page_data, use_container_width=True, hide_index=True)
                
                # Auto-refresh by rerunning after 2 seconds
                time.sleep(2)
                st.rerun()

    st.divider()

    # --- C. Per-Layer Tabs (existing, enhanced) ---
    layer_tab = st.tabs([
        t(tr, "crawler.layers.ntaTaxAnswer"),
        t(tr, "crawler.layers.mofTaxReform"),
        t(tr, "crawler.layers.egovLaw"),
        t(tr, "crawler.layers.all")
    ])

    # --- 1. Layer 1: NTA Tax Answer ---
    with layer_tab[0]:
        st.subheader(t(tr, "crawler.nta.title"))

        # Health Overview
        try:
            health = fetch_json("/admin/nta/health")
            status = health["status"]
            status_emoji = {"healthy": "✅ OK", "degraded": "⚠️ WARN", "error": "❌ ERR"}.get(status, "?")

            col1, col2, col3 = st.columns(3)
            col1.metric(t(tr, "crawler.nta.status"), status_emoji)
            col2.metric(t(tr, "crawler.nta.activePages"), t(tr, "crawler.nta.activePagesCount", active=health['active_target_pages'], total=health['total_target_pages']))

            if health["last_run"]:
                last = health["last_run"]
                col3.metric(
                    t(tr, "crawler.nta.lastRun"),
                    t(tr, "crawler.nta.lastRunInfo", checked=last['pages_checked'], changed=last['pages_changed']),
                )
                st.text(t(tr, "crawler.nta.lastRunTime", time=last['started_at'], trigger=last['trigger']))
                if last["pages_failed"] > 0:
                    st.warning(t(tr, "crawler.nta.pagesFailed", count=last['pages_failed']))
            else:
                col3.metric(t(tr, "crawler.nta.lastRun"), t(tr, "crawler.nta.never"))
                st.info(t(tr, "crawler.nta.noRuns"))

        except Exception as e:
            st.error(t(tr, "crawler.nta.fetchError", error=str(e)))

        # Run Now button (background)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(t(tr, "crawler.nta.runButton"), key="nta_run"):
                with st.spinner(t(tr, "crawler.nta.running")):
                    try:
                        changes = post_json("/admin/nta/check-now")
                        if changes:
                            st.success(t(tr, "crawler.nta.completeChanges", count=len(changes)))
                            for change in changes:
                                st.write(t(tr, "crawler.nta.changeInfo", page=change['page_name'], hash=change['new_hash'][:12]))
                        else:
                            st.success(t(tr, "crawler.nta.completeNoChanges"))
                        st.rerun()
                    except Exception as e:
                        st.error(t(tr, "crawler.nta.runFailed", error=str(e)))
        
        with col_b:
            if st.button(t(tr, "crawler.progress.runBackground"), key="nta_run_bg"):
                try:
                    result = post_json("/admin/nta/start-crawl?layer=nta")
                    st.success(result.get("message", "Started"))
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "crawler.progress.startFailed", error=str(e)))

    # --- 2. Layer 2: MOF Tax Reform ---
    with layer_tab[1]:
        st.subheader(t(tr, "crawler.mof.title"))
        st.info(t(tr, "crawler.mof.description"))

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(t(tr, "crawler.mof.runButton"), key="mof_run"):
                with st.spinner(t(tr, "crawler.mof.running")):
                    try:
                        changes = post_json("/admin/nta/check-mof")
                        if changes:
                            st.success(t(tr, "crawler.mof.completeChanges", count=len(changes)))
                            for change in changes:
                                st.write(t(tr, "crawler.mof.changeInfo", page=change['page_name'], hash=change['new_hash'][:12]))
                        else:
                            st.success(t(tr, "crawler.mof.completeNoChanges"))
                        st.rerun()
                    except Exception as e:
                        st.error(t(tr, "crawler.mof.runFailed", error=str(e)))
        
        with col_b:
            if st.button(t(tr, "crawler.progress.runBackground"), key="mof_run_bg"):
                try:
                    result = post_json("/admin/nta/start-crawl?layer=mof")
                    st.success(result.get("message", "Started"))
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "crawler.progress.startFailed", error=str(e)))

    # --- 3. Layer 3: e-Gov Law ---
    with layer_tab[2]:
        st.subheader(t(tr, "crawler.egov.title"))
        st.info(t(tr, "crawler.egov.description"))

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(t(tr, "crawler.egov.runButton"), key="egov_run"):
                with st.spinner(t(tr, "crawler.egov.running")):
                    try:
                        changes = post_json("/admin/nta/check-egov")
                        if changes:
                            st.success(t(tr, "crawler.egov.completeChanges", count=len(changes)))
                            for change in changes:
                                st.write(t(tr, "crawler.egov.changeInfo", page=change['page_name'], hash=change['new_hash'][:12]))
                        else:
                            st.success(t(tr, "crawler.egov.completeNoChanges"))
                        st.rerun()
                    except Exception as e:
                        st.error(t(tr, "crawler.egov.runFailed", error=str(e)))
        
        with col_b:
            if st.button(t(tr, "crawler.progress.runBackground"), key="egov_run_bg"):
                try:
                    result = post_json("/admin/nta/start-crawl?layer=egov")
                    st.success(result.get("message", "Started"))
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "crawler.progress.startFailed", error=str(e)))

    # --- 4. All Layers ---
    with layer_tab[3]:
        st.subheader(t(tr, "crawler.allLayers.title"))
        st.info(t(tr, "crawler.allLayers.description"))

        if st.button(t(tr, "crawler.allLayers.runButton"), key="all_run"):
            with st.spinner(t(tr, "crawler.allLayers.running")):
                try:
                    result = post_json("/admin/nta/check-all")
                    st.success(t(tr, "crawler.allLayers.completeChanges", total=result['total_changes']))
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric(t(tr, "crawler.allLayers.ntaChanges"), len(result['nta_changes']))
                    col2.metric(t(tr, "crawler.allLayers.mofChanges"), len(result['mof_changes']))
                    col3.metric(t(tr, "crawler.allLayers.egovChanges"), len(result['egov_changes']))
                    
                    if result['nta_changes']:
                        st.write(t(tr, "crawler.allLayers.ntaChangesList"))
                        for change in result['nta_changes']:
                            st.write(f"- {change['page_name']}")
                    if result['mof_changes']:
                        st.write(t(tr, "crawler.allLayers.mofChangesList"))
                        for change in result['mof_changes']:
                            st.write(f"- {change['page_name']}")
                    if result['egov_changes']:
                        st.write(t(tr, "crawler.allLayers.egovChangesList"))
                        for change in result['egov_changes']:
                            st.write(f"- {change['page_name']}")
                    
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "crawler.allLayers.runFailed", error=str(e)))

    # --- Target Pages Management (shared) ---
    st.divider()
    st.subheader(t(tr, "crawler.targets.title"))

    try:
        targets = fetch_json("/admin/nta/targets")
        if targets:
            # Group by source_type
            nta_targets = [tgt for tgt in targets if tgt.get("source_type") == "NTA_TAX_ANSWER"]
            mof_targets = [tgt for tgt in targets if tgt.get("source_type") == "MOF_TAX_REFORM"]
            egov_targets = [tgt for tgt in targets if tgt.get("source_type") == "EGOV_LAW"]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(t(tr, "crawler.targets.layer1", count=len(nta_targets)))
                for target in nta_targets:
                    status_label = "✅" if target["is_active"] else "❌"
                    with st.expander(f"{status_label} {target['name']}"):
                        st.text(t(tr, "crawler.targets.url", url=target['url']))
                        st.text(t(tr, "crawler.targets.description", desc=target.get('description', 'N/A')))
                        st.text(t(tr, "crawler.targets.checkInterval", hours=target['check_interval_hours']))
            
            with col2:
                st.write(t(tr, "crawler.targets.layer2", count=len(mof_targets)))
                for target in mof_targets:
                    status_label = "✅" if target["is_active"] else "❌"
                    with st.expander(f"{status_label} {target['name']}"):
                        st.text(t(tr, "crawler.targets.url", url=target['url']))
                        st.text(t(tr, "crawler.targets.description", desc=target.get('description', 'N/A')))
                        st.text(t(tr, "crawler.targets.checkInterval", hours=target['check_interval_hours']))
            
            with col3:
                st.write(t(tr, "crawler.targets.layer3", count=len(egov_targets)))
                for target in egov_targets:
                    status_label = "✅" if target["is_active"] else "❌"
                    with st.expander(f"{status_label} {target['name']}"):
                        st.text(t(tr, "crawler.targets.url", url=target['url']))
                        st.text(t(tr, "crawler.targets.description", desc=target.get('description', 'N/A')))
                        st.text(t(tr, "crawler.targets.checkInterval", hours=target['check_interval_hours']))
        else:
            st.info(t(tr, "crawler.targets.noTargets"))
    except Exception as e:
        st.error(t(tr, "crawler.targets.fetchError", error=str(e)))

    # Add new target page
    st.divider()
    st.subheader(t(tr, "crawler.targets.addUpdate"))
    with st.form("add_target"):
        name = st.text_input(t(tr, "crawler.targets.pageName"), placeholder=t(tr, "crawler.targets.pageNamePlaceholder"))
        url = st.text_input(t(tr, "crawler.targets.urlInput"), placeholder=t(tr, "crawler.targets.urlPlaceholder"))
        description = st.text_input(t(tr, "crawler.targets.descriptionInput"), placeholder=t(tr, "crawler.targets.descriptionPlaceholder"))
        source_type = st.selectbox(
            t(tr, "crawler.targets.sourceType"),
            options=["NTA_TAX_ANSWER", "MOF_TAX_REFORM", "EGOV_LAW"],
            help=t(tr, "crawler.targets.sourceTypeHelp"),
        )
        check_interval = st.number_input(t(tr, "crawler.targets.checkIntervalHours"), min_value=1, max_value=720, value=24)
        is_active = st.checkbox(t(tr, "crawler.targets.activeCheckbox"), value=True)

        if st.form_submit_button(t(tr, "crawler.targets.saveButton")):
            if name and url:
                try:
                    result = put_json(
                        "/admin/nta/targets",
                        {
                            "name": name,
                            "url": url,
                            "description": description or None,
                            "source_type": source_type,
                            "check_interval_hours": check_interval,
                            "is_active": is_active,
                        },
                    )
                    st.success(t(tr, "crawler.targets.saved", name=result['name']))
                    st.rerun()
                except Exception as e:
                    st.error(t(tr, "crawler.targets.saveFailed", error=str(e)))
            else:
                st.warning(t(tr, "crawler.targets.fillRequired"))

    # --- 3. Snapshot History ---
    st.divider()
    st.subheader(t(tr, "crawler.snapshots.title"))

    col1, col2 = st.columns(2)
    filter_page = col1.text_input(t(tr, "crawler.snapshots.filterByPage"), placeholder=t(tr, "crawler.snapshots.filterPlaceholder"))
    changes_only = col2.checkbox(t(tr, "crawler.snapshots.changesOnly"))

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
                status_icon = {
                    "SUCCESS": t(tr, "crawler.snapshots.status.success"),
                    "FAILED": t(tr, "crawler.snapshots.status.failed"),
                    "TIMEOUT": t(tr, "crawler.snapshots.status.timeout")
                }.get(snap["status"], "?")
                label = f"{snap['target_page_name']} | {snap['fetched_at']} | {status_icon}"
                if snap["response_time_ms"]:
                    label += f" | {snap['response_time_ms']}ms"

                with st.expander(label):
                    st.text(t(tr, "crawler.snapshots.hash", hash=snap['content_hash']))
                    st.text(t(tr, "crawler.snapshots.url", url=snap['target_page_url']))

                    if snap.get("error_message"):
                        st.error(t(tr, "crawler.snapshots.error", error=snap['error_message']))

                    if snap.get("fit_markdown"):
                        tab1, tab2 = st.tabs([t(tr, "crawler.snapshots.renderedMarkdown"), t(tr, "crawler.snapshots.rawCopyable")])
                        with tab1:
                            st.markdown(snap["fit_markdown"][:5000])
                        with tab2:
                            st.code(snap["fit_markdown"], language="markdown")

                    if snap.get("extracted_tables"):
                        st.subheader(t(tr, "crawler.snapshots.extractedTables"))
                        st.json(snap["extracted_tables"])
        else:
            st.info(t(tr, "crawler.snapshots.noSnapshots"))
    except Exception as e:
        st.error(t(tr, "crawler.snapshots.fetchError", error=str(e)))

    # --- 4. Crawl Run Log ---
    st.divider()
    st.subheader(t(tr, "crawler.runLog.title"))

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
            st.info(t(tr, "crawler.runLog.noRuns"))
    except Exception as e:
        st.error(t(tr, "crawler.runLog.fetchError", error=str(e)))

    # --- 5. Error Log ---
    st.divider()
    st.subheader(t(tr, "crawler.errorLog.title"))

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
            st.success(t(tr, "crawler.errorLog.noErrors"))
    except Exception as e:
        st.error(t(tr, "crawler.errorLog.fetchError", error=str(e)))
