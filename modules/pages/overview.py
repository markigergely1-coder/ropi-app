import streamlit as st
import pandas as pd

from modules.db import get_attendance_rows_fs
from modules.utils import generate_tuesday_dates, parse_date_str


def render_attendance_overview_page(fs_db):
    st.title("📅 Alkalmak Áttekintése")
    st.markdown("Itt ellenőrizheted a résztvevők számát és névsorát az elmúlt 8 alkalomra visszamenőleg.")
    dates = generate_tuesday_dates(past_count=8, future_count=0)
    selected_date_str = st.selectbox("Válassz egy dátumot az áttekintéshez:", dates)
    if selected_date_str:
        selected_date = parse_date_str(selected_date_str)
        with st.spinner("Adatok betöltése a Firestore-ból..."):
            df_fs = get_attendance_rows_fs(fs_db)
        if df_fs.empty:
            st.warning("Nem sikerült betölteni a Firestore adatokat.")
            return
        yes_set = set()
        no_set = set()
        for _, row in df_fs.iterrows():
            name = str(row["Név"]).strip() if pd.notna(row["Név"]) else ""
            is_coming = str(row["Jön-e"]).strip() if pd.notna(row["Jön-e"]) else ""
            if not name:
                continue
            mode_val = str(row["Mód"]).strip().lower() if pd.notna(row["Mód"]) else "valós"
            if mode_val == "teszt":
                continue
            reg_val = str(row["Regisztráció Időpontja"]) if pd.notna(row["Regisztráció Időpontja"]) else ""
            evt_val = str(row["Alkalom Dátuma"]) if pd.notna(row["Alkalom Dátuma"]) else ""
            rel_date = parse_date_str(evt_val) or parse_date_str(reg_val)
            if rel_date == selected_date:
                if is_coming == "Yes":
                    yes_set.add(name)
                elif is_coming == "No":
                    no_set.add(name)
        final_attendees = sorted(list(yes_set - no_set))
        count = len(final_attendees)
        st.markdown("---")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric(label="Résztvevők száma", value=f"{count} fő")
        with col2:
            if count > 0:
                st.subheader("Résztvevők névsora:")
                name_cols = st.columns(2)
                for i, name in enumerate(final_attendees):
                    name_cols[i % 2].markdown(f"✅ **{name}**")
            else:
                st.info("Erre az alkalomra nincs érvényes regisztráció.")
