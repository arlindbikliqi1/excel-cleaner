"""Persistence: settings.json për rregullat, SQLite për admins dhe historik."""
import json
import re
import sqlite3
from copy import deepcopy
from pathlib import Path

import pandas as pd
from werkzeug.security import check_password_hash, generate_password_hash

PASSWORD_HASH_METHOD = "pbkdf2:sha256"

from name_cleaning import DEFAULT_SURNAMES

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "excel_cleaner.db"
SETTINGS_PATH = BASE_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "business_categories": {
        "FASHIONA": ["tuta", "fustan", "fund", "pantolla", "komplet"],
        "Andrra Online": ["krem", "suplimente", "shampo"],
        "FLETA SHOP": ["suplimente", "krem", "sprej"],
        "INFINITYSHOP": ["suplimente", "krem", "aksesor"],
        "ARBI": ["bodi", "korset", "tekstil"],
        "Butiku Enisi": ["bluze", "fustan"],
        "LuxuryFashion": ["fustan", "pantolla", "veshje"],
        "Toponline": ["elektronike", "aksesor"],
        "ZONE": ["tekstil", "pajisje"],
    },
    "surnames": [
        "Bikliqi", "Gashi", "Krasniqi", "Berisha", "Hoxha",
        "Leka", "Prifti", "Dibra", "Marku", "Kola",
    ],
    "business_keywords": [
        "Parukeri", "Butiku", "Sukin", "Farmaci", "Spa", "Qender", "Sallon",
    ],
    "product_keywords": {
        "trenerka": "tuta",
        "spray": "suplimente",
        "sprej": "suplimente",
        "kr": "krem",
        "krem": "krem",
    },
    "name_cleaning_rules": None,
}


def _ensure_name_cleaning_rules(data: dict) -> dict:
    """Vetëm mbiemrat ruhen në settings; rregullat e tjera janë hardcoded."""
    rules = data.get("name_cleaning_rules")
    if not rules or not isinstance(rules, dict):
        rules = {}
    surnames = rules.get("surnames") or data.get("surnames") or list(DEFAULT_SURNAMES)
    data["name_cleaning_rules"] = {"surnames": list(surnames)}
    data["surnames"] = list(surnames)
    return data


def get_connection():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS processing_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT,
                output_filename TEXT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        admin = conn.execute(
            "SELECT id FROM admins WHERE username = ?", ("admin",)
        ).fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                ("admin", generate_password_hash("admin123", method=PASSWORD_HASH_METHOD)),
            )
        conn.commit()

    if not SETTINGS_PATH.exists():
        save_settings(deepcopy(DEFAULT_SETTINGS))


