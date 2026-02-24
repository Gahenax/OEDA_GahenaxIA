from __future__ import annotations

import time
import sqlite3
from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# Configuration for the Gahenax UI
st.set_option('deprecation.showPyplotGlobalUse', False)

@dataclass
class DBConfig:
    path: str = "ua_ledger.sqlite"
    table: str = "ua_ledger"


def read_ledger(db: DBConfig, limit: int = 5000) -> pd.DataFrame:
    if not os.path.exists(db.path):
        return pd.DataFrame()
    con = sqlite3.connect(db.path)
    try:
        # Pull newest rows
        q = f"""
        SELECT
            id, timestamp_start, timestamp_end, user_id, session_id, request_id,
            engine_version, contract_version,
            ua_spend, delta_s, delta_s_per_ua,
            latency_ms, contract_valid, h_rigidity, work_units, evidence_hash
        FROM {db.table}
        ORDER BY id DESC
        LIMIT ?
        """
        df = pd.read_sql_query(q, con, params=(limit,))
    finally:
        con.close()

    if df.empty:
        return df

    # Normalize types
    df["timestamp_end"] = pd.to_datetime(df["timestamp_end"], errors="coerce", utc=True)
    df["contract_valid"] = df["contract_valid"].astype(int)
    df = df.sort_values("id")  # oldest -> newest for time plots
    return df


def pctl(series: pd.Series, q: float) -> float:
    s = series.dropna()
    if s.empty:
        return float("nan")
    return float(s.quantile(q))


def metric_panel(df: pd.DataFrame) -> Tuple[float, float, float, float, float]:
    lat_p50 = pctl(df["latency_ms"], 0.50)
    lat_p95 = pctl(df["latency_ms"], 0.95)
    pass_rate = float(df["contract_valid"].mean()) if len(df) else float("nan")
    ua_med = pctl(df["ua_spend"], 0.50)
    dsua_med = pctl(df["delta_s_per_ua"], 0.50) if "delta_s_per_ua" in df else float("nan")
    return lat_p50, lat_p95, pass_rate, ua_med, dsua_med


def fig_timeseries(df: pd.DataFrame, y: str, title: str) -> plt.Figure:
    fig = plt.figure(figsize=(10, 4))
    ax = fig.add_subplot(111)
    d = df.dropna(subset=["timestamp_end", y])
    ax.plot(d["timestamp_end"], d[y], marker='o', markersize=4, linestyle='-', alpha=0.7)
    ax.set_title(title)
    ax.set_xlabel("time (UTC)")
    ax.set_ylabel(y)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    return fig


def fig_hist(df: pd.DataFrame, col: str, title: str, bins: int = 30) -> plt.Figure:
    fig = plt.figure(figsize=(10, 4))
    ax = fig.add_subplot(111)
    d = df[col].dropna()
    ax.hist(d, bins=bins, color='skyblue', edgecolor='black', alpha=0.7)
    ax.set_title(title)
    ax.set_xlabel(col)
    ax.set_ylabel("count")
    ax.grid(True, alpha=0.3)
    return fig


