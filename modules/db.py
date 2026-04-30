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
    FIRESTORE_SETTLEMENTS, FIRESTORE_DEVICES, FIRESTORE_LEGACY, LEGACY_SHEET_NAME,
    FIRESTORE_HISTORICAL, HISTORICAL_SHEET_NAME
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
    error_msg_gs = ""
    error_msg_fs = ""

    # Google Sheets mentés — hiba esetén folytatódik a Firestore mentés
    if gs_client:
        try:
            sheet = gs_client.open(GSHEET_NAME).sheet1
            sheet.append_rows(rows, value_input_option='USER_ENTERED')
            success_gs = True
        except Exception as e:
            error_msg_gs = str(e)
            print(f"GSheet mentési hiba: {e}")

    # Firestore mentés — a GS eredményétől független
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
            print(f"Firestore mentési hiba: {e}")
    else:
        error_msg_fs = "Nincs aktív Firestore kapcsolat."

    st.cache_data.clear()

    if success_gs and success_fs:
        return True, "Sikeres mentés a Google Sheet-be és a Firestore-ba is! ✅☁️"
    elif success_fs and not success_gs:
        return True, f"Mentve a Firestore-ba, de Google Sheet hiba: {error_msg_gs} ⚠️"
    elif success_gs and not success_fs:
        return True, f"Mentve a Sheet-be, de Firestore hiba: {error_msg_fs} ⚠️"
    else:
        return False, f"Kritikus hiba, egyik adatbázis sem érhető el. (GS: {error_msg_gs} | FS: {error_msg_fs})"


@st.cache_data(ttl=300)
def get_attendance_rows_gs(_client):
    if _client is None:
        return []
    try:
        return _client.open(GSHEET_NAME).sheet1.get_all_values()
    except Exception as e:
        st.warning(f"⚠️ Google Sheet betöltési hiba: {e}")
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
    except Exception as e:
        st.warning(f"⚠️ Törölt alkalmak betöltési hiba (az elszámolás pontatlan lehet): {e}")
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
    except Exception as e:
        st.error(f"❌ Számlák betöltési hiba: {e}")
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


@st.cache_data(ttl=300)
def get_members_gs(_gs_client):
    if _gs_client is None:
        return pd.DataFrame(columns=["Név", "Email", "Aktív"])
    try:
        ss = _gs_client.open(GSHEET_NAME)
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


@st.cache_data(ttl=300)
def get_all_settlements_for_player(_fs_db, name: str) -> list:
    """
    Összegyűjti az összes elmentett elszámolásból az adott játékos adatait.

    Visszatér: [{"year": int, "month_num": int, "month_name": str,
                  "count": int, "amount": float}, ...] — időrend szerint növekvő.
    """
    if _fs_db is None:
        return []
    try:
        docs = _fs_db.collection(FIRESTORE_SETTLEMENTS).stream()
        results = []
        for doc in docs:
            d = doc.to_dict()
            if "df_osszesito" not in d:
                continue
            try:
                df_osszesito = pd.read_json(d["df_osszesito"], orient="records")
            except Exception:
                continue
            if df_osszesito.empty or "Név" not in df_osszesito.columns:
                continue
            player_row = df_osszesito[df_osszesito["Név"] == name]
            if player_row.empty:
                continue
            row = player_row.iloc[0]
            results.append({
                "year": int(d.get("year", 0)),
                "month_num": int(d.get("month_num", 0)),
                "month_name": str(d.get("month_name", "")),
                "count": int(row.get("Részvétel száma", 0)),
                "amount": float(row.get("Fizetendő (Ft)", 0.0)),
            })
        results.sort(key=lambda x: (x["year"], x["month_num"]))
        return results
    except Exception as e:
        print(f"get_all_settlements_for_player hiba: {e}")
        return []


@st.cache_data(ttl=300)
def get_avg_session_attendees_for_year(_fs_db, year: int):
    """
    Kiszámolja az átlagos résztvevőszámot a megadott évre az elmentett elszámolások alapján.
    Ezzel pontosítható a becsült összeg. Ha nincs adat, None-t ad vissza.
    """
    if _fs_db is None:
        return None
    try:
        docs = _fs_db.collection(FIRESTORE_SETTLEMENTS).stream()
        total_attendees = 0
        total_sessions = 0
        for doc in docs:
            d = doc.to_dict()
            if int(d.get("year", 0)) != year:
                continue
            if "df_elszamolas" not in d:
                continue
            try:
                df_elszamolas = pd.read_json(d["df_elszamolas"], orient="records")
            except Exception:
                continue
            if "Létszám" in df_elszamolas.columns:
                for val in df_elszamolas["Létszám"]:
                    try:
                        num = int(str(val).replace(" fő", "").strip())
                        total_attendees += num
                        total_sessions += 1
                    except Exception:
                        pass
        if total_sessions == 0:
            return None
        return round(total_attendees / total_sessions, 1)
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
    except Exception as e:
        st.warning(f"⚠️ Eszköz regisztráció mentési hiba (legközelebb újra kell azonosítanod magad): {e}")
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


