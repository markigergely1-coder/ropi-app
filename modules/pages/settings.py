import streamlit as st
import calendar
from io import BytesIO
from google.cloud import firestore

from modules.config import FIRESTORE_CANCELLED
from modules.db import get_cancelled_sessions_fs


def _generate_qr_bytes(url):
    import qrcode
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_settings_page(fs_db):
    st.title("⚙️ Beállítások (Kivételek)")

    with st.container(border=True):
        st.subheader("📲 QR Check-in kód")
        try:
            checkin_url = st.secrets["app"]["checkin_url"]
        except Exception:
            checkin_url = "https://markigergely1-coder.github.io/ropi-app/checkin.html"
        col_qr, col_info = st.columns([1, 2], vertical_alignment="center")
        with col_qr:
            st.image(_generate_qr_bytes(checkin_url), width=180)
        with col_info:
            st.markdown("**Check-in URL:**")
            st.code(checkin_url, language=None)
            st.caption("Nyomtasd ki vagy jelenítsd meg a teremben. A tagok ezzel jelentkeznek be.")
    st.markdown("---")

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
