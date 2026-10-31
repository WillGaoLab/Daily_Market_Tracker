"""Minimal Streamlit dashboard for Daily Market Tracker."""

from __future__ import annotations

from pathlib import Path
import json
import xml.etree.ElementTree as ET

import streamlit as st
import streamlit.components.v1 as components
from scripts.history import MISSING_VALUE, HistoryValidationError, read_history
from scripts.interactive_fingerprint import component_html, render_svg, values_for

PROJECT_ROOT = Path(__file__).resolve().parent
HISTORY_PATH = PROJECT_ROOT / "data" / "history.csv"
FIGURES_DIR = PROJECT_ROOT / "figures"
INSTRUMENTS = (
    ("sp500", "S&P 500"),
    ("nasdaq100", "Nasdaq-100 Futures"),
    ("dow", "Dow Jones Industrial Average"),
    ("vix", "VIX"),
    ("bitcoin", "Bitcoin"),
    ("gold", "Gold Futures"),
    ("tnx", "U.S. 10-Year Treasury Yield"),
    ("dxy", "U.S. Dollar Index"),
    ("wti", "WTI Crude Oil"),
)
GA4_MEASUREMENT_ID = "G-B9DJEVW7SW"
CLARITY_PROJECT_ID = "xn38mjsmco"


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


def display_value(value: str) -> float | None:
    """Return a numeric history value, preserving migrated unavailable values."""
    return None if value == MISSING_VALUE else float(value)


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
selected_date = st.selectbox("Fingerprint date", [row["date"] for row in rows])
selected = next(row for row in rows if row["date"] == selected_date)

@st.cache_data(show_spinner=False)
def interactive_svg(day: str, history_contents: str) -> str:
    # The history contents are part of the cache key, including source revisions.
    stored = FIGURES_DIR / f"{day}.svg"
    if stored.exists():
        text = stored.read_text()
        svg_root = ET.fromstring(text)
        record = next(row for row in read_history(HISTORY_PATH) if row["date"] == day)
        if svg_root.get("data-fingerprint-date") == day and json.loads(svg_root.get("data-fingerprint-values", "null")) == values_for(record):
            return text
    return render_svg(day, HISTORY_PATH)

try:
    with st.spinner("Loading interactive fingerprint…"):
        svg = interactive_svg(selected_date, HISTORY_PATH.read_text())
        components.html(component_html(selected, svg), height=730, scrolling=True)
except ValueError as error:
    st.info(str(error))

image_path = FIGURES_DIR / f"{selected_date}.png"
if image_path.exists():
    with st.expander("Original PNG"):
        st.image(str(image_path), width="stretch")

st.subheader(f"Raw data · {selected_date}")
latest_data = []
for key, label in INSTRUMENTS:
    is_bitcoin = key == "bitcoin"
    latest_data.append(
        {
            "Indicator": label,
            "Previous close / UTC open": display_value(
                selected[f"{key}_{'open' if is_bitcoin else 'previous_close'}"]
            ),
            "Open / current price": display_value(
                selected[f"{key}_{'current' if is_bitcoin else 'open'}"]
            ),
            "Gap / change": display_value(selected[f"{key}_{'change' if is_bitcoin else 'gap'}"]),
            "Gap % / change %": display_value(
                selected[f"{key}_{'change_pct' if is_bitcoin else 'gap_pct'}"]
            ),
        }
    )
st.caption(
    "Bitcoin compares its 00:00 UTC daily open with Yahoo Finance's current market price; "
    "all other indicators compare the previous close with their daily open."
)
st.dataframe(latest_data, width="stretch", hide_index=True)

st.subheader("Historical data")
st.dataframe(rows, width="stretch", hide_index=True)
