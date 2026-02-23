"""Ultimate GSC Audit AI Agent — Streamlit Application."""

import streamlit as st

from core.gsc_client import (
    GSCClient,
    get_authorization_url,
    handle_oauth_callback,
)
from core.data_store import DataStore
from core.data_fetcher import DataFetcher
from models.audit_finding import AUDIT_GROUPS, TASK_NAMES, TASK_TO_GROUP
from models.audit_result import AuditResult
from utils.date_utils import get_date_range
from utils.formatting import format_number, format_percentage, format_position

st.set_page_config(
    page_title="GSC Audit Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        "authenticated": False,
        "credentials": None,
        "gsc_client": None,
        "properties": [],
        "selected_property": None,
        "brand_name": "",
        "audit_result": None,
        "audit_running": False,
        "data_store": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def handle_oauth_redirect():
    """Check URL query params for OAuth callback code and exchange it for credentials."""
    auth_code = st.query_params.get("code")
    if auth_code and not st.session_state.get("authenticated"):
        try:
            credentials = handle_oauth_callback(auth_code)
            st.session_state["credentials"] = credentials
            st.session_state["gsc_client"] = GSCClient(credentials)
            st.session_state["authenticated"] = True
            st.session_state["properties"] = st.session_state[
                "gsc_client"
            ].list_properties()
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.query_params.clear()
            st.error(f"Authentication failed: {e}")


def render_sidebar():
    """Render the sidebar with auth, property selection, and audit controls."""
    st.sidebar.title("🔍 GSC Audit Agent")
    st.sidebar.markdown("---")

    # --- Authentication ---
    if not st.session_state["authenticated"]:
        st.sidebar.subheader("1. Connect to Google")
        auth_url = get_authorization_url()
        st.sidebar.link_button("🔗 Sign in with Google", auth_url)
        st.sidebar.caption(
            "Grant read-only access to your Search Console data. "
            "You'll be redirected back here automatically."
        )
        return None

    st.sidebar.success("✅ Connected to Google")

    # --- Property Selection ---
    st.sidebar.subheader("2. Select Property")
    property_urls = [p["url"] for p in st.session_state["properties"]]
    if not property_urls:
        st.sidebar.warning("No GSC properties found.")
        return None

    selected = st.sidebar.selectbox(
        "GSC Property:",
        options=property_urls,
        index=0,
    )
    st.session_state["selected_property"] = selected

    # --- Brand Name ---
    st.session_state["brand_name"] = st.sidebar.text_input(
        "Brand Name (optional):",
        value=st.session_state.get("brand_name", ""),
        help="Used to separate brand vs. non-brand queries.",
    )

    st.sidebar.markdown("---")

    # --- Audit Scope ---
    st.sidebar.subheader("3. Audit Scope")
    scope_mode = st.sidebar.radio(
        "Tasks to run:",
        options=["All 56 Tasks", "Select by Group", "Custom Selection"],
        index=0,
    )

    selected_tasks: list[int] = []
    if scope_mode == "All 56 Tasks":
        selected_tasks = list(range(1, 57))
    elif scope_mode == "Select by Group":
        selected_groups = st.sidebar.multiselect(
            "Select groups:",
            options=list(AUDIT_GROUPS.keys()),
            format_func=lambda g: f"Group {g}: {AUDIT_GROUPS[g]}",
            default=list(AUDIT_GROUPS.keys()),
        )
        for g in selected_groups:
            selected_tasks.extend(
                [tid for tid, gid in TASK_TO_GROUP.items() if gid == g]
            )
    else:
        selected_tasks = st.sidebar.multiselect(
            "Select tasks:",
            options=list(TASK_NAMES.keys()),
            format_func=lambda t: f"{t}. {TASK_NAMES[t]}",
            default=list(TASK_NAMES.keys()),
        )

    st.sidebar.markdown("---")

    # --- AI Settings ---
    st.sidebar.subheader("4. AI Analysis")
    ai_enabled = st.sidebar.toggle("Enable AI Analysis", value=True)

    st.sidebar.markdown("---")

    # --- Date Range ---
    st.sidebar.subheader("5. Date Range")
    days = st.sidebar.slider("Analysis window (days):", 7, 365, 90)
    start_date, end_date = get_date_range(days)
    st.sidebar.caption(f"Analyzing: {start_date} to {end_date}")
    include_yoy = st.sidebar.checkbox("Include YoY data (365 days)", value=True)

    st.sidebar.markdown("---")

    # --- Run Button ---
    run_clicked = st.sidebar.button(
        "🚀 Run Audit",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.get("audit_running", False),
    )

    return {
        "selected_tasks": sorted(selected_tasks),
        "ai_enabled": ai_enabled,
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "include_yoy": include_yoy,
        "run_clicked": run_clicked,
    }


def run_audit(config: dict):
    """Execute the full audit pipeline."""
    st.session_state["audit_running"] = True
    store = DataStore()
    st.session_state["data_store"] = store

    task_ids = config["selected_tasks"]
    site_url = st.session_state["selected_property"]
    brand_name = st.session_state.get("brand_name", "")

    result = AuditResult(
        property_url=site_url,
        start_date=config["start_date"],
        end_date=config["end_date"],
        tasks_executed=task_ids,
    )

    progress_bar = st.progress(0, text="Starting audit...")
    status_text = st.empty()

    # --- Phase 1: Data Fetching (0-40%) ---
    status_text.text("📡 Fetching GSC data...")
    fetcher = DataFetcher(
        client=st.session_state["gsc_client"],
        store=store,
        site_url=site_url,
    )

    def fetch_progress(current, total, message):
        pct = int((current / max(total, 1)) * 40)
        progress_bar.progress(pct, text=f"Fetching: {message}")

    fetcher.fetch_for_tasks(task_ids, progress_callback=fetch_progress)

    # --- Phase 2: Audit Execution (40-80%) ---
    status_text.text("🔎 Running audit tasks...")
    from auditors import get_auditors_for_tasks

    auditors = get_auditors_for_tasks(task_ids, store, brand_name)
    total_auditors = len(auditors)

    for i, (auditor, auditor_task_ids) in enumerate(auditors):
        findings = auditor.run_tasks(auditor_task_ids)
        result.add_findings(findings)
        pct = 40 + int(((i + 1) / max(total_auditors, 1)) * 40)
        progress_bar.progress(pct, text=f"Completed: {auditor.__class__.__name__}")

    # --- Phase 3: AI Analysis (80-95%) ---
    if config["ai_enabled"]:
        status_text.text("🧠 Running AI analysis...")
        try:
            from ai.analysis_engine import AnalysisEngine

            engine = AnalysisEngine()
            engine.analyze_result(result, progress_callback=lambda p, msg: (
                progress_bar.progress(80 + int(p * 15), text=f"AI: {msg}")
            ))
        except Exception as e:
            st.warning(f"AI analysis skipped: {e}")
    progress_bar.progress(95, text="Generating reports...")

    # --- Phase 4: Report Generation (95-100%) ---
    status_text.text("📄 Generating reports...")
    st.session_state["audit_result"] = result
    progress_bar.progress(100, text="Audit complete!")
    status_text.text("✅ Audit complete!")
    st.session_state["audit_running"] = False


def render_connect_tab():
    """Render the Connect & Configure tab."""
    if not st.session_state["authenticated"]:
        st.header("Welcome to the GSC Audit Agent")
        st.markdown("""
        This tool performs a comprehensive 56-task audit of your Google Search Console data,
        covering everything from CTR optimization and keyword cannibalization to Core Web Vitals
        and strategic trend analysis.

        **Get started:** Use the sidebar to sign in with your Google account.

        ### What this audit covers:
        """)
        for gid, gname in AUDIT_GROUPS.items():
            task_count = sum(1 for t in TASK_TO_GROUP.values() if t == gid)
            st.markdown(f"- **Group {gid}: {gname}** ({task_count} tasks)")
    else:
        st.header("✅ Connected")
        st.markdown(f"**Property:** {st.session_state['selected_property']}")
        st.markdown(f"**Available properties:** {len(st.session_state['properties'])}")
        st.info("Configure your audit scope in the sidebar and click **Run Audit**.")


def render_results_tab():
    """Render the Results Dashboard tab."""
    result: AuditResult | None = st.session_state.get("audit_result")
    if result is None:
        st.info("Run an audit to see results here.")
        return

    # Health Score
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Health Score", f"{result.health_score}/100")
    with col2:
        st.metric("Health Grade", result.health_grade)
    with col3:
        st.metric("Total Findings", format_number(result.total_findings))
    with col4:
        st.metric("Tasks Executed", format_number(len(result.tasks_executed)))

    # Severity distribution
    st.subheader("Findings by Severity")
    severity_counts = result.severity_counts
    cols = st.columns(5)
    severity_labels = ["critical", "high", "medium", "low", "insight"]
    severity_emojis = ["🔴", "🟠", "🟡", "🔵", "⚪"]
    for col, label, emoji in zip(cols, severity_labels, severity_emojis):
        with col:
            st.metric(f"{emoji} {label.title()}", severity_counts.get(label, 0))

    st.markdown("---")

    # Group-by-group findings
    for group_id in sorted(result.findings_by_group.keys()):
        group_findings = result.findings_by_group[group_id]
        group_name = AUDIT_GROUPS.get(group_id, f"Group {group_id}")

        with st.expander(
            f"**Group {group_id}: {group_name}** — {len(group_findings)} findings",
            expanded=False,
        ):
            for finding in sorted(group_findings, key=lambda f: f.severity.priority):
                severity_color = finding.severity.color
                st.markdown(
                    f"<span style='color:{severity_color};font-weight:bold;'>"
                    f"{finding.severity.emoji} {finding.severity.value.upper()}</span> | "
                    f"**Task {finding.task_id}: {finding.task_name}**",
                    unsafe_allow_html=True,
                )
                st.markdown(finding.summary)

                if finding.recommendations:
                    st.markdown("**Recommendations:**")
                    for rec in finding.recommendations:
                        st.markdown(f"- {rec}")

                if finding.data_table is not None and not finding.data_table.empty:
                    st.dataframe(
                        finding.data_table.head(20),
                        use_container_width=True,
                        hide_index=True,
                    )

                if finding.opportunity_value:
                    st.caption(f"💰 Opportunity: {finding.opportunity_value}")

                st.markdown("---")


def render_ai_tab():
    """Render the AI Insights tab."""
    result: AuditResult | None = st.session_state.get("audit_result")
    if result is None:
        st.info("Run an audit to see AI insights here.")
        return

    if result.ai_executive_summary:
        st.header("Executive Summary")
        st.markdown(result.ai_executive_summary)
        st.markdown("---")

    if result.ai_content_plan:
        st.header("Content Optimization Plan")
        st.markdown(result.ai_content_plan)
        st.markdown("---")

    if result.ai_group_analyses:
        st.header("Group-Level Analysis")
        for group_id in sorted(result.ai_group_analyses.keys()):
            group_name = AUDIT_GROUPS.get(group_id, f"Group {group_id}")
            with st.expander(f"Group {group_id}: {group_name}"):
                st.markdown(result.ai_group_analyses[group_id])
    else:
        st.info("AI analysis was not enabled for this audit. Toggle it on in the sidebar.")


def render_export_tab():
    """Render the Export tab with download buttons."""
    result: AuditResult | None = st.session_state.get("audit_result")
    if result is None:
        st.info("Run an audit to export results.")
        return

    st.header("Export Audit Report")

    col1, col2 = st.columns(2)

    with col1:
        try:
            from reports.report_generator import generate_markdown_report

            md_report = generate_markdown_report(result)
            st.download_button(
                label="📥 Download Markdown Report",
                data=md_report,
                file_name=f"gsc-audit-{result.property_url.replace('/', '_').replace(':', '')}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Markdown report generation failed: {e}")

    with col2:
        try:
            from reports.report_generator import generate_html_report

            html_report = generate_html_report(result)
            st.download_button(
                label="📥 Download HTML Report",
                data=html_report,
                file_name=f"gsc-audit-{result.property_url.replace('/', '_').replace(':', '')}.html",
                mime="text/html",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"HTML report generation failed: {e}")

    st.markdown("---")
    st.subheader("Report Preview")
    try:
        from reports.report_generator import generate_markdown_report

        md_report = generate_markdown_report(result)
        st.markdown(md_report)
    except Exception as e:
        st.info(f"Preview not available: {e}")


def main():
    """Main application entry point."""
    init_session_state()
    handle_oauth_redirect()

    sidebar_config = render_sidebar()

    tab_connect, tab_results, tab_ai, tab_export = st.tabs(
        ["🔌 Connect", "📊 Results", "🧠 AI Insights", "📥 Export"]
    )

    with tab_connect:
        render_connect_tab()

    with tab_results:
        render_results_tab()

    with tab_ai:
        render_ai_tab()

    with tab_export:
        render_export_tab()

    # Handle audit trigger
    if sidebar_config and sidebar_config.get("run_clicked"):
        if not st.session_state.get("authenticated"):
            st.error("Please connect to Google first.")
        elif not sidebar_config.get("selected_tasks"):
            st.error("Please select at least one audit task.")
        else:
            with tab_results:
                run_audit(sidebar_config)
                st.rerun()


if __name__ == "__main__":
    main()
