import streamlit as st
import gspread
from google.cloud import firestore
from google.oauth2 import service_account
import os
import json
import pandas as pd

from modules.config import (
    CREDENTIALS_FILE, GSHEET_NAME, FIRESTORE_COLLECTION, FIRESTORE_INVOICES,
    FIRESTORE_CANCELLED, FIRESTORE_MEMBERS, MEMBERS_SHEET_NAME, FIRESTORE_NAME_MAPPING,
    FIRESTORE_SETTLEMENTS, FIRESTORE_DEVICES,
)


def _parse_private_key(creds_dict):
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"].strip().strip('"').strip("'")
        if "\\n" in pk:
            pk = pk.replace("\\n", "\n")
        creds_dict["private_key"] = pk
    return creds_dict


@st.cache_resource(ttl=3600)
def get_gsheet_connection():
    if hasattr(st, 'secrets') and "google_creds" in st.secrets:
        try:
            creds_dict = _parse_private_key(dict(st.secrets["google_creds"]))
            return gspread.service_account_from_dict(creds_dict)
        except Exception as e:
            st.warning(f"GSheet kapcsolódási hiba: {e}")
    if os.path.exists(CREDENTIALS_FILE):
        try:
            return gspread.service_account(filename=CREDENTIALS_FILE)
        except Exception as e:
            st.warning(f"GSheet kapcsolódási hiba (fájl): {e}")
    return None


@st.cache_resource(ttl=3600)
def get_firestore_db():
    try:
        if hasattr(st, 'secrets') and "google_creds" in st.secrets:
            creds_dict = _parse_private_key(dict(st.secrets["google_creds"]))
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds, project=creds_dict.get("project_id"))
        elif os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                creds_dict = json.load(f)
            return firestore.Client.from_service_account_json(CREDENTIALS_FILE, project=creds_dict.get("project_id"))
    except Exception as e:
        st.error(f"Firestore indítási hiba: {e}")
    return None


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
                    "name": r[0], "status": r[1], "timestamp": r[2],
                    "event_date": r[3], "mode": r[5] if len(r) > 5 else "ismeretlen"
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
        return True, f"Mentve a Sheet-be, de Firestore hiba: {error_msg_fs} ⚠️"
    else:
        return False, "Kritikus hiba, egyik adatbázis sem érhető el."


@st.cache_data(ttl=300)
def get_attendance_rows_gs(_client):
    if _client is None:
        return []
    try:
        return _client.open(GSHEET_NAME).sheet1.get_all_values()
    except Exception:
        return []


@st.cache_data(ttl=60)
def get_attendance_rows_fs(_db):
    if _db is None:
        return pd.DataFrame(columns=["ID", "Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Mód"])
    try:
        docs = _db.collection(FIRESTORE_COLLECTION).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            data.append([doc.id, d.get("name"), d.get("status"), d.get("timestamp"), d.get("event_date"), d.get("mode", "ismeretlen")])
        return pd.DataFrame(data, columns=["ID", "Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Mód"])
    except Exception as e:
        st.error(f"Hiba a Firestore adatok betöltésekor: {e}")
        return pd.DataFrame(columns=["ID", "Név", "Jön-e", "Regisztráció Időpontja", "Alkalom Dátuma", "Mód"])


@st.cache_data(ttl=60)
def get_cancelled_sessions_fs(_db):
    if _db is None:
        return set()
    try:
        from modules.utils import parse_date_str
        docs = _db.collection(FIRESTORE_CANCELLED).stream()
        cancelled = set()
        for doc in docs:
            d = doc.to_dict()
            date_str = d.get("date")
            if date_str:
                date_obj = parse_date_str(date_str)
                if date_obj:
                    cancelled.add(date_obj)
        return cancelled
    except Exception:
        return set()


@st.cache_data(ttl=60)
def get_invoices_fs(_db):
    if _db is None:
        return []
    try:
        docs = _db.collection(FIRESTORE_INVOICES).stream()
        invoices = []
        month_names = ["Január", "Február", "Március", "Április", "Május", "Június",
                       "Július", "Augusztus", "Szeptember", "Október", "November", "December"]
        for doc in docs:
            d = doc.to_dict()
            d["ID"] = doc.id
            if "month_name" not in d and "target_month" in d:
                d["month_name"] = month_names[int(d["target_month"]) - 1]
            invoices.append(d)
        invoices.sort(key=lambda x: (int(x.get('target_year', 0)), int(x.get('target_month', 0))), reverse=True)
        return invoices
    except Exception:
        return []


@st.cache_data(ttl=120)
def get_members_fs(_db):
    if _db is None:
        return pd.DataFrame(columns=["ID", "Név", "Email", "Aktív"])
    try:
        docs = _db.collection(FIRESTORE_MEMBERS).order_by("name").stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            data.append([doc.id, d.get("name", ""), d.get("email", ""), d.get("active", True)])
        return pd.DataFrame(data, columns=["ID", "Név", "Email", "Aktív"])
    except Exception as e:
        st.error(f"Hiba a tagok betöltésekor: {e}")
        return pd.DataFrame(columns=["ID", "Név", "Email", "Aktív"])


