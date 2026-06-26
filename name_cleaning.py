from __future__ import annotations

"""Pastrimi i kolonës Pranuesi — rregullat strukturore janë të fiksuara në kod."""
import random
import re
import unicodedata

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
# Fjalë biznesi — vetëm si fjalë të plota (jo nën-varg, p.sh. «spa» në «spahiu»)
BUSINESS_TYPE_WORDS = frozenset({
    "parukeri", "butiku", "sukin", "farmaci", "spa", "qender", "sallon", "salon",
    "beaty", "beauty", "barber", "shop", "store", "dyqan", "klinike",
})
BIZNES_PREFIX_RE = re.compile(r"^(?:biznes\s*:\s*)+", re.IGNORECASE)
APOSTROPHE_PREFIX_RE = re.compile(
    r"^mi[\s''`´\u2018\u2019\u201B\u2032]+\s*",
    re.IGNORECASE,
)
PAREN_TAG_RE = re.compile(r"\s*\([A-Za-z]{1,4}\)")
TRAILING_GARBAGE_RE = re.compile(r"\s+[A-Za-z]{1,2}$")
# Etiketa kanalesh / mbetje (IG, Fl, FB, …) — jo emra
GARBAGE_NAME_TOKENS = frozenset({
    "ig", "fb", "fl", "tt", "yt", "sc", "dm", "nf", "in", "tw", "ok", "id",
    "xl", "xs", "eu", "uk", "us", "ig", "igj", "web", "www", "com",
})
# Etiketa nga formularët / Excel (Emri, Mbiemri, …) — jo pjesë e emrit
NAME_LABEL_TOKENS = frozenset({
    "emri", "emer", "emër", "name", "firstname", "first", "emra",
    "mbiemri", "mbiemer", "mbiemei", "mbiemer", "surname", "lastname", "last",
    "klienti", "klient", "pranuesi", "pranues", "customer", "client",
})
LEADING_NOISE_WORDS = frozenset({"la", "ti", "te"})
MI_PREFIX_TOKEN_RE = re.compile(
    r"^mi[\s''`´\u2018\u2019\u201B\u2032]*$",
    re.IGNORECASE,
)
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
    "Heq simbolet: ! @ # $ % ^ & * ( ) _ + { } [ ] : ; < > ? ,",
    "Heq shkronja të vetme (A, B, …) — p.sh. «Arlind Bikliqi A» → «Arlind Bikliqi»",
    "Heq mbetje numrash+shkronjash (16z, 7z) — p.sh. «Imelda 16z» → «Imelda [mbiemër]»",
    "Ndan emra të bashkuar — p.sh. «Enkelejdafejzulla Kinaj» → «Enkelejda Fejzulla Kinaj»",
    "Heq përsëritje emër/mbiemër — «Denis Denis Berati Berati» → «Denis Berati»",
    "Heq etiketat Emri/Mbiemri dhe dy emra të bashkuar — «La Ti Emri Taulant Mbiemei» → «Taulant …»",
    "Heq fjalë biznesi (Sallon, Salon, …) kur pas tyre vjen emër personi",
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


def _strip_business_type_prefix(words: list[str]) -> list[str]:
    """Heq fjalët e biznesit në fillim — «Sallon miranda» → «miranda»."""
    out = list(words)
    while out and out[0].lower() in BUSINESS_TYPE_WORDS:
        out.pop(0)
    return out


def _normalize_unicode_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _is_label_token(word: str) -> bool:
    return word.strip().lower().replace("ë", "e") in NAME_LABEL_TOKENS


def _is_garbage_name_token(word: str) -> bool:
    """Etiketa si IG, Fl, FB — jo pjesë e emrit."""
    w = word.strip(".'\"`´'’“”").lower()
    if not w:
        return True
    if _is_label_token(w):
        return True
    if w in GARBAGE_NAME_TOKENS:
        return True
    if len(w) == 1 and w.isalpha():
        return True
    if MI_PREFIX_TOKEN_RE.fullmatch(w):
        return True
    # Dy shkronja të kodeve (IG, FL, FB)
    if len(w) == 2 and w.isalpha() and w.upper() == w:
        return True
    return False


def _strip_edge_garbage_tokens(words: list[str]) -> list[str]:
    out = list(words)
    while out and _is_garbage_name_token(out[0]):
        out.pop(0)
    while out and _is_garbage_name_token(out[-1]):
        out.pop()
    return out


def _strip_trailing_garbage_text(text: str) -> str:
    """Heq përsëri etiketat në fund (IG, Fl, A, …) derisa të stabilizohet."""
    prev = None
    current = text.strip()
    while prev != current:
        prev = current
        current = TRAILING_GARBAGE_RE.sub("", current).strip()
        words = current.split()
        words = _strip_edge_garbage_tokens(words)
        current = " ".join(words)
    return current


