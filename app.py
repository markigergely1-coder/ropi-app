import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, timedelta
import os
import json
import pytz 
import pandas as pd
import time

# --- 1. CONFIG ---
st.set_page_config(page_title="Röpi App Pro", layout="wide", page_icon="🏐")

# --- KONFIGURÁCIÓ ---
CREDENTIALS_FILE = 'credentials.json'
GSHEET_NAME = 'Attendance'
HUNGARY_TZ = pytz.timezone("Europe/Budapest")
FIRESTORE_COLLECTION = "attendance_records"

MAIN_NAME_LIST = [
    "Anna Sengler", "Annamária Földváry", "Flóra", "Boti", 
    "Csanád Laczkó", "Csenge Domokos", "Detti Szabó", "Dóri Békási", 
    "Gergely Márki", "Márki Jancsi", "Kilyénfalvi Júlia", "Laura Piski", "Linda Antal", "Máté Lajer", "Nóri Sásdi", "Laci Márki", 
    "Domokos Kadosa", "Áron Szabó", "Máté Plank", "Lea Plank", "Océane Olivier"
]
MAIN_NAME_LIST.sort()

PLUS_PEOPLE_COUNT = [str(i) for i in range(11)]

# --- LEGACY ADATOK (Statisztikához) ---
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

# --- 2. ADATBÁZIS KAPCSOLATOK ---

@st.cache_resource(ttl=3600)
def get_gsheet_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if hasattr(st, 'secrets') and "google_creds" in st.secrets:
        try:
            creds_dict = dict(st.secrets["google_creds"])
            if "private_key" in creds_dict:
                pk = creds_dict["private_key"].strip().strip('"').strip("'")
                if "\\n" in pk: pk = pk.replace("\\n", "\n")
                creds_dict["private_key"] = pk
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except: pass
    if os.path.exists(CREDENTIALS_FILE):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
            return gspread.authorize(creds)
        except: pass
    return None

@st.cache_resource(ttl=3600)
def get_firestore_db():
    try:
        if hasattr(st, 'secrets') and "google_creds" in st.secrets:
            creds_dict = dict(st.secrets["google_creds"])
            if "private_key" in creds_dict:
                pk = creds_dict["private_key"].strip().strip('"').strip("'")
                if "\\n" in pk: pk = pk.replace("\\n", "\n")
                creds_dict["private_key"] = pk
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
        elif os.path.exists(CREDENTIALS_FILE):
            return firestore.Client.from_service_account_json(CREDENTIALS_FILE)
    except: return None
    return None

# --- 3. SEGÉDFÜGGVÉNYEK ---

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

def save_all_data(gs_client, fs_client, rows):
    success_gs = False
    
    # 1. Mentés Google Sheets-be (Kötelező)
    if gs_client:
        try:
            sheet = gs_client.open(GSHEET_NAME).sheet1
            sheet.append_rows(rows, value_input_option='USER_ENTERED')
            success_gs = True
        except Exception as e:
            return False, f"Hiba a Google Sheet mentésekor: {e}"

    # 2. Mentés Firestore-ba (Opcionális - ha működik, jó)
    if fs_client:
        try:
            for r in rows:
                doc_ref = fs_client.collection(FIRESTORE_COLLECTION).document()
                doc_ref.set({
                    "name": r[0],
                    "status": r[1],
                    "timestamp": r[2],
                    "event_date": r[3],
                    "mode": r[5] if len(r) > 5 else "ismeretlen"
                })
        except: 
            # Ha a Firestore hibára fut, nem omlik össze, megy tovább
            pass
            
    st.cache_data.clear()
    
    if success_gs:
        return True, "Sikeres mentés a Google Sheet-be!"
    else:
        return False, "Sikertelen mentés."

@st.cache_data(ttl=300)
def get_attendance_rows_gs(_client):
    if _client is None: return []
    try: return _client.open(GSHEET_NAME).sheet1.get_all_values()
    except: return []

def get_historical_guests_list(rows, main_name):
    if not rows: return []
    prefix = f"{main_name} - "
    guests = set()
    for row in rows[1:]:
        if row and row[0].startswith(prefix):
            guest_part = row[0].replace(prefix, "", 1).strip()
            if guest_part: guests.add(guest_part)
    return sorted(list(guests))

