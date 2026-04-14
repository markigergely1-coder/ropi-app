import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.db import get_gsheet_connection

client = get_gsheet_connection()
if not client:
    print("Could not connect to GSheet.")
    sys.exit()

try:
    ss = client.open("röplabda jelenlét")
    ws = ss.sheet1
    vals = ws.get_all_values()
    print(f"Success! Found {len(vals)} rows.")
    if len(vals) > 0:
        print("Header row preview (Cols A..Y):")
        # Col A is index 0, Col Y is index 24
        print(f"Col A: {vals[0][0] if len(vals[0]) > 0 else 'N/A'}")
        print(f"Col Y: {vals[0][24] if len(vals[0]) > 24 else 'N/A'}")
        
    print("First data row preview:")
    if len(vals) > 1:
         print(f"Col A: {vals[1][0] if len(vals[1]) > 0 else 'N/A'}")
         print(f"Col Y: {vals[1][24] if len(vals[1]) > 24 else 'N/A'}")
         
except Exception as e:
    print(f"Error opening sheet: {e}")
    # Let's list some available files
    files = client.listall()
    print("Available spreadsheets:")
    for f in files:
        print("-", f['name'])
