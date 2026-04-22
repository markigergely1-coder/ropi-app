import streamlit as st
import os
import pandas as pd
import calendar
from datetime import datetime, timedelta

from modules.config import HUNGARY_TZ


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
    tuesdays = []
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        tuesday_day = week[calendar.TUESDAY]
        if tuesday_day != 0:
            tuesdays.append(datetime(year, month, tuesday_day).date())
    return tuesdays


def parse_date_str(date_str):
    if not date_str or pd.isna(date_str):
        return None
    clean_str = str(date_str).strip()
    if clean_str.lower() in ['nan', 'none', '']:
        return None
    if clean_str.endswith('.'):
        clean_str = clean_str[:-1]
    clean_str = clean_str.replace('. ', '-').replace('.', '-')
    try:
        return datetime.strptime(clean_str.split(" ")[0], "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S").date()
        except Exception:
            return None


parse_hungarian_date = parse_date_str


def get_historical_guests_list(rows, main_name):
    if not rows:
        return []
    prefix = f"{main_name} - "
    guests = set()
    for row in rows[1:]:
        if row and row[0].startswith(prefix):
            guest_part = row[0].replace(prefix, "", 1).strip()
            if guest_part:
                guests.add(guest_part)
    return sorted(list(guests))


def build_total_attendance(rows, year=None):
    status_by_name_date = {}
    for row in rows[1:]:
        name = row[0].strip() if len(row) > 0 else ""
        response = row[1].strip() if len(row) > 1 else ""
        evt = row[3].strip() if len(row) > 3 else ""
        reg = row[2].strip() if len(row) > 2 else ""
        if not name or response not in {"Yes", "No"}:
            continue
        record_date = parse_date_str(evt) or parse_date_str(reg)
        if record_date is None:
            continue
        if year is not None and record_date.year != year:
            continue
        key = (name, record_date)
        status = status_by_name_date.setdefault(key, {"yes": False, "no": False})
        if response == "Yes":
            status["yes"] = True
        else:
            status["no"] = True
    totals = {}
    for (name, _), status in status_by_name_date.items():
        if status["yes"] and not status["no"]:
            totals[name] = totals.get(name, 0) + 1
    return totals


def build_total_attendance_fs(df_fs, year=None):
    """Számítja az összgesített részvételi listát a Firestore DataFrame alapján.
    Alkalmas az átkonvertált legacy adatok és az új rekordok egységes kezelésére."""
    if df_fs is None or df_fs.empty:
        return {}
    status_by_name_date = {}
    for _, row in df_fs.iterrows():
        name = str(row["Név"]).strip() if pd.notna(row["Név"]) else ""
        is_coming = str(row["Jön-e"]).strip() if pd.notna(row["Jön-e"]) else ""
        if not name or is_coming not in {"Yes", "No"}:
            continue
        mode_val = str(row["Mód"]).strip().lower() if pd.notna(row["Mód"]) else "valós"
        if mode_val == "teszt":
            continue
        reg_val = str(row["Regisztráció Időpontja"]) if pd.notna(row["Regisztráció Időpontja"]) else ""
        evt_val = str(row["Alkalom Dátuma"]) if pd.notna(row["Alkalom Dátuma"]) else ""
        rec_date = parse_date_str(evt_val) or parse_date_str(reg_val)
        if rec_date is None:
            continue
        if year is not None and rec_date.year != year:
            continue
        key = (name, rec_date)
        status = status_by_name_date.setdefault(key, {"yes": False, "no": False})
        if is_coming == "Yes":
            status["yes"] = True
        else:
            status["no"] = True
    totals = {}
    for (name, _), status in status_by_name_date.items():
        if status["yes"] and not status["no"]:
            totals[name] = totals.get(name, 0) + 1
    return totals


