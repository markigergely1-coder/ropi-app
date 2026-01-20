import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import os
import json
import pytz 

# --- KONFIGURÁCIÓ ---
CREDENTIALS_FILE = 'credentials.json'
GSHEET_NAME = 'Attendance'
MAIN_NAME_LIST = [
    "Anna Sengler", "Annamária Földváry", "Flóra", "Boti", 
    "Csanád Laczkó", "Csenge Domokos", "Detti Szabó", "Dóri Békási", 
    "Gergely Márki", "Márki Jancsi", "Kilyénfalvi Júlia", "Laura Piski", "Linda Antal", "Máté Lajer", "Nóri Sásdi", "Laci Márki", 
    "Domokos Kadosa", "Áron Szabó", "Máté Plank", "Lea Plank", "Océane Olivier"
]
LEGACY_ATTENDANCE_TOTALS = {
    "András Papp": 7,
    "Anna Sengler": 25,
    "Annamária Földváry": 36,
    "Flóra & Boti": 19,
    "Csanád Laczkó": 41,
    "Csenge Domokos": 47,
    "Detti Szabó": 39,
    "Dóri Békási": 45,
    "Gergely Márki": 342,
    "Kilyénfalvi Júlia": 3,
    "Kristóf Szelényi": 5,
    "Laura Piski": 4,
    "Léna Piski": 1,
    "Linda Antal": 3,
    "Máté Lajer": 2,
    "Nóri Sásdi": 24,
    "Laci Márki": 39,
    "Domokos Kadosa": 30,
    "Áron Szabó": 24,
    "Máté Plank": 36,
    "Lea Plank": 15,
}
YEARLY_LEGACY_TOTALS = {
    2024: {
        "András Papp": 4,
        "Anna Sengler": 7,
        "Annamária Földváry": 6,
        "Flóra & Boti": 4,
        "Csanád Laczkó": 8,
        "Csenge Domokos": 7,
        "Detti Szabó": 5,
        "Dóri Békási": 6,
        "Gergely Márki": 8,
        "Kilyénfalvi Júlia": 6,
        "Kristóf Szelényi": 4,
        "Laura Piski": 6,
        "Léna Piski": 7,
        "Linda Antal": 5,
        "Máté Lajer": 6,
        "Nóri Sásdi": 0,
        "Laci Márki": 0,
        "Domokos Kadosa": 0,
        "Áron Szabó": 0,
        "Máté Plank": 7,
        "Lea Plank": 0,
    },
    2025: {
        "András Papp": 3,
        "Anna Sengler": 19,
        "Annamária Földváry": 31,
        "Flóra & Boti": 15,
        "Csanád Laczkó": 34,
        "Csenge Domokos": 41,
        "Detti Szabó": 35,
        "Dóri Békási": 39,
        "Gergely Márki": 35,
        "Kilyénfalvi Júlia": 7,
        "Kristóf Szelényi": 1,
        "Laura Piski": 6,
        "Léna Piski": 7,
        "Linda Antal": 1,
        "Máté Lajer": 1,
        "Nóri Sásdi": 19,
        "Laci Márki": 28,
        "Domokos Kadosa": 23,
        "Áron Szabó": 16,
        "Máté Plank": 33,
        "Lea Plank": 15,
    },
}
PLUS_PEOPLE_COUNT = [str(i) for i in range(11)]
HUNGARY_TZ = pytz.timezone("Europe/Budapest") 

# --- HÁTTÉRLOGIKA (VÁLTOZATLAN) ---

