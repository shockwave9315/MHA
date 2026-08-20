"""Regression coverage for updater account ID redaction in diagnostics."""

from homeassistant.components.diagnostics import async_redact_data

from custom_components.mitsubishi_wf_rac.diagnostics import TO_REDACT


def test_updated_by_account_id_is_redacted() -> None:
    """An updater account ID must never survive a diagnostics export."""
    diagnostics = {"device": {"updated_by": "account-secret-123"}}

    redacted = async_redact_data(diagnostics, TO_REDACT)

    assert redacted["device"]["updated_by"] == "**REDACTED**"
