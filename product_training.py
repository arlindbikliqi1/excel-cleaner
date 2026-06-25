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