@st.cache_resource(ttl=3600)
def get_gsheet_connection():
    # ... (nincs változás, hagyd úgy, ahogy van) ...
    print("GSpread: Új kapcsolat létrehozása...")
    
    if hasattr(st, 'secrets'):
        try:
            creds_json = {
                "type": st.secrets["google_creds"]["type"],
                "project_id": st.secrets["google_creds"]["project_id"],
                "private_key_id": st.secrets["google_creds"]["private_key_id"],
                "private_key": st.secrets["google_creds"]["private_key"].replace('\\n', '\n'),
                "client_email": st.secrets["google_creds"]["client_email"],
                "client_id": st.secrets["google_creds"]["client_id"],
                "auth_uri": st.secrets["google_creds"]["auth_uri"],
                "token_uri": st.secrets["google_creds"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["google_creds"]["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["google_creds"]["client_x509_cert_url"]
            }
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json)
        except Exception as e:
            st.error(f"Hiba a Streamlit titkos kulcsok olvasásakor: {e}")
            return None
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            st.error(f"Hiba: '{CREDENTIALS_FILE}' nem található.")
            return None
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE)

    try:
        client = gspread.authorize(creds)
        spreadsheet = client.open(GSHEET_NAME)
        return spreadsheet.sheet1
    except Exception as e:
        st.error(f"Google Sheets csatlakozási hiba: {e}")
        return None

@st.cache_data(ttl=300)
def get_counter_value(_gsheet):
    # ... (nincs változás, hagyd úgy, ahogy van) ...
    if _gsheet is None:
        return "N/A"
    try:
        print("GSpread: Létszám frissítése...")
        count = _gsheet.cell(2, 5).value # E2 cella
        return count
    except Exception as e:
        print(f"Hiba a létszám olvasásakor: {e}")
        return "Hiba"

def generate_tuesday_dates(past_count=8, future_count=2):
    # ... (nincs változás, hagyd úgy, ahogy van) ...
    tuesday_dates_list = []
    today = datetime.now(HUNGARY_TZ).date()
    days_since_tuesday = (today.weekday() - 1) % 7 
    last_tuesday = today - timedelta(days=days_since_tuesday)
    
    for i in range(past_count):
        past_date = last_tuesday - timedelta(weeks=i)
        tuesday_dates_list.insert(0, past_date.strftime("%Y-%m-%d")) 

    for i in range(1, future_count + 1): 
        future_date = last_tuesday + timedelta(weeks=i)
        tuesday_dates_list.append(future_date.strftime("%Y-%m-%d"))
    return tuesday_dates_list

def save_data_to_gsheet(gsheet, rows_to_add):
    # ... (nincs változás, hagyd úgy, ahogy van) ...
    if gsheet is None:
        return False, "Nincs GSheet kapcsolat."
    try:
        gsheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        print(f"GSpread: {len(rows_to_add)} sor hozzáadva.")
        st.cache_data.clear() 
        return True, "Sikeres mentés."
    except Exception as e:
        print(f"GSpread Mentési Hiba: {e}")
        return False, f"Hiba a mentés közben: {e}"

@st.cache_data(ttl=300)
def get_attendance_rows(_gsheet):
    if _gsheet is None:
        return []
    try:
        print("GSpread: Attendance adatok lekérése...")
        return _gsheet.get_all_values()
    except Exception as e:
        print(f"Hiba a Attendance adatok olvasásakor: {e}")
        return []

def parse_attendance_date(registration_value, event_value):
    date_value = event_value or registration_value
    if not date_value:
        return None
    try:
        return datetime.strptime(date_value.split(" ")[0], "%Y-%m-%d").date()
    except ValueError:
        print(f"Hiba a dátum feldolgozásakor: {date_value}")
        return None

def build_monthly_stats(rows):
    status_by_name_date = {}
    for row in rows[1:]:
        name = row[0].strip() if len(row) > 0 else ""
        response = row[1].strip() if len(row) > 1 else ""
        registration_value = row[2].strip() if len(row) > 2 else ""
        event_value = row[3].strip() if len(row) > 3 else ""

        if not name or response not in {"Yes", "No"}:
            continue

        record_date = parse_attendance_date(registration_value, event_value)
        if record_date is None:
            continue

        key = (name, record_date)
        status = status_by_name_date.setdefault(key, {"yes": False, "no": False})
        if response == "Yes":
            status["yes"] = True
        else:
            status["no"] = True

    counts_by_month = {}
    for (name, record_date), status in status_by_name_date.items():
        if status["yes"] and not status["no"]:
            month_key = record_date.strftime("%Y-%m")
            counts_by_month.setdefault(month_key, {})
            counts_by_month[month_key][name] = counts_by_month[month_key].get(name, 0) + 1

    return counts_by_month

