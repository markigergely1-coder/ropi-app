import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime

def render_monthly_attendance_chart(df, year, month):
    """
    Renders a bar chart showing attendance per session in a given month.
    """
    st.markdown(f"#### 📅 Alkalmankénti Jelenlét ({year}. {month:02d}.)")
    
    if df is None or df.empty:
        st.info("Nincs elérhető jelenléti adat.")
        return

    records = []
    for _, row in df.iterrows():
        date_val = str(row.get("Alkalom Dátuma", "")).strip()
        from modules.utils import parse_date_str
        dt = parse_date_str(date_val)
        
        is_coming = str(row.get("Jön-e", "")).strip()
        
        if dt and dt.year == year and dt.month == month and is_coming == "Yes":
            records.append({"Dátum": dt.strftime("%Y-%m-%d"), "Jelenlét": 1})
            
    if not records:
        st.info(f"Nem találtunk aktív 'Yes' jelenlétet a {year}/{month} időszakban.")
        return
        
    df_chart = pd.DataFrame(records).groupby("Dátum").sum().reset_index()
    df_chart.columns = ["Dátum", "Létszám (fő)"]
    
    chart = alt.Chart(df_chart).mark_bar(cornerRadiusEnd=5, color="#4a90d9").encode(
        x=alt.X("Dátum:N", title="Edzés Dátuma"),
        y=alt.Y("Létszám (fő):Q", title="Részvevők Száma"),
        tooltip=["Dátum", "Létszám (fő)"]
    ).properties(height=350)
    
    text = chart.mark_text(
        align='center',
        baseline='bottom',
        dy=-5,
        color='white'
    ).encode(
        text='Létszám (fő):Q'
    )
    
    st.altair_chart(chart + text, use_container_width=True)


def render_yearly_attendance_chart(df, year):
    """
    Renders a bar/line chart showing cumulative attendance per month in a year.
    Plus average attendance per session.
    """
    st.markdown(f"#### 📈 Éves Kumulált Jelenlét és Átlag ({year})")
    
    if df is None or df.empty:
        st.info("Nincs elérhető jelenléti adat.")
        return

    month_names = ["Január", "Február", "Március", "Április", "Május", "Június", 
                   "Július", "Augusztus", "Szeptember", "Október", "November", "December"]
                   
    from modules.utils import parse_date_str
    
    monthly_stats = {m: {"total": 0, "sessions": set()} for m in range(1, 13)}
    
    for _, row in df.iterrows():
        date_val = str(row.get("Alkalom Dátuma", "")).strip()
        dt = parse_date_str(date_val)
        is_coming = str(row.get("Jön-e", "")).strip()
        
        if dt and dt.year == year:
            monthly_stats[dt.month]["sessions"].add(dt.strftime("%Y-%m-%d"))
            if is_coming == "Yes":
                monthly_stats[dt.month]["total"] += 1
                
    chart_data = []
    for m in range(1, 13):
        total = monthly_stats[m]["total"]
        session_count = len(monthly_stats[m]["sessions"])
        avg = total / session_count if session_count > 0 else 0
        
        chart_data.append({
            "Hónap": month_names[m-1],
            "Hónap Sorszám": m,
            "Összes Részvétel": total,
            "Átlagos Részvétel": round(avg, 1)
        })
        
    df_chart = pd.DataFrame(chart_data)
    
    if df_chart["Összes Részvétel"].sum() == 0:
        st.info(f"Nincsenek adatok a {year}. évre.")
        return

    base = alt.Chart(df_chart).encode(
        x=alt.X("Hónap:N", sort=alt.EncodingSortField(field="Hónap Sorszám", order="ascending"), title="")
    )

    bar = base.mark_bar(opacity=0.7, color="#3498db", cornerRadiusEnd=5).encode(
        y=alt.Y("Összes Részvétel:Q", title="Összes Részvétel"),
        tooltip=["Hónap", "Összes Részvétel", "Átlagos Részvétel"]
    )
    
    line = base.mark_line(color="#e74c3c", strokeWidth=3, point=True).encode(
        y=alt.Y("Átlagos Részvétel:Q", title="Átlagos Részvétel / Alkalom", axis=alt.Axis(titleColor="#e74c3c", labelColor="#e74c3c")),
        tooltip=["Hónap", "Összes Részvétel", "Átlagos Részvétel"]
    )

    final_chart = alt.layer(bar, line).resolve_scale(
        y='independent'
    ).properties(height=400)

    st.altair_chart(final_chart, use_container_width=True)


def render_top5_chart(legacy_list_of_dicts):
    """
    Renders an impressive horizontal bar chart for the top 5 players.
    Data format expected: [{"Helyezés": i, "Név": n, "Összes Részvétel": c}, ...]
    """
    st.markdown("#### 🏅 Top 5 Legszorgalmasabb Játékos")
    
    if not legacy_list_of_dicts:
        st.info("Nincs elegendő adat.")
        return
        
    df_top5 = pd.DataFrame(legacy_list_of_dicts).head(5)
    
    if df_top5.empty:
        st.info("Nincs elegendő adat.")
        return
        
    chart = alt.Chart(df_top5).mark_bar(cornerRadiusEnd=5, color=alt.Gradient(
        gradient='linear',
        stops=[alt.GradientStop(color='#6fb1fc', offset=0),
               alt.GradientStop(color='#0052cc', offset=1)],
        x1=0, x2=1, y1=0, y2=0
    )).encode(
        x=alt.X("Összes Részvétel:Q", title="Alkalmak száma"),
        y=alt.Y("Név:N", sort="-x", title=""),
        tooltip=["Helyezés", "Név", "Összes Részvétel"]
    ).properties(height=300)

    text = chart.mark_text(
        align='left',
        baseline='middle',
        dx=5,
        color='white'
    ).encode(
        text='Összes Részvétel:Q'
    )

    st.altair_chart(chart + text, use_container_width=True)
