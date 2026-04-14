import pytz

CREDENTIALS_FILE = 'credentials.json'
GSHEET_NAME = 'Attendance'
HUNGARY_TZ = pytz.timezone("Europe/Budapest")
FIRESTORE_COLLECTION = "attendance_records"
FIRESTORE_INVOICES = "invoices"
FIRESTORE_CANCELLED = "cancelled_sessions"
FIRESTORE_MEMBERS = "members"
MEMBERS_SHEET_NAME = "Tagok"
FIRESTORE_NAME_MAPPING = "revolut_name_mapping"
FIRESTORE_SETTLEMENTS = "settlements"
FIRESTORE_DEVICES = "device_registrations"
FIRESTORE_LEGACY = "legacy_attendance"
LEGACY_SHEET_NAME = "Legacy_Totals"
FIRESTORE_HISTORICAL = "historical_session_totals"
HISTORICAL_SHEET_NAME = "Old_Sessions_Totals"
TOLERANCE = 500  # Ft

MAIN_NAME_LIST = [
    "Anna Sengler", "Annamária Földváry", "Flóra", "Boti",
    "Csanád Laczkó", "Csenge Domokos", "Detti Szabó", "Dóri Békási",
    "Gergely Márki", "Márki Jancsi", "Kilyénfalvi Júlia", "Laura Piski",
    "Linda Antal", "Máté Lajer", "Nóri Sásdi", "Laci Márki",
    "Domokos Kadosa", "Áron Szabó", "Máté Plank", "Lea Plank", "Océane Olivier"
]
MAIN_NAME_LIST.sort()
PLUS_PEOPLE_COUNT = [str(i) for i in range(11)]