def calculate_monthly_accounting_fs(fs_db, inv_dict):
    from modules.db import get_attendance_rows_fs, get_cancelled_sessions_fs
    target_year = int(inv_dict["target_year"])
    target_month = int(inv_dict["target_month"])
    target_month_name = inv_dict["month_name"]
    total_amount = float(inv_dict["amount"])
    all_tuesdays = get_tuesdays_in_month(target_year, target_month)
    cancelled_dates = get_cancelled_sessions_fs(fs_db)
    session_dates = [d for d in all_tuesdays if d not in cancelled_dates]
    if not session_dates:
        return False, f"Nincsenek érvényes edzésnapok {target_year}. {target_month_name} hónapban.", None, None, None, None
    cost_per_session = total_amount / len(session_dates)
    df_fs = get_attendance_rows_fs(fs_db)
    processed_att = []
    if not df_fs.empty:
        for _, row in df_fs.iterrows():
            name = str(row["Név"]).strip() if pd.notna(row["Név"]) else ""
            is_coming = str(row["Jön-e"]).strip() if pd.notna(row["Jön-e"]) else ""
            if not name or not is_coming:
                continue
            mode_val = str(row["Mód"]).strip().lower() if pd.notna(row["Mód"]) else "valós"
            if mode_val == "teszt":
                continue
            reg_val = str(row["Regisztráció Időpontja"]) if pd.notna(row["Regisztráció Időpontja"]) else ""
            evt_val = str(row["Alkalom Dátuma"]) if pd.notna(row["Alkalom Dátuma"]) else ""
            rel_date = parse_date_str(evt_val) or parse_date_str(reg_val)
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
                if rec["is_coming"] == "Yes":
                    yes_set.add(rec["name"])
                elif rec["is_coming"] == "No":
                    no_set.add(rec["name"])
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
    osszesito_data = [
        {"Név": n, "Részvétel száma": person_counts[n], "Fizetendő (Ft)": person_totals[n]}
        for n in sorted(person_totals.keys())
    ]
    return True, "Siker", pd.DataFrame(elszamolas_data), pd.DataFrame(osszesito_data), target_month_name, target_year


def bulk_calculate_settlements(fs_db, force_recalculate: bool = False) -> dict:
    """
    Az összes Firestore számlára elvégzi az elszámolás kalkulációt és menti az eredményt.

    Args:
        fs_db: Firestore adatbázis kapcsolat
        force_recalculate: Ha True, a már meglévő elszámolásokat is újraszámolja.
                           Ha False, csak a hiányzókat számolja ki.

    Returns:
        {
          "ok": [...],         # Sikeresen kiszámított hónapok listája
          "skipped": [...],    # Kihagyott hónapok (már léteztek)
          "failed": [...],     # Hibás hónapok
          "total": int
        }
    """
    from modules.db import get_invoices_fs, get_settlement_fs, save_settlement_fs
    from modules.utils import generate_pdf_bytes

    invoices = get_invoices_fs(fs_db)
    if not invoices:
        return {"ok": [], "skipped": [], "failed": [{"reason": "Nincsenek számlák a Firestore-ban."}], "total": 0}

    results = {"ok": [], "skipped": [], "failed": [], "total": len(invoices)}

    for inv in invoices:
        year = int(inv.get("target_year", 0))
        month_num = int(inv.get("target_month", 0))
        month_name = inv.get("month_name", f"{month_num}. hónap")
        label = f"{year}. {month_name}"

        if not force_recalculate:
            existing = get_settlement_fs(fs_db, year, month_num)
            if existing is not None:
                results["skipped"].append({"label": label, "year": year, "month_num": month_num})
                continue

        success, msg, df_elszamolas, df_osszesito, mn, yr = calculate_monthly_accounting_fs(fs_db, inv)
        if not success:
            results["failed"].append({"label": label, "year": year, "month_num": month_num, "reason": msg})
            continue

        ok, result = save_settlement_fs(fs_db, yr, month_num, mn, df_elszamolas, df_osszesito)
        if ok:
            results["ok"].append({
                "label": label, "year": year, "month_num": month_num,
                "people": len(df_osszesito),
                "total_ft": float(df_osszesito["Fizetendő (Ft)"].sum()) if not df_osszesito.empty else 0.0
            })
        else:
            results["failed"].append({"label": label, "year": year, "month_num": month_num, "reason": result})

    return results




def generate_pdf_bytes(df_osszesito, month_name, year):
    from fpdf import FPDF  # lazy: csak PDF generáláskor töltődik be
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


def _get_smtp_connection():
    import smtplib  # lazy: csak email küldéskor töltődik be
    try:
        sender = st.secrets["email"]["sender"]
        password = st.secrets["email"]["password"]
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender, password)
        return server, sender
    except Exception as e:
        raise Exception(f"SMTP kapcsolódási hiba: {e}")


