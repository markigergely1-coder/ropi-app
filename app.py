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
import calendar
from fpdf import FPDF

# --- 1. CONFIG ---
st.set_page_config(page_title="Röpi App Pro", layout="wide", page_icon="🏐")

# --- KONFIGURÁCIÓ ---
CREDENTIALS_FILE = 'credentials.json'
GSHEET_NAME = 'Attendance'
HUNGARY_TZ = pytz.timezone("Europe/Budapest")

# Firestore Gyűjtemények (Collections)
FIRESTORE_COLLECTION = "attendance_records"
FIRESTORE_INVOICES = "invoices"
FIRESTORE_CANCELLED = "cancelled_sessions"

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
            return firestore.Client(credentials=creds, project=creds_dict.get("project_id"))
        elif os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                creds_dict = json.load(f)
            return firestore.Client.from_service_account_json(CREDENTIALS_FILE, project=creds_dict.get("project_id"))
    except Exception as e: 
        st.error(f"Firestore indítási hiba: {e}")
        return None
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

def get_tuesdays_in_month(year, month):
    """Visszaadja a megadott hónap összes keddi napját (datetime.date objektumként)."""
    tuesdays = []
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        tuesday_day = week[calendar.TUESDAY]
        if tuesday_day != 0:
            tuesdays.append(datetime(year, month, tuesday_day).date())
    return tuesdays

def save_all_data(gs_client, fs_client, rows):
    success_gs = False
    success_fs = False
    error_msg_fs = ""
    
    if gs_client:
        try:
            sheet = gs_client.open(GSHEET_NAME).sheet1
            sheet.append_rows(rows, value_input_option='USER_ENTERED')
            success_gs = True
        except Exception as e:
            return False, f"Hiba a Google Sheet mentésekor: {e}"

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
            success_fs = True
        except Exception as e: 
            error_msg_fs = str(e)
    else:
        error_msg_fs = "Nincs aktív Firestore kapcsolat."
            
    st.cache_data.clear()
    
    if success_gs and success_fs: 
        return True, "Sikeres mentés a Google Sheet-be és a Firestore-ba is! ✅☁️"
    elif success_gs and not success_fs: 
        return True, f"Mentve a Sheet-be, de a Firestore HIBA miatt nem mentette a felhőbe: {error_msg_fs} ⚠️"
    else: 
        return False, "Kritikus hiba, egyik adatbázis sem érhető el."

@st.cache_data(ttl=300)
def get_attendance_rows_gs(_client):
    if _client is None: return []
    try: return _client.open(GSHEET_NAME).sheet1.get_all_values()
    except: return []

@st.cache_data(ttl=60)
def get_attendance_rows_fs(_db):
    if _db is None: return pd.DataFrame(columns=["ID", "Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Mód"])
    try:
        docs = _db.collection(FIRESTORE_COLLECTION).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            data.append([
                doc.id, 
                d.get("name"), 
                d.get("status"), 
                d.get("timestamp"), 
                d.get("event_date"), 
                d.get("mode", "ismeretlen")
            ])
        return pd.DataFrame(data, columns=["ID", "Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Mód"])
    except Exception as e: 
        st.error(f"Hiba a Firestore adatok betöltésekor: {e}")
        return pd.DataFrame(columns=["ID", "Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Mód"])

def get_historical_guests_list(rows, main_name):
    if not rows: return []
    prefix = f"{main_name} - "
    guests = set()
    for row in rows[1:]:
        if row and row[0].startswith(prefix):
            guest_part = row[0].replace(prefix, "", 1).strip()
            if guest_part: guests.add(guest_part)
    return sorted(list(guests))

def parse_hungarian_date(date_str):
    if not date_str or pd.isna(date_str): return None
    clean_str = str(date_str).strip()
    if clean_str.lower() in ['nan', 'none', '']: return None
    if clean_str.endswith('.'): clean_str = clean_str[:-1]
    clean_str = clean_str.replace('. ', '-').replace('.', '-')
    try: return datetime.strptime(clean_str.split(" ")[0], "%Y-%m-%d").date()
    except ValueError:
        try: return datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S").date()
        except: return None

def build_total_attendance(rows, year=None):
    status_by_name_date = {}
    for row in rows[1:]:
        name = row[0].strip() if len(row) > 0 else ""
        response = row[1].strip() if len(row) > 1 else ""
        reg = row[2].strip() if len(row) > 2 else ""
        evt = row[3].strip() if len(row) > 3 else ""
        if not name or response not in {"Yes", "No"}: continue
        record_date = parse_hungarian_date(evt) or parse_hungarian_date(reg)
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