def build_total_attendance(rows, year=None):
    status_by_name_date = {}
    for row in rows[1:]:
        name = row[0].strip() if len(row) > 0 else ""
        response = row[1].strip() if len(row) > 1 else ""
        registration_value = row[2].strip() if len(row) > 2 else ""
        event_value = row[3].strip() if len(row) > 3 else ""

        if not name or response not in {"Yes", "No"}:
            continue

        record_date = parse_attendance_date(registration_value, event_value)
        if record_date is None:
            continue
        if year is not None and record_date.year != year:
            continue

        key = (name, record_date)
        status = status_by_name_date.setdefault(key, {"yes": False, "no": False})
        if response == "Yes":
            status["yes"] = True
        else:
            status["no"] = True

    totals = {}
    for (name, _), status in status_by_name_date.items():
        if status["yes"] and not status["no"]:
            totals[name] = totals.get(name, 0) + 1

    return totals

# --- FŐOLDALI ŰRLAP FELDOLGOZÓJA ---
def process_main_form_submission():
    # ... (nincs változás, hagyd úgy, ahogy van) ...
    gsheet = get_gsheet_connection()
    if gsheet is None:
        st.error("Hiba: A Google Sheets kapcsolat nem él. Próbáld frissíteni az oldalt.")
        return

    try:
        name_val = st.session_state.name_select
        answer_val = st.session_state.answer_radio
        past_event_val = st.session_state.past_event_check
        past_date_val = st.session_state.get("past_date_select", "") 
        plus_count_val = st.session_state.plus_count if answer_val == "Yes" else "0"
        
        submission_timestamp = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
        
        rows_to_add = []
        main_row = [name_val, answer_val, submission_timestamp, past_date_val]
        rows_to_add.append(main_row)
        
        guests_added_count = 0
        if answer_val == "Yes":
            for i in range(int(plus_count_val)):
                extra_name_key = f"plus_name_txt_{i}"
                extra_name = st.session_state.get(extra_name_key, "").strip()
                
                if extra_name:
                    extra_row = [f"{name_val} - {extra_name}", "Yes", submission_timestamp, past_date_val]
                    rows_to_add.append(extra_row)
                    guests_added_count += 1
        
        success, message = save_data_to_gsheet(gsheet, rows_to_add)
        
        if success:
            success_msg = f"Köszönjük, {name_val}! A válaszod rögzítve."
            if guests_added_count > 0:
                success_msg += f" (Plusz {guests_added_count} fő vendég)"
            st.success(success_msg)
            
            # Űrlap alaphelyzetbe állítása
            st.session_state["name_select"] = MAIN_NAME_LIST[0]
            st.session_state["answer_radio"] = "Yes"
            st.session_state["past_event_check"] = False
            st.session_state["plus_count"] = "0"
            if "past_date_select" in st.session_state:
                tuesday_dates = generate_tuesday_dates()
                default_index = len(tuesday_dates) - 3 if len(tuesday_dates) >= 3 else 0
                st.session_state["past_date_select"] = tuesday_dates[default_index]
            for i in range(10):
                if f"plus_name_txt_{i}" in st.session_state:
                    st.session_state[f"plus_name_txt_{i}"] = ""
            
        else:
            st.error(f"Mentési hiba: {message}")

    except Exception as e:
        st.error(f"Váratlan hiba a feldolgozás során: {e}")


# --- ADMIN OLDALI FÜGGVÉNYEK ---

def reset_admin_form(set_step=1):
    """Alaphelyzetbe állítja az admin űrlapot."""
    st.session_state.admin_step = set_step
    
    # <<< JAVÍTÁS: A DÁTUMOT MÁR NEM BÁNTJUK! >>>
    
    st.session_state.admin_attendance = {name: {"present": False, "guests": "0"} for name in MAIN_NAME_LIST}
    st.session_state.admin_guest_data = {} 

def admin_save_guest_name(key):
    """Callback: Elmenti a beírt vendégnevet a 'admin_guest_data' tárolóba."""
    st.session_state.admin_guest_data[key] = st.session_state.get(key, "")

