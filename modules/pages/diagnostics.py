import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore

from modules.config import FIRESTORE_APP_LOGS
from modules.logger import get_logs_fs


def render_diagnostics_page(fs_db, gs_client):
    st.title("🛠️ Rendszer Diagnosztika")

    tab_tests, tab_logs = st.tabs(["🩺 Felhő Tesztek", "📜 Rendszernapló (Logok)"])

    with tab_tests:
        st.subheader("Kapcsolatok Tesztelése")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("### Google Sheets")
            if st.button("🔄 GS Kapcsolat Teszt", use_container_width=True):
                with st.spinner("Tesztelés..."):
                    try:
                        if gs_client:
                            ss = gs_client.open(st.secrets.get("app", {}).get("gsheet_name", "Attendance"))
                            st.success(f"✅ OK! (Nyitva: {ss.title})")
                        else:
                            st.error("❌ Hiba: Kliens nem jött létre. Hibás credentials?")
                    except Exception as e:
                        st.error(f"❌ Kapcsolati Hiba: {e}")

        with col2:
            st.markdown("### Firestore (DB)")
            if st.button("🔥 FS Kapcsolat Teszt", use_container_width=True):
                with st.spinner("Tesztelés..."):
                    try:
                        if fs_db:
                            # Írás/olvasás teszt, majd azonnali törlés
                            doc_ref = fs_db.collection("test_ping").document("ping")
                            doc_ref.set({"timestamp": firestore.SERVER_TIMESTAMP})
                            data = doc_ref.get().to_dict()
                            doc_ref.delete()  # Teszt dokumentum azonnal törlődik
                            if data:
                                st.success("✅ OK! (Dokumentum írás/olvasás/törlés sikeres)")
                            else:
                                st.warning("Adatbázis elérhető, de az olvasás üreset adott.")
                        else:
                            st.error("❌ Hiba: Firestore db kliens nincs inicializálva.")
                    except Exception as e:
                        st.error(f"❌ Inicializálási Hiba: {e}")

        with col3:
            st.markdown("### Külső Email")
            if st.button("📧 Email Környezet Teszt", use_container_width=True):
                email_cfg = st.secrets.get("email") if hasattr(st, "secrets") else None
                if email_cfg and "sender" in email_cfg and "password" in email_cfg:
                    st.success(f"✅ Email környezet beállítva (Küldő: {email_cfg['sender']}).")
                else:
                    st.warning("🟡 Nincs 'email' szekció beállítva a Streamlit Secrets-ben ('sender' és 'password').")

    with tab_logs:
        st.subheader("Belső App Események (Logok)")
        st.write("Itt követheted nyomon az app működését, hibákat és rendszerüzeneteket.")

        if fs_db is None:
            st.error("A Firestore nem elérhető, a logok nem tölthetőek be.")
            return

        logs = get_logs_fs(fs_db, limit=300)

        if not logs:
            st.info("Nincs rögzített log esemény.")
        else:
            df = pd.DataFrame(logs)
            if "created_at_local" not in df.columns:
                df["created_at_local"] = ""
            if "ip_address" not in df.columns:
                df["ip_address"] = ""

            col_filter, col_del = st.columns([3, 1])
            with col_filter:
                filter_level = st.multiselect(
                    "Szintek szűrése",
                    options=["INFO", "WARNING", "ERROR"],
                    default=["INFO", "WARNING", "ERROR"]
                )

            filtered_df = df[df["level"].isin(filter_level)]
            display_cols = ["created_at_local", "level", "message", "user_name", "ip_address", "details"]
            existent_cols = [c for c in display_cols if c in filtered_df.columns]
            st.dataframe(filtered_df[existent_cols], use_container_width=True)

            with col_del:
                st.markdown("<br>", unsafe_allow_html=True)
                # Megerősítési lépés véletlenszerű törlés ellen
                if "confirm_delete_logs" not in st.session_state:
                    st.session_state.confirm_delete_logs = False

                if not st.session_state.confirm_delete_logs:
                    if st.button("🗑️ Összes Log Törlése", use_container_width=True):
                        st.session_state.confirm_delete_logs = True
                        st.rerun()
                else:
                    st.warning("Biztos vagy benne?")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Igen", use_container_width=True, type="primary"):
                        with st.spinner("Törlés..."):
                            try:
                                # Chunkolás: max 500/batch (Firestore limit)
                                deleted = 0
                                while True:
                                    docs_chunk = list(fs_db.collection(FIRESTORE_APP_LOGS).limit(500).stream())
                                    if not docs_chunk:
                                        break
                                    batch = fs_db.batch()
                                    for d in docs_chunk:
                                        batch.delete(d.reference)
                                    batch.commit()
                                    deleted += len(docs_chunk)
                                get_logs_fs.clear()
                                st.session_state.confirm_delete_logs = False
                                st.success(f"{deleted} napló elem törölve.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Hiba törléskor: {e}")
                    if c2.button("❌ Mégse", use_container_width=True):
                        st.session_state.confirm_delete_logs = False
                        st.rerun()
