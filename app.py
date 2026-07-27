"""
METSI-EWS — City of Tshwane.

Run with:  streamlit run app.py

Supports two data sources via the sidebar toggle:
  - REAL  : data_real/  — trained on tshwane_real_panel.csv (real incidents).
            Early baseline. Read the warning on the Model Validation tab
            before quoting any number from this mode to a stakeholder.
  - SYNTHETIC : data/  — trained on the synthetic panel (src/generate_synthetic_data.py).
            Validates that the pipeline works end-to-end. Says nothing about
            real-world performance.

The two sources have different schemas (ward_id/month vs unit_id/week_start,
different feature sets, different label columns) — DATA_SOURCES below is the
single place that maps those differences so the rest of the page can stay
generic.
"""

import json
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.metrics import roc_curve
from streamlit_folium import st_folium

from tab_notify import render_notify_tab

BASE_DIR = Path(__file__).resolve().parent

st.set_page_config(page_title="METSI-EWS — Tshwane", layout="wide")

DATA_SOURCES = {
    "real": {
        "label": "Real Tshwane incidents (early baseline)",
        "dir": BASE_DIR / "data" / "model_outputs" / "real",
        "id_col": "ward_id",
        "id_label": "Ward",
        "time_col": "month",
        "time_index_col": "month_index",
        "time_label": "month",
        "label_col": "failure_within_3mo",
        "label_display": "failure-within-3mo",
        "rate_key": "test_failure_rate",
        "period_keys": ("train_months", "test_months"),
        "hover_features": ["months_since_last_failure", "cumulative_failures_to_date", "is_known_chokepoint", "wss_bdrr"],
        "table_columns": ["ward_id", "risk_score", "wss_bdrr", "area_km2", "months_since_last_failure",
                           "cumulative_failures_to_date", "is_known_chokepoint"],
        "equity_feature": "informal_settlement_pct",  # Census 2011 SAL — Dwellings + Piped Water (Stats SA, July 2026)
    },
    "synthetic": {
        "label": "Synthetic data (pipeline validation only)",
        "dir": BASE_DIR / "data" / "model_outputs" / "synthetic",
        "id_col": "unit_id",
        "id_label": "Unit",
        "time_col": "week_start",
        "time_index_col": "week_index",
        "time_label": "week",
        "label_col": "burst_next_week",
        "label_display": "burst-next-week",
        "rate_key": "test_burst_rate",
        "period_keys": ("train_weeks", "test_weeks"),
        "hover_features": ["infra_age_years", "nrw_pct", "days_since_maintenance"],
        "table_columns": ["unit_id", "risk_score", "infra_age_years", "nrw_pct",
                           "days_since_maintenance", "historical_incidents_90d", "is_known_hotspot"],
        "equity_feature": "informal_settlement_pct",
    },
}


@st.cache_data
def load_data(data_dir_str: str):
    data_dir = Path(data_dir_str)
    predictions = pd.read_csv(data_dir / "predictions.csv")
    shap_values = pd.read_csv(data_dir / "shap_values.csv")
    with open(data_dir / "metrics.json") as f:
        metrics = json.load(f)
    # Merge Census 2011 SAL equity features if available (real data only)
    equity_path = BASE_DIR / "data" / "processed" / "census_sal_equity.csv"
    if equity_path.exists() and "ward_id" in predictions.columns:
        equity = pd.read_csv(equity_path)[["ward_id", "informal_settlement_pct", "no_piped_water_pct"]]
        predictions = predictions.merge(equity, on="ward_id", how="left")
    return predictions, shap_values, metrics


source_key = st.sidebar.radio(
    "Data source",
    options=list(DATA_SOURCES.keys()),
    format_func=lambda k: DATA_SOURCES[k]["label"],
    index=0,  # defaults to "real"
)
cfg = DATA_SOURCES[source_key]

predictions, shap_df, metrics = load_data(str(cfg["dir"]))

st.title("💧 METSI-EWS — City of Tshwane")
if source_key == "real":
    st.caption(
        "Running on **real** incident data — 50 geocoded Tshwane incidents, Aug 2019–Jun 2026. "
        "Features: recency, cumulative failures, known chokepoint flag, ward area, calendar/season, "
        "NRW (municipal constant), and **WSS Blue Drop Risk Rating** (ward-varying, DWS BD PAT 2025). "
        "Pipe age, material, and maintenance data still pending (IMQS Pipe Priority Programme request sent). "
        "ROC-AUC 0.694 on held-out test set — genuine signal for repeat-failure wards, "
        "limited for first-time failures."
    )