def get_members_gs(gs_client):
    if gs_client is None:
        return pd.DataFrame(columns=["Név", "Email", "Aktív"])
    try:
        ss = gs_client.open(GSHEET_NAME)
        sheet_titles = [w.title for w in ss.worksheets()]
        if MEMBERS_SHEET_NAME not in sheet_titles:
            ws = ss.add_worksheet(title=MEMBERS_SHEET_NAME, rows=100, cols=5)
            ws.append_row(["Név", "Email", "Aktív"])
            return pd.DataFrame(columns=["Név", "Email", "Aktív"])
        ws = ss.worksheet(MEMBERS_SHEET_NAME)
        rows = ws.get_all_values()
        if len(rows) < 2:
            return pd.DataFrame(columns=["Név", "Email", "Aktív"])
        return pd.DataFrame(rows[1:], columns=rows[0])
    except Exception as e:
        st.error(f"Tagok betöltési hiba (Sheet): {e}")
        return pd.DataFrame(columns=["Név", "Email", "Aktív"])


def sync_members_fs_to_gs(fs_db, gs_client):
    df = get_members_fs(fs_db)
    try:
        ss = gs_client.open(GSHEET_NAME)
        sheet_titles = [w.title for w in ss.worksheets()]
        if MEMBERS_SHEET_NAME not in sheet_titles:
            ws = ss.add_worksheet(title=MEMBERS_SHEET_NAME, rows=100, cols=5)
        else:
            ws = ss.worksheet(MEMBERS_SHEET_NAME)
        ws.clear()
        rows = [["Név", "Email", "Aktív"]]
        for _, row in df.iterrows():
            rows.append([row["Név"], row["Email"], str(row["Aktív"])])
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        return True, f"{len(df)} tag szinkronizálva a Sheet-be."
    except Exception as e:
        return False, str(e)


def sync_members_gs_to_fs(gs_client, fs_db):
    df = get_members_gs(gs_client)
    try:
        docs = fs_db.collection(FIRESTORE_MEMBERS).stream()
        for doc in docs:
            doc.reference.delete()
        count = 0
        for _, row in df.iterrows():
            name = str(row.get("Név", "")).strip()
            email = str(row.get("Email", "")).strip()
            if not name:
                continue
            active = str(row.get("Aktív", "True")).lower() not in ("false", "0", "nem")
            fs_db.collection(FIRESTORE_MEMBERS).add({"name": name, "email": email, "active": active})
            count += 1
        return True, f"{count} tag szinkronizálva a Firestore-ba."
    except Exception as e:
        return False, str(e)


def save_settlement_fs(fs_db, year, month_num, month_name, df_elszamolas, df_osszesito):
    """Elmenti az elszámolás eredményét Firestore-ba. Doc ID: 'YYYY-MM' formátum."""
    if fs_db is None:
        return False, "Nincs Firestore kapcsolat."
    try:
        doc_id = f"{year}-{int(month_num):02d}"
        fs_db.collection(FIRESTORE_SETTLEMENTS).document(doc_id).set({
            "year": year,
            "month_num": int(month_num),
            "month_name": month_name,
            "df_elszamolas": df_elszamolas.to_json(orient="records", force_ascii=False),
            "df_osszesito": df_osszesito.to_json(orient="records", force_ascii=False),
            "saved_at": firestore.SERVER_TIMESTAMP,
        })
        return True, doc_id
    except Exception as e:
        return False, str(e)


def get_settlement_fs(fs_db, year, month_num):
    """Betölti az elszámolást Firestore-ból. Visszatér: (df_elszamolas, df_osszesito, month_name) vagy None."""
    if fs_db is None:
        return None
    try:
        doc_id = f"{year}-{int(month_num):02d}"
        doc = fs_db.collection(FIRESTORE_SETTLEMENTS).document(doc_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict()
        df_elszamolas = pd.read_json(d["df_elszamolas"], orient="records")
        df_osszesito = pd.read_json(d["df_osszesito"], orient="records")
        return df_elszamolas, df_osszesito, d["month_name"]
    except Exception:
        return None


def sync_qr_checkins_to_sheet(fs_db, gs_client):
    """QR check-in rekordokat (synced_to_sheet=False) szinkronizálja a Google Sheetsbe."""
    if not fs_db or not gs_client:
        return 0
    try:
        docs = list(fs_db.collection(FIRESTORE_COLLECTION)
                    .where("synced_to_sheet", "==", False).stream())
        if not docs:
            return 0
        rows = []
        for doc in docs:
            d = doc.to_dict()
            rows.append([d.get("name",""), d.get("status","Yes"),
                         d.get("timestamp",""), d.get("event_date",""), "", d.get("mode","qr")])
        sheet = gs_client.open(GSHEET_NAME).sheet1
        sheet.append_rows(rows, value_input_option='USER_ENTERED')
        for doc in docs:
            doc.reference.update({"synced_to_sheet": True})
        return len(rows)
    except Exception:
        return 0


def get_device_registration(fs_db, device_id):
    """Visszaadja a device_id-hez tartozó nevet, vagy None-t."""
    if not fs_db or not device_id:
        return None
    try:
        doc = fs_db.collection(FIRESTORE_DEVICES).document(device_id).get()
        if doc.exists:
            return doc.to_dict().get("name")
        return None
    except Exception:
        return None


def save_device_registration(fs_db, device_id, name):
    """Elmenti a device_id → name mappinget Firestore-ba."""
    if not fs_db or not device_id:
        return False
    try:
        fs_db.collection(FIRESTORE_DEVICES).document(device_id).set({
            "name": name,
            "registered_at": firestore.SERVER_TIMESTAMP,
        })
        return True
    except Exception:
        return False


@st.cache_data(ttl=120)
def get_name_mappings_fs(_db):
    if _db is None:
        return {}
    try:
        docs = _db.collection(FIRESTORE_NAME_MAPPING).stream()
        mapping = {}
        for doc in docs:
            d = doc.to_dict()
            mapping[d.get("revolut_name", "")] = {
                "system_name": d.get("system_name", ""),
                "doc_id": doc.id
            }
        return mapping
    except Exception:
        return {}
