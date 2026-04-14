import sys
import os
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.db import get_gsheet_connection, get_firestore_db
from modules.config import GSHEET_NAME

def main():
    print("Loading Excel...")
    df = pd.read_excel('Röplabda jelenlét.xlsx')
    
    historical_data = []
    
    # Keresünk egy Dátum és Összesítő oszlopot
    col_date = df.columns[0]
    # The totals column was indices 24
    if len(df.columns) > 24:
        col_total = df.columns[24]
    else:
        print("Nem található az Y oszlop!")
        return
        
    print(f"Dátum oszlop: {col_date}, Létszám oszlop: {col_total}")
    
    for i in range(len(df)):
        dt_val = df.iloc[i][col_date]
        tot_val = df.iloc[i][col_total]
        
        # Ha a dátum string vagy datetime
        if pd.isna(dt_val) or pd.isna(tot_val):
            continue
            
        # Átalakítás ha szükséges
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
            date_str = dt_obj.strftime("%Y-%m-%d")
            historical_data.append({
                "date": date_str,
                "total": total_num
            })

    # Sort
    historical_data.sort(key=lambda x: x["date"])
    print(f"Sikeresen feldolgozva: {len(historical_data)} nap!")

    print("Connecting to Firestore...")
    fs_db = get_firestore_db()
    if fs_db:
        batch = fs_db.batch()
        for doc in fs_db.collection("historical_session_totals").stream():
            batch.delete(doc.reference)
        batch.commit()
        
        batch = fs_db.batch()
        for h in historical_data:
            doc_ref = fs_db.collection("historical_session_totals").document(h["date"])
            batch.set(doc_ref, h)
        batch.commit()
        print("Firestore feltöltés KÉSZ!")
    else:
        print("Firestore connection failed.")
        
    print("Connecting to GSheet...")
    gs_client = get_gsheet_connection()
    if gs_client:
        ss = gs_client.open(GSHEET_NAME)
        worksheet_title = "Historical_Totals"
        sheet_titles = [w.title for w in ss.worksheets()]
        if worksheet_title not in sheet_titles:
            ws = ss.add_worksheet(title=worksheet_title, rows=max(100, len(historical_data)+10), cols=2)
        else:
            ws = ss.worksheet(worksheet_title)
            
        ws.clear()
        
        rows = [["Dátum", "Összes Részvétel"]]
        for h in historical_data:
            rows.append([h["date"], h["total"]])
            
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        print("Google Sheet feltöltés KÉSZ!")
    else:
        print("Google Sheet connection failed.")

if __name__ == "__main__":
    main()
