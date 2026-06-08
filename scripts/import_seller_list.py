"""
Import shitës + kategori nga lista (kolona Shitësi / Kategoria).
Zëvendëson business_categories dhe përditëson mbiemrat (~30%).
"""
import json
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SETTINGS_PATH = BASE / "settings.json"

# MOS PËRDOR — lista e vjetër e gabuar (dyqane Kosovo nga imazh, jo Excel-i yt).
# Import vetëm nga imports/seller_list.xlsx
SELLER_ROWS_DEPRECATED = [
    # Supermarket / Market
    ("VIVA FRESH STORE", "supermarket"),
    ("INTEREX", "supermarket"),
    ("ETC", "supermarket"),
    ("MERIDIAN EXPRESS", "supermarket"),
    ("SPAR", "supermarket"),
    ("SUPER VIVA", "supermarket"),
    ("MAXI", "supermarket"),
    ("CONAD", "supermarket"),
    # Karburant
    ("HIB PETROL", "karburant"),
    ("KOSOVA PETROL", "karburant"),
    # Qendër tregtare
    ("ALBI MALL", "qender tregtare"),
    ("GALERIA SHOPPING MALL", "qender tregtare"),
    ("PRISHTINA MALL", "qender tregtare"),
    ("VIVA FRESH MALL", "qender tregtare"),
    ("THE VILLAGE SHOPPING & LEISURE", "qender tregtare"),
    ("GRAND STORE", "qender tregtare"),
    ("MINIMAX", "qender tregtare"),
    ("ABI CARSHIA", "qender tregtare"),
    ("ROYAL MALL", "qender tregtare"),
    ("PALMA MALL", "qender tregtare"),
    ("CITY PARK", "qender tregtare"),
    ("QTU", "qender tregtare"),
    ("TEG", "qender tregtare"),
    ("RING CENTER", "qender tregtare"),
    ("TOPTANI SHOPPING CENTER", "qender tregtare"),
    ("EAST GATE MALL", "qender tregtare"),
    ("SKOPJE CITY MALL", "qender tregtare"),
    ("CAPITOL MALL", "qender tregtare"),
    ("RAMSTORE MALL", "qender tregtare"),
    ("VERO CENTER", "qender tregtare"),
    ("GTC", "qender tregtare"),
    # Veshmbathje
    ("ZARA", "veshmbathje"),
    ("BERSHKA", "veshmbathje"),
    ("PULL & BEAR", "veshmbathje"),
    ("STRADIVARIUS", "veshmbathje"),
    ("MASSIMO DUTTI", "veshmbathje"),
    ("OYSHO", "veshmbathje"),
    ("MANGO", "veshmbathje"),
    ("LC WAIKIKI", "veshmbathje"),
    ("KOTON", "veshmbathje"),
    ("DEFACTO", "veshmbathje"),
    ("NEW YORKER", "veshmbathje"),
    ("C&A", "veshmbathje"),
    ("H&M", "veshmbathje"),
    ("RESERVED", "veshmbathje"),
    ("SINSAY", "veshmbathje"),
    ("MOHITO", "veshmbathje"),
    ("CROPP", "veshmbathje"),
    ("HOUSE", "veshmbathje"),
    ("TERRANOVA", "veshmbathje"),
    ("CALLIOPE", "veshmbathje"),
    ("US POLO ASSN", "veshmbathje"),
    ("LEVIS", "veshmbathje"),
    ("TOMMY HILFIGER", "veshmbathje"),
    ("CALVIN KLEIN", "veshmbathje"),
    ("GUESS", "veshmbathje"),
    ("HUGO BOSS", "veshmbathje"),
    ("ARMANI EXCHANGE", "veshmbathje"),
    ("DIESEL", "veshmbathje"),
    ("REPLAY", "veshmbathje"),
    ("SPRINGFIELD", "veshmbathje"),
    ("WOMEN'S SECRET", "veshmbathje"),
    ("YAMAMAY", "veshmbathje"),
    ("TEZENIS", "veshmbathje"),
    ("CALZEDONIA", "veshmbathje"),
    ("INTIMISSIMI", "veshmbathje"),
    ("LINDEX", "veshmbathje"),
    ("ORCHESTRA", "veshmbathje"),
    ("OKAIDI", "veshmbathje"),
    ("BLUKIDS", "veshmbathje"),
    ("MOTHERCARE", "veshmbathje"),
    ("CHICCO", "veshmbathje"),
    # Elektronikë / pajisje
    ("NEPTUN", "elektronike"),
    ("AZTECH", "elektronike"),
    ("GORENJE", "pajisje shtepiake"),
    # Këpucë / sport
    ("TIMBERLAND", "kepuce"),
    ("ADIDAS", "sport"),
    ("NIKE", "sport"),
    ("PUMA", "sport"),
    ("REEBOK", "sport"),
    ("SKECHERS", "kepuce"),
    ("INTERSPORT", "sport"),
    ("SPORT VISION", "sport"),
    ("BUZZ", "sport"),
    ("THE ATHLETE'S FOOT", "sport"),
    ("DEICHMANN", "kepuce"),
    ("CCC", "kepuce"),
    ("OFFICE SHOES", "kepuce"),
    ("ECCO", "kepuce"),
    ("GEOX", "kepuce"),
    ("TAMARIS", "kepuce"),
    ("BATA", "kepuce"),
    ("ALDO", "kepuce"),
    # Kozmetikë / aksesorë
    ("ROSSMANN", "kozmetike"),
    ("DM", "kozmetike"),
    ("PANDORA", "aksesore"),
    ("SWAROVSKI", "aksesore"),
    ("CARPISA", "aksesore"),
    ("PARFOIS", "aksesore"),
    ("MINISO", "aksesore"),
    # Lodra / argëtim / ushqim
    ("JUMBO", "lodra"),
    ("KIDS CINEMA", "argetim"),
    ("CINEPLEXX", "argetim"),
    ("BUSHIDO", "restorant"),
    ("SOMA SLOW FOOD", "restorant"),
    ("BABAGHANUSH", "restorant"),
    ("PISHAT", "restorant"),
    ("LIBURNIA", "restorant"),
    ("TIFFANY", "restorant"),
    ("RENAISSANCE", "restorant"),
    ("COUNTRY HOUSE", "restorant"),
    ("GRECO", "restorant"),
    ("EL GRECO", "restorant"),
    ("MEZE HOUSE", "restorant"),
    ("PANE VINO", "restorant"),
    ("NAPOLI", "restorant"),
    ("GUSTO", "restorant"),
    ("PINOCCHIO", "restorant"),
    ("VILA GERMIA", "restorant"),
    ("VILA PARK", "restorant"),
    ("VILA BLED", "restorant"),
    ("VILA 100", "restorant"),
    ("VILA 31", "restorant"),
    ("VILA 21", "restorant"),
    ("SOMA BOOK STATION", "kafene"),
    ("HALF & HALF", "kafene"),
    ("DIT' E NAT'", "kafene"),
    ("MIQT PUB", "pub"),
    ("BEER GARDEN", "pub"),
    ("SABRINA", "embeltore"),
    ("MISSINI", "embeltore"),
    ("ELIDA", "embeltore"),
]

