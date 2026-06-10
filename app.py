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
    verify_admin,
)
from name_cleaning import HARDCODED_RULES_SUMMARY, clean_name_from_rules

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


def _business_category_for_norm(categories: list, target_norm: str) -> str | None:
    for cat in categories:
        if _norm_category(cat) == target_norm:
            return cat
    return None


def _pick_business_fallback(business_cats_list: list) -> str:
    return random.choice(business_cats_list)


def _finalize_business_category(
    original: str, result: str, business_cats_list: list
) -> str:
    """Output = gjithmonë kategori nga lista e biznesit; kurrë emri origjinal i produktit."""
    if not business_cats_list:
        return result
    if len(business_cats_list) == 1:
        return business_cats_list[0]

    matched = _business_category_for_norm(business_cats_list, _norm_category(result))
    if matched:
        return matched

    # Kurrë mos kthe emrin origjinal të produktit si kategori
    if _norm_category(result) == _norm_category(original):
        return _pick_business_fallback(business_cats_list)

    return _pick_business_fallback(business_cats_list)


def _meaningful_tokens(tokens: list) -> list:
    return [
        t
        for t in tokens
        if not t.isdigit() and len(t) >= 2 and t not in TOKEN_STOP_WORDS and t not in SIZE_TOKENS
    ]


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


def _resolve_business_category(
    normalized: str,
    compact: str,
    tokens: list,
    meaningful: list,
    business_cats_list: list,
    product_keywords: dict,
) -> str:
    """Përputh kategori të biznesit; pa përputhje të besueshme → random."""
    if len(business_cats_list) == 1:
        return business_cats_list[0]

    scores: dict[str, int] = {}
    cat_by_norm = {_norm_category(cat): cat for cat in business_cats_list}

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
        scores[norm] = max(scores.get(norm, 0), kw_score)

    if not scores or max(scores.values()) < MIN_CONFIDENT_MATCH_SCORE:
        return _pick_business_fallback(business_cats_list)

    best_norm = max(scores, key=lambda norm: scores[norm])
    return cat_by_norm.get(best_norm) or _pick_business_fallback(business_cats_list)


def resolve_product_category(
    product_name,
    product_keywords: dict,
    business_categories: dict,
    business_cats_list: list | None = None,
) -> str:
    """
    Nxjerr kategorinë nga emërtimi i produktit.
    Biznes i njohur → vetëm kategoritë e tij (të ngjashme ose random).
    Biznes i panjohur → mbetet emri origjinal (pa kategori globale).
    """
    if product_name is None or (isinstance(product_name, float) and pd.isna(product_name)):
        return ""

    original = str(product_name).strip()
    if not original or original.lower() in ("nan", "none"):
        return ""

    if not business_cats_list:
        return original

    normalized = normalize_product_text(original)
    compact = normalized.replace(" ", "")
    tokens = _product_tokens(normalized)
    meaningful = _meaningful_tokens(tokens)

    return _resolve_business_category(
        normalized, compact, tokens, meaningful, business_cats_list, product_keywords
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
        return original

    result = resolve_product_category(
        product_name,
        product_keywords,
        business_categories,
        business_cats_list,
    )
    return _finalize_business_category(original, result, business_cats_list)


def _norm_header_cell(val) -> str:
    return str(val).strip().lower().replace("ë", "e")


def _classify_header_cell(val) -> str | None:
    """Kthen 'pranuesi', 'produkti', 'shitesi' ose None."""
    v = _norm_header_cell(val)
    if not v or v in ("nan", "none"):
        return None
    if v in ("shitesi", "shites", "seller", "dyqan", "shop") or "shites" in v:
        return "shitesi"
    if v in ("pranuesi", "pranues", "pranuesin") or "pranues" in v:
        return "pranuesi"
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
            "score": 0,
        }
    return best


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
    """Të gjitha kolonat e produktit/kategorisë që duhen zëvendësuar."""
    cols: set[int] = set()
    header_row = mapping["header_row"]
    if header_row is not None:
        for col_idx in range(df.shape[1]):
            if _classify_header_cell(df.iat[header_row, col_idx]) == "produkti":
                cols.add(col_idx)
    if mapping["produkti_col"] is not None:
        cols.add(mapping["produkti_col"])
    if not cols:
        inferred = _infer_produkti_column(df, mapping)
        if inferred is not None:
            cols.add(inferred)
    return sorted(cols)