# <<< ÚJ CALLBACK: Csak a dátum mentésére >>>
def admin_save_date():
    """Callback: Elmenti a kiválasztott dátumot a 'admin_date'-be."""
    st.session_state.admin_date = st.session_state.admin_date_selector

def process_admin_submission(gsheet):
    """
    Az admin "Küldés" gombjának logikája.
    Most már a 'admin_guest_data'-ból olvas.
    """
    try:
        target_date_str = st.session_state.admin_date
        submission_timestamp = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
        rows_to_add = []
        
        for name, data in st.session_state.admin_attendance.items():
            if data["present"]:
                rows_to_add.append([name, "Yes", submission_timestamp, target_date_str])
                
                guest_count = int(data["guests"])
                if guest_count > 0:
                    for i in range(guest_count):
                        guest_name_key = f"admin_guest_{name}_{i}"
                        guest_name = st.session_state.admin_guest_data.get(guest_name_key, "").strip()
                        if guest_name:
                            rows_to_add.append([
                                f"{name} - {guest_name}", 
                                "Yes", 
                                submission_timestamp, 
                                target_date_str
                            ])
        
        if not rows_to_add:
            st.warning("Nincs senki kiválasztva, nincs mit menteni.")
            return

        success, message = save_data_to_gsheet(gsheet, rows_to_add)
        
        if success:
            st.success(f"{len(rows_to_add)} személy sikeresen regisztrálva a {target_date_str} napra!")
            reset_admin_form() # Alaphelyzetbe állítás (a dátumot már nem bántja)
        else:
            st.error(f"Mentési hiba: {message}")
            
    except Exception as e:
        st.error(f"Váratlan hiba az admin feldolgozás során: {e}")

# --- FŐOLDALI MEGJELENÍTŐ FÜGGVÉNY ---
def render_main_page(gsheet):
    # ... (nincs változás, hagyd úgy, ahogy van) ...
    st.title("🏐 Röpi Jelenléti Ív")
    counter_value = get_counter_value(gsheet)
    st.header(f"Következő alkalom létszáma: {counter_value} fő")
    st.markdown("---")

    st.selectbox("Válassz nevet:", MAIN_NAME_LIST, key="name_select")
    st.radio("Részt veszel az röpin?", ["Yes", "No"], horizontal=True, key="answer_radio")
    st.markdown("---")

    past_event_var = st.checkbox("Múltbeli alkalmat regisztrálok", key="past_event_check")
    if past_event_var:
        tuesday_dates = generate_tuesday_dates()
        default_index = len(tuesday_dates) - 3 if len(tuesday_dates) >= 3 else 0
        if 'past_date_select' not in st.session_state:
            st.session_state.past_date_select = tuesday_dates[default_index]
        st.selectbox("Alkalom dátuma:", tuesday_dates, key="past_date_select")

    if st.session_state.answer_radio == "Yes":
        st.selectbox("Hozol plusz embert?", PLUS_PEOPLE_COUNT, key="plus_count")
        
        plus_count_int = int(st.session_state.get("plus_count", 0))
        if plus_count_int > 0:
            st.markdown(f"**{plus_count_int} vendég neve:**")
            for i in range(plus_count_int):
                if f"plus_name_txt_{i}" not in st.session_state:
                     st.session_state[f"plus_name_txt_{i}"] = ""
                st.text_input(f"{i+1}. ember név:", key=f"plus_name_txt_{i}")

    st.button("Küldés", on_click=process_main_form_submission)