# --- FIRESTORE ALAPÚ ELSZÁMOLÁSI LOGIKA ÉS FUNKCIÓK ---

@st.cache_data(ttl=60)
def get_cancelled_sessions_fs(_db):
    if _db is None: return set()
    try:
        docs = _db.collection(FIRESTORE_CANCELLED).stream()
        cancelled = set()
        for doc in docs:
            d = doc.to_dict()
            date_str = d.get("date")
            if date_str:
                date_obj = parse_hungarian_date(date_str)
                if date_obj: cancelled.add(date_obj)
        return cancelled
    except: return set()

@st.cache_data(ttl=60)
def get_invoices_fs(_db):
    if _db is None: return []
    try:
        docs = _db.collection(FIRESTORE_INVOICES).stream()
        invoices = []
        month_names = ["Január", "Február", "Március", "Április", "Május", "Június", "Július", "Augusztus", "Szeptember", "Október", "November", "December"]
        for doc in docs:
            d = doc.to_dict()
            d["ID"] = doc.id
            if "month_name" not in d and "target_month" in d:
                d["month_name"] = month_names[int(d["target_month"])-1]
            invoices.append(d)
        
        invoices.sort(key=lambda x: (int(x.get('target_year', 0)), int(x.get('target_month', 0))), reverse=True)
        return invoices
    except: return []

def calculate_monthly_accounting_fs(fs_db, inv_dict):
    target_year = int(inv_dict["target_year"])
    target_month = int(inv_dict["target_month"])
    target_month_name = inv_dict["month_name"]
    total_amount = float(inv_dict["amount"])

    all_tuesdays = get_tuesdays_in_month(target_year, target_month)
    cancelled_dates = get_cancelled_sessions_fs(fs_db)
    session_dates = [d for d in all_tuesdays if d not in cancelled_dates]

    if not session_dates:
        return False, f"Nincsenek érvényes edzésnapok rögzítve {target_year}. {target_month_name} hónapban (vagy mind elmaradt!).", None, None, None, None

    cost_per_session = total_amount / len(session_dates)

    df_fs = get_attendance_rows_fs(fs_db)
    processed_att = []
    
    if not df_fs.empty:
        for _, row in df_fs.iterrows():
            name = str(row["Név"]).strip() if pd.notna(row["Név"]) else ""
            is_coming = str(row["Jön-e"]).strip() if pd.notna(row["Jön-e"]) else ""
            
            if not name or not is_coming: continue
            
            reg_val = str(row["Regisztráció Időpontja"]) if pd.notna(row["Regisztráció Időpontja"]) else ""
            evt_val = str(row["Alkalom Dátuma"]) if pd.notna(row["Alkalom Dátuma"]) else ""
            
            mode_val = str(row["Mód"]).strip().lower() if pd.notna(row["Mód"]) else "valós"
            if mode_val == "teszt": continue

            rel_date = parse_hungarian_date(evt_val) or parse_hungarian_date(reg_val)
            if rel_date:
                processed_att.append({"name": name, "is_coming": is_coming, "date": rel_date})

    elszamolas_data = []
    person_totals = {}
    person_counts = {}

    for s_date in session_dates:
        yes_set = set()
        no_set = set()
        for rec in processed_att:
            if rec["date"] == s_date:
                if rec["is_coming"] == "Yes": yes_set.add(rec["name"])
                elif rec["is_coming"] == "No": no_set.add(rec["name"])

        final_attendees = yes_set - no_set
        attendee_count = len(final_attendees)
        cost_per_person = cost_per_session / attendee_count if attendee_count > 0 else 0

        elszamolas_data.append({
            "Dátum": s_date.strftime("%Y-%m-%d"),
            "Költség / alkalom": f"{cost_per_session:.0f} Ft",
            "Létszám": f"{attendee_count} fő",
            "Költség / Fő": f"{cost_per_person:.0f} Ft"
        })

        for att_name in final_attendees:
            person_totals[att_name] = person_totals.get(att_name, 0) + cost_per_person
            person_counts[att_name] = person_counts.get(att_name, 0) + 1

    osszesito_data = []
    for n in sorted(person_totals.keys()):
        osszesito_data.append({
            "Név": n,
            "Részvétel száma": person_counts[n],
            "Fizetendő (Ft)": person_totals[n]
        })

    df_elszamolas = pd.DataFrame(elszamolas_data)
    df_osszesito = pd.DataFrame(osszesito_data)

    return True, "Siker", df_elszamolas, df_osszesito, target_month_name, target_year

