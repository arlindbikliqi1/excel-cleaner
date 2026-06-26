from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TRAINING_PATH = BASE_DIR / "data" / "product_training.json"

# Normalizon variante / typo nga lista DG
CATEGORY_CANONICAL = {
    "pastrues xhami": "pastrues gjamash",
    "pastrues gjamashi": "pastrues gjamash",
    "sulpimente": "suplimente",
    "jastak ortopedik": "jastek ortopedik",
    "drejtues shpine": "drejtuese per shpine",
    "aksesore vare": "aksesore varese",
    "aksesore varse": "aksesore varese",
    "shtrenguese gjuri": "shtrenguese per gjunje",
    "loder rosak": "loder rosaku",
    "aksesore ": "aksesore",
}

QTY_PREFIX = re.compile(
    r"^(\d+\s*)?(cop|cope|copë|pako|paketa|set|pal)\s+",
    re.IGNORECASE,
)


def normalize_product_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def norm_category(text: str) -> str:
    c = normalize_product_text(text).replace("ë", "e")
    return CATEGORY_CANONICAL.get(c, c)


def strip_product_noise(text: str) -> str:
    """Heq sasinë në fillim: «2 cop», «50 cop», «3cop» …"""
    t = normalize_product_text(text)
    prev = None
    while prev != t:
        prev = t
        t = QTY_PREFIX.sub("", t).strip()
        t = re.sub(r"^\d+\s+", "", t).strip()
    return t


def compact_text(text: str) -> str:
    return strip_product_noise(text).replace(" ", "")


def load_training_data() -> dict:
    if not TRAINING_PATH.exists():
        return {"pairs": [], "phrases": {}}
    with open(TRAINING_PATH, encoding="utf-8") as f:
        return json.load(f)


def _training_index(data: dict) -> tuple[dict[str, str], list[tuple[str, str]]]:
    exact: dict[str, str] = {}
    for item in data.get("pairs", []):
        src = item.get("source", "")
        cat = norm_category(item.get("category", ""))
        if not src or not cat:
            continue
        key = strip_product_noise(src)
        if key:
            exact[key] = cat
        full = normalize_product_text(src)
        if full:
            exact[full] = cat

    phrases = []
    for phrase, cat in data.get("phrases", {}).items():
        p = strip_product_noise(phrase)
        c = norm_category(cat)
        if p and c:
            phrases.append((p, c))
    phrases.sort(key=lambda x: len(x[0]), reverse=True)
    return exact, phrases


_CACHE: tuple[dict[str, str], list[tuple[str, str]]] | None = None


def _get_index() -> tuple[dict[str, str], list[tuple[str, str]]]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _training_index(load_training_data())
    return _CACHE


def reload_training_cache() -> None:
    global _CACHE
    _CACHE = None


def import_training_from_excel(path: Path | str) -> tuple[int, int]:
    """Lexon Excel referencë (emërtim → kategori) dhe përditëson product_training.json."""
    import pandas as pd
    from collections import Counter, defaultdict

    path = Path(path)
    df = pd.read_excel(path, header=None, engine="openpyxl")

    src_col, tgt_col = _detect_reference_columns(df)
    if src_col is None:
        raise ValueError("Nuk u gjet formati referencë (2 kolona: emërtim + kategori).")

    rows: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        src = row.iloc[src_col] if src_col < len(row) else None
        tgt = row.iloc[tgt_col] if tgt_col < len(row) else None
        if src is None or tgt is None:
            continue
        src_s = str(src).strip()
        tgt_s = str(tgt).strip()
        if not src_s or src_s.lower() in ("nan", "none"):
            continue
        if not tgt_s or tgt_s.lower() in ("nan", "none"):
            continue
        rows.append((src_s, norm_category(tgt_s)))

    if not rows:
        raise ValueError("Excel referencë nuk ka rreshta të vlefshëm.")

    votes: dict[str, Counter] = defaultdict(Counter)
    for src, cat in rows:
        key = strip_product_noise(src)
        if key:
            votes[key][cat] += 1

    exact = {k: c.most_common(1)[0][0] for k, c in votes.items()}
    phrases = dict(exact)
    for src, cat in rows:
        clean = strip_product_noise(src)
        if len(clean) >= 5:
            phrases[clean] = exact.get(clean, cat)

    existing = load_training_data()
    old_pairs = {(strip_product_noise(p["source"]), norm_category(p["category"])) for p in existing.get("pairs", [])}
    seen: set[str] = set()
    pairs = []
    for src, cat in rows:
        key = strip_product_noise(src)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"source": src, "category": exact[key]})

    for p in existing.get("pairs", []):
        key = strip_product_noise(p.get("source", ""))
        if key and key not in seen:
            seen.add(key)
            pairs.append(p)

    old_phrases = existing.get("phrases", {})
    merged_phrases = dict(old_phrases)
    merged_phrases.update(phrases)

    TRAINING_PATH.parent.mkdir(exist_ok=True)
    with open(TRAINING_PATH, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs, "phrases": merged_phrases}, f, ensure_ascii=False, indent=2)

    reload_training_cache()
    return len(rows), len(pairs)