else:
    st.caption(
        "Running on **synthetic** data. Unit IDs stand in for Tshwane's 107 wards until real "
        "boundaries/zones and more city data are in hand. This mode validates that the pipeline "
        "works end-to-end — it says nothing about real-world performance."
    )

latest_time_idx = predictions[cfg["time_index_col"]].max()
latest_time_label = predictions.loc[
    predictions[cfg["time_index_col"]] == latest_time_idx, cfg["time_col"]
].iloc[0]
latest = predictions[predictions[cfg["time_index_col"]] == latest_time_idx].sort_values(
    "risk_score", ascending=False
)

tab_map, tab_table, tab_signal, tab_validation, tab_equity, tab_send = st.tabs(
    ["📍 Risk Ranking", f"📋 {cfg['id_label']} Table", "🔍 Signal Explorer", "✅ Model Validation", "⚖️ Equity Check", "📤 Send Report"]
)

# ---------------------------------------------------------------------------
# TAB 1: Risk Ranking
# ---------------------------------------------------------------------------
with tab_map:
    st.subheader(f"Ward risk map — {cfg['time_label']} {latest_time_label}")

    if source_key == "real":
        # --- Choropleth map (real mode) ---
        @st.cache_data
        def load_ward_geo():
            gdf = gpd.read_file(BASE_DIR / "data" / "raw" / "tshwane_wards_2020.geojson")
            if gdf.crs is None:
                gdf = gdf.set_crs(epsg=4326)
            gdf = gdf.to_crs(epsg=4326)
            gdf["geometry"] = gdf.geometry.buffer(0)
            return gdf

        gdf_wards = load_ward_geo()
        merged = gdf_wards.merge(
            latest[["ward_id", "risk_score"] + [f for f in cfg["hover_features"] if f in latest.columns]],
            left_on="WardLabel", right_on="ward_id", how="left",
        )
        merged["risk_score"] = merged["risk_score"].fillna(0).round(1)
        # Cast any non-serialisable columns (e.g. Date Timestamps) to string
        for col in merged.columns:
            if col == "geometry":
                continue
            if hasattr(merged[col], "dt") or str(merged[col].dtype).startswith("datetime"):
                merged[col] = merged[col].astype(str)

        m = folium.Map(
            location=[-25.75, 28.23], zoom_start=10,
            tiles="CartoDB positron", prefer_canvas=True,
        )

        choropleth = folium.Choropleth(
            geo_data=merged.__geo_interface__,
            data=merged[["WardLabel", "risk_score"]],
            columns=["WardLabel", "risk_score"],
            key_on="feature.properties.WardLabel",
            fill_color="YlOrRd",
            fill_opacity=0.75,
            line_opacity=0.3,
            line_color="#555",
            legend_name="Failure risk score (0–100)",
            nan_fill_color="#cccccc",
            highlight=True,
        ).add_to(m)

        # Tooltip on hover
        folium.GeoJson(
            merged.__geo_interface__,
            style_function=lambda f: {
                "fillOpacity": 0, "weight": 0,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["WardLabel", "risk_score"] + [
                    f for f in cfg["hover_features"] if f in merged.columns
                ],
                aliases=["Ward", "Risk score (0–100)"] + [
                    f.replace("_", " ").title()
                    for f in cfg["hover_features"] if f in merged.columns
                ],
                localize=True, sticky=True,
            ),
        ).add_to(m)

        st_folium(m, width="100%", height=560, returned_objects=[])

        st.caption(
            f"Ward risk scores for **{latest_time_label}** — darker red = higher predicted failure risk. "
            "Scores spread 4–93/100. Hover over any ward for detail. "
            "Known chokepoints (TSH_58 Bosman Station, TSH_80 Salvokop) and high-BDRR wards "
            "(TSH_102/103/105 Bronkhorstpruit, TSH_49 Hammanskraal) show elevated scores. "
            "See Model Validation for honest caveats."
        )

        st.divider()
        st.subheader("Top at-risk wards")
        top_n = st.slider("Show top N wards", 5, 50, 15)
        top_units = latest.head(top_n)
        fig_bar = px.bar(
            top_units.sort_values("risk_score"),
            x="risk_score", y=cfg["id_col"], orientation="h",
            color="risk_score", color_continuous_scale="YlOrRd",
            labels={"risk_score": "Risk score (0–100)", cfg["id_col"]: "Ward"},
            hover_data=cfg["hover_features"],
        )
        fig_bar.update_layout(height=max(350, top_n * 22))
        st.plotly_chart(fig_bar, width="stretch")

    else:
        # --- Synthetic mode: keep existing bar chart ---
        st.caption(
            "Placeholder ranked view. Switch to Real Data mode (sidebar) for the choropleth map."
        )
        top_n = st.slider(f"Show top N {cfg['id_label'].lower()}s", 5, 50, 15)
        top_units = latest.head(top_n)
        fig = px.bar(
            top_units.sort_values("risk_score"),
            x="risk_score", y=cfg["id_col"], orientation="h",
            color="risk_score", color_continuous_scale="OrRd",
            labels={"risk_score": "Risk score (0-100)", cfg["id_col"]: cfg["id_label"]},
            hover_data=cfg["hover_features"],
        )
        fig.update_layout(height=max(400, top_n * 22))
        st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# TAB 2: Unit / Ward Table
