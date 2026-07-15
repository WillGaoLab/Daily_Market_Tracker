"""Minimal Streamlit dashboard for Daily Market Tracker."""

from __future__ import annotations

import csv
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from scripts.history import HistoryValidationError, read_history

PROJECT_ROOT = Path(__file__).resolve().parent
HISTORY_PATH = PROJECT_ROOT / "data" / "history.csv"
FIGURES_DIR = PROJECT_ROOT / "figures"
INSTRUMENTS = (
    ("sp500", "S&P 500"),
    ("nasdaq100", "Nasdaq-100 Futures"),
    ("vix", "VIX"),
    ("tnx", "U.S. 10-Year Treasury Yield"),
    ("dxy", "U.S. Dollar Index"),
    ("wti", "WTI Crude Oil"),
)
GA4_MEASUREMENT_ID = "G-B9DJEVW7SW"
CLARITY_PROJECT_ID = "x1tq0msm2n"


def render_analytics() -> None:
    """Load hosted-app analytics without adding visible interface content."""
    components.html(
        f"""
        <script async src="https://www.googletagmanager.com/gtag/js?id={GA4_MEASUREMENT_ID}"></script>
        <script>
            window.dataLayer = window.dataLayer || [];
            function gtag(){{dataLayer.push(arguments);}}

            const pageLocation = window.location.href;
            const pagePath = window.location.pathname + window.location.search + window.location.hash;

            if (!window.__dailyMarketTrackerGa4Loaded) {{
                window.__dailyMarketTrackerGa4Loaded = true;
                gtag("js", new Date());
                gtag("config", "{GA4_MEASUREMENT_ID}", {{
                    page_location: pageLocation,
                    page_path: pagePath
                }});
            }} else if (window.__dailyMarketTrackerLastGa4Page !== pageLocation) {{
                gtag("event", "page_view", {{
                    page_location: pageLocation,
                    page_path: pagePath
                }});
            }}
            window.__dailyMarketTrackerLastGa4Page = pageLocation;
        </script>
        <script>
            if (!window.__dailyMarketTrackerClarityLoaded) {{
                window.__dailyMarketTrackerClarityLoaded = true;
                (function(c,l,a,r,i,t,y){{
                    c[a]=c[a]||function(){{(c[a].q=c[a].q||[]).push(arguments)}};
                    t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
                    y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
                }})(window, document, "clarity", "script", "{CLARITY_PROJECT_ID}");
            }}
        </script>
        """,
        height=0,
        width=0,
    )


def load_history() -> list[dict[str, str]]:
    return sorted(read_history(HISTORY_PATH), key=lambda row: row["date"], reverse=True)


st.set_page_config(page_title="Daily Market Tracker", layout="wide")
render_analytics()
st.title("Daily Market Tracker")
try:
    rows = load_history()
except HistoryValidationError as error:
    st.error(f"data/history.csv is invalid: {error}")
    st.stop()
if not rows:
    st.info("No market history is available yet.")
    st.stop()

latest = rows[0]
latest_date = latest["date"]
st.caption(f"Latest U.S. trading day: {latest_date}")
image_path = FIGURES_DIR / f"{latest_date}.png"
if image_path.exists():
    st.image(str(image_path), width="stretch")
else:
    st.warning("The latest fingerprint image has not been generated yet.")

st.subheader("Latest raw data")
latest_data = []
for key, label in INSTRUMENTS:
    latest_data.append(
        {
            "Indicator": label,
            "Previous daily close": float(latest[f"{key}_previous_close"]),
            "Open": float(latest[f"{key}_open"]),
            "Gap": float(latest[f"{key}_gap"]),
            "Gap %": float(latest[f"{key}_gap_pct"]),
        }
    )
st.dataframe(latest_data, width="stretch", hide_index=True)

st.subheader("Historical data")
st.dataframe(rows, width="stretch", hide_index=True)