def generate_pdf_bytes(df_osszesito, month_name, year):
    pdf = FPDF()
    pdf.add_page()
    
    has_custom_font = False
    font_path = "Roboto-Regular.ttf"
    font_bold_path = "Roboto-Bold.ttf"
    
    if os.path.exists(font_path) and os.path.exists(font_bold_path):
        try:
            try:
                pdf.add_font("Roboto", "", font_path, uni=True)
                pdf.add_font("Roboto", "B", font_bold_path, uni=True)
            except TypeError:
                pdf.add_font("Roboto", "", font_path)
                pdf.add_font("Roboto", "B", font_bold_path)
            has_custom_font = True
        except Exception as e:
            print(f"Betűtípus betöltési hiba: {e}")
    
    def safe_txt(t):
        t_str = str(t)
        if has_custom_font:
            return t_str
        else:
            t_str = t_str.replace('ő', 'ö').replace('ű', 'ü').replace('Ő', 'Ö').replace('Ű', 'Ü')
            return t_str.encode('latin-1', 'replace').decode('latin-1')

    font_family = "Roboto" if has_custom_font else "Arial"

    pdf.set_font(font_family, "B", 16)
    pdf.cell(0, 10, txt=safe_txt(f"Havi Röplabda Elszámolás - {year}. {month_name}"), ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font(font_family, "B", 12)
    pdf.cell(90, 10, safe_txt("Név"), border=1)
    pdf.cell(40, 10, safe_txt("Részvétel száma"), border=1, align='C')
    pdf.cell(50, 10, safe_txt("Fizetendő"), border=1, align='R')
    pdf.ln()
    
    pdf.set_font(font_family, "", 12)
    for _, row in df_osszesito.iterrows():
        pdf.cell(90, 10, safe_txt(row['Név']), border=1)
        pdf.cell(40, 10, str(row['Részvétel száma']), border=1, align='C')
        pdf.cell(50, 10, safe_txt(f"{row['Fizetendő (Ft)']:.0f} Ft"), border=1, align='R')
        pdf.ln()
        
    try:
        return pdf.output(dest='S').encode('latin-1')
    except TypeError:
        return pdf.output()
    except AttributeError:
        return bytes(pdf.output())

# --- MEGJELENÍTÉS (UI) ---

def render_admin_page(gs_client, fs_client):
    st.title("🛠️ Admin Regisztráció")
    
    st.success("🟢 Aktív: Jelenlét rögzítése üzemmód.")
        
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
                st.session_state.admin_attendance[name]["present"] = c2.checkbox("Jelen volt", value=st.session_state.admin_attendance[name]["present"], key=f"p_{name}")
                st.session_state.admin_attendance[name]["guests"] = c3.selectbox(
                    "Vendégek száma", PLUS_PEOPLE_COUNT, 
                    index=PLUS_PEOPLE_COUNT.index(st.session_state.admin_attendance[name]["guests"]), 
                    key=f"g_{name}", label_visibility="collapsed"
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
                current_mode = "valós" # Mindig valós módként mentünk
                
                rows_to_add = []
                for name, data in st.session_state.admin_attendance.items():
                    if data["present"]:
                        rows_to_add.append([name, "Yes", ts, target_date, "", current_mode])
                        for i in range(int(data["guests"])):
                            g_name = st.session_state.admin_guest_data.get(f"admin_guest_{name}_{i}", "").strip()
                            if g_name: 
                                rows_to_add.append([f"{name} - {g_name}", "Yes", ts, target_date, "", current_mode])
                                
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

def render_attendance_overview_page(fs_db):
    st.title("📅 Alkalmak Áttekintése")
    st.markdown("Itt ellenőrizheted a résztvevők számát és névsorát az elmúlt 8 alkalomra visszamenőleg. *(Az adatok a Firestore felhőből származnak)*")

    dates = generate_tuesday_dates(past_count=8, future_count=0)
    selected_date_str = st.selectbox("Válassz egy dátumot az áttekintéshez:", dates)

    if selected_date_str:
        selected_date = parse_hungarian_date(selected_date_str)
        
        with st.spinner("Adatok betöltése a Firestore-ból..."):
            df_fs = get_attendance_rows_fs(fs_db)
        
        if df_fs.empty:
            st.warning("Nem sikerült betölteni a Firestore adatokat.")
            return

        yes_set = set()
        no_set = set()

        for _, row in df_fs.iterrows():
            name = str(row["Név"]).strip() if pd.notna(row["Név"]) else ""
            is_coming = str(row["Jön-e"]).strip() if pd.notna(row["Jön-e"]) else ""
            
            if not name: continue
            
            reg_val = str(row["Regisztráció Időpontja"]) if pd.notna(row["Regisztráció Időpontja"]) else ""
            evt_val = str(row["Alkalom Dátuma"]) if pd.notna(row["Alkalom Dátuma"]) else ""
            
            mode_val = str(row["Mód"]).strip().lower() if pd.notna(row["Mód"]) else "valós"
            if mode_val == "teszt": continue

            rel_date = parse_hungarian_date(evt_val) or parse_hungarian_date(reg_val)
            
            if rel_date == selected_date:
                if is_coming == "Yes": yes_set.add(name)
                elif is_coming == "No": no_set.add(name)

        final_attendees = sorted(list(yes_set - no_set))
        count = len(final_attendees)
        
        st.markdown("---")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric(label="Résztvevők száma", value=f"{count} fő")
            
        with col2:
            if count > 0:
                st.subheader("Résztvevők névsora:")
                name_cols = st.columns(2)
                for i, name in enumerate(final_attendees):
                    name_cols[i % 2].markdown(f"✅ **{name}**")
            else:
                st.info("Erre az alkalomra nincs érvényes regisztráció.")

def render_database_page(gs_client, fs_db):
    st.title("🗂️ Adatbázis")
    
    tab1, tab2, tab3 = st.tabs(["📝 Beküldött Adatok (Sheet)", "☁️ Felhő Adatok (Firestore)", "🏆 Ranglista"])
    
    with tab1:
        st.subheader("Google Sheet adatok megtekintése")
        rows = get_attendance_rows_gs(gs_client)
        if rows:
            cols = rows[0][:6] 
            while len(cols) < 6:
                cols.append(f"Oszlop {len(cols)+1}")
                
            df_data = []
            for r in rows[1:]:
                padded_row = r[:6] + [""] * (6 - len(r[:6]))
                df_data.append(padded_row)
                
            df = pd.DataFrame(df_data, columns=cols)
            
            col_sort, col_order = st.columns([2, 1])
            with col_sort:
                sort_col = st.selectbox("Rendezés alapja:", df.columns, index=2, key="sort1")
            with col_order:
                ascending = st.checkbox("Növekvő sorrend (legrégebbi felül)", value=False, key="asc1")
            
            df = df.sort_values(by=sort_col, ascending=ascending)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("Nem sikerült betölteni a Google Sheets adatokat.")

    with tab2:
        st.subheader("Firestore Adatbázis megtekintése és szerkesztése")
        st.markdown("Ide kerültek lementésre a felhő alapú működéshez szükséges adatok.")
        
        # --- SZINKRONIZÁCIÓS SZEKCIÓ ---
        st.markdown("---")
        with st.expander("🔄 Adatok Szinkronizálása (Sheet ↔ Firestore)"):
            st.warning("⚠️ Figyelem: A szinkronizálás felülírja a cél-adatbázist a forrás-adatbázis tartalmával!")
            
            sync_source = st.radio("Melyik legyen a FORRÁS (alap) adatbázis?", ["Google Sheets", "Firestore"], horizontal=True)
            sync_target = "Firestore" if sync_source == "Google Sheets" else "Google Sheets"
            
            st.info(f"👉 Irány: **{sync_source}** ➡️ **{sync_target}** (A cél adatai törlődnek és lecserélődnek!)")
            
            col_m1, col_m2 = st.columns(2)
            
            with col_m1:
                if st.button(f"👥 Jelenlét szinkronizálása", type="primary", use_container_width=True):
                    with st.spinner("Jelenlét szinkronizálása..."):
                        if sync_source == "Google Sheets":
                            # Sheets -> Firestore
                            gs_rows = get_attendance_rows_gs(gs_client)
                            if len(gs_rows) > 1:
                                docs = fs_db.collection(FIRESTORE_COLLECTION).stream()
                                for doc in docs:
                                    doc.reference.delete()
                                
                                success_count = 0
                                for r in gs_rows[1:]:
                                    try:
                                        name = r[0] if len(r) > 0 else ""
                                        if not name: continue
                                        fs_db.collection(FIRESTORE_COLLECTION).add({
                                            "name": name,
                                            "status": r[1] if len(r) > 1 else "Yes",
                                            "timestamp": r[2] if len(r) > 2 else "",
                                            "event_date": r[3] if len(r) > 3 else "",
                                            "mode": "valós"
                                        })
                                        success_count += 1
                                    except Exception: pass
                                st.success(f"Kész! {success_count} jelenléti adat átmásolva a Firestore-ba.")
                            else:
                                st.info("Nincs másolható jelenléti adat a Sheet-ben.")
                        
                        else:
                            # Firestore -> Sheets
                            df_fs = get_attendance_rows_fs(fs_db)
                            if not df_fs.empty:
                                try:
                                    sheet = gs_client.open(GSHEET_NAME).sheet1
                                    sheet.clear()
                                    
                                    new_rows = [["Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Üres", "Mód"]]
                                    for _, row in df_fs.iterrows():
                                        new_rows.append([
                                            row["Név"], row["Jön-e"], row["Regisztráció Időpontja"], 
                                            row["Alkalom Dátuma"], "", "valós"
                                        ])
                                    
                                    sheet.append_rows(new_rows, value_input_option='USER_ENTERED')
                                    st.success(f"Kész! {len(new_rows)-1} jelenléti adat átmásolva a Sheet-be.")
                                except Exception as e:
                                    st.error(f"Hiba a Google Sheet írásakor: {e}")
                            else:
                                st.info("Nincs adat a Firestore-ban.")
                        
                        st.cache_data.clear()
                        time.sleep(2)
                        st.rerun()

            with col_m2:
                if st.button(f"🧾 Számlák szinkronizálása", type="primary", use_container_width=True):
                    with st.spinner("Számlák szinkronizálása..."):
                        try:
                            ss = gs_client.open(GSHEET_NAME)
                            szamlak_sheet = ss.worksheet("Szamlak") if "Szamlak" in [w.title for w in ss.worksheets()] else ss.worksheet("szamlak")
                            
                            if sync_source == "Google Sheets":
                                # Sheets -> Firestore
                                rows = szamlak_sheet.get_all_values()
                                if len(rows) > 1:
                                    docs = fs_db.collection(FIRESTORE_INVOICES).stream()
                                    for doc in docs:
                                        doc.reference.delete()
                                        
                                    success_count = 0
                                    for r in rows[1:]:
                                        if not r[0]: continue
                                        inv_date = parse_hungarian_date(r[0])
                                        if not inv_date: continue
                                        
                                        try: amount = float(str(r[1]).replace(' ', '').replace('Ft', '').replace('HUF', '').replace('\xa0', ''))
                                        except: continue
                                        
                                        t_month = 12 if inv_date.month == 1 else inv_date.month - 1
                                        t_year = inv_date.year - 1 if inv_date.month == 1 else inv_date.year
                                            
                                        fs_db.collection(FIRESTORE_INVOICES).add({
                                            "inv_date": inv_date.strftime("%Y-%m-%d"),
                                            "target_year": t_year,
                                            "target_month": t_month,
                                            "amount": amount,
                                            "filename": r[2] if len(r) > 2 else ""
                                        })
                                        success_count += 1
                                    st.success(f"Kész! {success_count} számla átmásolva a Firestore-ba.")
                                else:
                                    st.info("Nincs számla a Sheet-ben.")
                            
                            else:
                                # Firestore -> Sheets
                                invoices = get_invoices_fs(fs_db)
                                if invoices:
                                    szamlak_sheet.clear()
                                    new_rows = [["Dátum", "Összeg", "Fájlnév"]]
                                    for inv in invoices:
                                        new_rows.append([
                                            inv["inv_date"], 
                                            f"{int(inv['amount'])} Ft", 
                                            inv.get("filename", "")
                                        ])
                                    szamlak_sheet.append_rows(new_rows, value_input_option='USER_ENTERED')
                                    st.success(f"Kész! {len(invoices)} számla átmásolva a Sheet-be.")
                                else:
                                    st.info("Nincs számla a Firestore-ban.")
                                    
                            st.cache_data.clear()
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Hiba a szinkronizálás közben: {e}")

        st.markdown("---")
        
        view_selection = st.radio("Mit szeretnél megtekinteni/szerkeszteni?", ["👥 Jelenléti adatok", "🧾 Számlák"], horizontal=True)
        st.markdown("---")
        
        if view_selection == "👥 Jelenléti adatok":
            df_fs = get_attendance_rows_fs(fs_db)
            
            if not df_fs.empty:
                edit_mode = st.toggle("✏️ Szerkesztés mód bekapcsolása")
                
                col_sort_fs, col_order_fs = st.columns([2, 1])
                with col_sort_fs:
                    sortable_cols = [c for c in df_fs.columns if c != "ID"]
                    sort_col_fs = st.selectbox("Rendezés alapja:", sortable_cols, index=2, key="sort2")
                with col_order_fs:
                    ascending_fs = st.checkbox("Növekvő sorrend (legrégebbi felül)", value=False, key="asc2")
                    
                df_fs = df_fs.sort_values(by=sort_col_fs, ascending=ascending_fs).reset_index(drop=True)
                
                if edit_mode:
                    st.info("💡 **Tipp:** Kattints duplán a cellákra a szerkesztéshez! Egy sor törléséhez jelöld ki a sort bal oldalt és nyomj a billentyűzeten **Delete** gombot.")
                    
                    edited_df = st.data_editor(
                        df_fs, 
                        key="fs_editor", 
                        num_rows="dynamic",
                        column_config={"ID": None},
                        use_container_width=True
                    )
                    
                    if st.button("💾 Változtatások mentése a felhőbe", type="primary"):
                        changes = st.session_state["fs_editor"]
                        if changes.get("edited_rows") or changes.get("added_rows") or changes.get("deleted_rows"):
                            try:
                                for row_idx in changes.get("deleted_rows", []):
                                    doc_id = df_fs.iloc[row_idx]["ID"]
                                    fs_db.collection(FIRESTORE_COLLECTION).document(doc_id).delete()
                                
                                col_map = {"Név": "name", "Jön-e": "status", "Regisztráció Időpontja": "timestamp", "Alkalom Dátuma": "event_date", "Mód": "mode"}
                                for row_idx, edits in changes.get("edited_rows", {}).items():
                                    doc_id = df_fs.iloc[row_idx]["ID"]
                                    update_data = {col_map[k]: v for k, v in edits.items() if k in col_map}
                                    if update_data:
                                        fs_db.collection(FIRESTORE_COLLECTION).document(doc_id).update(update_data)
                                        
                                for new_row in changes.get("added_rows", []):
                                    add_data = {
                                        "name": new_row.get("Név", ""),
                                        "status": new_row.get("Jön-e", "Yes"),
                                        "timestamp": new_row.get("Regisztráció Időpontja", datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")),
                                        "event_date": new_row.get("Alkalom Dátuma", ""),
                                        "mode": new_row.get("Mód", "valós")
                                    }
                                    fs_db.collection(FIRESTORE_COLLECTION).add(add_data)
                                    
                                st.success("Sikeresen frissítetted a felhő adatbázist! ✅")
                                st.cache_data.clear()
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Hiba történt a mentés során: {e}")
                        else:
                            st.info("Nem történt változtatás a táblázatban.")
                else:
                    st.dataframe(df_fs.drop(columns=["ID"]), use_container_width=True)
            else:
                st.info("Még nincsenek adatok a Firestore adatbázisban, vagy a csatlakozás sikertelen volt.")

        elif view_selection == "🧾 Számlák":
            invoices = get_invoices_fs(fs_db)
            if invoices:
                df_inv = pd.DataFrame(invoices)
                edit_mode_inv = st.toggle("✏️ Számlák szerkesztésének bekapcsolása", key="toggle_inv")
                
                col_sort_inv, col_order_inv = st.columns([2, 1])
                with col_sort_inv:
                    sortable_cols_inv = [c for c in df_inv.columns if c != "ID"]
                    sort_col_inv = st.selectbox("Rendezés alapja:", sortable_cols_inv, index=0, key="sort3")
                with col_order_inv:
                    ascending_inv = st.checkbox("Növekvő sorrend (legrégebbi felül)", value=False, key="asc3")
                    
                df_inv = df_inv.sort_values(by=sort_col_inv, ascending=ascending_inv).reset_index(drop=True)
                
                if edit_mode_inv:
                    st.info("💡 **Tipp:** Kattints duplán a cellákra a szerkesztéshez! Egy sor törléséhez jelöld ki a sort bal oldalt és nyomj a billentyűzeten **Delete** gombot.")
                    
                    edited_df_inv = st.data_editor(
                        df_inv, 
                        key="inv_editor", 
                        num_rows="dynamic",
                        column_config={"ID": None},
                        use_container_width=True
                    )
                    
                    if st.button("💾 Számlák mentése a felhőbe", type="primary", key="save_inv_btn"):
                        changes = st.session_state["inv_editor"]
                        if changes.get("edited_rows") or changes.get("added_rows") or changes.get("deleted_rows"):
                            try:
                                for row_idx in changes.get("deleted_rows", []):
                                    doc_id = df_inv.iloc[row_idx]["ID"]
                                    fs_db.collection(FIRESTORE_INVOICES).document(doc_id).delete()
                                
                                for row_idx, edits in changes.get("edited_rows", {}).items():
                                    doc_id = df_inv.iloc[row_idx]["ID"]
                                    if edits:
                                        fs_db.collection(FIRESTORE_INVOICES).document(doc_id).update(edits)
                                        
                                for new_row in changes.get("added_rows", []):
                                    add_data = {k: v for k, v in new_row.items() if k != "ID"}
                                    if add_data:
                                        fs_db.collection(FIRESTORE_INVOICES).add(add_data)
                                    
                                st.success("Sikeresen frissítetted a számlákat a felhőben! ✅")
                                st.cache_data.clear()
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Hiba történt a mentés során: {e}")
                        else:
                            st.info("Nem történt változtatás a táblázatban.")
                else:
                    st.dataframe(df_inv.drop(columns=["ID"]), use_container_width=True)
            else:
                st.info("Még nincsenek számlák a Firestore adatbázisban.")

    with tab3:
        st.subheader("Részvételi Ranglista")
        rows = get_attendance_rows_gs(gs_client)
        if rows:
            v = st.selectbox("Év kiválasztása:", ["All time", "2024", "2025"])
            totals = build_total_attendance(rows, int(v) if v != "All time" else None)
            
            legacy = dict(LEGACY_ATTENDANCE_TOTALS) if v == "All time" else dict(YEARLY_LEGACY_TOTALS.get(int(v), {}))
            for n, c in totals.items(): 
                legacy[n] = legacy.get(n, 0) + c
                
            data = [{"Helyezés": i, "Név": n, "Összes Részvétel": c} for i, (n, c) in enumerate(sorted(legacy.items(), key=lambda x: (-x[1], x[0])), 1)]
            st.dataframe(data, use_container_width=True)
        else:
            st.warning("Nem sikerült betölteni a Google Sheets adatokat a ranglistához.")

def render_settings_page(fs_db):
    st.title("⚙️ Beállítások (Kivételek)")
    st.markdown("Itt adhatod meg azokat a keddi napokat, amikor **ELMARADT** az edzés (pl. teremzárás, ünnepnap). Az elszámoló logika ezeket a napokat automatikusan kivonja az adott havi költségosztásból.")

    if fs_db is None:
        st.error("Nincs Firestore kapcsolat.")
        return

    # Új elmaradt nap hozzáadása
    with st.container(border=True):
        st.subheader("Új kivétel rögzítése")
        col1, col2 = st.columns([2, 1], vertical_alignment="bottom")
        with col1:
            new_date = st.date_input("Válaszd ki az elmaradt edzés dátumát:")
        with col2:
            if st.button("➕ Hozzáadás", type="primary", use_container_width=True):
                # Keddi nap ellenőrzése
                if new_date.weekday() != calendar.TUESDAY:
                    st.warning("⚠️ Biztos vagy benne? Ez a nap nem Keddre esik!")
                
                date_str = new_date.strftime("%Y-%m-%d")
                existing = get_cancelled_sessions_fs(fs_db)
                if new_date in existing:
                    st.warning("Ez a dátum már szerepel a kivételek között!")
                else:
                    try:
                        fs_db.collection(FIRESTORE_CANCELLED).add({"date": date_str})
                        st.success("Sikeresen rögzítve!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hiba mentéskor: {e}")

    # Lista megjelenítése
    st.markdown("---")
    st.subheader("Jelenleg rögzített elmaradt edzések")
    try:
        docs = fs_db.collection(FIRESTORE_CANCELLED).order_by("date", direction=firestore.Query.DESCENDING).stream()
        cancelled_list = [{"ID": doc.id, "Dátum": doc.to_dict().get("date")} for doc in docs]

        if cancelled_list:
            for item in cancelled_list:
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1], vertical_alignment="center")
                    c1.markdown(f"🗓️ **{item['Dátum']}**")
                    if c2.button("❌ Törlés", key=f"del_{item['ID']}", use_container_width=True):
                        fs_db.collection(FIRESTORE_CANCELLED).document(item['ID']).delete()
                        st.cache_data.clear()
                        st.rerun()
        else:
            st.info("Jelenleg nincsenek elmaradt edzések rögzítve az adatbázisban.")
    except Exception as e:
        st.error(f"Hiba a lista betöltésekor: {e}")

def render_accounting_page(fs_db):
    st.title("💰 Havi Elszámolás")
    st.markdown("Ezzel a funkcióval kiszámolhatod a teremköltségek személyenkénti elosztását a valós jelenléti adatok alapján. *(A logika most már teljesen a Firestore felhőre támaszkodik, és automatikusan számolja a naptári keddeket!)*")
    
    invoices = get_invoices_fs(fs_db)
    
    if not invoices:
        st.warning("⚠️ Nem találtam számlát a Firestore-ban! Kérlek, menj az 'Adatbázis' fülre, nyisd le a 'Szinkronizáció' részt, és másold át a számlákat a Sheet-ből!")
        return
        
    selected_inv = st.selectbox(
        "Válaszd ki az elszámolandó hónapot (a rögzített számlák alapján):", 
        invoices, 
        format_func=lambda x: f"{x['target_year']}. {x['month_name']} (Számla kelte: {x['inv_date']} | Összeg: {x['amount']:,.0f} Ft)".replace(',', ' ')
    )
    
    if st.button("Elszámolás Kalkulálása 🚀", type="primary"):
        with st.spinner(f"Adatok beolvasása és {selected_inv['target_year']}. {selected_inv['month_name']} havi elszámolás számítása..."):
            success, msg, df_elszamolas, df_osszesito, month_name, year = calculate_monthly_accounting_fs(fs_db, selected_inv)
            
        if success:
            st.success(f"✅ Kalkuláció sikeres: {year}. {month_name}")
            
            pdf_bytes = generate_pdf_bytes(df_osszesito, month_name, year)
            st.download_button(
                label="📥 Elszámolás Letöltése (PDF)",
                data=pdf_bytes,
                file_name=f"Havi_Elszamolas_{year}_{month_name}.pdf",
                mime="application/pdf",
                type="primary"
            )
            
            # --- MESSENGER ÜZENET GENERÁLÁS ---
            st.markdown("---")
            st.subheader("💬 Üzenet a Messenger csoportba")
            st.markdown("A jobb felső sarokban lévő kis ikonra kattintva egyből a vágólapra másolhatod a szöveget!")
            
            msg_text = f"Sziasztok! 🏐\n\nElkészült a {year}. {month_name} havi röpi elszámolás! A terembérlet és a részvétel alapján a pontos bontást a csatolt PDF-ben találjátok.\n\nKérlek, nézzétek meg és utaljátok a rátok eső összeget a szokásos számlaszámra! Köszi! 🙌"
            
            st.code(msg_text, language="text")
            # ----------------------------------
            
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Bontás Alkalmanként")
                st.dataframe(df_elszamolas, use_container_width=True)
            with col2:
                st.subheader("Személyenkénti Összesítő")
                df_display = df_osszesito.copy()
                df_display['Fizetendő (Ft)'] = df_display['Fizetendő (Ft)'].apply(lambda x: f"{x:.0f} Ft")
                st.dataframe(df_display, use_container_width=True)
        else:
            st.error(msg)

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

# State inicializálás (Teszt mód kiszedve, mindig valós)
if 'admin_step' not in st.session_state: reset_admin_form()
if 'admin_date' not in st.session_state: st.session_state.admin_date = generate_tuesday_dates()[0]

# --- FŐ LOGIKA (APP) ---
st.sidebar.markdown("---")
page = st.sidebar.radio("Menü", ["Admin Regisztráció", "Alkalmak Áttekintése", "Adatbázis", "Havi Elszámolás", "Beállítások (Kivételek)"])

if page == "Admin Regisztráció": 
    render_admin_page(gs_client, fs_db)
elif page == "Alkalmak Áttekintése":
    render_attendance_overview_page(fs_db)
elif page == "Adatbázis": 
    render_database_page(gs_client, fs_db)
elif page == "Havi Elszámolás":
    render_accounting_page(fs_db) 
elif page == "Beállítások (Kivételek)":
    render_settings_page(fs_db)
