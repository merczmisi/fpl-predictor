import streamlit as st
import pandas as pd

from fpl_session import FPLSession
from fpl_draft.predict import (
    compute_expected_points_for_entry,
    compute_expected_points_for_entry_from_my_team,
)


@st.cache_resource
def get_fpl_session() -> FPLSession:
    """Reuse a single authenticated session (and its browser profile) across reruns."""
    return FPLSession()


st.set_page_config(page_title="FPL Draft Dashboard", layout="wide")

st.title("FPL Draft — Expected Points Dashboard")

st.sidebar.header("Inputs")
entry_id = st.sidebar.number_input("Entry ID", value=293299, step=1)
use_my_team = st.sidebar.checkbox("Use my-team (no event)", value=True)
event_id = st.sidebar.number_input("Event ID", value=1, step=1)

if st.sidebar.button("Compute expected points"):
    with st.spinner("Fetching data and computing expected points..."):
        session = get_fpl_session()

        try:
            if use_my_team:
                df = compute_expected_points_for_entry_from_my_team(session, int(entry_id))
            else:
                df = compute_expected_points_for_entry(session, int(entry_id), int(event_id))

            # Build display name
            if "web_name" in df.columns:
                df["display_name"] = df["web_name"]
            else:
                first = df.get("first_name") or df.get("first_name")
                second = df.get("second_name") or df.get("second_name")
                df["display_name"] = (
                    df["first_name"].fillna("")
                    + " "
                    + df["second_name"].fillna("")
                )

            st.subheader(f"Expected points for entry {entry_id}")

            cols = [c for c in ["display_name", "expected_points", "fixture_adjusted_points", "base_points", "fdr_multiplier"] if c in df.columns]

            st.dataframe(df[cols].sort_values("expected_points", ascending=False).reset_index(drop=True))

            if "display_name" in df.columns and "expected_points" in df.columns:
                chart_df = df.set_index("display_name")["expected_points"].sort_values(ascending=False)
                st.bar_chart(chart_df)

        except Exception as e:
            st.error(f"Error computing expected points: {e}")
