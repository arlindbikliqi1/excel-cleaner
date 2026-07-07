from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.utils import secure_filename

from database import (
    add_business,
    add_category_to_business,
    add_name_surname,
    admin_exists,
    analyze_businesses_from_text,
    delete_business,
    get_all_businesses,
    get_name_cleaning_rules,
    init_db,
    list_jobs,
    load_settings,
    log_job,
    normalize_business_name,
    remove_category_from_business,
    remove_name_surname,
    save_random_columns_settings,
    verify_admin,
)
from name_cleaning import HARDCODED_RULES_SUMMARY, clean_name_from_rules
from product_training import (
    expand_product_word_aliases,
    import_training_from_excel,
    is_reference_training_excel,
    match_business_training_with_mode,
    match_training_category,
    match_training_category_with_mode,
    norm_category as canonical_product_category,
    reload_training_cache,
    strip_product_noise,
    _detect_reference_columns,
)
from weight_price_generator import apply_random_pesha_cmimi, get_random_columns_config

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_FOLDER = BASE_DIR / "uploads"
DOWNLOAD_FOLDER = BASE_DIR / "downloads"
LAST_UPLOAD_FILE = UPLOAD_FOLDER / "_last_upload.xlsx"
PREVIEW_HTML_PATH = DATA_DIR / "last_preview.html"
PREVIEW_META_PATH = DATA_DIR / "last_preview_meta.json"

UPLOAD_FOLDER.mkdir(exist_ok=True)
DOWNLOAD_FOLDER.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

TOKEN_PATTERN = re.compile(r"[a-z0-9à-ž]+", re.IGNORECASE)
TOKEN_STOP_WORDS = frozenset({"per", "dhe", "me", "te", "ne", "nga", "nje", "pa", "se"})
SIZE_TOKENS = frozenset({"xs", "s", "m", "l", "xl", "xxl", "xxxl", "2xl", "3xl", "4xl"})
SHORT_KEYWORD_MAX_LEN = 3
MIN_CATEGORY_MATCH_SCORE = 55
MIN_CONFIDENT_MATCH_SCORE = 110
MIN_TRAINING_MATCH_SCORE = 520
MIN_SHORT_KEYWORD_SCORE = 280
MIN_PREFIX_TOKEN_LEN = 4
MIN_STRONG_PREFIX_LEN = 5
MIN_PREFIX_CATEGORY_LEN = 5

# Variante shkrimi → kategori standarde (si lista manuale)
CATEGORY_ALIASES = {
    "pantallona": "pantollona",
    "pantalla": "pantollona",
    "pantolla": "pantollona",
    "pantolon": "pantollona",
    "kmishe": "kemishe",
    "kmise": "kemishe",
    "trenerka": "tuta",
    "trenerk": "tuta",
    "sete": "veshje",
    "lodra": "loder",
    "lodrat": "loder",
    "lodër": "loder",
    "maic": "bluze",
    "maice": "bluze",
    "maica": "bluze",
    "dopsuese": "bluze",
    "body": "bluze",
    "shtrengesa": "bluze",
    "brus": "bluze",
    "qerpik": "aksesore",
    "tekstil": "mbulese",
    "komplet": "mbulese",
    "komplete": "mbulese",
    "fust": "bluze",
    "fustan": "bluze",
    "fustana": "bluze",
    "fustane": "bluze",
    "fustanin": "bluze",
    "fustanet": "bluze",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "excel-cleaner-dev-secret-change-me")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["DOWNLOAD_FOLDER"] = str(DOWNLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

init_db()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, user_id: str):
        self.id = user_id


@login_manager.user_loader
def load_user(user_id):
    if user_id and admin_exists(user_id):
        return User(user_id)
    return None


def normalize_product_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def _product_tokens(normalized: str) -> list[str]:
    """Ndan edhe me - dhe / (p.sh. TEKSTIL-3R, loder/rosaku)."""
    expanded = normalized.replace("-", " ").replace("/", " ")
    return TOKEN_PATTERN.findall(expanded)


def keyword_matches_product(keyword: str, normalized: str, compact: str, tokens: list) -> bool:
    kw = normalize_product_text(keyword)
    if not kw:
        return False
    if len(kw) <= SHORT_KEYWORD_MAX_LEN:
        return kw in tokens
    return kw in normalized or kw.replace(" ", "") in compact


def build_business_lookup(business_categories: dict) -> dict:
    lookup = {}
    for name, categories in business_categories.items():
        key = normalize_business_name(name)
        if key and categories:
            lookup[key] = categories
    return lookup


def _norm_category(text: str) -> str:
    return normalize_product_text(text).replace("ë", "e")


def _is_fustan_category(text: str) -> bool:
    norm = _norm_category(text)
    return norm in ("fustan", "fustana", "fustane", "fustanin", "fustanet", "fust")


def _fustan_to_bluze(
    category: str, business_cats_list: list | None = None
) -> str:
    """Kurrë mos kthe fustan — gjithmonë bluze."""
    if not category or not _is_fustan_category(category):
        return category
    if business_cats_list:
        matched = _business_category_for_norm(business_cats_list, "bluze")
        if matched:
            return matched
    return "bluze"


def _text_mentions_fustan(normalized: str, tokens: list, meaningful: list) -> bool:
    if "fustan" in normalized:
        return True
    return any(
        t.startswith("fustan") or t in ("fustana", "fustane", "fustanin", "fustanet", "fust")
        for t in meaningful + tokens
    )


def _business_category_for_norm(categories: list, target_norm: str) -> str | None:
    for cat in categories:
        if _norm_category(cat) == target_norm:
            return cat
    return None


def _beautify_category_output(
    result: str, business_cats_list: list | None = None
) -> str:
    """Formë e pastër e kategorisë — nga lista e biznesit ose kanonike."""
    if not result:
        return result
    cleaned = re.sub(r"\s+", " ", str(result).strip())
    norm = _norm_category(cleaned)
    if business_cats_list:
        matched = _business_category_for_norm(business_cats_list, norm)
        if matched:
            return _fustan_to_bluze(matched, business_cats_list)
    return _fustan_to_bluze(canonical_product_category(cleaned), business_cats_list)


