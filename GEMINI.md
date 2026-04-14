# Project Context: ropi-app

## Áttekintés
Ez egy tagnyilvántartó és pénzügyi kezelő alkalmazás (valószínűleg sportegyesület vagy klub számára). Az alkalmazás lehetővé teszi a tagok kezelését, befizetések követését és QR-kódos check-in rendszert használ.

## Technológiai Stack
- **Nyelv:** Python 3.x
- **Keretrendszer:** Streamlit (a `modules/pages` struktúra alapján)
- **Adatbázis:** SQLite/PostgreSQL (kezelése: `modules/db.py`)
- **UI:** Custom HTML sablonok (`checkin.html`) és Roboto betűtípusok.

## Mappaszerkezet és Logika
- `app.py`: Az alkalmazás fő belépési pontja.
- `modules/`: Itt található a logika magja.
    - `db.py`: Adatbázis műveletek (lekérések, mentések).
    - `config.py`: Beállítások kezelése.
    - `utils.py`: Segédfüggvények (pl. formázás, számítások).
- `modules/pages/`: A különálló menüpontok logikája (Accounting, Admin, Members, Payments, QR, Settings).

## Szabályok a Gemini Agent számára
1. **Nyelv:** A változtatásokról szóló magyarázatokat és a commit üzeneteket mindig **magyarul** írd.
2. **Commit stílus:** Használj konvencionális commit jelöléseket (pl. `feat:`, `fix:`, `docs:`).
3. **Kódstílus:** Törekedj a tiszta, modularizált Python kódra. Ha módosítasz egy oldalt a `pages` mappában, ellenőrizd, hogy szükséges-e módosítás a `db.py`-ban is.
4. **Biztonság:** Az adatbázis kapcsolatokat és titkos kulcsokat mindig a `config.py`-on keresztül kezeld.

## Gyakori feladatok
- Új admin funkciók hozzáadása a `modules/pages/admin.py`-hoz.
- Statisztikák bővítése az `overview.py`-ban.
- QR-kód generálás logikájának finomítása a `qr_page.py`-ban.