def _strip_name_prefix_noise(text: str) -> str:
    text = BIZNES_PREFIX_RE.sub("", text.strip())
    text = APOSTROPHE_PREFIX_RE.sub("", text.strip())
    return text.strip()


def _separator_char(raw: str) -> str:
    if raw in (r"\\", "\\\\"):
        return "\\"
    return raw


def apply_slash_rule(text: str) -> str:
    """Mban pjesën majtas; nëse majtas 1 emër dhe djathtas mbiemër → bashkon."""
    for sep in ("/", "\\", "|"):
        if sep not in text:
            continue
        left, right = text.split(sep, 1)
        left = left.strip()
        right = right.strip()
        if not right:
            return left
        left_words = [
            w for w in left.split()
            if w and re.search(r"[a-zA-Zà-žÀ-Ž]", w) and not w.isdigit()
        ]
        right_words = [
            w for w in right.split()
            if w and re.search(r"[a-zA-Zà-žÀ-Ž]", w) and not w.isdigit()
        ]
        if len(left_words) == 1 and right_words:
            return f"{left_words[0]} {right_words[0]}"
        return left
    return text.strip()


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


def _is_valid_name_word(word: str) -> bool:
    """Fjalë e vlefshme emri/mbiemri — jo numra, jo 16z/7z, jo shkronja të vetme."""
    w = word.strip(".")
    if _is_garbage_name_token(w):
        return False
    if not w or w.isdigit() or re.fullmatch(r"\d+\.?\d*", w):
        return False
    if len(w) == 1 and re.fullmatch(r"[a-zA-Zà-žÀ-ŽëËçÇ]", w):
        return False
    # 16z, 7z, 3a — mbetje nga Excel/ID
    if re.fullmatch(r"\d+[a-zA-Z]{1,4}", w):
        return False
    if re.search(r"\d", w):
        return False
    if not re.search(r"[a-zA-Zà-žÀ-Ž]", w):
        return False
    return True


def _build_name_vocab(rules: dict | None) -> set[str]:
    vocab: set[str] = set()
    for name in DEFAULT_FIRST_NAMES + DEFAULT_SURNAMES:
        vocab.add(name.lower())
    for s in get_surnames_from_settings(rules):
        vocab.add(str(s).lower())
    return vocab


def _score_name_segment(seg: str, vocab: set[str]) -> int:
    if len(seg) < 4:
        return -100
    if len(seg) < 6:
        score = len(seg) - 3
    else:
        score = min(len(seg), 12) + 4
    if seg in vocab:
        score += 30
    if seg[-1] in "aeiouë":
        score += 1
    return score


def _dp_split_fused(word: str, vocab: set[str]) -> list[str]:
    """Ndaj fjalë të gjata të bashkuara (p.sh. enkelejdafejzulla)."""
    w = word.lower()
    n = len(w)
    if n < 11:
        return [word]

    best_parts: list[str] | None = None
    best_score = -1
    best_balance = -1

    def consider(parts: list[str]) -> None:
        nonlocal best_parts, best_score, best_balance
        if any(len(p) < 5 for p in parts):
            return
        score = sum(_score_name_segment(p, vocab) for p in parts)
        if len(parts) == 2:
            score += 6
        balance = min(len(p) for p in parts)
        if score > best_score or (
            score == best_score and balance > best_balance
        ):
            best_score = score
            best_balance = balance
            best_parts = parts

    for i in range(5, n - 4):
        consider([w[:i], w[i:]])

    for i in range(5, n - 9):
        for j in range(i + 5, n - 4):
            consider([w[:i], w[i:j], w[j:]])

    if best_parts and best_score >= 16:
        return best_parts
    return [word]


def _split_camel_case(word: str) -> list[str]:
    parts = re.findall(r"[A-Z]?[a-zà-žëË]+|[A-Z]{2,}(?![a-z])", word)
    if len(parts) > 1:
        return [p for p in parts if len(p) >= 2]
    return []


def _greedy_vocab_split(word: str, vocab: set[str]) -> list[str]:
    w = word.lower()
    parts: list[str] = []
    i = 0
    while i < len(w):
        found = None
        for size in range(min(18, len(w) - i), 2, -1):
            chunk = w[i : i + size]
            if chunk in vocab:
                found = chunk
                break
        if found:
            parts.append(found)
            i += len(found)
        else:
            break
    if parts and i == len(w):
        return parts
    return []