def _pick_business_fallback(business_cats_list: list) -> str:
    pool = [
        cat
        for cat in business_cats_list
        if not _is_fustan_category(cat)
    ] or business_cats_list
    return _fustan_to_bluze(random.choice(pool), business_cats_list)


def _finalize_business_category(
    original: str, result: str, business_cats_list: list
) -> str:
    """Output = gjithmonë kategori nga lista e biznesit; kurrë emri origjinal i produktit."""
    if not business_cats_list:
        return result
    if len(business_cats_list) == 1:
        return _fustan_to_bluze(business_cats_list[0], business_cats_list)

    matched = _business_category_for_norm(business_cats_list, _norm_category(result))
    if matched:
        return _fustan_to_bluze(matched, business_cats_list)

    # Kurrë mos kthe emrin origjinal të produktit si kategori
    if _norm_category(result) == _norm_category(original):
        return _pick_business_fallback(business_cats_list)

    return _pick_business_fallback(business_cats_list)


def _meaningful_tokens(tokens: list) -> list:
    return [
        t
        for t in tokens
        if not t.isdigit()
        and len(t) >= 2
        and not re.search(r"\d", t)
        and t not in TOKEN_STOP_WORDS
        and t not in SIZE_TOKENS
    ]


def _direct_business_category_match(
    normalized: str, tokens: list, meaningful: list, business_cats_list: list
) -> str | None:
    """
    Kategori e biznesit që shfaqet qartë në tekst (bluze, tuta…).
    Ka prioritet mbi listën globale DG.
    """
    if _text_mentions_fustan(normalized, tokens, meaningful):
        bluze = _business_category_for_norm(business_cats_list, "bluze")
        if bluze:
            return bluze

    cat_by_norm = {_norm_category(cat): cat for cat in business_cats_list}

    for token in meaningful:
        for token_norm in (
            _apply_category_alias(_norm_category(token)),
            _norm_category(token),
        ):
            if token_norm in cat_by_norm:
                return cat_by_norm[token_norm]

    for cat in sorted(business_cats_list, key=lambda c: len(_norm_category(c)), reverse=True):
        cat_norm = _norm_category(cat)
        if len(cat_norm) <= SHORT_KEYWORD_MAX_LEN:
            continue
        if cat_norm in normalized:
            return cat
        if cat_norm.replace(" ", "") in normalized.replace(" ", ""):
            return cat

    return None


def _apply_category_alias(token_norm: str) -> str:
    return _norm_category(CATEGORY_ALIASES.get(token_norm, token_norm))


def _score_category_in_product(category: str, normalized: str, compact: str, tokens: list) -> int:
    """Sa mirë përputhet emri i kategorisë me emërtimin e produktit (më i gjati = më i fortë)."""
    cat_norm = _norm_category(category)
    if not cat_norm:
        return 0
    if cat_norm == normalized:
        return 500 + len(cat_norm)
    cat_compact = cat_norm.replace(" ", "")
    if len(cat_norm) <= SHORT_KEYWORD_MAX_LEN:
        if cat_norm in tokens:
            return 60 + len(cat_norm)
        return 0
    score = 0
    if cat_norm in normalized:
        score = max(score, 450 + len(cat_norm))
    if cat_compact in compact:
        score = max(score, 190 + len(cat_compact))
    return score


def _business_form_for_token(
    token: str, business_cats_list: list, normalized: str = ""
) -> str | None:
    """Gjen kategorinë e biznesit që përputhet me token (emër i plotë, alias ose prefiks)."""
    token_norm = _apply_category_alias(_norm_category(token))
    if not token_norm:
        return None

    direct = _business_category_for_norm(business_cats_list, token_norm)
    if direct:
        return direct

    candidates: list[tuple[int, str, str]] = []
    for cat in business_cats_list:
        cat_norm = _norm_category(cat)
        if not cat_norm:
            continue
        span = 0
        if token_norm == cat_norm:
            return cat
        if len(token_norm) >= MIN_STRONG_PREFIX_LEN and len(cat_norm) >= MIN_PREFIX_CATEGORY_LEN:
            if cat_norm.startswith(token_norm) or token_norm.startswith(cat_norm):
                span = min(len(token_norm), len(cat_norm))
            elif len(token_norm) >= 5 and (token_norm in cat_norm or cat_norm in token_norm):
                span = min(len(token_norm), len(cat_norm))
        if span > 0:
            candidates.append((span, cat, cat_norm))

    if not candidates:
        return None

    if normalized:
        in_text = [item for item in candidates if item[2] in normalized]
        if in_text:
            return max(in_text, key=lambda item: len(item[2]))[1]

    return max(candidates, key=lambda item: item[0])[1]


def _token_matches_category(token_norm: str, cat_norm: str) -> int:
    """Pikë vetëm për përputhje të besueshme token ↔ kategori."""
    if not token_norm or not cat_norm:
        return 0
    if token_norm == cat_norm:
        return 420 + len(cat_norm)
    for part in cat_norm.split():
        if token_norm == part:
            return 340 + len(part)
    if len(token_norm) >= MIN_STRONG_PREFIX_LEN and len(cat_norm) >= MIN_PREFIX_CATEGORY_LEN:
        if cat_norm.startswith(token_norm):
            return 380 + len(token_norm)
        if token_norm.startswith(cat_norm):
            return 370 + len(cat_norm)
    for part in cat_norm.split():
        if len(token_norm) >= MIN_STRONG_PREFIX_LEN and len(part) >= MIN_PREFIX_CATEGORY_LEN:
            if part.startswith(token_norm) or token_norm.startswith(part):
                return 320 + min(len(token_norm), len(part))
    if len(token_norm) >= 5 and len(cat_norm) >= 5 and (
        token_norm in cat_norm or cat_norm in token_norm
    ):
        return 300 + min(len(token_norm), len(cat_norm))
    return 0


def _score_business_category_match(
    category: str, normalized: str, compact: str, tokens: list, meaningful: list
) -> int:
    score = _score_category_in_product(category, normalized, compact, tokens)
    cat_norm = _norm_category(category)
    for token in meaningful:
        token_norm = _apply_category_alias(_norm_category(token))
        score = max(score, _token_matches_category(token_norm, cat_norm))
    return score