def send_personal_email(to_address, name, month_name, year, count, amount, guest_details=None):
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    try:
        server, sender = _get_smtp_connection()
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Röpi App 🏐 <{sender}>"
        msg["To"] = to_address
        msg["Subject"] = f"🏐 Röpi elszámolás — {year}. {month_name}"
        keresztnev = name.split()[0]

        has_guests = bool(guest_details and guest_details.get("guests"))
        detail_rows = ""
        if has_guests:
            own_count = guest_details["own_count"]
            own_cost = guest_details["own_cost"]
            detail_rows += f"""<tr style="background:#f9f9f9;"><td style="padding:10px; color:#555;">👤 Saját részvétel</td><td style="padding:10px; text-align:right; color:#555;">{own_count} alkalom</td></tr>"""
            detail_rows += f"""<tr style="background:#f9f9f9;"><td style="padding:10px; color:#555;">👤 Saját díj</td><td style="padding:10px; text-align:right; color:#555;">{own_cost:,.0f} Ft</td></tr>"""
            for g in guest_details["guests"]:
                detail_rows += f"""<tr style="background:#fff8e1;"><td style="padding:10px; color:#8a6d00;">🧑‍🤝‍🧑 Vendég: {g['name']}</td><td style="padding:10px; text-align:right; color:#8a6d00;">{g['count']} alkalom</td></tr>"""
                detail_rows += f"""<tr style="background:#fff8e1;"><td style="padding:10px; color:#8a6d00;">💸 {g['name']} díja</td><td style="padding:10px; text-align:right; color:#8a6d00;">{g['cost']:,.0f} Ft</td></tr>"""

        html_body = f"""<html><body style="font-family: Arial, sans-serif; color: #333; max-width: 520px; margin: auto;">
          <div style="background: #f8f8f8; border-radius: 12px; padding: 28px;">
            <h2 style="color: #4a90d9; margin-top:0;">🏐 Havi Röpi Elszámolás</h2>
            <p>Szia <strong>{keresztnev}</strong>!</p>
            <p>Elkészült a <strong>{year}. {month_name}</strong> havi elszámolás.</p>
            <table style="width:100%; border-collapse: collapse; margin: 16px 0;">
              <tr style="background:#4a90d9; color:white;"><th style="padding:12px; text-align:left;">Megnevezés</th><th style="padding:12px; text-align:right;">Részlet</th></tr>
              {detail_rows}
              <tr style="background:#eaf4ff;"><td style="padding:12px;"><strong>📅 Összes részvétel</strong></td><td style="padding:12px; text-align:right;"><strong>{count} alkalom</strong></td></tr>
              <tr style="background:#fff;"><td style="padding:14px; font-size:1.1em;">💰 <strong>Fizetendő összeg</strong></td><td style="padding:14px; font-size:1.3em; text-align:right; color:#e74c3c;"><strong>{amount:,.0f} Ft</strong></td></tr>
            </table>
            {"<p style='color:#888; font-size:0.9em;'>ℹ️ A fizetendő összeg tartalmazza a vendégeid terembérleti díját is.</p>" if has_guests else ""}
            <p>Kérlek utald el a fenti összeget a szokásos számlaszámra! 🙏</p>
            <hr style="border:none; border-top:1px solid #ddd; margin:20px 0;">
            <p style="font-size:0.8em; color:#aaa; margin:0;">Ez egy automatikus üzenet — Röpi App Pro 🏐</p>
          </div></body></html>"""
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.warning(f"Email hiba ({to_address}): {e}")
        return False


