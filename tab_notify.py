"""
METSI-EWS  —  Streamlit "Send Report" tab
==========================================
Renders the notification UI as a self-contained function.

Integration (in your main Streamlit app):
──────────────────────────────────────────
    from tab_notify import render_notify_tab

    tab1, tab2, tab3, tab4, tab5, tab_send = st.tabs([
        "Overview", "Map", "Ward Detail", "Equity Check", "Model", "📤 Send Report"
    ])

    with tab_send:
        render_notify_tab(predictions_df)

Where `predictions_df` is the DataFrame loaded from predictions.csv.
Pass None or an empty DataFrame if the pipeline has not run yet.
"""

import os
import streamlit as st
from notify import compose_risk_report, send_report


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_RECIPIENTS = [
    "datahub@tshwane.gov.za",
]


# ---------------------------------------------------------------------------
# Main tab renderer
# ---------------------------------------------------------------------------

def render_notify_tab(predictions_df):
    """
    Render the Send Report tab.

    Parameters
    ----------
    predictions_df : pd.DataFrame | None
        Current risk predictions. If None / empty, the tab shows a warning.
    """
    st.header("📤 Send Risk Report")
    st.caption(
        "Compose and send the current ward-risk summary to City of Tshwane contacts "
        "or data partners."
    )

    # ── Guard: pipeline must have run ─────────────────────────────────────────
    if predictions_df is None or predictions_df.empty:
        st.warning(
            "No predictions are loaded. Run the pipeline first (`run_pipeline.py`) "
            "so that `predictions.csv` is present."
        )
        return

    # ── SMTP credentials ─────────────────────────────────────────────────────
    env_ok = _env_configured()
    with st.expander(
        "⚙️ SMTP Settings" + (" ✅ env vars detected" if env_ok else " — enter credentials"),
        expanded=not env_ok,
    ):
        st.caption(
            "Use a Gmail App Password (not your account password). "
            "See: https://myaccount.google.com/apppasswords"
        )
        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input(
                "SMTP host",
                value=os.environ.get("METSI_SMTP_HOST", "smtp.gmail.com"),
                key="smtp_host",
            )
            smtp_user = st.text_input(
                "Sender email",
                value=os.environ.get("METSI_SMTP_USER", ""),
                key="smtp_user",
            )
        with col2:
            smtp_port = st.number_input(
                "Port",
                value=int(os.environ.get("METSI_SMTP_PORT", 587)),
                step=1,
                key="smtp_port",
            )
            smtp_pass = st.text_input(
                "App password",
                type="password",
                value=os.environ.get("METSI_SMTP_PASS", ""),
                key="smtp_pass",
            )

    smtp_cfg = {
        "host":     smtp_host,
        "port":     int(smtp_port),
        "user":     smtp_user,
        "password": smtp_pass,
    }

    # ── Recipients ────────────────────────────────────────────────────────────
    st.subheader("Recipients")
    raw_recipients = st.text_area(
        "One email address per line",
        value="\n".join(DEFAULT_RECIPIENTS),
        height=110,
        key="recipients",
    )
    to_addrs = [addr.strip() for addr in raw_recipients.splitlines() if addr.strip()]

    if not to_addrs:
        st.warning("Enter at least one recipient address.")

    # ── Report options ────────────────────────────────────────────────────────
    st.subheader("Report options")
    col1, col2 = st.columns(2)
    with col1:
        threshold = st.slider(
            "Minimum risk score to include",
            min_value=0.10,
            max_value=0.90,
            value=0.30,
            step=0.05,
            help="Wards below this score are excluded from the report.",
            key="threshold",
        )
    with col2:
        top_n = st.number_input(
            "Max wards to include",
            min_value=5,
            max_value=107,
            value=15,
            step=5,
            key="top_n",
        )

    custom_subject = st.text_input(
        "Custom subject line (optional — leave blank for default)",
        value="",
        key="subject",
    )

    # ── Preview ───────────────────────────────────────────────────────────────
    with st.expander("👁 Preview report"):
        try:
            plain, _ = compose_risk_report(
                predictions_df,
                top_n=int(top_n),
                threshold=float(threshold),
            )
            n_rows = len(
                predictions_df[
                    predictions_df[
                        next(
                            c for c in ["risk_score", "failure_prob", "predicted_prob"]
                            if c in predictions_df.columns
                        )
                    ] >= threshold
                ]
            )
            st.caption(f"{min(n_rows, int(top_n))} ward(s) will be included at this threshold.")
            st.text(plain)
        except Exception as exc:
            st.error(f"Preview error: {exc}")

    # ── Send button ───────────────────────────────────────────────────────────
    st.divider()

    creds_missing = not smtp_cfg["user"] or not smtp_cfg["password"]
    send_disabled = not to_addrs or creds_missing

    if creds_missing:
        st.caption("⚠️ Enter SMTP credentials above before sending.")

    if st.button(
        "📧 Send Report",
        type="primary",
        disabled=send_disabled,
        key="send_btn",
    ):
        subject = custom_subject.strip() or None

        with st.spinner("Sending…"):
            result = send_report(
                to_addrs=to_addrs,
                predictions_df=predictions_df,
                smtp_cfg=smtp_cfg,
                subject=subject,
                top_n=int(top_n),
                threshold=float(threshold),
            )

        if result["success"]:
            st.success(f"✅ Report sent to: {', '.join(to_addrs)}")
            st.balloons()
        else:
            st.error(f"❌ Send failed: {result['error']}")
            st.caption(
                "Common causes: wrong app password, SMTP host/port mismatch, "
                "or Gmail 2-step verification not enabled."
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _env_configured() -> bool:
    """Return True if all four SMTP env vars are present."""
    return all(
        os.environ.get(k)
        for k in ["METSI_SMTP_HOST", "METSI_SMTP_PORT", "METSI_SMTP_USER", "METSI_SMTP_PASS"]
    )