def _keyword_to_business_category(
    keyword: str,
    mapped_category: str,
    business_cats_list: list,
    normalized: str,
) -> str | None:
    mapped_norm = _norm_category(mapped_category)
    business_form = _business_category_for_norm(business_cats_list, mapped_norm)
    if business_form:
        return business_form
    for kw_part in normalize_product_text(keyword).split():
        business_form = _business_form_for_token(kw_part, business_cats_list, normalized)
        if business_form:
            return business_form
    return None


def _map_training_to_business(
    product_name: str, business_cats_list: list
) -> tuple[str | None, str]:
    """Lista DG → kategori e biznesit."""
    trained, mode = match_training_category_with_mode(product_name)
    if not trained:
        return None, ""
    direct = _business_category_for_norm(business_cats_list, _norm_category(trained))
    if direct:
        return direct, mode
    for cat in business_cats_list:
        if _norm_category(cat) == _norm_category(trained):
            return cat, mode
    form = _business_form_for_token(trained, business_cats_list)
    if form:
        return form, mode
    # kategori e trajnimit jo në listë — gjej më të afërtin
    trained_norm = _norm_category(trained)
    for cat in business_cats_list:
        cat_norm = _norm_category(cat)
        if trained_norm in cat_norm or cat_norm in trained_norm:
            return cat, mode
    return None, ""


def _resolve_business_category(
    normalized: str,
    compact: str,
    tokens: list,
    meaningful: list,
    business_cats_list: list,
    product_keywords: dict,
    original: str = "",
    business_name: str = "",
) -> str:
    """Përputh kategori të biznesit; pa përputhje të besueshme → random."""
    if len(business_cats_list) == 1:
        return _fustan_to_bluze(business_cats_list[0], business_cats_list)

    # 0) Kategori e biznesit në tekst — para DG globale
    direct = _direct_business_category_match(
        normalized, tokens, meaningful, business_cats_list
    )
    if direct:
        return direct

    # 0b) Trajnim specifik për këtë biznes (lista e pastruar)
    if business_name:
        biz_trained, biz_mode = match_business_training_with_mode(
            business_name, original or normalized
        )
        if biz_trained:
            biz_form = _business_category_for_norm(
                business_cats_list, _norm_category(biz_trained)
            )
            if biz_form:
                return biz_form

    scores: dict[str, int] = {}
    cat_by_norm = {_norm_category(cat): cat for cat in business_cats_list}

    # 1) Lista DG — vetëm nëse nuk ka përputhje direkte më sipër
    trained_form, train_mode = _map_training_to_business(original or normalized, business_cats_list)
    if trained_form and train_mode == "exact":
        return trained_form
    if trained_form and train_mode == "phrase":
        return trained_form
    if trained_form:
        norm = _norm_category(trained_form)
        scores[norm] = max(scores.get(norm, 0), MIN_TRAINING_MATCH_SCORE + len(norm))

    for cat in business_cats_list:
        norm = _norm_category(cat)
        scores[norm] = max(
            scores.get(norm, 0),
            _score_business_category_match(cat, normalized, compact, tokens, meaningful),
        )

    sorted_keywords = sorted(
        product_keywords.items(),
        key=lambda item: len(normalize_product_text(item[0])),
        reverse=True,
    )
    for keyword, mapped_category in sorted_keywords:
        if not keyword_matches_product(keyword, normalized, compact, tokens):
            continue
        business_form = _keyword_to_business_category(
            keyword, mapped_category, business_cats_list, normalized
        )
        if not business_form:
            continue
        norm = _norm_category(business_form)
        kw_score = 300 + len(normalize_product_text(keyword))
        if len(normalize_product_text(keyword)) <= SHORT_KEYWORD_MAX_LEN:
            kw_score = MIN_SHORT_KEYWORD_SCORE + len(keyword)
        scores[norm] = max(scores.get(norm, 0), kw_score)

    if not scores or max(scores.values()) < MIN_CONFIDENT_MATCH_SCORE:
        return _pick_business_fallback(business_cats_list)

    best_norm = max(scores, key=lambda norm: scores[norm])
    return cat_by_norm.get(best_norm) or _pick_business_fallback(business_cats_list)


def resolve_product_global(product_name, product_keywords: dict) -> str:
    """Pa biznes: lista DG + fjalëkyçe (jo random)."""
    if product_name is None or (isinstance(product_name, float) and pd.isna(product_name)):
        return ""

    original = str(product_name).strip()
    if not original or original.lower() in ("nan", "none"):
        return ""

    expanded = expand_product_word_aliases(original)
    normalized = strip_product_noise(expanded)
    compact = normalized.replace(" ", "")
    tokens = _product_tokens(normalized)
    meaningful = _meaningful_tokens(tokens)

    if _text_mentions_fustan(normalized, tokens, meaningful):
        return "bluze"

    trained, mode = match_training_category_with_mode(original)
    if trained:
        return _fustan_to_bluze(_beautify_category_output(trained))

    best_cat = None
    best_score = 0
    for keyword, mapped in sorted(
        product_keywords.items(),
        key=lambda item: len(normalize_product_text(item[0])),
        reverse=True,
    ):
        if not keyword_matches_product(keyword, normalized, compact, tokens):
            continue
        score = len(normalize_product_text(keyword))
        if len(normalize_product_text(keyword)) <= SHORT_KEYWORD_MAX_LEN:
            score = MIN_SHORT_KEYWORD_SCORE
        if score > best_score:
            best_score = score
            best_cat = mapped

    return best_cat if best_cat else original


def map_product_cell(
    shitesi_val: str,
    product_name,
    business_categories: dict,
    product_keywords: dict,
) -> str:
    """Mapo produktin — me biznes, pa biznes, ose vetëm trajnimi."""
    if product_name is None or (isinstance(product_name, float) and pd.isna(product_name)):
        return ""

    original = str(product_name).strip()
    if not original or original.lower() in ("nan", "none"):
        return ""

    business_cats_list = None
    if shitesi_val:
        lookup = build_business_lookup(business_categories)
        business_cats_list = lookup.get(normalize_business_name(str(shitesi_val)))

    if business_cats_list:
        result = get_product_by_business(
            shitesi_val, product_name, business_categories, product_keywords
        )
        return _beautify_category_output(result, business_cats_list)

    return _beautify_category_output(
        resolve_product_global(product_name, product_keywords)
    )