def parse_attendance_date(reg_val, evt_val):
    d = evt_val or reg_val
    if not d: return None
    try: return datetime.strptime(d.split(" ")[0], "%Y-%m-%d").date()
    except: return None

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

def render_landing_page():
    st.markdown("<h1 style='text-align: center; margin-bottom: 30px;'>🏐 Röpi App</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: gray; margin-bottom: 50px;'>Kérjük, válassz üzemmódot a belépéshez:</h3>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
    
    with col2:
        if st.button("🟢 Jelenlét felvitel\n\n(Valós adatok mentése)", use_container_width=True, type="primary"):
            st.session_state.app_mode = "valós"
            st.rerun()
            
    with col3:
        if st.button("🧪 Teszt\n\n(Kipróbálás)", use_container_width=True):
            st.session_state.app_mode = "teszt"
            st.rerun()

def render_admin_page(gs_client, fs_client):
    st.title("🛠️ Admin Regisztráció")
    
    # Kijelző a jelenlegi üzemmódról
    if st.session_state.app_mode == "teszt":
        st.warning("⚠️ Figyelem: Jelenleg TESZT üzemmódban vagy. Az adatok 'teszt' címkével kerülnek mentésre.")
    else:
        st.success("🟢 Jelenleg VALÓS Jelenlét felvitel üzemmódban vagy.")
        
    rows = get_attendance_rows_gs(gs_client)
    
    if st.session_state.admin_step == 1:
        dt = generate_tuesday_dates()
        idx = dt.index(st.session_state.admin_date) if st.session_state.admin_date in dt else 0
        st.selectbox("Dátum kiválasztása:", dt, index=idx, key="admin_date_selector", on_change=admin_save_date)
        st.markdown("---")
        
        # UX javítás: Bekeretezett sorok és függőleges igazítás
        for name in MAIN_NAME_LIST:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="center")
                c1.markdown(f"**{name}**")
                st.session_state.admin_attendance[name]["present"] = c2.checkbox("Jelen volt", value=st.session_state.admin_attendance[name]["present"], key=f"p_{name}")
                st.session_state.admin_attendance[name]["guests"] = c3.selectbox(
                    "Vendégek száma", 
                    PLUS_PEOPLE_COUNT, 
                    index=PLUS_PEOPLE_COUNT.index(st.session_state.admin_attendance[name]["guests"]), 
                    key=f"g_{name}", 
                    label_visibility="collapsed" # Eltüntetjük a feliratot, hogy pontosan középen maradjon
                )
        
        st.markdown("---")
        if st.button("Tovább a vendégnevekhez ➡️", type="primary"): 
            st.session_state.admin_step = 2
            st.rerun()

    elif st.session_state.admin_step == 2:
        pg = [(n, int(d["guests"])) for n, d in st.session_state.admin_attendance.items() if d["present"] and int(d["guests"]) > 0]
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
                        st.text_input(f"Vendég pontos neve:", key=f"admin_guest_{n}_{i}", on_change=admin_save_guest_name, args=(f"admin_guest_{n}_{i}",))
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
        
        if st.button("💾 Végleges Mentés", type="primary"):
            try:
                target_date = st.session_state.admin_date
                ts = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
                current_mode = st.session_state.app_mode
                
                rows_to_add = []
                for name, data in st.session_state.admin_attendance.items():
                    if data["present"]:
                        # 6 elemű tömb: [Név, Státusz, Regisztráció, Dátum, Üres (E oszlop miatt), Mód (F oszlopba)]
                        rows_to_add.append([name, "Yes", ts, target_date, "", current_mode])
                        for i in range(int(data["guests"])):
                            g_name = st.session_state.admin_guest_data.get(f"admin_guest_{name}_{i}", "").strip()
                            if g_name: 
                                rows_to_add.append([f"{name} - {g_name}", "Yes", ts, target_date, "", current_mode])
                                
                success, msg = save_all_data(gs_client, fs_client, rows_to_add)
                if success:
                    st.success(msg)
                    reset_admin_form()
                    time.sleep(2)
                    st.rerun()
                else: 
                    st.error(msg)
            except Exception as e: 
                st.error(f"Hiba: {e}")
                
        if st.button("⬅️ Vissza a szerkesztéshez"): 
            st.session_state.admin_step = 2
            st.rerun()

