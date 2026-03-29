import streamlit as st
import calendar
from google.cloud import firestore

from modules.config import FIRESTORE_CANCELLED
from modules.db import get_cancelled_sessions_fs


def render_settings_page(fs_db):
    st.title("⚙️ Beállítások (Kivételek)")
    st.markdown("Itt adhatod meg azokat a keddi napokat, amikor **ELMARADT** az edzés.")
    if fs_db is None:
        st.error("Nincs Firestore kapcsolat.")
        return
    with st.container(border=True):
        st.subheader("Új kivétel rögzítése")
        col1, col2 = st.columns([2, 1], vertical_alignment="bottom")
        with col1:
            new_date = st.date_input("Válaszd ki az elmaradt edzés dátumát:")
        with col2:
            if st.button("➕ Hozzáadás", type="primary", use_container_width=True):
                if new_date.weekday() != calendar.TUESDAY:
                    st.warning("⚠️ Biztos vagy benne? Ez a nap nem Keddre esik!")
                date_str = new_date.strftime("%Y-%m-%d")
                existing = get_cancelled_sessions_fs(fs_db)
                if new_date in existing:
                    st.warning("Ez a dátum már szerepel a kivételek között!")
                else:
                    try:
                        fs_db.collection(FIRESTORE_CANCELLED).add({"date": date_str})
                        st.success("Sikeresen rögzítve!")
                        st.cache_data.clear()
                        import time; time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hiba mentéskor: {e}")
    st.markdown("---")
    st.subheader("Jelenleg rögzített elmaradt edzések")
    try:
        docs = fs_db.collection(FIRESTORE_CANCELLED).order_by("date", direction=firestore.Query.DESCENDING).stream()
        cancelled_list = [{"ID": doc.id, "Dátum": doc.to_dict().get("date")} for doc in docs]
        if cancelled_list:
            for item in cancelled_list:
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1], vertical_alignment="center")
                    c1.markdown(f"🗓️ **{item['Dátum']}**")
                    if c2.button("❌ Törlés", key=f"del_{item['ID']}", use_container_width=True):
                        fs_db.collection(FIRESTORE_CANCELLED).document(item['ID']).delete()
                        st.cache_data.clear()
                        st.rerun()
        else:
            st.info("Jelenleg nincsenek elmaradt edzések rögzítve.")
    except Exception as e:
        st.error(f"Hiba a lista betöltésekor: {e}")