def _split_fused_name_word(word: str, vocab: set[str]) -> list[str]:
    camel = _split_camel_case(word)
    if len(camel) > 1:
        return [capitalize_word(p) for p in camel]

    w_lower = word.lower()
    if len(w_lower) <= 10 and w_lower in vocab:
        return [capitalize_word(word)]

    greedy = _greedy_vocab_split(word, vocab)
    if len(greedy) > 1:
        return [capitalize_word(p) for p in greedy]

    if len(w_lower) >= 11:
        dp_parts = _dp_split_fused(word, vocab)
        if len(dp_parts) > 1:
            return [capitalize_word(p) for p in dp_parts]

    return [capitalize_word(word)]


def _expand_name_tokens(text: str, rules: dict | None) -> list[str]:
    """Ndan fjalë të bashkuara para filtrimit final."""
    vocab = _build_name_vocab(rules)
    tokens: list[str] = []
    for raw in text.split():
        w = raw.strip(".")
        if _is_garbage_name_token(w) or MI_PREFIX_TOKEN_RE.fullmatch(w.strip(".'\"`´'’")):
            continue
        if not _is_valid_name_word(w):
            continue
        if len(w) > 10 or (len(w) > 7 and w.lower() not in vocab):
            tokens.extend(_split_fused_name_word(w, vocab))
        else:
            tokens.append(capitalize_word(w))
    return tokens


def _name_words(text: str, rules: dict | None = None) -> list[str]:
    """Fjalë të vlefshme emri — ndan edhe emra të bashkuar."""
    return _expand_name_tokens(text, rules)


def build_symbol_pattern() -> re.Pattern:
    return re.compile("[" + re.escape("".join(HARDCODED_SYMBOLS)) + "]")


def clean_name_from_rules(value, rules: dict | None) -> str:
    surnames = get_surnames_from_settings(rules)

    if _is_blank_value(value):
        return ""

    if _is_numeric_only_value(value):
        return _random_full_name(surnames)

    original = _strip_name_prefix_noise(_normalize_unicode_text(str(value).strip()))

    text = apply_separators(original)
    text = PAREN_TAG_RE.sub(" ", text)
    text = apply_dot_split(text)
    text = build_symbol_pattern().sub(" ", text)
    text = re.sub(r"\s*/\s*", " ", text)
    text = _strip_trailing_garbage_text(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or _is_numeric_only_value(text):
        return _random_full_name(surnames)

    raw_tokens = _name_words(text, rules)
    words = _finalize_name_words(raw_tokens)
    if not words:
        return _random_full_name(surnames)
    if len(words) == 1:
        if surnames:
            return f"{words[0]} {random.choice(surnames)}".strip()
        return words[0]
    return " ".join(words)


def _collapse_consecutive_duplicates(words: list[str]) -> list[str]:
    """«Denis Denis Berati» → «Denis Berati»."""
    if not words:
        return words
    out = [words[0]]
    for w in words[1:]:
        if w.lower() != out[-1].lower():
            out.append(w)
    return out


def _dedupe_repeated_halves(words: list[str]) -> list[str]:
    """«Arlind Bikliqi Arlind Bikliqi» → «Arlind Bikliqi»."""
    n = len(words)
    if n >= 2 and n % 2 == 0:
        mid = n // 2
        if [w.lower() for w in words[:mid]] == [w.lower() for w in words[mid:]]:
            return words[:mid]
    return words


def _dedupe_name_tokens(words: list[str]) -> list[str]:
    """Heq emra/mbiemra të përsëritur në sequence."""
    prev = None
    current = list(words)
    while prev != current:
        prev = current
        current = _collapse_consecutive_duplicates(current)
        current = _dedupe_repeated_halves(current)
    return current


def _strip_leading_noise_words(words: list[str]) -> list[str]:
    """«La Ti Taulant» → «Taulant»."""
    out = list(words)
    while out and out[0].lower() in LEADING_NOISE_WORDS and len(out) > 1:
        out.pop(0)
    return out


def _strip_name_label_tokens(words: list[str]) -> list[str]:
    return [w for w in words if not _is_label_token(w)]


def _keep_first_name_pair(words: list[str]) -> list[str]:
    """
    «Xhensila Gjergji Mirake Vindado» → «Xhensila Gjergji».
    Dy çifte emër+mbiemër të bashkuara — mban vetëm të parin.
    """
    n = len(words)
    if n == 4:
        return words[:2]
    if n >= 6 and n % 2 == 0:
        return words[:2]
    return words


def _finalize_name_words(raw_tokens: list[str]) -> list[str]:
    words = _strip_business_type_prefix([w.lower() for w in raw_tokens])
    words = [capitalize_word(w) for w in words if _is_valid_name_word(w)]
    words = _strip_leading_noise_words(words)
    words = _strip_name_label_tokens(words)
    words = _dedupe_name_tokens(words)
    words = _keep_first_name_pair(words)
    return _strip_edge_garbage_tokens(words)
