import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

from modules.db import get_attendance_rows_fs, get_all_settlements_for_player, get_avg_session_attendees_for_year
from modules.utils import parse_date_str, estimate_cost_for_player
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

    # --- Pénzügyi összesítő ---
    st.markdown(f"#### 💰 Pénzügyi összesítő — {selected_year}")

    # Átlagos létszám lekérése az elszámolásokból (pontosabb becsléshez)
    avg_attendees = get_avg_session_attendees_for_year(fs_db, selected_year)

    # Becsült összeg kiszámítása
    cost_est = estimate_cost_for_player(year_count, selected_year, avg_attendees)

    # Elszámolások lekérése erre a játékosra
    all_settlements = get_all_settlements_for_player(fs_db, selected_name)
    year_settlements = [s for s in all_settlements if s["year"] == selected_year]

    # Összeg az elszámolásokból (ahol megvan)
    exact_total = sum(s["amount"] for s in year_settlements)
    exact_count_from_settlements = sum(s["count"] for s in year_settlements)
    has_exact = len(year_settlements) > 0

    # Megjelenítés
    fin_col1, fin_col2 = st.columns([1, 1])

    with fin_col1:
        st.markdown("**📊 Becsült fizetendő összeg**")

        # Pontosabb becslés
        precise_label = f"~{cost_est['precise']:,.0f} Ft".replace(",", " ")
        if avg_attendees:
            attendees_note = f"{avg_attendees:.0f} fő"
        else:
            attendees_note = "12 fő (becsült)"

        st.markdown(
            f"""
            <div style="background:#1e3a5f; border-radius:10px; padding:16px 20px; margin-bottom:10px;">
              <div style="color:#a8c8f8; font-size:0.82em; margin-bottom:4px;">
                📐 Pontosabb becslés
                <span style="opacity:0.7; font-size:0.85em;">
                  ({cost_est['hourly_rate']:,} Ft/óra · {cost_est['duration']} óra · {attendees_note})
                </span>
              </div>
              <div style="font-size:1.6em; font-weight:700; color:#60a5fa; letter-spacing:0.5px;">
                {precise_label}
              </div>
              <div style="color:#6b7280; font-size:0.78em; margin-top:6px;">
                ≈ {cost_est['cost_per_session']:,.0f} Ft / alkalom · {year_count} alkalom
              </div>
            </div>
            """.replace(",", " "),
            unsafe_allow_html=True
        )

        # Egyszerű becslés (másodlagos)
        simple_label = f"~{cost_est['simple']:,.0f} Ft".replace(",", " ")
        st.markdown(
            f"""
            <div style="background:#1a2a1a; border-radius:8px; padding:10px 16px; margin-bottom:4px;">
              <div style="color:#86efac; font-size:0.78em; margin-bottom:2px;">
                💡 Egyszerű becslés (2 300 Ft/alkalom)
              </div>
              <div style="font-size:1.1em; font-weight:600; color:#4ade80;">
                {simple_label}
              </div>
            </div>
            """.replace(",", " "),
            unsafe_allow_html=True
        )

    with fin_col2:
        if has_exact:
            total_label = f"{exact_total:,.0f} Ft".replace(",", " ")
            st.markdown("**✅ Pontos összeg (elszámolásokból)**")
            st.markdown(
                f"""
                <div style="background:#1a3a2a; border-radius:10px; padding:16px 20px; margin-bottom:10px;">
                  <div style="color:#86efac; font-size:0.82em; margin-bottom:4px;">
                    💳 Elszámolásokból összesítve ({len(year_settlements)} hónap)
                  </div>
                  <div style="font-size:1.6em; font-weight:700; color:#4ade80; letter-spacing:0.5px;">
                    {total_label}
                  </div>
                  <div style="color:#6b7280; font-size:0.78em; margin-top:6px;">
                    {exact_count_from_settlements} alkalom alapján
                  </div>
                </div>
                """.replace(",", " "),
                unsafe_allow_html=True
            )

            # Havi bontás táblázat
            df_exact = pd.DataFrame(year_settlements)
            df_exact = df_exact.rename(columns={
                "month_name": "Hónap",
                "count": "Alkalmak",
                "amount": "Fizetendő (Ft)",
            })[["Hónap", "Alkalmak", "Fizetendő (Ft)"]]
            df_exact["Fizetendő (Ft)"] = df_exact["Fizetendő (Ft)"].apply(
                lambda x: f"{x:,.0f} Ft".replace(",", " ")
            )
            st.dataframe(df_exact, use_container_width=True, hide_index=True)
        else:
            st.markdown("**⏳ Elszámolás még nem elérhető**")
            st.markdown(
                f"""
                <div style="background:#2a2a1a; border-radius:10px; padding:16px 20px; color:#fbbf24; font-size:0.9em;">
                  📭 <strong>{selected_year}-re</strong> még nem készült el vagy nem lett elmentve elszámolás.<br>
                  <span style="opacity:0.7; font-size:0.85em;">
                    Végezd el az elszámolást az 'Elszámolás' menüpontban — automatikusan mentésre kerül.
                  </span>
                </div>
                """,
                unsafe_allow_html=True
            )

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
