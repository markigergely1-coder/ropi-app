import streamlit as st
import pandas as pd
import time

from modules.db import get_invoices_fs, get_members_fs
from modules.utils import calculate_monthly_accounting_fs, generate_pdf_bytes, send_personal_email, send_admin_summary_email


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
        st.rerun()

    if "acc_df_osszesito" not in st.session_state:
        return

    df_osszesito = st.session_state["acc_df_osszesito"]
    df_elszamolas = st.session_state["acc_df_elszamolas"]
    month_name = st.session_state["acc_month_name"]
    year = st.session_state["acc_year"]
    pdf_bytes = st.session_state["acc_pdf_bytes"]

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
                    guest_names = list(guest_rows["Név"].str.replace(guest_prefix, "", regex=False)) if not guest_rows.empty else []
                    email_preview.append({
                        "Név": member_name, "Email": member["Email"],
                        "Saját részvétel": own_count,
                        "Vendégek": ", ".join(guest_names) if guest_names else "—",
                        "Összes részvétel": total_count,
                        "Fizetendő (Ft)": total_cost,
                        "📧 Küldés?": True,
                    })

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
                            for i, (_, row) in enumerate(to_send.iterrows()):
                                ok = send_personal_email(
                                    to_address=row["Email"], name=row["Név"], month_name=month_name,
                                    year=year, count=row["Összes részvétel"], amount=row["Fizetendő (Ft)"],
                                    own_count=row["Saját részvétel"], guest_names=row["Vendégek"]
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