# ---------------------------------------------------------------------------
with tab_table:
    st.subheader(f"All {cfg['id_label'].lower()}s — {cfg['time_label']} {latest_time_label}")
    sort_options = [c for c in cfg["table_columns"] if c != cfg["id_col"]]
    sort_col = st.selectbox("Sort by", sort_options)
    st.dataframe(
        latest[cfg["table_columns"]]
        .sort_values(sort_col, ascending=False)
        .reset_index(drop=True),
        width="stretch",
        height=600,
    )

# ---------------------------------------------------------------------------
# TAB 3: Signal Explorer — per-unit SHAP breakdown
# ---------------------------------------------------------------------------
with tab_signal:
    st.subheader(f"Why is this {cfg['id_label'].lower()} flagged?")
    id_options = latest[cfg["id_col"]].tolist()
    selected_id = st.selectbox(f"Select {cfg['id_label'].lower()}", id_options)

    row = shap_df[
        (shap_df[cfg["id_col"]] == selected_id)
        & (shap_df[cfg["time_col"]] == shap_df[cfg["time_col"]].max())
    ]
    if row.empty:
        row = shap_df[shap_df[cfg["id_col"]] == selected_id].iloc[[-1]]

    shap_cols = [c for c in shap_df.columns if c.startswith("shap_")]
    contributions = row[shap_cols].iloc[0]
    contributions.index = [c.replace("shap_", "") for c in contributions.index]
    contributions = contributions.sort_values()

    fig = go.Figure(go.Bar(
        x=contributions.values, y=contributions.index, orientation="h",
        marker_color=["#d62728" if v > 0 else "#1f77b4" for v in contributions.values],
    ))
    fig.update_layout(
        title=f"Feature contributions to {selected_id}'s risk score "
              f"({row['risk_score'].values[0]:.1f}/100)",
        xaxis_title="SHAP value (push toward higher risk →)",
        height=450,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("Red bars push risk up, blue bars pull it down. Bar length = strength of that signal.")
    if source_key == "real":
        st.caption(
            "Contributing features (by mean |SHAP|): ward area, WSS Blue Drop Risk Rating, "
            "calendar month, months since last failure, known-chokepoint flag, cumulative failures. "
            "NRW (nrw_pct) is a municipal constant — its bar is always zero. "
            "Wards with no prior failure history and mid-range BDRR will show small bars across "
            "the board; that is the model correctly expressing uncertainty, not a bug."
        )

# ---------------------------------------------------------------------------
# TAB 4: Model Validation
# ---------------------------------------------------------------------------
with tab_validation:
    st.subheader(f"Validation metrics (held-out test {cfg['time_label']}s)")
    col1, col2, col3 = st.columns(3)
    col1.metric("ROC AUC", f"{metrics['roc_auc']:.3f}")
    col2.metric("PR AUC", f"{metrics['pr_auc']:.3f}")
    col3.metric(f"Test {cfg['label_display']} rate", f"{metrics[cfg['rate_key']] * 100:.2f}%")

    train_key, test_key = cfg["period_keys"]
    st.caption(
        f"Trained on {cfg['time_label']}s {metrics[train_key][0]}–{metrics[train_key][1]}, "
        f"tested on {metrics[test_key][0]}–{metrics[test_key][1]} "
        "(chronological split — never random, to avoid leaking future information into training)."
    )

    if source_key == "real":
        n_test_pos = metrics.get("test_positives")
        st.warning(
            f"⚠️ **Honest caveats — read before quoting these numbers.** "
            f"Test fold has {n_test_pos} positive ward-months across 50 real incidents (city-wide, Aug 2019–Jun 2026). "
            "**What is working:** Scores now spread 4–93/100 (no longer flat). "
            "Ward 22 ranks top 1.2% for its confirmed March 2026 failure. "
            "TSH_58 (Bosman Station chokepoint) consistently ranks top 6–11%. "
            "WSS Blue Drop Risk Rating is the 2nd-ranked SHAP feature — wards served by "
            "high-risk water supply systems (Bronkhorstpruit WTW 74%, Temba WTW 73%) "
            "are correctly flagged as elevated risk. "
            "**What is not working yet:** First-time failure wards with average BDRR "
            "(TSH_70, TSH_36, TSH_29) rank 25–69% — the model cannot flag them without "
            "pipe-age or maintenance data. IMQS Pipe Priority Programme request is sent. "
            "PR-AUC is 0.025 vs 0.008 base rate — weak precision at high recall. "
            "ROC-AUC 0.694 with 14 test positives is a directional read, not a stable estimate."
        )
    else:
        st.warning(
            "⚠️ This AUC is on **synthetic** data and deliberately not over-tuned. "
            "It validates that the pipeline works end-to-end — it says nothing about real-world "
            "performance, which depends entirely on the real data once it's fully in hand."
        )

    if cfg["label_col"] in predictions.columns:
        fpr, tpr, _ = roc_curve(predictions[cfg["label_col"]], predictions["risk_score"] / 100)
        fig_roc = px.line(
            x=fpr, y=tpr, labels={"x": "False Positive Rate", "y": "True Positive Rate"},
            title=f"ROC Curve (test {cfg['time_label']}s)",
        )
        fig_roc.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line=dict(dash="dash", color="gray"))
        st.plotly_chart(fig_roc, width="stretch")

