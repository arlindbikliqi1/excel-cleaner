from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
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
    "fust": "bluze",
    "fustan": "bluze",
    "fustana": "bluze",
    "fustane": "bluze",
    "fustanin": "bluze",
    "fustanet": "bluze",
}

QTY_PREFIX = re.compile(
    r"^(\d+\s*)?(cop|cope|copë|pako|paketa|set|pal)\s+",
    re.IGNORECASE,
)

# Shkurtesa / fjalë të parregullta → forma e plotë (nga lista referencë)
WORD_TOKEN_ALIASES = {
    "tekstild": "tekstil",
    "teksitl": "tekstil",
    "teksil": "tekstil",
    "fustn": "fustan",
    "fustna": "fustan",
    "fusana": "fustan",
    "fuatane": "fustan",
    "fustani": "fustan",
    "pantoll": "pantollona",
    "pantolla": "pantollona",
    "trenerke": "trenerka",
    "trenerkat": "trenerka",
    "pigjam": "pigjama",
    "pigjama": "pigjama",
    "bluza": "bluze",
    "bluzat": "bluze",
    "arom": "aromatizues",
    "aromat": "aromatizues",
    "det": "detergjent",
    "cop": "copa",
    "caf": "cafe",
    "col": "cola",
    "bir": "birra",
    "fan": "fanta",
    "fru": "fruta",
    "art": "artikull",
    "artiku": "artikull",
    "triciklet": "paisje per ushtrime",
}


def normalize_product_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def expand_product_word_aliases(text: str) -> str:
    """Zëvendëson shkurtesa të njohura në nivel fjale."""
    parts = []
    for raw in str(text).split():
        w = raw.strip(".,;:/\\|")
        if not w:
            continue
        low = w.lower().replace("ë", "e")
        parts.append(WORD_TOKEN_ALIASES.get(low, w))
    return " ".join(parts) if parts else str(text).strip()


def norm_category(text: str) -> str:
    c = normalize_product_text(text).replace("ë", "e")
    return CATEGORY_CANONICAL.get(c, c)


MODEL_CODE_RE = re.compile(r"\b[a-z]{1,4}[-_]?\d{3,}[a-z0-9]*\b", re.IGNORECASE)


def get_category_display(norm_cat: str) -> str:
    """Forma e shfaqjes së kategorisë (si kolona C e Excel-it)."""
    if not norm_cat:
        return norm_cat
    data = load_training_data()
    labels = data.get("category_labels") or {}
    norm = norm_category(norm_cat)
    return labels.get(norm, str(norm_cat).strip())


def _pick_category_winner(votes: Counter) -> str:
    """Zgjedh kategori nga votat; barazim → kategoria më specifike (më e gjatë)."""
    if not votes:
        return ""
    ranked = votes.most_common()
    top_count = ranked[0][1]
    tied = [cat for cat, count in ranked if count == top_count]
    if len(tied) == 1:
        return tied[0]
    return max(tied, key=len)