def resolve_product_category(
    product_name,
    product_keywords: dict,
    business_categories: dict,
    business_cats_list: list | None = None,
    business_name: str | None = None,
) -> str:
    """
    Nxjerr kategorinë nga emërtimi i produktit.
    Biznes i njohur → vetëm kategoritë e tij (të ngjashme ose random).
    Biznes i panjohur → lista DG + fjalëkyçe.
    """
    if product_name is None or (isinstance(product_name, float) and pd.isna(product_name)):
        return ""

    original = str(product_name).strip()
    if not original or original.lower() in ("nan", "none"):
        return ""

    if not business_cats_list:
        return resolve_product_global(original, product_keywords)

    expanded = expand_product_word_aliases(original)
    normalized = strip_product_noise(expanded)
    compact = normalized.replace(" ", "")
    tokens = _product_tokens(normalized)
    meaningful = _meaningful_tokens(tokens)

    return _resolve_business_category(
        normalized,
        compact,
        tokens,
        meaningful,
        business_cats_list,
        product_keywords,
        original,
        business_name=business_name or "",
    )


def get_product_by_business(
    business_name,
    product_name,
    business_categories: dict,
    product_keywords: dict,
) -> str:
    if product_name is None or (isinstance(product_name, float) and pd.isna(product_name)):
        return ""

    original = str(product_name).strip()
    if not original or original.lower() in ("nan", "none"):
        return ""

    business_cats_list = None
    if business_name is not None and not (
        isinstance(business_name, float) and pd.isna(business_name)
    ):
        lookup = build_business_lookup(business_categories)
        business_cats_list = lookup.get(normalize_business_name(str(business_name)))

    if not business_cats_list:
        trained = match_training_category(original)
        if trained:
            return trained
        return resolve_product_global(original, product_keywords)

    result = resolve_product_category(
        product_name,
        product_keywords,
        business_categories,
        business_cats_list,
        business_name=str(business_name).strip() if business_name else None,
    )
    return _finalize_business_category(original, result, business_cats_list)


def _norm_header_cell(val) -> str:
    return (
        str(val)
        .strip()
        .lower()
        .replace("ë", "e")
        .replace("ç", "c")
    )


# Kolona që nuk duhen kurrë mapuar si produkt (kodi, pako, telefon, etj.)
_PROTECTED_COLUMN_HEADERS = frozenset({
    "kodi", "kod", "code", "pako", "pesha", "pesha/kg", "cmimi", "origjina",
    "origin", "qyteti", "city", "opsionale", "telefon", "tel", "phone",
    "pranuesi", "pranues", "shitesi", "shites", "seller", "dyqan", "shop",
})


def _header_label(df: pd.DataFrame, header_row: int | None, col_idx: int) -> str:
    if header_row is None or col_idx >= df.shape[1]:
        return ""
    return _norm_header_cell(df.iat[header_row, col_idx])


def _is_protected_column(df: pd.DataFrame, mapping: dict, col_idx: int) -> bool:
    """Kolona që nuk duhet prekur nga mapimi i produktit."""
    label = _header_label(df, mapping.get("header_row"), col_idx)
    if not label:
        return False
    if label in _PROTECTED_COLUMN_HEADERS:
        return True
    return any(
        tag in label
        for tag in ("kodi", "pako", "pesha", "cmim", "origjin", "qytet", "opsion", "telefon")
    )


def _looks_like_kodi_column(df: pd.DataFrame, col_idx: int, data_start: int) -> bool:
    """Kolona me kode artikujsh (00056-004607) — jo përshkrim produkti."""
    code_like = 0
    total = 0
    for row_idx in range(data_start, min(data_start + 60, len(df))):
        text = _cell_text(df.iat[row_idx, col_idx])
        if not text:
            continue
        total += 1
        if re.match(r"^[\dA-Za-z\-]+$", text) and "-" in text and len(text) >= 8:
            code_like += 1
    return total >= 5 and code_like / total >= 0.5


def _classify_header_cell(val) -> str | None:
    """Kthen 'pranuesi', 'produkti', 'shitesi' ose None."""
    v = _norm_header_cell(val)
    if not v or v in ("nan", "none"):
        return None
    if v in ("shitesi", "shites", "seller", "dyqan", "shop") or "shites" in v:
        return "shitesi"
    if v in ("pranuesi", "pranues", "pranuesin") or "pranues" in v:
        return "pranuesi"
    if "pershkrim" in v or v in ("description", "desc"):
        return "produkti"
    if (
        v in ("produkti", "produktet", "produkt")
        or "produkt" in v
        or "emertimi" in v
        or "artikull" in v
        or v in ("kategori", "kategoria", "kategorite")
        or "kategori" in v
    ):
        return "produkti"
    if v in ("emri", "klienti", "klient", "recipient"):
        return "pranuesi"
    return None


def find_excel_column_mapping(df: pd.DataFrame) -> dict:
    """
    Gjen rreshtin e titullit dhe indekset e kolonave Pranuesi / Produkti / SHITESI.
    Nuk heq kolona të tjera — vetëm identifikon ku janë kolonat tona.
    """
    best = None
    scan_rows = min(15, len(df))

    for idx in range(scan_rows):
        pranuesi_col = produkti_col = shitesi_col = None
        for col_idx in range(df.shape[1]):
            kind = _classify_header_cell(df.iat[idx, col_idx])
            if kind == "pranuesi":
                pranuesi_col = col_idx
            elif kind == "produkti":
                produkti_col = col_idx
            elif kind == "shitesi":
                shitesi_col = col_idx
        if shitesi_col is None:
            continue
        score = sum(x is not None for x in (pranuesi_col, produkti_col, shitesi_col))
        candidate = {
            "header_row": idx,
            "data_start": idx + 1,
            "pranuesi_col": pranuesi_col,
            "produkti_col": produkti_col,
            "shitesi_col": shitesi_col,
            "score": score,
        }
        if best is None or score > best["score"]:
            best = candidate

    if best is None:
        return {
            "header_row": None,
            "data_start": 0,
            "pranuesi_col": None,
            "produkti_col": None,
            "shitesi_col": None,
            "pesha_col": None,
            "cmimi_col": None,
            "score": 0,
        }
    pesha_col, cmimi_col = _detect_pesha_cmimi_cols(df, best["header_row"])
    best["pesha_col"] = pesha_col
    best["cmimi_col"] = cmimi_col
    return best


