# Excel Cleaner System

Aplikacion Flask me sidebar për transformimin e Excel-it (Pranuesi, Produkti nga SHITESI).

## Struktura

```
excel-cleaner/
├── app.py
├── database.py
├── settings.json          # biznese, kategori, mbiemra, fallback keywords
├── requirements.txt
├── templates/
│   ├── base.html          # sidebar
│   ├── login.html
│   ├── dashboard.html
│   ├── businesses.html
│   └── history.html
├── uploads/
├── downloads/
└── data/excel_cleaner.db  # admins + historiku
```

## Login

http://127.0.0.1:5000 — **admin** / **admin123**

## Funksionaliteti

- **Dashboard:** upload Excel → preview i plotë → shkarkim
- **Bizneset:** menaxhim biznesesh/kategorish + analizë SHITESI (ngjit kolonën nga Excel)
- **Historiku:** përpunimet e mëparshme

## Produkti

1. Lexohet **SHITESI** → zgjedhet random një kategori nga `business_categories[biznesi]`
2. Nëse biznesi mungon ose nuk ka kategori → **pattern matching** (`product_keywords` në settings.json)

## Nisja

**Mac / Linux:**
```bash
./import_reference.sh   # herën e parë ose kur shtoni listë të re Excel
./start.sh
```

**Windows (CMD ose PowerShell):**
```bat
import_reference.bat
start.bat
```

**Mac (manual):**
```bash
venv/bin/python3 scripts/import_cleaned_reference.py
./start.sh
```

> Excel-et referencë (`LINDI LISTA DOGANA.xlsx`, `LINDI DOGANA 2/3/5.xlsx`) duhen kopjuar në `uploads/` — nuk janë në git.

Ose manualisht:
```bash
cd excel-cleaner
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
