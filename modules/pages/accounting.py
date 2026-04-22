import streamlit as st
import pandas as pd
import time

from modules.db import get_invoices_fs, get_members_fs, save_settlement_fs, get_settlement_fs
from modules.utils import calculate_monthly_accounting_fs, generate_pdf_bytes, send_personal_email, send_admin_summary_email, bulk_calculate_settlements


def _render_bulk_section(fs_db):
    """Tömeges elszámolás-generáló szekció — önálló helper, bárhonnan hívható."""
    st.markdown("---")
    st.subheader("🔄 Összes elszámolás generálása")
    st.markdown(
        "Ezzel a funkcióval az összes Firestore-ban tárolt számlára automatikusan elvégzi "
        "az elszámolás kalkulációt és elmenti az eredményt. "
        "A profiloldalon ezután megjelenik a **pontos éves összeg** minden játékosnál."
    )

    force_recalc = st.checkbox(
        "🔁 Már meglévő elszámolások felülírása (újraszámolás)",
        value=False,
        key="bulk_force_recalc",
        help="Ha be van jelölve, minden hónapot újraszámol — akkor is, ha már volt elszámolás."
    )

    if st.button("🚀 Összes elszámolás generálása és mentése", type="primary", key="bulk_calc_btn"):
        invoices_check = get_invoices_fs(fs_db)
        if not invoices_check:
            st.error("❌ Nincsenek számlák a Firestore-ban!")
        else:
            progress = st.progress(0, text="Elszámolások generálása...")
            with st.spinner(f"Feldolgozás... (összesen {len(invoices_check)} számla)"):
                bulk_results = bulk_calculate_settlements(fs_db, force_recalculate=force_recalc)
                st.cache_data.clear()
            progress.empty()

            ok_count = len(bulk_results["ok"])
            skip_count = len(bulk_results["skipped"])
            fail_count = len(bulk_results["failed"])
            total = bulk_results["total"]

            if ok_count > 0:
                st.success(f"✅ Sikeresen generálva és mentve: **{ok_count}/{total}** hónap")
            if skip_count > 0:
                st.info(f"⏭️ Kihagyva (már létezett): **{skip_count}** hónap")
            if fail_count > 0:
                st.warning(f"⚠️ Sikertelen: **{fail_count}** hónap")

            if bulk_results["ok"]:
                st.markdown("**✅ Sikeresen generált elszámolások:**")
                df_ok = pd.DataFrame(bulk_results["ok"])[["label", "people", "total_ft"]]
                df_ok.columns = ["Hónap", "Résztvevők", "Összköltség (Ft)"]
                df_ok["Összköltség (Ft)"] = df_ok["Összköltség (Ft)"].apply(
                    lambda x: f"{x:,.0f} Ft".replace(",", " ")
                )
                st.dataframe(df_ok, use_container_width=True, hide_index=True)

            if bulk_results["skipped"]:
                with st.expander(f"⏭️ Kihagyott hónapok ({skip_count} db)"):
                    df_skip = pd.DataFrame(bulk_results["skipped"])[["label"]]
                    df_skip.columns = ["Hónap"]
                    st.dataframe(df_skip, use_container_width=True, hide_index=True)

            if bulk_results["failed"]:
                with st.expander(f"❌ Hibás hónapok ({fail_count} db)"):
                    df_fail = pd.DataFrame(bulk_results["failed"])[["label", "reason"]]
                    df_fail.columns = ["Hónap", "Hiba oka"]
                    st.dataframe(df_fail, use_container_width=True, hide_index=True)




