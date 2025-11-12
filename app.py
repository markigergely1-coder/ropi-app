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

# --- HÁTTÉRLOGIKA (GSPREAD ÉS DÁTUMOK) ---

@st.cache_resource(ttl=3600)
def get_gsheet_connection():
    """Csatlakozik a Google Sheets-hez és visszaadja a munkalapot."""
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
    """Elmenti a sorokat a Google Sheets-be."""
    if gsheet is None:
        return False, "Nincs GSheet kapcsolat."
    try:
        gsheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        print(f"GSpread: {len(rows_to_add)} sor hozzáadva.")
        
        st.cache_data.clear() # Törli a számláló gyorsítótárát
        
        return True, "Sikeres mentés."
    except Exception as e:
        print(f"GSpread Mentési Hiba: {e}")
        return False, f"Hiba a mentés közben: {e}"

# --- JAVÍTOTT FÜGGVÉNY: Az űrlapfeldolgozó logika ---
def process_form_submission():
    """
    Ez a függvény fut le, amikor a felhasználó a "Küldés" gombra kattint.
    Összegyűjti az adatokat a session_state-ből, elmenti, és alaphelyzetbe állítja az űrlapot.
    """
    
    # 0. Hozzáférés a GSheet-hez (a cache-ből)
    gsheet = get_gsheet_connection()
    if gsheet is None:
        st.error("Hiba: A Google Sheets kapcsolat nem él. Próbáld frissíteni az oldalt.")
        return

    # 1. Adatok gyűjtése a session_state-ből
    try:
        name_val = st.session_state.name_select
        answer_val = st.session_state.answer_radio
        past_event_val = st.session_state.past_event_check
        past_date_val = st.session_state.get("past_date_select", "") # .get() biztonságosabb
        plus_count_val = st.session_state.plus_count if answer_val == "Yes" else "0"
        
        submission_timestamp = datetime.now(HUNGARY_TZ).strftime("%Y-%m-%d %H:%M:%S")
        
        rows_to_add = []
        
        # Fő felhasználó
        main_row = [name_val, answer_val, submission_timestamp, past_date_val]
        rows_to_add.append(main_row)
        
        # Plusz emberek
        guests_added_count = 0
        if answer_val == "Yes":
            for i in range(int(plus_count_val)):
                extra_name_key = f"plus_name_txt_{i}"
                extra_name = st.session_state.get(extra_name_key, "").strip()
                
                if extra_name: # Csak ha ki van töltve a név
                    extra_row = [
                        f"{name_val} - {extra_name}", 
                        "Yes", 
                        submission_timestamp, 
                        past_date_val
                    ]
                    rows_to_add.append(extra_row)
                    guests_added_count += 1
        
        # 2. Mentés
        success, message = save_data_to_gsheet(gsheet, rows_to_add)
        
        if success:
            success_msg = f"Köszönjük, {name_val}! A válaszod rögzítve."
            if guests_added_count > 0:
                success_msg += f" (Plusz {guests_added_count} fő vendég)"
            st.success(success_msg)
            
            # 3. Űrlap alaphelyzetbe állítása (Reset)
            # A kulcsok törlése a session_state-ből a helyes módja az alaphelyzetbe állításnak
            keys_to_reset = [
                "plus_count", "past_event_check", "past_date_select",
                "name_select", "answer_radio"
            ]
            for i in range(10):
                keys_to_reset.append(f"plus_name_txt_{i}")
            
            for key in keys_to_reset:
                if key in st.session_state:
                    del st.session_state[key]
            
            # (Az alapértelmezett értékeket a szkript tetején lévő "if 'key' not in..." 
            #  logika fogja újra beállítani a st.rerun() után)
            
        else:
            st.error(f"Mentési hiba: {message}")

    except Exception as e:
        st.error(f"Váratlan hiba a feldolgozás során: {e}")


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

# Alapértelmezett értékek beállítása (ha még nem léteznek)
if 'plus_count' not in st.session_state:
    st.session_state.plus_count = "0"

# 1. Alap kérdések
st.selectbox("Válassz nevet:", MAIN_NAME_LIST, index=0, key="name_select")
st.radio("Részt veszel az röpin?", ["Yes", "No"], index=0, horizontal=True, key="answer_radio")

st.markdown("---")

# 2. Dinamikus mezők
past_event_var = st.checkbox("Múltbeli alkalmat regisztrálok", key="past_event_check")
if past_event_var:
    tuesday_dates = generate_tuesday_dates()
    default_index = len(tuesday_dates) - 3 if len(tuesday_dates) >= 3 else 0
    st.selectbox(
        "Alkalom dátuma:", 
        tuesday_dates, 
        index=default_index,
        key="past_date_select"
    )

if st.session_state.answer_radio == "Yes":
    st.selectbox(
        "Hozol plusz embert?", 
        PLUS_PEOPLE_COUNT, 
        key="plus_count" # A key már be van állítva a session state-ben
    )
    
    plus_count_int = int(st.session_state.plus_count)
    if plus_count_int > 0:
        st.markdown(f"**{plus_count_int} vendég neve:**")
        
        # A beviteli mezők létrehozása
        for i in range(plus_count_int):
            st.text_input(
                f"{i+1}. ember név:", 
                key=f"plus_name_txt_{i}" # Egyedi kulcs
            )

# 3. Küldés gomb
# <<< JAVÍTÁS: A gomb most már az "on_click" callback-et hívja
st.button("Küldés", on_click=process_form_submission)