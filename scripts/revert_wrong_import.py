"""Heq shitësit e shtuar gabimisht nga import_seller_list (dyqane Kosovo, jo lista jote)."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SETTINGS_PATH = BASE / "settings.json"

# Emrat e shtuar gabimisht (lista e gabuar nga imazhi)
from import_seller_list import SELLER_ROWS_DEPRECATED

WRONG = {row[0].strip() for row in SELLER_ROWS_DEPRECATED}
WRONG_NORM = {" ".join(n.lower().split()) for n in WRONG}

ORIGINAL_SURNAMES = [
    "Bikliqi", "Gashi", "Krasniqi", "Berisha", "Hoxha",
    "Leka", "Prifti", "Dibra", "Marku", "Kola",
]


def norm_key(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def main():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)

    biz = settings.get("business_categories", {})
    removed = []
    kept = {}
    for name, cats in biz.items():
        if norm_key(name) in WRONG_NORM or name.strip() in WRONG:
            removed.append(name)
        else:
            kept[name] = cats

    settings["business_categories"] = kept
    settings["name_cleaning_rules"] = {"surnames": ORIGINAL_SURNAMES}
    settings["surnames"] = ORIGINAL_SURNAMES

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    print(f"Hequr {len(removed)} shites te gabuar.")
    print(f"Mbetur {len(kept)} shites (lista jote e vjeter).")
    print(f"Mbiemra rikthyer: {len(ORIGINAL_SURNAMES)}")


if __name__ == "__main__":
    main()
