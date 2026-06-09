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
    "+", "{", "}", "[", "]", ":", ";", "<", ">", "?", ",", "-",
]
HARDCODED_BUSINESS_KEYWORDS = [
    "Parukeri", "Butiku", "Sukin", "Farmaci", "Spa", "Qender", "Sallon",
]
DEFAULT_SURNAMES = [
    "Golaj", "Gashi", "Krasniqi", "Berisha", "Hoxha",
    "Leka", "Prifti", "Dibra", "Marku", "Kola",
]

HARDCODED_RULES_SUMMARY = [
    "Ndarësit / - | \\ → mban pjesën majtas (para ndarësit)",
    "Për / → keep_first (p.sh. «Jonuz Muca / Web O» → «Jonuz Muca»)",
    "Heq simbolet: ! @ # $ % ^ & * ( ) _ + { } [ ] : ; < > ? , -",
    "Fjalë biznesi (Parukeri, Butiku, …) → «Biznes: [emri]»",
    "Pikë në emër (arlind.bikliqi) → Arlind Bikliqi",
    "Kapitalizon çdo fjalë",
    "Një fjalë pa mbiemër → shton mbiemër random nga lista juaj",
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
    if "." not in text:
        return text
    parts = [p.strip() for p in text.split(".") if p.strip()]
    if not parts:
        return text
    if all(" " not in p for p in parts):
        return " ".join(capitalize_word(p) for p in parts)
    return text


def build_symbol_pattern() -> re.Pattern:
    return re.compile("[" + re.escape("".join(HARDCODED_SYMBOLS)) + "]")


def clean_name_from_rules(value, rules: dict | None) -> str:
    surnames = get_surnames_from_settings(rules)

    if value is None:
        return ""
    try:
        import pandas as pd

        if isinstance(value, float) and pd.isna(value):
            return ""
    except ImportError:
        pass

    original = str(value).strip()
    if not original or original.lower() in ("nan", "none"):
        return ""

    if contains_business_keyword(original):
        return f"Biznes: {original}"

    text = apply_separators(original)
    text = apply_dot_split(text)
    text = build_symbol_pattern().sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    words = [capitalize_word(w) for w in text.split()]
    if len(words) == 1:
        if surnames:
            return f"{words[0]} {random.choice(surnames)}".strip()
        return words[0]
    return " ".join(words)