def _detect_pesha_cmimi_cols(df: pd.DataFrame, header_row: int | None) -> tuple[int | None, int | None]:
    pesha_col = cmimi_col = None
    if header_row is None:
        return pesha_col, cmimi_col
    for col_idx in range(df.shape[1]):
        v = _norm_header_cell(df.iat[header_row, col_idx])
        if not v:
            continue
        if "pesha" in v:
            pesha_col = col_idx
        elif "cmim" in v:
            cmimi_col = col_idx
    return pesha_col, cmimi_col


def _forward_fill_shitesi(df: pd.DataFrame, sh_col: int, data_start: int) -> None:
    """Excel shpesh ka emrin e shitësit vetëm në rreshtin e parë të grupit."""
    last = ""
    for row_idx in range(data_start, len(df)):
        text = _cell_text(df.iat[row_idx, sh_col])
        if text:
            last = text
        elif last:
            df.iat[row_idx, sh_col] = last


def _shitesi_for_row(df: pd.DataFrame, row_idx: int, sh_col: int, data_start: int) -> str:
    text = _cell_text(df.iat[row_idx, sh_col])
    if text:
        return text
    for prev in range(row_idx - 1, data_start - 1, -1):
        text = _cell_text(df.iat[prev, sh_col])
        if text:
            return text
    return ""


def _infer_produkti_column(df: pd.DataFrame, mapping: dict) -> int | None:
    sh_col = mapping["shitesi_col"]
    pr_col = mapping["pranuesi_col"]
    data_start = mapping["data_start"]
    skip = {c for c in (sh_col, pr_col) if c is not None}
    best_col = None
    best_score = 0
    for col_idx in range(df.shape[1]):
        if col_idx in skip:
            continue
        if _is_protected_column(df, mapping, col_idx):
            continue
        if _looks_like_kodi_column(df, col_idx, data_start):
            continue
        score = 0
        for row_idx in range(data_start, min(data_start + 200, len(df))):
            text = _cell_text(df.iat[row_idx, col_idx])
            if len(text) >= 3:
                score += min(len(text), 40)
        if score > best_score:
            best_score = score
            best_col = col_idx
    return best_col if best_score > 0 else None


def _produkti_columns(df: pd.DataFrame, mapping: dict) -> list[int]:
    """Vetëm kolona Pershkrimi/Produkti — jo Kodi apo kolona të tjera."""
    cols: set[int] = set()
    header_row = mapping["header_row"]
    if header_row is not None:
        for col_idx in range(df.shape[1]):
            if _classify_header_cell(df.iat[header_row, col_idx]) == "produkti":
                if not _is_protected_column(df, mapping, col_idx):
                    cols.add(col_idx)
    if mapping["produkti_col"] is not None and not _is_protected_column(
        df, mapping, mapping["produkti_col"]
    ):
        cols.add(mapping["produkti_col"])
    if not cols:
        inferred = _infer_produkti_column(df, mapping)
        if inferred is not None:
            cols.add(inferred)
    return sorted(cols)


def _canonical_business_name(name: str, business_categories: dict) -> str:
    """Emër i njohur nga settings — ruaj shkrimin zyrtar."""
    if not name:
        return name
    target = normalize_business_name(name)
    for key in business_categories:
        if normalize_business_name(key) == target:
            return key
    return str(name).strip()


