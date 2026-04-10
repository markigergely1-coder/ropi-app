import streamlit as st

from modules.db import get_gsheet_connection, get_firestore_db
from modules.utils import generate_tuesday_dates
from modules.pages.admin import render_admin_page, reset_admin_form
from modules.pages.overview import render_attendance_overview_page
from modules.pages.database import render_database_page
from modules.pages.accounting import render_accounting_page
from modules.pages.members import render_members_page
from modules.pages.payments import render_payment_check_page
from modules.pages.settings import render_settings_page
from modules.pages.qr_page import render_qr_page

st.set_page_config(page_title="Röpi App Pro", layout="wide", page_icon="🏐")

gs_client = get_gsheet_connection()
fs_db = get_firestore_db()

# QR check-in oldal — publikus, login/sidebar nélkül
if st.query_params.get("checkin") == "1":
    from modules.pages.checkin import render_checkin_page
    render_checkin_page(fs_db)
    st.stop()

if 'admin_step' not in st.session_state:
    reset_admin_form()
if 'admin_date' not in st.session_state:
    st.session_state.admin_date = generate_tuesday_dates()[0]

# --- Google OAuth alapú admin hozzáférés ---
_raw = st.secrets.get("auth", {}).get("admin_emails", [])
ADMIN_EMAILS = [e.strip().lower() for e in _raw]

logged_in = bool(st.user.is_logged_in and st.user.email.lower() in ADMIN_EMAILS)
st.session_state.logged_in = logged_in

# --- Sidebar ---
st.sidebar.title("🏐 Röpi App Pro")
st.sidebar.markdown("---")

PUBLIC_PAGES  = ["Admin Regisztráció", "Alkalmak Áttekintése", "Adatbázis", "📲 Check-in QR"]
PRIVATE_PAGES = ["Havi Elszámolás", "💳 Befizetések Ellenőrzése", "👤 Tagok & Email", "Beállítások (Kivételek)"]

if logged_in:
    page = st.sidebar.radio("Menü", PUBLIC_PAGES + PRIVATE_PAGES)
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"👤 **{st.user.name}**")
        if st.button("🚪 Kijelentkezés", use_container_width=True):
            st.logout()
else:
    page = st.sidebar.radio("Menü", PUBLIC_PAGES)
    with st.sidebar:
        st.markdown("---")
        if st.user.is_logged_in:
            st.warning("⛔ Nincs admin jogosultságod.")
            if st.button("🚪 Kijelentkezés", use_container_width=True):
                st.logout()
        else:
            st.button(
                "🔑 Bejelentkezés Google fiókkal",
                on_click=st.login, args=["google"],
                type="primary", use_container_width=True,
            )

with st.sidebar:
    st.markdown("---")
    st.markdown("**Kapcsolatok:**")
    st.markdown("🟢 Google Sheet" if gs_client else "🔴 Google Sheet")
    st.markdown("🟢 Firestore" if fs_db else "🔴 Firestore")
    email_ok = hasattr(st, 'secrets') and "email" in st.secrets
    st.markdown("🟢 Email" if email_ok else "🟡 Email (nincs beállítva)")

if page == "Admin Regisztráció":
    render_admin_page(gs_client, fs_db)
elif page == "Alkalmak Áttekintése":
    render_attendance_overview_page(fs_db)
elif page == "Adatbázis":
    render_database_page(gs_client, fs_db, logged_in=logged_in)
elif page == "Havi Elszámolás" and logged_in:
    render_accounting_page(fs_db, gs_client)
elif page == "💳 Befizetések Ellenőrzése" and logged_in:
    render_payment_check_page(fs_db, gs_client)
elif page == "👤 Tagok & Email" and logged_in:
    render_members_page(fs_db, gs_client)
elif page == "Beállítások (Kivételek)" and logged_in:
    render_settings_page(fs_db)
elif page == "📲 Check-in QR":
    render_qr_page()
