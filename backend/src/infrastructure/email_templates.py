"""HTML email templates for TaxPilot notifications.

Each template function returns (subject, html_body, text_body).
Templates use simple string formatting (no Jinja2 dependency for MVP).

TODO: HTML escaping is not yet implemented for user-controlled values.
This means values derived from NTA content or exception messages could
contain HTML tags. For production, wrap interpolated values in html.escape().
"""

import html

STYLE = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: #1a56db; color: white; padding: 16px; border-radius: 8px 8px 0 0; }
    .body { background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; }
    .footer { padding: 12px; text-align: center; color: #6b7280; font-size: 12px; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-high { background: #fee2e2; color: #dc2626; }
    .badge-medium { background: #fef3c7; color: #d97706; }
    .badge-low { background: #dbeafe; color: #2563eb; }
    .btn { display: inline-block; padding: 10px 20px; background: #1a56db; color: white; text-decoration: none; border-radius: 6px; }
</style>
"""


def _escape(value: str) -> str:
    """Escape HTML entities to prevent injection.

    Args:
        value: Raw string that may contain HTML tags

    Returns:
        Escaped string safe for HTML interpolation
    """
    return html.escape(value)


def regulation_change_detected(
    page_name: str, page_url: str, snapshot_id: int, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for REGULATION_CHANGE_DETECTED event."""
    subject = f"[TaxPilot] New regulation change detected: {page_name}"
    html_body = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Regulation Change Detected</h2>
        </div>
        <div class="body">
            <p>The NTA crawler has detected a content change on a monitored page:</p>
            <ul>
                <li><strong>Page:</strong> {_escape(page_name)}</li>
                <li><strong>URL:</strong> <a href="{_escape(page_url)}">{_escape(page_url)}</a></li>
                <li><strong>Snapshot ID:</strong> {snapshot_id}</li>
            </ul>
            <p>The Evolution Loop will automatically parse this change and generate
            updated formulas for your review.</p>
            <p><a href="{dashboard_url}" class="btn">Open Dashboard</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Regulation Change Detected\n\n"
        f"Page: {page_name}\n"
        f"URL: {page_url}\n"
        f"Snapshot ID: {snapshot_id}\n\n"
        f"Open dashboard: {dashboard_url}"
    )
    return subject, html_body, text


def formula_ready_for_review(
    run_id: int, function_name: str, change_summary: str, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for FORMULA_READY_FOR_REVIEW event."""
    subject = f"[TaxPilot] New formula ready for review (Run #{run_id})"
    html_body = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Formula Ready for Review</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-high">Action Required</span></p>
            <p>A new formula has been generated and requires your review:</p>
            <ul>
                <li><strong>Run:</strong> #{run_id}</li>
                <li><strong>Function:</strong> {_escape(function_name)}</li>
                <li><strong>Change:</strong> {_escape(change_summary)}</li>
            </ul>
            <p>You can Accept, Modify, Regenerate, or Skip this formula.</p>
            <p><a href="{dashboard_url}" class="btn">Review Now</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Formula Ready for Review\n\n"
        f"Run: #{run_id}\n"
        f"Function: {function_name}\n"
        f"Change: {change_summary}\n\n"
        f"Review at: {dashboard_url}"
    )
    return subject, html_body, text


def formula_activated(
    function_name: str, version: str, decision: str, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for FORMULA_ACTIVATED event."""
    subject = f"[TaxPilot] Formula activated: {function_name} v{version}"
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Formula Activated</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-medium">Info</span></p>
            <p>A formula has been activated:</p>
            <ul>
                <li><strong>Function:</strong> {function_name}</li>
                <li><strong>Version:</strong> {version}</li>
                <li><strong>Decision:</strong> {decision}</li>
            </ul>
            <p>The previous version has been archived. Rollback is available via the dashboard.</p>
            <p><a href="{dashboard_url}" class="btn">View Details</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Formula Activated\n\n"
        f"Function: {function_name}\n"
        f"Version: {version}\n"
        f"Decision: {decision}\n\n"
        f"View at: {dashboard_url}"
    )
    return subject, html, text


def formula_regenerating(
    run_id: int, attempt: int, max_attempts: int, hints: str | None, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for FORMULA_REGENERATING event."""
    subject = f"[TaxPilot] Regeneration requested for Run #{run_id} (attempt {attempt}/{max_attempts})"
    hints_text = hints or "No specific hints provided"
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Formula Regeneration Requested</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-low">Info</span></p>
            <ul>
                <li><strong>Run:</strong> #{run_id}</li>
                <li><strong>Attempt:</strong> {attempt} of {max_attempts}</li>
                <li><strong>Hints:</strong> {hints_text}</li>
            </ul>
            <p>The LLM will generate a new version. You will be notified when it is ready for review.</p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Regeneration Requested\n\n"
        f"Run: #{run_id}\n"
        f"Attempt: {attempt}/{max_attempts}\n"
        f"Hints: {hints_text}"
    )
    return subject, html, text


def run_failed(
    run_id: int, failed_step: str, error: str, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for RUN_FAILED event."""
    subject = f"[TaxPilot] Evolution run #{run_id} failed at {failed_step} step"
    html_body = f"""
    {STYLE}
    <div class="container">
        <div class="header" style="background: #dc2626;">
            <h2>Evolution Run Failed</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-high">Error</span></p>
            <ul>
                <li><strong>Run:</strong> #{run_id}</li>
                <li><strong>Failed Step:</strong> {_escape(failed_step)}</li>
                <li><strong>Error:</strong> {_escape(error)}</li>
            </ul>
            <p>Please check the dashboard for details and consider re-running.</p>
            <p><a href="{dashboard_url}" class="btn">View Run Details</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Evolution Run Failed\n\n"
        f"Run: #{run_id}\n"
        f"Failed Step: {failed_step}\n"
        f"Error: {error}\n\n"
        f"View at: {dashboard_url}"
    )
    return subject, html_body, text


def deferred_reminder(
    deferred_count: int, deferred_runs: list[dict], dashboard_url: str
) -> tuple[str, str, str]:
    """Template for DEFERRED_REMINDER weekly digest."""
    subject = f"[TaxPilot] {deferred_count} deferred regulation updates await manual handling"
    runs_html = "".join(
        f"<li>Run #{r['id']}: {r['summary']} (deferred {r['date']})</li>"
        for r in deferred_runs
    )
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Deferred Tasks Reminder</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-medium">Reminder</span></p>
            <p>You have <strong>{deferred_count}</strong> deferred regulation updates
            that are waiting for manual handling:</p>
            <ul>{runs_html}</ul>
            <p><a href="{dashboard_url}" class="btn">Review Deferred Tasks</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring (Weekly Digest)
        </div>
    </div>
    """
    text = (
        f"Deferred Tasks Reminder\n\n"
        f"You have {deferred_count} deferred regulation updates.\n\n"
        f"View at: {dashboard_url}"
    )
    return subject, html, text
