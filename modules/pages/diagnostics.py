import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore

from modules.config import FIRESTORE_APP_LOGS
from modules.logger import get_logs_fs
from modules.db import get_firestore_db, get_gsheet_connection

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
                        # Próbáljuk meg lekérni a kliens infóját
                        if gs_client:
                            # a gspread egy gyors API hívással lekérdezi a felhasználót 
                            # vagy egy sheet nevet, ami igazolja hogy a ping sikeres
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
                            # Írás/olvasás teszt egy temporary gyűjteményben
                            doc_ref = fs_db.collection("test_ping").document("ping")
                            doc_ref.set({"timestamp": firestore.SERVER_TIMESTAMP})
                            data = doc_ref.get().to_dict()
                            if data:
                                st.success("✅ OK! (Dokumentum írás/olvasás sikeres)")
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
                if email_cfg and "api_key" in email_cfg:
                    st.success("✅ Email API kulcs beállítva a secrets-ben.")
                else:
                    st.warning("🟡 Nincs 'email' vagy 'api_key' beállítva a Streamlit Secrets-ben. Az e-mail küldő funkciók nem fognak működni.")
                    
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
                    "Színtek szűrése", 
                    options=["INFO", "WARNING", "ERROR"], 
                    default=["INFO", "WARNING", "ERROR"]
                )
            
            filtered_df = df[df["level"].isin(filter_level)]
            
            # Formázunk egy picit a táblázaton, hogy jobban olvasható legyen
            display_cols = ["created_at_local", "level", "message", "user_name", "ip_address", "details"]
            existent_cols = [c for c in display_cols if c in filtered_df.columns]
            
            st.dataframe(filtered_df[existent_cols], use_container_width=True)
            
            with col_del:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Összes Log Törlése", type="primary"):
                    with st.spinner("Törlés folyamatban..."):
                        try:
                            batch = fs_db.batch()
                            docs = fs_db.collection(FIRESTORE_APP_LOGS).stream()
                            deleted = 0
                            for val in docs:
                                batch.delete(val.reference)
                                deleted += 1
                            if deleted > 0:
                                batch.commit()
                            get_logs_fs.clear()
                            st.success(f"{deleted} napló elem törölve.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Hiba törléskor: {e}")
                            
