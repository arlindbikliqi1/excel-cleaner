#!/usr/bin/env python3
"""
Sinkronizon nga DG LIST.xlsx:
- product_keywords (shkurtesa: bluz→bluze, kr→krem, …)
- product_training (pa mapime të gabuara fustan→bluze)
- business_categories (lista e bizneseve + kategoritë nga përdoruesi)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from product_training import (
    CATEGORY_CANONICAL,
    norm_category,
    normalize_product_text,
    reload_training_cache,
    strip_product_noise,
)

SETTINGS_PATH = BASE / "settings.json"
DG_PATH = BASE / "uploads" / "DG LIST.xlsx"
TRAINING_PATH = BASE / "data" / "product_training.json"

# Lista e bizneseve nga përdoruesi (emër → kategori)
BUSINESS_IMPORT = """
Produkte 123 → suplimente
A Fashion → tuta, t-shirt
LFK → kemishe
Simply → kemishe
Perla Store → kemishe, bluze
ITECH → aksesore, tuta
Americanshoppingonline → tuta, t-shirt, suplimente, veshje
Butiku Enisi → t-shirt, bluze, fustan, tuta
Andrra Online → suplimente, shampo, krem, fasho lidhese
KASTRATI FASHION → veshje, bluze, tuta, fustan, pantollona, kemishe
Toponline → aksesore, pastrues gjamash, aksesore depilatore, korset, krem, loder, loder rosaku, raft plastike, mikrofon argetues, drite led, top fleksibil, ngjites dy komponentesh, mini blinder
Butiku Zojzi → bluze, kemishe, pantollona
Regina → pantollona, veshje
Xafa Online → veshje
LUNA MODA → veshje, bluze
DUA → veshje, bluze
PorosiDiva → bluze, pantollona
Plus Tekstil → pantollona, veshje, bluze
AM ONLINE1 → veshje, bluze, kemishe
AM ONLINE3 → tuta, veshje
Perfect Shop → mbulese, aksesore, mbulese divani
ZONE → fasho lidhese, drite led, aksesore
ZONE1 → loder rosaku, kosh per mbeturina, raft plastike, veshje, aksesore
LentiLPP → bluze, tuta, pantollona, veshje, mbulese
Lori Fashion → bluze
ARBI → tuta, t-shirt, bluze, fustan
SHOPONLINE → suplimente, krem, fasho lidhese
DORASHOP → fasho lidhese, krem
FLETA SHOP → suplimente, aksesore, fasho lidhese, krem
Rreth Femrave → bluze
INFINITYSHOP → krem, fasho lidhese, suplimente
Sara Shop Veshje Islame → bluze, pantollona, veshje, mbulese
R.STORE → pantollona, bluze
R.STORE1 → tuta, bluze
GT-01 → tuta, bluze, pantollona, veshje
MARMO → tuta, kemishe, bluze
FASHIONA → bluze, pantollona, fustan, tuta, veshje
ENMODA → pantollona, bluze, veshje
CLOTHINGSV → bluze, kemishe
Lux Aksesore → aksesore syze
janinafashionstore → pantollona, bluze
AJLA ONLINE → pantollona, bluze
DYQANISHOP → aksesore syze, mbulese, veshje, raft kendor, ulese, spoiler, perde magnetike, shtrenguese per gjunje, loder, suplimente, set tushi, jastek ortopedik, prerese pllake, shampo, aparat per ngjyrosje, aksesore mask, aksesore rrota, aksesore, vegel pune, drejtuese per shpine, shtypese qeliku, pastrues gypi, jastek per qafe, raft organizues, sprej polir, krem
SOLEMI01 → jastek per qafe, aksesore varese, aksesore, vegel pune, aksesore karikues, raft kendore, veshje, aparat per ngjyrosje, prerese pllake, loder, drite led, arke, shampo, riparues muri, aksesore kufje, aksesore mask, shtypese qeliku, jastek ortopedik, aksesore qels, mbulese, set tushi, aksesore syze, pastrues gypi, drejtuese per shpine
LEA FASHION → veshje, bluze
NOVA → veshje, pantollona
DIMAL FASHION → pantollona, bluze
DONA DRESS → pantollona, tuta, veshje, fustan
Meral - Women Store → mbulese, bluze
ToniOnline01 → aksesore, blender dore, raft plastike, veshje, suplimente, drite led, loder
Buna → veshje, bluze
Lorifashion1 → bluze, tuta, pantollona
LuxuryFashion → veshje, bluze, fustan, pantollona, tuta
LORIFASHION2 → bluze, tuta, fustan, veshje
SARASHOP MODEST → bluze, tuta, fustan, veshje
Runis → mbulese
SIVEGETA → vegel pune
NOIRCORP1 → bluze, fustan
MallofBallkan → aksesore karikues, drite led, paisje per ushtrime, mbulese, loder
Niki Tekstil → bluze
HALL OF FAME SHOP → bluze, tuta
ButikuLF → bluze
Butiku Erdi → kemishe, veshje, bluze
ZazaKosova → aksesore syze
LZAN → bluze
Donikaloci → korset
LabelNue1 → bluze
Butiku Rina → tuta, aksesore, bluze, veshje
Online1 → aksesore
Bosforidesign → aksesore, korset
ReOnline → mbulese
Donacenter → mbulese, bluze
Maxx → bluze, veshje, pantollona, kemishe
Butiku Albi → t-shirt, bluze, tuta, fustan, pantollona, veshje
Tarashop SAS_veshjeislame → t-shirt, mbulese, bluze
Onlin_nora1 → veshje, tuta
MARBLE → aksesore
Amra Kids → bluze, mbulese
HOMECARCAFET → mbulese divani, mbulese
HomeTekstile - Sara Shop → mbulese divani, mbulese
Biokoz → krem
Marabella.Kosova → aksesore, aksesore syze
SECOND HAND KS → pantollona, tuta, bluze, veshje
Cozy → mbulese
Butiku Arti → bluze
eerrzzaa → tuta, bluze
Nyx cosmetics → aksesore
Butiku77 → bluze
Lenti → veshje, bluze, pantollona, t-shirt
LUNA CENTER → bluze, kemishe, tuta, veshje
AM ONLINE5 → veshje, bluze, kemishe
LettiFashion → bluze, veshje, kemishe, t-shirt, tuta
LENTI ÇAGLLAVIC → t-shirt, veshje
V D → tuta, fustan, fund, pantollona, bluze, veshje, kemishe, xhakete, t-shirt
DC SH → bluze
DC F → bluze
"""

NAME_ALIASES = {
    "porosidiva": "Porosidiva",
    "donikaloci": "DonikaLOCI",
    "biokoz": "Biokozmetika",
    "nyx cosmetics": "Nyxonline",
}

MANUAL_KEYWORDS = {
    "bluz": "bluze",
    "blu": "bluze",
    "bluza": "bluze",
    "bluzet": "bluze",
    "bluzat": "bluze",
    "kem": "kemishe",
    "kemis": "kemishe",
    "kemish": "kemishe",
    "kemishat": "kemishe",
    "kemishet": "kemishe",
    "tut": "tuta",
    "tute": "tuta",
    "tutat": "tuta",
    "pant": "pantollona",
    "pantallon": "pantollona",
    "pantallona": "pantollona",
    "fust": "fustan",
    "fustane": "fustan",
    "fustana": "fustan",
    "fustanet": "fustan",
    "veshj": "veshje",
    "veshjet": "veshje",
    "shamp": "shampo",
    "shampoo": "shampo",
    "aks": "aksesore",
    "aksesor": "aksesore",
    "aksesoret": "aksesore",
    "mbul": "mbulese",
    "mbulesa": "mbulese",
    "sup": "suplimente",
    "supliment": "suplimente",
    "suplimet": "suplimente",
    "suplimete": "suplimente",
    "kreme": "krem",
    "krema": "krem",
    "kr": "krem",
    "tshirt": "t-shirt",
    "tshir": "t-shirt",
    "t shirt": "t-shirt",
    "trenerka": "tuta",
    "trenerk": "tuta",
    "maic": "bluze",
    "maice": "bluze",
    "komplet": "bluze",
    "komplete": "bluze",
    "fustan": "fustan",
    "fustanin": "fustan",
    "flashlight": "drite led",
    "drita": "drite led",
    "ngjites": "aksesore",
    "loder rosak": "loder",
    "lodra": "loder",
    "pastrues xhamash": "pastrues gjamash",
    "pastrues gjamashi": "pastrues gjamash",
    "sulpimente": "suplimente",
    "jastak ortopedik": "jastek ortopedik",
    "drejtues shpine": "drejtuese per shpine",
    "qetsues shpine": "drejtuese per shpine",
}

STOP_TOKENS = frozenset(
    {"cop", "cope", "pako", "per", "dhe", "me", "te", "nga", "post", "posta", "fn", "euro", "e"}
)

CATEGORY_WORDS = frozenset(
    {
        "bluze", "kemishe", "tuta", "pantollona", "fustan", "veshje", "krem", "shampo",
        "suplimente", "aksesore", "mbulese", "loder", "t-shirt", "xhakete", "fund",
        "drite led", "fasho lidhese", "korset", "mbulese divani",
    }
)


def norm_biz(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower()).replace(".", " ")


def parse_business_import() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in BUSINESS_IMPORT.strip().splitlines():
        line = line.strip()
        if not line or "→" not in line:
            continue
        name, cats = line.split("→", 1)
        name = name.strip()
        categories = [norm_category(c.strip()) for c in cats.split(",") if c.strip()]
        nk = norm_biz(name)
        key = NAME_ALIASES.get(nk, name)
        if key not in result:
            result[key] = []
        for c in categories:
            if c not in result[key]:
                result[key].append(c)
    return result


def rows_from_dg(path: Path) -> list[tuple[str, str]]:
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


def extract_keywords_from_dg(rows: list[tuple[str, str]]) -> dict[str, str]:
    kw = dict(MANUAL_KEYWORDS)
    by_cat: dict[str, Counter] = defaultdict(Counter)

    for src, cat in rows:
        clean = strip_product_noise(src)
        for tok in re.findall(r"[a-zà-žë]{2,}", clean):
            if tok in STOP_TOKENS:
                continue
            by_cat[cat][tok] += 1

    for cat, ctr in by_cat.items():
        cat_norm = norm_category(cat)
        for tok, cnt in ctr.most_common(20):
            if tok == cat_norm or cat_norm.startswith(tok + " "):
                continue
            if tok in CATEGORY_WORDS:
                kw[tok] = tok
                continue
            if cnt >= 2 and len(tok) <= 8:
                if tok not in kw or len(cat_norm) > len(kw.get(tok, "")):
                    kw[tok] = cat_norm

    return kw


def build_training(rows: list[tuple[str, str]]) -> tuple[list[dict], dict[str, str]]:
    votes: dict[str, Counter] = defaultdict(Counter)
    for src, cat in rows:
        key = strip_product_noise(src)
        if key:
            votes[key][cat] += 1

    exact: dict[str, str] = {}
    for key, counter in votes.items():
        cat = counter.most_common(1)[0][0]
        # nëse burimi është vetë emri i kategorisë, mos mapo gabim
        key_norm = norm_category(key)
        if key_norm in CATEGORY_WORDS or key_norm in {norm_category(c) for c in counter}:
            if key_norm in counter:
                cat = key_norm
            elif key_norm in CATEGORY_CANONICAL.values():
                cat = key_norm
        exact[key] = cat

    phrases = dict(exact)
    for src, cat in rows:
        clean = strip_product_noise(src)
        if len(clean) >= 5:
            phrases[clean] = exact.get(strip_product_noise(src), cat)

    # frazat që janë vetë kategori → vetvetja
    for word in CATEGORY_WORDS:
        phrases[word] = word
        for alias in (word + "a", word + "e", word + "at"):
            if alias in phrases and phrases[alias] != word:
                if word in ("bluze", "fustan", "kemishe", "tuta", "veshje"):
                    phrases[alias] = word

    seen: set[str] = set()
    pairs = []
    for src, _ in rows:
        key = strip_product_noise(src)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"source": src, "category": exact[key]})

    return pairs, dict(sorted(phrases.items(), key=lambda x: (-len(x[0]), x[0])))


def merge_businesses(settings: dict, imported: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    biz = settings.setdefault("business_categories", {})
    lookup = {norm_biz(k): k for k in biz}
    new_businesses: list[str] = []
    updated: list[str] = []

    for name, cats in imported.items():
        nk = norm_biz(name)
        resolved = NAME_ALIASES.get(nk, name)
        key = lookup.get(norm_biz(resolved), resolved)
        if norm_biz(key) not in lookup:
            biz[key] = []
            lookup[norm_biz(key)] = key
            new_businesses.append(key)

        existing_norm = {norm_category(c): c for c in biz[key]}
        added = []
        for cat in cats:
            cn = norm_category(cat)
            if cn not in existing_norm:
                biz[key].append(cat)
                existing_norm[cn] = cat
                added.append(cat)
        if added:
            updated.append(key)
        biz[key] = sorted(biz[key], key=lambda x: x.lower())

    settings["business_categories"] = dict(sorted(biz.items(), key=lambda x: x[0].lower()))
    return new_businesses, updated


def main():
    dg = DG_PATH
    if len(sys.argv) > 1:
        dg = Path(sys.argv[1])
    if not dg.exists():
        print(f"Mungon: {dg}")
        raise SystemExit(1)

    rows = rows_from_dg(dg)
    pairs, phrases = build_training(rows)
    keywords = extract_keywords_from_dg(rows)
    imported = parse_business_import()

    TRAINING_PATH.parent.mkdir(exist_ok=True)
    with open(TRAINING_PATH, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs, "phrases": phrases}, f, ensure_ascii=False, indent=2)

    with open(SETTINGS_PATH, encoding="utf-8") as f:
        settings = json.load(f)

    merged_kw = dict(settings.get("product_keywords", {}))
    merged_kw.update(keywords)
    settings["product_keywords"] = dict(sorted(merged_kw.items(), key=lambda x: x[0].lower()))

    new_biz, updated_biz = merge_businesses(settings, imported)

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    reload_training_cache()

    print(f"DG rreshta: {len(rows)}")
    print(f"Trajnim: {len(pairs)} çifte, {len(phrases)} fraza")
    print(f"Fjalëkyçe: {len(merged_kw)}")
    print(f"Biznese të reja: {len(new_biz)}")
    for n in new_biz:
        print(f"  + {n}")
    print(f"Biznese të përditësuara: {len(updated_biz)}")
    for n in updated_biz[:30]:
        print(f"  ~ {n}")
    if len(updated_biz) > 30:
        print(f"  ... +{len(updated_biz) - 30}")


if __name__ == "__main__":
    main()