# --- ADMIN OLDALI MEGJELENÍTŐ FÜGGVÉNY ---
def render_admin_page(gsheet):
    st.title("Admin: Tömeges Regisztráció")
    
    # --- 1. LÉPÉS: JELENLÉT KIVÁLASZTÁSA ---
    if st.session_state.admin_step == 1:
        st.header("1. Lépés: Jelenlét és vendégek")
        
        # <<< JAVÍTÁS: A DÁTUMVÁLASZTÓ MÁR NEM 'key='-t HASZNÁL >>>
        tuesday_dates = generate_tuesday_dates()
        default_index = 0
        if st.session_state.admin_date in tuesday_dates:
            default_index = tuesday_dates.index(st.session_state.admin_date)
        
        # A 'key' itt 'admin_date_selector', és az 'on_change' frissíti
        # a valódi 'admin_date' állapotot.
        st.selectbox("Válassz dátumot a regisztrációhoz:", 
                     tuesday_dates, 
                     index=default_index,
                     key="admin_date_selector", # Ez egy "ideiglenes" kulcs
                     on_change=admin_save_date) # Callback, ami menti a választást
        
        st.markdown("---")
        
        st.write("Jelöld be, kik voltak ott és hány vendéget hoztak:")
        
        attendance_data = st.session_state.admin_attendance
        
        col1_head, col2_head, col3_head = st.columns([2, 1, 1])
        col1_head.write("**Név**")
        col2_head.write("**Ott volt?**")
        col3_head.write("**Vendégek**")
        
        for name in MAIN_NAME_LIST:
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.write(name)
            with col2:
                attendance_data[name]["present"] = st.checkbox("", value=attendance_data[name]["present"], key=f"admin_present_{name}", label_visibility="collapsed")
            with col3:
                attendance_data[name]["guests"] = st.selectbox("", PLUS_PEOPLE_COUNT, index=PLUS_PEOPLE_COUNT.index(attendance_data[name]["guests"]), key=f"admin_guests_{name}", label_visibility="collapsed")
        
        st.session_state.admin_attendance = attendance_data
        
        if st.button("Tovább a vendégnevekhez"):
            st.session_state.admin_step = 2
            st.rerun()

    # --- 2. LÉPÉS: VENDÉGNEVEK ---
    elif st.session_state.admin_step == 2:
        st.header("2. Lépés: Vendégnevek megadása")
        # <<< JAVÍTÁS: A dátumot a 'admin_date'-ből olvassuk, ami már nem íródik felül >>>
        st.info(f"Kiválasztott dátum: **{st.session_state.admin_date}**") 
        
        people_with_guests = []
        for name, data in st.session_state.admin_attendance.items():
            if data["present"] and int(data["guests"]) > 0:
                people_with_guests.append((name, int(data["guests"])))
        
        if not people_with_guests:
            st.info("Senki nem hozott vendéget. Nyomj a 'Tovább' gombra.")
        
        for name, guest_count in people_with_guests:
            st.subheader(name)
            for i in range(guest_count):
                guest_key = f"admin_guest_{name}_{i}"
                st.text_input(
                    f"{i+1}. vendég:", 
                    key=guest_key, 
                    on_change=admin_save_guest_name, 
                    args=(guest_key,) 
                )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Vissza a listához"):
                st.session_state.admin_step = 1
                st.rerun()
        with col2:
            if st.button("Tovább az összesítéshez"):
                st.session_state.admin_step = 3
                st.rerun()

    # --- 3. LÉPÉS: MEGERŐSÍTÉS ÉS KÜLDÉS ---
    elif st.session_state.admin_step == 3:
        st.header("3. Lépés: Összesítés és Küldés")
        # <<< JAVÍTÁS: A dátumot a 'admin_date'-ből olvassuk >>>
        st.info(f"Kiválasztott dátum: **{st.session_state.admin_date}**") 
        st.markdown("---")
        
        final_list_for_display = []
        
        for name, data in st.session_state.admin_attendance.items():
            if data["present"]:
                final_list_for_display.append(f"✅ **{name}**")
                
                guest_count = int(data["guests"])
                if guest_count > 0:
                    for i in range(guest_count):
                        guest_name_key = f"admin_guest_{name}_{i}"
                        guest_name = st.session_state.admin_guest_data.get(guest_name_key, "").strip()
                        if guest_name:
                            final_list_for_display.append(f"  ➡️ {guest_name} ({name} vendége)")
                        else:
                            final_list_for_display.append(f"  ⚠️ [ÜRES VENDÉG] ({name} vendége)")
        
        if not final_list_for_display:
            st.warning("Senki nincs kiválasztva. Menj vissza az 1. lépéshez.")
        else:
            st.write("A következő személyek lesznek regisztrálva:")
            st.markdown("\n".join(f"- {item}" for item in final_list_for_display))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Vissza (Vendégnevek)"):
                st.session_state.admin_step = 2
                st.rerun()
        with col2:
            st.button(
                "Küldés a Google Sheets-be", 
                type="primary", 
                disabled=(not final_list_for_display),
                on_click=process_admin_submission, 
                args=(gsheet,) 
            )