def render_database_page(client):
    st.title("🗂️ Adatbázis")
    
    # Két "fül" (Tab) létrehozása az oldalon belül
    tab1, tab2 = st.tabs(["📝 Beküldött Adatok", "🏆 Ranglista"])
    
    # 1. Tab: Beküldött adatok táblázata (Nyers adatok)
    with tab1:
        st.subheader("Google Sheet adatok megtekintése")
        rows = get_attendance_rows_gs(client)
        if rows:
            # Csak az első 6 oszlopot használjuk biztos ami biztos (Hogy látszódjon a Mód is)
            cols = rows[0][:6] 
            # Ha esetleg a fejléc rövidebb, kitöltjük üressel
            while len(cols) < 6:
                cols.append(f"Oszlop {len(cols)+1}")
                
            df_data = []
            for r in rows[1:]:
                # Kipótoljuk üressel, ha a sor rövidebb mint 6 elem
                padded_row = r[:6] + [""] * (6 - len(r[:6]))
                df_data.append(padded_row)
                
            df = pd.DataFrame(df_data, columns=cols)
            
            # Rendezési opciók
            col_sort, col_order = st.columns([2, 1])
            with col_sort:
                sort_col = st.selectbox("Rendezés alapja:", df.columns, index=2) # Alapból Regisztráció Időpontja
            with col_order:
                ascending = st.checkbox("Növekvő sorrend (legrégebbi felül)", value=False)
            
            # Táblázat rendezése
            df = df.sort_values(by=sort_col, ascending=ascending)
            
            # Táblázat kirajzolása
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("Nem sikerült betölteni a Google Sheets adatokat.")

    # 2. Tab: Ranglista
    with tab2:
        st.subheader("Részvételi Ranglista")
        rows = get_attendance_rows_gs(client)
        if rows:
            v = st.selectbox("Év kiválasztása:", ["All time", "2024", "2025"])
            totals = build_total_attendance(rows, int(v) if v != "All time" else None)
            
            # Alap adatok betöltése
            legacy = dict(LEGACY_ATTENDANCE_TOTALS) if v == "All time" else dict(YEARLY_LEGACY_TOTALS.get(int(v), {}))
            
            # Aktuális adatok hozzáadása
            for n, c in totals.items(): 
                legacy[n] = legacy.get(n, 0) + c
                
            # Formázás és rendezés
            data = [{"Helyezés": i, "Név": n, "Összes Részvétel": c} for i, (n, c) in enumerate(sorted(legacy.items(), key=lambda x: (-x[1], x[0])), 1)]
            
            st.dataframe(data, use_container_width=True)
        else:
            st.warning("Nem sikerült betölteni a Google Sheets adatokat a ranglistához.")

# --- ADMIN HELPER FUNCTIONS ---
def reset_admin_form(set_step=1):
    st.session_state.admin_step = set_step
    st.session_state.admin_attendance = {name: {"present": False, "guests": "0"} for name in MAIN_NAME_LIST}
    st.session_state.admin_guest_data = {} 

def admin_save_guest_name(key):
    st.session_state.admin_guest_data[key] = st.session_state.get(key, "")

def admin_save_date():
    st.session_state.admin_date = st.session_state.admin_date_selector

# --- APP START ---
gs_client = get_gsheet_connection()
fs_db = get_firestore_db()

# State inicializálás
if 'app_mode' not in st.session_state: st.session_state.app_mode = None
if 'admin_step' not in st.session_state: reset_admin_form()
if 'admin_date' not in st.session_state: st.session_state.admin_date = generate_tuesday_dates()[0]

# --- FŐ LOGIKA (KEZDŐKÉPERNYŐ VAGY APP) ---
if st.session_state.app_mode is None:
    # Ha nincs kiválasztva mód, mutatjuk a kezdőképernyőt
    render_landing_page()
else:
    # Ha már van mód, mutatjuk az applikációt és a menüt
    st.sidebar.markdown(f"**Üzemmód:** {'🟢 Valós' if st.session_state.app_mode == 'valós' else '🧪 Teszt'}")
    if st.sidebar.button("Kijelentkezés / Módváltás"):
        st.session_state.app_mode = None
        reset_admin_form()
        st.rerun()
        
    st.sidebar.markdown("---")
    page = st.sidebar.radio("Menü", ["Admin Regisztráció", "Adatbázis"])

    if page == "Admin Regisztráció": 
        render_admin_page(gs_client, fs_db)
    elif page == "Adatbázis": 
        render_database_page(gs_client)