def admin_exists(username: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM admins WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
    return row is not None


def verify_admin(username: str, password: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM admins WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
    if not row:
        return False
    return check_password_hash(row["password_hash"], password)


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        save_settings(deepcopy(DEFAULT_SETTINGS))
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = deepcopy(DEFAULT_SETTINGS)
        save_settings(data)

    for key, default in DEFAULT_SETTINGS.items():
        if key not in data and default is not None:
            data[key] = deepcopy(default)
    _ensure_name_cleaning_rules(data)
    return data


def get_name_cleaning_rules() -> dict:
    return deepcopy(load_settings().get("name_cleaning_rules", {"surnames": DEFAULT_SURNAMES}))


def save_name_cleaning_rules(rules: dict):
    settings = load_settings()
    surnames = rules.get("surnames", DEFAULT_SURNAMES)
    settings["name_cleaning_rules"] = {"surnames": list(surnames)}
    settings["surnames"] = list(surnames)
    save_settings(settings)


def add_name_surname(surname: str):
    name = surname.strip()
    if not name:
        return
    rules = get_name_cleaning_rules()
    surnames = rules.setdefault("surnames", list(DEFAULT_SURNAMES))
    if name not in surnames:
        surnames.append(name)
    save_name_cleaning_rules(rules)


def remove_name_surname(surname: str):
    rules = get_name_cleaning_rules()
    rules["surnames"] = [s for s in rules.get("surnames", []) if s != surname]
    save_name_cleaning_rules(rules)


def save_settings(settings: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def normalize_business_name(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text).strip().lower())
    return cleaned.replace(".", " ")


def get_all_businesses() -> dict:
    return load_settings().get("business_categories", {})


def add_business(name: str, categories_list: list):
    settings = load_settings()
    biz = settings.setdefault("business_categories", {})
    biz[name.strip()] = [c.strip() for c in categories_list if str(c).strip()]
    save_settings(settings)


def delete_business(name: str):
    settings = load_settings()
    biz = settings.get("business_categories", {})
    key_to_delete = None
    target = normalize_business_name(name)
    for k in biz:
        if normalize_business_name(k) == target or k == name.strip():
            key_to_delete = k
            break
    if key_to_delete:
        del biz[key_to_delete]
        save_settings(settings)


def add_category_to_business(business_name: str, category: str):
    settings = load_settings()
    biz = settings.get("business_categories", {})
    cat = category.strip()
    if not cat:
        return
    for k, cats in biz.items():
        if normalize_business_name(k) == normalize_business_name(business_name) or k == business_name.strip():
            if cat not in cats:
                cats.append(cat)
            save_settings(settings)
            return
    add_business(business_name, [cat])


def remove_category_from_business(business_name: str, category: str):
    settings = load_settings()
    biz = settings.get("business_categories", {})
    cat = category.strip()
    for k, cats in list(biz.items()):
        if normalize_business_name(k) == normalize_business_name(business_name) or k == business_name.strip():
            biz[k] = [c for c in cats if c != cat]
            save_settings(settings)
            return


def _find_shitesi_column(df_raw: pd.DataFrame):
    shitesi_col = None
    data_start = 0
    for idx in range(min(10, len(df_raw))):
        row = df_raw.iloc[idx].astype(str).str.lower().str.strip()
        for col_idx, val in enumerate(row):
            if (
                "shites" in val
                or "shitës" in val
                or "shitesi" in val
                or "seller" in val
                or "dyqan" in val
                or "shop" in val
            ):
                shitesi_col = col_idx
        if shitesi_col is not None:
            data_start = idx + 1
            break
    return shitesi_col, data_start


SHITESI_HEADER_NAMES = frozenset(
    {"shitesi", "shitësi", "shites", "seller", "dyqan", "shop"}
)


def parse_shitesi_paste(text: str) -> list[str]:
    """Nxjerr emra unikë biznesesh nga teksti i ngjitur (kolona SHITESI nga Excel)."""
    if not text or not str(text).strip():
        return []

    unique_names = []
    seen = set()
    skipped_header = False

    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        name = parts[0] if parts else line
        if name.lower() in ("nan", "none", ""):
            continue
        norm = normalize_business_name(name)
        if not norm:
            continue
        if not skipped_header and norm in SHITESI_HEADER_NAMES:
            skipped_header = True
            continue
        if norm not in seen:
            seen.add(norm)
            unique_names.append(name)

    return unique_names


def analyze_businesses_from_text(text: str) -> dict:
    """
    Krahaso emrat e ngjitur me business_categories në settings.
    Kthen: known, unknown, all, error.
    """
    settings = load_settings()
    known_keys = {
        normalize_business_name(k) for k in settings.get("business_categories", {})
    }

    unique_names = parse_shitesi_paste(text)
    if not unique_names:
        return {
            "known": [],
            "unknown": [],
            "all": [],
            "error": "Nuk u gjet asnjë emër. Ngjis kolonën SHITESI nga Excel (Ctrl+C → Ctrl+V).",
        }

    known_display = []
    unknown_display = []
    for name in unique_names:
        if normalize_business_name(name) in known_keys:
            known_display.append(name)
        else:
            unknown_display.append(name)

    return {
        "known": sorted(known_display),
        "unknown": sorted(unknown_display),
        "all": sorted(unique_names),
        "error": None,
    }


def get_unknown_businesses_from_excel(filepath: str) -> dict:
    """
    Kthen: known (lista), unknown (lista), all (lista e unikeve nga Excel).
    """
    settings = load_settings()
    known_keys = {
        normalize_business_name(k) for k in settings.get("business_categories", {})
    }

    df_raw = pd.read_excel(filepath, header=None, engine="openpyxl")
    shitesi_col, data_start = _find_shitesi_column(df_raw)
    if shitesi_col is None:
        return {"known": [], "unknown": [], "all": [], "error": "Kolona SHITESI nuk u gjet."}

    lines = []
    for val in df_raw.iloc[data_start:, shitesi_col].dropna():
        name = str(val).strip()
        if name and name.lower() not in ("nan", "none"):
            lines.append(name)
    return analyze_businesses_from_text("\n".join(lines))


def log_job(original_filename: str, output_filename: str, row_count: int, created_by: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO processing_jobs
                (original_filename, output_filename, row_count, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (original_filename, output_filename, row_count, created_by),
        )
        conn.commit()


def list_jobs(limit: int = 50):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, original_filename, output_filename, row_count,
                   created_by, created_at
            FROM processing_jobs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
