"""Tests for email templates."""

import pytest

from src.infrastructure import email_templates


class TestEmailTemplates:
    """Test all email template functions."""

    def test_regulation_change_detected_template(self):
        """Should generate regulation change notification email."""
        subject, html, text = email_templates.regulation_change_detected(
            page_name="所得税法 第2条",
            page_url="https://www.nta.go.jp/law/joho-zeikaishaku/shotoku/01.htm",
            snapshot_id=12345,
            dashboard_url="https://taxpilot.com/admin/snapshots/12345",
        )

        assert "regulation change detected" in subject.lower()
        assert "所得税法 第2条" in subject
        assert "所得税法 第2条" in html
        assert "https://www.nta.go.jp/law" in html
        assert "12345" in html
        assert "Open Dashboard" in html

        assert "所得税法 第2条" in text
        assert "https://www.nta.go.jp/law" in text

    def test_formula_ready_for_review_template(self):
        """Should generate formula review notification email."""
        subject, html, text = email_templates.formula_ready_for_review(
            run_id=42,
            function_name="calculate_income_tax_2024",
            change_summary="Threshold updated from ¥2M to ¥2.4M",
            dashboard_url="https://taxpilot.com/admin/runs/42",
        )

        assert "New formula ready for review" in subject
        assert "Run #42" in subject
        assert "Action Required" in html
        assert "calculate_income_tax_2024" in html
        assert "Threshold updated" in html
        assert "Review Now" in html

        assert "Run: #42" in text
        assert "calculate_income_tax_2024" in text

    def test_formula_activated_template(self):
        """Should generate formula activation notification email."""
        subject, html, text = email_templates.formula_activated(
            function_name="calculate_income_tax_2024",
            version="2024.12.01-01",
            decision="ACCEPT",
            dashboard_url="https://taxpilot.com/admin/runs/42",
        )

        assert "Formula activated" in subject
        assert "calculate_income_tax_2024" in subject
        assert "v2024.12.01-01" in subject
        assert "calculate_income_tax_2024" in html
        assert "2024.12.01-01" in html
        assert "ACCEPT" in html
        assert "rollback" in html.lower()

        assert "calculate_income_tax_2024" in text
        assert "2024.12.01-01" in text

    def test_formula_regenerating_template(self):
        """Should generate formula regeneration notification email."""
        subject, html, text = email_templates.formula_regenerating(
            run_id=42,
            attempt=2,
            max_attempts=3,
            hints="Fix the bracket logic for amounts over ¥10M",
            dashboard_url="https://taxpilot.com/admin/runs/42",
        )

        assert "Regeneration requested" in subject
        assert "Run #42" in subject
        assert "attempt 2/3" in subject
        assert "#42" in html
        assert "2 of 3" in html
        assert "Fix the bracket logic" in html

        assert "Run: #42" in text
        assert "2/3" in text

    def test_formula_regenerating_template_no_hints(self):
        """Should handle None hints gracefully."""
        subject, html, text = email_templates.formula_regenerating(
            run_id=42,
            attempt=1,
            max_attempts=3,
            hints=None,
            dashboard_url="https://taxpilot.com/admin/runs/42",
        )

        assert "No specific hints provided" in html
        assert "No specific hints provided" in text

    def test_run_failed_template(self):
        """Should generate run failure notification email."""
        subject, html, text = email_templates.run_failed(
            run_id=42,
            failed_step="PARSING",
            error="RegulationParser failed: could not parse threshold value",
            dashboard_url="https://taxpilot.com/admin/runs/42",
        )

        assert "Evolution run #42 failed" in subject
        assert "PARSING" in subject
        assert "Evolution Run Failed" in html
        assert "#42" in html
        assert "PARSING" in html
        assert "could not parse threshold value" in html
        assert "Error" in html  # Badge

        assert "Run: #42" in text
        assert "PARSING" in text
        assert "could not parse threshold value" in text

    def test_deferred_reminder_template(self):
        """Should generate deferred reminder digest email."""
        deferred_runs = [
            {"id": 101, "summary": "Threshold update pending", "date": "2024-11-15"},
            {"id": 102, "summary": "New deduction added", "date": "2024-11-20"},
            {"id": 103, "summary": "Bracket change", "date": "2024-11-25"},
        ]

        subject, html, text = email_templates.deferred_reminder(
            deferred_count=3,
            deferred_runs=deferred_runs,
            dashboard_url="https://taxpilot.com/admin/evolution/deferred",
        )

        assert "3 deferred regulation updates" in subject
        assert "Deferred Tasks Reminder" in html
        assert "<strong>3</strong>" in html
        assert "Run #101" in html
        assert "Threshold update pending" in html
        assert "2024-11-15" in html
        assert "Run #102" in html
        assert "Run #103" in html
        assert "Weekly Digest" in html

        assert "3 deferred regulation updates" in text

    def test_all_templates_return_three_part_tuple(self):
        """Should ensure all templates return (subject, html, text)."""
        templates = [
            (
                email_templates.regulation_change_detected,
                {
                    "page_name": "Test",
                    "page_url": "http://test",
                    "snapshot_id": 1,
                    "dashboard_url": "http://dashboard",
                },
            ),
            (
                email_templates.formula_ready_for_review,
                {
                    "run_id": 1,
                    "function_name": "test_func",
                    "change_summary": "Test",
                    "dashboard_url": "http://dashboard",
                },
            ),
            (
                email_templates.formula_activated,
                {
                    "function_name": "test_func",
                    "version": "1.0",
                    "decision": "ACCEPT",
                    "dashboard_url": "http://dashboard",
                },
            ),
            (
                email_templates.formula_regenerating,
                {
                    "run_id": 1,
                    "attempt": 1,
                    "max_attempts": 3,
                    "hints": None,
                    "dashboard_url": "http://dashboard",
                },
            ),
            (
                email_templates.run_failed,
                {
                    "run_id": 1,
                    "failed_step": "PARSING",
                    "error": "Test error",
                    "dashboard_url": "http://dashboard",
                },
            ),
            (
                email_templates.deferred_reminder,
                {
                    "deferred_count": 1,
                    "deferred_runs": [{"id": 1, "summary": "Test", "date": "2024-01-01"}],
                    "dashboard_url": "http://dashboard",
                },
            ),
        ]

        for template_func, kwargs in templates:
            result = template_func(**kwargs)
            assert isinstance(result, tuple)
            assert len(result) == 3
            subject, html, text = result
            assert isinstance(subject, str)
            assert isinstance(html, str)
            assert isinstance(text, str)
            assert len(subject) > 0
            assert len(html) > 0
            assert len(text) > 0

    def test_all_html_templates_contain_styling(self):
        """Should ensure all HTML templates include base styling."""
        # Test one representative template
        _, html, _ = email_templates.formula_ready_for_review(
            run_id=1,
            function_name="test",
            change_summary="test",
            dashboard_url="test",
        )

        assert "<style>" in html
        assert "font-family" in html
        assert ".container" in html
        assert ".header" in html
        assert ".body" in html
        assert ".footer" in html