# Mbiemra nga fundi i listës (+ emra të plotë)
SURNAME_POOL = [
    "Bikliqi", "Muca", "Gashi", "Krasniqi", "Berisha", "Hoxha", "Leka", "Prifti",
    "Dibra", "Marku", "Kola", "Shala", "Morina", "Bytyqi", "Kelmendi", "Thaqi",
    "Hoti", "Kastrati", "Kryeziu", "Rexhepi", "Ahmeti", "Bajrami", "Ramadani",
    "Jashari", "Rugova", "Haradinaj", "Kurti", "Osmani", "Konjufca", "Abdixhiku",
    "Limaj", "Veseli", "Thaci", "Pacolli", "Mustafa", "Sejdiu",
]


def norm_key(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def rows_from_excel(path: Path) -> list[tuple[str, str]]:
    import pandas as pd

    df = pd.read_excel(path, header=None, engine="openpyxl")
    rows = []
    for _, row in df.iterrows():
        if len(row) < 2:
            continue
        seller = str(row.iloc[0]).strip()
        cat = str(row.iloc[1]).strip().lower()
        if not seller or seller.lower() in ("nan", "shitesi", "shitësi", "seller"):
            continue
        if not cat or cat == "nan":
            continue
        rows.append((seller, cat))
    return rows


def build_business_categories(rows: list[tuple[str, str]]):
    result = {}
    for seller, cat in rows:
        seller = seller.strip()
        cat = cat.strip().lower()
        if seller not in result:
            result[seller] = []
        if cat not in result[seller]:
            result[seller].append(cat)
    return result


def main():
    import sys

    excel_path = BASE / "imports" / "seller_list.xlsx"
    if len(sys.argv) > 1:
        excel_path = Path(sys.argv[1])

    if excel_path.exists():
        source_rows = rows_from_excel(excel_path)
        print(f"Lexuar {len(source_rows)} rreshta nga {excel_path}")
    else:
        print("ERROR: Vendos skedarin Excel ne imports/seller_list.xlsx (kolona A=Shitesi, B=Kategoria)")
        raise SystemExit(1)

    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)

    old_biz = settings.get("business_categories", {})
    old_keys = {norm_key(k): k for k in old_biz}
    import_biz = build_business_categories(source_rows)

    newly_added = []
    categories_replaced = []
    merged_biz = dict(old_biz)

    for name, cats in import_biz.items():
        nk = norm_key(name)
        if nk not in old_keys:
            newly_added.append(name)
            merged_biz[name] = cats
        else:
            old_name = old_keys[nk]
            if merged_biz.get(old_name) != cats:
                categories_replaced.append(old_name)
            merged_biz[old_name] = cats  # zëvendëson kategoritë e vjetra

    random.seed(42)
    sample_size = max(1, round(len(SURNAME_POOL) * 0.30))
    sampled_surnames = sorted(random.sample(SURNAME_POOL, sample_size))

    settings["business_categories"] = merged_biz
    settings["name_cleaning_rules"] = {"surnames": sampled_surnames}
    settings["surnames"] = sampled_surnames

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    report_path = BASE / "data" / "import_sellers_report.txt"
    report_path.parent.mkdir(exist_ok=True)
    lines = [
        f"Shitës në listë import: {len(import_biz)}",
        f"Gjithsej në settings: {len(merged_biz)}",
        f"Të rinj (nuk ishin në settings): {len(newly_added)}",
        f"Kategori të zëvendësuara: {len(categories_replaced)}",
        f"Mbiemra random (~30%): {len(sampled_surnames)}",
        "",
        "=== SHITËS TË RINJ ===",
    ]
    lines.extend(f"  + {n} → {import_biz[n]}" for n in newly_added)
    lines.extend(["", "=== KATEGORI TË REJA (ishin në settings) ==="])
    lines.extend(
        f"  ~ {n} → {merged_biz.get(n, import_biz.get(n))}"
        for n in sorted(categories_replaced)[:80]
    )
    if len(categories_replaced) > 80:
        lines.append(f"  ... dhe {len(categories_replaced) - 80} të tjerë")
    lines.extend(["", "=== MBİEMRA (30%) ==="])
    lines.extend(f"  {s}" for s in sampled_surnames)

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(report_path.read_text(encoding="utf-8").encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    main()
