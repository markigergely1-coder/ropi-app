import streamlit as st
import pandas as pd
import time

from modules.config import FIRESTORE_NAME_MAPPING, TOLERANCE
from modules.db import get_name_mappings_fs
from modules.utils import parse_revolut_csv


def render_payment_check_page(fs_db, gs_client):
    st.title("💳 Befizetések Ellenőrzése")
    st.markdown("Töltsd fel a Revolut CSV kivonatot, és az app összehasonlítja a kiküldött elszámolással.")

    if "acc_df_osszesito" not in st.session_state:
        st.warning("⚠️ Először futtasd le az elszámolást a **Havi Elszámolás** oldalon, majd gyere vissza ide!")
        return

    df_osszesito = st.session_state["acc_df_osszesito"]
    month_name   = st.session_state["acc_month_name"]
    year         = st.session_state["acc_year"]

    st.info(f"📅 Aktuális elszámolás: **{year}. {month_name}** — {len(df_osszesito)} tétel")

    tab1, tab2 = st.tabs(["📤 Kivonat & Ellenőrzés", "🔗 Név párosítások"])

    with tab1:
        uploaded = st.file_uploader("Töltsd fel a Revolut CSV kivonatot:", type=["csv"], key="revolut_upload")

        if uploaded is None:
            st.markdown("""
            **Hogyan exportáld a kivonatot Revolut appból:**
            1. Nyisd meg a Revolut appot
            2. Menj a fiókodra → **Kimutatások / Statements**
            3. Válaszd ki a hónapot → Formátum: **CSV**
            4. Töltsd fel itt
            """)
            return

        df_revolut, err = parse_revolut_csv(uploaded)
        if err:
            st.error(err)
            return

        st.success(f"✅ {len(df_revolut)} bejövő átutalás betöltve.")

        name_mappings = get_name_mappings_fs(fs_db)
        rev_to_sys = {rev_n: info["system_name"] for rev_n, info in name_mappings.items()}

        main_members = df_osszesito[~df_osszesito["Név"].str.contains(" - ", na=False)].copy()

        results = []
        matched_revolut_names = set()

        for _, member_row in main_members.iterrows():
            sys_name = member_row["Név"]
            expected = float(member_row["Fizetendő (Ft)"])

            paid_amount = None
            matched_rev_name = None

            for rev_n, s_name in rev_to_sys.items():
                if s_name == sys_name:
                    match = df_revolut[df_revolut["_name"].str.upper() == rev_n.upper()]
                    if not match.empty:
                        paid_amount = float(match["_amount"].sum())
                        matched_rev_name = rev_n
                        matched_revolut_names.add(rev_n)
                    break

            if paid_amount is None:
                first = sys_name.split()[0].lower()
                last  = sys_name.split()[-1].lower() if len(sys_name.split()) > 1 else ""
                candidates = df_revolut[
                    df_revolut["_name"].str.lower().str.contains(first, na=False) |
                    (last != "" and df_revolut["_name"].str.lower().str.contains(last, na=False))
                ]
                if len(candidates) == 1:
                    paid_amount = float(candidates.iloc[0]["_amount"])
                    matched_rev_name = candidates.iloc[0]["_name"]
                    matched_revolut_names.add(matched_rev_name)

            if paid_amount is not None:
                diff = paid_amount - expected
                if abs(diff) <= TOLERANCE:
                    status = "✅ Fizetett"
                elif diff > TOLERANCE:
                    status = "✅ Fizetett (többet)"
                else:
                    status = "⚠️ Kevesebbet fizetett"
            else:
                status = "❌ Nem fizetett"
                diff = -expected

            results.append({
                "Név": sys_name,
                "Fizetendő (Ft)": f"{expected:.0f} Ft",
                "Revolut név": matched_rev_name or "— ismeretlen",
                "Befizetett (Ft)": f"{paid_amount:.0f} Ft" if paid_amount else "—",
                "Különbség": f"{diff:+.0f} Ft" if paid_amount else "—",
                "Státusz": status,
            })

        fizet = sum(1 for r in results if "✅" in r["Státusz"])
        nem   = sum(1 for r in results if "❌" in r["Státusz"])
        kevs  = sum(1 for r in results if "⚠️" in r["Státusz"])
        m1, m2, m3 = st.columns(3)
        m1.metric("✅ Fizetett", f"{fizet} fő")
        m2.metric("❌ Nem fizetett", f"{nem} fő")
        m3.metric("⚠️ Kevesebbet", f"{kevs} fő")
        st.markdown("---")

        def color_status(val):
            if "✅" in str(val): return "background-color: #d4edda; color: #155724;"
            elif "❌" in str(val): return "background-color: #f8d7da; color: #721c24;"
            elif "⚠️" in str(val): return "background-color: #fff3cd; color: #856404;"
            return ""

        st.dataframe(
            pd.DataFrame(results).style.applymap(color_status, subset=["Státusz"]),
            use_container_width=True, hide_index=True
        )

        nem_fizeto = [r["Név"] for r in results if "❌" in r["Státusz"]]
        keveset    = [r["Név"] for r in results if "⚠️" in r["Státusz"]]
        if nem_fizeto or keveset:
            st.markdown("---")
            st.subheader("💬 Emlékeztető üzenet")
            reszek = []
            if nem_fizeto:
                reszek.append("Nem fizetett: " + ", ".join(nem_fizeto))
            if keveset:
                reszek.append("Kevesebbet fizetett: " + ", ".join(keveset))
            reminder = (f"Sziasztok! 🏐\n\nA {year}. {month_name} havi röpi befizetéseket ellenőriztem.\n"
                        + "\n".join(reszek) + "\n\nKérlek utaljátok mielőbb! 🙏")
            st.code(reminder, language="text")

        unmatched_revolut = df_revolut[~df_revolut["_name"].isin(matched_revolut_names)]
        already_mapped = set(rev_to_sys.keys())
        new_unmatched = unmatched_revolut[~unmatched_revolut["_name"].isin(already_mapped)]

        if not new_unmatched.empty:
            st.markdown("---")
            st.subheader("🔍 Párosítatlan befizetők")
            st.info("Ezek a Revolut nevek nem lettek egyeztetve. Párosítsd őket a 'Név párosítások' fülön!")
            st.dataframe(
                new_unmatched.rename(columns={"_name": "Revolut név", "_amount": "Összeg (Ft)"}),
                use_container_width=True, hide_index=True
            )

    with tab2:
        st.subheader("🔗 Revolut név ↔ Rendszer név párosítások")
        st.markdown("Párosítsd a Revolut neveket a rendszerben lévő nevekkel. Ez **egyszer elég** — a rendszer megjegyzi.")

        name_mappings = get_name_mappings_fs(fs_db)
        rev_to_sys = {rev_n: info["system_name"] for rev_n, info in name_mappings.items()}
        already_mapped_revolut = set(rev_to_sys.keys())

        revolut_names_from_csv = []
        if "revolut_upload" in st.session_state and st.session_state["revolut_upload"] is not None:
            try:
                st.session_state["revolut_upload"].seek(0)
                df_tmp, _ = parse_revolut_csv(st.session_state["revolut_upload"])
                if df_tmp is not None:
                    revolut_names_from_csv = sorted(df_tmp["_name"].unique().tolist())
            except Exception:
                pass

        unpaired_revolut = [n for n in revolut_names_from_csv if n not in already_mapped_revolut]

        with st.container(border=True):
            st.markdown("**Új párosítás hozzáadása**")

            sys_name_options = sorted(
                df_osszesito[~df_osszesito["Név"].str.contains(" - ", na=False)]["Név"].tolist()
            )

            col1, col2 = st.columns(2)
            with col1:
                if unpaired_revolut:
                    rev_choice = st.selectbox(
                        "Revolut név (a feltöltött CSV-ből):",
                        ["— Válassz —"] + unpaired_revolut,
                        key="rev_name_dropdown"
                    )
                    rev_name_input = rev_choice if rev_choice != "— Válassz —" else ""
                else:
                    st.info("Minden Revolut név már párosítva van, vagy nincs feltöltött CSV.")
                    rev_name_input = st.text_input("Vagy írj be manuálisan:", key="rev_name_manual")

            with col2:
                sys_name_select = st.selectbox("Rendszerben lévő neve:", sys_name_options, key="sys_name_select")

            if st.button("💾 Párosítás mentése", type="primary"):
                if not rev_name_input.strip():
                    st.warning("Válassz vagy írj be egy Revolut nevet!")
                else:
                    try:
                        for rev_n, info in name_mappings.items():
                            if info["system_name"] == sys_name_select:
                                fs_db.collection(FIRESTORE_NAME_MAPPING).document(info["doc_id"]).delete()
                        fs_db.collection(FIRESTORE_NAME_MAPPING).add({
                            "revolut_name": rev_name_input.strip(),
                            "system_name": sys_name_select
                        })
                        get_name_mappings_fs.clear()
                        st.success(f"✅ Mentve: **{rev_name_input.strip()}** → **{sys_name_select}**")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hiba: {e}")

        st.markdown("---")
        st.subheader("Mentett párosítások")
        current = get_name_mappings_fs(fs_db)
        if current:
            for rev_n, info in current.items():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="center")
                    c1.markdown(f"**{rev_n}** *(Revolut)*")
                    c2.markdown(f"→ **{info['system_name']}** *(Rendszer)*")
                    if c3.button("❌ Törlés", key=f"del_map_{info['doc_id']}", use_container_width=True):
                        fs_db.collection(FIRESTORE_NAME_MAPPING).document(info["doc_id"]).delete()
                        get_name_mappings_fs.clear()
                        st.rerun()
        else:
            st.info("Még nincsenek mentett párosítások.")
