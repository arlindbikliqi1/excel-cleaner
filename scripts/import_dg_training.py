#!/usr/bin/env python3
"""Importon DG LIST.xlsx → data/product_training.json + fjalëkyçe në settings."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from product_training import norm_category, strip_product_noise

DG_PATH = BASE / "uploads" / "DG LIST.xlsx"
OUT_PATH = BASE / "data" / "product_training.json"
SETTINGS_PATH = BASE / "settings.json"

STOP_PHRASE_WORDS = frozenset(
    {"cop", "cope", "pako", "per", "dhe", "me", "te", "nga", "post", "posta", "fn", "x"}
)

MANUAL_PHRASES = {
    "mini flashlight": "drite led",
    "decoraction lamp": "drite led",
    "drita solare": "drite led",
    "ngjites dy komponentesh": "aksesore",
    "krem per fytyr": "krem",
    "loder rosak": "loder",
    "loder rosaku": "loder",
    "pastrues gjamash": "pastrues gjamash",
    "pastrues xhami": "pastrues gjamash",
    "mbulesa": "mbulese",
    "vaj lubrifikues": "suplimente",
    "kapse bimesh": "aksesore",
    "tapet ujor": "aksesore",
    "top fleksibil": "aksesore",
    "audio reciver": "aksesore",
    "shtresa ortopedike": "aksesore",
    "raft mbi tv": "raft plastike",
    "kreher per mjekerr": "aksesore",
    "mini blinder": "mini blinder",
}

MANUAL_KEYWORDS = {
    "kr": "krem",
    "ndrrim": "bluze",
    "kompl": "bluze",
    "ulliri": "mbulese",
    "aerobin": "mbulese",
    "flashlight": "drite led",
    "lamp": "drite led",
    "drita": "drite led",
    "solare": "drite led",
    "ngjites": "aksesore",
    "kapse": "aksesore",
    "bim": "aksesore",
    "bimesh": "aksesore",
    "lubrifikues": "suplimente",
    "serum": "suplimente",
    "detoks": "fasho lidhese",
    "kinoki": "fasho lidhese",
    "varikoze": "fasho lidhese",
    "fasha": "fasho lidhese",
}


def rows_from_excel(path: Path) -> list[tuple[str, str]]:
    import pandas as pd

    df = pd.read_excel(path, header=None, engine="openpyxl")
    rows = []
    for _, row in df.iterrows():
        if len(row) < 4:
            continue
        src, tgt = row.iloc[2], row.iloc[3]
        if src is None or tgt is None:
            continue
        src_s = str(src).strip()
        tgt_s = str(tgt).strip()
        if not src_s or src_s.lower() in ("nan", "none"):
            continue
        if not tgt_s or tgt_s.lower() in ("nan", "none"):
            continue
        rows.append((src_s, norm_category(tgt_s)))
    return rows


def build_exact_pairs(rows: list[tuple[str, str]]) -> dict[str, str]:
    """Çdo produkt → kategoria më e shpeshtë në DG LIST."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for src, cat in rows:
        key = strip_product_noise(src)
        if key:
            votes[key][cat] += 1
    return {key: counter.most_common(1)[0][0] for key, counter in votes.items()}


def extract_phrases(rows: list[tuple[str, str]], exact: dict[str, str]) -> dict[str, str]:
    phrases: dict[str, str] = dict(exact)
    by_cat: dict[str, Counter] = defaultdict(Counter)

    for src, cat in rows:
        clean = strip_product_noise(src)
        words = [w for w in re.findall(r"[a-zà-žë0-9]+", clean) if w not in STOP_PHRASE_WORDS]
        for i in range(len(words)):
            for j in range(i + 2, min(i + 5, len(words)) + 1):
                phrase = " ".join(words[i:j])
                if len(phrase) >= 5:
                    by_cat[cat][phrase] += 1

    for cat, counter in by_cat.items():
        for phrase, count in counter.most_common(10):
            if count >= 2 and phrase not in phrases:
                phrases[phrase] = cat

    for phrase, cat in MANUAL_PHRASES.items():
        p = strip_product_noise(phrase)
        if p not in phrases:
            phrases[p] = norm_category(cat)

    return dict(sorted(phrases.items(), key=lambda x: (-len(x[0]), x[0])))


def keyword_updates(phrases: dict[str, str]) -> dict[str, str]:
    kw = dict(MANUAL_KEYWORDS)
    for phrase, cat in phrases.items():
        if len(phrase) <= 40:
            kw[phrase] = cat
        for token in phrase.split():
            if 2 <= len(token) <= 12 and token not in STOP_PHRASE_WORDS:
                if token not in kw:
                    kw[token] = cat
    return kw


def main():
    excel = DG_PATH
    if len(sys.argv) > 1:
        excel = Path(sys.argv[1])
    if not excel.exists():
        print(f"Skedari nuk ekziston: {excel}")
        raise SystemExit(1)

    rows = rows_from_excel(excel)
    exact = build_exact_pairs(rows)
    phrases = extract_phrases(rows, exact)

    seen = set()
    pairs = []
    for src, _ in rows:
        key = strip_product_noise(src)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"source": src, "category": exact[key]})

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs, "phrases": phrases}, f, ensure_ascii=False, indent=2)

    with open(SETTINGS_PATH, encoding="utf-8") as f:
        settings = json.load(f)

    merged_kw = dict(settings.get("product_keywords", {}))
    merged_kw.update(keyword_updates(phrases))
    settings["product_keywords"] = dict(sorted(merged_kw.items(), key=lambda x: x[0].lower()))

    biz = settings.setdefault("business_categories", {})
    top = biz.setdefault("Toponline", [])
    norm_top = {c.lower().replace("ë", "e") for c in top}
    for cat in [
        "drite led", "suplimente", "mbulese", "bluze", "veshje", "tuta",
        "kemishe", "shampo", "fasho lidhese", "perde magnetike",
        "raft kendor", "aparat per ngjyrosje", "set tushi",
        "aksesore varese", "aksesore mask", "jastek ortopedik",
        "pastrues gypi", "arke", "vegel pune", "dogana", "mini blinder",
    ]:
        if cat.replace("ë", "e") not in norm_top:
            top.append(cat)
            norm_top.add(cat.replace("ë", "e"))

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    print(f"Importuar {len(pairs)} çifte, {len(phrases)} fraza → {OUT_PATH}")
    print(f"Fjalëkyçe në settings: {len(merged_kw)}")


if __name__ == "__main__":
    main()
