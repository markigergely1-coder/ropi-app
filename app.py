import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import os
import json

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

# --- HÁTTÉRLOGIKA (GSPREAD ÉS DÁTUMOK) ---

@st.cache_resource(ttl=3600) # 1 óráig gyorsítótárazza a kapcsolatot
def get_gsheet_connection():
    """Csatlakozik a Google Sheets-hez és visszaadja a munkalapot."""
    print("GSpread: Új kapcsolat létrehozása...")
    
    # Titkos kulcsok kezelése (Streamlit Cloud-hoz)
    # Próbálja meg a Streamlit titkos kulcsait
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
    # Ha lokálisan fut, használja a credentials.json fájlt
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            st.error(f"Hiba: '{CREDENTIALS_FILE}' nem található.")
            return None
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE)

    try:
        client = gspread.authorize(creds)
        spreadsheet = client.open(GSHEET_NAME)
        return spreadsheet.sheet1 # Visszaadja az "Attendance" lapot
    except Exception as e:
        st.error(f"Google Sheets csatlakozási hiba: {e}")
        return None

@st.cache_data(ttl=300) # 5 percig gyorsítótárazza a létszámot
def get_counter_value(_gsheet):
    """Beolvassa a számlálót az E2 cellából."""
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
    """Legenerálja a keddi dátumokat egy listába."""
    tuesday_dates_list = []
    today = datetime.now().date()
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
    """Elmenti a sorokat a Google Sheets-be."""
    if gsheet is None:
        return False, "Nincs GSheet kapcsolat."
    try:
        gsheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        print(f"GSpread: {len(rows_to_add)} sor hozzáadva.")
        return True, "Sikeres mentés."
    except Exception as e:
        print(f"GSpread Mentési Hiba: {e}")
        return False, f"Hiba a mentés közben: {e}"

# --- FŐ ALKALMAZÁS (WEBES FELÜLET) ---

# Oldal beállítása
st.set_page_config(page_title="Röpi Jelenlét", layout="centered")

# Csatlakozás
gsheet = get_gsheet_connection()

# Cím és Számláló
st.title("🏐 Röpi Jelenléti Ív")
counter_value = get_counter_value(gsheet)
st.header(f"Következő alkalom létszáma: {counter_value} fő")
st.markdown("---")

# Űrlap létrehozása (hogy ne frissítsen minden kattintásra)
with st.form(key="attendance_form", clear_on_submit=True):
    
    # 1. Alap kérdések
    name_var = st.selectbox("Válassz nevet:", MAIN_NAME_LIST, index=0)
    answer_var = st.radio("Részt veszel az röpin?", ["Yes", "No"], index=0, horizontal=True)
    
    st.markdown("---")
    
    # 2. Dinamikus mezők
    past_event_var = st.checkbox("Múltbeli alkalmat regisztrálok")
    past_date_var = ""
    if past_event_var:
        tuesday_dates = generate_tuesday_dates()
        default_index = len(tuesday_dates) - 3 if len(tuesday_dates) >= 3 else 0
        past_date_var = st.selectbox(
            "Alkalom dátuma:", 
            tuesday_dates, 
            index=default_index
        )

    plus_count_var = "0"
    plus_people_names = []
    if answer_var == "Yes":
        plus_count_var = st.selectbox("Hozol plusz embert?", PLUS_PEOPLE_COUNT, index=0)
        
        # Plusz emberek nevei
        plus_count_int = int(plus_count_var)
        if plus_count_int > 0:
            st.markdown(f"**{plus_count_int} vendég neve:**")
            for i in range(plus_count_int):
                # Egyedi kulcsot (key) kell adni minden elemnek
                name_input = st.text_input(f"{i+1}. ember név:", key=f"plus_name_{i}")
                plus_people_names.append(name_input)

    # 3. Küldés gomb
    submitted = st.form_submit_button("Küldés")

# --- Feldolgozás (Űrlapon kívül) ---
if submitted:
    if gsheet is None:
        st.error("Hiba: A Google Sheets kapcsolat nem él. Próbáld frissíteni az oldalt.")
    else:
        # Adatok gyűjtése
        submission_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_date_str = past_date_var if past_event_var else ""
        
        rows_to_add = []
        
        # Fő felhasználó
        main_row = [name_var, answer_var, submission_timestamp, target_date_str]
        rows_to_add.append(main_row)
        
        # Plusz emberek
        guests_added_count = 0
        if answer_var == "Yes":
            for extra_name in plus_people_names:
                if extra_name.strip(): # Csak ha ki van töltve a név
                    extra_row = [
                        f"{name_var} - {extra_name.strip()}", 
                        "Yes", 
                        submission_timestamp, 
                        target_date_str
                    ]
                    rows_to_add.append(extra_row)
                    guests_added_count += 1
        
        # Mentés
        success, message = save_data_to_gsheet(gsheet, rows_to_add)
        
        if success:
            success_msg = f"Köszönjük, {name_var}! A válaszod rögzítve."
            if guests_added_count > 0:
                success_msg += f" (Plusz {guests_added_count} fő vendég)"
            st.success(success_msg)
        else:
            st.error(f"Mentési hiba: {message}")