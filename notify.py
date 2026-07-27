"""
METSI-EWS  —  Email notification utility
=========================================
Composes and sends a ward-risk summary report via SMTP.
Requires only stdlib + pandas (already in project).

SMTP credentials are read from environment variables:
    METSI_SMTP_HOST   e.g. smtp.gmail.com
    METSI_SMTP_PORT   e.g. 587
    METSI_SMTP_USER   e.g. your.email@gmail.com
    METSI_SMTP_PASS   Gmail App Password (NOT your account password)

Optional: install python-dotenv and call load_dotenv() before importing
this module, or set the variables in the Streamlit UI instead.
"""

import os
import smtplib
import textwrap
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_TIERS = [
    (0.70, "CRITICAL", "#c0392b"),
    (0.50, "HIGH",     "#e67e22"),
    (0.30, "MODERATE", "#d4ac0d"),
    (0.00, "LOW",      "#27ae60"),
]

MODEL_AUC   = "≈ 0.69"
INSTITUTION = "Richfield Graduate Institute of Technology, Pretoria"
HORIZON_LABEL = "3-month forward prediction"

# Columns to look for risk score (in priority order)
_SCORE_COLS = ["risk_score", "failure_prob", "predicted_prob"]
# Columns to look for ward identifier
_WARD_COLS  = ["WardLabel", "ward_id", "ward"]
# Optional chokepoint flag
_CHP_COL    = "is_chokepoint"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_smtp_cfg() -> dict:
    """
    Read SMTP settings from environment variables.
    Raises EnvironmentError with a clear message if any required var is missing.
    """
    keys = {
        "host":     "METSI_SMTP_HOST",
        "port":     "METSI_SMTP_PORT",
        "user":     "METSI_SMTP_USER",
        "password": "METSI_SMTP_PASS",
    }
    cfg, missing = {}, []
    for attr, env_key in keys.items():
        val = os.environ.get(env_key)
        if not val:
            missing.append(env_key)
        else:
            cfg[attr] = val

    if missing:
        raise EnvironmentError(
            f"Missing SMTP environment variables: {', '.join(missing)}\n"
            "Copy .env.example → .env and fill in your credentials,\n"
            "or enter them in the Streamlit SMTP Settings panel."
        )
    cfg["port"] = int(cfg["port"])
    return cfg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_col(df: pd.DataFrame, candidates: list, label: str) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(
        f"Could not find {label} column in predictions. "
        f"Expected one of: {candidates}. Got: {list(df.columns)}"
    )


def _tier(score: float) -> tuple:
    for threshold, name, colour in RISK_TIERS:
        if score >= threshold:
            return name, colour
    return "LOW", "#27ae60"


def _forward_horizon() -> str:
    """Return approximate 3-month forward month label."""
    from dateutil.relativedelta import relativedelta  # type: ignore
    try:
        target = datetime.now() + relativedelta(months=3)
        return target.strftime("%B %Y")
    except ImportError:
        return "3 months ahead"


# ---------------------------------------------------------------------------
# Report composer
# ---------------------------------------------------------------------------

