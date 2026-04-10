import streamlit as st
import uuid
from datetime import datetime

from modules.config import MAIN_NAME_LIST, FIRESTORE_MEMBERS, HUNGARY_TZ
from modules.db import (
    get_members_fs, get_device_registration, save_device_registration, save_all_data,
)
from modules.utils import generate_tuesday_dates


def _get_event_date():
    dates = generate_tuesday_dates(past_count=1, future_count=0)
    return dates[0]


def _already_checked_in(fs_db, name, event_date):
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
    ts = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
    row = [name, "Yes", ts, event_date, "", "qr"]
    return save_all_data(None, fs_db, [row])


def _get_all_member_names(fs_db):
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

    # device_id olvasása URL query paramból
    device_id = st.query_params.get("did")

    # --- Ismert eszköz: automatikus check-in ---
    if device_id:
        name = get_device_registration(fs_db, device_id)

        if name:
            event_date = _get_event_date()

            if _already_checked_in(fs_db, name, event_date):
                st.success(f"Szia **{name}**!")
                st.info(f"✅ Már be vagy jelentkezve erre az alkalomra ({event_date}).")
                if st.button("↩️ Jelenlét visszavonása", type="secondary"):
                    try:
                        from modules.config import FIRESTORE_COLLECTION
                        docs = list(
                            fs_db.collection(FIRESTORE_COLLECTION)
                            .where("name", "==", name)
                            .where("event_date", "==", event_date)
                            .where("mode", "==", "qr")
                            .limit(5)
                            .stream()
                        )
                        if not docs:
                            st.info("A jelenlét már vissza lett vonva.")
                        else:
                            for doc in docs:
                                doc.reference.delete()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hiba: {e}")
            else:
                with st.spinner("Jelenlét rögzítése..."):
                    ok, msg = _register_attendance(fs_db, name, event_date)
                if ok:
                    st.balloons()
                    st.success(f"Szia **{name}**! 🏐")
                    st.success(f"✅ Jelenlét rögzítve: {event_date}")
                else:
                    st.error(f"Hiba a rögzítéskor: {msg}")
            return

        # Stale device_id (nem létezik Firestore-ban) → reset
        st.query_params.pop("did", None)
        st.rerun()

    # --- Ismeretlen eszköz: regisztrációs form ---
    st.markdown("### Üdvözöllek! Először azonosítsd magad.")
    st.caption("Egyszeri azonosítás — utána az eszközöd megjegyezzük.")

    all_names = _get_all_member_names(fs_db)
    NEW_PERSON_OPTION = "➕ Nem szerepelek a listában"

    tab_own, tab_guest = st.tabs(["🙋 Magamnak jelentkezem", "👥 Vendégként jövök"])

    with tab_own:
        name_options = all_names + [NEW_PERSON_OPTION]
        selected = st.selectbox("Válaszd ki a neved:", name_options, key="ci_own_select")

        custom_name = None
        custom_email = None
        if selected == NEW_PERSON_OPTION:
            custom_name = st.text_input("Teljes neved:", key="ci_own_custom_name")
            custom_email = st.text_input("Email cím (opcionális):", key="ci_own_email")

        if st.button("✅ Bejelentkezés", type="primary", use_container_width=True, key="ci_own_submit"):
            if selected == NEW_PERSON_OPTION:
                name = custom_name.strip() if custom_name else ""
                if not name:
                    st.warning("Add meg a neved!")
                    st.stop()
                email = custom_email.strip() if custom_email else ""
                if email:
                    try:
                        fs_db.collection(FIRESTORE_MEMBERS).add({
                            "name": name, "email": email, "active": True
                        })
                        get_members_fs.clear()
                    except Exception as e:
                        st.warning(f"⚠️ Az email cím mentése nem sikerült, de a jelenlét rögzítve lesz: {e}")
            else:
                name = selected

            event_date = _get_event_date()
            if _already_checked_in(fs_db, name, event_date):
                st.info(f"✅ **{name}** már be van jelentkezve erre az alkalomra ({event_date}).")
                st.stop()

            new_did = str(uuid.uuid4())
            save_device_registration(fs_db, new_did, name)

            ok, msg = _register_attendance(fs_db, name, event_date)
            if ok:
                st.query_params["did"] = new_did
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
            if _already_checked_in(fs_db, record_name, event_date):
                st.info(f"✅ **{g_name}** ({host} vendége) már be van jelentkezve erre az alkalomra ({event_date}).")
                st.stop()

            ok, msg = _register_attendance(fs_db, record_name, event_date)
            if ok:
                st.balloons()
                st.success(f"Szia **{g_name}**! 🏐")
                st.success(f"✅ Vendég jelenlét rögzítve: {event_date}")
            else:
                st.error(f"Hiba a jelenlét rögzítésekor: {msg}")
