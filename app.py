import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import os
import json
import pytz 
import pandas as pd
import time

# --- 1. CONFIG & DESIGN ---
st.set_page_config(page_title="Röpi App Pro", layout="wide", page_icon="🏐")

def add_visual_styling():
    st.markdown(
        """
        <style>
        .stApp, p, h1, h2, h3, h4, label, div, span, input {
            color: #1E1E1E !important; 
        }
        .stApp {
            background-color: #f8f9fa;
        }
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #ddd;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }
        div.stButton > button {
            background-color: #2c3e50;
            color: white !important;
            border-radius: 8px;
            border: none;
            width: 100%;
        }
        div.stButton > button:hover {
            background-color: #34495e;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

# --- KONFIGURÁCIÓ ---
CREDENTIALS_FILE = 'credentials.json'
GSHEET_NAME = 'Attendance'
HUNGARY_TZ = pytz.timezone("Europe/Budapest")

MAIN_NAME_LIST = [
    "Anna Sengler", "Annamária Földváry", "Flóra", "Boti", 
    "Csanád Laczkó", "Csenge Domokos", "Detti Szabó", "Dóri Békási", 
    "Gergely Márki", "Márki Jancsi", "Kilyénfalvi Júlia", "Laura Piski", "Linda Antal", "Máté Lajer", "Nóri Sásdi", "Laci Márki", 
    "Domokos Kadosa", "Áron Szabó", "Máté Plank", "Lea Plank", "Océane Olivier"
]
MAIN_NAME_LIST.sort()

LEGACY_ATTENDANCE_TOTALS = {
    "András Papp": 7, "Anna Sengler": 25, "Annamária Földváry": 36,
    "Flóra & Boti": 19, "Csanád Laczkó": 41, "Csenge Domokos": 47,
    "Detti Szabó": 39, "Dóri Békási": 45, "Gergely Márki": 42,
    "Kilyénfalvi Júlia": 3, "Kristóf Szelényi": 5, "Laura Piski": 4,
    "Léna Piski": 1, "Linda Antal": 3, "Máté Lajer": 2,
    "Nóri Sásdi": 24, "Laci Márki": 39, "Domokos Kadosa": 30,
    "Áron Szabó": 24, "Máté Plank": 36, "Lea Plank": 15,
}

YEARLY_LEGACY_TOTALS = {
    2024: {
        "András Papp": 4, "Anna Sengler": 7, "Annamária Földváry": 6, "Flóra & Boti": 4,
        "Csanád Laczkó": 8, "Csenge Domokos": 7, "Detti Szabó": 5, "Dóri Békási": 6,
        "Gergely Márki": 8, "Kilyénfalvi Júlia": 6, "Kristóf Szelényi": 4, "Laura Piski": 6,
        "Léna Piski": 7, "Linda Antal": 5, "Máté Lajer": 6, "Nóri Sásdi": 0,
        "Laci Márki": 0, "Domokos Kadosa": 0, "Áron Szabó": 0, "Máté Plank": 7, "Lea Plank": 0,
    },
    2025: {
        "András Papp": 3, "Anna Sengler": 19, "Annamária Földváry": 31, "Flóra & Boti": 15,
        "Csanád Laczkó": 34, "Csenge Domokos": 41, "Detti Szabó": 35, "Dóri Békási": 39,
        "Gergely Márki": 35, "Kilyénfalvi Júlia": 7, "Kristóf Szelényi": 1, "Laura Piski": 6,
        "Léna Piski": 7, "Linda Antal": 1, "Máté Lajer": 1, "Nóri Sásdi": 19,
        "Laci Márki": 28, "Domokos Kadosa": 23, "Áron Szabó": 16, "Máté Plank": 33, "Lea Plank": 15,
    },
}

PLUS_PEOPLE_COUNT = [str(i) for i in range(11)]

# --- SESSION STATE INICIALIZÁLÁS ---
if 'session_submissions' not in st.session_state:
    st.session_state.session_submissions = []

# --- CSATLAKOZÁS ---

@st.cache_resource(ttl=3600)
def get_gsheet_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if hasattr(st, 'secrets'):
        if "gcp" in st.secrets and "json_content" in st.secrets["gcp"]:
            try:
                creds_dict = json.loads(st.secrets["gcp"]["json_content"])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                return gspread.authorize(creds)
            except Exception as e:
                st.error(f"Hiba a JSON Secrets feldolgozásakor: {e}")
        if "google_creds" in st.secrets:
            try:
                creds_dict = dict(st.secrets["google_creds"])
                if "private_key" in creds_dict:
                    pk = creds_dict["private_key"].strip().strip('"').strip("'")
                    if "\\n" in pk: pk = pk.replace("\\n", "\n")
                    creds_dict["private_key"] = pk
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                return gspread.authorize(creds)
            except Exception as e:
                st.error(f"Hiba a régi Secrets beolvasásakor: {e}")
    if os.path.exists(CREDENTIALS_FILE):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"Hiba a helyi fájl olvasásakor: {e}")
    return None

# --- SEGÉDFÜGGVÉNYEK ---

@st.cache_data(ttl=300)
def get_counter_value(_client):
    if _client is None: return "N/A"
    try:
        sheet = _client.open(GSHEET_NAME).sheet1
        return sheet.cell(2, 5).value 
    except: return "Hiba"

def generate_tuesday_dates(past_count=8, future_count=2):
    tuesday_dates_list = []
    today = datetime.now(HUNGARY_TZ).date()
    days_since_tuesday = (today.weekday() - 1) % 7 
    last_tuesday = today - timedelta(days=days_since_tuesday)
    for i in range(past_count):
        tuesday_dates_list.insert(0, (last_tuesday - timedelta(weeks=i)).strftime("%Y-%m-%d")) 
    for i in range(1, future_count + 1): 
        tuesday_dates_list.append((last_tuesday + timedelta(weeks=i)).strftime("%Y-%m-%d"))
    return tuesday_dates_list

def save_data_to_gsheet(client, rows_to_add, sheet_name="Attendance"):
    if client is None: return False, "Nincs kapcsolat."
    try:
        ss = client.open(GSHEET_NAME)
        if sheet_name == "Attendance":
            sheet = ss.sheet1
        else:
            try: sheet = ss.worksheet(sheet_name)
            except: sheet = ss.add_worksheet(title=sheet_name, rows=100, cols=20)
        
        sheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        
        # Friss adatok listájához hozzáadás
        for r in rows_to_add:
            st.session_state.session_submissions.insert(0, r)
            
        st.cache_data.clear() 
        return True, "Sikeres mentés."
    except Exception as e:
        return False, f"Hiba: {e}"

@st.cache_data(ttl=300)
def get_attendance_rows(_client):
    if _client is None: return []
    try: return _client.open(GSHEET_NAME).sheet1.get_all_values()
    except: return []

def get_historical_guests_list(rows, main_name):
    """Kikeresi a táblázatból a névhez tartozó korábbi vendégeket."""
    if not rows: return []
    prefix = f"{main_name} - "
    guests = set()
    for row in rows[1:]:
        if row and row[0].startswith(prefix):
            guest_part = row[0].replace(prefix, "", 1).strip()
            if guest_part:
                guests.add(guest_part)
    return sorted(list(guests))

def parse_attendance_date(registration_value, event_value):
    date_value = event_value or registration_value
    if not date_value: return None
    try: return datetime.strptime(date_value.split(" ")[0], "%Y-%m-%d").date()
    except: return None

def build_monthly_stats(rows):
    status_by_name_date = {}
    for row in rows[1:]:
        name = row[0].strip() if len(row) > 0 else ""
        response = row[1].strip() if len(row) > 1 else ""
        reg = row[2].strip() if len(row) > 2 else ""
        evt = row[3].strip() if len(row) > 3 else ""
        if not name or response not in {"Yes", "No"}: continue
        record_date = parse_attendance_date(reg, evt)
        if record_date is None: continue
        key = (name, record_date)
        status = status_by_name_date.setdefault(key, {"yes": False, "no": False})
        if response == "Yes": status["yes"] = True
        else: status["no"] = True
    counts = {}
    for (name, record_date), status in status_by_name_date.items():
        if status["yes"] and not status["no"]:
            m_key = record_date.strftime("%Y-%m")
            counts.setdefault(m_key, {})
            counts[m_key][name] = counts[m_key].get(name, 0) + 1
    return counts

def build_total_attendance(rows, year=None):
    status_by_name_date = {}
    for row in rows[1:]:
        name = row[0].strip() if len(row) > 0 else ""
        response = row[1].strip() if len(row) > 1 else ""
        reg = row[2].strip() if len(row) > 2 else ""
        evt = row[3].strip() if len(row) > 3 else ""
        if not name or response not in {"Yes", "No"}: continue
        record_date = parse_attendance_date(reg, evt)
        if record_date is None: continue
        if year is not None and record_date.year != year: continue
        key = (name, record_date)
        status = status_by_name_date.setdefault(key, {"yes": False, "no": False})
        if response == "Yes": status["yes"] = True
        else: status["no"] = True
    totals = {}
    for (name, _), status in status_by_name_date.items():
        if status["yes"] and not status["no"]: totals[name] = totals.get(name, 0) + 1
    return totals

# --- MEGJELENÍTÉS ---

def render_main_page(client):
    st.title("🏐 Röpi Jelenléti Ív")
    st.header(f"Következő alkalom létszáma: {get_counter_value(client)} fő")
    st.markdown("---")

    rows = get_attendance_rows(client)
    name = st.selectbox("Válassz nevet:", MAIN_NAME_LIST, key="name_select")
    answer = st.radio("Jössz edzésre?", ["Yes", "No"], horizontal=True, key="answer_radio")
    
    if st.checkbox("Múltbeli alkalmat regisztrálok", key="past_event_check"):
        dt = generate_tuesday_dates()
        if 'past_date_select' not in st.session_state: st.session_state.past_date_select = dt[0]
        st.selectbox("Dátum:", dt, key="past_date_select")

    if st.session_state.answer_radio == "Yes":
        st.selectbox("Vendégek száma:", PLUS_PEOPLE_COUNT, key="plus_count")
        
        num_guests = int(st.session_state.plus_count)
        if num_guests > 0:
            history = get_historical_guests_list(rows, name)
            options = ["-- Új név írása --"] + history
            
            for i in range(num_guests):
                sel = st.selectbox(f"{i+1}. vendég kiválasztása:", options, key=f"sel_plus_{i}")
                if sel == "-- Új név írása --":
                    st.text_input(f"Írd be a {i+1}. vendég nevét:", key=f"plus_name_txt_{i}")
                else:
                    # Session state-be mentjük a választást, hogy a küldés funkció lássa
                    st.session_state[f"plus_name_txt_{i}"] = sel

    if st.button("Küldés"):
        try:
            name_val = st.session_state.name_select
            answer_val = st.session_state.answer_radio
            past_date_val = st.session_state.get("past_date_select", "") 
            plus_count_val = st.session_state.plus_count if answer_val == "Yes" else "0"
            ts = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
            
            if not st.session_state.get("past_event_check", False):
                 dates = generate_tuesday_dates(past_count=0, future_count=1)
                 if dates: past_date_val = dates[0]

            rows_to_add = [[name_val, answer_val, ts, past_date_val]]
            if answer_val == "Yes":
                for i in range(int(plus_count_val)):
                    extra_name = st.session_state.get(f"plus_name_txt_{i}", "").strip()
                    if extra_name:
                        rows_to_add.append([f"{name_val} - {extra_name}", "Yes", ts, past_date_val])
            
            success, msg = save_data_to_gsheet(client, rows_to_add)
            if success:
                st.success(f"Köszönjük, {name_val}!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Hiba: {msg}")
        except Exception as e:
            st.error(f"Váratlan hiba: {e}")

def render_admin_page(client):
    st.title("Admin Regisztráció")
    rows = get_attendance_rows(client)
    
    if st.session_state.admin_step == 1:
        dt = generate_tuesday_dates()
        idx = dt.index(st.session_state.admin_date) if st.session_state.admin_date in dt else 0
        st.selectbox("Dátum:", dt, index=idx, key="admin_date_selector", on_change=admin_save_date)
        st.markdown("---")
        
        for name in MAIN_NAME_LIST:
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.write(name)
            st.session_state.admin_attendance[name]["present"] = c2.checkbox("", value=st.session_state.admin_attendance[name]["present"], key=f"p_{name}")
            st.session_state.admin_attendance[name]["guests"] = c3.selectbox("", PLUS_PEOPLE_COUNT, index=PLUS_PEOPLE_COUNT.index(st.session_state.admin_attendance[name]["guests"]), key=f"g_{name}")
        
        if st.button("Tovább"): 
            st.session_state.admin_step = 2
            st.rerun()

    elif st.session_state.admin_step == 2:
        st.info(f"Dátum: {st.session_state.admin_date}")
        pg = [(n, int(d["guests"])) for n, d in st.session_state.admin_attendance.items() if d["present"] and int(d["guests"]) > 0]
        if not pg: st.info("Nincs vendég.")
        
        for n, c in pg:
            st.subheader(f"**{n}** vendégei:")
            history = get_historical_guests_list(rows, n)
            options = ["-- Új név írása --"] + history
            
            for i in range(c):
                k_sel = f"admin_sel_{n}_{i}"
                k_txt = f"admin_guest_{n}_{i}"
                
                sel = st.selectbox(f"{i+1}. vendég kiválasztása ({n}):", options, key=k_sel)
                if sel == "-- Új név írása --":
                    st.text_input(f"{i+1}. vendég neve:", key=k_txt, on_change=admin_save_guest_name, args=(k_txt,))
                else:
                    st.session_state.admin_guest_data[k_txt] = sel
        
        c1, c2 = st.columns(2)
        if c1.button("Vissza"): st.session_state.admin_step = 1; st.rerun()
        if c2.button("Mentés"): 
            st.session_state.admin_step = 3; st.rerun()

    elif st.session_state.admin_step == 3:
        st.info(f"Dátum: {st.session_state.admin_date}")
        if st.button("Mentés a Google Sheets-be"): 
            process_admin_submission(client)
        if st.button("Vissza"): st.session_state.admin_step = 2; st.rerun()

def render_recent_submissions_page(df_all):
    st.title("📝 Friss Beküldések")
    st.subheader("🔹 Ebben a munkamenetben felvitt adatok")
    
    if st.session_state.session_submissions:
        sdf = pd.DataFrame(st.session_state.session_submissions, columns=["Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma"])
        st.table(sdf)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("Összes törlése"):
                st.session_state.session_submissions = []
                st.rerun()
        with col2:
            to_remove = st.multiselect("Csak bizonyos sorok törlése:", range(len(st.session_state.session_submissions)), 
                                        format_func=lambda i: f"{st.session_state.session_submissions[i][0]} ({st.session_state.session_submissions[i][3]})")
            if to_remove and st.button("Kijelöltek törlése"):
                st.session_state.session_submissions = [item for i, item in enumerate(st.session_state.session_submissions) if i not in to_remove]
                st.rerun()
    else:
        st.info("Még nem vittél fel adatot.")
    
    st.markdown("---")
    st.subheader("📂 Legutóbbi 20 sor a Google Sheet-ből")
    rows = get_attendance_rows(client)
    if rows:
        df = pd.DataFrame(rows[1:], columns=rows[0])
        st.dataframe(df.tail(20).iloc[::-1], use_container_width=True)

def render_stats_page(client):
    st.title("Statisztika")
    rows = get_attendance_rows(client)
    if rows:
        m = build_monthly_stats(rows)
        months = sorted(m.keys(), reverse=True)
        sel_month = st.selectbox("Hónap:", months)
        if sel_month:
            data = [{"Név": n, "Alkalom": c} for n, c in sorted(m[sel_month].items(), key=lambda x: (-x[1], x[0]))]
            st.dataframe(data, use_container_width=True)

def render_leaderboard_page(client):
    st.title("Ranglista")
    rows = get_attendance_rows(client)
    if rows:
        v = st.selectbox("Nézet:", ["All time", "2024", "2025"])
        totals = build_total_attendance(rows, int(v) if v != "All time" else None)
        legacy = dict(LEGACY_ATTENDANCE_TOTALS) if v == "All time" else dict(YEARLY_LEGACY_TOTALS.get(int(v), {}))
        for n, c in totals.items(): legacy[n] = legacy.get(n, 0) + c
        data = [{"#": i, "Név": n, "Összesen": c} for i, (n, c) in enumerate(sorted(legacy.items(), key=lambda x: (-x[1], x[0])), 1)]
        st.dataframe(data, use_container_width=True)

# --- ADMIN HELPER FUNCTIONS ---

def reset_admin_form(set_step=1):
    st.session_state.admin_step = set_step
    st.session_state.admin_attendance = {name: {"present": False, "guests": "0"} for name in MAIN_NAME_LIST}
    st.session_state.admin_guest_data = {} 

def admin_save_guest_name(key):
    st.session_state.admin_guest_data[key] = st.session_state.get(key, "")

def admin_save_date():
    st.session_state.admin_date = st.session_state.admin_date_selector

def process_admin_submission(client):
    try:
        target_date = st.session_state.admin_date
        ts = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
        rows_to_add = []
        for name, data in st.session_state.admin_attendance.items():
            if data["present"]:
                rows_to_add.append([name, "Yes", ts, target_date])
                guest_count = int(data["guests"])
                if guest_count > 0:
                    for i in range(guest_count):
                        g_name = st.session_state.admin_guest_data.get(f"admin_guest_{name}_{i}", "").strip()
                        if g_name: rows_to_add.append([f"{name} - {g_name}", "Yes", ts, target_date])
        success, msg = save_data_to_gsheet(client, rows_to_add)
        if success:
            st.success("Sikeres mentés!")
            reset_admin_form()
            time.sleep(1)
            st.rerun()
        else:
            st.error(msg)
    except Exception as e:
        st.error(f"Hiba: {e}")

# --- APP START ---

add_visual_styling()
tuesday_dates = generate_tuesday_dates()
default_date = tuesday_dates[0] if tuesday_dates else "Nincs dátum"

if 'admin_step' not in st.session_state: reset_admin_form()
if 'admin_date' not in st.session_state: st.session_state.admin_date = default_date
if 'past_event_check' not in st.session_state: st.session_state.past_event_check = False
if 'answer_radio' not in st.session_state: st.session_state.answer_radio = "Yes"
if 'name_select' not in st.session_state: st.session_state.name_select = MAIN_NAME_LIST[0]
if 'plus_count' not in st.session_state: st.session_state.plus_count = "0"

page = st.sidebar.radio("Menü", ["Jelenléti Ív", "Admin Regisztráció", "Friss Beküldések", "Statisztika", "Leaderboard"])
client = get_gsheet_connection()

if page == "Jelenléti Ív": render_main_page(client)
elif page == "Admin Regisztráció": render_admin_page(client)
elif page == "Friss Beküldések": render_recent_submissions_page(None)
elif page == "Statisztika": render_stats_page(client)
elif page == "Leaderboard": render_leaderboard_page(client)
