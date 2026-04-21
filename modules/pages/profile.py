import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

from modules.db import get_attendance_rows_fs
from modules.utils import parse_date_str
from modules.config import HUNGARY_TZ


def _get_player_attendance(df_fs: pd.DataFrame, name: str) -> pd.DataFrame:
    """Visszaadja a játékos összes érvényes (Yes, nem teszt) jelenlétét dátummal."""
    if df_fs.empty:
        return pd.DataFrame(columns=["date"])

    records = []
    seen = set()  # (name, date) deduplikálás

    for _, row in df_fs.iterrows():
        r_name = str(row["Név"]).strip() if pd.notna(row["Név"]) else ""
        if r_name != name:
            continue
        is_coming = str(row["Jön-e"]).strip() if pd.notna(row["Jön-e"]) else ""
        mode = str(row["Mód"]).strip().lower() if pd.notna(row["Mód"]) else "valós"
        if mode == "teszt" or is_coming != "Yes":
            continue
        evt = str(row["Alkalom Dátuma"]) if pd.notna(row["Alkalom Dátuma"]) else ""
        reg = str(row["Regisztráció Időpontja"]) if pd.notna(row["Regisztráció Időpontja"]) else ""
        d = parse_date_str(evt) or parse_date_str(reg)
        if d and (name, d) not in seen:
            seen.add((name, d))
            records.append({"date": d, "year": d.year, "month": d.month})

    return pd.DataFrame(records) if records else pd.DataFrame(columns=["date", "year", "month"])


def render_player_profile_page(fs_db):
    st.title("📊 Játékos Profil")

    # --- Adatok betöltése ---
    with st.spinner("Adatok betöltése..."):
        df_all = get_attendance_rows_fs(fs_db)

    if df_all.empty:
        st.warning("Nem sikerült betölteni az adatokat.")
        return

    # --- Játékos nevei (deduplikált, rendezett) ---
    all_names = sorted(set(
        str(r).strip() for r in df_all["Név"].dropna()
        if str(r).strip() and str(r).strip() not in ("nan", "")
    ))

    if not all_names:
        st.info("Nincsenek elérhető játékosok.")
        return

    col_sel, col_year = st.columns([2, 1])
    with col_sel:
        selected_name = st.selectbox(
            "👤 Válassz játékost:",
            all_names,
            key="profile_name_sel"
        )
    with col_year:
        current_year = datetime.now(HUNGARY_TZ).year
        available_years = sorted(
            set(df_all["Alkalom Dátuma"].dropna().apply(
                lambda x: parse_date_str(str(x))
            ).dropna().apply(lambda d: d.year)),
            reverse=True
        )
        if not available_years:
            available_years = [current_year]
        selected_year = st.selectbox(
            "📅 Év (havi diagramhoz):",
            available_years,
            key="profile_year_sel"
        )

    st.markdown("---")

    # --- Szűrt adatok ---
    df_player = _get_player_attendance(df_all, selected_name)

    if df_player.empty:
        st.info(f"**{selected_name}** nincs bejegyezve egyetlen alkalomra sem.")
        return

    total = len(df_player)
    this_year_count = len(df_player[df_player["year"] == current_year])
    this_month = datetime.now(HUNGARY_TZ).month
    this_month_count = len(df_player[
        (df_player["year"] == current_year) & (df_player["month"] == this_month)
    ])
    year_count = len(df_player[df_player["year"] == selected_year])

    # --- Metrikák ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏆 Összes alkalom", f"{total}")
    c2.metric(f"📅 {current_year}", f"{this_year_count}")
    c3.metric(f"🗓️ {current_year}/{this_month:02d}", f"{this_month_count}")
    c4.metric(f"📌 {selected_year}", f"{year_count}")

    st.markdown("---")

    # --- Éves összesítő diagram ---
    st.markdown("#### 📈 Éves összesítő")
    yearly = (
        df_player.groupby("year")
        .size()
        .reset_index(name="Alkalmak száma")
        .rename(columns={"year": "Év"})
    )
    yearly["Év"] = yearly["Év"].astype(str)

    chart_yearly = (
        alt.Chart(yearly)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, color="#4a90d9")
        .encode(
            x=alt.X("Év:N", title=""),
            y=alt.Y("Alkalmak száma:Q", title="Alkalmak száma"),
            tooltip=["Év", "Alkalmak száma"],
        )
        .properties(height=280)
    )
    labels_yearly = chart_yearly.mark_text(
        align="center", baseline="bottom", dy=-4, color="white", fontSize=13, fontWeight="bold"
    ).encode(text="Alkalmak száma:Q")
    st.altair_chart(chart_yearly + labels_yearly, use_container_width=True)

    st.markdown("---")

    # --- Havi bontás a kiválasztott évre ---
    month_names = [
        "Jan", "Feb", "Már", "Ápr", "Máj", "Jún",
        "Júl", "Aug", "Szep", "Okt", "Nov", "Dec"
    ]
    st.markdown(f"#### 🗂️ Havi bontás — {selected_year}")

    df_year = df_player[df_player["year"] == selected_year]
    monthly = (
        df_year.groupby("month")
        .size()
        .reindex(range(1, 13), fill_value=0)
        .reset_index()
    )
    monthly.columns = ["Hónap száma", "Alkalmak száma"]
    monthly["Hónap"] = monthly["Hónap száma"].apply(lambda m: month_names[m - 1])

    chart_monthly = (
        alt.Chart(monthly)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
        .encode(
            x=alt.X(
                "Hónap:N",
                sort=["Jan", "Feb", "Már", "Ápr", "Máj", "Jún",
                      "Júl", "Aug", "Szep", "Okt", "Nov", "Dec"],
                title=""
            ),
            y=alt.Y("Alkalmak száma:Q", title="Alkalmak száma"),
            color=alt.condition(
                alt.datum["Alkalmak száma"] > 0,
                alt.value("#27ae60"),
                alt.value("#2c3e50")
            ),
            tooltip=["Hónap", "Alkalmak száma"],
        )
        .properties(height=260)
    )
    labels_monthly = chart_monthly.mark_text(
        align="center", baseline="bottom", dy=-4, fontSize=12, fontWeight="bold",
        color="white"
    ).encode(
        text=alt.condition(
            alt.datum["Alkalmak sz\u00e1ma"] > 0,
            alt.Text("Alkalmak sz\u00e1ma:Q"),
            alt.value("")
        )
    )
    st.altair_chart(chart_monthly + labels_monthly, use_container_width=True)

    st.markdown("---")

    # --- Utolsó 10 alkalom ---
    st.markdown("#### 🕐 Utolsó 10 alkalom")
    recent = (
        df_player.sort_values("date", ascending=False)
        .head(10)
        .copy()
    )
    recent["date"] = recent["date"].apply(lambda d: d.strftime("%Y-%m-%d"))
    recent = recent.rename(columns={"date": "Dátum", "year": "Év", "month": "Hónap"})
    st.dataframe(recent[["Dátum"]].reset_index(drop=True), use_container_width=True, hide_index=True)