def hard_gates(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    FCD hard gate: contract must be 100% in the observed window.
    """
    if df.empty:
        return False, "No data in ledger."
    pass_rate = float(df["contract_valid"].mean())
    if pass_rate < 1.0:
        return False, f"DEATH: Contract pass-rate < 100% (now {pass_rate:.3f})."
    return True, "OK: Contract pass-rate = 100%."

import os

def main() -> None:
    st.set_page_config(page_title="Gahenax Rigor Console", layout="wide")
    st.title("🛡️ Consola de Rigor (FCD-1.0)")
    st.markdown("Instrumento de auditoría para la validación de la soberanía inferencial de Gahenax.")

    # Sidebar controls
    st.sidebar.header("Governance Controls")
    db_path = st.sidebar.text_input("ua_ledger.sqlite path", value="ua_ledger.sqlite")
    limit = st.sidebar.slider("Rows to analyze", min_value=100, max_value=20000, value=5000, step=100)
    refresh = st.sidebar.checkbox("Live refresh (Warp Mode)", value=False)
    refresh_s = st.sidebar.slider("Refresh interval (s)", min_value=1, max_value=30, value=5, step=1)

    db = DBConfig(path=db_path)

    df = read_ledger(db, limit=limit)

    # Hard Gates
    st.header("1. Hard Sovereignty Gates")
    ok, msg = hard_gates(df)
    if ok:
        st.success(f"**STATUS**: {msg}")
    else:
        st.error(f"**STATUS**: {msg}")

    if df.empty:
        st.warning("Ledger is empty. Waiting for operational data...")
        if refresh:
            time.sleep(refresh_s)
            st.rerun()
        st.stop()

    # Top metrics panel
    lat_p50, lat_p95, pass_rate, ua_med, dsua_med = metric_panel(df)
    c1, c2, c3, c4, c5 = st.columns(5)
    
    # Latency formatting: use ms or µs
    if lat_p50 < 1.0:
        c1.metric("Latency p50", f"{lat_p50*1000:.0f} µs", help="Stored in ms, displayed in microseconds for precision.")
    else:
        c1.metric("Latency p50 (ms)", f"{lat_p50:.2f}")

    if lat_p95 < 1.0:
        c2.metric("Latency p95", f"{lat_p95*1000:.0f} µs")
    else:
        c2.metric("Latency p95 (ms)", f"{lat_p95:.2f}")

    c3.metric("Contract Pass-rate", f"{pass_rate:.3%}")
    c4.metric("UA Median Cost", f"{ua_med:.2f} UA")
    c5.metric("ΔS/UA Efficiency", f"{dsua_med:.6f}" if pd.notna(dsua_med) else "n/a")

    st.divider()

    # Claim Visualization
    st.header("2. Falsifiability Analysis (A1-A4)")
    
    tab1, tab2, tab3 = st.tabs(["Performance (A2)", "Efficiency (A1/A4)", "Structural Rigidity (A3)"])

    with tab1:
        st.subheader("Claim A2: Constant Latency & Schema Adherence")
        l_col, r_col = st.columns(2)
        l_col.pyplot(fig_timeseries(df, "latency_ms", "Latency Drift (ms)"), clear_figure=True)
        r_col.pyplot(fig_hist(df, "latency_ms", "Latency Distribution (ms)"), clear_figure=True)

    with tab2:
        st.subheader("Claim A1/A4: Work Reduction & UA Efficiency")
        l_col, r_col = st.columns(2)
        l_col.pyplot(fig_timeseries(df, "delta_s_per_ua", "Efficiency over time (ΔS/UA)"), clear_figure=True)
        r_col.pyplot(fig_hist(df, "delta_s_per_ua", "Efficiency Distribution"), clear_figure=True)
        
        st.pyplot(fig_timeseries(df, "work_units", "Work Units (Processed logical dimensions)"), clear_figure=True)

    with tab3:
        st.subheader("Claim A3: Chronos-Hodge Structural Stability")
        if df["h_rigidity"].notna().any():
            l_col, r_col = st.columns(2)
            l_col.pyplot(fig_timeseries(df, "h_rigidity", "H-Rigidity Index (Stochasticity)"), clear_figure=True)
            r_col.pyplot(fig_hist(df, "h_rigidity", "Rigidity Distribution"), clear_figure=True)
        else:
            st.info("Insufficient H-Rigidity data in current window.")

    st.divider()

    # Evidence viewer
    st.header("3. Immutable Raw Evidence")
    cols = [
        "id", "timestamp_start", "timestamp_end", "user_id", "session_id", "request_id",
        "ua_spend", "delta_s_per_ua", "latency_ms", "contract_valid",
        "h_rigidity", "work_units", "evidence_hash",
    ]
    st.dataframe(df[cols].tail(100), use_container_width=True)

    # Live refresh loop
    if refresh:
        time.sleep(refresh_s)
        st.rerun()


if __name__ == "__main__":
    main()
