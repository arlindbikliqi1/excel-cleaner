from __future__ import annotations

"""Pastrimi i kolonës Pranuesi — rregullat strukturore janë të fiksuara në kod."""
import random
import re

# --- Rregulla të fiksuara (nuk ndryshohen nga UI) ---
HARDCODED_SEPARATORS = [
    {"char": "/", "position": "left"},
    {"char": "-", "position": "left"},
    {"char": "|", "position": "left"},
    {"char": "\\", "position": "left"},
]
HARDCODED_SLASH_RULE = "keep_first"
HARDCODED_SYMBOLS = [
    "!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "_",
    "+", "{", "}", "[", "]", ":", ";", "<", ">", "?", ",", "-", ".",
]
HARDCODED_BUSINESS_KEYWORDS = [
    "Parukeri", "Butiku", "Sukin", "Farmaci", "Spa", "Qender", "Sallon",
]
DEFAULT_SURNAMES = [
    "Golaj", "Gashi", "Krasniqi", "Berisha", "Hoxha",
    "Leka", "Prifti", "Dibra", "Marku", "Kola",
]
DEFAULT_FIRST_NAMES = [
    "Arlind", "Agron", "Besnik", "Driton", "Erion", "Fatmir", "Gent",
    "Ilir", "Jetmir", "Kujtim", "Lulzim", "Marigona", "Natasha", "Olta",
    "Pranvera", "Rozafa", "Valbona", "Adrian", "Blerta", "Elona",
    "Flutura", "Gentiana", "Hana", "Jonida", "Klara", "Liridon",
]

HARDCODED_RULES_SUMMARY = [
    "Ndarësit / - | \\ → mban pjesën majtas (para ndarësit)",
    "Për / → keep_first (p.sh. «Jonuz Muca / Web O» → «Jonuz Muca»)",
    "Heq simbolet: ! @ # $ % ^ & * ( ) _ + { } [ ] : ; < > ? , -",
    "Fjalë biznesi (Parukeri, Butiku, …) → «Biznes: [emri]»",
    "Pikë në emër (arlind.bikliqi) → Arlind Bikliqi",
    "Kapitalizon çdo fjalë",
    "Një fjalë pa mbiemër → shton mbiemër random nga lista juaj",
    "Vetëm numra / telefon → emër + mbiemër random",
]


def get_surnames_from_settings(rules: dict | None) -> list:
    if rules and rules.get("surnames"):
        return list(rules["surnames"])
    return list(DEFAULT_SURNAMES)


def capitalize_word(word: str) -> str:
    if not word:
        return word
    return word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper()


def contains_business_keyword(text: str) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in HARDCODED_BUSINESS_KEYWORDS)


def _separator_char(raw: str) -> str:
    if raw in (r"\\", "\\\\"):
        return "\\"
    return raw


def apply_slash_rule(text: str) -> str:
    if "/" not in text:
        return text
    parts = [p.strip() for p in text.split("/", 1)]
    if len(parts) < 2:
        return parts[0]
    return parts[0]


def apply_separators(text: str) -> str:
    handled_slash = False
    for item in HARDCODED_SEPARATORS:
        char = _separator_char(str(item.get("char", "")))
        if not char:
            continue
        if char == "/":
            if not handled_slash:
                text = apply_slash_rule(text)
                handled_slash = True
            continue
        if char not in text:
            continue
        parts = text.split(char, 1)
        text = parts[0].strip()
    if "/" in text and not handled_slash:
        text = apply_slash_rule(text)
    return text


def apply_dot_split(text: str) -> str:
    """Pikë vetëm për emra (arlind.bikliqi), jo numra (114.114)."""
    if "." not in text:
        return text
    parts = [p.strip() for p in text.split(".") if p.strip()]
    if not parts:
        return text
    if all(
        " " not in p and re.fullmatch(r"[a-zA-Zà-žÀ-ŽëËçÇ]+", p, re.IGNORECASE)
        for p in parts
    ):
        return " ".join(capitalize_word(p) for p in parts)
    return text


def _is_blank_value(value) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        if isinstance(value, float) and pd.isna(value):
            return True
    except ImportError:
        pass
    s = str(value).strip()
    return not s or s.lower() in ("nan", "none")


def _is_numeric_only_value(value) -> bool:
    """Numra, ID, telefona — zëvendësohen me emër + mbiemër random."""
    if value is None:
        return False
    try:
        import pandas as pd

        if isinstance(value, float) and pd.isna(value):
            return False
    except ImportError:
        pass
    if isinstance(value, (int, float)):
        return True

    s = str(value).strip()
    if not s:
        return False
    if re.fullmatch(r"\d+\.0+", s):
        return True

    compact = re.sub(r"[\s.\-+(),/\\|]", "", s)
    return compact.isdigit() and len(compact) >= 1


def _random_full_name(surnames: list) -> str:
    first = random.choice(DEFAULT_FIRST_NAMES)
    if not surnames:
        return first
    surname = random.choice(surnames)
    if len(surnames) > 1:
        attempts = 0
        while surname.lower() == first.lower() and attempts < 8:
            surname = random.choice(surnames)
            attempts += 1
    return f"{first} {surname}"


def _name_words(text: str) -> list[str]:
    """Fjalë të vlefshme emri — pa numra, simbole, pika."""
    words = []
    for raw in text.split():
        w = raw.strip(".")
        if not w or w.isdigit() or re.fullmatch(r"\d+\.?\d*", w):
            continue
        if not re.search(r"[a-zA-Zà-žÀ-Ž]", w):
            continue
        words.append(capitalize_word(w))
    return words


def build_symbol_pattern() -> re.Pattern:
    return re.compile("[" + re.escape("".join(HARDCODED_SYMBOLS)) + "]")


def clean_name_from_rules(value, rules: dict | None) -> str:
    surnames = get_surnames_from_settings(rules)

    if _is_blank_value(value):
        return ""

    if _is_numeric_only_value(value):
        return _random_full_name(surnames)

    original = str(value).strip()
    if contains_business_keyword(original):
        return f"Biznes: {original}"

    text = apply_separators(original)
    text = apply_dot_split(text)
    text = build_symbol_pattern().sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or _is_numeric_only_value(text):
        return _random_full_name(surnames)

    words = _name_words(text)
    if not words:
        return _random_full_name(surnames)
    if len(words) == 1:
        if surnames:
            return f"{words[0]} {random.choice(surnames)}".strip()
        return words[0]
    return " ".join(words)