def _detect_test_liste_columns(df) -> tuple[int | None, int | None]:
    """Test LISTE: Kodi | Pershkrimi | Kategori | Pako — trajnimi është kol. 1 → 2."""
    if df.shape[1] < 3:
        return None, None

    header = [str(df.iat[0, c]).strip().lower().replace("ë", "e") for c in range(min(4, df.shape[1]))]
    if any("pershkrimi" in h for h in header):
        desc_col = next((i for i, h in enumerate(header) if "pershkrimi" in h), 1)
        cat_col = desc_col + 1 if desc_col + 1 < df.shape[1] else 2
        return desc_col, cat_col

    code_rows = 0
    for row_idx in range(1, min(60, len(df))):
        c0 = str(df.iat[row_idx, 0]).strip()
        c1 = str(df.iat[row_idx, 1]).strip()
        c2 = str(df.iat[row_idx, 2]).strip() if df.shape[1] > 2 else ""
        if (
            re.match(r"^[\dA-Za-z\-]+$", c0)
            and len(c0) >= 6
            and len(c1) >= 3
            and len(c2) >= 2
            and len(c1) > len(c2)
            and c1.lower() not in ("nan", "none")
            and c2.lower() not in ("nan", "none")
        ):
            code_rows += 1
    if code_rows >= 10:
        return 1, 2
    return None, None


def _detect_reference_columns(df) -> tuple[int | None, int | None]:
    """Gjen 2 kolonat: majtas emërtim i gjatë, djathtas kategori e shkurtër."""
    test_cols = _detect_test_liste_columns(df)
    if test_cols[0] is not None:
        return test_cols

    best_count = 0
    best_src, best_tgt = None, None
    cols = df.shape[1]
    for src_col in range(cols):
        for tgt_col in range(cols):
            if src_col == tgt_col:
                continue
            count = 0
            for row_idx in range(len(df)):
                try:
                    s = str(df.iat[row_idx, src_col]).strip()
                    t = str(df.iat[row_idx, tgt_col]).strip()
                except Exception:
                    continue
                if s.lower() in ("nan", "none", "") or t.lower() in ("nan", "none", ""):
                    continue
                if len(s) >= 2 and len(t) >= 2 and len(s) >= len(t):
                    count += 1
            if count > best_count:
                best_count = count
                best_src, best_tgt = src_col, tgt_col
    if best_count < 8:
        return None, None
    return best_src, best_tgt


def is_reference_training_excel(df) -> bool:
    src, tgt = _detect_reference_columns(df)
    if src is None:
        return False
    scan = min(15, len(df))
    for row_idx in range(scan):
        for col_idx in range(df.shape[1]):
            val = str(df.iat[row_idx, col_idx]).strip().lower().replace("ë", "e")
            if val in ("shitesi", "shites", "seller", "dyqan") or val.startswith("shites"):
                return False
            if "pranues" in val or "pershkrim" in val or val in ("kodi", "pako"):
                return False
    return True


def match_training_category(product_name: str) -> str | None:
    """Kthen kategorinë nga lista DG (para mapimit te biznesi)."""
    cat, _ = match_training_category_with_mode(product_name)
    return cat


def match_training_category_with_mode(product_name: str) -> tuple[str | None, str]:
    """Kthen (kategori, 'exact'|'phrase'|'' )."""
    if not product_name:
        return None, ""

    exact, phrases = _get_index()
    normalized = normalize_product_text(product_name)
    stripped = strip_product_noise(product_name)

    for key in (stripped, normalized):
        if key in exact:
            return exact[key], "exact"

    compact = compact_text(product_name)
    for key, cat in exact.items():
        key_compact = compact_text(key)
        if len(key_compact) >= 6 and key_compact == compact:
            return cat, "exact"

    for phrase, cat in phrases:
        if phrase in stripped or phrase in normalized:
            return cat, "phrase"
        if len(phrase) >= 5 and phrase.replace(" ", "") in compact:
            return cat, "phrase"

    return None, ""