def _cell_text(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def _is_blank_cell(val) -> bool:
    return _cell_text(val) == ""


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


def transform_excel(filepath: str, settings: dict) -> tuple:
    """
    Lexon Excel-in të plotë, ndryshon vetëm qelizat në kolonat Pranuesi / Produkti / SHITESI,
    ruan të gjitha kolonat dhe radhitjen e rreshtave si në skedarin origjinal.
    """
    df = pd.read_excel(filepath, header=None, engine="openpyxl")
    if df.empty:
        raise ValueError("Excel-i është bosh.")

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

    unknown_businesses = collect_unknown_businesses_full(df, mapping, settings)

    pr_col = mapping["pranuesi_col"]
    produkti_cols = _produkti_columns(df, mapping)

    for row_idx in range(data_start, len(df)):
        shitesi_val = _shitesi_for_row(df, row_idx, sh_col, data_start) if sh_col is not None else ""

        for prod_col in produkti_cols:
            if not _cell_text(shitesi_val):
                continue
            if _is_blank_cell(df.iat[row_idx, prod_col]):
                continue
            orig_product = df.iat[row_idx, prod_col]
            df.iat[row_idx, prod_col] = get_product_by_business(
                shitesi_val,
                orig_product,
                business_categories,
                product_keywords,
            )

        if pr_col is not None and not _is_blank_cell(df.iat[row_idx, pr_col]):
            df.iat[row_idx, pr_col] = clean_name_from_rules(
                df.iat[row_idx, pr_col], name_rules
            )

    df_export = _prepare_df_for_export(df)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"cleaned_{timestamp}.xlsx"
    out_path = DOWNLOAD_FOLDER / out_name
    df_export.to_excel(
        out_path, index=False, header=False, engine="openpyxl", na_rep=""
    )

    data_row_count = max(0, len(df) - data_start)
    return df, unknown_businesses, out_name, data_row_count


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
    df: pd.DataFrame, unknown: list, out_name: str, row_count: int | None = None
):
    """Preview në disk — session cookie nuk mbajnë tabela të mëdha (>4KB)."""
    preview_df = _prepare_df_for_export(df)
    html = preview_df.to_html(
        classes="table table-striped table-bordered table-sm mb-0",
        index=False,
        header=False,
        na_rep="",
    )
    PREVIEW_HTML_PATH.write_text(html, encoding="utf-8")
    meta = {
        "last_download": out_name,
        "row_count": row_count if row_count is not None else len(df),
        "unknown_businesses": unknown,
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
    if "file" not in request.files or not request.files["file"].filename:
        flash("Zgjidhni një skedar Excel.", "warning")
        return redirect(url_for("dashboard"))

    file = request.files["file"]
    original_name = file.filename
    filename = secure_filename(original_name)
    if not filename.lower().endswith((".xlsx", ".xls")):
        flash("Lejohen vetëm skedarë .xlsx ose .xls.", "warning")
        return redirect(url_for("dashboard"))

    save_path = UPLOAD_FOLDER / filename
    file.save(save_path)

    try:
        settings = load_settings()
        df, unknown, out_name, row_count = transform_excel(str(save_path), settings)
        save_last_upload(save_path)
        save_dashboard_preview(df, unknown, out_name, row_count)

        username = current_user.id if current_user.is_authenticated else "admin"
        log_job(original_name, out_name, row_count, username)

        flash(
            f"Excel u transformua me sukses. {row_count} rreshta të dhënash u përpunuan "
            f"(të gjitha kolonat u ruajtën).",
            "success",
        )
        if unknown:
            flash(
                f"Biznese të panjohura ({len(unknown)}): {', '.join(unknown[:5])}"
                + ("..." if len(unknown) > 5 else ""),
                "warning",
            )
    except Exception as exc:
        flash(f"Gabim gjatë përpunimit: {exc}", "danger")
    finally:
        if save_path.exists() and save_path != LAST_UPLOAD_FILE:
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
