import streamlit as st
import time
from datetime import datetime

from modules.config import MAIN_NAME_LIST, PLUS_PEOPLE_COUNT, HUNGARY_TZ
from modules.db import get_attendance_rows_gs, save_all_data, sync_qr_checkins_to_sheet
from modules.utils import generate_tuesday_dates, get_historical_guests_list


def reset_admin_form(set_step=1):
    st.session_state.admin_step = set_step
    st.session_state.admin_attendance = {name: {"present": False, "guests": "0"} for name in MAIN_NAME_LIST}
    st.session_state.admin_guest_data = {}


def admin_save_guest_name(key):
    st.session_state.admin_guest_data[key] = st.session_state.get(key, "")


def admin_save_date():
    st.session_state.admin_date = st.session_state.admin_date_selector


def render_admin_page(gs_client, fs_client):
    st.title("🛠️ Admin Regisztráció")
    st.success("🟢 Aktív: Jelenlét rögzítése üzemmód.")
    if "qr_sync_done" not in st.session_state:
        synced = sync_qr_checkins_to_sheet(fs_client, gs_client)
        st.session_state.qr_sync_done = True
        if synced > 0:
            st.toast(f"✅ {synced} QR check-in szinkronizálva a Sheetsbe.", icon="📊")
    rows = get_attendance_rows_gs(gs_client)

    if st.session_state.admin_step == 1:
        dt = generate_tuesday_dates()
        idx = dt.index(st.session_state.admin_date) if st.session_state.admin_date in dt else 0
        st.selectbox("Dátum kiválasztása:", dt, index=idx, key="admin_date_selector", on_change=admin_save_date)
        st.markdown("---")
        for name in MAIN_NAME_LIST:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="center")
                c1.markdown(f"**{name}**")
                st.session_state.admin_attendance[name]["present"] = c2.checkbox(
                    "Jelen volt", value=st.session_state.admin_attendance[name]["present"], key=f"p_{name}")
                st.session_state.admin_attendance[name]["guests"] = c3.selectbox(
                    "Vendégek száma", PLUS_PEOPLE_COUNT,
                    index=PLUS_PEOPLE_COUNT.index(st.session_state.admin_attendance[name]["guests"]),
                    key=f"g_{name}", label_visibility="collapsed")
        st.markdown("---")
        present_count = sum(1 for d in st.session_state.admin_attendance.values() if d["present"])
        if present_count == 0:
            st.warning("⚠️ Még senki nincs bejelölve!")
        if st.button("Tovább a vendégnevekhez ➡️", type="primary", disabled=(present_count == 0)):
            st.session_state.admin_step = 2
            st.rerun()

    elif st.session_state.admin_step == 2:
        pg = [(n, int(d["guests"])) for n, d in st.session_state.admin_attendance.items()
              if d["present"] and int(d["guests"]) > 0]
        st.info(f"Kiválasztott dátum: {st.session_state.admin_date}")
        if not pg:
            st.success("Nincsenek rögzítendő vendégek. Készen állsz a mentésre!")
        for n, c in pg:
            with st.container(border=True):
                st.subheader(f"**{n}** vendégei:")
                history = get_historical_guests_list(rows, n)
                options = ["-- Új név írása --"] + history
                for i in range(c):
                    sel = st.selectbox(f"{i+1}. vendég ({n}):", options, key=f"admin_sel_{n}_{i}")
                    if sel == "-- Új név írása --":
                        st.text_input(f"Vendég pontos neve:", key=f"admin_guest_{n}_{i}",
                                      on_change=admin_save_guest_name, args=(f"admin_guest_{n}_{i}",))
                    else:
                        st.session_state.admin_guest_data[f"admin_guest_{n}_{i}"] = sel
        st.markdown("---")
        c1, c2 = st.columns(2)
        if c1.button("⬅️ Vissza"):
            st.session_state.admin_step = 1
            st.rerun()
        if c2.button("Adatok ellenőrzése", type="primary"):
            st.session_state.admin_step = 3
            st.rerun()

    elif st.session_state.admin_step == 3:
        st.info(f"Dátum: {st.session_state.admin_date}")
        st.subheader("Összesítés:")
        present_list = [n for n, d in st.session_state.admin_attendance.items() if d["present"]]
        for name in present_list:
            st.markdown(f"✅ **{name}**")
            for i in range(int(st.session_state.admin_attendance[name]["guests"])):
                g = st.session_state.admin_guest_data.get(f"admin_guest_{name}_{i}", "")
                if g:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;↳ {g}")
        st.markdown("---")
        if st.button("💾 Végleges Mentés", type="primary"):
            try:
                target_date = st.session_state.admin_date
                ts = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
                rows_to_add = []
                for name, data in st.session_state.admin_attendance.items():
                    if data["present"]:
                        rows_to_add.append([name, "Yes", ts, target_date, "", "valós"])
                        for i in range(int(data["guests"])):
                            g_name = st.session_state.admin_guest_data.get(f"admin_guest_{name}_{i}", "").strip()
                            if g_name:
                                rows_to_add.append([f"{name} - {g_name}", "Yes", ts, target_date, "", "valós"])
                success, msg = save_all_data(gs_client, fs_client, rows_to_add)
                if success:
                    st.success(msg)
                    reset_admin_form()
                    time.sleep(3)
                    st.rerun()
                else:
                    st.warning(msg)
                    time.sleep(4)
                    reset_admin_form()
                    st.rerun()
            except Exception as e:
                st.error(f"Hiba: {e}")
        if st.button("⬅️ Vissza a szerkesztéshez"):
            st.session_state.admin_step = 2
            st.rerun()
