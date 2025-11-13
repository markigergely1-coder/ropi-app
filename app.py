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
    "András Papp", "Anna Sengler", "Annamária Földváry", "Flóra & Boti", 
    "Csanád Laczkó", "Csenge Domokos", "Detti Szabó", "Dóri Békási", 
    "Gergely Márki", "Kilyénfalvi Júlia", "Kristóf Szelényi", "Laura Piski", 
    "Léna Piski", "Linda Antal", "Máté Lajer", "Nóri Sásdi", "Laci Márki", 
    "Domokos Kadosa", "Áron Szabó", "Máté Plank", "Lea Plank"
]
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
    # Csak a jelenlétet és a vendégadatokat töröljük.
    
    st.session_state.admin_attendance = {name: {"present": False, "guests": "0"} for name in MAIN_NAME_LIST}
    st.session_state.admin_guest_data = {} # Töröljük a beírt vendégneveket

def admin_save_guest_name(key):
    """Callback: Elmenti a beírt vendégnevet a 'admin_guest_data' tárolóba."""
    st.session_state.admin_guest_data[key] = st.session_state.get(key, "")

def process_admin_submission(gsheet):
    """
    Az admin "Küldés" gombjának logikája.
    Most már a 'admin_guest_data'-ból olvas.
    """
    try:
        # A dátumot a state-ből olvassuk, ami már nem íródik felül
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
        
        # Dátumválasztó (A key="admin_date" elmenti a választást a session state-be)
        tuesday_dates = generate_tuesday_dates()
        # Az indexet a state-ből olvassuk
        default_index = 0
        if st.session_state.admin_date in tuesday_dates:
            default_index = tuesday_dates.index(st.session_state.admin_date)
        
        st.selectbox("Válassz dátumot a regisztrációhoz:", 
                     tuesday_dates, 
                     index=default_index,
                     key="admin_date") # Ez frissíti a 'st.session_state.admin_date'-et
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
        st.info(f"Kiválasztott dátum: **{st.session_state.admin_date}**") # Most már a helyes dátumot olvassa
        
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
                    on_change=admin_save_guest_name, # Callback hívás
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
        st.info(f"Kiválasztott dátum: **{st.session_state.admin_date}**") # Helyes dátum
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

# --- FŐ ALKALMAZÁS INDÍTÁSA ---

# <<< JAVÍTÁS: INICIALIZÁLÁS A KÓD ELEJÉRE >>>
# Ez a blokk most már a script legelején lefut, egyszer
tuesday_dates = generate_tuesday_dates()
default_date = tuesday_dates[-3] if len(tuesday_dates) >= 3 else (tuesday_dates[0] if tuesday_dates else "Nincs dátum")

# Alapértelmezett állapotok beállítása (ha még nem léteznek)
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
page = st.sidebar.radio("Válassz oldalt:", ["Jelenléti Ív", "Admin Regisztráció"], key="page_select")
gsheet = get_gsheet_connection()

if page == "Jelenléti Ív":
    render_main_page(gsheet)
elif page == "Admin Regisztráció":
    render_admin_page(gsheet)
