import streamlit as st

from modules.db import get_gsheet_connection, get_firestore_db
from modules.utils import generate_tuesday_dates
from modules.pages.admin import reset_admin_form  # startup-kor kell (session_state init)
from modules.logger import log_event

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
_raw = st.secrets.get("app", {}).get("admin_emails", [])
ADMIN_EMAILS = [e.strip().lower() for e in _raw]

logged_in = bool(st.user.is_logged_in and st.user.email.lower() in ADMIN_EMAILS)
st.session_state.logged_in = logged_in

# Alapvető oldal meglátogatás naplózása (mindenki - vendég és admin is)
if "visit_logged" not in st.session_state:
    szerep = "Admin" if logged_in else "Vendég"
    melyik_oldal = "QR Checkin oldal" if st.query_params.get("checkin") == "1" else "Főoldal"
    log_event(fs_db, "INFO", f"Új látogató ({szerep})", {"oldal": melyik_oldal})
    st.session_state.visit_logged = True

# Külön logoljuk a sikeres admin bejelentkezést (ha később lép be)
if logged_in:
    if "admin_login_logged" not in st.session_state:
        log_event(fs_db, "INFO", "Sikeres Admin bejelentkezés", {"email": st.user.email})
        st.session_state.admin_login_logged = True

# --- Sidebar ---
st.sidebar.title("🏐 Röpi App Pro")
st.sidebar.markdown("---")

PUBLIC_PAGES  = ["Admin Regisztráció", "Alkalmak Áttekintése", "Adatbázis", "📲 Check-in QR"]
PRIVATE_PAGES = ["📊 Játékos Profil", "Havi Elszámolás", "💳 Befizetések Ellenőrzése", "👤 Tagok & Email", "Beállítások (Kivételek)", "🛠️ Rendszer Diagnosztika"]

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
            if st.button("🔑 Bejelentkezés Google fiókkal",
                         type="primary", use_container_width=True):
                st.login("google")

with st.sidebar:
    st.markdown("---")
    st.markdown("**Kapcsolatok:**")
    st.markdown("🟢 Google Sheet" if gs_client else "🔴 Google Sheet")
    st.markdown("🟢 Firestore" if fs_db else "🔴 Firestore")
    email_ok = hasattr(st, 'secrets') and "email" in st.secrets
    st.markdown("🟢 Email" if email_ok else "🟡 Email (nincs beállítva)")

if page == "Admin Regisztráció":
    from modules.pages.admin import render_admin_page
    render_admin_page(gs_client, fs_db)
elif page == "Alkalmak Áttekintése":
    from modules.pages.overview import render_attendance_overview_page
    render_attendance_overview_page(fs_db)
elif page == "Adatbázis":
    from modules.pages.database import render_database_page
    render_database_page(gs_client, fs_db, logged_in=logged_in)
elif page == "📊 Játékos Profil":
    from modules.pages.profile import render_player_profile_page
    render_player_profile_page(fs_db)
elif page == "Havi Elszámolás" and logged_in:
    from modules.pages.accounting import render_accounting_page
    render_accounting_page(fs_db, gs_client)
elif page == "💳 Befizetések Ellenőrzése" and logged_in:
    from modules.pages.payments import render_payment_check_page
    render_payment_check_page(fs_db, gs_client)
elif page == "👤 Tagok & Email" and logged_in:
    from modules.pages.members import render_members_page
    render_members_page(fs_db, gs_client)
elif page == "Beállítások (Kivételek)" and logged_in:
    from modules.pages.settings import render_settings_page
    render_settings_page(fs_db)
elif page == "🛠️ Rendszer Diagnosztika" and logged_in:
    from modules.pages.diagnostics import render_diagnostics_page
    render_diagnostics_page(fs_db, gs_client)
elif page == "📲 Check-in QR":
    from modules.pages.qr_page import render_qr_page
    render_qr_page()
