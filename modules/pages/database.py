import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore

from modules.config import (
    FIRESTORE_COLLECTION, FIRESTORE_INVOICES, GSHEET_NAME, FIRESTORE_LEGACY,
)
from modules.db import (
    get_attendance_rows_gs, get_attendance_rows_fs, get_invoices_fs,
    get_members_fs, sync_members_fs_to_gs, sync_members_gs_to_fs,
    get_legacy_totals_fs, sync_legacy_fs_to_gs, sync_legacy_gs_to_fs,
)
from modules.charts import render_monthly_attendance_chart, render_yearly_attendance_chart, render_top5_chart
from modules.utils import parse_date_str, build_total_attendance


def render_database_page(gs_client, fs_db, logged_in=False):
    st.title("🗂️ Adatbázis")

    if logged_in:
        tab_sheet, tab_firestore, tab_diagramok, tab_ranglista = st.tabs(["📝 Beküldött Adatok (Sheet)", "☁️ Felhő Adatok (Firestore)", "📊 Statisztikák", "🏆 Ranglista"])
    else:
        tab_firestore, tab_diagramok, tab_ranglista = st.tabs(["☁️ Felhő Adatok (Firestore)", "📊 Statisztikák", "🏆 Ranglista"])

    if logged_in:
        with tab_sheet:
            st.subheader("Google Sheet adatok megtekintése")
            rows = get_attendance_rows_gs(gs_client)
            if rows:
                cols = rows[0][:6]
                while len(cols) < 6:
                    cols.append(f"Oszlop {len(cols)+1}")
                df_data = [r[:6] + [""] * (6 - len(r[:6])) for r in rows[1:]]
                df = pd.DataFrame(df_data, columns=cols)
                col_sort, col_order = st.columns([2, 1])
                with col_sort:
                    sort_col = st.selectbox("Rendezés alapja:", df.columns, index=2, key="sheet_sort_col")
                with col_order:
                    ascending = st.checkbox("Növekvő sorrend", value=False, key="sheet_asc")
                st.dataframe(df.sort_values(by=sort_col, ascending=ascending), use_container_width=True)
            else:
                st.warning("Nem sikerült betölteni a Google Sheets adatokat.")

    with tab_firestore:
        st.subheader("Firestore Adatbázis")

        if logged_in:
            st.markdown("---")
            with st.expander("🔄 Adatok Szinkronizálása (Sheet ↔ Firestore)"):
                st.warning("⚠️ A szinkronizálás felülírja a céladatbázist!")
                sync_source = st.radio("Melyik legyen a FORRÁS?", ["Google Sheets", "Firestore"], horizontal=True, key="db_sync_source")
                st.info(f"👉 Irány: **{sync_source}** ➡️ **{'Firestore' if sync_source == 'Google Sheets' else 'Google Sheets'}**")
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    if st.button("👥 Jelenlét szinkronizálása", type="primary", use_container_width=True):
                        with st.spinner("Folyamatban..."):
                            if sync_source == "Google Sheets":
                                gs_rows = get_attendance_rows_gs(gs_client)
                                if len(gs_rows) > 1:
                                    new_docs = []
                                    for r in gs_rows[1:]:
                                        name = r[0] if len(r) > 0 else ""
                                        if not name: continue
                                        new_docs.append({
                                            "name": name, "status": r[1] if len(r) > 1 else "Yes",
                                            "timestamp": r[2] if len(r) > 2 else "",
                                            "event_date": r[3] if len(r) > 3 else "", "mode": "valós"
                                        })
                                    try:
                                        # 1. törlés batch-csal
                                        del_batch = fs_db.batch()
                                        del_count = 0
                                        for doc in fs_db.collection(FIRESTORE_COLLECTION).stream():
                                            del_batch.delete(doc.reference)
                                            del_count += 1
                                            if del_count >= 500:
                                                del_batch.commit()
                                                del_batch = fs_db.batch()
                                                del_count = 0
                                        if del_count > 0:
                                            del_batch.commit()
                                        # 2. írás batch-csal
                                        ins_batch = fs_db.batch()
                                        ins_count = 0
                                        for data in new_docs:
                                            ins_batch.set(fs_db.collection(FIRESTORE_COLLECTION).document(), data)
                                            ins_count += 1
                                            if ins_count >= 500:
                                                ins_batch.commit()
                                                ins_batch = fs_db.batch()
                                                ins_count = 0
                                        if ins_count > 0:
                                            ins_batch.commit()
                                        st.success(f"Kész! {len(new_docs)} adat átmásolva a Firestore-ba.")
                                    except Exception as e:
                                        st.error(f"Szinkronizálási hiba: {e}")
                                else:
                                    st.info("Nincs másolható adat a Sheet-ben.")
                            else:
                                df_fs_sync = get_attendance_rows_fs(fs_db)
                                if not df_fs_sync.empty:
                                    try:
                                        sheet = gs_client.open(GSHEET_NAME).sheet1
                                        sheet.clear()
                                        new_rows = [["Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Üres", "Mód"]]
                                        for _, row in df_fs_sync.iterrows():
                                            new_rows.append([row["Név"], row["Jön-e"], row["Regisztráció Időpontja"], row["Alkalom Dátuma"], "", "valós"])
                                        sheet.append_rows(new_rows, value_input_option='USER_ENTERED')
                                        st.success(f"Kész! {len(new_rows)-1} adat átmásolva a Sheet-be.")
                                    except Exception as e:
                                        st.error(f"Hiba: {e}")
                            st.cache_data.clear()
                            st.rerun()
                with col_m2:
                    if st.button("🧾 Számlák szinkronizálása", type="primary", use_container_width=True):
                        with st.spinner("Folyamatban..."):
                            try:
                                ss = gs_client.open(GSHEET_NAME)
                                ws_titles = [w.title for w in ss.worksheets()]
                                szamlak_sheet = ss.worksheet("Szamlak") if "Szamlak" in ws_titles else ss.worksheet("szamlak")
                                if sync_source == "Google Sheets":
                                    rows_sz = szamlak_sheet.get_all_values()
                                    if len(rows_sz) > 1:
                                        new_invoices = []
                                        for r in rows_sz[1:]:
                                            if not r[0]: continue
                                            inv_date = parse_date_str(r[0])
                                            if not inv_date: continue
                                            try:
                                                amount = float(str(r[1]).replace(' ', '').replace('Ft', '').replace('HUF', '').replace('\xa0', ''))
                                            except Exception:
                                                continue
                                            t_month = 12 if inv_date.month == 1 else inv_date.month - 1
                                            t_year = inv_date.year - 1 if inv_date.month == 1 else inv_date.year
                                            new_invoices.append({
                                                "inv_date": inv_date.strftime("%Y-%m-%d"), "target_year": t_year,
                                                "target_month": t_month, "amount": amount,
                                                "filename": r[2] if len(r) > 2 else ""
                                            })
                                        try:
                                            del_batch = fs_db.batch()
                                            del_count = 0
                                            for doc in fs_db.collection(FIRESTORE_INVOICES).stream():
                                                del_batch.delete(doc.reference)
                                                del_count += 1
                                                if del_count >= 500:
                                                    del_batch.commit()
                                                    del_batch = fs_db.batch()
                                                    del_count = 0
                                            if del_count > 0:
                                                del_batch.commit()
                                            ins_batch = fs_db.batch()
                                            ins_count = 0
                                            for data in new_invoices:
                                                ins_batch.set(fs_db.collection(FIRESTORE_INVOICES).document(), data)
                                                ins_count += 1
                                                if ins_count >= 500:
                                                    ins_batch.commit()
                                                    ins_batch = fs_db.batch()
                                                    ins_count = 0
                                            if ins_count > 0:
                                                ins_batch.commit()
                                            st.success(f"Kész! {len(new_invoices)} számla átmásolva.")
                                        except Exception as e:
                                            st.error(f"Szinkronizálási hiba: {e}")
                                    else:
                                        st.info("Nincs számla a Sheet-ben.")
                                else:
                                    invoices_sync = get_invoices_fs(fs_db)
                                    if invoices_sync:
                                        szamlak_sheet.clear()
                                        new_rows = [["Dátum", "Összeg", "Fájlnév"]]
                                        for inv in invoices_sync:
                                            new_rows.append([inv["inv_date"], f"{int(inv['amount'])} Ft", inv.get("filename", "")])
                                        szamlak_sheet.append_rows(new_rows, value_input_option='USER_ENTERED')
                                        st.success(f"Kész! {len(invoices_sync)} számla átmásolva.")
                                    else:
                                        st.info("Nincs számla a Firestore-ban.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Szinkronizálási hiba: {e}")
                with col_m3:
                    if st.button("👤 Tagok szinkronizálása", type="primary", use_container_width=True):
                        with st.spinner("Folyamatban..."):
                            if sync_source == "Google Sheets":
                                ok, msg = sync_members_gs_to_fs(gs_client, fs_db)
                                get_members_fs.clear()
                            else:
                                ok, msg = sync_members_fs_to_gs(fs_db, gs_client)
                            st.toast(f"✅ {msg}" if ok else f"❌ {msg}")
                            st.cache_data.clear()
                            st.rerun()

                st.markdown("---")
                if st.button("🏛️ Legacy db szinkronizálása", type="primary", use_container_width=True):
                    with st.spinner("Folyamatban..."):
                        if sync_source == "Google Sheets":
                            ok, msg = sync_legacy_gs_to_fs(gs_client, fs_db)
                        else:
                            ok, msg = sync_legacy_fs_to_gs(fs_db, gs_client)
                        st.toast(f"✅ {msg}" if ok else f"❌ {msg}")
                        st.cache_data.clear()
                        st.rerun()

            st.markdown("---")
            view_selection = st.radio("Mit szeretnél megtekinteni/szerkeszteni?",
                                      ["👥 Jelenléti adatok", "🧾 Számlák", "🏛️ Legacy Adatok"], horizontal=True, key="db_view_sel")
            st.markdown("---")
        else:
            view_selection = "👥 Jelenléti adatok"

        if view_selection == "👥 Jelenléti adatok":
            df_fs = get_attendance_rows_fs(fs_db)
            if not df_fs.empty:
                col_sort_fs, col_order_fs = st.columns([2, 1])
                with col_sort_fs:
                    sortable_cols = [c for c in df_fs.columns if c != "ID"]
                    sort_col_fs = st.selectbox("Rendezés alapja:", sortable_cols, index=2, key="db_sort_col")
                with col_order_fs:
                    ascending_fs = st.checkbox("Növekvő sorrend", value=False, key="db_asc")
                df_fs = df_fs.sort_values(by=sort_col_fs, ascending=ascending_fs).reset_index(drop=True)
                edit_mode = st.toggle("✏️ Szerkesztés mód bekapcsolása", key="db_edit_toggle")
                if edit_mode:
                    st.info("💡 Kattints duplán a cellákra a szerkesztéshez! Törléshez jelöld ki a sort és nyomj **Delete**-t.")
                    st.data_editor(df_fs, key="db_fs_editor", num_rows="dynamic",
                                   column_config={"ID": None}, use_container_width=True)
                    if st.button("💾 Változtatások mentése a felhőbe", type="primary", key="db_save_btn"):
                        changes = st.session_state["db_fs_editor"]
                        if changes.get("edited_rows") or changes.get("added_rows") or changes.get("deleted_rows"):
                            try:
                                for row_idx in changes.get("deleted_rows", []):
                                    fs_db.collection(FIRESTORE_COLLECTION).document(df_fs.iloc[row_idx]["ID"]).delete()
                                col_map = {"Név": "name", "Jön-e": "status", "Regisztráció Időpontja": "timestamp",
                                           "Alkalom Dátuma": "event_date", "Mód": "mode"}
                                for row_idx, edits in changes.get("edited_rows", {}).items():
                                    doc_id = df_fs.iloc[row_idx]["ID"]
                                    update_data = {col_map[k]: v for k, v in edits.items() if k in col_map}
                                    if update_data:
                                        fs_db.collection(FIRESTORE_COLLECTION).document(doc_id).update(update_data)
                                for new_row in changes.get("added_rows", []):
                                    fs_db.collection(FIRESTORE_COLLECTION).add({
                                        "name": new_row.get("Név", ""), "status": new_row.get("Jön-e", "Yes"),
                                        "timestamp": new_row.get("Regisztráció Időpontja", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                                        "event_date": new_row.get("Alkalom Dátuma", ""), "mode": new_row.get("Mód", "valós")
                                    })
                                st.toast("✅ Sikeresen frissítetted a felhő adatbázist!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Mentési hiba: {e}")
                        else:
                            st.info("Nem történt változtatás.")
                else:
                    st.dataframe(df_fs.drop(columns=["ID"]), use_container_width=True)
            else:
                st.info("Még nincsenek adatok a Firestore adatbázisban.")

        elif view_selection == "🧾 Számlák" and logged_in:
            invoices = get_invoices_fs(fs_db)
            if invoices:
                df_inv = pd.DataFrame(invoices)
                edit_mode_inv = st.toggle("✏️ Számlák szerkesztése", key="db_inv_toggle")
                col_sort_inv, col_order_inv = st.columns([2, 1])
                with col_sort_inv:
                    sortable_cols_inv = [c for c in df_inv.columns if c != "ID"]
                    sort_col_inv = st.selectbox("Rendezés alapja:", sortable_cols_inv, index=0, key="db_inv_sort")
                with col_order_inv:
                    ascending_inv = st.checkbox("Növekvő sorrend", value=False, key="db_inv_asc")
                df_inv = df_inv.sort_values(by=sort_col_inv, ascending=ascending_inv).reset_index(drop=True)
                if edit_mode_inv:
                    st.info("💡 Kattints duplán a cellákra a szerkesztéshez!")
                    st.data_editor(df_inv, key="db_inv_editor", num_rows="dynamic",
                                   column_config={"ID": None}, use_container_width=True)
                    if st.button("💾 Számlák mentése a felhőbe", type="primary", key="db_inv_save_btn"):
                        changes = st.session_state["db_inv_editor"]
                        if changes.get("edited_rows") or changes.get("added_rows") or changes.get("deleted_rows"):
                            try:
                                for row_idx in changes.get("deleted_rows", []):
                                    fs_db.collection(FIRESTORE_INVOICES).document(df_inv.iloc[row_idx]["ID"]).delete()
                                for row_idx, edits in changes.get("edited_rows", {}).items():
                                    doc_id = df_inv.iloc[row_idx]["ID"]
                                    if edits:
                                        fs_db.collection(FIRESTORE_INVOICES).document(doc_id).update(edits)
                                for new_row in changes.get("added_rows", []):
                                    add_data = {k: v for k, v in new_row.items() if k != "ID"}
                                    if add_data:
                                        fs_db.collection(FIRESTORE_INVOICES).add(add_data)
                                st.toast("✅ Sikeresen frissítetted a számlákat!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Mentési hiba: {e}")
                        else:
                            st.info("Nem történt változtatás.")
                else:
                    st.dataframe(df_inv.drop(columns=["ID"]), use_container_width=True)
            else:
                st.info("Még nincsenek számlák a Firestore adatbázisban.")
                
        elif view_selection == "🏛️ Legacy Adatok" and logged_in:
            legacy_data_fs = get_legacy_totals_fs(fs_db)
            if legacy_data_fs:
                df_leg = pd.DataFrame(legacy_data_fs)
                edit_mode_leg = st.toggle("✏️ Legacy Adatok szerkesztése", key="db_leg_toggle")
                df_leg = df_leg.sort_values(by="name").reset_index(drop=True)
                if edit_mode_leg:
                    st.info("💡 Kattints duplán a cellákra a szerkesztéshez! A tagnév (name) módosítása vagy törlése megengedett.")
                    st.data_editor(df_leg, key="db_leg_editor", num_rows="dynamic", use_container_width=True)
                    if st.button("💾 Legacy mentése a felhőbe", type="primary", key="db_leg_save_btn"):
                        changes = st.session_state["db_leg_editor"]
                        if changes.get("edited_rows") or changes.get("added_rows") or changes.get("deleted_rows"):
                            try:
                                for row_idx in changes.get("deleted_rows", []):
                                    doc_id = str(df_leg.iloc[row_idx]["name"]).replace(" ", "_")
                                    fs_db.collection(FIRESTORE_LEGACY).document(doc_id).delete()
                                for row_idx, edits in changes.get("edited_rows", {}).items():
                                    orig_name = str(df_leg.iloc[row_idx]["name"])
                                    doc_id = orig_name.replace(" ", "_")
                                    if edits:
                                        fs_db.collection(FIRESTORE_LEGACY).document(doc_id).update(edits)
                                for new_row in changes.get("added_rows", []):
                                    if "name" in new_row and new_row["name"]:
                                        doc_id = str(new_row["name"]).replace(" ", "_")
                                        fs_db.collection(FIRESTORE_LEGACY).document(doc_id).set(new_row)
                                st.toast("✅ Sikeresen frissítetted a legacy adatokat!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Mentési hiba: {e}")
                        else:
                            st.info("Nem történt változtatás.")
                else:
                    st.dataframe(df_leg, use_container_width=True)
            else:
                st.info("Még nincsenek legacy adatok a Firestore-ban. Használd a betöltés gombot a Szinkronizálás fül alatt!")

    with tab_diagramok:
        st.subheader("📊 Jelenléti Statisztikák")
        df_chart_source = get_attendance_rows_fs(fs_db)
        
        col_cd1, col_cd2 = st.columns(2)
        with col_cd1:
            # We provide current year as default and some static options
            cur_year = datetime.now().year
            chart_year = st.selectbox("Év kiválasztása:", sorted(list(set([cur_year, 2026, 2025, 2024])), reverse=True), key="chart_ev")
        with col_cd2:
            chart_month = st.selectbox("Hónap kiválasztása (csak havi diagramhoz):", list(range(1, 13)), index=datetime.now().month-1, key="chart_ho")
            
        st.markdown("---")
        render_monthly_attendance_chart(df_chart_source, chart_year, chart_month)
        st.markdown("---")
        render_yearly_attendance_chart(df_chart_source, chart_year)

    with tab_ranglista:
        st.subheader("Részvételi Ranglista")
        rows = get_attendance_rows_gs(gs_client)
        legacy_data_fs = get_legacy_totals_fs(fs_db)
        if rows:
            v = st.selectbox("Év kiválasztása:", ["All time", "2024", "2025", "2026"], key="ranglista_ev")
            totals = build_total_attendance(rows, int(v) if v != "All time" else None)
            
            legacy = {}
            for rec in legacy_data_fs:
                name = rec.get("name", "")
                if not name: continue
                if v == "All time":
                    legacy[name] = rec.get("total_all_time", 0)
                elif v == "2024":
                    legacy[name] = rec.get("year_2024", 0)
                elif v == "2025":
                    legacy[name] = rec.get("year_2025", 0)
                elif v == "2026":
                    legacy[name] = rec.get("year_2026", 0)

            for n, c in totals.items():
                legacy[n] = legacy.get(n, 0) + c
            data = [{"Helyezés": i, "Név": n, "Összes Részvétel": c}
                    for i, (n, c) in enumerate(sorted(legacy.items(), key=lambda x: (-x[1], x[0])), 1) if c > 0]
            
            tab_rl_lista, tab_rl_top5 = st.tabs(["📋 Adattábla", "🏅 Top 5 Hősök"])
            
            with tab_rl_lista:
                st.dataframe(data, use_container_width=True)
            
            with tab_rl_top5:
                render_top5_chart(data)
        else:
            st.warning("Nem sikerült betölteni a Google Sheets adatokat.")