# ---------------------------------------------------------------------------
# TAB 5: Equity Check — adapted from GBV-EWS's Fairness Audit for the water domain
# ---------------------------------------------------------------------------
with tab_equity:
    st.subheader("Is the model under-flagging informal/under-serviced areas?")
    if cfg["equity_feature"] is None:
        st.info(
            "Not available yet on real data — no socioeconomic layer is merged into the ward "
            "panel. Planned source: Census 2011 Small Area Layer via the Adrian Frith Community "
            "Profile Platform (census2011.adrianfrith.com), providing dwelling type, piped water "
            "access, and informal settlement classification at small-area level. Census 2022 "
            "socioeconomic data was confirmed unavailable by Statistics South Africa due to data "
            "quality concerns; the 2011 SAL is the appropriate publicly accessible alternative. "
            "Once integrated, this tab will compare predicted risk against ward-level "
            "informality/deprivation measures. Switch to the synthetic source in the sidebar to "
            "see how this check will work once that data exists."
        )
    else:
        st.caption(
            "Real infrastructure ML risk: historically under-invested areas often have *less* "
            "monitoring data, which can make models under-predict their risk, not over-predict it. "
            "Worth checking this every time real data swaps in."
        )
        bins = pd.qcut(latest[cfg["equity_feature"]], 4, duplicates="drop")
        equity_check = latest.groupby(bins)["risk_score"].mean().reset_index()
        equity_check.columns = [f"{cfg['equity_feature']} (quartile)", "Mean predicted risk score"]
        # pd.qcut produces Interval objects; Plotly's JSON encoder can't serialize them,
        # so cast to string before they hit the figure.
        equity_check[f"{cfg['equity_feature']} (quartile)"] = equity_check[
            f"{cfg['equity_feature']} (quartile)"
        ].astype(str)
        fig_eq = px.bar(equity_check, x=f"{cfg['equity_feature']} (quartile)", y="Mean predicted risk score",
                         color_discrete_sequence=["#1E88E5"])
        fig_eq.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_eq, use_container_width=True)
        st.caption(
            "If mean risk score does NOT rise with informal settlement %, that's a signal the model "
            "may be missing risk in exactly the areas most likely to be under-monitored."
        )
        # ── Piped water access chart ────────────────────────────────────────
        if "no_piped_water_pct" in latest.columns:
            st.markdown("#### Water access deprivation vs. predicted risk")
            bins_pw = pd.qcut(latest["no_piped_water_pct"], 4, duplicates="drop")
            pw_check = latest.groupby(bins_pw)["risk_score"].mean().reset_index()
            pw_check.columns = ["No piped water % (quartile)", "Mean predicted risk score"]
            pw_check["No piped water % (quartile)"] = pw_check["No piped water % (quartile)"].astype(str)
            fig_pw = px.bar(pw_check, x="No piped water % (quartile)", y="Mean predicted risk score",
                            color_discrete_sequence=["#FB8C00"])
            fig_pw.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pw, use_container_width=True)
            st.caption(
                "Wards with higher proportions of households lacking piped water access "
                "may face compounding infrastructure and service delivery risk."
            )

# ---------------------------------------------------------------------------
# TAB 6: Send Report
# ---------------------------------------------------------------------------
with tab_send:
    render_notify_tab(latest)