@st.cache_data(ttl=300)
def get_legacy_totals_fs(_db):
    if _db is None:
        return []
    try:
        docs = _db.collection(FIRESTORE_LEGACY).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            data.append(d)
        return data
    except Exception as e:
        st.error(f"Hiba a legacy adatok betöltésekor: {e}")
        return []





def sync_legacy_fs_to_gs(fs_db, gs_client):
    data = get_legacy_totals_fs(fs_db)
    if not data:
        return False, "Nincs adat a Firestore-ban."
    try:
        ss = gs_client.open(GSHEET_NAME)
        sheet_titles = [w.title for w in ss.worksheets()]
        if LEGACY_SHEET_NAME not in sheet_titles:
            ws = ss.add_worksheet(title=LEGACY_SHEET_NAME, rows=100, cols=4)
        else:
            ws = ss.worksheet(LEGACY_SHEET_NAME)
        ws.clear()
        rows = [["Név", "Összes (All time)", "2024", "2025", "2026"]]
        for rec in data:
            rows.append([rec.get("name", ""), rec.get("total_all_time", 0), rec.get("year_2024", 0), rec.get("year_2025", 0), rec.get("year_2026", 0)])
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        return True, f"{len(data)} legacy rekord szinkronizálva a Sheet-be."
    except Exception as e:
        return False, str(e)


def sync_legacy_gs_to_fs(gs_client, fs_db):
    try:
        ss = gs_client.open(GSHEET_NAME)
        ws = ss.worksheet(LEGACY_SHEET_NAME)
        rows = ws.get_all_values()
        if len(rows) < 2:
            return False, "Nincs adat a Sheet-ben."
            
        docs_to_insert = []
        for r in rows[1:]:
            if not r[0]: continue
            docs_to_insert.append({
                "name": r[0],
                "total_all_time": int(r[1]) if len(r) > 1 and r[1] else 0,
                "year_2024": int(r[2]) if len(r) > 2 and r[2] else 0,
                "year_2025": int(r[3]) if len(r) > 3 and r[3] else 0,
                "year_2026": int(r[4]) if len(r) > 4 and r[4] else 0
            })

        if not docs_to_insert:
            return False, "Üres lista, nincs mit szinkronizálni."

        # Biztonságos sorrend: ELŐBB ír, UTÁNA töröl — adatvesztés elkerülése
        batch = fs_db.batch()
        for rec in docs_to_insert:
            doc_id = rec["name"].replace(" ", "_")
            doc_ref = fs_db.collection(FIRESTORE_LEGACY).document(doc_id)
            batch.set(doc_ref, rec)
        batch.commit()

        # Töröljük azokat, amelyek nem szerepelnek az új listában
        new_ids = {rec["name"].replace(" ", "_") for rec in docs_to_insert}
        old_docs = list(fs_db.collection(FIRESTORE_LEGACY).stream())
        stale = [d for d in old_docs if d.id not in new_ids]
        if stale:
            del_batch = fs_db.batch()
            for d in stale:
                del_batch.delete(d.reference)
            del_batch.commit()

        return True, f"{len(docs_to_insert)} legacy rekord szinkronizálva a Firestore-ba."
    except Exception as e:
        return False, str(e)


@st.cache_data(ttl=300)
def get_historical_stats_fs(_db):
    if _db is None:
        return []
    try:
        docs = _db.collection(FIRESTORE_HISTORICAL).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            # doc id is date string, data has "date", "total"
            if "date" in d and "total" in d:
                data.append({"date": d["date"], "total": d["total"]})
        return data
    except Exception as e:
        st.error(f"Hiba a historikus adatok betöltésekor: {e}")
        return []


def import_historical_stats_to_db(fs_db, gs_client):
    try:
        from datetime import datetime
        
        # A projekt gyökérkönyvtárának meghatározása a db.py helyzete alapján
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        excel_path = os.path.join(base_dir, 'Röplabda jelenlét.xlsx')
        
        if not os.path.exists(excel_path):
            return False, f"Nem található a fájl ezen az útvonalon: {excel_path}"
            
        df = pd.read_excel(excel_path)
        col_date = df.columns[0]
        
        if len(df.columns) <= 24:
            return False, "A fájl nem tartalmazza a várt 25 oszlopot (az Y oszlop hiányzik)."
            
        col_total = df.columns[24]
        
        historical_data = []
        for i in range(len(df)):
            dt_val = df.iloc[i][col_date]
            tot_val = df.iloc[i][col_total]
            
            if pd.isna(dt_val) or pd.isna(tot_val):
                continue
                
            if isinstance(dt_val, str):
                try:
                    dt_obj = datetime.strptime(str(dt_val)[:10], "%Y-%m-%d")
                except:
                    continue
            elif isinstance(dt_val, datetime) or hasattr(dt_val, "strftime"):
                dt_obj = dt_val
            else:
                continue
                
            try:
                total_num = int(float(str(tot_val)))
            except:
                total_num = 0
                
            if total_num > 0:
                historical_data.append({
                    "date": dt_obj.strftime("%Y-%m-%d"),
                    "total": total_num
                })
                
        historical_data.sort(key=lambda x: x["date"])
        
        if fs_db:
            batch = fs_db.batch()
            for doc in fs_db.collection(FIRESTORE_HISTORICAL).stream():
                batch.delete(doc.reference)
            batch.commit()
            
            batch = fs_db.batch()
            for h in historical_data:
                doc_ref = fs_db.collection(FIRESTORE_HISTORICAL).document(h["date"])
                batch.set(doc_ref, h)
            batch.commit()
            
        if gs_client:
            ss = gs_client.open(GSHEET_NAME)
            sheet_titles = [w.title for w in ss.worksheets()]
            if HISTORICAL_SHEET_NAME not in sheet_titles:
                ws = ss.add_worksheet(title=HISTORICAL_SHEET_NAME, rows=max(100, len(historical_data)+10), cols=2)
            else:
                ws = ss.worksheet(HISTORICAL_SHEET_NAME)
            ws.clear()
            rows = [["Dátum", "Összes Részvétel"]]
            for h in historical_data:
                rows.append([h["date"], h["total"]])
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            
        return True, f"Sikeresen beolvasva és szinkronizálva {len(historical_data)} régi nap!"
    except Exception as e:
        return False, f"Hiba az Excel importkor: {e}"


