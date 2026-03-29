import streamlit as st
from datetime import datetime

from streamlit_js_eval import streamlit_js_eval

from modules.config import MAIN_NAME_LIST, FIRESTORE_MEMBERS, HUNGARY_TZ
from modules.db import (
    get_members_fs, get_device_registration, save_device_registration, save_all_data,
)
from modules.utils import generate_tuesday_dates


def _get_event_date():
    """Visszaadja a legutóbbi kedd dátumát (ma, ha ma kedd)."""
    dates = generate_tuesday_dates(past_count=1, future_count=0)
    return dates[0]


def _already_checked_in(fs_db, name, event_date):
    """Ellenőrzi, hogy a tag már be van-e jelentkezve QR-rel erre az alkalomra."""
    try:
        from modules.config import FIRESTORE_COLLECTION
        docs = (
            fs_db.collection(FIRESTORE_COLLECTION)
            .where("name", "==", name)
            .where("event_date", "==", event_date)
            .where("mode", "==", "qr")
            .limit(1)
            .stream()
        )
        return any(True for _ in docs)
    except Exception:
        return False


def _register_attendance(fs_db, name, event_date):
    """Jelenlét rögzítése a Firestore attendance_records collectionbe."""
    ts = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
    row = [name, "Yes", ts, event_date, "", "qr"]
    return save_all_data(None, fs_db, [row])


def _get_all_member_names(fs_db):
    """MAIN_NAME_LIST + Firestore members, duplikátum nélkül, rendezve."""
    names = set(MAIN_NAME_LIST)
    try:
        df = get_members_fs(fs_db)
        if not df.empty:
            names.update(df["Név"].tolist())
    except Exception:
        pass
    return sorted(names)


