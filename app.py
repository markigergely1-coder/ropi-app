import streamlit as st

from modules.db import get_gsheet_connection, get_firestore_db, get_members_fs
from modules.utils import generate_tuesday_dates
from modules.pages.admin import render_admin_page, reset_admin_form
from modules.pages.overview import render_attendance_overview_page
from modules.pages.database import render_database_page
from modules.pages.accounting import render_accounting_page
from modules.pages.members import render_members_page
from modules.pages.payments import render_payment_check_page
from modules.pages.settings import render_settings_page
from modules.pages.checkin import render_checkin_page

st.set_page_config(page_title="Röpi App Pro", layout="wide", page_icon="🏐")

gs_client = get_gsheet_connection()
fs_db = get_firestore_db()

# QR check-in oldal — publikus, login/sidebar nélkül
if st.query_params.get("checkin") == "1":
    render_checkin_page(fs_db)
    st.stop()

if 'admin_step' not in st.session_state:
    reset_admin_form()
if 'admin_date' not in st.session_state:
    st.session_state.admin_date = generate_tuesday_dates()[0]
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False


def check_login(email_input, password_input):
    try:
        correct_password = st.secrets["auth"]["password"]
    except Exception:
        correct_password = "Gergo2010"
    if password_input != correct_password:
        return False
    try:
        members_df = get_members_fs(fs_db)
        if members_df.empty:
            return False
        valid_emails = [e.strip().lower() for e in members_df["Email"].tolist() if e]
        return email_input.strip().lower() in valid_emails
    except Exception:
        return False


def render_login_dialog():
    with st.sidebar.expander("🔐 Bejelentkezés", expanded=True):
        login_email = st.text_input("Email cím:", key="input_login_email")
        login_password = st.text_input("Jelszó:", type="password", key="input_login_password")
        if st.button("Belépés", type="primary", use_container_width=True):
            if check_login(login_email, login_password):
                st.session_state.logged_in = True
                st.session_state.logged_in_as = login_email
                st.rerun()
            else:
                st.error("Hibás email vagy jelszó!")


st.sidebar.title("🏐 Röpi App Pro")
st.sidebar.markdown("---")

PUBLIC_PAGES  = ["Admin Regisztráció", "Alkalmak Áttekintése", "Adatbázis"]
PRIVATE_PAGES = ["Havi Elszámolás", "💳 Befizetések Ellenőrzése", "👤 Tagok & Email", "Beállítások (Kivételek)"]

if st.session_state.logged_in:
    page = st.sidebar.radio("Menü", PUBLIC_PAGES + PRIVATE_PAGES)
    with st.sidebar:
        st.markdown("---")
        st.markdown("👤 Bejelentkezve")
        if st.button("🚪 Kijelentkezés", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.pop("logged_in_as", None)
            st.rerun()
else:
    page = st.sidebar.radio("Menü", PUBLIC_PAGES)
    st.sidebar.markdown("---")
    render_login_dialog()

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
    render_database_page(gs_client, fs_db, logged_in=st.session_state.logged_in)
elif page == "Havi Elszámolás" and st.session_state.logged_in:
    render_accounting_page(fs_db, gs_client)
elif page == "💳 Befizetések Ellenőrzése" and st.session_state.logged_in:
    render_payment_check_page(fs_db, gs_client)
elif page == "👤 Tagok & Email" and st.session_state.logged_in:
    render_members_page(fs_db, gs_client)
elif page == "Beállítások (Kivételek)" and st.session_state.logged_in:
    render_settings_page(fs_db)