def send_admin_summary_email(month_name, year, df_osszesito, pdf_bytes):
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    try:
        admin_email = st.secrets["email"]["admin_email"]
        server, sender = _get_smtp_connection()
        msg = MIMEMultipart()
        msg["From"] = f"Röpi App 🏐 <{sender}>"
        msg["To"] = admin_email
        msg["Subject"] = f"[Admin] 🏐 Teljes elszámolás — {year}. {month_name}"
        table_rows = ""
        for _, row in df_osszesito.iterrows():
            table_rows += f"""<tr><td style="padding:8px; border-bottom:1px solid #eee;">{row['Név']}</td><td style="padding:8px; text-align:center;">{row['Részvétel száma']}</td><td style="padding:8px; text-align:right; color:#e74c3c;"><strong>{row['Fizetendő (Ft)']:,.0f} Ft</strong></td></tr>"""
        total_sum = df_osszesito["Fizetendő (Ft)"].sum()
        html_body = f"""<html><body style="font-family: Arial, sans-serif; color: #333; max-width: 620px; margin: auto;">
          <div style="background: #f8f8f8; border-radius: 12px; padding: 28px;">
            <h2 style="color: #4a90d9; margin-top:0;">📊 Admin Összesítő — {year}. {month_name}</h2>
            <table style="width:100%; border-collapse: collapse;">
              <tr style="background:#4a90d9; color:white;"><th style="padding:10px; text-align:left;">Név</th><th style="padding:10px; text-align:center;">Részvétel</th><th style="padding:10px; text-align:right;">Fizetendő</th></tr>
              {table_rows}
              <tr style="background:#eaf4ff; font-weight:bold;"><td style="padding:10px;">ÖSSZESEN</td><td></td><td style="padding:10px; text-align:right; color:#4a90d9;">{total_sum:,.0f} Ft</td></tr>
            </table>
            <p style="margin-top:20px;">A részletes PDF csatolva. 📎</p>
            <hr style="border:none; border-top:1px solid #ddd; margin:20px 0;">
            <p style="font-size:0.8em; color:#aaa; margin:0;">Röpi App Pro — Admin értesítő 🏐</p>
          </div></body></html>"""
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        att = MIMEBase("application", "octet-stream")
        att.set_payload(pdf_bytes)
        encoders.encode_base64(att)
        att.add_header("Content-Disposition", "attachment", filename=f"Admin_Elszamolas_{year}_{month_name}.pdf")
        msg.attach(att)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Admin email hiba: {e}")
        return False


def parse_revolut_csv(uploaded_file):
    try:
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(uploaded_file, sep=",")
            if len(df.columns) < 3:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=";")
        except Exception:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=";")

        df.columns = [c.strip() for c in df.columns]

        leiras_col = next((c for c in df.columns if "leírás" in c.lower() or "leiras" in c.lower() or "description" in c.lower()), None)
        osszeg_col = next((c for c in df.columns if "összeg" in c.lower() or "osszeg" in c.lower() or "amount" in c.lower()), None)
        state_col  = next((c for c in df.columns if "state" in c.lower()), None)

        if not leiras_col or not osszeg_col:
            return None, f"Nem találom az oszlopokat. Talált oszlopok: {list(df.columns)}"

        if state_col:
            df = df[df[state_col].astype(str).str.upper() == "ELVÉGEZVE"].copy()

        df["_amount"] = pd.to_numeric(df[osszeg_col].astype(str).str.replace(",", "."), errors="coerce")

        incoming = df[
            (df["_amount"] > 0) &
            (df[leiras_col].astype(str).str.contains("tőle|tole|transfer from|from", case=False, na=False))
        ].copy()

        def extract_name(desc):
            desc = str(desc)
            for prefix in ["Átutalás tőle:", "Atutalas tole:", "Transfer from:", "From:"]:
                if prefix.lower() in desc.lower():
                    idx = desc.lower().index(prefix.lower()) + len(prefix)
                    return desc[idx:].strip()
            return desc.strip()

        incoming["_name"] = incoming[leiras_col].apply(extract_name)

        return incoming[["_name", "_amount"]].reset_index(drop=True), None

    except Exception as e:
        return None, f"Hiba a fájl feldolgozásakor: {e}"


def estimate_cost_for_player(session_count: int, year: int, avg_attendees: float | None = None) -> dict:
    """
    Becslés a játékos fizetendő összegéről egy adott évre.

    Kétféle módszert ad vissza:
    - 'precise': (óradíj × időtartam) / résztvevőszám × alkalmak
    - 'simple': alkalmak × 2300 Ft

    Args:
        session_count: Az adott évben volt alkalmak száma
        year: Az év (díjszabás meghatározásához)
        avg_attendees: Átlagos résztvevőszám (ha None, fix 12 fővel számol)

    Returns:
        {'precise': float, 'simple': float, 'hourly_rate': int,
         'duration': float, 'avg_attendees': float}
    """
    # Óradíj az év alapján
    hourly_rate = 14_000 if year <= 2024 else 16_000
    duration_hours = 1.5  # átlagos játékidő (óra)
    attendees = avg_attendees if avg_attendees and avg_attendees > 0 else 12.0

    cost_per_session_precise = (hourly_rate * duration_hours) / attendees
    precise = session_count * cost_per_session_precise
    simple = session_count * 2_300.0

    return {
        "precise": precise,
        "simple": simple,
        "hourly_rate": hourly_rate,
        "duration": duration_hours,
        "avg_attendees": attendees,
        "cost_per_session": cost_per_session_precise,
    }