def render_checkin_page(fs_db):
    st.title("🏐 Röpi Check-in")

    if fs_db is None:
        st.error("Az adatbázis nem elérhető. Kérlek próbáld újra!")
        return

    # --- State machine ---
    if "checkin_state" not in st.session_state:
        st.session_state.checkin_state = "loading"

    state = st.session_state.checkin_state

    # LOADING: localStorage-ból olvassuk/generáljuk a device_id-t
    if state == "loading":
        device_id = streamlit_js_eval(
            js_expressions="""
                (function() {
                    let did = localStorage.getItem('ropi_device_id');
                    if (!did) {
                        did = (typeof crypto !== 'undefined' && crypto.randomUUID)
                            ? crypto.randomUUID()
                            : Math.random().toString(36).substr(2, 12) + Date.now().toString(36);
                        localStorage.setItem('ropi_device_id', did);
                    }
                    return did;
                })()
            """,
            key="get_or_create_did",
        )
        if device_id:
            st.session_state.checkin_device_id = device_id
            st.session_state.checkin_state = "lookup"
            st.rerun()
        else:
            st.info("Betöltés...")
            st.stop()

    # LOOKUP: Firestore-ban keressük a device_id-t
    elif state == "lookup":
        device_id = st.session_state.get("checkin_device_id")
        name = get_device_registration(fs_db, device_id)
        if name:
            st.session_state.checkin_name = name
            st.session_state.checkin_state = "auto_register"
        else:
            st.session_state.checkin_state = "show_form"
        st.rerun()

    # AUTO_REGISTER: ismert eszköz → automatikus jelenlét
    elif state == "auto_register":
        name = st.session_state.checkin_name
        event_date = _get_event_date()

        if _already_checked_in(fs_db, name, event_date):
            st.success(f"Szia **{name}**!")
            st.info(f"✅ Már be vagy jelentkezve erre az alkalomra ({event_date}).")
            if st.button("↩️ Visszavonás", type="secondary"):
                st.session_state.checkin_state = "undo_confirm"
                st.rerun()
        else:
            with st.spinner("Jelenlét rögzítése..."):
                ok, msg = _register_attendance(fs_db, name, event_date)
            if ok:
                st.balloons()
                st.success(f"Szia **{name}**! 🏐")
                st.success(f"✅ Jelenlét rögzítve: {event_date}")
            else:
                st.error(f"Hiba a rögzítéskor: {msg}")

    # UNDO_CONFIRM: jelenlét visszavonás megerősítése
    elif state == "undo_confirm":
        name = st.session_state.checkin_name
        event_date = _get_event_date()
        st.warning(f"Biztosan visszavonod **{name}** jelenlétét ({event_date})?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Igen, visszavonom", type="primary", use_container_width=True):
                try:
                    from modules.config import FIRESTORE_COLLECTION
                    docs = (
                        fs_db.collection(FIRESTORE_COLLECTION)
                        .where("name", "==", name)
                        .where("event_date", "==", event_date)
                        .where("mode", "==", "qr")
                        .stream()
                    )
                    for doc in docs:
                        doc.reference.delete()
                    st.session_state.checkin_state = "auto_register"
                    st.rerun()
                except Exception as e:
                    st.error(f"Hiba: {e}")
        with col2:
            if st.button("Mégsem", use_container_width=True):
                st.session_state.checkin_state = "auto_register"
                st.rerun()

    # SHOW_FORM: ismeretlen eszköz → regisztrációs form
    elif state == "show_form":
        st.markdown("### Üdvözöllek! Először azonosítsd magad.")

        tab_own, tab_guest = st.tabs(["🙋 Magamnak jelentkezem", "👥 Vendégként jövök"])

        all_names = _get_all_member_names(fs_db)
        NEW_PERSON_OPTION = "➕ Nem szerepelek a listában"

        with tab_own:
            name_options = all_names + [NEW_PERSON_OPTION]
            selected = st.selectbox("Válaszd ki a neved:", name_options, key="ci_own_select")

            if selected == NEW_PERSON_OPTION:
                custom_name = st.text_input("Teljes neved:", key="ci_own_custom_name")
                custom_email = st.text_input("Email cím:", key="ci_own_email")
            else:
                custom_name = None
                custom_email = None

            if st.button("✅ Bejelentkezés", type="primary", use_container_width=True, key="ci_own_submit"):
                if selected == NEW_PERSON_OPTION:
                    name = custom_name.strip() if custom_name else ""
                    email = custom_email.strip() if custom_email else ""
                    if not name:
                        st.warning("Add meg a neved!")
                        st.stop()
                    # Új tag mentése a members collectionbe (csak FS, GSheet nélkül)
                    if email:
                        try:
                            fs_db.collection(FIRESTORE_MEMBERS).add({
                                "name": name, "email": email, "active": True
                            })
                            get_members_fs.clear()
                        except Exception:
                            pass
                else:
                    name = selected

                device_id = st.session_state.get("checkin_device_id")
                save_device_registration(fs_db, device_id, name)

                event_date = _get_event_date()
                ok, msg = _register_attendance(fs_db, name, event_date)
                if ok:
                    st.session_state.checkin_name = name
                    st.session_state.checkin_state = "auto_register"
                    st.rerun()
                else:
                    st.error(f"Hiba a jelenlét rögzítésekor: {msg}")

        with tab_guest:
            guest_name = st.text_input("A te neved (vendég):", key="ci_guest_name")
            host = st.selectbox("Kinek a vendége vagy?", all_names, key="ci_guest_host")

            if st.button("✅ Bejelentkezés vendégként", type="primary", use_container_width=True, key="ci_guest_submit"):
                g_name = guest_name.strip() if guest_name else ""
                if not g_name:
                    st.warning("Add meg a neved!")
                    st.stop()

                record_name = f"{host} - {g_name}"
                event_date = _get_event_date()
                ok, msg = _register_attendance(fs_db, record_name, event_date)
                if ok:
                    st.session_state.checkin_state = "guest_success"
                    st.session_state.checkin_guest_display = g_name
                    st.rerun()
                else:
                    st.error(f"Hiba a jelenlét rögzítésekor: {msg}")

    # GUEST_SUCCESS: vendég sikeres bejelentkezés
    elif state == "guest_success":
        g_name = st.session_state.get("checkin_guest_display", "Vendég")
        event_date = _get_event_date()
        st.balloons()
        st.success(f"Szia **{g_name}**! 🏐")
        st.success(f"✅ Vendég jelenlét rögzítve: {event_date}")
