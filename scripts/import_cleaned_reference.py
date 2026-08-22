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

from product_training import import_multiple_cleaned_lists

SETTINGS_PATH = BASE / "settings.json"
DEFAULT_PATHS = [
    BASE / "uploads" / "LINDI LISTA DOGANA.xlsx",
    BASE / "uploads" / "LINDI DOGANA 2.xlsx",
    BASE / "uploads" / "LINDI DOGANA 3.xlsx",
]


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


def main():
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = [p for p in DEFAULT_PATHS if p.exists()]

    if not paths:
        print("Asnjë skedar referencë nuk u gjet.")
        raise SystemExit(1)

    for p in paths:
        if not p.exists():
            print(f"Skedari nuk ekziston: {p}")
            raise SystemExit(1)

    result = import_multiple_cleaned_lists(paths, merge_with_existing=False)
    added_cats = merge_business_categories(result["biz_categories"])

    print(f"Importuar {result['rows']} rreshta nga {len(paths)} skedarë")
    print("Skedarët:", ", ".join(result.get("files", [])))
    print(f"Çifte globale: {result['pairs']}")
    print(f"Biznese me trajnim: {result['businesses']}")
    print(f"Kategori të reja në settings: {added_cats}")


if __name__ == "__main__":
    main()
