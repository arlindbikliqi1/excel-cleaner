#!/usr/bin/env python3
"""Importon lista referencë LINDI (Pershkrimi → kategori) + përditëson shitësit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
sys.path.insert(0, str(BASE))

from _bootstrap_venv import ensure_project_venv

ensure_project_venv()

from product_training import (
    TRAINING_PATH,
    get_category_display,
    import_multiple_cleaned_lists,
    match_training_category_with_mode,
    reload_training_cache,
)

SETTINGS_PATH = BASE / "settings.json"
UPLOADS_DIR = BASE / "uploads"

VERIFY_SAMPLES = [
    "hekur sf-9134",
    "Shtupe sonifer sf 2253",
    "Thithese Hero 3001",
    "Fustan",
    "Pastruese me avull DH-4006",
]


def discover_reference_paths() -> list[Path]:
    """Gjen automatikisht të gjitha listat LINDI në uploads/."""
    paths: list[Path] = []
    lista = UPLOADS_DIR / "LINDI LISTA DOGANA.xlsx"
    if lista.exists():
        paths.append(lista)

    for path in sorted(UPLOADS_DIR.glob("LINDI DOGANA *.xlsx"), key=lambda p: p.name.lower()):
        if "RAW" in path.stem.upper():
            continue
        paths.append(path)

    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def merge_business_categories(biz_cats: dict) -> int:
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        settings = json.load(f)
    biz = settings.setdefault("business_categories", {})
    updated = 0
    for name, cats in biz_cats.items():
        existing = biz.setdefault(name, [])
        norm_existing = {c.lower().replace("ë", "e") for c in existing}
        for cat in cats:
            if cat.lower().replace("ë", "e") not in norm_existing:
                existing.append(cat)
                norm_existing.add(cat.lower().replace("ë", "e"))
                updated += 1
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return updated


def verify_import(pair_count: int) -> None:
    reload_training_cache()
    print(f"\nTrajnimi u ruajt: {TRAINING_PATH.resolve()}")
    if TRAINING_PATH.exists():
        print(f"Madhësia: {TRAINING_PATH.stat().st_size:,} bytes")
    if pair_count < 500:
        print("KUJDES: Çifte shumë pak — kontrolloni që Excel-et janë në uploads/.")

    print("\nKontroll i shpejtë:")
    for sample in VERIFY_SAMPLES:
        cat, mode = match_training_category_with_mode(sample)
        label = get_category_display(cat) if cat else "(pa përputhje)"
        print(f"  {sample!r} -> {label!r} [{mode or 'none'}]")


def main():
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = discover_reference_paths()

    if not paths:
        print("Asnjë skedar referencë LINDI nuk u gjet në uploads/.")
        print("Vendosni Excel-et (LINDI LISTA DOGANA.xlsx, LINDI DOGANA 2/3/5.xlsx) dhe provoni përsëri.")
        raise SystemExit(1)

    missing = [p for p in paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"Skedari nuk ekziston: {p}")
        raise SystemExit(1)

    print("Skedarët që do importohen:")
    for p in paths:
        print(f"  - {p.name}")

    result = import_multiple_cleaned_lists(paths, merge_with_existing=False)
    added_cats = merge_business_categories(result["biz_categories"])

    print(f"\nImportuar {result['rows']} rreshta nga {len(paths)} skedarë")
    print("Skedarët:", ", ".join(result.get("files", [])))
    print(f"Çifte globale: {result['pairs']}")
    print(f"Biznese me trajnim: {result['businesses']}")
    print(f"Kategori të reja në settings: {added_cats}")

    verify_import(result["pairs"])
    print("\nNëse serveri është duke u ekzekutuar, rinisni (Ctrl+C pastaj start.bat / ./start.sh).")


if __name__ == "__main__":
    main()