def import_legacy_attendance_records(fs_db, gs_client):
    """Importálja az egyéni Legacy jelenléti rekordokat az Excel-ből az attendance_records-ba.
    Csak 'Jövök :)' értékeket importál, mode='legacy' taggel.
    Duplikálás ellen: ha már van legacy rekord, leáll."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base_dir, 'Röplabda jelenlét.xlsx')

    if not os.path.exists(excel_path):
        return False, f"Nem találom a fájlt: {excel_path}", 0

    # Duplikálás ellenőrzése
    if fs_db:
        try:
            existing = list(fs_db.collection(FIRESTORE_COLLECTION)
                            .where("mode", "==", "legacy").limit(1).stream())
            if existing:
                return False, "Már vannak 'legacy' rekordok az adatbázisban – duplikálás elkerülése végett az import le lett állítva.", 0
        except Exception as e:
            return False, f"Ellenőrzési hiba: {e}", 0

    df = pd.read_excel(excel_path, header=None)

    # 0. sor: fejléc — 0. oszlop = 'Név:', 1-21 = játékosok, 22 = 'Plusz emberek száma'
    player_cols = []
    for c in range(1, len(df.columns)):
        cell = df.iloc[0, c]
        if pd.isna(cell):
            continue
        name = str(cell).strip()
        if name in ("", "Plusz emberek száma"):
            continue
        player_cols.append((c, name))

    records = []
    for r in range(1, len(df)):
        date_val = df.iloc[r, 0]
        if pd.isna(date_val):
            continue
        try:
            if hasattr(date_val, 'strftime'):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                from datetime import datetime as _dt
                date_str = _dt.strptime(str(date_val)[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
        except Exception:
            continue

        for col_idx, name in player_cols:
            cell_val = df.iloc[r, col_idx]
            if pd.isna(cell_val):
                continue
            val_str = str(cell_val).strip()

            # Szöveges formátum: "Jövök :)" / "Nem jövök :("
            if "Jövök" in val_str or ":)" in val_str:
                is_coming = True
            elif "Nem" in val_str or ":(" in val_str:
                is_coming = False
            else:
                # Numerikus formátum: 0 = nem jön, >=1 = jön
                try:
                    num = float(val_str)
                    is_coming = num >= 1
                except ValueError:
                    continue  # ismeretlen érték, skip

            if is_coming:
                records.append({
                    "name": name,
                    "status": "Yes",
                    "timestamp": date_str + " 12:00:00",
                    "event_date": date_str,
                    "mode": "legacy"
                })

    if not records:
        return False, "Nem sikerült 'Jövök' értékeket kiolvasni az Excelből.", 0

    # Firestore batch write (max 500/batch)
    if fs_db:
        try:
            batch = fs_db.batch()
            count_batch = 0
            for rec in records:
                doc_ref = fs_db.collection(FIRESTORE_COLLECTION).document()
                batch.set(doc_ref, rec)
                count_batch += 1
                if count_batch >= 500:
                    batch.commit()
                    batch = fs_db.batch()
                    count_batch = 0
            if count_batch > 0:
                batch.commit()
        except Exception as e:
            return False, f"Firestore írási hiba: {e}", 0

    # GSheet write (max 500 sor/hívás)
    if gs_client:
        try:
            sheet = gs_client.open(GSHEET_NAME).sheet1
            rows_to_add = [
                [rec["name"], rec["status"], rec["timestamp"], rec["event_date"], "", rec["mode"]]
                for rec in records
            ]
            for i in range(0, len(rows_to_add), 500):
                sheet.append_rows(rows_to_add[i:i + 500], value_input_option='USER_ENTERED')
        except Exception as e:
            st.cache_data.clear()
            return True, f"Firestore OK, de GSheet hiba: {e}", len(records)

    st.cache_data.clear()
    unique_dates = len(set(r['event_date'] for r in records))
    return True, f"Sikeresen importálva {len(records)} egyéni jelenlét rekord ({unique_dates} különböző dátumból).", len(records)