def _model_stripped_key(text: str) -> str:
    """Heq kode modeli (sf-9134, dh-4006) për përputhje të afërt."""
    t = normalize_product_text(strip_product_noise(expand_product_word_aliases(text)))
    t = MODEL_CODE_RE.sub(" ", t)
    t = re.sub(r"\b\d+\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


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
    t = strip_product_noise(text).replace(" ", "")
    return t.replace("-", "").replace("_", "")


def _split_model_token(token: str) -> list[str]:
    """Ndaj kode si sf9134 → sf + 9134 (variante pa vizë/hapësirë)."""
    match = re.fullmatch(r"([a-z]{1,4})(\d{3,}[a-z0-9]*)", token, re.IGNORECASE)
    if match:
        return [match.group(1).lower(), match.group(2).lower()]
    return [token]


def _search_tokens(text: str) -> list[str]:
    """Tokena stabilë për variante pikësimi, aksentesh dhe rendi fjalësh."""
    expanded = expand_product_word_aliases(text)
    normalized = unicodedata.normalize("NFKD", strip_product_noise(expanded))
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    raw = re.findall(r"[a-z0-9]+", ascii_text.lower())
    tokens: list[str] = []
    for token in raw:
        tokens.extend(_split_model_token(token))
    return tokens


def _search_signature(text: str) -> str:
    """I njëjti produkt me rend tjetër fjalësh merr të njëjtën nënshkrim."""
    return " ".join(sorted(_search_tokens(text)))


def _fuzzy_training_match(
    product_name: str, exact: dict[str, str]
) -> tuple[str | None, str]:
    """
    Gjen variante me typo të vogla. Kthen rezultat vetëm me prag të lartë dhe
    kur kategoria fituese ndahet qartë nga kategori të tjera.
    """
    query_tokens = _search_tokens(product_name)
    if not query_tokens:
        return None, ""
    query_signature = " ".join(sorted(query_tokens))
    query_compact = "".join(query_tokens)
    if len(query_compact) < 5:
        return None, ""

    # Rend tjetër fjalësh / pikësim tjetër: përputhje e sigurt pa fuzzy.
    signature_hits = [
        (key, cat)
        for key, cat in exact.items()
        if _search_signature(key) == query_signature
    ]
    signature_categories = {cat for _, cat in signature_hits}
    if len(signature_categories) == 1:
        return next(iter(signature_categories)), "signature"
    if len(signature_categories) > 1:
        # Kontradiktë në trajnim: kërko shumicë të qartë, përndryshe mos gjej.
        votes = Counter(cat for _, cat in signature_hits)
        top_cat, top_n = votes.most_common(1)[0]
        second_n = votes.most_common(2)[1][1] if len(votes) > 1 else 0
        if top_n >= 2 and top_n > second_n:
            return top_cat, "signature"
        return None, ""

    best_by_category: dict[str, float] = {}
    for key, cat in exact.items():
        key_tokens = _search_tokens(key)
        if not key_tokens:
            continue
        key_compact = "".join(key_tokens)
        # Gjatësi shumë të ndryshme zakonisht janë produkte të ndryshme.
        length_ratio = min(len(query_compact), len(key_compact)) / max(
            len(query_compact), len(key_compact)
        )
        if length_ratio < 0.72:
            continue

        query_set, key_set = set(query_tokens), set(key_tokens)
        overlap = query_set & key_set
        token_score = len(overlap) / max(len(query_set | key_set), 1)
        # Multi-token: kërko overlap real. Single-token: lëri pragun e lartë.
        if len(query_tokens) >= 2 and len(overlap) < 2 and token_score < 0.5:
            continue

        char_score = SequenceMatcher(None, query_compact, key_compact).ratio()
        sorted_score = SequenceMatcher(
            None, query_signature, " ".join(sorted(key_tokens))
        ).ratio()
        score = max(char_score, sorted_score, 0.55 * sorted_score + 0.45 * token_score)
        if score > best_by_category.get(cat, 0.0):
            best_by_category[cat] = score

    if not best_by_category:
        return None, ""
    ranked = sorted(best_by_category.items(), key=lambda item: item[1], reverse=True)
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    threshold = 0.94 if len(query_compact) < 8 else 0.88
    if best_score >= threshold and best_score - second_score >= 0.06:
        return best_cat, "fuzzy"
    return None, ""


def _phrase_matches_query(phrase: str, query: str) -> bool:
    """Përputhje fraze me kufij tokenash — jo substring i pasigurt."""
    phrase_tokens = set(_search_tokens(phrase))
    if not phrase_tokens:
        return False
    query_tokens = set(_search_tokens(query))
    if not phrase_tokens.issubset(query_tokens):
        return False
    # Bag i plotë = signature/exact; phrase vetëm për nënvarg të vërtetë.
    if phrase_tokens == query_tokens:
        return False
    content = [t for t in phrase_tokens if len(t) >= 4]
    if content:
        return True
    phrase_compact = "".join(phrase_tokens)
    return len(phrase_tokens) >= 2 and len(phrase_compact) >= 10


_TOKEN_MODEL_STOPWORDS = frozenset(
    {
        "cope", "copa", "cop", "pako", "paketa", "masa", "model", "kodi",
        "ngjyra", "foto", "eshte", "jane", "dhe", "edhe", "nga", "per", "me",
        "nje", "dy", "set", "pal", "tekstil", "artikull", "produkt",
        "bardhe", "bardh", "zeze", "zi", "kuqe", "blu", "jeshile", "bezhe",
        "roze", "kafe", "gri", "verdh", "portokalli",
        "small", "medium", "large",
    }
)


def _business_token_training_match(
    product_name: str, exact: dict[str, str]
) -> tuple[str | None, str]:
    """
    Për emërtime të reja, përdor fjalë dalluese që janë parë të paktën dy herë
    me të njëjtën kategori te i njëjti biznes. Fjalët e përgjithshme përjashtohen.
    """
    query_tokens = {
        token
        for token in _search_tokens(product_name)
        if len(token) >= 4
        and not any(ch.isdigit() for ch in token)
        and token not in _TOKEN_MODEL_STOPWORDS
    }
    if not query_tokens:
        return None, ""

    token_votes: dict[str, Counter] = {}
    seen_examples: set[tuple[str, str]] = set()
    for key, cat in exact.items():
        signature = _search_signature(key)
        example = (signature, cat)
        if not signature or example in seen_examples:
            continue
        seen_examples.add(example)
        for token in set(_search_tokens(key)):
            if (
                len(token) >= 4
                and not any(ch.isdigit() for ch in token)
                and token not in _TOKEN_MODEL_STOPWORDS
            ):
                token_votes.setdefault(token, Counter())[cat] += 1

    scores: Counter = Counter()
    evidence: Counter = Counter()
    for token in query_tokens:
        counts = token_votes.get(token)
        if not counts:
            continue
        cat, top_count = counts.most_common(1)[0]
        total = sum(counts.values())
        purity = top_count / total
        if top_count >= 2 and purity >= 0.85:
            scores[cat] += 1.0 + min(top_count, 5) * 0.2
            evidence[cat] += 1

    if not scores:
        return None, ""
    ranked = scores.most_common()
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if evidence[best_cat] >= 1 and best_score - second_score >= 0.8:
        return best_cat, "token"
    return None, ""


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
_BIZ_CACHE: dict[str, dict[str, str]] | None = None
_REF_TOKEN_INDEX: dict[str, list[str]] | None = None
_TRAINING_MTIME: float | None = None


def _training_file_mtime() -> float:
    try:
        return TRAINING_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _ensure_training_fresh() -> None:
    """Rifreskon cache kur product_training.json ndryshon (pas importit)."""
    global _CACHE, _BIZ_CACHE, _REF_TOKEN_INDEX, _TRAINING_MTIME
    mtime = _training_file_mtime()
    if _CACHE is not None and _TRAINING_MTIME == mtime:
        return
    _CACHE = None
    _BIZ_CACHE = None
    _REF_TOKEN_INDEX = None
    _TRAINING_MTIME = mtime


def _normalize_business_key(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(name).strip().lower())
    return cleaned.replace(".", " ")


def _business_training_index(data: dict) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for biz, mapping in data.get("by_business", {}).items():
        biz_key = _normalize_business_key(biz)
        if not biz_key or not isinstance(mapping, dict):
            continue
        exact: dict[str, str] = {}
        # Së pari ruaj format origjinale. Kur një typo-alias bashkon dy çelësa
        # kontradiktorë (p.sh. tekstil/teksitl), forma e saktë ka prioritet.
        for src, cat in mapping.items():
            if not src or not cat:
                continue
            key = strip_product_noise(src)
            if key:
                exact[key] = norm_category(cat)
            full = normalize_product_text(src)
            if full:
                exact[full] = norm_category(cat)
        # Pastaj shto variantet e zgjeruara vetëm kur nuk mbishkruajnë një
        # emërtim real të trajnuar.
        for src, cat in mapping.items():
            if not src or not cat:
                continue
            expanded = expand_product_word_aliases(src)
            key = strip_product_noise(expanded)
            if key:
                exact.setdefault(key, norm_category(cat))
            full = normalize_product_text(expanded)
            if full:
                exact.setdefault(full, norm_category(cat))
        if exact:
            out[biz_key] = exact
    return out


def _get_index() -> tuple[dict[str, str], list[tuple[str, str]]]:
    global _CACHE
    _ensure_training_fresh()
    if _CACHE is None:
        _CACHE = _training_index(load_training_data())
    return _CACHE


def _get_business_index() -> dict[str, dict[str, str]]:
    global _BIZ_CACHE
    _ensure_training_fresh()
    if _BIZ_CACHE is None:
        _BIZ_CACHE = _business_training_index(load_training_data())
    return _BIZ_CACHE


def reload_training_cache() -> None:
    global _CACHE, _BIZ_CACHE, _REF_TOKEN_INDEX, _TRAINING_MTIME
    _CACHE = None
    _BIZ_CACHE = None
    _REF_TOKEN_INDEX = None
    _TRAINING_MTIME = None


def _get_ref_token_index() -> dict[str, list[str]]:
    global _REF_TOKEN_INDEX
    if _REF_TOKEN_INDEX is not None:
        return _REF_TOKEN_INDEX
    exact, _ = _get_index()
    index: dict[str, set[str]] = {}
    for key in exact:
        for token in set(_search_tokens(key)):
            if len(token) >= 3:
                index.setdefault(token, set()).add(key)
    _REF_TOKEN_INDEX = {t: sorted(keys) for t, keys in index.items()}
    return _REF_TOKEN_INDEX


def _reference_candidate_keys(product_name: str, exact: dict[str, str]) -> list[str]:
    """Filtron çelësat e referencës që ndajnë fjalë me query-n."""
    query_tokens = _search_tokens(product_name)
    if not query_tokens:
        return []
    scores: Counter = Counter()
    token_index = _get_ref_token_index()
    for token in query_tokens:
        if len(token) < 3:
            continue
        for key in token_index.get(token, []):
            scores[key] += 1
    if not scores:
        return []
    query_set = set(query_tokens)
    candidates: list[str] = []
    for key, shared in scores.most_common(40):
        key_tokens = set(_search_tokens(key))
        overlap = query_set & key_tokens
        if shared >= 2 or any(len(t) >= 5 for t in overlap):
            candidates.append(key)
    if not candidates:
        candidates = [scores.most_common(1)[0][0]]
    return candidates


def _match_reference_closest(
    product_name: str, exact: dict[str, str]
) -> tuple[str | None, str]:
    """Gjen kategori më të afërt nga listat referencë (3 Excel)."""
    expanded = expand_product_word_aliases(product_name)
    normalized = normalize_product_text(expanded)
    stripped = strip_product_noise(expanded)

    for key in (stripped, normalized, _model_stripped_key(expanded)):
        if key and key in exact:
            return exact[key], "exact"

    compact = compact_text(expanded)
    for key, cat in exact.items():
        if len(key) >= 5 and compact_text(key) == compact:
            return cat, "exact"

    fuzzy_cat, fuzzy_mode = _fuzzy_training_match(expanded, exact)
    if fuzzy_cat:
        return fuzzy_cat, fuzzy_mode

    candidates = _reference_candidate_keys(expanded, exact)
    if candidates:
        subset = {k: exact[k] for k in candidates if k in exact}
        fuzzy_cat, fuzzy_mode = _fuzzy_training_match(expanded, subset)
        if fuzzy_cat:
            return fuzzy_cat, "reference"

    skeleton = _model_stripped_key(expanded)
    if len(skeleton) >= 4:
        sk_hits = [cat for key, cat in exact.items() if _model_stripped_key(key) == skeleton]
        if sk_hits:
            winner = _pick_category_winner(Counter(sk_hits))
            if winner:
                return winner, "reference"
    return None, ""


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
    payload = dict(existing)
    payload["pairs"] = pairs
    payload["phrases"] = merged_phrases
    payload.setdefault("by_business", existing.get("by_business", {}))
    payload.setdefault("word_aliases", existing.get("word_aliases", WORD_TOKEN_ALIASES))

    TRAINING_PATH.parent.mkdir(exist_ok=True)
    with open(TRAINING_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    reload_training_cache()
    return len(rows), len(pairs)


def import_cleaned_list_training(path: Path | str) -> dict:
    """Importon një listë referencë (Pershkrimi → kategori)."""
    return import_multiple_cleaned_lists([path], merge_with_existing=True)


def _iter_cleaned_list_rows(path: Path | str):
    """Rreshta (src, kategori, shitesi) nga Excel referencë."""
    import pandas as pd

    path = Path(path)
    df = pd.read_excel(path, header=None, engine="openpyxl")
    src_col, tgt_col = _detect_test_liste_columns(df)
    if src_col is None:
        src_col, tgt_col = _detect_reference_columns(df)
    if src_col is None or tgt_col is None:
        raise ValueError(f"Nuk u gjet Pershkrimi → kategori në {path.name}.")

    shitesi_col = None
    data_start = 1
    for idx in range(min(5, len(df))):
        for col_idx in range(df.shape[1]):
            val = str(df.iat[idx, col_idx]).strip().lower().replace("ë", "e")
            if "shites" in val:
                shitesi_col = col_idx
                data_start = idx + 1
                break
        if shitesi_col is not None:
            break

    for row_idx in range(data_start, len(df)):
        src = df.iat[row_idx, src_col] if src_col < df.shape[1] else None
        tgt = df.iat[row_idx, tgt_col] if tgt_col < df.shape[1] else None
        if src is None or tgt is None:
            continue
        src_s = str(src).strip()
        tgt_s = str(tgt).strip()
        if not src_s or src_s.lower() in ("nan", "none", "pershkrimi"):
            continue
        if not tgt_s or tgt_s.lower() in ("nan", "none"):
            continue
        biz = ""
        if shitesi_col is not None:
            biz = str(df.iat[row_idx, shitesi_col]).strip()
            if biz.lower() in ("nan", "none", "shitesi"):
                biz = ""
        yield src_s, tgt_s, biz


def import_multiple_cleaned_lists(
    paths: list[Path | str], merge_with_existing: bool = False
) -> dict:
    """
    Importon një ose më shumë lista referencë (kol. B → kol. C).
    Kombinon votat nga të gjitha skedarët; barazim → kategoria më specifike.
    """
    combined_global: dict[str, Counter] = defaultdict(Counter)
    combined_biz: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    display_votes: dict[str, Counter] = defaultdict(Counter)
    biz_cats: dict[str, set[str]] = defaultdict(set)
    row_count = 0

    for path in paths:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(str(path))
        for src_s, tgt_s, biz in _iter_cleaned_list_rows(path):
            row_count += 1
            key = strip_product_noise(src_s)
            cat = norm_category(tgt_s)
            if not key or not cat:
                continue
            combined_global[key][cat] += 1
            display_votes[cat][tgt_s.strip()] += 1
            if biz:
                combined_biz[biz][key][cat] += 1
                biz_cats[biz].add(tgt_s.strip())

    existing = load_training_data()
    if merge_with_existing:
        for item in existing.get("pairs", []):
            key = strip_product_noise(item.get("source", ""))
            cat = norm_category(item.get("category", ""))
            if key and cat:
                combined_global[key][cat] += 1
        for biz, mapping in existing.get("by_business", {}).items():
            if not isinstance(mapping, dict):
                continue
            for src, cat in mapping.items():
                key = strip_product_noise(src)
                c = norm_category(cat)
                if key and c:
                    combined_biz[biz][key][c] += 1
                    biz_cats[biz].add(str(cat).strip())

    exact_global = {k: _pick_category_winner(v) for k, v in combined_global.items()}
    category_labels = {
        cat: votes.most_common(1)[0][0] for cat, votes in display_votes.items()
    }
    for cat in exact_global.values():
        category_labels.setdefault(cat, cat)

    pairs = [{"source": key, "category": cat} for key, cat in exact_global.items()]
    phrases = dict(exact_global)
    for src_key, counter in combined_global.items():
        for phrase, _ in counter.most_common(3):
            if len(phrase) >= 4:
                phrases[phrase] = exact_global[src_key]

    by_business: dict[str, dict[str, str]] = {}
    for biz, key_map in combined_biz.items():
        by_business[biz] = {
            key: _pick_category_winner(counter) for key, counter in key_map.items()
        }

    if merge_with_existing:
        for biz, mapping in existing.get("by_business", {}).items():
            if biz not in by_business:
                by_business[biz] = dict(mapping)

    payload = {
        "pairs": pairs,
        "phrases": phrases,
        "by_business": by_business,
        "word_aliases": dict(existing.get("word_aliases") or WORD_TOKEN_ALIASES),
        "category_labels": category_labels,
    }
    TRAINING_PATH.parent.mkdir(exist_ok=True)
    with open(TRAINING_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    reload_training_cache()

    return {
        "rows": row_count,
        "pairs": len(pairs),
        "businesses": len(by_business),
        "biz_categories": {k: sorted(v) for k, v in biz_cats.items()},
        "files": [str(Path(p).name) for p in paths],
    }


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


def match_business_training_with_mode(
    business_name: str, product_name: str
) -> tuple[str | None, str]:
    """Trajnim specifik për biznesin (Pershkrimi → kategori e saktë)."""
    if not business_name or not product_name:
        return None, ""
    biz_key = _normalize_business_key(business_name)
    exact = _get_business_index().get(biz_key)
    if not exact:
        return None, ""

    cat, mode = _match_reference_closest(product_name, exact)
    if cat:
        return cat, mode

    expanded = expand_product_word_aliases(product_name)
    for key, cat in sorted(exact.items(), key=lambda x: len(x[0]), reverse=True):
        if len(key) >= 5 and _phrase_matches_query(key, expanded):
            return cat, "phrase"

    token_cat, token_mode = _business_token_training_match(expanded, exact)
    if token_cat:
        return token_cat, token_mode
    return None, ""


def match_business_training(business_name: str, product_name: str) -> str | None:
    cat, _ = match_business_training_with_mode(business_name, product_name)
    return cat


def match_training_category_with_mode(product_name: str) -> tuple[str | None, str]:
    """Kthen (kategori, 'exact'|'phrase'|'' )."""
    if not product_name:
        return None, ""

    exact, phrases = _get_index()
    cat, mode = _match_reference_closest(product_name, exact)
    if cat:
        return cat, mode

    expanded = expand_product_word_aliases(product_name)
    for phrase, cat in phrases:
        if len(phrase) >= 5 and _phrase_matches_query(phrase, expanded):
            return cat, "phrase"

    return None, ""
