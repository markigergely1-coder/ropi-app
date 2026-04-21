import pandas as pd
import numpy as np
from collections import Counter
from datetime import datetime as _dt

df = pd.read_excel('Röplabda jelenlét.xlsx', header=None)

player_cols = []
for c in range(1, len(df.columns)):
    cell = df.iloc[0, c]
    if pd.isna(cell):
        continue
    name = str(cell).strip()
    if name in ('', 'Plusz emberek száma'):
        continue
    player_cols.append((c, name))

records = []
skipped_rows = []
skipped_vals = set()

for r in range(1, len(df)):
    date_val = df.iloc[r, 0]
    if pd.isna(date_val):
        continue
    try:
        if hasattr(date_val, 'strftime'):
            date_str = date_val.strftime('%Y-%m-%d')
        else:
            date_str = _dt.strptime(str(date_val)[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
    except Exception:
        skipped_rows.append(f'Sor {r+1}: {repr(date_val)}')
        continue

    for col_idx, name in player_cols:
        cell_val = df.iloc[r, col_idx]
        if pd.isna(cell_val):
            continue
        val_str = str(cell_val).strip()

        if 'Jövök' in val_str or ':)' in val_str:
            is_coming = True
        elif 'Nem' in val_str or ':(' in val_str:
            is_coming = False
        else:
            try:
                num = float(val_str)
                is_coming = num >= 1
            except ValueError:
                skipped_vals.add(val_str)
                continue

        if is_coming:
            records.append({'name': name, 'date': date_str})

print(f'Kihagyott sorok (érvénytelen dátum): {skipped_rows}')
print(f'Kihagyott értékek (ismeretlen): {skipped_vals}')
print(f'Importálandó Yes rekordok: {len(records)}')
unique_dates = len(set(r['date'] for r in records))
print(f'Egyedi dátumok: {unique_dates}')
totals = Counter(r['name'] for r in records)
print()
for name, cnt in sorted(totals.items(), key=lambda x: -x[1]):
    print(f'  {name}: {cnt}')