def compose_risk_report(
    predictions_df: pd.DataFrame,
    top_n: int = 15,
    threshold: float = 0.30,
) -> tuple:
    """
    Build plain-text and HTML versions of the risk summary.

    Parameters
    ----------
    predictions_df : DataFrame produced by the METSI-EWS pipeline.
                     Must contain a risk-score column and a ward-ID column.
    top_n          : Maximum number of wards to list.
    threshold      : Minimum risk score to include (0–1).

    Returns
    -------
    (plain_text: str, html: str)
    """
    df = predictions_df.copy()
    score_col = _get_col(df, _SCORE_COLS, "risk score")
    ward_col  = _get_col(df, _WARD_COLS,  "ward ID")
    has_chp   = _CHP_COL in df.columns

    df = (
        df[df[score_col] >= threshold]
        .sort_values(score_col, ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    now       = datetime.now().strftime("%d %B %Y, %H:%M")
    horizon   = _forward_horizon()
    n_wards   = len(df)
    n_critical = (df[score_col] >= 0.70).sum()
    n_high     = ((df[score_col] >= 0.50) & (df[score_col] < 0.70)).sum()

    # ── Plain text ───────────────────────────────────────────────────────────
    header = textwrap.dedent(f"""\
        METSI-EWS  |  Water Infrastructure Risk Report
        City of Tshwane Metropolitan Municipality
        Generated : {now}
        Horizon   : {horizon} ({HORIZON_LABEL})
        ─────────────────────────────────────────────────────────────
        {n_wards} ward(s) at or above {int(threshold * 100)}% predicted failure risk
        {n_critical} CRITICAL  |  {n_high} HIGH
        ─────────────────────────────────────────────────────────────
        """)

    col_w = f"  {'Ward':<14} {'Score':>7}   Tier\n  {'─' * 36}"
    rows = []
    for _, row in df.iterrows():
        ward  = str(row[ward_col])
        score = float(row[score_col])
        tier, _ = _tier(score)
        flag  = " ★ CHOKEPOINT" if has_chp and row.get(_CHP_COL, False) else ""
        rows.append(f"  {ward:<14} {score:>7.3f}   [{tier}]{flag}")

    plain = (
        header
        + col_w
        + "\n"
        + "\n".join(rows)
        + textwrap.dedent(f"""

        ─────────────────────────────────────────────────────────────
        ★  Known infrastructure chokepoint
        CRITICAL ≥ 0.70  |  HIGH ≥ 0.50  |  MODERATE ≥ 0.30
        ─────────────────────────────────────────────────────────────
        This report was generated automatically by METSI-EWS,
        an early-warning system developed at {INSTITUTION}.

        Model  : XGBoost classifier  |  ROC-AUC {MODEL_AUC}
        Note   : Predictions carry inherent uncertainty and should be
                 validated against field inspection before operational use.
        ─────────────────────────────────────────────────────────────
        """)
    )

    # ── HTML ─────────────────────────────────────────────────────────────────
    row_html = ""
    for i, row in df.iterrows():
        ward  = str(row[ward_col])
        score = float(row[score_col])
        tier, colour = _tier(score)
        flag  = " ★" if has_chp and row.get(_CHP_COL, False) else ""
        bg    = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        row_html += (
            f'<tr style="background:{bg}">'
            f'<td style="padding:7px 14px;font-family:monospace">{ward}{flag}</td>'
            f'<td style="padding:7px 14px;text-align:center">{score:.3f}</td>'
            f'<td style="padding:7px 14px;color:{colour};font-weight:bold">{tier}</td>'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<body style="font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;
             max-width:700px;margin:32px auto;padding:0 16px">

  <h2 style="border-bottom:3px solid #1565C0;padding-bottom:10px;color:#1565C0">
    🚰 METSI-EWS — Water Infrastructure Risk Report
  </h2>

  <p style="color:#444;font-size:14px">
    <strong>City of Tshwane Metropolitan Municipality</strong><br>
    Generated: {now} &nbsp;|&nbsp; Horizon: {horizon} ({HORIZON_LABEL})
  </p>

  <table style="background:#EBF5FB;border-left:4px solid #1565C0;
                padding:12px 16px;border-radius:4px;margin:16px 0;
                font-size:14px;width:100%">
    <tr>
      <td><strong>{n_wards}</strong> wards at ≥ {int(threshold*100)}% risk</td>
      <td><strong style="color:#c0392b">{n_critical} CRITICAL</strong></td>
      <td><strong style="color:#e67e22">{n_high} HIGH</strong></td>
    </tr>
  </table>

  <table style="border-collapse:collapse;width:100%;font-size:14px">
    <thead>
      <tr style="background:#1565C0;color:#fff">
        <th style="padding:9px 14px;text-align:left">Ward</th>
        <th style="padding:9px 14px;text-align:center">Risk Score</th>
        <th style="padding:9px 14px;text-align:left">Tier</th>
      </tr>
    </thead>
    <tbody>{row_html}</tbody>
  </table>

  <p style="font-size:12px;color:#888;margin-top:16px">
    ★ = known infrastructure chokepoint &nbsp;|&nbsp;
    CRITICAL ≥ 0.70 &nbsp;|&nbsp; HIGH ≥ 0.50 &nbsp;|&nbsp; MODERATE ≥ 0.30
  </p>

  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
  <p style="font-size:11px;color:#aaa;line-height:1.6">
    Generated automatically by METSI-EWS ({INSTITUTION}, 2026).<br>
    Model: XGBoost classifier &nbsp;|&nbsp; ROC-AUC {MODEL_AUC}.<br>
    Predictions carry inherent uncertainty and must be validated
    against field inspection before operational use.
  </p>

</body></html>"""

    return plain, html


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_report(
    to_addrs: List[str],
    predictions_df: pd.DataFrame,
    smtp_cfg: Optional[dict] = None,
    subject: Optional[str] = None,
    top_n: int = 15,
    threshold: float = 0.30,
    from_name: str = "METSI-EWS Early Warning System",
) -> dict:
    """
    Compose and send the ward-risk report.

    Parameters
    ----------
    to_addrs       : List of recipient email addresses.
    predictions_df : DataFrame with risk scores (from predictions.csv).
    smtp_cfg       : Dict with keys host/port/user/password.
                     If None, read from environment variables.
    subject        : Override the default subject line.
    top_n          : Maximum wards to include in the report.
    threshold      : Minimum risk score to include.
    from_name      : Sender display name.

    Returns
    -------
    {"success": True}
    or
    {"success": False, "error": str}
    """
    try:
        cfg = smtp_cfg or load_smtp_cfg()

        if not to_addrs:
            raise ValueError("to_addrs must not be empty.")

        plain, html = compose_risk_report(
            predictions_df, top_n=top_n, threshold=threshold
        )

        now_label = datetime.now().strftime("%B %Y")
        subj = subject or f"METSI-EWS: Water Infrastructure Risk Report — {now_label}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subj
        msg["From"]    = f"{from_name} <{cfg['user']}>"
        msg["To"]      = ", ".join(to_addrs)

        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html,  "html",  "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], to_addrs, msg.as_string())

        return {"success": True}

    except Exception as exc:
        return {"success": False, "error": str(exc)}