def render_accounting_page(fs_db, gs_client):
    st.title("💰 Havi Elszámolás")
    st.markdown("Ezzel a funkcióval kiszámolhatod a teremköltségek személyenkénti elosztását a valós jelenléti adatok alapján.")
    invoices = get_invoices_fs(fs_db)
    if not invoices:
        st.warning("⚠️ Nem találtam számlát a Firestore-ban! Kérlek, menj az 'Adatbázis' fülre és szinkronizáld a számlákat.")
        return
    selected_inv = st.selectbox(
        "Válaszd ki az elszámolandó hónapot:", invoices,
        format_func=lambda x: f"{x['target_year']}. {x['month_name']} (Számla kelte: {x['inv_date']} | Összeg: {x['amount']:,.0f} Ft)".replace(',', ' ')
    )

    if st.button("Elszámolás Kalkulálása 🚀", type="primary"):
        with st.spinner("Kalkulálás folyamatban..."):
            success, msg, df_elszamolas, df_osszesito, month_name, year = calculate_monthly_accounting_fs(fs_db, selected_inv)
        if not success:
            st.error(msg)
            return
        st.session_state["acc_df_elszamolas"] = df_elszamolas
        st.session_state["acc_df_osszesito"] = df_osszesito
        st.session_state["acc_month_name"] = month_name
        st.session_state["acc_year"] = year
        st.session_state["acc_pdf_bytes"] = generate_pdf_bytes(df_osszesito, month_name, year)
        st.session_state["acc_from_cache"] = False
        ok, result = save_settlement_fs(fs_db, year, selected_inv["target_month"], month_name, df_elszamolas, df_osszesito)
        if not ok:
            st.warning(f"⚠️ Firestore mentés sikertelen: {result}")
        st.cache_data.clear()  # profil oldal is friss adatot kap
        st.rerun()

    if "acc_df_osszesito" not in st.session_state:
        # Megpróbáljuk betölteni Firestore-ból az utoljára kalkulált hónapot
        loaded = get_settlement_fs(fs_db, selected_inv["target_year"], selected_inv["target_month"])
        if loaded:
            df_elszamolas, df_osszesito, month_name = loaded
            st.session_state["acc_df_elszamolas"] = df_elszamolas
            st.session_state["acc_df_osszesito"] = df_osszesito
            st.session_state["acc_month_name"] = month_name
            st.session_state["acc_year"] = selected_inv["target_year"]
            st.session_state["acc_pdf_bytes"] = generate_pdf_bytes(df_osszesito, month_name, selected_inv["target_year"])
            st.session_state["acc_from_cache"] = True
        else:
            # Nincs betöltött elszámolás — de a tömeges generálót még megmutatjuk
            _render_bulk_section(fs_db)
            return


    df_osszesito = st.session_state["acc_df_osszesito"]
    df_elszamolas = st.session_state["acc_df_elszamolas"]
    month_name = st.session_state["acc_month_name"]
    year = st.session_state["acc_year"]
    pdf_bytes = st.session_state["acc_pdf_bytes"]

    if st.session_state.get("acc_from_cache"):
        st.info(f"💾 Mentett elszámolás betöltve: {year}. {month_name}")
    else:
        st.success(f"✅ Kalkuláció sikeres: {year}. {month_name}")
    st.download_button(label="📥 Elszámolás Letöltése (PDF)", data=pdf_bytes,
                       file_name=f"Havi_Elszamolas_{year}_{month_name}.pdf", mime="application/pdf", type="primary")

    st.markdown("---")
    st.subheader("📧 Email értesítések küldése")
    email_configured = hasattr(st, 'secrets') and "email" in st.secrets
    if not email_configured:
        st.warning("⚠️ Az email küldéshez add meg az email beállításokat a `.streamlit/secrets.toml` fájlban!")
        with st.expander("Hogyan kell beállítani?"):
            st.code("""[email]\nsender = "ropiplabda.app@gmail.com"\npassword = "xxxx xxxx xxxx xxxx"\nadmin_email = "admin@example.com" """, language="toml")
    else:
        members_df = get_members_fs(fs_db)
        active_members = members_df[members_df["Aktív"] == True] if not members_df.empty else pd.DataFrame()
        if active_members.empty:
            st.warning("⚠️ Nincsenek tagok az adatbázisban! Add hozzá őket a '👤 Tagok & Email' menüpontban.")
        else:
            email_preview = []
            guest_details_map = {}
            for _, member in active_members.iterrows():
                member_name = member["Név"]
                own_match = df_osszesito[df_osszesito["Név"] == member_name]
                own_count = int(own_match.iloc[0]["Részvétel száma"]) if not own_match.empty else 0
                own_cost = float(own_match.iloc[0]["Fizetendő (Ft)"]) if not own_match.empty else 0.0
                guest_prefix = f"{member_name} - "
                guest_rows = df_osszesito[df_osszesito["Név"].str.startswith(guest_prefix)]
                guest_cost = float(guest_rows["Fizetendő (Ft)"].sum()) if not guest_rows.empty else 0.0
                total_count = own_count + (int(guest_rows["Részvétel száma"].sum()) if not guest_rows.empty else 0)
                total_cost = own_cost + guest_cost
                if total_cost > 0:
                    guests_list = []
                    for _, gr in guest_rows.iterrows():
                        guests_list.append({
                            "name": gr["Név"].replace(guest_prefix, "", 1),
                            "count": int(gr["Részvétel száma"]),
                            "cost": float(gr["Fizetendő (Ft)"]),
                        })
                    guest_details_map[member_name] = {
                        "own_cost": own_cost,
                        "own_count": own_count,
                        "guests": guests_list,
                    }
                    email_preview.append({
                        "Név": member_name, "Email": member["Email"],
                        "Saját részvétel": own_count,
                        "Vendégek": ", ".join(g["name"] for g in guests_list) if guests_list else "—",
                        "Összes részvétel": total_count,
                        "Fizetendő (Ft)": total_cost,
                        "📧 Küldés?": True,
                    })
            st.session_state["acc_guest_details_map"] = guest_details_map

            if not email_preview:
                st.info("Ebben a hónapban egy aktív tagnak sem volt részvétele.")
            else:
                st.markdown(f"**{len(email_preview)} tagnak** küldhető személyes email:")
                preview_df = pd.DataFrame(email_preview)
                edited_preview = st.data_editor(
                    preview_df, key="email_preview_editor",
                    column_config={
                        "📧 Küldés?": st.column_config.CheckboxColumn("📧 Küldés?"),
                        "Fizetendő (Ft)": st.column_config.NumberColumn(format="%.0f Ft"),
                    },
                    disabled=["Név", "Email", "Saját részvétel", "Vendégek", "Összes részvétel", "Fizetendő (Ft)"],
                    use_container_width=True, hide_index=True
                )

                send_col1, send_col2 = st.columns(2)
                with send_col1:
                    if st.button("📧 Személyes emailek küldése", type="primary", use_container_width=True):
                        to_send = edited_preview[edited_preview["📧 Küldés?"] == True]
                        if to_send.empty:
                            st.warning("Nincs kijelölt tag!")
                        else:
                            progress = st.progress(0, text="Emailek küldése...")
                            success_count = 0
                            total = len(to_send)
                            details_map = st.session_state.get("acc_guest_details_map", {})
                            for i, (_, row) in enumerate(to_send.iterrows()):
                                ok = send_personal_email(
                                    to_address=row["Email"], name=row["Név"], month_name=month_name,
                                    year=year, count=row["Összes részvétel"], amount=row["Fizetendő (Ft)"],
                                    guest_details=details_map.get(row["Név"])
                                )
                                if ok:
                                    success_count += 1
                                progress.progress((i + 1) / total, text=f"Küldés: {row['Név']} ({i+1}/{total})")
                                time.sleep(0.3)
                            progress.empty()
                            if success_count == total:
                                st.success(f"✅ Sikeresen elküldve: {success_count}/{total} email!")
                            else:
                                st.warning(f"⚠️ {success_count}/{total} email elküldve.")

                with send_col2:
                    if st.button("📊 Admin összesítő küldése (PDF-fel)", use_container_width=True):
                        with st.spinner("Admin email küldése..."):
                            ok = send_admin_summary_email(month_name, year, df_osszesito, pdf_bytes)
                        if ok:
                            st.success(f"✅ Admin összesítő elküldve: {st.secrets['email']['admin_email']}")

    st.markdown("---")
    st.subheader("💬 Üzenet a Messenger csoportba")
    msg_text = (f"Sziasztok! 🏐\n\nElkészült a {year}. {month_name} havi röpi elszámolás!\n"
                f"Mindenki kapott egy emailt a pontos összeggel. 📧\n\n"
                f"Kérlek utaljátok a rátok eső összeget a szokásos számlaszámra! Köszi! 🙌")
    st.code(msg_text, language="text")
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Bontás Alkalmanként")
        st.dataframe(df_elszamolas, use_container_width=True)
    with col2:
        st.subheader("Személyenkénti Összesítő")
        df_display = df_osszesito.copy()
        df_display['Fizetendő (Ft)'] = df_display['Fizetendő (Ft)'].apply(lambda x: f"{x:.0f} Ft")
        st.dataframe(df_display, use_container_width=True)

    _render_bulk_section(fs_db)