def _cell_text(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def _is_blank_cell(val) -> bool:
    return _cell_text(val) == ""


def _is_order_data_row(
    df: pd.DataFrame,
    row_idx: int,
    mapping: dict,
    produkti_cols: list[int] | None = None,
) -> bool:
    """Rresht i vlefshëm porosie — jo rresht bosh (edhe pas forward-fill të SHITESI)."""
    if row_idx < mapping["data_start"]:
        return False
    if produkti_cols is None:
        produkti_cols = _produkti_columns(df, mapping)
    pr_col = mapping.get("pranuesi_col")

    for col_idx in produkti_cols:
        if _cell_text(df.iat[row_idx, col_idx]):
            return True
    if pr_col is not None and _cell_text(df.iat[row_idx, pr_col]):
        return True
    kodi = _cell_text(df.iat[row_idx, 0])
    if kodi and kodi.lower() not in ("kodi", "code") and (len(kodi) > 4 or "-" in kodi):
        return True
    return False


def _count_order_data_rows(df: pd.DataFrame, mapping: dict) -> int:
    produkti_cols = _produkti_columns(df, mapping)
    return sum(
        1
        for row_idx in range(mapping["data_start"], len(df))
        if _is_order_data_row(df, row_idx, mapping, produkti_cols)
    )


def _trim_to_order_rows(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Heq rreshtat bosh — Excel shpesh lexon 1000+ rreshta të zbrazëta."""
    produkti_cols = _produkti_columns(df, mapping)
    keep = list(range(0, mapping["data_start"]))
    for row_idx in range(mapping["data_start"], len(df)):
        if _is_order_data_row(df, row_idx, mapping, produkti_cols):
            keep.append(row_idx)
    return df.iloc[keep].copy().reset_index(drop=True)


def _prepare_df_for_export(df: pd.DataFrame) -> pd.DataFrame:
    """Qelizat bosh mbeten bosh në Excel/preview — jo teksti 'NaN'."""
    out = df.copy()
    for row_idx in range(len(out)):
        for col_idx in range(out.shape[1]):
            val = out.iat[row_idx, col_idx]
            if val is None:
                continue
            if isinstance(val, float) and pd.isna(val):
                out.iat[row_idx, col_idx] = None
            elif isinstance(val, str) and val.strip().lower() in ("nan", "none"):
                out.iat[row_idx, col_idx] = None
    return out


def collect_unknown_businesses_full(
    df: pd.DataFrame, mapping: dict, settings: dict
) -> list:
    lookup = build_business_lookup(settings.get("business_categories", {}))
    shitesi_col = mapping["shitesi_col"]
    data_start = mapping["data_start"]
    unknown = set()
    for row_idx in range(data_start, len(df)):
        name = _cell_text(df.iat[row_idx, shitesi_col])
        if not name:
            continue
        key = normalize_business_name(name)
        if key and key not in lookup:
            unknown.add(name)
    return sorted(unknown)


def _shitesi_column_has_data(df: pd.DataFrame, mapping: dict) -> bool:
    col = mapping["shitesi_col"]
    if col is None:
        return False
    for row_idx in range(mapping["data_start"], len(df)):
        if _cell_text(df.iat[row_idx, col]):
            return True
    return False


def transform_reference_training_excel(filepath: str, settings: dict) -> tuple:
    """
  Excel referencë DG (emërtim → kategori): importon trajnimin dhe mapo kolonën e majtë.
    """
    df = pd.read_excel(filepath, header=None, engine="openpyxl")
    if df.empty:
        raise ValueError("Excel-i është bosh.")

    if not is_reference_training_excel(df):
        raise ValueError("Skedari nuk është format referencë DG (2 kolona emërtim/kategori).")

    row_count, pair_count = import_training_from_excel(filepath)
    product_keywords = settings.get("product_keywords", {})
    business_categories = settings.get("business_categories", {})

    src_col, tgt_col = _detect_reference_columns(df)
    df = df.copy()
    matched = 0
    processed = 0

    for row_idx in range(len(df)):
        src = _cell_text(df.iat[row_idx, src_col])
        if not src:
            continue
        processed += 1
        mapped = map_product_cell("", src, business_categories, product_keywords)
        df.iat[row_idx, src_col] = mapped
        expected = _cell_text(df.iat[row_idx, tgt_col])
        if expected and _norm_category(mapped) == _norm_category(expected):
            matched += 1

    df_export = _prepare_df_for_export(df)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"dg_mapped_{timestamp}.xlsx"
    out_path = DOWNLOAD_FOLDER / out_name
    df_export.to_excel(out_path, index=False, header=False, engine="openpyxl", na_rep="")

    pct = round(100 * matched / processed, 1) if processed else 0
    meta_note = [f"DG referencë: {pair_count} çifte, përputhje {matched}/{processed} ({pct}%)"]
    return df, meta_note, out_name, processed


def transform_excel(
    filepath: str, settings: dict, target_total_kg: float | None = None
) -> tuple:
    """
    Lexon Excel-in të plotë, ndryshon vetëm qelizat në kolonat Pranuesi / Produkti / SHITESI,
    ruan të gjitha kolonat dhe radhitjen e rreshtave si në skedarin origjinal.
    """
    df = pd.read_excel(filepath, header=None, engine="openpyxl")
    if df.empty:
        raise ValueError("Excel-i është bosh.")

    if is_reference_training_excel(df):
        df, unknown, out_name, row_count = transform_reference_training_excel(
            filepath, settings
        )
        return df, unknown, out_name, row_count, {"applied": False}

    mapping = find_excel_column_mapping(df)
    if mapping["shitesi_col"] is None:
        raise ValueError(
            'Nuk u gjet kolona "SHITESI" (ose Shitësi / Seller / Dyqan) në titujt e Excel-it.'
        )
    if not _shitesi_column_has_data(df, mapping):
        raise ValueError(
            'Kolona "SHITESI" ekziston por nuk ka të dhëna në rreshtat e listës.'
        )

    df = df.copy()
    business_categories = settings.get("business_categories", {})
    product_keywords = settings.get("product_keywords", {})
    name_rules = settings.get("name_cleaning_rules") or get_name_cleaning_rules()

    sh_col = mapping["shitesi_col"]
    data_start = mapping["data_start"]
    if sh_col is not None:
        _forward_fill_shitesi(df, sh_col, data_start)

    produkti_cols = _produkti_columns(df, mapping)
    order_row_indices = [
        i
        for i in range(data_start, len(df))
        if _is_order_data_row(df, i, mapping, produkti_cols)
    ]

    gen_meta = apply_random_pesha_cmimi(
        df,
        mapping,
        settings,
        order_row_indices,
        target_total_kg=target_total_kg,
    )

    unknown_businesses = collect_unknown_businesses_full(df, mapping, settings)

    pr_col = mapping["pranuesi_col"]

    for row_idx in order_row_indices:
        shitesi_val = _shitesi_for_row(df, row_idx, sh_col, data_start) if sh_col is not None else ""

        if sh_col is not None and not _is_blank_cell(df.iat[row_idx, sh_col]):
            df.iat[row_idx, sh_col] = _canonical_business_name(
                df.iat[row_idx, sh_col], business_categories
            )
            shitesi_val = _cell_text(df.iat[row_idx, sh_col])

        for prod_col in produkti_cols:
            if _is_blank_cell(df.iat[row_idx, prod_col]):
                continue
            orig_product = df.iat[row_idx, prod_col]
            df.iat[row_idx, prod_col] = map_product_cell(
                shitesi_val,
                orig_product,
                business_categories,
                product_keywords,
            )

        if pr_col is not None and not _is_blank_cell(df.iat[row_idx, pr_col]):
            df.iat[row_idx, pr_col] = clean_name_from_rules(
                df.iat[row_idx, pr_col], name_rules
            )

    data_row_count = _count_order_data_rows(df, mapping)
    df = _trim_to_order_rows(df, mapping)

    df_export = _prepare_df_for_export(df)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"cleaned_{timestamp}.xlsx"
    out_path = DOWNLOAD_FOLDER / out_name
    df_export.to_excel(
        out_path, index=False, header=False, engine="openpyxl", na_rep=""
    )

    return df, unknown_businesses, out_name, data_row_count, gen_meta


def save_last_upload(source_path: Path):
    import shutil

    shutil.copy2(source_path, LAST_UPLOAD_FILE)
    session["has_last_upload"] = True


def parse_categories_string(categories_string: str) -> list:
    return [c.strip() for c in categories_string.replace("\n", ",").split(",") if c.strip()]


def refresh_detect_result_in_session():
    pasted = session.get("shitesi_paste", "")
    if pasted.strip():
        session["detect_result"] = analyze_businesses_from_text(pasted)


def save_dashboard_preview(
    df: pd.DataFrame,
    unknown: list,
    out_name: str,
    row_count: int | None = None,
    target_kg: float | None = None,
):
    """Preview në disk — session cookie nuk mbajnë tabela të mëdha (>4KB)."""
    preview_df = _prepare_df_for_export(df)
    html = preview_df.to_html(
        classes="table table-sm preview-table mb-0",
        index=False,
        header=False,
        na_rep="",
    )
    PREVIEW_HTML_PATH.write_text(html, encoding="utf-8")
    meta = {
        "last_download": out_name,
        "row_count": row_count if row_count is not None else len(df),
        "unknown_businesses": unknown,
        "last_target_kg": target_kg,
    }
    PREVIEW_META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    session["has_preview"] = True


def load_dashboard_preview() -> dict:
    if not PREVIEW_HTML_PATH.exists():
        return {
            "preview_html": None,
            "last_download": None,
            "unknown_businesses": [],
            "row_count": None,
            "last_target_kg": None,
            "has_last_upload": LAST_UPLOAD_FILE.exists(),
        }
    preview_html = PREVIEW_HTML_PATH.read_text(encoding="utf-8")
    meta = {}
    if PREVIEW_META_PATH.exists():
        try:
            meta = json.loads(PREVIEW_META_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    return {
        "preview_html": preview_html,
        "last_download": meta.get("last_download"),
        "unknown_businesses": meta.get("unknown_businesses", []),
        "row_count": meta.get("row_count"),
        "last_target_kg": meta.get("last_target_kg"),
        "has_last_upload": LAST_UPLOAD_FILE.exists(),
    }


def clear_dashboard_preview():
    session.pop("has_preview", None)
    for path in (PREVIEW_HTML_PATH, PREVIEW_META_PATH):
        if path.exists():
            path.unlink(missing_ok=True)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if verify_admin(username, password):
            login_user(User(username))
            return redirect(url_for("dashboard"))
        flash("Kredencialet janë të gabuara.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    for key in (
        "preview_html",
        "last_download",
        "unknown_businesses",
        "has_last_upload",
        "has_preview",
        "detect_result",
        "shitesi_paste",
    ):
        session.pop(key, None)
    clear_dashboard_preview()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    ctx = load_dashboard_preview()
    return render_template("dashboard.html", **ctx)


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    has_new_file = file is not None and bool(file.filename)

    if not has_new_file and not LAST_UPLOAD_FILE.exists():
        flash("Zgjidhni një skedar Excel.", "warning")
        return redirect(url_for("dashboard"))

    target_total_kg = None
    target_raw = request.form.get("target_total_kg", "").strip().replace(",", ".")
    if target_raw:
        try:
            target_total_kg = float(target_raw)
            if target_total_kg <= 0:
                raise ValueError("negative")
        except ValueError:
            flash("Pesha totale e listës duhet të jetë një numër pozitiv (p.sh. 410).", "warning")
            return redirect(url_for("dashboard"))
    else:
        flash("Vendosni pesha totale të listës në kg.", "warning")
        return redirect(url_for("dashboard"))

    reprocess = False
    if has_new_file:
        original_name = file.filename
        filename = secure_filename(original_name)
        if not filename.lower().endswith((".xlsx", ".xls")):
            flash("Lejohen vetëm skedarë .xlsx ose .xls.", "warning")
            return redirect(url_for("dashboard"))
        save_path = UPLOAD_FOLDER / filename
        file.save(save_path)
    else:
        save_path = LAST_UPLOAD_FILE
        original_name = save_path.name
        reprocess = True

    try:
        settings = load_settings()
        df, unknown, out_name, row_count, gen_meta = transform_excel(
            str(save_path), settings, target_total_kg=target_total_kg
        )
        if has_new_file:
            save_last_upload(save_path)
        save_dashboard_preview(
            df, unknown, out_name, row_count, target_kg=target_total_kg
        )

        username = current_user.id if current_user.is_authenticated else "admin"
        log_job(original_name, out_name, row_count, username)

        dg_msg = None
        if unknown and len(unknown) == 1 and str(unknown[0]).startswith("DG referencë"):
            dg_msg = str(unknown[0])
            unknown = []

        flash(
            f"Excel u transformua me sukses. {row_count} rreshta të dhënash u përpunuan.",
            "success",
        )
        if reprocess:
            flash("Lista e fundit u ripërpunua me peshën e re.", "info")
        if gen_meta.get("applied"):
            parts = []
            if gen_meta.get("target_kg"):
                parts.append(
                    f"Pesha: {gen_meta['rows']} rreshta → {gen_meta.get('pesha_sum', 0)} kg"
                )
            if gen_meta.get("cmimi_generated"):
                cfg = get_random_columns_config(settings)
                parts.append(f"Çmimi random {cfg['cmimi_min']}–{cfg['cmimi_max']}")
            if parts:
                flash("Gjenerim random: " + " · ".join(parts) + ".", "info")
        if dg_msg:
            flash(dg_msg, "info")
        if unknown:
            flash(
                f"Biznese të panjohura ({len(unknown)}): {', '.join(unknown[:5])}"
                + ("..." if len(unknown) > 5 else "")
                + " — produktet mapohen nga lista DG / fjalëkyçe.",
                "warning",
            )
    except Exception as exc:
        flash(f"Gabim gjatë përpunimit: {exc}", "danger")
    finally:
        if has_new_file and save_path.exists() and save_path != LAST_UPLOAD_FILE:
            save_path.unlink(missing_ok=True)

    return redirect(url_for("dashboard"))


@app.route("/history")
@login_required
def history():
    return render_template("history.html", jobs=list_jobs(50))


@app.route("/businesses", methods=["GET", "POST"])
@login_required
def businesses():
    if request.method == "POST":
        name = request.form.get("business_name", "").strip()
        categories_string = request.form.get("categories_string", "")
        categories = parse_categories_string(categories_string)
        if name:
            add_business(name, categories)
            flash(f"Biznesi «{name}» u krijua.", "success")
        else:
            flash("Emri i biznesit është i detyrueshëm.", "warning")
        return redirect(url_for("businesses"))

    detect_result = session.get("detect_result")
    raw = get_all_businesses()
    businesses_sorted = dict(sorted(raw.items(), key=lambda x: str(x[0]).lower()))
    return render_template(
        "businesses.html",
        businesses=businesses_sorted,
        detect_result=detect_result,
        shitesi_paste=session.get("shitesi_paste", ""),
    )


@app.route("/businesses/<path:business_name>/add_category", methods=["POST"])
@login_required
def business_add_category(business_name):
    business_name = unquote(business_name)
    category = request.form.get("category", "").strip()
    if category:
        add_category_to_business(business_name, category)
        flash("Kategoria u shtua.", "success")
    return redirect(url_for("businesses"))


@app.route(
    "/businesses/<path:business_name>/remove_category/<path:category>",
    methods=["POST"],
)
@login_required
def business_remove_category(business_name, category):
    business_name = unquote(business_name)
    category = unquote(category)
    remove_category_from_business(business_name, category)
    flash("Kategoria u hoq.", "info")
    return redirect(url_for("businesses"))


@app.route("/businesses/<path:business_name>/delete", methods=["POST"])
@login_required
def business_delete(business_name):
    business_name = unquote(business_name)
    delete_business(business_name)
    flash("Biznesi u fshi.", "info")
    return redirect(url_for("businesses"))


@app.route("/businesses/create-from-unknown", methods=["POST"])
@login_required
def create_from_unknown():
    name = request.form.get("business_name", "").strip()
    categories_string = request.form.get("categories_string", "")
    categories = parse_categories_string(categories_string)
    if name:
        add_business(name, categories)
        refresh_detect_result_in_session()
        flash(f"Biznesi «{name}» u krijua.", "success")
    return redirect(url_for("businesses"))


@app.route("/businesses/create-all-unknown", methods=["POST"])
@login_required
def create_all_unknown():
    detect_result = session.get("detect_result") or {}
    unknown = detect_result.get("unknown") or []
    if not unknown:
        flash("Asnjë biznes i panjohur për të krijuar.", "warning")
        return redirect(url_for("businesses"))

    categories = parse_categories_string(request.form.get("default_categories", ""))
    if not categories:
        flash("Vendos kategoritë që do u aplikohen për të gjitha bizneset e reja.", "warning")
        return redirect(url_for("businesses"))

    created = 0
    for name in unknown:
        add_business(name, categories)
        created += 1

    refresh_detect_result_in_session()
    flash(f"U krijuan {created} biznese me kategoritë: {', '.join(categories)}.", "success")
    return redirect(url_for("businesses"))


@app.route("/detect-unknown", methods=["POST"])
@login_required
def detect_unknown():
    pasted = request.form.get("shitesi_paste", "")
    if not pasted.strip():
        flash("Ngjis kolonën SHITESI nga Excel në fushën e tekstit.", "warning")
        return redirect(url_for("businesses"))

    result = analyze_businesses_from_text(pasted)
    session["shitesi_paste"] = pasted
    if result.get("error"):
        flash(result["error"], "danger")
        session.pop("detect_result", None)
    else:
        session["detect_result"] = result
        total = len(result["all"])
        flash(
            f"Analiza: {total} biznese unike — "
            f"{len(result['known'])} në settings, {len(result['unknown'])} të panjohura.",
            "success" if not result["unknown"] else "warning",
        )

    return redirect(url_for("businesses"))


@app.route("/generation-settings", methods=["GET", "POST"])
@login_required
def generation_settings():
    if request.method == "POST":
        common_raw = request.form.get("pesha_common", "")
        common_vals = []
        for part in common_raw.replace(";", ",").split(","):
            part = part.strip().replace(",", ".")
            if not part:
                continue
            try:
                common_vals.append(float(part))
            except ValueError:
                continue

        try:
            pesha_min = float(request.form.get("pesha_min", "0.5").replace(",", "."))
            pesha_max = float(request.form.get("pesha_max", "0.96").replace(",", "."))
            cmimi_min = int(request.form.get("cmimi_min", "15"))
            cmimi_max = int(request.form.get("cmimi_max", "22"))
        except ValueError:
            flash("Vlerat e ranges duhet të jenë numra të vlefshëm.", "warning")
            return redirect(url_for("generation_settings"))

        if pesha_min > pesha_max:
            pesha_min, pesha_max = pesha_max, pesha_min
        if cmimi_min > cmimi_max:
            cmimi_min, cmimi_max = cmimi_max, cmimi_min

        cfg = {
            "enabled": request.form.get("enabled") == "on",
            "pesha_min": pesha_min,
            "pesha_max": pesha_max,
            "pesha_common": common_vals or get_random_columns_config({})["pesha_common"],
            "cmimi_min": cmimi_min,
            "cmimi_max": cmimi_max,
        }
        save_random_columns_settings(cfg)
        flash("Settings për Pesha & Çmimi u ruajtën.", "success")
        return redirect(url_for("generation_settings"))

    cfg = get_random_columns_config(load_settings())
    return render_template("generation_settings.html", cfg=cfg)


@app.route("/recipient-rules", methods=["GET", "POST"])
@login_required
def recipient_rules():
    rules = get_name_cleaning_rules()
    test_input = ""
    test_output = None

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "add_surname":
            add_name_surname(request.form.get("surname", ""))
            flash("Mbiemri u shtua.", "success")
            return redirect(url_for("recipient_rules"))
        if action == "delete_surname":
            remove_name_surname(request.form.get("surname", ""))
            flash("Mbiemri u hoq.", "info")
            return redirect(url_for("recipient_rules"))
        if action == "test_name":
            test_input = request.form.get("test_input", "").strip()
            test_output = clean_name_from_rules(test_input, get_name_cleaning_rules())
            return render_template(
                "recipient_rules.html",
                rules=get_name_cleaning_rules(),
                rules_summary=HARDCODED_RULES_SUMMARY,
                test_input=test_input,
                test_output=test_output,
            )

    return render_template(
        "recipient_rules.html",
        rules=rules,
        rules_summary=HARDCODED_RULES_SUMMARY,
        test_input=test_input,
        test_output=test_output,
    )


@app.route("/download/<filename>")
@login_required
def download(filename):
    safe = secure_filename(filename)
    path = DOWNLOAD_FOLDER / safe
    if not path.exists():
        flash("Skedari nuk u gjet.", "danger")
        return redirect(url_for("dashboard"))
    return send_from_directory(app.config["DOWNLOAD_FOLDER"], safe, as_attachment=True)


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", "5001"))
    app.run(debug=debug, use_reloader=debug, host="0.0.0.0", port=port)
