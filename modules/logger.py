import streamlit as st
import datetime
import json
from google.cloud import firestore

from modules.config import FIRESTORE_APP_LOGS

def get_client_ip():
    """
    Megpróbálja kinyerni a kliens IP címét a Streamlit contextből.
    Ez Streamlit 1.37+ verziókon és bizonyos felhő környezeteknél működik a legjobban.
    """
    try:
        # Próbáljuk a session_state-be ágyazott esetleges header info-kat elérni (ha van proxy)
        if hasattr(st, "context") and hasattr(st.context, "headers"):
            headers = st.context.headers
            if "X-Forwarded-For" in headers:
                return headers["X-Forwarded-For"].split(",")[0].strip()
            elif "X-Real-IP" in headers:
                return headers["X-Real-IP"].strip()
    except Exception:
        pass
    
    return "Ismeretlen IP"


def log_event(fs_db, level, message, details=None):
    """
    Esemény naplózása a Firestore FIRESTORE_APP_LOGS gyűjteményébe.
    
    :param fs_db: Firestore kliens
    :param level: "INFO", "WARNING", "ERROR"
    :param message: Rövid eseményleírás
    :param details: Bármilyen extra adat (dict)
    """
    if fs_db is None:
        return False
        
    try:
        user_email = ""
        user_name = ""
        if hasattr(st, "user"):
            user_email = st.user.email if hasattr(st.user, "email") else ""
            user_name = st.user.name if hasattr(st.user, "name") else ""
            
        ip_addr = get_client_ip()
        
        log_data = {
            "timestamp": firestore.SERVER_TIMESTAMP,
            "created_at_local": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level.upper(),
            "message": message,
            "user_email": user_email,
            "user_name": user_name,
            "ip_address": ip_addr
        }
        
        if details:
            if isinstance(details, dict):
                log_data["details"] = json.dumps(details, ensure_ascii=False)
            else:
                log_data["details"] = str(details)
                
        fs_db.collection(FIRESTORE_APP_LOGS).add(log_data)
        return True
    except Exception as e:
        # Ha a naplózás beszakad, írjuk a konzolra vagy belső állapotba
        print(f"Hiba a naplózás (log_event) során: {e}")
        return False


@st.cache_data(ttl=60)
def get_logs_fs(_db, limit=200):
    """
    Letölti az eddig naplózott eseményeket a kezelőfelülethez.
    """
    if _db is None:
        return []
        
    try:
        docs = _db.collection(FIRESTORE_APP_LOGS).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
        data = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            data.append(d)
        return data
    except Exception as e:
        print(f"Hiba a logok lekérésében: {e}")
        return []

