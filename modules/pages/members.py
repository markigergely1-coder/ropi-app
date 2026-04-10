import streamlit as st
import re

from modules.config import MAIN_NAME_LIST, GSHEET_NAME, MEMBERS_SHEET_NAME
from modules.db import get_members_fs, sync_members_fs_to_gs, sync_members_gs_to_fs


def render_members_page(fs_db, gs_client):
    st.title("👤 Tagok & Email Beállítások")
    st.markdown("Itt kezelheted a tagok email címeit. Az adatok **mindkét adatbázisban** tárolódnak.")
    tab1, tab2 = st.tabs(["📋 Tagok listája", "🔄 Szinkronizálás"])

    with tab1:
        df = get_members_fs(fs_db)
        with st.expander("➕ Új tag hozzáadása"):
            existing_names = list(df["Név"]) if not df.empty else []
            available_names = [n for n in MAIN_NAME_LIST if n not in existing_names]
            name_options = ["-- Válassz a listából --"] + available_names + ["-- Egyéni név megadása --"]
            selected_option = st.selectbox("Válassz egy nevet a listából:", name_options, key="new_m_select")
            if selected_option == "-- Egyéni név megadása --":
                new_name = st.text_input("Egyéni teljes név:", key="new_m_name_custom")
            elif selected_option == "-- Válassz a listából --":
                new_name = ""
                st.caption("Válassz egy nevet, vagy add meg egyénileg.")
            else:
                new_name = selected_option
                st.info(f"Kiválasztva: **{new_name}**")
            new_email = st.text_input("Email cím:", key="new_m_email")
            new_active = st.checkbox("Aktív tag", value=True, key="new_m_active")
            if st.button("💾 Mentés mindkét adatbázisba", type="primary"):
                if not new_name or not new_email:
                    st.warning("Töltsd ki a nevet és az email-t!")
                elif not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', new_email):
                    st.warning("Érvényes email cím szükséges! (pl: nev@domain.hu)")
                else:
                    try:
                        fs_db.collection("members").add({"name": new_name, "email": new_email, "active": new_active})
                        ss = gs_client.open(GSHEET_NAME)
                        ws_titles = [w.title for w in ss.worksheets()]
                        if MEMBERS_SHEET_NAME not in ws_titles:
                            ws = ss.add_worksheet(title=MEMBERS_SHEET_NAME, rows=100, cols=5)
                            ws.append_row(["Név", "Email", "Aktív"])
                        else:
                            ws = ss.worksheet(MEMBERS_SHEET_NAME)
                        ws.append_row([new_name, new_email, str(new_active)])
                        st.toast(f"✅ {new_name} sikeresen hozzáadva!")
                        get_members_fs.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hiba: {e}")
        st.markdown("---")
        if df.empty:
            st.info("Még nincsenek tagok. Add hozzá őket fentebb!")
        else:
            edit_mode = st.toggle("✏️ Szerkesztés mód", key="members_edit_toggle")
            if edit_mode:
                st.info("💡 Szerkeszd a cellákat, majd kattints a Mentés gombra.")
                st.data_editor(df, key="members_editor",
                               column_config={"ID": None, "Aktív": st.column_config.CheckboxColumn("Aktív")},
                               use_container_width=True, num_rows="dynamic")
                if st.button("💾 Változtatások mentése (Firestore + Sheet)", type="primary"):
                    try:
                        changes = st.session_state["members_editor"]
                        for idx in changes.get("deleted_rows", []):
                            fs_db.collection("members").document(df.iloc[idx]["ID"]).delete()
                        field_map = {"Név": "name", "Email": "email", "Aktív": "active"}
                        for idx, edits in changes.get("edited_rows", {}).items():
                            doc_id = df.iloc[idx]["ID"]
                            update = {field_map[k]: v for k, v in edits.items() if k in field_map}
                            if update:
                                fs_db.collection("members").document(doc_id).update(update)
                        for new_row in changes.get("added_rows", []):
                            fs_db.collection("members").add({
                                "name": new_row.get("Név", ""), "email": new_row.get("Email", ""), "active": new_row.get("Aktív", True)
                            })
                        get_members_fs.clear()
                        ok, msg = sync_members_fs_to_gs(fs_db, gs_client)
                        st.toast(f"✅ Mentve! {msg}" if ok else f"⚠️ Firestore OK, de Sheet hiba: {msg}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hiba: {e}")
            else:
                st.dataframe(df.drop(columns=["ID"]), use_container_width=True)

    with tab2:
        st.subheader("🔄 Tagok szinkronizálása")
        st.warning("A szinkronizálás felülírja a céladatbázist!")
        direction = st.radio("Irány:", ["Firestore → Google Sheet", "Google Sheet → Firestore"], horizontal=True)
        if st.button("🔄 Szinkronizálás indítása", type="primary"):
            with st.spinner("Folyamatban..."):
                if direction == "Firestore → Google Sheet":
                    ok, msg = sync_members_fs_to_gs(fs_db, gs_client)
                else:
                    ok, msg = sync_members_gs_to_fs(gs_client, fs_db)
                    get_members_fs.clear()
                st.toast(f"✅ {msg}" if ok else f"❌ {msg}")
                st.rerun()