def render_stats_page(gsheet):
    st.title("Statisztika: Havi részvétel")
    rows = get_attendance_rows(gsheet)
    if not rows:
        st.info("Nincs elérhető adat az Attendance táblában.")
        return

    monthly_counts = build_monthly_stats(rows)
    if not monthly_counts:
        st.info("Nincs feldolgozható statisztikai adat.")
        return

    months = sorted(monthly_counts.keys(), reverse=True)
    selected_month = st.selectbox("Válassz hónapot:", months)
    month_data = monthly_counts.get(selected_month, {})

    if not month_data:
        st.info("Ebben a hónapban nincs rögzített jelenlét.")
        return

    stats_rows = [
        {"Név": name, "Alkalmak száma": count}
        for name, count in sorted(
            month_data.items(),
            key=lambda item: (-item[1], item[0])
        )
    ]
    st.dataframe(stats_rows, use_container_width=True)

def render_leaderboard_page(gsheet):
    st.title("Összesített jelenlét")
    rows = get_attendance_rows(gsheet)
    if not rows:
        st.info("Nincs elérhető adat az Attendance táblában.")
        return

    view_options = ["All time", "2024", "2025", "2026"]
    selected_view = st.selectbox("Válassz nézetet:", view_options)
    if selected_view == "All time":
        totals = build_total_attendance(rows)
        combined_totals = dict(LEGACY_ATTENDANCE_TOTALS)
    else:
        selected_year = int(selected_view)
        totals = build_total_attendance(rows, year=selected_year)
        combined_totals = dict(YEARLY_LEGACY_TOTALS.get(selected_year, {}))

    for name, count in totals.items():
        combined_totals[name] = combined_totals.get(name, 0) + count

    sorted_totals = sorted(
        combined_totals.items(),
        key=lambda item: (-item[1], item[0])
    )
    leaderboard_rows = [
        {"#": index, "Név": name, "Összes jelenlét": count}
        for index, (name, count) in enumerate(sorted_totals, start=1)
    ]

    st.dataframe(leaderboard_rows, use_container_width=True)

# --- FŐ ALKALMAZÁS INDÍTÁSA ---

# Alapértelmezett állapotok beállítása (egyszer, a legelején)
tuesday_dates = generate_tuesday_dates()
default_date = tuesday_dates[-3] if len(tuesday_dates) >= 3 else (tuesday_dates[0] if tuesday_dates else "Nincs dátum")

if 'admin_step' not in st.session_state:
    st.session_state.admin_step = 1
if 'admin_date' not in st.session_state:
    st.session_state.admin_date = default_date
if 'admin_attendance' not in st.session_state:
    st.session_state.admin_attendance = {name: {"present": False, "guests": "0"} for name in MAIN_NAME_LIST}
if 'admin_guest_data' not in st.session_state:
    st.session_state.admin_guest_data = {}
if 'plus_count' not in st.session_state: 
    st.session_state.plus_count = "0"
if 'past_event_check' not in st.session_state: 
    st.session_state.past_event_check = False
if 'answer_radio' not in st.session_state: 
    st.session_state.answer_radio = "Yes"
if 'name_select' not in st.session_state: 
    st.session_state.name_select = MAIN_NAME_LIST[0]


# --- Oldalválasztás ---
page = st.sidebar.radio(
    "Válassz oldalt:",
    ["Jelenléti Ív", "Admin Regisztráció", "Statisztika", "Leaderboard"],
    key="page_select"
)
gsheet = get_gsheet_connection()

if page == "Jelenléti Ív":
    render_main_page(gsheet)
elif page == "Admin Regisztráció":
    render_admin_page(gsheet)
elif page == "Statisztika":
    render_stats_page(gsheet)
elif page == "Leaderboard":
    render_leaderboard_page(gsheet)

